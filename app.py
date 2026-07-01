import streamlit as st
import requests
import pandas as pd
import datetime

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

def fetch_twse_official():
    """ 🔴 第二層防線：直接調用台灣證交所官方大盤歷史資料 """
    try:
        url = "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) >= 2:
                latest_day = data[-1]
                price = float(latest_day.get("ClosingIndex", "0").replace(',', ''))
                prev_day = data[-2]
                prev_price = float(prev_day.get("ClosingIndex", "0").replace(',', ''))
                
                change = price - prev_price
                change_pct = (change / prev_price) * 100
                return price, change, change_pct
    except Exception:
        pass
    return None, None, None

def fetch_yfinance_daily_fallback(ticker):
    """ 🔴 第三層防線（極致保底）：利用歷史 Chart 接口直接拉 3 天的日線收盤價，此接口最不容易被擋 """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            res_json = response.json()
            result = res_json.get('chart', {}).get('result', [{}])[0]
            indicators = result.get('indicators', {}).get('quote', [{}])[0]
            close_prices = [p for p in indicators.get('close', []) if p is not None]
            
            if len(close_prices) >= 2:
                current_price = close_prices[-1]
                prev_price = close_prices[-2]
                change = current_price - prev_price
                change_pct = (change / prev_price) * 100
                return current_price, change, change_pct
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=5)  # 快取 5 秒，確保即時刷新
def fetch_realtime_api_data(tickers_dict):
    data_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for name, ticker in tickers_dict.items():
        current_price = None
        change = None
        change_pct = None
        try:
            # 1. 第一層嘗試：即時 Chart API 接口
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
            response = requests.get(url, headers=headers, timeout=4)
            
            if response.status_code == 200:
                res_json = response.json()
                meta = res_json.get('chart', {}).get('result', [{}])[0].get('meta', {})
                if meta:
                    current_price = meta.get('regularMarketPrice')
                    prev_price = meta.get('previousClose')
                    if current_price and prev_price:
                        change = current_price - prev_price
                        change_pct = (change / prev_price) * 100

            # 2. 第二層與第三層嘗試（特別針對未開盤或無資料商品進行保底）
            if current_price is None or pd.isna(current_price):
                if name == "台指期貨 (近月)":
                    # 優先找證交所
                    tw_price, tw_change, tw_pct = fetch_twse_official()
                    if tw_price:
                        current_price, change, change_pct = tw_price, tw_change, tw_pct
                    else:
                        # 證交所失敗，用 Yahoo 日線保底
                        yf_price, yf_change, yf_pct = fetch_yfinance_daily_fallback(ticker)
                        if yf_price:
                            current_price, change, change_pct = yf_price, yf_change, yf_pct
                else:
                    # 美股商品若 1m 接口失效，直接啟動日線保底
                    yf_price, yf_change, yf_pct = fetch_yfinance_daily_fallback(ticker)
                    if yf_price:
                        current_price, change, change_pct = yf_price, yf_change, yf_pct

            if current_price is not None:
                data_list.append({
                    "商品名稱": name,
                    "最新價格": float(current_price),
                    "漲跌點數": float(change) if change is not None else 0.0,
                    "漲跌幅 (%)": float(change_pct) if change_pct is not None else 0.0
                })
            else:
                data_list.append({"商品名稱": name, "最新價格": None, "漲跌點數": None, "漲跌幅 (%)": None})
                
        except Exception:
            # 萬一整個主程序崩潰，進入最終無條件保底
            yf_price, yf_change, yf_pct = fetch_yfinance_daily_fallback(ticker)
            if yf_price is not None:
                data_list.append({
                    "商品名稱": name, "最新價格": float(yf_price), "漲跌點數": float(yf_change), "漲跌幅 (%)": float(yf_pct)
                })
            else:
                data_list.append({"商品名稱": name, "最新價格": None, "漲跌點數": None, "漲跌幅 (%)": None})
            
    return pd.DataFrame(data_list)

# 重新整理按鈕
if st.button("🔄 點擊強制刷新最新跳動"):
    st.cache_data.clear()

with st.spinner("正在精準同步全球市場最新數據..."):
    df_market = fetch_realtime_api_data(market_tickers)

# --- 數據優化處理 ---
df_display = df_market.copy()
numeric_cols = ["最新價格", "漲跌點數", "漲跌幅 (%)"]
df_display[numeric_cols] = df_display[numeric_cols].round(2)

# --- 自訂精美即時字卡元件 (100% 掌握台股紅漲綠跌邏輯) ---
def render_custom_metric(name, df):
    row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        price = row["最新價格"]
        change = row["漲跌點數"]
        pct = row["漲跌幅 (%)"]
        
        if pd.notna(price):
            if change > 0:
                color = "#FF4B4B"  # 上漲為紅
                icon = "▲"
                sign = "+"
            elif change < 0:
                color = "#00B050"  # 下跌為綠
                icon = "▼"
                sign = ""
            else:
                color = "#888888"  # 平盤為灰
                icon = "—"
                sign = ""
            
            st.markdown(
                f"""
                <div style="
                    background-color: #1E222D; 
                    padding: 16px; 
                    border-radius: 10px; 
                    border-left: 6px solid {color};
                    margin-bottom: 12px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    <div style="color: #AEB3B7; font-size: 14px; font-weight: 500; margin-bottom: 6px;">{name}</div>
                    <div style="color: #FFFFFF; font-size: 28px; font-weight: 700; font-family: monospace; line-height: 1.2;">{price:,.2f}</div>
                    <div style="color: {color}; font-size: 15px; font-weight: 600; margin-top: 4px; font-family: monospace;">
                        {icon} {sign}{change:,.2f} ({sign}{pct:.2f}%)
                    </div>
                </div>
                """, 
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"""
                <div style="
                    background-color: #1E222D; 
                    padding: 16px; 
                    border-radius: 10px; 
                    border-left: 6px solid #FF4B4B;
                    margin-bottom: 12px;
                ">
                    <div style="color: #AEB3B7; font-size: 14px;">{name}</div>
                    <div style="color: #FF4B4B; font-size: 16px; font-weight: bold; margin-top: 5px;">❌ 暫無此時段盤後即時資料</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

# --- 介面呈現 ---

# 1. 台灣市場區塊
st.subheader("🇹🇼 台灣期貨市場")
render_custom_metric("台指期貨 (近月)", df_display)

st.markdown("---")

# 2. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨 (夜盤即時動態)")
col1, col2, col3 = st.columns(3)
futures_names = ["小道瓊", "小S&P500", "小那斯達克"]
cols = [col1, col2, col3]

for name, col in zip(futures_names, cols):
    with col:
        render_custom_metric(name, df_display)

st.markdown("---")

# 3. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)
index_names = ["道瓊指數", "S&P500", "那斯達克", "費城半導體"]
cols_idx = [col4, col5, col6, col7]

for name, col in zip(index_names, cols_idx):
    with col:
        render_custom_metric(name, df_display)

# 4. 資料總表
st.markdown("### 📋 數據總覽")

def style_positive_negative(val):
    if isinstance(val, (int, float)):
        if val > 0:
            return 'color: #FF4B4B; font-weight: bold;'
        elif val < 0:
            return 'color: #00B050; font-weight: bold;'
    return ''

df_final_table = df_display.fillna("N/A")
styled_df = df_final_table.style.map(style_positive_negative, subset=["漲跌點數", "漲跌幅 (%)"])

st.dataframe(
    styled_df, 
    use_container_width=True,
    hide_index=True,
    column_config={
        "最新價格": st.column_config.NumberColumn(format="%.2f"),
        "漲跌點數": st.column_config.NumberColumn(format="%.2f"),
        "漲跌幅 (%)": st.column_config.NumberColumn(format="%.2f%%")
    }
)
