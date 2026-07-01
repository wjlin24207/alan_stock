import streamlit as st
import yfinance as yf
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板")

# 定義商品代號清單
# 注意：yfinance 的台指期連續合約代號通常為 'WTX=F' 或 'TX=F'，美股期貨為 '=F' 結尾，指數為 '^' 開頭
market_tickers = {
    "台指期貨 (近月)": "WTX=F",
    "微型道瓊期貨 (小道瓊)": "MYM=F",
    "微型S&P500期貨 (小S&P)": "MES=F",
    "微型那斯達克期貨 (小那斯達克)": "MNQ=F",
    "道瓊工業指數": "^DJI",
    "S&P 500 指數": "^GSPC",
    "那斯達克綜合指數": "^IXIC",
    "費城半導體指數": "^SOX"
}

@st.cache_data(ttl=60)  # 快取資料 60 秒，避免頻繁刷網頁被 Yahoo 封鎖
def fetch_market_data(tickers_dict):
    data_list = []
    for name, ticker in tickers_dict.items():
        try:
            # 獲取最近 2 天的數據以計算昨日收盤
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="2d")
            
            if len(df) >= 2:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                
                data_list.append({
                    "商品名稱": name,
                    "最新價格": round(current_price, 2),
                    "漲跌點數": round(change, 2),
                    "漲跌幅 (%)": round(change_pct, 2)
                })
            else:
                # 只有一筆資料時嘗試拿 info
                info = ticker_obj.info
                current_price = info.get('regularMarketPrice') or info.get('currentPrice')
                prev_price = info.get('previousClose')
                
                if current_price and prev_price:
                    change = current_price - prev_price
                    change_pct = (change / prev_price) * 100
                    data_list.append({
                        "商品名稱": name,
                        "最新價格": round(current_price, 2),
                        "漲跌點數": round(change, 2),
                        "漲跌幅 (%)": round(change_pct, 2)
                    })
        except Exception as e:
            # 若擷取失敗則填入空值
            data_list.append({
                "商品名稱": name, "最新價格": "N/A", "漲跌點數": "N/A", "漲跌幅 (%)": "N/A"
            })
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 重新整理數據"):
    st.cache_data.clear()

with st.spinner("正在獲取最新市場數據..."):
    df_market = fetch_market_data(market_tickers)

# --- 介面呈現 ---

# 1. 台灣市場區塊
st.subheader("🇹🇼 台灣期貨市場")
taiwan_data = df_market[df_market["商品名稱"] == "台指期貨 (近月)"].iloc[0]

if taiwan_data["最新價格"] != "N/A":
    st.metric(
        label=taiwan_data["商品名稱"],
        value=f"{taiwan_data['最新價格']:,}",
        delta=f"{taiwan_data['漲跌點數']筑:+} ({taiwan_data['漲跌幅 (%)']筑:+_}%)"
    )
else:
    st.error("無法取得台指期最新數據，可能此時段無報價。")

st.markdown("---")

# 2. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨")
col1, col2, col3 = st.columns(3)

futures_names = ["微型道瓊期貨 (小道瓊)", "微型S&P500期貨 (小S&P)", "微型那斯達克期貨 (小那斯達克)"]
cols = [col1, col2, col3]

for name, col in zip(futures_names, cols):
    row = df_market[df_market["商品名稱"] == name].iloc[0]
    with col:
        if row["最新價格"] != "N/A":
            st.metric(label=name, value=f"{row['最新價格']:,}", delta=f"{row['漲跌點數']筑:+} ({row['漲跌幅 (%)']筑:+_}%)")
        else:
            st.caption(f"{name} 暫無資料")

st.markdown("---")

# 3. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)

index_names = ["道瓊工業指數", "S&P 500 指數", "那斯達克綜合指數", "費城半導體指數"]
cols_idx = [col4, col5, col6, col7]

for name, col in zip(index_names, cols_idx):
    row = df_market[df_market["商品名稱"] == name].iloc[0]
    with col:
        if row["最新價格"] != "N/A":
            st.metric(label=name, value=f"{row['最新價格']:,}", delta=f"{row['漲跌點數']:,} ({row['漲跌幅 (%)']:,}%)")
        else:
            st.caption(f"{name} 暫無資料")

# 4. 資料總表
st.markdown("### 📋 數據總覽")
st.dataframe(df_market, use_container_width=True)
