# -*- coding: utf-8 -*-
"""
變數建構（Feature Engineering）程式。

輸入：merged_tej_data.csv （由 merge_tej_data.py 產出的年度面板）
輸出：merged_tej_data_features.csv

依 study.md 的研究設計，進行下列處理：
  1. 綠電資料 2021 年前的缺值補 0（早期視為尚未導入，構成不平衡面板）。
  2. 水電設備 CAPEX 新增額 = 當期水電設備成本 − 前一年度水電設備成本。
  3. Tobin's Q 與 CAPEX 進行前後 1% 縮尾（Winsorize）。
  4. 應變數的遞延期變數（t+1、t+3、t+5）。
  5. 企業年齡 = 當年 − 設立年。
"""

import pandas as pd

INPUT_CSV = "merged_tej_data.csv"
OUTPUT_CSV = "merged_tej_data_features.csv"

CODE = "證券代碼"
YEAR = "西元年份"

# 綠電資料收錄起始年（study.md：企業使用綠電情形自 2021 年起）
GREEN_START_YEAR = 2021

# 縮尾分位（前後各 1%）
WINSOR_LOWER = 0.01
WINSOR_UPPER = 0.99

# 遞延期（將應變數向後遞延的期數）
LEAD_PERIODS = (1, 3, 5)

# 應變數（Y）：需要建立遞延期 t+k 的變數
DEPENDENT_VARS = ["營業費用率", "營業利益率", "Tobins Q_w", "Tobins Q (A)_w"]


def winsorize(s: pd.Series, lower: float, upper: float) -> pd.Series:
    """對數值序列做前後分位縮尾，保留缺值。"""
    lo = s.quantile(lower)
    hi = s.quantile(upper)
    return s.clip(lower=lo, upper=hi)


def add_lead(df: pd.DataFrame, col: str, k: int) -> pd.Series:
    """
    回傳同一公司在第 t+k 年的 col 值（遞延期／領先項）。
    以 (證券代碼, 西元年份) 精確對應年度，避免年份不連續造成誤差。
    """
    lookup = df.set_index([CODE, YEAR])[col]
    lookup = lookup[~lookup.index.duplicated(keep="last")]
    keys = list(zip(df[CODE], df[YEAR] + k))
    return pd.Series(lookup.reindex(keys).to_numpy(), index=df.index)


def add_prev_year(df: pd.DataFrame, col: str) -> pd.Series:
    """回傳同一公司前一年度（t-1）的 col 值。"""
    lookup = df.set_index([CODE, YEAR])[col]
    lookup = lookup[~lookup.index.duplicated(keep="last")]
    keys = list(zip(df[CODE], df[YEAR] - 1))
    return pd.Series(lookup.reindex(keys).to_numpy(), index=df.index)


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype={CODE: str}, low_memory=False)

    # 西元年份轉為整數，並依 公司、年份 排序
    df[YEAR] = pd.to_numeric(df[YEAR], errors="coerce").astype("Int64")
    df = df.dropna(subset=[CODE, YEAR]).copy()
    df[YEAR] = df[YEAR].astype(int)
    df = df.sort_values([CODE, YEAR]).reset_index(drop=True)

    # 確保數值欄為數值型
    numeric_cols = [
        "製程水回收率%", "水回收率%", "再生能源使用率", "水電設備成本",
        "營業費用率", "營業利益率", "Tobins Q", "Tobins Q (A)",
        "研究發展費", "研究發展費用率", "資產總額", "負債比率",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---------------------------------------------------------------
    # 1. 綠電資料 2021 年前的缺值補 0
    # ---------------------------------------------------------------
    mask_pre = df[YEAR] < GREEN_START_YEAR
    filled = df.loc[mask_pre, "再生能源使用率"].isna().sum()
    df.loc[mask_pre, "再生能源使用率"] = df.loc[
        mask_pre, "再生能源使用率"
    ].fillna(0)
    print(f"1. 綠電 {GREEN_START_YEAR} 年前補 0：填補 {filled} 個缺值")

    # ---------------------------------------------------------------
    # 2. 水電設備 CAPEX 新增額 = 當期 − 前一年度
    # ---------------------------------------------------------------
    prev = add_prev_year(df, "水電設備成本")
    df["水電設備CAPEX新增額"] = df["水電設備成本"] - prev
    print(
        f"2. 水電設備CAPEX新增額：計算 "
        f"{df['水電設備CAPEX新增額'].notna().sum()} 筆"
    )

    # ---------------------------------------------------------------
    # 3. Tobin's Q 與 CAPEX 縮尾（前後 1%）
    # ---------------------------------------------------------------
    winsor_targets = ["Tobins Q", "Tobins Q (A)", "水電設備CAPEX新增額"]
    for col in winsor_targets:
        if col in df.columns:
            df[col + "_w"] = winsorize(df[col], WINSOR_LOWER, WINSOR_UPPER)
    print(
        f"3. 縮尾（{int(WINSOR_LOWER*100)}%/{int(WINSOR_UPPER*100)}%）："
        f"{[c + '_w' for c in winsor_targets if c in df.columns]}"
    )

    # ---------------------------------------------------------------
    # 4. 應變數遞延期 t+1、t+3、t+5
    # ---------------------------------------------------------------
    created_leads = []
    for col in DEPENDENT_VARS:
        if col not in df.columns:
            continue
        for k in LEAD_PERIODS:
            newcol = f"{col}_t+{k}"
            df[newcol] = add_lead(df, col, k)
            created_leads.append(newcol)
    print(f"4. 遞延期變數：共建立 {len(created_leads)} 欄 {created_leads}")

    # ---------------------------------------------------------------
    # 5. 企業年齡 = 當年 − 設立年
    # ---------------------------------------------------------------
    if "設立日期" in df.columns:
        est_year = (
            df["設立日期"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.extract(r"(\d{4})")[0]
        )
        est_year = pd.to_numeric(est_year, errors="coerce")
        df["設立年"] = est_year.astype("Int64")
        df["企業年齡"] = (df[YEAR] - est_year).astype("Int64")
        print(
            f"5. 企業年齡：計算 {df['企業年齡'].notna().sum()} 筆 "
            f"(範圍 {df['企業年齡'].min()}~{df['企業年齡'].max()})"
        )

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n完成！輸出 {OUTPUT_CSV}")
    print(f"  總列數：{len(df)}，總欄數：{len(df.columns)}")
    print(f"  欄位：{list(df.columns)}")


if __name__ == "__main__":
    main()
