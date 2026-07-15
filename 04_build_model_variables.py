# -*- coding: utf-8 -*-
"""
建立迴歸模型所需變數（主樣本產業限定 + 交乘項 + 規模變數）。

輸入：03_sample_data.csv （篩選後的研究樣本）
輸出：04_model_data.csv  （限定產業、含交乘項與 LN 規模的模型資料）

處理內容：
  1. 將主樣本限定為水／綠電資料較充足的電子相關產業
     （半導體業 M2324、電子零組件 M2328、光電業 M2326）。
  2. 建立水能互補交乘項（模型 2）：
       水回收率% × 再生能源使用率
       製程水回收率% × 再生能源使用率
  3. 企業規模控制變數：資產總額取自然對數 LN(資產總額)。

備註：
  - 依 study.md，綠電資料 2021 年前已於步驟 02 補 0，故此處交乘項在
    早期年份多為 0，屬預期的不平衡面板現象。
  - 目標產業清單可於下方 TARGET_INDUSTRY_CODES 調整。
"""

import numpy as np
import pandas as pd

INPUT_CSV = "03_sample_data.csv"
OUTPUT_CSV = "04_model_data.csv"

CODE = "證券代碼"
YEAR = "西元年份"
COL_IND_CODE = "TSE產業_代碼"

# 主樣本目標產業（水／綠電資料較充足的電子相關產業）
TARGET_INDUSTRY_CODES = ["M2324", "M2328", "M2326"]  # 半導體、電子零組件、光電

# 變數欄位
COL_WATER = "水回收率%"
COL_PWATER = "製程水回收率%"
COL_GREEN = "再生能源使用率"
COL_ASSET = "資產總額"


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype={CODE: str}, low_memory=False)
    n0 = len(df)
    print(f"輸入樣本：{n0} 列，{df[CODE].nunique()} 家公司")

    # 1) 限定目標產業
    df = df[df[COL_IND_CODE].isin(TARGET_INDUSTRY_CODES)].copy()
    print(
        f"1. 限定主樣本產業 {TARGET_INDUSTRY_CODES}："
        f"保留 {len(df)} 列（移除 {n0 - len(df)} 列），"
        f"{df[CODE].nunique()} 家公司"
    )

    # 確保數值型
    for c in [COL_WATER, COL_PWATER, COL_GREEN, COL_ASSET]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # 2) 水能互補交乘項（模型 2）
    df["水回收率x再生能源"] = df[COL_WATER] * df[COL_GREEN]
    df["製程水回收率x再生能源"] = df[COL_PWATER] * df[COL_GREEN]
    print(
        "2. 交乘項：水回收率x再生能源、製程水回收率x再生能源 已建立 "
        f"（非缺值 {df['水回收率x再生能源'].notna().sum()} / "
        f"{df['製程水回收率x再生能源'].notna().sum()} 筆）"
    )

    # 3) 企業規模：資產總額取自然對數（資產須為正）
    asset = df[COL_ASSET]
    df["LN資產總額"] = np.where(asset > 0, np.log(asset), np.nan)
    print(
        f"3. LN資產總額：計算 {df['LN資產總額'].notna().sum()} 筆"
        f"（資產總額 <=0 或缺值者設為 NaN）"
    )

    df = df.sort_values([CODE, YEAR]).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n完成！輸出 {OUTPUT_CSV}")
    print(f"  總列數：{len(df)}，總欄數：{len(df.columns)}")
    print(
        f"  年份 {int(df[YEAR].min())}-{int(df[YEAR].max())}，"
        f"公司數 {df[CODE].nunique()}"
    )
    # 各產業樣本數
    print("  各產業樣本數：")
    for code, sub in df.groupby(COL_IND_CODE):
        print(f"    {code}: {len(sub)} 列, {sub[CODE].nunique()} 家公司")


if __name__ == "__main__":
    main()
