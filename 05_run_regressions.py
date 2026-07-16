# -*- coding: utf-8 -*-
"""
第 05 步：實證迴歸（模型 1 / 2 / 3）。

輸入：04_model_data.csv （限定產業、含交乘項與 LN 規模的模型資料）
輸出：
    1. 05_regression_results.txt  — 完整迴歸結果（人可讀）
    2. 05_regression_coef.csv     — 各模型係數彙總（機器可讀，供論文製表）

模型（對應 study.md）：
    模型 1 基礎效應：
        Y = a + b1·Water + b2·Energy + Controls
    模型 2 水能互補綜效（交乘項）：
        Y = a + b1·Water + b2·Energy + b3·(Water×Energy) + Controls
    模型 3 專項資本支出時間落差（遞延期 t+1/t+3/t+5）：
        Y(t+k) = a + b1·CAPEX + b2·Water + b3·Energy + Controls

估計方法：
    以雙向固定效果面板迴歸（entity + time fixed effects，PanelOLS）為主，
    標準誤採公司叢集穩健（cluster by entity）。
    Water 以「水回收率%」、Energy 以「再生能源使用率」、
    CAPEX 以縮尾後「水電設備CAPEX新增額_w」為代表變數。
    Y 使用縮尾後「Tobins Q_w」（公司價值）與「營業費用率」（營運成本）。
"""

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

INPUT_CSV = "04_model_data.csv"
OUTPUT_TXT = "05_regression_results.txt"
OUTPUT_COEF = "05_regression_coef.csv"

CODE = "證券代碼"
YEAR = "西元年份"

# 變數對應
WATER = "水回收率%"
ENERGY = "再生能源使用率"
INTERACT = "水回收率x再生能源"
CAPEX = "水電設備CAPEX新增額_w"
CONTROLS = ["研究發展費用率", "LN資產總額", "負債比率"]

# 應變數：當期（模型 1、2）
Y_VALUE = "Tobins Q_w"     # 公司價值
Y_COST = "營業費用率"       # 營運成本
DEP_VARS_CURRENT = [Y_VALUE, Y_COST]

# 模型 3 的遞延期應變數欄名樣板
LEAD_PERIODS = (1, 3, 5)


def rename_for_formula(cols):
    """把含特殊字元的欄名映射成 patsy/linearmodels 可用的安全變數名。"""
    mapping = {}
    for c in cols:
        safe = (
            c.replace("%", "pct")
            .replace("×", "x")
            .replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("+", "plus")
            .replace("-", "_")
        )
        mapping[c] = safe
    return mapping


def prepare_panel(df: pd.DataFrame) -> pd.DataFrame:
    """設定 (entity, time) 為 MultiIndex，供 PanelOLS 使用。"""
    d = df.copy()
    d[YEAR] = pd.to_numeric(d[YEAR], errors="coerce").astype("Int64")
    d = d.dropna(subset=[CODE, YEAR])
    d = d.set_index([CODE, YEAR])
    return d


def run_panel(df, dep, exog, label, results_lines, coef_rows):
    """執行一個雙向固定效果 PanelOLS，並記錄結果。"""
    cols = [dep] + exog
    sub = df[cols].apply(pd.to_numeric, errors="coerce").dropna()

    # 面板需要足夠的公司數與時間點
    n_entity = sub.index.get_level_values(0).nunique()
    n_time = sub.index.get_level_values(1).nunique()

    header = (
        f"\n{'='*78}\n[{label}]\n"
        f"  應變數 Y = {dep}\n"
        f"  自變數  = {exog}\n"
        f"  觀測數 N = {len(sub)}，公司數 = {n_entity}，年數 = {n_time}\n"
        f"{'-'*78}"
    )
    results_lines.append(header)

    if len(sub) < 20 or n_entity < 5:
        msg = "  ** 樣本過小，略過此模型 **"
        results_lines.append(msg)
        return

    y = sub[dep]
    X = sub[exog]

    try:
        mod = PanelOLS(
            y, X, entity_effects=True, time_effects=True, drop_absorbed=True
        )
        res = mod.fit(cov_type="clustered", cluster_entity=True)
    except Exception as e:  # noqa: BLE001
        # 常見於小樣本 + 固定效果吸收後降秩（如綠電早年多為 0）。
        # 以 check_rank=False 後備估計，並在結果中註記係數可能不穩定。
        try:
            mod = PanelOLS(
                y, X, entity_effects=True, time_effects=True,
                drop_absorbed=True, check_rank=False,
            )
            res = mod.fit(cov_type="clustered", cluster_entity=True)
            results_lines.append(
                f"  ** 注意：設計矩陣降秩（{e}）。已改用 check_rank=False "
                f"估計，部分係數可能因共線性而不穩定，請謹慎解讀。 **"
            )
        except Exception as e2:  # noqa: BLE001
            results_lines.append(f"  ** 估計失敗：{e2} **")
            return

    results_lines.append(str(res))

    # 收集係數表
    for var in res.params.index:
        coef_rows.append({
            "模型": label,
            "應變數": dep,
            "變數": var,
            "係數": res.params[var],
            "標準誤": res.std_errors[var],
            "t值": res.tstats[var],
            "p值": res.pvalues[var],
            "N": int(res.nobs),
            "R2_within": res.rsquared_within,
        })


def main() -> None:
    raw = pd.read_csv(INPUT_CSV, dtype={CODE: str}, low_memory=False)

    # 欄名安全化（linearmodels 對含 % 空白等字元較敏感）
    needed = list({
        WATER, ENERGY, INTERACT, CAPEX, Y_VALUE, Y_COST, *CONTROLS,
        *[f"{Y_VALUE}_t+{k}" for k in LEAD_PERIODS],
        *[f"{Y_COST}_t+{k}" for k in LEAD_PERIODS],
    } & set(raw.columns))
    mapping = rename_for_formula(needed)
    raw = raw.rename(columns=mapping)

    def m(name):  # 取得安全欄名
        return mapping.get(name, name)

    panel = prepare_panel(raw)

    results_lines = []
    coef_rows = []

    controls_s = [m(c) for c in CONTROLS]

    # ---- 模型 1：基礎效應 ----
    for dep in DEP_VARS_CURRENT:
        run_panel(
            panel, m(dep), [m(WATER), m(ENERGY)] + controls_s,
            f"模型1-基礎效應 | Y={dep}", results_lines, coef_rows,
        )

    # ---- 模型 2：水能互補綜效（交乘項）----
    for dep in DEP_VARS_CURRENT:
        run_panel(
            panel, m(dep),
            [m(WATER), m(ENERGY), m(INTERACT)] + controls_s,
            f"模型2-水能互補綜效 | Y={dep}", results_lines, coef_rows,
        )

    # ---- 模型 3：CAPEX 遞延期效應（t+1/t+3/t+5）----
    for base_dep in DEP_VARS_CURRENT:
        for k in LEAD_PERIODS:
            dep_lead = f"{base_dep}_t+{k}"
            if m(dep_lead) not in panel.columns:
                continue
            run_panel(
                panel, m(dep_lead),
                [m(CAPEX), m(WATER), m(ENERGY)] + controls_s,
                f"模型3-遞延期 t+{k} | Y={base_dep}(t+{k})",
                results_lines, coef_rows,
            )

    # 對照表：安全欄名 -> 原始欄名
    inv = {v: k for k, v in mapping.items()}
    legend = "\n變數名對照：\n" + "\n".join(
        f"  {s} = {o}" for o, s in mapping.items()
    )

    text = "TEJ 水電資源實證迴歸結果（雙向固定效果 PanelOLS，公司叢集穩健標準誤）\n"
    text += legend + "\n" + "\n".join(results_lines) + "\n"
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(text)

    coef = pd.DataFrame(coef_rows)
    if not coef.empty:
        coef["變數"] = coef["變數"].map(lambda s: inv.get(s, s))
    coef.to_csv(OUTPUT_COEF, index=False, encoding="utf-8-sig")

    print(f"完成！輸出 {OUTPUT_TXT} 與 {OUTPUT_COEF}")
    print(f"  共執行 {coef['模型'].nunique() if not coef.empty else 0} 個模型設定")
    if not coef.empty:
        key_vars = [WATER, ENERGY, INTERACT, CAPEX]
        show = coef[coef["變數"].isin(key_vars)][
            ["模型", "應變數", "變數", "係數", "p值", "N"]
        ]
        with pd.option_context(
            "display.max_rows", None, "display.width", 200,
            "display.unicode.east_asian_width", True,
        ):
            print("\n關鍵自變數係數摘要：")
            print(show.to_string(index=False))


if __name__ == "__main__":
    main()
