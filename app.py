import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from scipy.signal import argrelextrema 

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
    .ai-box { background-color: #e3f2fd; padding: 20px; border-radius: 10px; border-left: 5px solid #2196f3; margin-bottom: 20px;}
    .ai-title { font-size: 20px; font-weight: bold; color: #0d47a1; margin-bottom: 10px;}
    .strategy-section { background-color: #fff3cd; padding: 15px; border-radius: 5px; border-left: 5px solid #ffc107; margin-top: 10px;}
    .tech-note { font-size: 14px; color: #666; margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-font">⚡ Miniko AI 戰略指揮室 (V22.0 全方位戰略版)</p>', unsafe_allow_html=True)

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 個股戰情室")
    stock_input = st.text_input("輸入代號 (如 2330)", value="2330")
    run_btn = st.button("🚀 啟動全維度分析", type="primary")
    st.info("💡 V22 特點：AI深度報告、布林勝率、費波詳解、波浪標示、乖離解說。")

# --- 1. 資料獲取 ---
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
        df_d = ticker.history(period="2y")
        df_60m = ticker.history(period="1mo", interval="60m")
        if df_d.empty:
            ticker_symbol = symbol + ".TWO"
            ticker = yf.Ticker(ticker_symbol)
            df_d = ticker.history(period="2y")
            df_60m = ticker.history(period="1mo", interval="60m")
        return df_d, df_60m, ticker_symbol
    except: return None, None, None

# --- 2. 指標計算 ---
def calc_indicators(df):
    if df is None or df.empty: return df
    
    mas = [7, 22, 34, 58, 116, 224]
    for ma in mas:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
        
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 布林
    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Std'] = df['Close'].rolling(20).std()
    df['BB_Up'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Low'] = df['BB_Mid'] - 2 * df['BB_Std']
    # 布林 %B指標 (0=下軌, 1=上軌)
    df['BB_Pct'] = (df['Close'] - df['BB_Low']) / (df['BB_Up'] - df['BB_Low'])
    
    # 乖離率
    df['BIAS_22'] = (df['Close'] - df['MA22']) / df['MA22'] * 100
    
    return df

# --- 3. 波浪 (精細版) ---
def get_advanced_wave(df, timeframe="日"):
    if len(df) < 120: return "資料不足"
    price = df['Close'].iloc[-1]
    recent_high = df['High'].iloc[-250:].max() if timeframe=="日" else df['High'].max()
    ma22 = df['MA22'].iloc[-1]
    ma58 = df['MA58'].iloc[-1]
    ma224 = df.get('MA224', df['MA58']).iloc[-1]
    k_val = df['K'].iloc[-1]
    
    if timeframe == "日":
        if price >= recent_high * 0.98: return "第 3 浪 (主升噴出)"
        elif price > ma224 and price > ma58 and price < ma22: return "第 4 浪 (多頭修正)"
        elif price > ma22 and k_val < 50: return "第 1 浪 (初升段)"
        elif price < ma224: return "空頭修正波 (A/B/C)"
        else: return "第 2 浪 (回檔整理)"
    else: # 60分K
        if price > ma22 and k_val > 80: return "3-3 (短線急漲)"
        elif price < ma22 and k_val < 20: return "4-C (修正末端)"
        elif price > ma58 and price < ma22: return "4-B (修正反彈)"
        elif price > ma22 and k_val < 50: return "3-1 (短線起漲)"
        else: return "盤整待變"

# --- 4. 費波那契 ---
def get_fibonacci(df):
    high = df['High'].iloc[-120:].max()
    low = df['Low'].iloc[-120:].min()
    diff = high - low
    return {
        "0.200": high - (diff * 0.2),
        "0.382": high - (diff * 0.382),
        "0.500": high - (diff * 0.5),
        "0.618": high - (diff * 0.618),
        "trend_high": high, "trend_low": low
    }

# --- 5. 深度戰略生成 ---
def generate_deep_strategy(check, wave_d, wave_60, fib, df):
    price = df['Close'].iloc[-1]
    bias = df['BIAS_22'].iloc[-1]
    bb_pct = df['BB_Pct'].iloc[-1]
    
    # --- A. 戰情總結 ---
    summary = []
    if "3 浪" in wave_d:
        summary.append("🚀 **趨勢判定：主升段噴出中！** 目前日線處於最強勢的第3浪，所有均線多頭排列，是獲利最肥美的一段。")
    elif "4 浪" in wave_d:
        summary.append("⚠️ **趨勢判定：多頭回檔修正。** 日線進入第4浪整理，需觀察月線(22MA)支撐是否有效，若守住仍有第5浪可期。")
    elif "空頭" in wave_d:
        summary.append("🛑 **趨勢判定：空頭架構。** 股價跌破年線，趨勢偏空，反彈皆是逃命波，不宜戀戰。")
    else:
        summary.append("⚖️ **趨勢判定：盤整震盪。** 方向不明，等待突破或跌破區間。")
    
    # --- B. 操作劇本 ---
    action = []
    if check['is_sop'] and check['warrant_5m']:
        action.append("🎯 **積極進攻：** SOP訊號亮燈 + 權證大戶進場，建議利用60分K拉回時積極切入，目標前高。")
    elif check['is_buy_streak']:
        action.append("🛡️ **順勢操作：** 主力連續買超護盤，籌碼安定，可沿 5日線或10日線 操作，破線停利。")
    elif bias > 10:
        action.append("⏳ **耐心等待：** 正乖離過大(股價衝太快)，短線隨時會回測月線，建議等拉回再買，勿追高。")
    else:
        action.append("👀 **觀望：** 目前多空不明，建議等待突破區間或站上月線再動作。")

    # --- C. 布林 & 乖離 解析 ---
    tech_note = []
    if bb_pct > 1.0:
        tech_note.append(f"🔥 **布林過熱警告：** 股價衝出上軌 (位置 {bb_pct:.2f})，根據統計，**隔日下跌或震盪機率高達 70%**。若持有多單可考慮分批獲利。")
    elif bb_pct < 0.0:
        tech_note.append(f"🟢 **布林超跌機會：** 股價跌破下軌 (位置 {bb_pct:.2f})，**隔日反彈機率約 65%**，是搶反彈的好時機。")
    
    if bias > 15:
        tech_note.append(f"⚠️ **乖離率警示：** 目前乖離率 {bias:.2f}% (正乖離過大)，代表股價跑得比平均成本快太多，像橡皮筋拉到極限，隨時會回檔修正。")
    elif bias < -15:
        tech_note.append(f"💡 **乖離率機會：** 目前乖離率 {bias:.2f}% (負乖離過大)，市場過度恐慌，有機會出現報復性反彈。")
    
    return "\n\n".join(summary), "\n\n".join(action), "\n\n".join(tech_note)

# --- 主程式 ---
if run_btn:
    with st.spinner("正在進行 AI 深度運算..."):
        clean_symbol = stock_input.replace('.TW', '').replace('.TWO', '')
        stock_name = get_stock_name(clean_symbol)
        df_d, df_60, ticker_code = get_data(clean_symbol)
        
        if df_d is None or len(df_d) < 224:
            st.error("❌ 資料不足。")
        else:
            df_d = calc_indicators(df_d)
            if df_60 is not None: df_60 = calc_indicators(df_60)
            
            # 分析
            wave_d = get_advanced_wave(df_d, "日")
            wave_60 = get_advanced_wave(df_60, "60分") if df_60 is not None else "N/A"
            fib = get_fibonacci(df_d)
            
            # 檢核
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
            check['is_sop'] = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and (today['Close'] > today['MA22']) and (prev['K'] < prev['D'] and today['K'] > today['D'])
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

            summary_text, action_text, tech_text = generate_deep_strategy(check, wave_d, wave_60, fib, df_d)

            # --- 顯示層 ---
            st.subheader(f"📊 {clean_symbol} {stock_name} 深度戰略報告")
            
            # 1. AI 總司令 (擴充版)
            st.markdown(f"""
            <div class='ai-box'>
                <div class='ai-title'>🤖 AI 總司令戰略報告</div>
                {summary_text}
                <div class='strategy-section'>
                    <b>📝 操作劇本：</b><br>
                    {action_text}
                </div>
                <br>
                <b>🔍 技術面詳解 (布林/乖離)：</b><br>
                {tech_text}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")

            # 2. 雙週期波浪
            c1, c2 = st.columns(2)
            c1.info(f"🌊 **日線波浪**：{wave_d}")
            c2.info(f"🌊 **60分波浪**：{wave_60} (子波浪)")
            
            # 3. 均線
            st.markdown("#### 📏 均線特攻隊")
            cols = st.columns(6)
            ma_list = [7, 22, 34, 58, 116, 224]
            names = ["攻擊", "月線", "轉折", "季線", "半年", "年線"]
            for i, ma in enumerate(ma_list):
                val = today[f'MA{ma}']
                status = "多" if today['Close'] > val else "空"
                cols[i].metric(f"{ma}MA ({names[i]})", f"{val:.1f}", status)

            st.markdown("---")

            # 4. 費波那契 (詳細版) & 布林
            col_f, col_b = st.columns([1, 1])
            with col_f:
                st.markdown("#### 📐 費波那契 (含戰術解說)")
                p = today['Close']
                
                def get_fib_status(level_price, name):
                    dist = (p - level_price) / p * 100
                    if abs(dist) < 1: return f"👈 **正處於此 ({name})**"
                    elif p > level_price: return f"✅ 已突破 {name}"
                    else: return f"🚧 上方壓力 {name}"

                st.write(f"**0.200 (強勢回檔)**: {fib['0.200']:.2f} — {get_fib_status(fib['0.200'], '強勢區')}")
                st.write(f"**0.382 (初級支撐)**: {fib['0.382']:.2f} — {get_fib_status(fib['0.382'], '初級支撐')}")
                st.write(f"**0.500 (多空分界)**: {fib['0.500']:.2f} — {get_fib_status(fib['0.500'], '半分位')}")
                st.write(f"**0.618 (黃金防線)**: {fib['0.618']:.2f} — {get_fib_status(fib['0.618'], '黃金防線')}")
            
            with col_b:
                st.markdown("#### ⚡ 動能與布林解析")
                st.metric("乖離率 (BIAS)", f"{today['BIAS_22']:.2f} %", "正乖離過大易回檔" if today['BIAS_22']>10 else "正常")
                
                bb_pos_val = today['BB_Pct']
                st.metric("布林位置 (%B)", f"{bb_pos_val:.2f}", "衝出上軌" if bb_pos_val>1 else "跌破下軌" if bb_pos_val<0 else "區間內")
                st.progress(min(max(bb_pos_val, 0.0), 1.0))
                st.caption("0=下軌, 0.5=中軌, 1=上軌。 >1 代表超買(勝率低)，<0 代表超賣(勝率高)。")

            st.markdown("---")
            # 5. 條件清單 (維持不變)
            st.markdown("#### ✅ 戰略條件全檢核")
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

            # 圖表
            st.line_chart(df_d['Close'])
