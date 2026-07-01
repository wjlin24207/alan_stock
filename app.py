import streamlit as st
import yfinance as yf
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板 (終極相容版)")

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

@st.cache_data(ttl=15)  # 快取 15 秒，避免頻繁請求
def fetch_bulletproof_data(tickers_dict):
    data_list = []
    
    for name, ticker in tickers_dict.items():
        current_price = None
        prev_price = None
        
        try:
            ticker_obj = yf.Ticker(ticker)
            
            # 第一層：下載歷史日 K 線（最穩定的標準 API，不易被阻擋）
            df_daily = ticker_obj.history(period="5d", interval="1d")
            
            if not df_daily.empty and len(df_daily) >= 2:
                current_price = df_daily['Close'].iloc[-1]
                prev_price = df_daily['Close'].iloc[-2]
            
            # 第二層備援（針對盤後夜盤）：若第一層拿到的價格非最新，或想補足最新即時跳動
            # 直接讀取 .info 字典，這個字典在盤後也會更新最後一筆成交價
            try:
                info = ticker_obj.info
                # 如果 info 裡有最新的盤後即時價，就覆蓋日 K 線的舊價格
                live_price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('ask') or info.get('bid')
                live_prev = info.get('regularMarketPreviousClose') or info.get('previousClose')
                
                if live_price and live_price > 0:
                    current_price = live_price
                if live_prev and live_prev > 0:
                    prev_price = live_prev
            except Exception:
                pass # 若 info 被限制，至少還有第一層的日 K 線資料打底
                
            # 計算漲跌
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

with st.spinner("正在強制同步最新市場數據..."):
    df_market = fetch_bulletproof_data(market_tickers)

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
            st.error(f"❌ {name} 暫無即時資料")

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
