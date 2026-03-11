# gov-tw 品質評分設計

## 目標

擴展 `dataset score` 命令，新增 `--method gov-tw` 選項，依據數位發展部「政府資料品質提升機制運作指引」的 7 項檢測指標中可自動化的 6 項，對資料集進行品質評估。

## 背景

來源文件：
- [政府資料品質提升機制運作指引](https://file.data.gov.tw/content/about/%E6%94%BF%E5%BA%9C%E8%B3%87%E6%96%99%E5%93%81%E8%B3%AA%E6%8F%90%E5%8D%87%E6%A9%9F%E5%88%B6%E9%81%8B%E4%BD%9C%E6%8C%87%E5%BC%95.pdf)（數位發展部，民國 112 年 1 月）
- [資料品質檢測系統基本方針](https://data.gov.tw/faqs/639)（補充文件）

指引定義 4 構面 7 項指標：

| # | 構面 | 指標 | 可自動化 |
|---|------|------|---------|
| 1 | 資料可直接取得 | 連結有效性 | ✅ |
| 2 | 資料可直接取得 | 資料可直接下載 | ✅ |
| 3 | 資料易於處理 | 結構化檔案類型 | ✅ |
| 4 | 資料易於理解 | 編碼描述與資料相符 | ✅ |
| 5 | 資料易於理解 | 欄位描述與資料相符 | ✅ |
| 6 | 資料易於理解 | 更新時效性 | ✅ |
| 7 | 民眾意見回饋 | 回復效率 | ❌ 人工 |

本次實作 #1–#6，跳過 #7（需人工檢核）。

## 設計

### CLI 介面

擴展 `dataset score` 加 `--method` 選項：

```bash
tw-odc dataset --dir <slug> score                     # 預設 5-stars
tw-odc dataset --dir <slug> score --method 5-stars    # 明確指定
tw-odc dataset --dir <slug> score --method gov-tw     # 政府品質指標
tw-odc dataset --dir <slug> score --method gov-tw --id <id>
```

```python
class ScoringMethod(StrEnum):
    FIVE_STARS = "5-stars"
    GOV_TW = "gov-tw"
```

### 新模組 `tw_odc/gov_tw_scorer.py`

獨立檔案，與 `scorer.py`（5-stars）平行。

**輸入：**
- `InspectionResult`（來自 inspector）
- `metadata: dict`（來自 export-json 的原始條目，含「編碼格式」「主要欄位說明」「更新頻率」「詮釋資料更新時間」）

**輸出：** `GovTwScore` dataclass

### 6 項指標實作

#### 1. 連結有效性 (`link_valid`: bool)

- `inspection.file_exists == True` → True
- 否則 → False

#### 2. 可直接下載 (`direct_download`: bool)

- 同上。fetcher 用直接 HTTP GET 下載，能下載到即代表可直接取得。
- 若回應為 HTML（格式偵測為 html）→ False（可能是登入頁或導向頁）

#### 3. 結構化檔案類型 (`structured`: bool)

結構化格式集合：`{csv, json, xml, geojson, xlsx, xls, kmz, kml, shp}`
- 偵測格式在此集合中 → True
- 否則 → False（pdf, doc, image 等為非結構化）

#### 4. 編碼描述相符 (`encoding_match`: bool | None)

- 僅對結構化文字檔（csv, json, xml）檢查
- 讀取前 N bytes 偵測實際編碼（chardet 或 BOM 偵測）
- 比對 metadata「編碼格式」欄位（常見值：UTF-8, BIG5）
- 若 metadata 編碼欄位為空 → 僅檢查是否為 UTF-8（指引建議 UTF-8）
- 非結構化檔案 → None（未知）

#### 5. 欄位描述相符 (`fields_match`: bool | None)

- 僅對固定欄位結構化資料（csv, json）
- 從 metadata「主要欄位說明」解析期望欄位列表（以全形頓號「、」分隔）
- CSV：讀 header row，比對所有期望欄位是否存在
- JSON：讀第一筆 record 的 keys，比對所有期望欄位是否存在
- XML：檢查所有 element name，比對所有期望欄位是否至少有一個對應
- 所有期望欄位都有對應 → True
- 非結構化、無主要欄位、或主要欄位為空 → None（未知）

#### 6. 更新時效性 (`update_timeliness`: bool | None)

- 從 metadata「更新頻率」解析預期更新間隔（如：每1日、每1月、每1年）
- 從 metadata「詮釋資料更新時間」取最後更新時間
- 距今超過預期間隔 → False（有逾期）
- 否則 → True（無逾期）
- 「不定期更新」或無法解析 → None（未知）

### 交集式輸出

依指引：資料集結果是所有資料資源檢測結果的交集。一個資料資源有一項為 False，則整個資料集該項為 False。`None`（未知）不影響結果。

此邏輯與 5-stars 的「最弱環節」一致。

### JSON 輸出格式

```json
{
  "id": "86440",
  "name": "中央研究院歷年資訊相關訓練課程",
  "method": "gov-tw",
  "indicators": {
    "link_valid": true,
    "direct_download": true,
    "structured": true,
    "encoding_match": true,
    "fields_match": null,
    "update_timeliness": true
  },
  "pass_count": 4,
  "total_count": 5,
  "issues": []
}
```

- `null` 表示未知，不計入 `total_count`
- `pass_count` / `total_count` 為已知指標中通過的數量

### Metadata 載入策略

`gov-tw` 評分需要 export-json 的 metadata（5-stars 不需要）。載入方式：

1. `dataset score --method gov-tw` 時，CLI 從根目錄載入 `export-json.json`
2. 以「資料集識別碼」為 key 建立 lookup dict
3. 傳入 `gov_tw_score_dataset(inspection, metadata)` 函數
4. 若找不到該 dataset 的 metadata → 所有需要 metadata 的指標設為 None

### 新增依賴

- `chardet`：用於偵測檔案編碼（指標 4）

### 檔案結構

```
tw_odc/
├── scorer.py           # 現有：5-stars 評分（不改動）
├── gov_tw_scorer.py    # 新增：gov-tw 品質評分
├── cli.py              # 修改：score 命令加 --method 選項
└── inspector.py        # 不改動
```
