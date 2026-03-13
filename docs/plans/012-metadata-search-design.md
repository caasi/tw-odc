# 012 — metadata search 設計文件

## 動機

tw-odc 現有的 CLI 只能列出所有機關（`metadata list`）或列出單一 provider 的資料集（`dataset list`），無法在 data.gov.tw 的 4 萬多筆資料集中做關鍵字搜尋。使用者被迫自己寫 Python 解析 `export-json.json`。

### 實際情境

- 搜「國防」「軍」→ 找國防相關機關和資料集
- 搜「採購」「廠商」→ 找政府採購資料集
- 搜「臺中」「工廠登記」→ 找特定地方的特定類型資料集
- 搜「中山科學」→ 確認某機關有沒有開放資料

這些操作目前都需要 `cat export-json.json | python3 -c "..."` 手動處理。

## 設計

### 指令介面

```bash
tw-odc metadata search <keywords...> [--field provider|name|desc] [--format json|text] [--dir PATH]
```

#### 參數

| 參數 | 類型 | 預設 | 說明 |
|---|---|---|---|
| `keywords` | positional, 一或多個 | 必填 | 搜尋關鍵字 |
| `--field` | 可多次指定 | 全部 | 限縮搜尋欄位：`provider`（提供機關）、`name`（資料集名稱）、`desc`（資料集描述） |
| `--format` | `json` / `text` | `json` | 輸出格式 |
| `--dir` | PATH | `data_dir()` | 指定 metadata 目錄（同其他 metadata 指令） |

### 搜尋邏輯

1. 讀取 `export-json.json`（同 `metadata list` 的資料來源）
2. 對每筆資料集，根據 `--field` 決定搜尋範圍：
   - `provider` → `提供機關`
   - `name` → `資料集名稱`
   - `desc` → `資料集描述`
   - 未指定 → 以上三者全部
3. 將選定欄位的值串接為一個搜尋字串
4. 每個 keyword 做 case-insensitive 子字串匹配（中文天然 case-insensitive，英文轉小寫）
5. **AND 邏輯**：所有 keyword 都命中同一筆資料集才算匹配（不需要在同一欄位）

### 輸出

#### JSON（預設）

```json
[
  {
    "id": "176745",
    "name": "115年臺南市工廠登記清冊",
    "provider": "臺南市政府經濟發展局",
    "format": "JSON;CSV;JSON;CSV"
  }
]
```

輸出依 `provider` 排序，同 provider 內依 `id` 排序。

#### Text

```
176745  115年臺南市工廠登記清冊  [臺南市政府經濟發展局]
```

一行一筆，tab 分隔。

搜尋結果筆數輸出至 stderr（如 `Found 15 datasets`），stdout 保持乾淨供 pipe。

### 不做的事

- 不做 relevance scoring 或排序權重
- 不做正規表達式（子字串匹配已足夠）
- 不做跨 provider 聚合（每筆結果是單一資料集）
- 不做已下載資料內容的全文搜尋（那是不同的功能）

## 使用範例

```bash
# 搜國防相關資料集
tw-odc metadata search 國防

# 搜國防 + 採購（AND）
tw-odc metadata search 國防 採購

# 只搜機關名含「臺中」
tw-odc metadata search 臺中 --field provider

# 臺中 + 工廠登記（跨欄位 AND）
tw-odc metadata search 臺中 工廠登記

# 人類可讀格式
tw-odc metadata search 廠商 --format text

# 搭配 jq 進一步篩選
tw-odc metadata search 工廠登記 | jq '.[].provider' | sort -u
```
