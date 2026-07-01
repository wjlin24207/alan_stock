import streamlit as st
import requests
import json
import re
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板 (JSON 精準對齊版)")

# 監控的商品代號
market_tickers = {
    "台指期貨 (近月)": "WTX=F",
    "小型道瓊期貨 (小道瓊)": "YM=F",
    "小型S&P500期貨 (小S&P)": "ES=F",
    "小型那斯達克期貨 (小那斯達克)": "NQ=F",
    "道瓊工業指數": "^DJI",
    "S&P 500 指數": "^GSPC",
    "那斯達克綜合指數": "^IXIC",
    "費城半導體指數": "^SOX"
}

@st.cache_data(ttl=5)  # 快取 5 秒，確保即時刷新
def fetch_exact_json_data(tickers_dict):
    data_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for name, ticker in tickers_dict.items():
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}"
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                # 關鍵突破點：Yahoo 把所有當下即時報價藏在 "context": {...} 這個 JSON 字串裡
                # 我們直接用正規表示式把這段核心資料精準挖出來
                match = re.search(r'root\.App\.main\s*=\s*({.*?});\s*<\/script>', response.text)
                if not match:
                    match = re.search(r'context\s*=\s*({.*?});\s*<\/script>', response.text)
                
                if match:
                    json_data = json.loads(match.group(1))
                    # 層層解析 Yahoo 的資料樹，揪出該 Ticker 當下的即時狀態數據
                    stores = json_data.get('context', {}).get('dispatcher', {}).get('stores', {})
                    quote_store = stores.get('QuoteSummaryStore', {})
                    price_store = quote_store.get('price', {})
                    
                    if price_store:
                        # 抓取即時價格與昨收
                        current_price = price_store.get('regularMarketPrice', {}).get('raw')
                        prev_price = price_store.get('regularMarketPreviousClose', {}).get('raw')
                        
                        # 特殊處理：某些期貨盤後交易會記錄在 postMarketPrice 裡
                        if price_store.get('marketState') != 'REGULAR':
                            post_price = price_store.get('postMarketPrice', {}).get('raw')
                            if post_price:
                                current_price = post_price
                        
                        if current_price and prev_price:
                            change = current_price - prev_price
                            change_pct = (change / prev_price) * 100
                            
                            data_list.append({
                                "商品名稱": name,
                                "最新價格": float(current_price),
                                "漲跌點數": float(change),
                                "漲跌幅 (%)": float(change_pct)
                            })
                            continue
                            
                # 如果正則解析被防爬蟲擋下，使用最基礎的網頁應急文字匹配 (HTML Streamer 備援)
                price_match = re.search(f'data-field="regularMarketPrice"[^>]*value="([^"]+)"[^>]*data-symbol="{ticker}"', response.text)
                if price_match:
                    price_val = float(price_match.group(1).replace(',', ''))
                    data_list.append({
                        "商品名稱": name, "最新價格": price_val, "漲跌點數": 0.0, "漲跌幅 (%)": 0.0
                    })
                    continue

            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
        except Exception:
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 點擊強制刷新最新跳動"):
    st.cache_data.clear()

with St.spinner("正在精準對齊並同步市場數據..."):
    Df_market = fetch_exact_json_data(market_tickers)

# --- 介面呈現 ---

def render_metric_card(name, df):
    Row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        Row = row_filter.iloc[0]
        if row["最新價格"] != "N/A":
            Val_str = f"{row['最新價格']:,.2f}"
            Delta_str = f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']:+.2f}%)"
            St.metric(label=name, value=val_str, delta=delta_str)
        else:
            St.error(f"❌ {name} 解析失敗")

# 1. 台灣市場區塊
st.subheader("🇹🇼 台灣期貨市場")
render_metric_card("台指期貨 (近月)", df_market)

st.markdown("---")

# 2. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨 (夜盤即時動態)")
col1, col2, col3 = st.columns(3)
futures_names = ["小型道瓊期貨 (小道瓊)", "小型S&P500期貨 (小S&P)", "小型那斯達克期貨 (小那斯達克)"]
cols = [col1, col2, col3]

for name, col in zip(futures_names, cols):
    with col:
        Render_metric_card(name, df_market)

st.markdown("---")

# 3. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)
index_names = ["道瓊工業指數", "S&P 500 指數", "那斯達克綜合指數", "費城半導體指數"]
cols_idx = [col4, col5, col6, col7]

for name, col in zip(index_names, cols_idx):
    with col:
        Render_metric_card(name, df_market)

# 4. 資料總表
st.markdown("### 📋 數據總覽")
st.dataframe(df_market, use_container_width=True)
