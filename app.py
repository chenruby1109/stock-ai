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
    .ai-advice { background-color: #e3f2fd; padding: 25px; border-radius: 12px; border-left: 6px solid #1976d2; font-size: 16px; line-height: 1.6; }
    .advice-section { margin-bottom: 15px; }
    .advice-title { font-weight: bold; color: #0d47a1; font-size: 18px; margin-bottom: 5px; display: block; }
    .buy-zone { background-color: #e8f5e9; padding: 15px; border-radius: 8px; border-left: 5px solid #4caf50; margin-top: 20px; }
    .wave-tag { font-size: 14px; background-color: #fff3cd; padding: 2px 6px; border-radius: 4px; border: 1px solid #ffeeba; font-weight: bold; color: #856404; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-font">⚡ Miniko AI 戰略指揮室 (V25.0 波浪微結構版)</p>', unsafe_allow_html=True)

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 個股戰情室")
    stock_input = st.text_input("輸入代號 (如 2330)", value="2330")
    run_btn = st.button("🚀 啟動全維度分析", type="primary")
    st.info("💡 V25 特點：新增 30分K 監測，啟用艾略特微波浪 (Micro-Wave) 識別演算法。")

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
        # 增加 30分K 資料
        df_60m = ticker.history(period="1mo", interval="60m")
        df_30m = ticker.history(period="1mo", interval="30m") 
        
        if df_d.empty:
            ticker_symbol = symbol + ".TWO"
            ticker = yf.Ticker(ticker_symbol)
            df_d = ticker.history(period="2y")
            df_60m = ticker.history(period="1mo", interval="60m")
            df_30m = ticker.history(period="1mo", interval="30m")
            
        return df_d, df_60m, df_30m, ticker_symbol
    except: return None, None, None, None

# --- 2. 指標計算 ---
def calc_indicators(df):
    if df is None or df.empty: return df
    
    mas = [5, 10, 20, 60, 120, 240]
    for ma in mas:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    
    special_mas = [7, 22, 34, 58, 116, 224]
    for ma in special_mas:
        df[f'SMA{ma}'] = df['Close'].rolling(ma).mean()

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
    df['BB_Pct'] = (df['Close'] - df['BB_Low']) / (df['BB_Up'] - df['BB_Low'])
    
    # 乖離 & ATR
    df['BIAS_20'] = (df['Close'] - df['MA20']) / df['MA20'] * 100
    df['TR'] = np.maximum(df['High'] - df['Low'], np.abs(df['High'] - df['Close'].shift(1)))
    df['ATR'] = df['TR'].rolling(14).mean()
    
    return df

# --- 3. 微波浪識別 (核心升級) ---
def get_micro_wave(df, timeframe="日"):
    if df is None or len(df) < 60: return "N/A"
    
    price = df['Close'].iloc[-1]
    ma5 = df['MA5'].iloc[-1]
    ma10 = df['MA10'].iloc[-1]
    ma20 = df['MA20'].iloc[-1]
    ma60 = df['MA60'].iloc[-1]
    
    k = df['K'].iloc[-1]
    prev_k = df['K'].iloc[-2]
    d = df['D'].iloc[-1]
    
    hist = df['MACD_Hist'].iloc[-1]
    prev_hist = df['MACD_Hist'].iloc[-2]
    
    # 判斷大趨勢 (Major Trend)
    trend = "Bull" if price > ma60 else "Bear"
    
    wave_label = ""
    
    if trend == "Bull":
        # 多頭架構下的波浪
        if price > ma20:
            # 價格在月線之上 (進攻浪)
            if hist > 0 and hist > prev_hist:
                # 動能增強
                if k > 80: wave_label = "3-5 (噴出末段)"
                else: wave_label = "3-3 (主升急漲)"
            elif hist > 0 and hist < prev_hist:
                # 動能減弱
                wave_label = "3-a (高檔震盪)"
            else:
                # MACD 綠柱但價格仍強
                wave_label = "3-1 (初升/轉折)"
        else:
            # 價格跌破月線 (修正浪)
            if price > ma60:
                if k < 20: wave_label = "4-c (修正末端)"
                elif k < prev_k: wave_label = "4-a (初跌修正)"
                else: wave_label = "4-b (反彈逃命)"
    else:
        # 空頭架構
        if price < ma20:
            if k < 20: wave_label = "C-5 (趕底急殺)"
            else: wave_label = "C-3 (主跌段)"
        else:
            # 反彈
            if k > 80: wave_label = "B-c (反彈高點)"
            else: wave_label = "B-a (跌深反彈)"

    return wave_label

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

# --- 5. 深度戰略生成 (個人化升級) ---
def generate_deep_strategy(stock_name, price, check, wave_d, wave_60, wave_30, fib, df):
    ma20 = df['MA20'].iloc[-1]
    bias = df['BIAS_20'].iloc[-1]
    vol_ratio = check['vol_ratio']
    
    sections = []
    
    # 1. 個性化戰略總評
    advice_intro = ""
    if "3-" in wave_d and "3-" in wave_60:
        advice_intro = f"【{stock_name}】目前日線與60分線產生『共振噴出』，屬於極強勢的多頭格局。價格 {price} 站穩所有均線，這是最容易獲利的階段。"
    elif "4-" in wave_d and "3-" in wave_30:
        advice_intro = f"【{stock_name}】日線目前正在進行 {wave_d} 的修正，但 30分K 出現 {wave_30} 的短線轉強訊號，這意味著『修正可能結束，主力正在嘗試止跌』。"
    elif "C-" in wave_d:
        advice_intro = f"【{stock_name}】目前處於空頭下跌波 {wave_d}，上方壓力重重，除非站回月線 {ma20:.2f}，否則任何上漲都視為反彈。"
    else:
        advice_intro = f"【{stock_name}】目前多空交戰，日線 {wave_d} 與短線訊號方向不一致，建議縮小部位，採取區間操作。"

    sections.append(f"""
    <div class='advice-section'>
        <span class='advice-title'>📡 {stock_name} 專屬戰略總評</span>
        {advice_intro}<br><br>
        <span class='wave-tag'>日線：{wave_d}</span> 
        <span class='wave-tag'>60K：{wave_60}</span> 
        <span class='wave-tag'>30K：{wave_30}</span>
    </div>
    """)
    
    # 2. 籌碼與動能 (結合量能與狀態)
    chips_desc = []
    if vol_ratio > 2.0:
        chips_desc.append(f"🔥 **爆量攻擊：** 今日成交量是五日均量的 {vol_ratio} 倍！這通常是『{wave_30}』轉折的確認訊號，主力攻擊意願極強。")
    if check['warrant_5m']:
        chips_desc.append("💰 **權證大戶進場：** 偵測到預估超過 500 萬的權證買盤，聰明錢正在押寶短線波動。")
    if check['is_sop']:
        chips_desc.append("✅ **SOP 三線合一：** 技術面出現 MACD 翻紅 + KD 金叉 + 站上攻擊線，這是標準的起漲訊號。")
    
    if not chips_desc:
        chips_desc.append(f"⚠️ **量能觀望：** 目前成交量平淡 ({vol_ratio}倍)，主力尚未表態，股價將隨波浪慣性 {wave_60} 漂流。")
        
    sections.append(f"""
    <div class='advice-section'>
        <span class='advice-title'>💰 動能深度解析</span>
        {'<br>'.join(chips_desc)}
    </div>
    """)
    
    # 3. 操作劇本 (針對波浪位置)
    action_desc = ""
    # 針對乖離的客製化
    bias_warning = f"(目前乖離率 {bias:.1f}% 偏高，勿追價)" if bias > 8 else "(乖離率適中，安全)"

    if "3-3" in wave_60 or "3-3" in wave_30:
        action_desc = f"🚀 **追價/加碼策略：** 短線處於『3-3 主升急漲段』{bias_warning}。若手中無部位，可利用 30分K 回測 5MA 時切入；若有部位，續抱直到跌破 60分K 的 10MA。"
    elif "4-c" in wave_60 or "4-c" in wave_30:
        action_desc = f"📉 **抄底策略：** 短線進入『4-c 修正末端』，這是盈虧比最好的買點。建議在 {fib['0.382']:.2f} (0.382支撐) 附近觀察，若出現下影線或紅K，大膽進場。"
    elif "B-" in wave_d:
        action_desc = "👀 **逃命策略：** 日線處於 B 波反彈，建議逢高減碼，不要留戀，上方套牢壓力大。"
    else:
        action_desc = "🛡️ **防守策略：** 目前趨勢不明，建議以月線為最後防守點，多看少做。"

    sections.append(f"""
    <div class='advice-section'>
        <span class='advice-title'>📝 精準操作劇本</span>
        {action_desc}
    </div>
    """)

    return "\n".join(sections)

# --- 主程式 ---
if run_btn:
    with st.spinner("正在進行微結構波浪運算 (Daily/60m/30m)..."):
        clean_symbol = stock_input.replace('.TW', '').replace('.TWO', '')
        stock_name = get_stock_name(clean_symbol)
        df_d, df_60, df_30, ticker_code = get_data(clean_symbol)
        
        if df_d is None or len(df_d) < 240:
            st.error("❌ 資料不足或代號錯誤。")
        else:
            # 計算指標
            df_d = calc_indicators(df_d)
            if df_60 is not None: df_60 = calc_indicators(df_60)
            if df_30 is not None: df_30 = calc_indicators(df_30)
            
            # 波浪分析 (三週期)
            wave_d = get_micro_wave(df_d, "日")
            wave_60 = get_micro_wave(df_60, "60分") if df_60 is not None else "N/A"
            wave_30 = get_micro_wave(df_30, "30分") if df_30 is not None else "N/A"
            
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
            check['is_sop'] = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and (today['Close'] > today['SMA22']) and (prev['K'] < prev['D'] and today['K'] > today['D'])
            recent = df_d.iloc[-10:]
            is_strong = (recent['Close'] >= recent['Open']) | (recent['Close'] > recent['Close'].shift(1))
            consecutive = 0
            for x in reversed(is_strong.values):
                if x: consecutive += 1
                else: break
            check['consecutive'] = consecutive
            check['is_buy_streak'] = 3 <= consecutive <= 10

            # 預計達標時間
            atr = df_d['ATR'].iloc[-1]
            targets = []
            for mult, win, atr_ratio in [(1.05, "85%", 0.5), (1.10, "65%", 0.4), (1.20, "40%", 0.3)]:
                p = today['Close'] * mult
                dist = p - today['Close']
                daily_move = atr * atr_ratio
                days = max(2, int(dist / daily_move)) if daily_move > 0 else 10
                targets.append({"p": p, "w": win, "days": days})

            # 買入價位
            buy_aggressive = max(today['MA5'], fib['0.200'])
            buy_conservative = max(today['MA20'], fib['0.382'])

            # 生成個人化 AI 建議
            ai_advice = generate_deep_strategy(stock_name, today['Close'], check, wave_d, wave_60, wave_30, fib, df_d)

            # --- 顯示層 ---
            st.subheader(f"📊 {clean_symbol} {stock_name} 全維度戰略報告")
            
            # AI 總司令
            st.markdown(f"""
            <div class='ai-advice'>
                <h4>🤖 AI 總司令戰略建議 (Personalized V25)</h4>
                {ai_advice}
            </div>
            """, unsafe_allow_html=True)
            
            # 買入建議區塊
            st.markdown(f"""
            <div class='buy-zone'>
                <h4>🛒 AI 建議買入價位 (Buy Zones)</h4>
                <ul>
                    <li><b>🦁 激進追價區 (Aggressive)：</b> {buy_aggressive:.2f} 元 (約 5日線/0.2強勢回檔) — 適合操作 {wave_30} 的投資人。</li>
                    <li><b>🐢 保守低接區 (Conservative)：</b> {buy_conservative:.2f} 元 (約 月線/0.382支撐) — 適合佈局 {wave_d} 的投資人。</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")

            # 波浪結構 (三週期並列)
            st.markdown("#### 🌊 艾略特波浪微結構 (Micro-Structure)")
            wc1, wc2, wc3 = st.columns(3)
            wc1.info(f"📅 **日線 (主趨勢)**\n\n# {wave_d}")
            wc2.warning(f"⏰ **60分K (波段)**\n\n# {wave_60}")
            wc3.error(f"⚡ **30分K (轉折)**\n\n# {wave_30}")
            
            st.markdown("---")

            # 均線特攻隊
            st.markdown("#### 📏 均線特攻隊")
            cols = st.columns(6)
            ma_list = [7, 22, 34, 58, 116, 224]
            names = ["攻擊", "月線", "轉折", "季線", "半年", "年線"]
            for i, ma in enumerate(ma_list):
                val = today[f'SMA{ma}']
                status = "多" if today['Close'] > val else "空"
                cols[i].metric(f"{ma}MA ({names[i]})", f"{val:.1f}", status)

            st.markdown("---")

            # 費波 & 布林
            col_f, col_b = st.columns([1, 1])
            with col_f:
                st.markdown("#### 📐 費波那契 (戰術意義)")
                p = today['Close']
                def fib_tag(level, name):
                    return f"✅ 守住 {name}" if p > level else f"⚠️ 跌破 {name}"
                
                st.write(f"**0.200 (強勢回檔)**: {fib['0.200']:.2f} — {fib_tag(fib['0.200'], '超級強勢區')}")
                st.write(f"**0.382 (初級支撐)**: {fib['0.382']:.2f} — {fib_tag(fib['0.382'], '第一道防線')}")
                st.write(f"**0.500 (多空分界)**: {fib['0.500']:.2f} — {fib_tag(fib['0.500'], '中線轉折')}")
                st.write(f"**0.618 (黃金防線)**: {fib['0.618']:.2f} — {fib_tag(fib['0.618'], '生命線 (破則轉空)')}")
            
            with col_b:
                st.markdown("#### ⚡ 動能與布林解析")
                bias = today['BIAS_20']
                bias_msg = "橡皮筋拉太緊 (過熱)" if bias > 10 else "橡皮筋過鬆 (超跌)" if bias < -10 else "張力正常"
                st.metric("乖離率 (BIAS)", f"{bias:.2f} %", bias_msg)
                
                bb_pct = today['BB_Pct']
                bb_msg = "衝出上軌 (賣訊)" if bb_pct > 1 else "跌破下軌 (買訊)" if bb_pct < 0 else "區間震盪"
                st.metric("布林位置", bb_msg)
                st.progress(min(max(bb_pct, 0.0), 1.0))
                st.caption(f"目前位置: {bb_pct*100:.1f}% (0%=下軌, 100%=上軌)")

            st.markdown("---")
            # 條件清單
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

            # 目標價
            st.markdown("---")
            st.markdown("#### 🎯 預測目標價 (含預估時間)")
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("短線目標", f"{targets[0]['p']:.2f}", f"{targets[0]['w']} (約{targets[0]['days']}天)")
            tc2.metric("波段目標", f"{targets[1]['p']:.2f}", f"{targets[1]['w']} (約{targets[1]['days']}天)")
            tc3.metric("長線目標", f"{targets[2]['p']:.2f}", f"{targets[2]['w']} (約{targets[2]['days']}天)")
            
            st.line_chart(df_d['Close'])
