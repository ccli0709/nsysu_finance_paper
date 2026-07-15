---
name: tej-panel-pipeline
description: >
  將 TEJ（台灣經濟新報）下載的多個 zip/CSV 財經資料庫，合併成年度追蹤資料
  (panel data)，並依序進行變數建構、樣本篩選、產業資料量統計與迴歸模型變數
  建立的一套可重複執行管線。當使用者要處理 TEJ 資料、做財務／永續（ESG、水
  資源、綠電）實證研究、合併多份 TEJ CSV、或需要建立面板迴歸資料時使用。
  關鍵字：TEJ、台灣經濟新報、證券代碼、年月、panel data、面板資料、Tobins Q、
  縮尾 winsorize、遞延期 lag、水回收率、再生能源、資本支出 CAPEX。
---

# TEJ 面板資料處理管線（Panel Data Pipeline）

把 TEJ 下載的多份 CSV，一步步整併成可跑迴歸的研究樣本。程式以數字前綴命名，
**依序執行**即可；資料更新後，重新從 01 跑到最後一步即可重建所有輸出。

## 執行順序

```
python 01_merge_tej_data.py          # 合併原始 zip/CSV → 01_merged_tej_data.csv
python 02_feature_engineering.py     # 變數建構        → 02_features_data.csv
python 03_sample_selection.py        # 樣本篩選+產業統計→ 03_sample_data.csv, 03_industry_stats.csv
python 04_build_model_variables.py   # 產業限定+建模變數→ 04_model_data.csv
```

命名慣例：`NN_描述.py` 產出 `NN_描述.csv`；下一步的輸入 = 上一步的輸出，
方便日後資料更新時「從頭依序重跑」。新增步驟就往後接 `05_`、`06_`。

## 環境

- Python 3.x + pandas、numpy。
- 原始資料放在 `tej_data/`，為 TEJ 匯出的 zip（內含單一 CSV）。

## 各步驟重點

### 01 合併（01_merge_tej_data.py）
- TEJ CSV 特性：**UTF-16 (LE, 含 BOM)、Tab 分隔**；「證券代碼」值形如
  `2201 裕隆`（代碼＋公司名稱，需以第一個空白拆開）。
- 主鍵：**證券代碼 + 西元年份**。
  - 有「年」欄 → 直接為西元年份。
  - 只有「年月」(如 200012) → 取前 4 碼為西元年份；季度資料取**每年最後一季
    （年末 Q4）**代表年度值。
- 兩類資料集分開處理：
  - `DATASETS`：年度／季度資料，以 [證券代碼, 西元年份] outer join。
  - `COMPANY_DATASETS`：公司靜態資料（產業別、設立日期），只以 [證券代碼]
    left join，套用到該公司所有年份。
- 更新資料時：把新的 zip 檔名加入 `DATASETS` 或 `COMPANY_DATASETS`。

### 02 變數建構（02_feature_engineering.py）
1. 綠電資料 `GREEN_START_YEAR`(=2021) 之前的缺值補 0（不平衡面板）。
2. 水電設備 CAPEX 新增額 = 當期 − 前一年度（依精確 t-1 對應）。
3. 縮尾 Winsorize：對 Tobin's Q、CAPEX 做前後 1%（`_w` 欄位）。
4. 遞延期領先項：對應變數建立 t+1／t+3／t+5（`_t+k` 欄位）。
5. 企業年齡 = 當年 − 設立年（由「設立日期」前 4 碼取設立年）。

### 03 樣本篩選 + 產業統計（03_sample_selection.py）
- 篩選（參數在檔案上方）：限定研究期間 `START_YEAR`~`END_YEAR`(預設 2013-2024)、
  排除金融業(M2800)、剔除企業年齡負值。
- 產出 `03_industry_stats.csv`：各產業的公司數、觀測數、水資料筆數、綠電筆數、
  水與綠電皆有筆數、CAPEX 筆數、Tobin's Q 筆數、迴歸可用筆數，
  **用來挑選資料充足的產業**。

### 04 建模變數（04_build_model_variables.py）
- 限定主樣本產業 `TARGET_INDUSTRY_CODES`（預設半導體 M2324、電子零組件 M2328、
  光電 M2326——水資料最充足者）。
- 交乘項（模型 2）：水回收率×再生能源、製程水回收率×再生能源。
- 企業規模：LN(資產總額)。

## 已知資料特性 / 注意事項

- 綠電（再生能源使用率>0）揭露資料**整體偏少**；跨產業合併或視為輔助變數較穩健。
- 模型 2 交乘項需「同時有水與綠電」，樣本會很小，建議全樣本跑或當穩健性分析。
- 企業年齡負值多為 KY（海外控股）公司，財報年份早於控股公司設立日；於 03 步驟
  以 `DROP_NEGATIVE_AGE` 剔除。

## 換主題 / 換資料時如何沿用

1. 把新的 TEJ zip 丟進 `tej_data/`，在 01 的 `DATASETS`/`COMPANY_DATASETS`
   登記檔名（附上欄位說明註解）。
2. 若主鍵欄名不同（例如只有「年」或「年月」），01 已自動判斷；季度資料預設取
   年末，如需其他彙總方式（如年平均）再改 `to_annual`。
3. 調整 02 的變數建構清單、03 的篩選參數與 04 的目標產業／交乘項。
4. 從 `01` 依序重跑到最後一步。
