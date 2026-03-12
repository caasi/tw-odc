# 010 — 修正 daily update 將格式覆寫為 "bin" 的問題

## 問題描述

`tw-odc metadata apply-daily` 執行時，daily-changed-json.json 中的 `"檔案格式"` 欄位全部為 `null`（CSV 版為 `""`）。`parse_dataset()` 將空值 fallback 成 `"bin"`，接著 `update_dataset_manifest()` 整筆覆蓋既有 dataset，導致原本正確的 format（如 `"csv"`、`"json"`）被改成 `"bin"`。

## 根本原因

1. **`parse_dataset()`** 對空格式無條件 fallback 為 `"bin"`——對 initial create 合理，但對 daily update 是錯的
2. **`update_dataset_manifest()`** 整筆取代而非 field-level merge，丟失既有欄位值

## 設計方案

### 1. `parse_dataset()` — 空格式回傳 `None`

```python
# 之前
fmt = formats[0].lower() if formats else "bin"

# 之後
fmt = formats[0].lower() if formats else None
```

`FORMAT_ALIASES.get(None, None)` 回傳 `None`，不影響。回傳型別從 `str` 變成 `str | None`。

### 2. `update_dataset_manifest()` — field-level merge

對已存在的 dataset，只用有值的欄位覆蓋舊值：

- `name`：永遠更新（daily-changed 有提供）
- `format`：`None` 時保留舊值，有值時更新
- `urls`：空列表時保留舊值，非空時更新
- `id`：作為 key，不變

新 dataset（既有 manifest 中不存在的 id）整筆寫入。

### 3. `fetcher.py` — `None` format fallback

`fetcher.py:47` 的 `dataset["format"].lower()` 改為：format 為 `None` 時用 `"bin"` 當檔名副檔名。這只影響檔名組合，不影響資料語意。

### 4. `inspector.py` — 處理未宣告格式

format 為 `None` 時的行為：

- **檔名**：用 `"bin"` 組檔名（與 fetcher 一致，才能找到正確的檔案）
- **`_SAFE_FMT_RE` 驗證**：在 regex 驗證之前處理 `None`，避免 `TypeError`
- **FORMAT_MISMATCH**：跳過（沒宣告就沒有 mismatch）
- **`declared_format`**：設為 `"bin"`（與磁碟檔名一致），不用偵測值覆蓋——偵測結果留在 `detected_formats` 欄位
- **新增 issue**：`"FORMAT_UNDECLARED"` 標記格式未宣告

> 為什麼 `declared_format` 不用偵測值？`gov_tw_scorer.py:298` 用 `inspection.declared_format` 組檔案路徑。如果 `declared_format` 是偵測值（如 `"csv"`）但磁碟上的檔是 `{id}.bin`，scorer 會找不到檔案。保持 `declared_format = "bin"` 確保與 fetcher 產生的檔名一致。

### 5. 測試

- `test_manifest.py`：`parse_dataset()` 空格式回傳 `None` 的案例
- `test_manifest.py`：`update_dataset_manifest()` field-level merge 行為——`None` format 不覆蓋既有值
- `test_fetcher.py`：format 為 `None` 時檔名使用 `"bin"` 副檔名
- `test_inspector.py`：format 為 `None` 時跳過 FORMAT_MISMATCH、新增 FORMAT_UNDECLARED、declared_format 為 `"bin"`

## 受影響的檔案

| 檔案 | 改動 |
|------|------|
| `tw_odc/manifest.py` | `parse_dataset()` 回傳 `None`；`update_dataset_manifest()` field-level merge |
| `tw_odc/fetcher.py` | `_dest_filename()` format `None` fallback `"bin"`（影響 `dataset download`、`dataset view`） |
| `tw_odc/inspector.py` | format `None` 處理邏輯、`_SAFE_FMT_RE` 防護、`FORMAT_UNDECLARED` issue |
| `tests/test_manifest.py` | 新增 `None` format 相關測試 |
| `tests/test_fetcher.py` | 新增 `None` format 測試 |
| `tests/test_inspector.py` | 新增 `None` format 測試 |

## 不受影響

- `create_dataset_manifest()`：用 export-json.json，`"檔案格式"` 有值，不受 `None` 影響。邊界情況：若 export-json 中某筆資料格式為空，manifest 會寫入 `"format": null`，這是正確行為（誠實反映資料狀態）
- `scorer.py`：吃 inspector 的 `InspectionResult`，不直接讀 manifest 的 format 欄位
- `gov_tw_scorer.py`：用 `inspection.declared_format` 組檔案路徑，因 inspector 在 format `None` 時設 `declared_format = "bin"`，與磁碟檔名一致，不受影響
- `cli.py:_find_export_json()`：操作 root metadata manifest（type=metadata），不走 `parse_dataset()`
- `dataset list`：直接輸出 manifest 內容，`"format": null` 是正確的 JSON 輸出
- `fetcher.py:clean_dataset()`：用 glob pattern `{id}.*` 找檔案，不依賴 format 欄位
