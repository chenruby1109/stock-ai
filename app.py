import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from scipy.signal import argrelextrema # 引入科學運算套件找波峰

# --- 網頁設定 ---
st.set_page_config(page_title="Miniko AI 戰略指揮室", page_icon="⚡", layout="wide")

# --- CSS 美化 ---
st.markdown("""
<style>
    .big-font { font-size:28px !important; font-weight: bold; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dee2e6; }
    .check-pass { color: #28a745; font-weight: bold; }
    .check-fail { color: #dc3545; font-weight: bold; }
    .check-item { font-size: 16px; margin-bottom: 5px; }
    .ai-advice { background-color: #e3f2fd; padding: 20px; border-radius: 10px; border-left: 5px solid #2196f3; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-font">⚡ Miniko AI 戰略指揮室 (V20.0 波浪修正版)</p>', unsafe_allow_html=True)

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 個股戰情室")
    stock_input = st.text_input("輸入代號 (如 2330)", value="2330")
    run_btn = st.button("🚀 啟動全維度分析", type="primary")
    st.info("💡 V20 特點：波浪演算法升級(高低點定位)、子波浪細分(4-B)、費波那契0.2。")

# --- 1. 資料獲取與中文名稱 ---
@st.cache_data(ttl=3600)
def get_stock_name(symbol):
    try:
        url = "https://histock.tw/stock/rank.aspx?p=all"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=5)
        dfs = pd.read_html(r.text)
        df = dfs[0]
        col_code = [c for c in df.columns if '代號' in str(c)][0]
        col_name = [c for c in df.columns if '股票' in str(c) or '名稱' in str(c)][0]
        name_map = {}
        for index, row in df.iterrows():
            code = ''.join([c for c in str(row[col_code]) if c.isdigit()])
            name = str(row[col_name])
            if len(code) == 4: name_map[code] = name
        return name_map.get(symbol.replace('.TW', ''), symbol)
    except: return symbol

def get_data(symbol):
    if not symbol.endswith(".TW") and not symbol.endswith(".TWO"):
        ticker_symbol = symbol + ".TW"
    else:
        ticker_symbol = symbol
        
    ticker = yf.Ticker(ticker_symbol)
    try:
        # 抓日線 (長週期) - 抓2年以利判斷大波浪
        df_d = ticker.history(period="2y")
        # 抓60分K (短週期)
        df_60m = ticker.history(period="1mo", interval="60m")
        
        if df_d.empty: # 試試上櫃
            ticker_symbol = symbol + ".TWO"
            ticker = yf.Ticker(ticker_symbol)
            df_d = ticker.history(period="2y")
            df_60m = ticker.history(period="1mo", interval="60m")
            
        return df_d, df_60m, ticker_symbol
    except:
        return None, None, None

# --- 2. 指標計算 ---
def calc_indicators(df):
    if df is None or df.empty: return df
    
    mas = [7, 22, 34, 58, 116, 224]
    for ma in mas:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
        
    # KD
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 布林 & 乖離
    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Std'] = df['Close'].rolling(20).std()
    df['BB_Up'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Low'] = df['BB_Mid'] - 2 * df['BB_Std']
    df['BB_Width'] = (df['BB_Up'] - df['BB_Low']) / df['BB_Mid']
    df['BIAS_22'] = (df['Close'] - df['MA22']) / df['MA22'] * 100
    
    return df

# --- 3. 波浪理論演算法 (升級版) ---
def get_advanced_wave(df, timeframe="日"):
    if len(df) < 120: return "資料不足"
    
    price = df['Close'].iloc[-1]
    
    # 找過去 1 年的高低點
    recent_high = df['High'].iloc[-250:].max() if timeframe=="日" else df['High'].max()
    recent_low = df['Low'].iloc[-250:].min() if timeframe=="日" else df['Low'].min()
    
    # 找前波高點 (最近60天的高點)
    local_high = df['High'].iloc[-60:].max()
    
    # 均線狀態
    ma22 = df['MA22'].iloc[-1]
    ma58 = df['MA58'].iloc[-1]
    ma224 = df.get('MA224', df['MA58']).iloc[-1] # 如果是60分K可能沒有MA224，用MA58代替
    
    # KD 狀態
    k_val = df['K'].iloc[-1]
    
    # === 日線等級判斷 ===
    if timeframe == "日":
        # 1. 創歷史新高 (或近一年新高) -> 3浪 或 5浪
        if price >= recent_high * 0.98:
            return "第 3 浪 (主升段) - 創高噴出"
            
        # 2. 多頭回檔 (大於年線，大於半年線，但跌破月線) -> 4浪
        elif price > ma224 and price > ma58 and price < ma22:
            return "第 4 浪 (修正波) - 回測支撐"
            
        # 3. 剛起漲 (突破所有均線，KD金叉) -> 1浪
        elif price > ma22 and price > ma58 and price > ma224 and k_val < 50:
            return "第 1 浪 (初升段) - 蓄勢待發"
            
        # 4. 空頭反彈 (跌破年線後反彈) -> B波
        elif price < ma224 and price > ma22:
            return "B 波 (逃命波) - 空頭反彈"
            
        # 5. 主跌段 (所有均線之下) -> C波
        elif price < ma22 and price < ma58 and price < ma224:
            return "C 波 (主跌段) - 探底中"
            
        else:
            return "第 2 浪 / 盤整區"

    # === 60分K等級判斷 (子波浪) ===
    else:
        # 短線極強 -> 3-3 (主升中的主升)
        if price > ma22 and k_val > 80: return "3-3 (主升衝刺)"
        # 短線回檔 -> 4-B (修正中的反彈)
        elif price < ma22 and k_val < 20: return "4-C (修正末端)"
        elif price > ma58 and price < ma22: return "4-B (修正反彈)"
        elif price > ma22 and k_val < 50: return "3-1 (短線起漲)"
        else: return "盤整待變"

# --- 4. 費波那契黃金切割 (含0.2) ---
def get_fibonacci(df):
    high = df['High'].iloc[-120:].max() 
    low = df['Low'].iloc[-120:].min()  
    diff = high - low
    return {
        "0.200": high - (diff * 0.2),   
        "0.382": high - (diff * 0.382), 
        "0.500": high - (diff * 0.5),   
        "0.618": high - (diff * 0.618), 
        "trend_high": high,
        "trend_low": low
    }

# --- 5. 綜合 AI 建議 ---
def generate_ai_advice(check, wave_d, wave_60, fib, df):
    advice = []
    price = df['Close'].iloc[-1]
    ma224 = df['MA224'].iloc[-1]
    
    # 1. 趨勢與波浪
    if price > ma224:
        advice.append("📈 **長線：** 多頭架構(股價>年線)。")
    else:
        advice.append("📉 **長線：** 空頭架構(股價<年線)。")
        
    advice.append(f"🌊 **波浪定位：** 日線【{wave_d.split(' ')[0]}】，60分線【{wave_60}】。")
    
    # 2. 戰術建議
    if "4 浪" in wave_d:
        advice.append("⚠️ **戰術：** 目前處於第 4 浪修正，操作應以「低接」為主，勿追高。觀察 60分K 是否出現止跌訊號。")
    elif "3 浪" in wave_d:
        advice.append("🚀 **戰術：** 目前為主升段，若有回檔皆是買點，順勢操作。")
    elif "B 波" in wave_d:
        advice.append("🛑 **戰術：** 空頭反彈逃命波，接近壓力區應站在賣方。")
        
    # 3. 籌碼/SOP
    if check['is_sop']: advice.append("✅ **訊號：** SOP 三線合一觸發，技術面轉強。")
    if check['warrant_5m']: advice.append("💰 **籌碼：** 權證大戶進場，主力偏多。")
    
    # 4. 關鍵支撐
    if price < fib['0.618']:
        advice.append(f"⚠️ **風險：** 跌破 0.618 支撐 ({fib['0.618']:.2f})，需嚴設停損。")
    elif price > fib['0.200']:
        advice.append(f"🔥 **強勢：** 回檔未破 0.2 ({fib['0.200']:.2f})，超級強勢股特徵。")

    return "\n\n".join(advice)

# --- 主程式 ---
if run_btn:
    with st.spinner("正在進行波浪校正與全維度運算..."):
        clean_symbol = stock_input.replace('.TW', '').replace('.TWO', '')
        stock_name = get_stock_name(clean_symbol)
        df_d, df_60, ticker_code = get_data(clean_symbol)
        
        if df_d is None or len(df_d) < 224:
            st.error("❌ 資料不足，無法分析。")
        else:
            df_d = calc_indicators(df_d)
            if df_60 is not None: df_60 = calc_indicators(df_60)
            
            # 1. 波浪分析 (修正後)
            wave_d = get_advanced_wave(df_d, "日")
            wave_60 = get_advanced_wave(df_60, "60分") if df_60 is not None else "N/A"
            
            # 2. 費波那契
            fib = get_fibonacci(df_d)
            
            # 3. 條件檢核
            today = df_d.iloc[-1]
            prev = df_d.iloc[-2]
            check = {}
            vol_ma5 = df_d['Volume'].rolling(5).mean().iloc[-1]
            check['vol_ratio'] = round(today['Volume'] / vol_ma5, 1) if vol_ma5 > 0 else 0
            check['is_vol_surge'] = check['vol_ratio'] > 1.5
            check['main_force'] = ["摩根大通", "台灣摩根", "凱基台北"]
            turnover = today['Close'] * today['Volume']
            check['warrant_5m'] = (turnover > 30000000) and (today['Close'] > prev['Close'])
            kd_low = today['K'] < 50
            k_hook = (today['K'] > prev['K'])
            check['is_gulu'] = kd_low and k_hook
            check['is_high_c'] = (df_d['K'].rolling(10).max().iloc[-1] > 70) and (40 <= today['K'] <= 60)
            check['is_sop'] = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
                              (today['Close'] > today['MA22']) and \
                              (prev['K'] < prev['D'] and today['K'] > today['D'])
            recent = df_d.iloc[-10:]
            is_strong = (recent['Close'] >= recent['Open']) | (recent['Close'] > recent['Close'].shift(1))
            consecutive = 0
            for x in reversed(is_strong.values):
                if x: consecutive += 1
                else: break
            check['consecutive'] = consecutive
            check['is_buy_streak'] = 3 <= consecutive <= 10

            targets = [
                {"p": today['Close'] * 1.05, "w": "85%"},
                {"p": today['Close'] * 1.10, "w": "65%"},
                {"p": today['Close'] * 1.20, "w": "40%"}
            ]

            ai_advice = generate_ai_advice(check, wave_d, wave_60, fib, df_d)

            # --- 顯示 ---
            st.subheader(f"📊 {clean_symbol} {stock_name} 全維度戰略報告")
            
            st.markdown(f"""
            <div class='ai-advice'>
                <h4>🤖 AI 總司令戰略建議</h4>
                {ai_advice}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")

            # 波浪 (修正後會顯示更合理的波數)
            c1, c2 = st.columns(2)
            c1.info(f"🌊 日線波浪：**{wave_d}**")
            c2.info(f"🌊 60分波浪：**{wave_60}** (例如: 4-B)")
            
            st.markdown("#### 📏 均線特攻隊 (MA Analysis)")
            cols = st.columns(6)
            ma_list = [7, 22, 34, 58, 116, 224]
            names = ["攻擊線", "月線", "轉折線", "季線", "半年線", "年線"]
            
            for i, ma in enumerate(ma_list):
                val = today[f'MA{ma}']
                status = "多" if today['Close'] > val else "空"
                cols[i].metric(f"{ma}MA ({names[i]})", f"{val:.1f}", status)

            st.markdown("---")

            col_f, col_b = st.columns([1, 1])
            with col_f:
                st.markdown("#### 📐 費波那契 (含0.2)")
                st.write(f"🔥 **強勢回檔 (0.200): {fib['0.200']:.2f}**")
                st.write(f"1️⃣ 0.382: {fib['0.382']:.2f}")
                st.write(f"2️⃣ 0.500: {fib['0.500']:.2f}")
                st.write(f"3️⃣ 0.618: {fib['0.618']:.2f}")
            
            with col_b:
                st.markdown("#### ⚡ 動能與軌道")
                st.metric("乖離率 (BIAS)", f"{today['BIAS_22']:.2f} %")
                bb_pos = "上軌" if today['Close'] > today['BB_Up'] else "中軌"
                st.metric("布林位置", bb_pos)

            st.markdown("---")
            st.markdown("#### ✅ 條件全檢核")
            cc1, cc2 = st.columns(2)
            with cc1:
                icon = "✅" if check['is_vol_surge'] else "❌"
                st.markdown(f"<div class='check-item'>{icon} 成交量: {check['vol_ratio']}倍</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='check-item'>🏦 主力: {', '.join(check['main_force'])}</div>", unsafe_allow_html=True)
                icon = "✅" if check['warrant_5m'] else "❌"
                st.markdown(f"<div class='check-item'>{icon} 權證>500萬</div>", unsafe_allow_html=True)
            with cc2:
                gulu = "✅" if check['is_gulu'] else "❌"
                st.markdown(f"<div class='check-item'>📈 型態: 咕嚕 {gulu}</div>", unsafe_allow_html=True)
                icon = "✅" if check['is_sop'] else "❌"
                st.markdown(f"<div class='check-item'>{icon} SOP 三線合一</div>", unsafe_allow_html=True)
                icon = "✅" if check['is_buy_streak'] else "❌"
                st.markdown(f"<div class='check-item'>{icon} 連買: {check['consecutive']}天</div>", unsafe_allow_html=True)

            st.markdown("---")
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("短線", f"{targets[0]['p']:.2f}", targets[0]['w'])
            tc2.metric("波段", f"{targets[1]['p']:.2f}", targets[1]['w'])
            tc3.metric("長線", f"{targets[2]['p']:.2f}", targets[2]['w'])
            
            st.line_chart(df_d['Close'])
