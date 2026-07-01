import streamlit as st
import requests
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板 (API 精準即時版)")

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
def fetch_realtime_api_data(tickers_dict):
    data_list = []
    # 模擬標準瀏覽器標頭
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for name, ticker in tickers_dict.items():
        try:
            # 使用 Yahoo Finance 的 Chart API 接口（回傳純 JSON，反應最即時、最不易被阻擋）
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                res_json = response.json()
                meta = res_json.get('chart', {}).get('result', [{}])[0].get('meta', {})
                
                if meta:
                    # 提取即時最新成交價與前一日收盤價
                    current_price = meta.get('regularMarketPrice')
                    prev_price = meta.get('previousClose')
                    
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
                        
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
        except Exception:
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 點擊強制刷新最新跳動"):
    st.cache_data.clear()

# 修正了 image_ad061e.png 中大寫 St.spinner 的 Bug
with st.spinner("正在精準同步全球市場最新數據..."):
    df_market = fetch_realtime_api_data(market_tickers)

# --- 介面呈現 ---

def render_metric_card(name, df):
    row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        if row["最新價格"] != "N/A":
            val_str = f"{row['最新價格']:,.2f}"
            delta_str = f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']:+.2f}%)"
            # 確保這裡也是標準的小寫 st.metric
            st.metric(label=name, value=val_str, delta=delta_str)
        else:
            st.error(f"❌ {name} 即時資料獲取失敗")

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
