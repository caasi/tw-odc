# 014 — OpenAPI/Swagger 偵測與評分：實作計畫

依據 `014-openapi-detection-scoring-design.md`。TDD：每步先寫測試再實作。

---

## Step 1: Inspector — `api` 偵測

### 1a. 測試：偵測 Swagger 2.0 spec

`tests/test_inspector.py`

```python
def test_detect_api_spec_swagger2(tmp_path):
    """JSON with top-level 'swagger' key → detected format 'api'."""
    spec = {"swagger": "2.0", "info": {"title": "test"}, "paths": {}}
    # 寫成檔案，呼叫 detect_api_spec()，斷言回傳 "api"

def test_detect_api_spec_openapi3(tmp_path):
    """JSON with top-level 'openapi' key → detected format 'api'."""
    spec = {"openapi": "3.0.0", "info": {"title": "test"}, "paths": {}}
```

### 1b. 實作：`inspector.py` 新增 `detect_api_spec()`

```python
def detect_api_spec(file_path: Path) -> str | None:
    """If file is a JSON API spec, return 'api'. Otherwise None."""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(data, dict) and ("swagger" in data or "openapi" in data):
        return "api"
    return None
```

### 1c. 測試：普通 JSON 不被誤判

```python
def test_detect_api_spec_regular_json(tmp_path):
    """Regular JSON data → None (not an API spec)."""
    data = [{"name": "foo", "value": 123}]
    # 斷言 detect_api_spec() 回傳 None

def test_detect_api_spec_taichung_data(tmp_path):
    """JSON with actual data (台中 swagger URL 回傳的) → None."""
    data = {"GISROOT": {"RECORD": [{"序號": 1, "名稱": "test"}]}}
```

### 1d. 測試：非 JSON 檔案不 crash

```python
def test_detect_api_spec_non_json(tmp_path):
    """Non-JSON file → None, no exception."""
    # 寫入 CSV 內容，斷言回傳 None

def test_detect_api_spec_missing_file(tmp_path):
    """Missing file → None."""
```

**驗證**：`uv run pytest tests/test_inspector.py -v -k api_spec`

---

## Step 2: Inspector — `link` 偵測

### 2a. 測試：找到 spec URL

```python
def test_find_spec_urls_swagger(tmp_path):
    """JSON containing URL ending with swagger.json → found."""
    data = [{"url": "http://example.com/swagger.json", "desc": "API"}]
    # 斷言 _find_spec_urls(data) 回傳 ["http://example.com/swagger.json"]

def test_find_spec_urls_openapi(tmp_path):
    """JSON containing URL ending with openapi.json → found."""

def test_find_spec_urls_nested(tmp_path):
    """Nested JSON structure → URL found recursively."""
    data = {"links": [{"nested": {"href": "https://api.example.com/openapi.json"}}]}

def test_find_spec_urls_gcis_redirect(tmp_path):
    """GCIS redirect.json format → finds swagger.json URL."""
    data = [
        {"類別": "字串", "網頁連結": "http://data.gcis.nat.gov.tw/resources/swagger/swagger.json"},
        {"類別": "網頁", "網頁連結": "https://data.gcis.nat.gov.tw/od/rule"},
    ]
    # 斷言只找到 swagger.json 那個
```

### 2b. 實作：`inspector.py` 新增 `_find_spec_urls()`

如 design doc 所述的遞迴掃描。

### 2c. 測試：不誤判

```python
def test_find_spec_urls_no_spec(tmp_path):
    """JSON with URLs but none pointing to spec → empty list."""
    data = [{"url": "https://data.taipei/api/download"}]

def test_find_spec_urls_non_http(tmp_path):
    """Non-HTTP string ending with swagger.json → not found."""
    data = {"path": "/local/path/swagger.json"}
```

**驗證**：`uv run pytest tests/test_inspector.py -v -k find_spec`

---

## Step 3: Inspector — 整合到 `inspect_dataset()`

### 3a. 測試：inspect_dataset 偵測 api format

```python
def test_inspect_dataset_api_spec(tmp_path):
    """Downloaded JSON is API spec → detected_formats=['api'], issues contains API_SPEC."""
    # 在 tmp_path/datasets/ 寫入 swagger spec JSON
    # 建立 dataset dict，呼叫 inspect_dataset()
    # 斷言 detected_formats == ["api"]
    # 斷言 "API_SPEC" in issues
```

### 3b. 測試：inspect_dataset 偵測 link format

```python
def test_inspect_dataset_link_to_spec(tmp_path):
    """Downloaded JSON contains spec URL → detected_formats=['link'], spec_urls populated."""
    # 寫入 GCIS-style redirect JSON
    # 斷言 detected_formats == ["link"]
    # 斷言 "LINK_TO_API_SPEC" in issues
    # 斷言 spec_urls == ["http://...swagger.json"]
```

### 3c. 實作：修改 `inspect_dataset()`

在既有 format 偵測迴圈中，當 `fmt == "json"` 時：

1. 呼叫 `detect_api_spec(file_path)` → 若回傳 `"api"`，替換 detected format
2. 否則讀取 JSON 呼叫 `_find_spec_urls()` → 若有結果，替換為 `"link"`，記錄 `spec_urls`

### 3d. 擴充 `InspectionResult`：新增 `spec_urls: list[str]`

### 3e. 測試：普通 JSON 不受影響

```python
def test_inspect_dataset_regular_json(tmp_path):
    """Regular JSON data file → detected_formats=['json'], no API issues."""
```

**驗證**：`uv run pytest tests/test_inspector.py -v`（全部通過，既有測試不壞）

---

## Step 4: Scorer — format sets 更新 + `score_dataset()` 簽名

### 4a. 測試：api/link format 得 ★3

```python
def test_format_star_api():
    assert _format_star("api") == 3

def test_format_star_link():
    assert _format_star("link") == 3
```

### 4b. 實作：更新 `MACHINE_READABLE` 和 `OPEN_FORMATS`

```python
MACHINE_READABLE = {"csv", "json", "xml", "xlsx", "xls", "kmz", "geojson", "api", "link"}
OPEN_FORMATS = {"csv", "json", "xml", "geojson", "api", "link"}
```

### 4c. 測試：score_dataset 接受 spec 參數

```python
def test_score_dataset_api_no_spec():
    """API format without spec dict → ★3, rdf_uris=False, linked_data=False."""

def test_score_dataset_api_with_spec():
    """API format with spec dict → passes spec to ★4/★5 checks."""
```

### 4d. 實作：`score_dataset()` 新增 `spec: dict | None = None` 參數

- 當 spec 不為 None 且 format 含 `api` 或 `link` → 呼叫 `_has_resource_uris(spec)` 和 `_has_external_links(spec)`
- 否則 ★4/★5 維持 False

**驗證**：`uv run pytest tests/test_scorer.py -v`

---

## Step 5: Scorer — ★4 `_has_resource_uris()`

### 5a. 測試：有路徑參數 + schema → True

```python
def test_has_resource_uris_swagger2():
    """Swagger 2.0 with path param and response schema → True."""
    spec = {
        "swagger": "2.0",
        "paths": {
            "/companies/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "schema": {"type": "object", "properties": {"name": {"type": "string"}}}
                        }
                    }
                }
            }
        }
    }

def test_has_resource_uris_openapi3():
    """OpenAPI 3.x with path param and content schema → True."""
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/companies/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
```

### 5b. 測試：listing API（無路徑參數）→ False

```python
def test_has_resource_uris_listing_only():
    """OData-style listing API (no path params, only $filter) → False."""
    spec = {
        "swagger": "2.0",
        "paths": {
            "/F0E8FB8D-E2FD-472E-886C-91C673641F31": {
                "get": {
                    "parameters": [
                        {"name": "$filter", "in": "query", "type": "string"},
                        {"name": "$skip", "in": "query", "type": "string"},
                    ],
                    "responses": {
                        "200": {"schema": {"type": "array"}}
                    }
                }
            }
        }
    }
    # 斷言 False — 沒有 {param} 在 path 裡
```

### 5c. 測試：無 paths → False

```python
def test_has_resource_uris_no_paths():
    spec = {"swagger": "2.0", "info": {"title": "empty"}}
```

### 5d. 測試：有路徑參數但無 schema → False

```python
def test_has_resource_uris_no_schema():
    spec = {
        "swagger": "2.0",
        "paths": {
            "/items/{id}": {
                "get": {"responses": {"200": {"description": "ok"}}}
            }
        }
    }
```

### 5e. 實作：`_has_resource_uris()` 和 `_has_response_schema()`

如 design doc 所述。

**驗證**：`uv run pytest tests/test_scorer.py -v -k resource_uris`

---

## Step 6: Scorer — ★5 `_has_external_links()`

### 6a. 測試：外部 $ref → True

```python
def test_has_external_links_external_ref():
    spec = {
        "swagger": "2.0",
        "definitions": {
            "Company": {
                "properties": {
                    "industry": {"$ref": "https://other-api.gov.tw/schemas/industry.json"}
                }
            }
        }
    }

def test_has_external_links_in_paths():
    """External $ref in inline path schema → True."""
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/items/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "https://example.com/schema.json"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
```

### 6b. 測試：內部 $ref → False

```python
def test_has_external_links_internal_ref():
    spec = {
        "swagger": "2.0",
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {"schema": {"$ref": "#/definitions/Item"}}
                    }
                }
            }
        },
        "definitions": {
            "Item": {"type": "object"}
        }
    }
    # 斷言 False — #/ 開頭是內部引用

def test_has_external_links_none():
    """Spec with no $ref at all → False."""
    spec = {"swagger": "2.0", "paths": {}}
```

### 6c. 測試：format: uri 不算（設計決策）

```python
def test_has_external_links_format_uri_ignored():
    """format: uri in schema field does NOT count as external link."""
    spec = {
        "swagger": "2.0",
        "definitions": {
            "Company": {
                "properties": {
                    "website": {"type": "string", "format": "uri"}
                }
            }
        }
    }
    # 斷言 False
```

### 6d. 實作：`_has_external_links()`

如 design doc 所述。

**驗證**：`uv run pytest tests/test_scorer.py -v -k external_links`

---

## Step 7: Scorer — `score_provider()` 讀取本地 spec

### 7a. 測試：有本地 spec 檔案

```python
def test_score_provider_reads_local_spec(tmp_path):
    """score_provider() reads {id}-spec.json when detected format is 'api'."""
    # 建立 manifest.json + datasets/{id}.json (swagger spec)
    # 呼叫 score_provider()
    # 斷言 rdf_uris 根據 spec 內容正確判斷

def test_score_provider_reads_link_spec(tmp_path):
    """score_provider() reads {id}-spec.json for 'link' format if spec file exists."""
    # 建立 manifest.json + datasets/{id}.json (redirect) + datasets/{id}-spec.json (spec)
```

### 7b. 測試：無本地 spec 檔案

```python
def test_score_provider_link_no_spec_file(tmp_path):
    """score_provider() with 'link' format but no spec file → ★3, no crash."""
```

### 7c. 實作：修改 `score_provider()`

在 `for dataset in manifest["datasets"]` 迴圈中：

1. `inspect_dataset()` 後，檢查 `detected_formats`
2. 若含 `api`：讀取 `datasets/{id}.{fmt}` 做 `json.loads()`
3. 若含 `link`：嘗試讀取 `datasets/{id}-spec.json`
4. 將 spec dict 傳入 `score_dataset(inspection, spec=spec)`

**驗證**：`uv run pytest tests/test_scorer.py -v`

---

## Step 8: CLI — `check` 輸出 + `score` 編排 spec 下載

### 8a. 測試：check 輸出包含 spec_urls

手動驗證或 CLI 整合測試：

```python
def test_cli_check_shows_spec_urls(tmp_path):
    """dataset check outputs spec_urls when link format detected."""
```

### 8b. 實作：`cli.py` 的 `check` 命令

在 `check` 輸出的 dict 中加入 `spec_urls`（當非空時）。

### 8c. 實作：`cli.py` 的 `score` 命令

在 score 流程中，inspection 後：

```python
spec = None
if "api" in inspection.detected_formats:
    # 讀取本地檔案
    spec_path = datasets_dir / f"{dataset_id}.{declared_fmt}"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
elif "link" in inspection.detected_formats and inspection.spec_urls:
    # 下載 spec
    spec_path = datasets_dir / f"{dataset_id}-spec.json"
    try:
        from urllib.request import urlopen
        with urlopen(inspection.spec_urls[0], timeout=30) as resp:
            content = resp.read()
        spec_path.write_bytes(content)
        spec = json.loads(content)
        # 確認是 api spec
        if not isinstance(spec, dict) or ("swagger" not in spec and "openapi" not in spec):
            spec = None
    except Exception as exc:
        print(f"W004: spec download failed: {exc}", file=sys.stderr)
        inspection.issues.append("SPEC_DOWNLOAD_FAILED")
        spec = None

score = score_dataset(inspection, spec=spec)
```

### 8d. 測試：spec 下載失敗 fallback

```python
def test_cli_score_spec_download_failed(tmp_path, monkeypatch):
    """Spec download failure → SPEC_DOWNLOAD_FAILED issue, ★3."""
```

**驗證**：`uv run pytest -v`（全部測試通過）

---

## Step 9: 整合測試 + 既有測試不壞

### 9a. 跑全部測試

```bash
uv run pytest -v
```

### 9b. 手動驗證 GCIS

如果 GCIS 網路可達：

```bash
uv run tw-odc dataset --dir data_gcis_nat_gov_tw_37b3e8de check --id 84883
uv run tw-odc dataset --dir data_gcis_nat_gov_tw_37b3e8de score --id 84883
```

預期：
- check → `detected_formats: ["link"]`, `spec_urls: ["http://...swagger.json"]`
- score → `star_score: 3`, `rdf_uris: false`（GCIS spec 無路徑參數）

---

## 依賴關係

```
Step 1 (api 偵測)
Step 2 (link 偵測)
  ↓
Step 3 (整合到 inspect_dataset) ← 依賴 1, 2
  ↓
Step 4 (format sets + score_dataset 簽名)
Step 5 (★4 _has_resource_uris)
Step 6 (★5 _has_external_links)
  ↓
Step 7 (score_provider 讀本地 spec) ← 依賴 3, 4, 5, 6
Step 8 (CLI check/score 編排) ← 依賴 3, 4, 5, 6
  ↓
Step 9 (整合測試) ← 依賴 all
```

Steps 1-2 可並行。Steps 4-6 可並行。Steps 7-8 可並行。
