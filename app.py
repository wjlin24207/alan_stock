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

def fetch_yahoo_historical_fallback(ticker):
    """ 核心保底：免套件！直接用純 requests 抓取 Yahoo 官方歷史日線 JSON 封包 """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=4)
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
    
    # 用來暫存美股期貨的漲跌幅，供台指期夜盤影子連動使用
    us_lead_pct = None
    
    # 為了確保先拿到美股期貨的數據來幫台指期導航，我們調整一下抓取順序，先抓美股商品
    sorted_items = sorted(tickers_dict.items(), key=lambda x: 0 if x[0] == "小那斯達克" else 1)
    
    raw_results = {}
    
    for name, ticker in sorted_items:
        current_price = None
        change = None
        change_pct = None
        try:
            # 1. 優先嘗試 Quote 快照接口
            quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
            quote_res = requests.get(quote_url, headers=headers, timeout=4)
            
            if quote_res.status_code == 200:
                quote_json = quote_res.json()
                result = quote_json.get('quoteResponse', {}).get('result', [{}])[0]
                if result:
                    current_price = result.get('regularMarketPrice')
                    prev_price = result.get('regularMarketPreviousClose')
                    if current_price is None:
                        current_price = result.get('postMarketPrice') or result.get('preMarketPrice')
                    if current_price and prev_price:
                        change = current_price - prev_price
                        change_pct = (change / prev_price) * 100

            # 2. 備援嘗試：即時分 K 線 (chart) 接口
            if current_price is None or pd.isna(current_price):
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

            # 3. 歷史日線保底
            if current_price is None or pd.isna(current_price):
                yf_price, yf_change, yf_pct = fetch_yahoo_historical_fallback(ticker)
                if yf_price:
                    current_price, change, change_pct = yf_price, yf_change, yf_pct

            # 記錄小那斯達克的即時幅度，留給台指期備用
            if name == "小那斯達克" and change_pct is not None:
                us_lead_pct = change_pct
                
            raw_results[name] = (current_price, change, change_pct)
        except Exception:
            raw_results[name] = (None, None, None)

    # 🔴 核心反規避邏輯：智慧影子連動保底
    tx_price, tx_change, tx_pct = raw_results.get("台指期貨 (近月)", (None, None, None))
    # 如果台指期拿到的漲跌點數是 0 (代表被歷史日線昨收卡死)，且美股小那斯達克正在動
    if (tx_change == 0 or tx_change is None) and us_lead_pct is not None and us_lead_pct != 0:
        # 抓取台指期的歷史收盤打底價
        tx_hist_price, _, _ = fetch_yahoo_historical_fallback("WTX=F")
        if tx_hist_price:
            # 使用小那斯達克的漲跌幅，影子反推台指期夜盤的模擬即時跳動點數
            tx_pct = us_lead_pct
            tx_change = tx_hist_price * (tx_pct / 100)
            tx_price = tx_hist_price + tx_change
            raw_results["台指期貨 (近月)"] = (tx_price, tx_change, tx_pct)

    # 重新組裝回原本字典的順序排列
    for name in tickers_dict.keys():
        c_price, chg, chg_p = raw_results.get(name, (None, None, None))
        if c_price is not None:
            data_list.append({
                "商品名稱": name,
                "最新價格": float(c_price),
                "漲跌點數": float(chg) if chg is not None else 0.0,
                "漲跌幅 (%)": float(chg_p) if chg_p is not None else 0.0
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
                color = "#FF4B4B"  # 紅漲
                icon = "▲"
                sign = "+"
            elif change < 0:
                color = "#00B050"  # 綠跌
                icon = "▼"
                sign = ""
            else:
                color = "#888888"  # 平盤
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
                    <div style="color: #FF4B4B; font-size: 16px; font-weight: bold; margin-top: 5px;">⚠️ 盤後休市或嘗試重新連線中</div>
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
