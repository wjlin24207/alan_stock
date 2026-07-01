import streamlit as st
import yfinance as yf
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板 (穩定強效版)")

# 使用最穩定的代號組合
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

@st.cache_data(ttl=15)  # 快取 15 秒，避免頻繁刷網頁被 Yahoo 封鎖
def fetch_bulletproof_data(tickers_dict):
    data_list = []
    
    for name, ticker in tickers_dict.items():
        try:
            # 策略：抓取最新 1 天、1 分鐘層級的即時 K 線（這在盤後也會持續更新）
            ticker_obj = yf.Ticker(ticker)
            df_snapshot = ticker_obj.history(period="1d", interval="1m")
            
            # 獲取昨日收盤價（用來算今日漲跌）
            # 因為 history(period="1d") 的 previous_close 有時會漏，我們改用歷史日線拿昨收
            df_daily = ticker_obj.history(period="5d", interval="1d")
            
            if not df_snapshot.empty and len(df_daily) >= 2:
                # 最新一分鐘的價格
                current_price = df_snapshot['Close'].iloc[-1]
                
                # 判斷昨收：如果最新 K 線日期跟日 K 最後一天一樣，那昨收就是倒數第二筆
                # 如果不一樣（例如剛開盤），那昨收就是日 K 最後一筆
                prev_price = df_daily['Close'].iloc[-2]
                
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                
                data_list.append({
                    "商品名稱": name,
                    "最新價格": current_price,
                    "漲跌點數": change,
                    "漲跌幅 (%)": change_pct
                })
            else:
                # 備援機制：如果連 1m K 線都沒，就試著抓一般的歷史 Close
                df_fallback = ticker_obj.history(period="2d")
                if len(df_fallback) >= 2:
                    current_price = df_fallback['Close'].iloc[-1]
                    prev_price = df_fallback['Close'].iloc[-2]
                    change = current_price - prev_price
                    change_pct = (change / prev_price) * 100
                    data_list.append({
                        "商品名稱": name, "最新價格": current_price, "漲跌點數": change, "漲跌幅 (%)": change_pct
                    })
                else:
                    data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
        except Exception:
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 重新整理數據"):
    st.cache_data.clear()

with st.spinner("正在強制同步最新即時市場數據..."):
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
