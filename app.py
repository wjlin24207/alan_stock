import streamlit as st
import requests
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板")

# 監控的商品代號
market_tickers = {
    "台指期貨 (近月)": "WTX=F",
    "小道瓊": "YM=F",
    "小S&P500": "ES=F",
    "小那斯達克": "NQ=F",
    "道瓊指數": "^DJI",
    "S&P500": "^GSPC",
    "那斯達克": "^IXIC",
    "費城半導體": "^SOX"
}

@st.cache_data(ttl=5)  # 快取 5 秒，確保即時刷新
def fetch_realtime_api_data(tickers_dict):
    data_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for name, ticker in tickers_dict.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                res_json = response.json()
                meta = res_json.get('chart', {}).get('result', [{}])[0].get('meta', {})
                
                if meta:
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
                        
            data_list.append({"商品名稱": name, "最新價格": None, "漲跌點數": None, "漲跌幅 (%)": None})
        except Exception:
            data_list.append({"商品名稱": name, "最新價格": None, "漲跌點數": None, "漲跌幅 (%)": None})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 點擊強制刷新最新跳動"):
    st.cache_data.clear()

with st.spinner("正在精準同步全球市場最新數據..."):
    df_market = fetch_realtime_api_data(market_tickers)

# --- 數據優化處理 ---
# 複製一份資料用來做介面呈現，並將數值欄位統一四捨五入到小數後兩位
df_display = df_market.copy()
numeric_cols = ["最新價格", "漲跌點數", "漲跌幅 (%)"]
df_display[numeric_cols] = df_display[numeric_cols].round(2)

# --- 介面呈現 ---

def render_metric_card(name, df):
    row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        if pd.notna(row["最新價格"]):
            val_str = f"{row['最新價格']:,.2f}"
            delta_str = f"{row['漲跌點數']:+.2f} ({row['漲跌幅 (%)']:+.2f}%)"
            st.metric(label=name, value=val_str, delta=delta_str)
        else:
            st.error(f"❌ {name} 即時資料獲取失敗")

# 1. 台灣市場區塊
st.subheader("🇹🇼 台灣期貨市場")
render_metric_card("台指期貨 (近月)", df_display)

st.markdown("---")

# 2. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨 (夜盤即時動態)")
col1, col2, col3 = st.columns(3)
futures_names = ["小道瓊", "小S&P500", "小那斯達克"]
cols = [col1, col2, col3]

for name, col in zip(futures_names, cols):
    with col:
        render_metric_card(name, df_display)

st.markdown("---")

# 3. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)
index_names = ["道瓊指數", "S&P500", "那斯達克", "費城半導體"]
cols_idx = [col4, col5, col6, col7]

for name, col in zip(index_names, cols_idx):
    with col:
        render_metric_card(name, df_display)

# 4. 資料總表（將 NaN 填補為 "N/A" 方便看盤，且已格式化至小數點後兩位）
st.markdown("### 📋 數據總覽")
df_final_table = df_display.fillna("N/A")

# 使用 Streamlit 的 column_config 確保千分位逗號與小數點兩位完美呈現
st.dataframe(
    df_final_table, 
    use_container_width=True,
    column_config={
        "最新價格": st.column_config.NumberColumn(format="%.2f"),
        "漲跌點數": st.column_config.NumberColumn(format="%.2f"),
        "漲跌幅 (%)": st.column_config.NumberColumn(format="%.2f")
    }
)
