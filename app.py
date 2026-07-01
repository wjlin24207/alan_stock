import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板 (網頁即時爬蟲版)")

# 網頁爬蟲對應的 Yahoo Finance 代號
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

@st.cache_data(ttl=5)  # 快取降到 5 秒，確保每次按重新整理都是當下最新
def fetch_real_live_data(tickers_dict):
    data_list = []
    
    # 模擬瀏覽器標頭，避免被 Yahoo 封鎖
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for name, ticker in tickers_dict.items():
        try:
            # 直接進入 Yahoo Finance 該商品的網頁 HTML
            url = f"https://finance.yahoo.com/quote/{ticker}"
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 利用 Yahoo 網頁的關鍵欄位屬性 (data-field) 抓取最新成交價、漲跌點數、漲跌幅
                # 這些欄位包含網頁上正在閃爍的即時即跳數值
                price_element = soup.find('section', {'class': 'container'}).find('span', {'data-field': 'regularMarketPrice'})
                change_element = soup.find('section', {'class': 'container'}).find('span', {'data-field': 'regularMarketChange'})
                pct_element = soup.find('section', {'class': 'container'}).find('span', {'data-field': 'regularMarketChangePercent'})
                
                # 如果是期貨，Yahoo 網頁有時會改用 fin-streamer 標籤
                if not price_element:
                    price_element = soup.find('fin-streamer', {'data-field': 'regularMarketPrice'})
                    change_element = soup.find('fin-streamer', {'data-field': 'regularMarketChange'})
                    pct_element = soup.find('fin-streamer', {'data-field': 'regularMarketChangePercent'})
                
                if price_element:
                    # 取得純文字並移除千分位逗號，轉換為數值
                    price_txt = price_element.text.replace(',', '')
                    change_txt = change_element.text.replace(',', '') if change_element else "0"
                    
                    # 提取百分比中的數字 (例如 +1.23% -> 1.23)
                    pct_txt = pct_element.text if pct_element else "0%"
                    pct_match = re.search(r'([+-]?\d+\.\d+)', pct_txt)
                    pct_val = pct_match.group(1) if pct_match else "0"
                    
                    data_list.append({
                        "商品名稱": name,
                        "最新價格": float(price_txt),
                        "漲跌點數": float(change_txt),
                        "漲跌幅 (%)": float(pct_val)
                    })
                    continue
                    
            # 失敗備援
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
        except Exception:
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 點擊強制刷新最新跳動"):
    st.cache_data.clear()

with st.spinner("正在直接從網頁撈取最新跳動數據..."):
    df_market = fetch_real_live_data(market_tickers)

# --- 介面呈現 ---

def render_metric_card(name, df):
    row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        if row["最新價格"] != "N/A":
            val_str = f"{row['最新價格']:,.2f}"
            delta_str = f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']:+.2f}%)"
            st.metric(label=name, value=val_str, delta=delta_str)
        else:
            st.error(f"❌ {name} 網頁解析失敗")

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
        render_metric_card(name, df_market)

st.markdown("---")

# 3. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)

index_names = ["道瓊工業指數", "S&P 500 指數", "那斯達克綜合指數", "費城半導體指數"]
cols_idx = [col4, col5, col6, col7]

for name, col in zip(index_names, cols_idx):
    with col:
        render_metric_card(name, df_market)

# 4. 資料總表
st.markdown("### 📋 數據總覽")
st.dataframe(df_market, use_container_width=True)
