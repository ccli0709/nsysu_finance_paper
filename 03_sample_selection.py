# -*- coding: utf-8 -*-
"""
樣本篩選與產業資料量統計程式。

輸入：02_features_data.csv （變數建構後的年度面板）
輸出：
    1. 03_sample_data.csv     — 篩選後的研究樣本
    2. 03_industry_stats.csv  — 各產業資料量統計（協助挑選資料充足的產業）

篩選條件（可於下方參數區調整）：
    - 限定研究期間 [START_YEAR, END_YEAR]
    - 排除金融業（產業代碼 M2800）
    - 剔除企業年齡為負值的觀測（公司成立年之前的財報年份）

產業統計目的：
    由於再生水／再生能源揭露資料不多，透過各產業的資料量統計，
    協助挑選「水資料」「綠電資料」較充足、適合持續研究的產業。
"""

import pandas as pd

INPUT_CSV = "02_features_data.csv"
OUTPUT_SAMPLE_CSV = "03_sample_data.csv"
OUTPUT_STATS_CSV = "03_industry_stats.csv"

CODE = "證券代碼"
YEAR = "西元年份"

# ---- 篩選參數 -------------------------------------------------------
# 研究期間：企業用水量資料自 2013 年起收錄，故起始年預設 2013。
START_YEAR = 2013
END_YEAR = 2024  # 2025、2026 財報多不完整，預設排除

# 要排除的產業代碼（金融業）
EXCLUDE_INDUSTRY_CODES = ["M2800"]
# 金融相關名稱關鍵字（備援：部分列可能無產業代碼但名稱可辨識）
EXCLUDE_INDUSTRY_NAME_KW = "金融|證券|保險|銀行"

# 是否剔除企業年齡負值
DROP_NEGATIVE_AGE = True
# --------------------------------------------------------------------

# 欄位名稱
COL_WATER1 = "水回收率%"
COL_WATER2 = "製程水回收率%"
COL_GREEN = "再生能源使用率"
COL_CAPEX = "水電設備CAPEX新增額"
COL_TOBINQ = "Tobins Q"
COL_OPEXR = "營業費用率"
COL_ASSET = "資產總額"
COL_DEBT = "負債比率"
COL_IND_CODE = "TSE產業_代碼"
COL_IND_NAME = "TSE產業_名稱"
COL_AGE = "企業年齡"


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype={CODE: str}, low_memory=False)
    df[YEAR] = pd.to_numeric(df[YEAR], errors="coerce")
    n0 = len(df)
    print(f"原始樣本：{n0} 列，{df[CODE].nunique()} 家公司")

    # 1) 限定研究期間
    df = df[(df[YEAR] >= START_YEAR) & (df[YEAR] <= END_YEAR)].copy()
    print(
        f"1. 限定研究期間 {START_YEAR}-{END_YEAR}："
        f"保留 {len(df)} 列（移除 {n0 - len(df)} 列）"
    )

    # 2) 排除金融業
    n_before = len(df)
    code_mask = df[COL_IND_CODE].isin(EXCLUDE_INDUSTRY_CODES)
    name_mask = df[COL_IND_NAME].astype(str).str.contains(
        EXCLUDE_INDUSTRY_NAME_KW, na=False
    )
    df = df[~(code_mask | name_mask)].copy()
    print(
        f"2. 排除金融業（{EXCLUDE_INDUSTRY_CODES}）："
        f"保留 {len(df)} 列（移除 {n_before - len(df)} 列）"
    )

    # 3) 剔除企業年齡負值
    if DROP_NEGATIVE_AGE and COL_AGE in df.columns:
        n_before = len(df)
        age = pd.to_numeric(df[COL_AGE], errors="coerce")
        df = df[~(age < 0)].copy()
        print(
            f"3. 剔除企業年齡負值："
            f"保留 {len(df)} 列（移除 {n_before - len(df)} 列）"
        )

    print(
        f"\n篩選後研究樣本：{len(df)} 列，{df[CODE].nunique()} 家公司，"
        f"年份 {int(df[YEAR].min())}-{int(df[YEAR].max())}"
    )

    df.to_csv(OUTPUT_SAMPLE_CSV, index=False, encoding="utf-8-sig")
    print(f"輸出研究樣本：{OUTPUT_SAMPLE_CSV}")

    # ---------------------------------------------------------------
    # 產業資料量統計
    # ---------------------------------------------------------------
    has_water = df[COL_WATER1].notna() | df[COL_WATER2].notna()
    has_green = pd.to_numeric(df[COL_GREEN], errors="coerce").fillna(0) > 0
    has_both = has_water & has_green
    has_capex = df[COL_CAPEX].notna()
    has_tobinq = df[COL_TOBINQ].notna()

    # 迴歸可用（模型1）：至少一個自變數 + 應變數(Tobin's Q) + 控制變數
    reg_ready = (
        (has_water | has_green)
        & df[COL_TOBINQ].notna()
        & df[COL_ASSET].notna()
        & df[COL_DEBT].notna()
    )

    work = df.assign(
        _has_water=has_water,
        _has_green=has_green,
        _has_both=has_both,
        _has_capex=has_capex,
        _has_tobinq=has_tobinq,
        _reg_ready=reg_ready,
    )

    grp = work.groupby([COL_IND_CODE, COL_IND_NAME], dropna=False)
    stats = grp.agg(
        公司數=(CODE, "nunique"),
        觀測數_公司年=(CODE, "size"),
        水資料筆數=("_has_water", "sum"),
        綠電筆數=("_has_green", "sum"),
        水與綠電皆有筆數=("_has_both", "sum"),
        水電CAPEX筆數=("_has_capex", "sum"),
        TobinsQ筆數=("_has_tobinq", "sum"),
        迴歸可用筆數=("_reg_ready", "sum"),
    ).reset_index()

    # 有水資料的公司數（衡量橫斷面充足度）
    water_firms = (
        work[work["_has_water"]]
        .groupby([COL_IND_CODE, COL_IND_NAME], dropna=False)[CODE]
        .nunique()
        .rename("有水資料公司數")
        .reset_index()
    )
    green_firms = (
        work[work["_has_green"]]
        .groupby([COL_IND_CODE, COL_IND_NAME], dropna=False)[CODE]
        .nunique()
        .rename("有綠電公司數")
        .reset_index()
    )
    stats = stats.merge(
        water_firms, on=[COL_IND_CODE, COL_IND_NAME], how="left"
    ).merge(green_firms, on=[COL_IND_CODE, COL_IND_NAME], how="left")
    stats[["有水資料公司數", "有綠電公司數"]] = (
        stats[["有水資料公司數", "有綠電公司數"]].fillna(0).astype(int)
    )

    # 以「水資料筆數」為主排序（水資料為主要自變數且較充足）
    stats = stats.sort_values(
        ["水資料筆數", "水與綠電皆有筆數"], ascending=False
    ).reset_index(drop=True)

    # 重新排欄位順序
    ordered = [
        COL_IND_CODE, COL_IND_NAME, "公司數", "觀測數_公司年",
        "水資料筆數", "有水資料公司數", "綠電筆數", "有綠電公司數",
        "水與綠電皆有筆數", "水電CAPEX筆數", "TobinsQ筆數", "迴歸可用筆數",
    ]
    stats = stats[ordered]

    stats.to_csv(OUTPUT_STATS_CSV, index=False, encoding="utf-8-sig")
    print(f"輸出產業統計：{OUTPUT_STATS_CSV}\n")

    print("各產業資料量（依水資料筆數排序，前 15 名）：")
    with pd.option_context(
        "display.max_columns", None, "display.width", 200,
        "display.unicode.east_asian_width", True,
    ):
        print(stats.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
