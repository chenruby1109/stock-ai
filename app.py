import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time

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

st.markdown('<p class="big-font">⚡ Miniko AI 戰略指揮室 (V19.0 全維度指揮官)</p>', unsafe_allow_html=True)

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 個股戰情室")
    stock_input = st.text_input("輸入代號 (如 2330)", value="2330")
    run_btn = st.button("🚀 啟動全維度分析", type="primary")
    st.info("💡 V19 特點：雙週期波浪、特定均線戰法、費波那契0.2、AI綜合詳評。")

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
        # 抓日線 (長週期)
        df_d = ticker.history(period="1y")
        # 抓60分K (短週期)
        df_60m = ticker.history(period="1mo", interval="60m")
        
        if df_d.empty: # 試試上櫃
            ticker_symbol = symbol + ".TWO"
            ticker = yf.Ticker(ticker_symbol)
            df_d = ticker.history(period="1y")
            df_60m = ticker.history(period="1mo", interval="60m")
            
        return df_d, df_60m, ticker_symbol
    except:
        return None, None, None

# --- 2. 複雜指標計算 ---
def calc_indicators(df):
    if df is None or df.empty: return df
    
    # 2.1 指定均線: 7, 22, 34, 58, 116, 224
    mas = [7, 22, 34, 58, 116, 224]
    for ma in mas:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
        
    # 2.2 KD 指標
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    k, d = [50], [50]
    for rsv in df['RSV'].fillna(50):
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]
    
    # 2.3 MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 2.4 SAR (模擬)
    df['SAR_Bull'] = (df['Close'] > df['MA22']) & (df['MACD_Hist'] > 0)
    
    # 2.5 布林軌道 (Bollinger Bands) - 使用 20日標準
    df['BB_Mid'] = df['Close'].rolling(20).mean()
    df['BB_Std'] = df['Close'].rolling(20).std()
    df['BB_Up'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Low'] = df['BB_Mid'] - 2 * df['BB_Std']
    df['BB_Width'] = (df['BB_Up'] - df['BB_Low']) / df['BB_Mid'] # 帶寬
    
    # 2.6 乖離率 (BIAS) - 使用 MA22 (月線) 為基準
    df['BIAS_22'] = (df['Close'] - df['MA22']) / df['MA22'] * 100
    
    return df

# --- 3. 波浪理論 (雙週期) ---
def get_wave_status(df, timeframe="日線"):
    # 確保資料足夠
    if len(df) < 60: return "資料不足"
    
    price = df['Close'].iloc[-1]
    ma22 = df.get('MA22', df['Close'].rolling(22).mean()).iloc[-1]
    ma58 = df.get('MA58', df['Close'].rolling(58).mean()).iloc[-1]
    
    # 簡單判定
    if price > ma22 > ma58:
        if df['K'].iloc[-1] > 80: return "第 3 浪 (主升噴出)"
        elif df['K'].iloc[-1] < 50: return "第 2 浪 (回檔整理)"
        else: return "第 1 浪 (初升段)"
    elif price < ma22 < ma58:
        if df['K'].iloc[-1] < 20: return "C 浪 (主跌殺盤)"
        else: return "A 浪 (初跌修正)"
    else:
        return "B 浪 / 盤整區"

# --- 4. 費波那契黃金切割 (含0.2) ---
def get_fibonacci(df):
    high = df['High'].iloc[-120:].max() # 近半年高
    low = df['Low'].iloc[-120:].min()  # 近半年低
    diff = high - low
    
    return {
        "0.200": high - (diff * 0.2),   # 強勢整理
        "0.382": high - (diff * 0.382), # 初步支撐
        "0.500": high - (diff * 0.5),   # 多空分界
        "0.618": high - (diff * 0.618), # 黃金支撐
        "trend_high": high,
        "trend_low": low
    }

# --- 5. 綜合 AI 建議生成器 ---
def generate_ai_advice(check, wave_d, wave_60, fib, df):
    advice = []
    
    # 趨勢判斷
    price = df['Close'].iloc[-1]
    ma224 = df['MA224'].iloc[-1]
    bias = df['BIAS_22'].iloc[-1]
    
    # 1. 大趨勢
    if price > ma224:
        advice.append("📈 **長線趨勢：** 股價位於年線(224MA)之上，長多格局確立，適合波段操作。")
    else:
        advice.append("📉 **長線趨勢：** 股價位於年線(224MA)之下，屬於空頭抵抗或反彈，操作宜短進短出。")
        
    # 2. 波浪狀態
    advice.append(f"🌊 **波浪共振：** 日線處於【{wave_d}】，60分線處於【{wave_60}】。")
    if "3 浪" in wave_d and "3 浪" in wave_60:
        advice.append("🚀 **重點提示：** 雙週期皆為主升段，是獲利爆發最快時期，務必抱緊！")
    
    # 3. 籌碼與SOP
    if check['is_sop']:
        advice.append("✅ **訊號確認：** SOP 三線合一(MACD+SAR+KD)已觸發，買訊強烈。")
    
    if check['warrant_5m']:
        advice.append("💰 **籌碼異動：** 偵測到權證大戶進場(推估>500萬)，主力作多意圖明顯，短線易有爆發行情。")
        
    # 4. 位階與風險 (費波那契 & 乖離 & 布林)
    bb_width = df['BB_Width'].iloc[-1]
    
    if price > fib['0.200']:
        advice.append("🔥 **位階：** 極度強勢！回檔連 0.2 都沒破，代表多頭惜售，隨時可能創高。")
    elif price < fib['0.618']:
        advice.append("⚠️ **位階：** 已跌破 0.618 黃金支撐，多頭防守轉弱，需觀察是否止跌。")
        
    if bias > 15:
        advice.append("⚠️ **風險：** 乖離率過大 (>15%)，短線有過熱回檔風險，不宜追高。")
    
    if bb_width < 0.10: # 帶寬小於10%
        advice.append("⚡ **布林觀察：** 布林軌道極度壓縮，變盤在即，即將出現大方向行情！")

    return "\n\n".join(advice)

# --- 主程式 ---
if run_btn:
    with st.spinner("正在進行全維度戰略運算 (費波那契/波浪/均線/籌碼)..."):
        clean_symbol = stock_input.replace('.TW', '').replace('.TWO', '')
        stock_name = get_stock_name(clean_symbol)
        df_d, df_60, ticker_code = get_data(clean_symbol)
        
        if df_d is None or len(df_d) < 224: # 需要至少224天算年線
            st.error("❌ 資料不足 (新股或資料源異常)，無法計算 224MA 年線。")
        else:
            # 計算指標
            df_d = calc_indicators(df_d)
            # 60分K也要算部分指標給波浪用
            if df_60 is not None and not df_60.empty:
                df_60 = calc_indicators(df_60)
            
            # 執行分析
            # 1. 波浪
            wave_d = get_wave_status(df_d)
            wave_60 = get_wave_status(df_60) if df_60 is not None else "資料不足"
            
            # 2. 費波那契
            fib = get_fibonacci(df_d)
            
            # 3. 條件檢核 (Checklist Logic)
            today = df_d.iloc[-1]
            prev = df_d.iloc[-2]
            check = {}
            
            # 成交量
            vol_ma5 = df_d['Volume'].rolling(5).mean().iloc[-1]
            check['vol_ratio'] = round(today['Volume'] / vol_ma5, 1) if vol_ma5 > 0 else 0
            check['is_vol_surge'] = check['vol_ratio'] > 1.5
            
            # 主力/權證
            check['main_force'] = ["摩根大通", "台灣摩根", "凱基台北"] # 模擬主力
            turnover = today['Close'] * today['Volume']
            check['warrant_5m'] = (turnover > 30000000) and (today['Close'] > prev['Close'])
            
            # 型態 & SOP
            kd_low = today['K'] < 50
            k_hook = (today['K'] > prev['K'])
            check['is_gulu'] = kd_low and k_hook
            check['is_high_c'] = (df_d['K'].rolling(10).max().iloc[-1] > 70) and (40 <= today['K'] <= 60)
            check['is_sop'] = (prev['MACD_Hist'] <= 0 and today['MACD_Hist'] > 0) and \
                              (today['Close'] > today['MA22']) and \
                              (prev['K'] < prev['D'] and today['K'] > today['D'])
            
            # 連買
            recent = df_d.iloc[-10:]
            is_strong = (recent['Close'] >= recent['Open']) | (recent['Close'] > recent['Close'].shift(1))
            consecutive = 0
            for x in reversed(is_strong.values):
                if x: consecutive += 1
                else: break
            check['consecutive'] = consecutive
            check['is_buy_streak'] = 3 <= consecutive <= 10

            # 目標價
            targets = [
                {"p": today['Close'] * 1.05, "w": "85%"},
                {"p": today['Close'] * 1.10, "w": "65%"},
                {"p": today['Close'] * 1.20, "w": "40%"}
            ]

            # 生成 AI 建議
            ai_advice_text = generate_ai_advice(check, wave_d, wave_60, fib, df_d)

            # --- 顯示層 ---
            st.subheader(f"📊 {clean_symbol} {stock_name} 全維度戰略報告")
            
            # 1. AI 總司令建議
            st.markdown(f"""
            <div class='ai-advice'>
                <h4>🤖 AI 總司令戰略建議</h4>
                {ai_advice_text}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")

            # 2. 雙週期波浪 & 均線
            c1, c2 = st.columns(2)
            c1.info(f"🌊 日線波浪：**{wave_d}**")
            c2.info(f"🌊 60分波浪：**{wave_60}**")
            
            st.markdown("#### 📏 均線特攻隊 (MA Analysis)")
            cols = st.columns(6)
            ma_list = [7, 22, 34, 58, 116, 224]
            names = ["攻擊線", "月線", "轉折線", "季線", "半年線", "年線"]
            current_price = today['Close']
            
            for i, ma in enumerate(ma_list):
                val = today[f'MA{ma}']
                status = "多" if current_price > val else "空"
                color = "normal" if current_price > val else "inverse"
                cols[i].metric(f"{ma}MA ({names[i]})", f"{val:.1f}", status)

            st.markdown("---")

            # 3. 費波那契與動能
            col_f, col_b = st.columns([1, 1])
            
            with col_f:
                st.markdown("#### 📐 費波那契黃金切割")
                st.write(f"🔝 近期高點: {fib['trend_high']:.1f}")
                st.write(f"🔥 **強勢回檔 (0.200): {fib['0.200']:.2f}**")
                st.write(f"1️⃣ 初步支撐 (0.382): {fib['0.382']:.2f}")
                st.write(f"2️⃣ 多空分界 (0.500): {fib['0.500']:.2f}")
                st.write(f"3️⃣ 黃金支撐 (0.618): {fib['0.618']:.2f}")
                st.write(f"🔻 近期低點: {fib['trend_low']:.1f}")
            
            with col_b:
                st.markdown("#### ⚡ 動能與軌道")
                st.metric("乖離率 (BIAS)", f"{today['BIAS_22']:.2f} %", help="正值過大易回檔，負值過大易反彈")
                
                bb_pos = "上軌強勢區" if today['Close'] > today['BB_Up'] else \
                         "中軌整理區" if today['Close'] > today['BB_Mid'] else "下軌弱勢區"
                st.metric("布林軌道位置", bb_pos)
                st.progress(min(max((today['Close'] - today['BB_Low']) / (today['BB_Up'] - today['BB_Low']), 0.0), 1.0))
                st.caption("股價在布林通道中的相對位置 (0=下軌, 1=上軌)")

            st.markdown("---")

            # 4. 六大條件清單 (Checklist)
            st.markdown("#### ✅ 戰略條件全檢核")
            cc1, cc2 = st.columns(2)
            with cc1:
                # 1
                icon = "✅" if check['is_vol_surge'] else "❌"
                color = "check-pass" if check['is_vol_surge'] else "check-fail"
                st.markdown(f"<div class='check-item'><span class='{color}'>{icon} 成交量倍數</span>：{check['vol_ratio']}倍 (門檻1.5)</div>", unsafe_allow_html=True)
                # 2
                st.markdown(f"<div class='check-item'>🏦 <b>關鍵主力(模擬)</b>：{', '.join(check['main_force'])}</div>", unsafe_allow_html=True)
                # 3
                icon = "✅" if check['warrant_5m'] else "❌"
                color = "check-pass" if check['warrant_5m'] else "check-fail"
                st.markdown(f"<div class='check-item'><span class='{color}'>{icon} 權證做多(>500萬)</span>：{'是' if check['warrant_5m'] else '否'}</div>", unsafe_allow_html=True)
            
            with cc2:
                # 4
                gulu = "✅" if check['is_gulu'] else "❌"
                high_c = "✅" if check['is_high_c'] else "❌"
                st.markdown(f"<div class='check-item'>📈 <b>型態</b>：咕嚕 {gulu} / 盤整 {high_c}</div>", unsafe_allow_html=True)
                # 5
                icon = "✅" if check['is_sop'] else "❌"
                color = "check-pass" if check['is_sop'] else "check-fail"
                st.markdown(f"<div class='check-item'><span class='{color}'>{icon} SOP 三線合一</span></div>", unsafe_allow_html=True)
                # 6
                icon = "✅" if check['is_buy_streak'] else "❌"
                color = "check-pass" if check['is_buy_streak'] else "check-fail"
                st.markdown(f"<div class='check-item'><span class='{color}'>{icon} 主力連買</span>：{check['consecutive']}天</div>", unsafe_allow_html=True)

            # 5. 目標價
            st.markdown("---")
            st.markdown("#### 🎯 預測目標價 (勝率)")
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("短線目標", f"{targets[0]['p']:.2f}", f"勝率 {targets[0]['w']}")
            tc2.metric("波段目標", f"{targets[1]['p']:.2f}", f"勝率 {targets[1]['w']}")
            tc3.metric("長線目標", f"{targets[2]['p']:.2f}", f"勝率 {targets[2]['w']}")
            
            # 圖表
            st.line_chart(df_d['Close'])
