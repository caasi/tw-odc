# tw-odc CLI 重構設計

## 目標

將 `main.py` 和 `shared/` 模組重構為統一的 CLI 工具 `tw-odc`，支援兩種資料來源（metadata 和 dataset），輸出以 JSON 為主，可配合 `jq` 使用。移除所有 scaffolding 腳本，provider 資料夾只保留 `manifest.json`（committed）和輸出檔案（gitignored）。

## CLI 結構

```
tw-odc metadata download                        # 下載 metadata（export-json 等）
tw-odc metadata list                             # 列出機關，JSON 輸出
tw-odc metadata create --provider "財政部"       # 建立 dataset manifest，stdout 輸出資料夾路徑
tw-odc metadata update --provider "財政部"       # 更新既有 dataset manifest
tw-odc metadata update --dir mof_gov_tw          # 同上，用資料夾指定

tw-odc dataset download [--id ID] [--dir DIR]    # 下載 dataset（etag 快取自動判斷更新）
tw-odc dataset list [--dir DIR]                  # 列出 datasets，JSON 輸出
tw-odc dataset check [--id ID] [--dir DIR]       # 檢查 dataset（inspect）
tw-odc dataset score [--id ID] [--dir DIR]       # 評分
tw-odc dataset clean [--id ID] [--dir DIR]       # 清除下載檔案

全域 flag：--format json|text（預設 json）
```

## 目錄結構

```
roc-open-data-checker/
├── manifest.json              # type: metadata，committed
├── export-json.json           # 下載的 metadata（gitignored）
├── export-csv.csv             # gitignored
├── export-xml.xml             # gitignored
├── .gitignore                 # 更新：忽略 export-* 檔案
├── pyproject.toml             # 註冊 tw-odc 指令
├── tw_odc/                    # CLI 套件（取代 shared/）
│   ├── __init__.py
│   ├── __main__.py            # python -m tw_odc 進入點
│   ├── cli.py                 # typer app，metadata/dataset 子命令
│   ├── fetcher.py             # 下載邏輯（從 shared/fetcher.py 遷移）
│   ├── inspector.py           # 檔案檢查（從 shared/inspector.py 遷移）
│   ├── scorer.py              # 評分（從 shared/scorer.py 遷移）
│   └── manifest.py            # manifest 讀寫、RFC 6902 patch 套用
├── mof_gov_tw/
│   ├── manifest.json          # type: dataset，committed
│   ├── patch.json             # RFC 6902 patch，committed（可選）
│   └── datasets/              # gitignored
└── ...其他 provider 資料夾
```

## manifest.json 格式

### Metadata（根目錄）

```json
{
  "type": "metadata",
  "provider": "data.gov.tw",
  "datasets": [
    {
      "id": "export-json",
      "name": "全站資料集匯出 JSON",
      "format": "json",
      "urls": ["https://data.gov.tw/datasets/export/json"]
    }
  ]
}
```

### Dataset（provider 資料夾）

```json
{
  "type": "dataset",
  "provider": "財政部",
  "slug": "mof_gov_tw",
  "datasets": [
    {
      "id": "21001",
      "name": "綜合所得稅申報核定統計專冊",
      "format": "csv",
      "urls": ["..."]
    }
  ]
}
```

## Patch 機制

`patch.json`（RFC 6902）放在 dataset 資料夾，`metadata create` / `metadata update` 時自動套用：

```json
[
  {"op": "replace", "path": "/datasets/0/format", "value": "json"},
  {"op": "remove", "path": "/datasets/2"}
]
```

新增 `jsonpatch` 依賴。

## stdin/stdout 行為

- JSON 輸出寫 stdout，log/進度條寫 stderr
- `--format text` 時改為 human-readable 單行輸出（每筆一行）
- 非 tty 時不輸出 ANSI color

## 要刪除的東西

- `main.py` — 被 `tw-odc` 取代
- `shared/` — 邏輯搬到 `tw_odc/`，刪除 `scaffold.py`
- `data_gov_tw/` — manifest 搬到根目錄，整個資料夾刪除
- 所有 provider 的 `__init__.py` 和 `__main__.py` — 最後一個 commit 統一清理

## pyproject.toml 變更

```toml
[project.scripts]
tw-odc = "tw_odc.cli:app"
```

## 設計決策摘要

| 決策 | 選擇 |
|------|------|
| CLI 進入點 | `pyproject.toml` 的 `[project.scripts]` 註冊 `tw-odc` |
| 子命令結構 | 兩層：`metadata` / `dataset` |
| manifest 區分 | `type` 欄位：`metadata` 或 `dataset` |
| metadata list | 自動讀取已下載的 export-json.json，不保留 --query/--missing |
| dataset 指定 | `--id` flag 指定單一 dataset |
| 建立 manifest | 歸在 `metadata create`，stdout 輸出資料夾路徑 |
| 更新 manifest | 歸在 `metadata update` |
| dataset update | 包含在 `download` 中，靠 etag 判斷 |
| metadata 檔案位置 | 直接放根目錄 |
| 輸出格式切換 | `--format json\|text`，預設 json |
| patch 格式 | RFC 6902 JSON Patch |
