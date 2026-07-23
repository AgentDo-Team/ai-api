def fetch_page(session, base_url, service_key, bgn_dt, end_dt, page_no):
    url = (f"{base_url}?serviceKey={service_key}"
           f"&pageNo={page_no}&numOfRows=500&type=json&inqryDiv=1"
           f"&inqryBgnDt={bgn_dt}&inqryEndDt={end_dt}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()
