# -*- coding: utf-8 -*-
"""
合併 TEJ（台灣經濟新報）財經資料庫下載的 CSV 資料。

目的：
    依照 study.md 的研究設計，將 tej_data/ 資料夾中各 zip 內的 CSV
    以「證券代碼」與「西元年份」為主鍵 (KEY) 合併成一份年度追蹤資料
    (annual panel data)，供後續實證迴歸使用。

資料特性：
    - 檔案編碼：UTF-16 (LE, 含 BOM)，欄位以 Tab 分隔。
    - 「證券代碼」欄位值形如「2201 裕隆」，前段為代碼、後段為公司名稱。
    - 部分資料庫提供「年」(年度) 欄位，直接就是西元年份。
    - 部分資料庫僅提供「年月」(如 200012) 與「季別」，屬季度資料；
      西元年份取「年月」前 4 碼；並以每年最後一季 (季別=4 / 年末) 之
      數值代表該年度值，以對齊年度面板。

輸出：
    01_merged_tej_data.csv (UTF-8-BOM)  — 合併後的年度面板資料。
"""

import os
import zipfile
import pandas as pd

DATA_DIR = "tej_data"
OUTPUT_CSV = "01_merged_tej_data.csv"

# 主鍵
KEY_CODE = "證券代碼"
KEY_YEAR = "西元年份"

# 各資料集設定：zip 檔名 -> 該資料集的說明（僅供 log 使用）
DATASETS = [
    "TEJ20260716024111.zip",  # 企業用水量：製程水回收率%、水回收率%（年）
    "TEJ20260716024340.zip",  # 企業使用綠電：再生能源使用率（年）
    "TEJ20260716025604.zip",  # 資產負債表明細：水電設備成本（年月/季）
    "TEJ20260716030221.zip",  # 財務比率：營業費用率、營業利益率、Tobins Q（年月/季）
    "TEJ20260716030623.zip",  # 財務比率/控制變數：研發費、資產總額、負債比率（年月/季）
]

# 公司層級（靜態）資料集：無年度維度，僅以 證券代碼 合併，套用到該公司所有年份
COMPANY_DATASETS = [
    "TEJ20260716033627.zip",  # 企業基本資料：TSE 產業別、產業代碼/名稱、設立日期
]

# 讀取 CSV 時嘗試的編碼（TEJ 匯出通常為 UTF-16）
ENCODINGS = ("utf-16", "utf-8-sig", "cp950", "big5")


def read_tej_csv(zip_path: str) -> pd.DataFrame:
    """從 zip 中讀出唯一的 CSV，回傳字串型別的 DataFrame。"""
    with zipfile.ZipFile(zip_path) as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"{zip_path} 內找不到 CSV 檔")
        csv_name = csv_names[0]
        raw = z.read(csv_name)

    last_err = None
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
    else:
        raise UnicodeDecodeError(
            "tej", raw, 0, 1, f"無法以 {ENCODINGS} 解碼: {last_err}"
        )

    from io import StringIO

    df = pd.read_csv(
        StringIO(text),
        sep="\t",
        dtype=str,
        keep_default_na=False,
    )
    # 清理欄名（去除前後空白）
    df.columns = [c.strip() for c in df.columns]
    return df


def clean_cell(series: pd.Series) -> pd.Series:
    """去除字串前後空白、將空字串與 null byte 轉為缺值。"""
    s = series.astype(str).str.replace("\x00", "", regex=False).str.strip()
    return s.replace({"": pd.NA, "nan": pd.NA})


def split_code_name(df: pd.DataFrame) -> pd.DataFrame:
    """將「證券代碼」欄（如「2201 裕隆」）拆成代碼與公司名稱。"""
    col = clean_cell(df[KEY_CODE])
    parts = col.str.split(n=1, expand=True)
    df[KEY_CODE] = parts[0]
    name = parts[1] if parts.shape[1] > 1 else pd.NA
    df["公司名稱"] = name.str.strip() if hasattr(name, "str") else pd.NA
    return df


def derive_year(df: pd.DataFrame) -> pd.DataFrame:
    """建立「西元年份」欄：優先用「年」，否則由「年月」前 4 碼取得。"""
    if "年" in df.columns:
        df[KEY_YEAR] = clean_cell(df["年"]).str[:4]
    elif "年月" in df.columns:
        df[KEY_YEAR] = clean_cell(df["年月"]).str[:4]
    else:
        raise ValueError("資料集缺少『年』或『年月』欄，無法取得西元年份")
    return df


def to_annual(df: pd.DataFrame) -> pd.DataFrame:
    """
    將資料整理為每個 (證券代碼, 西元年份) 一列的年度資料。

    - 若為季度資料（含「年月/季別」），取每年最後一季（年末）之數值，
      作為該年度代表值（財報年末餘額 / 年度累計）。
    - 若原本即為年度資料，仍去除可能的重複列（保留最後一筆）。
    """
    df = df.copy()

    # 決定排序依據：年月 > 季別 > 序號，用來挑出「該年度最後一筆」
    sort_cols = []
    for c in ("年月", "季別", "序號"):
        if c in df.columns:
            df[c + "__sortkey"] = pd.to_numeric(
                clean_cell(df[c]), errors="coerce"
            )
            sort_cols.append(c + "__sortkey")

    if sort_cols:
        df = df.sort_values([KEY_CODE, KEY_YEAR] + sort_cols)

    # 每個 (代碼, 年份) 保留最後一筆（季度資料即為年末季）
    df = df.dropna(subset=[KEY_CODE, KEY_YEAR])
    df = df.drop_duplicates(subset=[KEY_CODE, KEY_YEAR], keep="last")

    # 移除輔助排序欄
    df = df[[c for c in df.columns if not c.endswith("__sortkey")]]
    return df


# 每個資料集特有的資料欄（合併後保留的變數），用來避免中繼欄（年、年月、
# 季別、序號）在多檔合併時重複衝突。
META_COLS = {"年", "年月", "季別", "序號", "公司名稱", KEY_CODE, KEY_YEAR}


def load_dataset(zip_name: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, zip_name)
    df = read_tej_csv(path)
    df = split_code_name(df)
    df = derive_year(df)
    df = to_annual(df)

    # 資料欄逐一清理，並嘗試轉為數值
    value_cols = [c for c in df.columns if c not in META_COLS]
    for c in value_cols:
        cleaned = clean_cell(df[c])
        numeric = pd.to_numeric(cleaned, errors="coerce")
        # 若整欄幾乎都能轉成數值，就採用數值型；否則保留清理後字串
        if numeric.notna().sum() >= cleaned.notna().sum() * 0.9:
            df[c] = numeric
        else:
            df[c] = cleaned

    # 只保留主鍵 + 公司名稱 + 資料欄（丟棄各檔各自的 年/年月/季別/序號）
    keep = [KEY_CODE, KEY_YEAR, "公司名稱"] + value_cols
    keep = [c for c in keep if c in df.columns]
    df = df[keep]

    print(
        f"  {zip_name}: {len(df):>6} 列, "
        f"年份 {df[KEY_YEAR].min()}~{df[KEY_YEAR].max()}, "
        f"變數 {value_cols}"
    )
    return df


def load_company_dataset(zip_name: str) -> pd.DataFrame:
    """
    載入公司層級（靜態）資料集，僅以「證券代碼」為鍵，每家公司一列。

    此類資料沒有年度維度（如產業別、設立日期），合併時會套用到該公司
    的所有年份。
    """
    path = os.path.join(DATA_DIR, zip_name)
    df = read_tej_csv(path)
    df = split_code_name(df)

    # 資料欄 = 除去主鍵與公司名稱的欄位
    value_cols = [c for c in df.columns if c not in META_COLS]
    for c in value_cols:
        df[c] = clean_cell(df[c])

    # 每家公司保留一列（避免重複）
    df = df.dropna(subset=[KEY_CODE]).drop_duplicates(
        subset=[KEY_CODE], keep="first"
    )

    keep = [KEY_CODE, "公司名稱"] + value_cols
    keep = [c for c in keep if c in df.columns]
    df = df[keep]

    print(f"  {zip_name}: {len(df):>6} 家公司, 欄位 {value_cols}")
    return df


def main() -> None:
    print("讀取並整理各 TEJ 資料集：")
    frames = [load_dataset(z) for z in DATASETS]

    print("\n以 [證券代碼, 西元年份] 進行 outer join 合併 ...")
    merged = frames[0]
    for df in frames[1:]:
        # 公司名稱以第一份為主，其餘檔的公司名稱作為補漏
        df_no_name = df.drop(columns=["公司名稱"], errors="ignore")
        name_map = df[[KEY_CODE, "公司名稱"]] if "公司名稱" in df.columns else None

        merged = merged.merge(
            df_no_name, on=[KEY_CODE, KEY_YEAR], how="outer"
        )

        if name_map is not None and "公司名稱" in merged.columns:
            # 補上第一份缺失的公司名稱
            name_lookup = (
                name_map.dropna(subset=["公司名稱"])
                .drop_duplicates(subset=[KEY_CODE])
                .set_index(KEY_CODE)["公司名稱"]
            )
            merged["公司名稱"] = merged["公司名稱"].fillna(
                merged[KEY_CODE].map(name_lookup)
            )

    # 合併公司層級（靜態）資料：僅以 證券代碼 為鍵，套用到該公司所有年份
    if COMPANY_DATASETS:
        print("\n以 [證券代碼] 合併公司基本資料 ...")
        for zip_name in COMPANY_DATASETS:
            cdf = load_company_dataset(zip_name)
            cname_map = cdf[[KEY_CODE, "公司名稱"]] if "公司名稱" in cdf.columns else None
            cdf_no_name = cdf.drop(columns=["公司名稱"], errors="ignore")

            merged = merged.merge(cdf_no_name, on=[KEY_CODE], how="left")

            # 用基本資料補上仍缺失的公司名稱
            if cname_map is not None and "公司名稱" in merged.columns:
                name_lookup = (
                    cname_map.dropna(subset=["公司名稱"])
                    .drop_duplicates(subset=[KEY_CODE])
                    .set_index(KEY_CODE)["公司名稱"]
                )
                merged["公司名稱"] = merged["公司名稱"].fillna(
                    merged[KEY_CODE].map(name_lookup)
                )

    # 排序：先代碼、後年份
    merged[KEY_YEAR + "_num"] = pd.to_numeric(merged[KEY_YEAR], errors="coerce")
    merged = merged.sort_values([KEY_CODE, KEY_YEAR + "_num"]).drop(
        columns=[KEY_YEAR + "_num"]
    )

    # 將主鍵與公司名稱移到最前面
    front = [KEY_CODE, "公司名稱", KEY_YEAR]
    front = [c for c in front if c in merged.columns]
    others = [c for c in merged.columns if c not in front]
    merged = merged[front + others]

    merged.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n完成！輸出 {OUTPUT_CSV}")
    print(f"  總列數：{len(merged)}")
    print(f"  總欄數：{len(merged.columns)}")
    print(f"  欄位：{list(merged.columns)}")
    print(
        f"  年份範圍：{merged[KEY_YEAR].min()} ~ {merged[KEY_YEAR].max()}, "
        f"公司數：{merged[KEY_CODE].nunique()}"
    )


if __name__ == "__main__":
    main()
