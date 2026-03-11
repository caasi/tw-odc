# 每日異動資料集整合設計

## 目標

將 data.gov.tw 的「每日異動資料集」納入 metadata 資料源，讓 tw-odc 可以下載並利用每日異動清單來追蹤變動紀錄及驅動增量更新。

## 背景

data.gov.tw 首頁提供「每日異動資料集」下載，API endpoint：

```
GET https://data.gov.tw/api/front/dataset/changed/export?format={csv|json}&report_date=YYYY-MM-DD
```

- 支援 CSV 和 JSON 兩種格式
- JSON 欄位結構與全站匯出 `export-json.json` 一致，多一個 `資料集變動狀態` 欄位（新增/修改/刪除）
- URL 需要 `report_date` 日期參數，不是靜態 URL

## 設計方案：params 擴展

在現有 dataset 結構中新增可選的 `params` 欄位，用於 URL 模板替換。

### manifest.json 變更

```json
{
  "type": "metadata",
  "provider": "data.gov.tw",
  "datasets": [
    { "id": "export-json", "name": "全站資料集匯出 JSON", "format": "json", "urls": ["https://data.gov.tw/datasets/export/json"] },
    { "id": "export-csv", "name": "全站資料集匯出 CSV", "format": "csv", "urls": ["https://data.gov.tw/datasets/export/csv"] },
    { "id": "export-xml", "name": "全站資料集匯出 XML", "format": "xml", "urls": ["https://data.gov.tw/datasets/export/xml"] },
    {
      "id": "daily-changed-json",
      "name": "每日異動資料集 JSON",
      "format": "json",
      "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=json&report_date={date}"],
      "params": { "date": "today" }
    },
    {
      "id": "daily-changed-csv",
      "name": "每日異動資料集 CSV",
      "format": "csv",
      "urls": ["https://data.gov.tw/api/front/dataset/changed/export?format=csv&report_date={date}"],
      "params": { "date": "today" }
    }
  ]
}
```

### params 語意

- `params` 為可選欄位，沒有時 URL 視為靜態（現有行為不變）
- 有 `params` 時，URL 中的 `{key}` 以 `str.format_map()` 替換
- 特殊值 `"today"` 解析為 `datetime.date.today().isoformat()`（YYYY-MM-DD）

### 檔名規則

帶 params 的 dataset 檔名包含參數值：

- `daily-changed-json-2026-03-10.json`
- `daily-changed-csv-2026-03-10.csv`

格式：`{id}-{param_values}.{format}`

### fetcher.py 變更

- 下載前檢查 dataset 是否有 `params`
- 有 `params` 時：解析特殊值（`"today"` → 今日日期）→ `str.format_map()` 替換 URL → 檔名帶參數值
- 無 `params` 時：現有邏輯不變

### CLI 變更

`metadata download` 新增 `--date` 選項：

```bash
# 用今天日期（預設）
tw-odc metadata download --only daily-changed-json.json

# 指定日期
tw-odc metadata download --only daily-changed-json.json --date 2026-03-10
```

`--date` 覆蓋 `params.date` 的值。

### .gitignore 變更

```gitignore
# Metadata downloads (root level)
/export-json.json
/export-csv.csv
/export-xml.xml
/daily-changed-*.*
```

### 下游影響

- `metadata list` 和 `metadata create/update` 讀的是 `export-json.json`，不受影響
- daily-changed JSON 欄位結構與 export-json 一致，可用同一個 `group_by_provider` + `parse_dataset` 處理增量更新

## `metadata apply-daily` 子命令

用下載好的每日異動 JSON 增量更新已存在的 provider manifest。

### CLI 介面

```bash
# 用今天日期（找 daily-changed-json-YYYY-MM-DD.json）
tw-odc metadata apply-daily

# 指定日期
tw-odc metadata apply-daily --date 2026-03-10
```

### 流程

```
daily-changed-json-{date}.json
  → group_by_provider()
  → 遍歷每個 provider:
      有本地 manifest? → update_dataset_manifest() 增量合併
      沒有?           → 加入 warnings（provider, reason: no_local_manifest）
      有「刪除」狀態?  → 加入 warnings（不處理，只警告）
```

### 增量合併策略

新增 `update_dataset_manifest(pkg_dir, changed_datasets) -> int`：
- 讀現有 `manifest.json` 的 datasets
- 用 changed datasets 按 id 合併（已存在的覆蓋，不存在的新增）
- 寫回 `manifest.json`
- 回傳更新的 dataset 數量

與 `create_dataset_manifest`（全量覆寫）分開，專做增量更新。

### 輸出（JSON 摘要）

```json
{
  "date": "2026-03-10",
  "updated": ["provider_slug_1", "provider_slug_2"],
  "skipped": ["provider_slug_3"],
  "warnings": [
    {"provider": "某機關", "reason": "no_local_manifest"},
    {"provider": "另機關", "reason": "contains_deleted_datasets"}
  ]
}
```

- **updated**: 有異動且成功更新的 provider slug
- **skipped**: daily JSON 裡有但本地 manifest 無變化
- **warnings**: 找不到本地 manifest，或含有刪除狀態的資料集

### 注意事項

- 「刪除」狀態不處理，只警告
- 檔案不存在就報錯退出（先用 `metadata download` 下載）
