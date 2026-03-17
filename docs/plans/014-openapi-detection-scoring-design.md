# 014 — OpenAPI/Swagger 偵測與評分

## 問題

data.gov.tw 上部分資料集的下載連結指向的不是資料本體，而是中繼資料：

1. **Redirect JSON**：下載到的 JSON 內容包含指向 `swagger.json` 或 `openapi.json` 的 URL（例如 GCIS 的 `redirect.json`）
2. **API Spec 本身**：下載到的 JSON 檔就是 OpenAPI/Swagger 規格文件

目前 inspector 把這些當成普通 JSON，scorer 給 ★3（open format），無法區分「有資料」和「只有 API 文件」。

### 規模

根據實際調查，manifest 中 URL 含 `swagger`/`openapi`/`redirect` 的 dataset 約 14,000 筆，但絕大多數（台中 6,834 筆、高雄 6,746 筆）URL 雖含這些關鍵字，回傳的卻是實際資料。真正回傳 API spec 或中繼資料的案例集中在：

- GCIS `data.gcis.nat.gov.tw/resources/swagger/redirect.json`：21 筆（redirect JSON → swagger.json）
- 其他零星案例

因此 **URL 關鍵字不可靠，必須檢查內容本身**。

## 設計

### 1. Inspector：偵測 API spec 與 link

在 `inspector.py` 新增兩種 detected format：

- **`api`**：檔案本身就是 OpenAPI/Swagger spec
- **`link`**：檔案內容包含指向 spec 的 URL

#### 偵測規則

**`api` 偵測**（確定是 spec）：

```python
# 下載回來的 JSON 頂層有 "swagger" 或 "openapi" 欄位
data = json.loads(content)
if isinstance(data, dict) and ("swagger" in data or "openapi" in data):
    return "api"
```

**`link` 偵測**（指向 spec 的跳板）：

```python
# JSON 內任何字串值的 URL path 結尾是 swagger.json 或 openapi.json
def _find_spec_urls(obj) -> list[str]:
    """遞迴掃描 JSON，找出指向 spec 的 URL。"""
    urls = []
    if isinstance(obj, str):
        if obj.startswith("http") and (
            obj.rstrip("/").endswith("swagger.json")
            or obj.rstrip("/").endswith("openapi.json")
        ):
            urls.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            urls.extend(_find_spec_urls(v))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(_find_spec_urls(item))
    return urls
```

#### 整合到 `inspect_dataset()`

在現有 format 偵測之後，若 detected format 是 `json`，進一步檢查內容：

1. 嘗試 `json.loads()` 讀取檔案
2. 若頂層有 `swagger`/`openapi` → detected format 改為 `api`
3. 否則掃描字串值找 spec URL → 若找到，detected format 改為 `link`，spec URL 記錄在 InspectionResult
4. JSON parse 失敗或不符合任何條件 → 維持 `json`

#### InspectionResult 擴充

```python
@dataclass
class InspectionResult:
    # ... 既有欄位 ...
    spec_urls: list[str] = field(default_factory=list)  # link 偵測到的 spec URL
```

#### Issue 標記

- detected format 為 `api` → 加入 `API_SPEC` issue
- detected format 為 `link` → 加入 `LINK_TO_API_SPEC` issue

### 2. CLI 編排 spec 下載

當 inspector 偵測到 `link` 並提取出 spec URL 時，需要下載 spec 來進行評分。

**職責分離**：inspector 只負責偵測和標記，不做網路 I/O。spec 下載由 CLI 層（`cli.py`）在 `score` 流程中編排：

#### 流程

1. `cli.py` 的 `score` 命令先執行 `inspect_dataset()`
2. 若 inspection 結果的 `detected_formats` 含 `link` 且 `spec_urls` 非空：
   - 用 `urllib.request.urlopen()` 同步下載第一個 spec URL
   - 存到 `datasets/{dataset_id}-spec.json`
   - 對 spec 檔案再做一次 `detect_api_spec()` 確認是 `api`
3. 將 spec 內容傳入 scorer 進行 ★4/★5 評分

#### 存放位置

spec 檔案存在同一個 `datasets/` 目錄下，命名為 `{dataset_id}-spec.json`，與原始下載檔案並列。

#### 錯誤處理

spec 下載可能失敗（網路錯誤、404、timeout、非 JSON、JSON 但不是 spec）。Fallback 行為：

- 下載失敗或內容不是 API spec → 維持 `link` format，spec 不傳入 scorer
- 加入 `SPEC_DOWNLOAD_FAILED` issue
- 評分停在 ★3（`link` 在 `OPEN_FORMATS`）
- 進度訊息輸出到 stderr

#### 為什麼不在 inspector 或 scorer 裡下載

- `inspector.py` 是純本地檔案檢查，沒有網路 I/O，維持這個特性
- `scorer.py` 是純計算邏輯，不應有副作用
- CLI 層已經有 async 下載的先例（`dataset download`），這裡用同步即可

#### `score_provider()` 的處理

`scorer.py` 的 `score_provider()` 直接呼叫 `score_dataset(inspection)` 而不經過 CLI。為了讓它也能處理 API spec：

- `score_provider()` 新增 spec 讀取邏輯：若 inspection 的 detected_formats 含 `api`，直接讀取本地檔案取得 spec dict
- 若含 `link`：檢查 `datasets/{id}-spec.json` 是否已存在（先前 CLI score 可能已下載過），有就讀取，沒有就 spec=None
- `score_provider()` 本身不做網路下載——保持無副作用，缺 spec 就評 ★3

#### `inspect_dataset()` 的 API 檢查粒度

API spec 檢查是 **per-file** 的：在既有的 per-URL 迴圈中，每個偵測為 `json` 的檔案獨立做 `api`/`link` 判斷。多 URL dataset 中若一個檔案是 `json`（且為 spec）、另一個是 `csv`，只有 JSON 那個會被標記。

### 3. Scorer：★4 和 ★5 實作

目前 `scorer.py` 的 ★4/★5 硬寫 `False`。對 `api` 類型的 dataset，從 spec 結構推斷：

#### ★1–★3

- `"api"` 和 `"link"` 都加入 `OPEN_FORMATS` 和 `MACHINE_READABLE` → `_format_star()` 回傳 3
- 正常流程：CLI 下載 spec 後傳入 scorer，scorer 用 spec 內容做 ★4/★5
- Fallback：spec 下載失敗時，`link` format 仍會到達 scorer（spec 為 None），★4/★5 為 False，維持 ★3

#### ★4 — URI 標識資源

從 spec 的 `paths` 判斷：

```python
def _has_resource_uris(spec: dict) -> bool:
    """Spec 的 paths 中有帶路徑參數的 endpoint 且有定義 response schema。"""
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        # 路徑包含參數模板（如 /{id}、/{Business_Accounting_NO}）
        if "{" not in path:
            continue
        for method_def in methods.values():
            if not isinstance(method_def, dict):
                continue
            responses = method_def.get("responses", {})
            ok_resp = responses.get("200") or responses.get("201")
            if ok_resp and _has_response_schema(ok_resp):
                return True
    return False


def _has_response_schema(response: dict) -> bool:
    """Check if a response object has a schema (Swagger 2.0 or OpenAPI 3.x)."""
    # Swagger 2.0: schema is directly under response
    if "schema" in response:
        return True
    # OpenAPI 3.x: schema is under content.{media-type}.schema
    content = response.get("content", {})
    for media_type in content.values():
        if isinstance(media_type, dict) and "schema" in media_type:
            return True
    return False
```

以 GCIS 為例：其 paths 用 UUID 作 path（`/F0E8FB8D-...`）但沒有路徑參數——查詢靠 `$filter` query parameter。所以 GCIS 這個 spec **不會**拿到 ★4，因為它沒有用 URI 標識個別 resource。這是正確的——OData-style 的 filter 查詢和 RESTful 的 resource URI 確實不同。

#### ★5 — 連結到外部資料

從 spec 的 schema 判斷：

```python
def _has_external_links(spec: dict) -> bool:
    """Spec 中的 schema 有 $ref 指向外部 URL。

    注意：只檢查外部 $ref（以 http 開頭的 $ref），這代表 spec 的 schema
    定義明確引用了外部資料集的 schema。

    不以 format: uri 作為判斷依據——format: uri 僅描述欄位值的格式
    （例如某個欄位是 URL），不代表 API 本身連結到外部資料集。
    """
    def _scan(obj):
        if isinstance(obj, dict):
            ref = obj.get("$ref", "")
            if ref.startswith("http"):
                return True
            return any(_scan(v) for v in obj.values())
        if isinstance(obj, list):
            return any(_scan(item) for item in obj)
        return False

    for section in ("definitions", "components", "paths"):
        if section in spec and _scan(spec[section]):
            return True
    return False
```

#### 評分流程

```
cli.py score 流程:
  inspect_dataset()
    → detected format = "json"
    → 進一步檢查 → "api" 或 "link"

  取得 spec dict:
    若 "api": spec = json.loads(檔案內容)  ← 檔案本身就是 spec
    若 "link" 且有 spec_urls:
      → cli 用 urllib.request 下載 spec
      → 存到 datasets/{id}-spec.json
      → spec = json.loads(下載內容)

  score_dataset(inspection, spec=spec_dict)
    → ★3: True ("api"/"link" 在 OPEN_FORMATS)
    → ★4: _has_resource_uris(spec)
    → ★5: _has_external_links(spec)
```

**Listing/Search API 的評分**：若 spec 只有 listing 或 search endpoint（無路徑參數，僅靠 `$filter`/`$skip`/`$top`/`limit`/`offset` 等 query parameter 查詢），★4 為 False——因為沒有穩定的單一 URI 標識個別 resource。這符合五星模型的嚴格定義：OData-style 的 `$filter=ID eq 123` 是查詢語句，不是 resource URI。

### 4. CLI 輸出

#### `dataset check` 輸出範例

```json
{
  "id": "84883",
  "name": "公司登記資本額查詢",
  "declared_format": "json",
  "detected_formats": ["link"],
  "spec_urls": ["http://data.gcis.nat.gov.tw/resources/swagger/swagger.json"],
  "issues": ["LINK_TO_API_SPEC"]
}
```

#### `dataset score` 輸出範例

```json
{
  "id": "84883",
  "name": "公司登記資本額查詢",
  "declared_format": "json",
  "detected_format": "api",
  "star_score": 3,
  "stars": {
    "available_online": true,
    "machine_readable": true,
    "open_format": true,
    "rdf_uris": false,
    "linked_data": false
  },
  "issues": ["LINK_TO_API_SPEC"]
}
```

（GCIS 的 spec 沒有路徑參數 endpoint，所以 ★4 是 false）

## 不做的事

- 不解析 OpenAPI spec 來列出 endpoint 給使用者（使用者可以 `dataset view` 看 spec 內容自己判斷）
- 不呼叫 API endpoint 取得實際資料
- 不處理非 JSON 格式的 spec（YAML OpenAPI）——data.gov.tw 上沒有這種案例
- 不對 URL 關鍵字做判斷——只檢查下載內容

## 影響範圍

| 檔案 | 變動 |
|------|------|
| `inspector.py` | 新增 `api`/`link` 偵測、`spec_urls` 欄位、`_find_spec_urls()` |
| `scorer.py` | `OPEN_FORMATS`/`MACHINE_READABLE` 加入 `api`/`link`；★4 `_has_resource_uris()`、★5 `_has_external_links()`；`score_dataset()` 接受可選的 spec dict |
| `fetcher.py` | 不變 |
| `cli.py` | `check` 輸出加入 `spec_urls`；`score` 流程編排 spec 下載（`urllib.request`）並傳入 scorer |
| `tests/` | 新增 test_inspector.py 和 test_scorer.py 的 API spec 測試案例 |

## 測試策略

- 用最小化的 Swagger 2.0 和 OpenAPI 3.0 JSON fixture 測試偵測邏輯
- 用含/不含路徑參數的 spec fixture 測試 ★4 判斷
- 用含/不含外部 `$ref` 的 spec fixture 測試 ★5 判斷
- Spec 下載失敗時 fallback 到 ★3 並加入 `SPEC_DOWNLOAD_FAILED` issue
- `score_provider()` 讀取本地 spec 檔案（存在/不存在兩種情境）
- GCIS redirect.json 作為 `link` 偵測的整合測試 fixture
- 確保台中/高雄那種 URL 含 swagger 但回傳實際資料的不會被誤判
