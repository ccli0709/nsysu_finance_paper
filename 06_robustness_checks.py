# -*- coding: utf-8 -*-
"""
第 06 步：穩健性檢定（Robustness Checks）。

輸入：03_sample_data.csv （篩選後全產業樣本；因需擴充產業，故不沿用
      已限定三大電子業的 04_model_data.csv）
輸出：
    1. 06_robustness_results.txt  — 各設定完整迴歸結果
    2. 06_robustness_coef.csv     — 各設定關鍵係數彙總
    3. 06_robustness_summary.csv  — 跨設定對照表（方便比較穩健性）

穩健性設計（產業樣本維度）：
    水資源衡量固定為「水回收率%」（不再使用製程水回收率），
    並保留「再生能源使用率」為自變數。
    產業樣本：
        S1 = 三大電子業（半導體 M2324、電子零組件 M2328、光電 M2326）
        S2 = 擴充樣本（再加鋼鐵 M2000、化學 M1721、紡織 M1400、
                       食品 M1200、塑膠 M1300、電腦及週邊 M2325）

    對每個產業樣本設定，跑模型 1（基礎）與模型 2（交乘）。

估計方法同第 05 步：雙向固定效果 PanelOLS + 公司叢集穩健標準誤。
"""

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

INPUT_CSV = "03_sample_data.csv"
OUTPUT_TXT = "06_robustness_results.txt"
OUTPUT_COEF = "06_robustness_coef.csv"
OUTPUT_SUMMARY = "06_robustness_summary.csv"

CODE = "證券代碼"
YEAR = "西元年份"
COL_IND_CODE = "TSE產業_代碼"

ENERGY = "再生能源使用率"
COL_ASSET = "資產總額"
CONTROLS = ["研究發展費用率", "LN資產總額", "負債比率"]

Y_VALUE = "Tobins Q_w"
Y_COST = "營業費用率"
DEP_VARS = [Y_VALUE, Y_COST]

# 水資源衡量設定（僅用水回收率%，不再使用製程水回收率）
WATER_MEASURES = {
    "W1-水回收率": "水回收率%",
}

# 產業樣本設定
ELECTRONICS = ["M2324", "M2328", "M2326"]
INDUSTRY_SETS = {
    "S1-三大電子": ELECTRONICS,
    "S2-擴充樣本": ELECTRONICS
    + ["M2000", "M1721", "M1400", "M1200", "M1300", "M2325"],
}


def rename_for_formula(cols):
    mapping = {}
    for c in cols:
        safe = (
            c.replace("%", "pct").replace("×", "x").replace(" ", "_")
            .replace("(", "").replace(")", "").replace("+", "plus")
            .replace("-", "_")
        )
        mapping[c] = safe
    return mapping


def prepare_panel(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d[YEAR] = pd.to_numeric(d[YEAR], errors="coerce").astype("Int64")
    d = d.dropna(subset=[CODE, YEAR])
    return d.set_index([CODE, YEAR])


def run_panel(df, dep, exog, label, results_lines, coef_rows, spec_tag):
    cols = [dep] + exog
    sub = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    n_entity = sub.index.get_level_values(0).nunique()
    n_time = sub.index.get_level_values(1).nunique()

    results_lines.append(
        f"\n{'='*78}\n[{label}]\n"
        f"  應變數 Y = {dep}\n  自變數 = {exog}\n"
        f"  觀測數 N = {len(sub)}，公司數 = {n_entity}，年數 = {n_time}\n"
        f"{'-'*78}"
    )

    if len(sub) < 20 or n_entity < 5:
        results_lines.append("  ** 樣本過小，略過此模型 **")
        return

    y, X = sub[dep], sub[exog]
    try:
        res = PanelOLS(
            y, X, entity_effects=True, time_effects=True, drop_absorbed=True
        ).fit(cov_type="clustered", cluster_entity=True)
    except Exception as e:  # noqa: BLE001
        try:
            res = PanelOLS(
                y, X, entity_effects=True, time_effects=True,
                drop_absorbed=True, check_rank=False,
            ).fit(cov_type="clustered", cluster_entity=True)
            results_lines.append(
                f"  ** 注意：設計矩陣降秩（{e}），改用 check_rank=False，"
                f"係數可能不穩定。 **"
            )
        except Exception as e2:  # noqa: BLE001
            results_lines.append(f"  ** 估計失敗：{e2} **")
            return

    results_lines.append(str(res))
    for var in res.params.index:
        coef_rows.append({
            "設定": spec_tag, "模型標籤": label, "應變數": dep, "變數": var,
            "係數": res.params[var], "標準誤": res.std_errors[var],
            "t值": res.tstats[var], "p值": res.pvalues[var],
            "N": int(res.nobs), "R2_within": res.rsquared_within,
        })


def main() -> None:
    raw = pd.read_csv(INPUT_CSV, dtype={CODE: str}, low_memory=False)

    # 建立建模變數（03 樣本尚未含交乘項與 LN 規模）
    for c in list(WATER_MEASURES.values()) + [ENERGY, COL_ASSET]:
        if c in raw.columns:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw["LN資產總額"] = np.where(raw[COL_ASSET] > 0, np.log(raw[COL_ASSET]), np.nan)
    raw["水回收率x再生能源"] = raw["水回收率%"] * raw[ENERGY]

    # 交乘項對應各水衡量
    interact_of = {
        "水回收率%": "水回收率x再生能源",
    }

    # 欄名安全化
    all_vars = list({
        *WATER_MEASURES.values(), ENERGY, *interact_of.values(),
        *CONTROLS, *DEP_VARS,
    } & set(raw.columns))
    mapping = rename_for_formula(all_vars)
    raw = raw.rename(columns=mapping)

    def m(name):
        return mapping.get(name, name)

    results_lines, coef_rows = [], []
    controls_s = [m(c) for c in CONTROLS]

    for wlabel, wcol in WATER_MEASURES.items():
        for slabel, codes in INDUSTRY_SETS.items():
            spec_tag = f"{slabel} | {wlabel}"
            sub_df = raw[raw[COL_IND_CODE].isin(codes)]
            panel = prepare_panel(sub_df)
            inter = interact_of[wcol]

            for dep in DEP_VARS:
                # 模型 1
                run_panel(
                    panel, m(dep), [m(wcol), m(ENERGY)] + controls_s,
                    f"[{spec_tag}] 模型1 | Y={dep}",
                    results_lines, coef_rows, spec_tag,
                )
                # 模型 2（交乘）
                run_panel(
                    panel, m(dep),
                    [m(wcol), m(ENERGY), m(inter)] + controls_s,
                    f"[{spec_tag}] 模型2 | Y={dep}",
                    results_lines, coef_rows, spec_tag,
                )

    # 輸出完整結果
    inv = {v: k for k, v in mapping.items()}
    legend = "\n變數名對照：\n" + "\n".join(
        f"  {s} = {o}" for o, s in mapping.items()
    )
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(
            "TEJ 水電資源實證：穩健性檢定（雙向固定效果 PanelOLS）\n"
            + legend + "\n" + "\n".join(results_lines) + "\n"
        )

    coef = pd.DataFrame(coef_rows)
    if not coef.empty:
        coef["變數"] = coef["變數"].map(lambda s: inv.get(s, s))
    coef.to_csv(OUTPUT_COEF, index=False, encoding="utf-8-sig")

    # 跨設定對照表：聚焦關鍵變數（各水衡量、綠電、交乘項）
    key_vars = list(WATER_MEASURES.values()) + [ENERGY] + list(interact_of.values())
    summary = pd.DataFrame()
    if not coef.empty:
        s = coef[coef["變數"].isin(key_vars)].copy()

        def star(p):
            return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""

        s["係數(顯著)"] = s.apply(
            lambda r: f"{r['係數']:.4f}{star(r['p值'])}", axis=1
        )
        summary = s[[
            "設定", "應變數", "模型標籤", "變數", "係數(顯著)", "p值", "N"
        ]]
    summary.to_csv(OUTPUT_SUMMARY, index=False, encoding="utf-8-sig")

    print(f"完成！輸出 {OUTPUT_TXT}、{OUTPUT_COEF}、{OUTPUT_SUMMARY}")
    if not summary.empty:
        with pd.option_context(
            "display.max_rows", None, "display.width", 220,
            "display.unicode.east_asian_width", True,
        ):
            print("\n跨設定關鍵係數對照（*** p<.01, ** p<.05, * p<.1）：")
            print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
