# ROC Open Data Checker

自動化稽核政府開放資料平台，以 Tim Berners-Lee 的五星開放資料模型評估資料集品質。

從[政府資料開放平臺](https://data.gov.tw/)開始，爬蟲收集資料集清單，再以確定性規則檢查格式、驗證連結、偵測常見問題（如 PDF、試算表當資料庫、下載失敗等）。評分結果以檔案形式儲存，讓資料品質可以被大規模量測。

LLM 只用於溝通，不用於評估——規則分析找出問題後，LLM 協助撰寫禮貌的改善建議信，由人工審核後寄出。

## 使用方式

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.13+。

```bash
# 安裝依賴
uv sync

# 執行單一平台的爬蟲
uv run python -m data_gov_tw crawl

# 執行所有平台（可設定平行數量）
uv run python main.py --concurrency 3
```

## 專案狀態

開發中。目前正在實作 data.gov.tw 的爬蟲，詳見 `docs/plans/`。
