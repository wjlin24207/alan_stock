import streamlit as st
import requests
import pandas as pd

# 設定網頁標題與配置
st.set_page_config(page_title="全球重要指數與期貨看板", layout="wide")
st.title("📊 全球重要指數與期貨即時看板")

# 監控的商品代號、對應跳轉連結，以及 🔴 修正後支援免登入公開渲染的 TradingView 代號
market_tickers = {
    "小道瓊": {"ticker": "YM=F", "url": "https://finance.yahoo.com/quote/YM=F", "tv_symbol": "CAPITALCOM:US30"},
    "小S&P500": {"ticker": "ES=F", "url": "https://finance.yahoo.com/quote/ES=F", "tv_symbol": "CAPITALCOM:US500"},
    "小那斯達克": {"ticker": "NQ=F", "url": "https://finance.yahoo.com/quote/NQ=F", "tv_symbol": "CAPITALCOM:US100"},
    "道瓊指數": {"ticker": "^DJI", "url": "https://finance.yahoo.com/quote/^DJI", "tv_symbol": "DJ:DJI"},
    "S&P500": {"ticker": "^GSPC", "url": "https://finance.yahoo.com/quote/^GSPC", "tv_symbol": "SP:SPX"},
    "那斯達克": {"ticker": "^IXIC", "url": "https://finance.yahoo.com/quote/^IXIC", "tv_symbol": "NASDAQ:IXIC"},
    "費城半導體": {"ticker": "^SOX", "url": "https://finance.yahoo.com/quote/^SOX", "tv_symbol": "PHLX:SOX"}
}

def fetch_yahoo_historical_fallback(ticker):
    """ 核心歷史日線保底 """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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

@st.cache_data(ttl=5)
def fetch_realtime_api_data(tickers_dict):
    data_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    raw_results = {}
    
    for name, info in tickers_dict.items():
        ticker = info["ticker"]
        base_price, base_change, base_pct = fetch_yahoo_historical_fallback(ticker)
        current_price = base_price if base_price else 0.0
        change = base_change if base_change else 0.0
        change_pct = base_pct if base_pct else 0.0
        
        try:
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
                        continue

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
                        continue

            raw_results[name] = (current_price, change, change_pct)
        except Exception:
            raw_results[name] = (current_price, change, change_pct)

    for name in tickers_dict.keys():
        c_price, chg, chg_p = raw_results.get(name, (0.0, 0.0, 0.0))
        data_list.append({
            "商品名稱": name, "最新價格": float(c_price), "漲跌點數": float(chg), "漲跌幅 (%)": float(chg_p)
        })
    return pd.DataFrame(data_list)

if st.button("🔄 點擊強制刷新最新跳動"):
    st.cache_data.clear()

with st.spinner("正在精準同步全球市場最新數據..."):
    df_market = fetch_realtime_api_data(market_tickers)

df_display = df_market.copy()
numeric_cols = ["最新價格", "漲跌點數", "漲跌幅 (%)"]
df_display[numeric_cols] = df_display[numeric_cols].round(2)

def render_custom_metric_with_chart(name, df, tickers_dict):
    row_filter = df[df["商品名稱"] == name]
    if not row_filter.empty:
        row = row_filter.iloc[0]
        price = row["最新價格"]
        change = row["漲跌點數"]
        pct = row["漲跌幅 (%)"]
        
        target_url = tickers_dict.get(name, {}).get("url", "#")
        tv_symbol = tickers_dict.get(name, {}).get("tv_symbol", "")
        
        if price > 0:
            if change > 0:
                color = "#00B050" if "F" in tickers_dict.get(name, {}).get("ticker", "") and name != "台指期貨 (近月)" else "#FF4B4B"
                # 配合美股顏色：上漲為綠，下跌為紅
                color = "#00B050" if change > 0 else "#FF4B4B"
                icon = "▲" if change > 0 else "▼"
                sign = "+" if change > 0 else ""
            elif change < 0:
                color = "#FF4B4B"
                icon = "▼"
                sign = ""
            else:
                color = "#888888"
                icon = "—"
                sign = ""
                
            # 🔴 統一介面顏色呈現：畫面上顯示綠色代表上漲，紅色代表下跌
            if change > 0:
                color = "#00B050"
                icon = "▲"
                sign = "+"
            elif change < 0:
                color = "#FF4B4B"
                icon = "▼"
                sign = ""
            else:
                color = "#888888"
                icon = "—"
                sign = ""
            
            st.markdown(
                f"""
                <a href="{target_url}" target="_blank" style="text-decoration: none; color: inherit;">
                    <div style="
                        background-color: #1E222D; 
                        padding: 16px; 
                        border-radius: 10px 10px 0px 0px; 
                        border-left: 6px solid {color};
                        cursor: pointer;
                        transition: background-color 0.2s ease;
                    " onmouseover="this.style.backgroundColor='#242936';" onmouseout="this.style.backgroundColor='#1E222D';">
                        <div style="color: #AEB3B7; font-size: 14px; font-weight: 500; margin-bottom: 6px;">{name} ↗</div>
                        <div style="color: #FFFFFF; font-size: 26px; font-weight: 700; font-family: monospace; line-height: 1.2;">{price:,.2f}</div>
                        <div style="color: {color}; font-size: 14px; font-weight: 600; margin-top: 4px; font-family: monospace;">
                            {icon} {sign}{change:,.2f} ({sign}{pct:.2f}%)
                        </div>
                    </div>
                </a>
                """, 
                unsafe_allow_html=True
            )
            
            tv_html = f"""
            <div class="tradingview-widget-container" style="height:200px; width:100%;">
              <div id="tradingview_{name}" style="height:200px; width:100%;"></div>
              <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
              <script type="text/javascript">
              new TradingView.widget({{
                "autosize": true,
                "symbol": "{tv_symbol}",
                "interval": "1",
                "timezone": "Asia/Taipei",
                "theme": "dark",
                "style": "3",
                "locale": "zh_TW",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_legend": true,
                "hide_side_toolbar": true,
                "save_image": false,
                "container_id": "tradingview_{name}"
              }});
              </script>
            </div>
            """
            st.components.v1.html(tv_html, height=200)

# --- 介面呈現 ---

# 1. 美國三大期貨區塊
st.subheader("🇺🇸 美國重要指數期貨 (夜盤即時動態)")
col1, col2, col3 = st.columns(3)
with col1: render_custom_metric_with_chart("小道瓊", df_display, market_tickers)
with col2: render_custom_metric_with_chart("小S&P500", df_display, market_tickers)
with col3: render_custom_metric_with_chart("小那斯達克", df_display, market_tickers)

st.markdown("---")

# 2. 美國四大現貨指數區塊
st.subheader("🏛️ 美國現貨指數")
col4, col5, col6, col7 = st.columns(4)
with col4: render_custom_metric_with_chart("道瓊指數", df_display, market_tickers)
with col5: render_custom_metric_with_chart("S&P500", df_display, market_tickers)
with col6: render_custom_metric_with_chart("那斯達克", df_display, market_tickers)
with col7: render_custom_metric_with_chart("費城半導體", df_display, market_tickers)

# 3. 資料總表
st.markdown("### 📋 數據總覽")
def style_positive_negative(val):
    if isinstance(val, (int, float)):
        if val > 0: return 'color: #00B050; font-weight: bold;'
        elif val < 0: return 'color: #FF4B4B; font-weight: bold;'
    return ''

df_final_table = df_display.fillna("N/A")
styled_df = df_final_table.style.map(style_positive_negative, subset=["漲跌點數", "漲跌幅 (%)"])

st.dataframe(
    styled_df, use_container_width=True, hide_index=True,
    column_config={
        "最新價格": st.column_config.NumberColumn(format="%.2f"),
        "漲跌點數": st.column_config.NumberColumn(format="%.2f"),
        "漲跌幅 (%)": st.column_config.NumberColumn(format="%.2f%%")
    }
)
