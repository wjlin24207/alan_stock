import streamlit as str_  # 避免關鍵字衝突
import streamlit as st
import yfinance as yf
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板")

# 更換為更穩定的 E-mini 小型期貨代號
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

@st.cache_data(ttl=30)  # 縮短快取時間至 30 秒，維持即時性
def fetch_market_data(tickers_dict):
    data_list = []
    for name, ticker in tickers_dict.items():
        try:
            # 抓取 3 天數據確保扣除假日或開盤空窗期後仍有足夠 K 線
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="3d")
            
            if df.empty:
                # 嘗試用快照方式拿資料
                info = ticker_obj.info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice')
                prev_price = info.get('previousClose')
            else:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                
            if current_price and prev_price and not pd.isna(current_price) and not pd.isna(prev_price):
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                
                data_list.append({
                    "商品名稱": name,
                    "最新價格": round(current_price, 2),
                    "漲跌點數": round(change, 2),
                    "漲跌幅 (%)": round(change_pct, 2)
                })
            else:
                data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
        except Exception as e:
            data_list.append({"商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 重新整理數據"):
    st.cache_data.clear()

with st.spinner("正在獲取最新市場數據..."):
    df_market = fetch_market_data(market_tickers)

# --- 介面呈現 ---

# 1. 台灣市場區塊
st.subheader("🇹🇼 台灣期貨市場")
taiwan_rows = df_market[df_market["商品名稱"] == "台指期貨 (近月)"]
if not taiwan_rows.empty:
    taiwan_data = taiwan_rows.iloc[0]
    if taiwan_data["最新價格"] != "N/A":
        st.metric(
            label=taiwan_data["商品名稱"],
            value=f"{taiwan_data['最新價格']:,}",
            delta=f"{taiwan_data['漲跌點數']:+.2f} ({taiwan_data['漲跌幅 (%)']}:+.2f%)"
        )
    else:
        st.warning("⚠️ 台指期目前非交易時段或 Yahoo 未提供盤後夜盤即時報價。")

st.markdown("---")

# 2. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨")
col1, col2, col3 = st.columns(3)

futures_names = ["小型道瓊期貨 (小道瓊)", "小型S&P500期貨 (小S&P)", "小型那斯達克期貨 (小那斯達克)"]
cols = [col1, col2, col3]

for name, col in zip(futures_names, cols):
    row_filter = df_market[df_market["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        with col:
            if row["最新價格"] != "N/A":
                st.metric(
                    label=name, 
                    value=f"{row['最新價格']:,}", 
                    delta=f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']}:+.2f%)"
                )
            else:
                st.caption(f"⚪ {name} 暫無資料")

st.markdown("---")

# 3. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)

index_names = ["道瓊工業指數", "S&P 500 指數", "那斯達克綜合指數", "費城半導體指數"]
cols_idx = [col4, col5, col6, col7]

for name, col in zip(index_names, cols_idx):
    row_filter = df_market[df_market["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        with col:
            if row["最新價格"] != "N/A":
                st.metric(
                    label=name, 
                    value=f"{row['最新價格']:,}", 
                    delta=f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']}:+.2f%)"
                )
            else:
                st.caption(f"⚪ {name} 暫無資料")

# 4. 資料總表
st.markdown("### 📋 數據總覽")
st.dataframe(df_market, use_container_width=True)
