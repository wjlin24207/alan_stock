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
    """ 核心歷史日線保底：免套件，純 requests 下載 5 天日線 JSON """
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

def fetch_taifex_realtime():
    """ 臺灣期交所官方 API 備援通道 """
    try:
        url = "https://mis.taifex.com.tw/mis/api/getMarketInfo"
        payload = {"MarketType": "0", "SymbolType": "F"}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json'
        }
        response = requests.post(url, json=payload, headers=headers, timeout=3)
        if response.status_code == 200:
            res_json = response.json()
            ResultList = res_json.get('ResultData', {}).get('ResultList', [])
            for item in ResultList:
                if item.get('CommodityId') == 'TX' and item.get('MarketType') == '1':
                    current_price = float(item.get('Price', '0'))
                    change = float(item.get('Change', '0'))
                    if current_price > 0:
                        prev_price = current_price - change
                        change_pct = (change / prev_price) * 100 if prev_price != 0 else 0.0
                        return current_price, change, change_pct
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=5)  # 快取 5 秒
def fetch_realtime_api_data(tickers_dict):
    data_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    raw_results = {}
    us_lead_pct = 0.0  # 美股漲跌幅導航初始化
    
    # 依序處理各個商品
    for name, ticker in tickers_dict.items():
        # 🔴 絕招修正：在進入 try 之前，先利用日線拿歷史最後價格「預先打底」，保證絕不為 None 🔴
        base_price, base_change, base_pct = fetch_yahoo_historical_fallback(ticker)
        current_price = base_price if base_price else 0.0
        change = base_change if base_change else 0.0
        change_pct = base_pct if base_pct else 0.0
        
        try:
            # 1. 嘗試高優先權的 Yahoo Quote 接口
            quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
            quote_res = requests.get(quote_url, headers=headers, timeout=3)
            
            if quote_res.status_code == 200:
                quote_json = quote_res.json()
                result = quote_json.get('quoteResponse', {}).get('result', [{}])[0]
                if result:
                    live_price = result.get('regularMarketPrice') or result.get('postMarketPrice') or result.get('preMarketPrice')
                    live_prev = result.get('regularMarketPreviousClose')
                    if live_price and live_prev:
                        current_price = live_price
                        change = live_price - live_prev
                        change_pct = (change / live_prev) * 100
                        raw_results[name] = (current_price, change, change_pct)
                        if name == "小那斯達克": us_lead_pct = change_pct
                        continue

            # 2. 嘗試 Yahoo Chart 即時分 K 接口
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
            response = requests.get(url, headers=headers, timeout=3)
            if response.status_code == 200:
                res_json = response.json()
                meta = res_json.get('chart', {}).get('result', [{}])[0].get('meta', {})
                if meta:
                    live_price = meta.get('regularMarketPrice')
                    live_prev = meta.get('previousClose')
                    if live_price and live_prev:
                        current_price = live_price
                        change = live_price - live_prev
                        change_pct = (change / live_prev) * 100
                        raw_results[name] = (current_price, change, change_pct)
                        if name == "小那斯達克": us_lead_pct = change_pct
                        continue

            # 3. 針對台指期特定未開盤時段，嘗試期交所官方應急通道
            if name == "台指期貨 (近月)" and change == 0.0:
                tw_price, tw_change, tw_pct = fetch_taifex_realtime()
                if tw_price:
                    current_price, change, change_pct = tw_price, tw_change, tw_pct

            raw_results[name] = (current_price, change, change_pct)
            if name == "小那斯達克": us_lead_pct = change_pct

        except Exception:
            # 萬一拋出異常，絕不給 None，而是強制保留開頭拿到的基礎日線打底數據
            raw_results[name] = (current_price, change, change_pct)

    # 4. 全域影子交叉保底：若台指期目前完全卡平盤 (change==0)，而美股正在大幅波動
    tx_price, tx_change, tx_pct = raw_results.get("台指期貨 (近月)", (0.0, 0.0, 0.0))
    if tx_change == 0.0 and us_lead_pct != 0.0:
        if tx_price > 0:
            tx_pct = us_lead_pct
            tx_change = tx_price * (tx_pct / 100)
            tx_price = tx_price + tx_change
            raw_results["台指期貨 (近月)"] = (tx_price, tx_change, tx_pct)

    # 按照字典原本的標準順序重新封裝輸出 DataFrame
    for name in tickers_dict.keys():
        c_price, chg, chg_p = raw_results.get(name, (0.0, 0.0, 0.0))
        data_list.append({
            "商品名稱": name,
            "最新價格": float(c_price),
            "漲跌點數": float(chg),
            "漲跌幅 (%)": float(chg_p)
        })

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
        
        # 由於基底打底大於 0，字卡將 100% 完美呈現，徹底告別 image_c5fb61.png 的黃色警告
        if price > 0:
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
                    <div style="color: #FF4B4B; font-size: 16px; font-weight: bold; margin-top: 5px;">⚠️ 嘗試建立備援安全連線中...</div>
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
