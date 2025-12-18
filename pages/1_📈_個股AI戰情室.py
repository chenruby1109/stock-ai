import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
import json

# --- 網頁設定 ---
st.set_page_config(page_title="全台股 AI 獵手", page_icon="🕵️", layout="wide")

st.title("🕵️ Miniko AI 全台股獵手 (V24.0 動態熱門版)")
st.markdown("### 🚀 鎖定「今日成交量前 100 大」，AI 自動掃描飆股型態")
st.info("💡 系統會自動抓取 Yahoo 股市即時排行榜，名單每天都不一樣！")

# --- 核心工具：抓取 Yahoo 排行榜 (爬蟲) ---
@st.cache_data(ttl=3600) # 1小時更新一次名單即可
def get_top_volume_stocks():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 1. 抓上市 (TAI) 前 80 名
        url_tai = "https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.rank;exchange=TAI;rankType=volume;limit=80"
        res_tai = requests.get(url_tai, headers=headers)
        data_tai = json.loads(res_tai.text)['list']
        
        # 2. 抓上櫃 (TWO) 前 50 名
        url_two = "https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.rank;exchange=TWO;rankType=volume;limit=50"
        res_two = requests.get(url_two, headers=headers)
        data_two = json.loads(res_two.text)['list']
        
        # 3. 提取代號
        stock_list = []
        for stock in data_tai:
            stock_list.append(stock['symbol'])
        for stock in data_two:
            stock_list.append(stock['symbol'])
            
        return stock_list
    except Exception as e:
        return None

# --- 核心工具：Yahoo Finance 連線 ---
def get_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session

def scan_stock(symbol, session):
    try:
        # 自動處理代號
        target = symbol.strip()
        if ".TW" not in target and ".TWO" not in target:
            # 簡單判斷：如果代號在名單是用抓的，通常 Yahoo API 會給乾淨的數字
            # 我們預設先試 .TW，失敗試 .TWO (或直接由 scan 邏輯處理)
            search_target = target + ".TW"
        else:
            search_target = target
            
        ticker = yf.Ticker(search_target, session=session)
        df = ticker.history(period="6mo", interval="1d")
        
        if df.empty:
            search_target = target + ".TWO"
            ticker = yf.Ticker(search_target, session=session)
            df = ticker.history(period="6mo", interval="1d")

        if df.empty: return None

        # --- V22.0 策略核心 ---
        close = df['Close'].iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        
        # 波動率
        recent_high = df['High'].rolling(10).max()
        recent_low = df['Low'].rolling(10).min()
        volatility = ((recent_high - recent_low) / recent_low).iloc[-1] * 100
        
        # KD
        high_9 = df['High'].rolling(9).max()
        low_9 = df['Low'].rolling(9).min()
        rsv = (df['Close'] - low_9) / (high_9 - low_9) * 100
        rsv = rsv.fillna(50)
        k, d = [50], [50]
        for val in rsv:
            k_val = k[-1]*2/3 + val*1/3
            k.append(k_val)
            d.append(d[-1]*2/3 + k_val*1/3)
        k_now = k[-1]
        d_now = d[-1]
        k_prev = k[-2]
        d_prev = d[-2]
        
        # MACD & OSC
        exp12 = df['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df['Close'].ewm(span=26, adjust=False).mean()
        dif = exp12 - exp26
        macd = dif.ewm(span=9, adjust=False).mean()
        osc = dif - macd
        osc_now = osc.iloc[-1]
        osc_prev = osc.iloc[-2]
        
        # --- 訊號判斷 ---
        signal = None
        score = 0
        reasons = []

        # A. 咕嚕咕嚕 (Bubble)
        if k_now < 30 and volatility < 6:
            signal = "🫧 底部咕嚕咕嚕"
            reasons.append(f"KD低檔({k_now:.1f})")
            reasons.append("波動壓縮")
            score += 80
            
        # B. 高檔強勢整理
        high_k_recent = pd.Series(k).iloc[-30:-5].max()
        if close > ma60 and 30 < k_now < 55 and volatility < 7 and high_k_recent > 70:
            signal = "⚓️ 高檔強勢整理"
            reasons.append("多頭回檔")
            reasons.append("籌碼穩定")
            score += 85

        # C. 完美共振 (KD金叉 + MACD轉強)
        kd_gold = k_prev < d_prev and k_now > d_now
        osc_turn_up = osc_prev < 0 and osc_now > 0
        
        if (osc_now > 0 and kd_gold) or (osc_turn_up and k_now < 50):
            if signal:
                signal += " + 🔥 共振"
                score += 20
            else:
                signal = "🚀 指標轉強"
                score += 70
            reasons.append("MACD/KD轉強")

        if signal:
            return {
                "代號": search_target.replace(".TW", "").replace(".TWO", ""),
                "現價": round(close, 2),
                "AI 訊號": signal,
                "詳細理由": ", ".join(reasons),
                "KD值": round(k_now, 1),
                "分數": score
            }
        else:
            return None

    except:
        return None

# --- UI 介面 ---

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("##### 👇 第一步：取得名單")
    load_hot = st.button("🔄 載入「今日成交量前 100 大」", help="點擊後，AI 會去抓取即時的 Yahoo 股市熱門榜")

if 'stock_list_str' not in st.session_state:
    st.session_state['stock_list_str'] = "2330, 2317, 2603" # 預設值

if load_hot:
    with st.spinner("正在連線 Yahoo 股市後台，抓取最新熱門股..."):
        hot_list = get_top_volume_stocks()
        if hot_list:
            # 取前 100 檔
            final_list = hot_list[:100]
            st.session_state['stock_list_str'] = ", ".join(final_list)
            st.success(f"✅ 成功載入 {len(final_list)} 檔熱門股！(包含上市與上櫃)")
        else:
            st.error("❌ 抓取失敗，請稍後再試。")

user_input = st.text_area("📋 掃描清單 (AI 將掃描以下股票)", value=st.session_state['stock_list_str'], height=150)

st.markdown("##### 👇 第二步：開始掃描")
run_scan = st.button("🚀 啟動 AI 全自動掃描", type="primary")

# --- 主程式執行 ---
if run_scan:
    # 處理清單
    stock_list = [x.strip() for x in user_input.split(',')]
    stock_list = list(set(stock_list)) # 去重
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    session = get_session()
    
    st.markdown("---")
    st.write(f"📊 準備掃描 {len(stock_list)} 檔股票，預計耗時 {len(stock_list)*0.4:.0f} 秒...")

    for i, stock in enumerate(stock_list):
        if not stock: continue
        
        status_text.text(f"📡 ({i+1}/{len(stock_list)}) 正在分析: {stock} ...")
        
        data = scan_stock(stock, session)
        if data:
            results.append(data)
        
        progress_bar.progress((i + 1) / len(stock_list))
        time.sleep(0.3) # 避免封鎖

    status_text.text("✅ 掃描完成！")
    
    if results:
        df_res = pd.DataFrame(results).sort_values("分數", ascending=False)
        
        st.balloons()
        st.subheader(f"🏆 AI 獵殺名單 ({len(results)} 檔)")
        st.info("💡 點擊欄位標題可以排序。紅字代表「指標共振」，藍字代表「咕嚕咕嚕」。")
        
        st.dataframe(
            df_res.style.applymap(lambda x: 'color: red; font-weight: bold' if '共振' in str(x) else 'color: blue' if '咕嚕' in str(x) else '', subset=['AI 訊號']),
            use_container_width=True,
            height=600
        )
    else:
        st.warning("👀 掃描了 100 檔熱門股，但沒有發現符合「強烈訊號」的股票。這可能代表今天盤勢較為膠著。")
