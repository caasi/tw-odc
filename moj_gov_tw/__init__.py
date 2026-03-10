from shared.fetcher import fetch_all

# 資料集例外說明（manifest.json 由工具自動產生，請勿修改原始資料）：
#
# ID 33003「法院案件統計資料」：
#   依台灣政府組織，法院（含各級法院）隸屬司法院，而非法務部。
#   法務部主管檢察、矯正及法制行政業務，並不管轄法院。
#   此資料集依 data.gov.tw 匯出資料歸屬法務部，但下載網址
#   (moj.gov.tw/uploadfiles/opendata/court_case_statistics.csv) 已回傳 404，
#   若日後補齊，應確認是否應移至 judicial_gov_tw（司法院）套件。
#
# ID 33005「地政士名冊」：
#   地政士（土地代書）業務主管機關為內政部地政司，並非法務部。
#   此資料集依 data.gov.tw 匯出資料歸屬法務部，
#   下載網址 (moj.gov.tw/uploadfiles/opendata/land_registration_agents.csv) 已回傳 404。
#   若日後補齊，應確認是否應移至 moi_gov_tw（內政部）套件。


async def run() -> None:
    await fetch_all(__file__)
