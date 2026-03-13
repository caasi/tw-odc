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

### 搜尋索引：slim JSONL

`export-json.json` 是 87MB 的單行 JSON array（53000+ 筆），每次搜尋都完整解析需要 ~1.3 秒。

為了避免每次搜尋都付完整解析成本，`metadata download` 完成後自動產生一份精簡索引檔 `export-search.jsonl`：

- **格式**：JSONL（每行一筆，獨立 JSON 物件）
- **欄位**：只保留搜尋所需的 5 個欄位（id, name, provider, desc, format）
- **大小**：約 15MB（原檔的 17%）
- **位置**：與 `export-json.json` 同目錄，同樣被 gitignore

搜尋時逐行讀取 JSONL，先對 raw text 做子字串匹配（不解析 JSON），只對命中行呼叫 `json.loads`。

#### 效能對比

| 方法 | 每次搜尋 | 備註 |
|---|---|---|
| stdlib json.load 全量解析 | ~1.3s | 無需索引檔 |
| slim JSONL + 逐行文字匹配 | **~0.06s** | 需要索引檔（15MB） |

#### 索引產生時機

- `metadata download` 下載 `export-json.json` 後自動產生/更新
- `metadata search` 時若索引不存在，fallback 為完整解析 `export-json.json`（相容但較慢）

### 搜尋邏輯

1. 讀取 `export-search.jsonl`（優先）或 fallback 至 `export-json.json`
2. 對每行（或每筆資料集），根據 `--field` 決定搜尋範圍：
   - `provider` → `提供機關`
   - `name` → `資料集名稱`
   - `desc` → `資料集描述`
   - 未指定 → 以上三者全部
3. 在 raw text 上做 case-insensitive 子字串匹配，命中才解析 JSON
4. 若指定 `--field`，解析後再驗證 keyword 確實出現在指定欄位（排除欄位間的誤命中）
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
- 不引入額外 dependency（orjson/ujson 等），stdlib 已足夠
- 不用 grep subprocess（fork 開銷反而比 Python 逐行匹配慢）

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
