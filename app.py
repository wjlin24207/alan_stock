import streamlit as st
import yfinance as yf
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板")

# 商品代號清單
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

@st.cache_data(ttl=10)  # 縮短到 10 秒，確保抓到最新的盤後走勢
def fetch_realtime_data(tickers_dict):
    data_list = []
    for name, ticker in tickers_dict.items():
        try:
            ticker_obj = yf.Ticker(ticker)
            
            # 使用 fast_info 獲取交易所當下的最新即時價格
            fast = ticker_obj.fast_info
            current_price = fast.get('last_price') or fast.get('regular_market_price')
            prev_price = fast.get('previous_close') or fast.get('regular_market_previous_close')
            
            # 如果 fast_info 拿不到，改用歷史 K 線最後一筆作為備援
            if not current_price or not prev_price:
                df = ticker_obj.history(period="2d")
                if len(df) >= 2:
                    current_price = df['Close'].iloc[-1]
                    prev_price = df['Close'].iloc[-2]

            if current_price and prev_price and not pd.isna(current_price) and not pd.isna(prev_price):
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                
                data_list.append({
                    "商品名稱": name,
                    "最新價格": current_price,
                    "漲跌點數": change,
                    "漲跌幅 (%)": change_pct
                })
            else:
                data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
        except Exception:
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 重新整理數據"):
    st.cache_data.clear()

with st.spinner("正在獲取最新即時市場數據..."):
    df_market = fetch_realtime_data(market_tickers)

# --- 介面呈現 ---

# Helper 函數：統一渲染卡片並修正格式化問題
def render_metric_card(name, df):
    row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        if row["最新價格"] != "N/A":
            # 修正了這裡的格式化語法，將正負號與小數點正確帶入
            val_str = f"{row['最新價格']烘:,.2f}"
            delta_str = f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']:+.2f}%)"
            st.metric(label=name, value=val_str, delta=delta_str)
        else:
            st.caption(f"⚪ {name} 暫無即時資料")

# 1. 台灣市場區塊
st.subheader("🇹🇼 台灣期貨市場")
render_metric_card("台指期貨 (近月)", df_market)

st.markdown("---")

# 2. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨")
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
