import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V42.0 菁英排序版)")

# --- 1. 智慧抓股引擎 (擴大抓取範圍) ---
@st.cache_data(ttl=1800)
def get_market_stocks():
    # 備援名單 (確保至少有基本盤)
    backup_codes = [
        "2330.TW", "2317.TW", "2324.TW", "2603.TW", "2609.TW", "3231.TW", "2357.TW", "3037.TW", "2382.TW", "2303.TW", 
        "2454.TW", "2379.TW", "2356.TW", "2615.TW", "3481.TW", "2409.TW", "2376.TW", "2301.TW", "3035.TW", "3017.TW",
        "1513.TW", "1519.TW", "1605.TW", "1503.TW", "2515.TW", "2501.TW", "2881.TW", "2882.TW", "2891.TW", "5880.TW",
        "2886.TW", "2892.TW", "1319.TW", "1722.TW", "1795.TW", "4763.TW", "4133.TW", "6446.TW", "6472.TW", "3711.TW",
        "2344.TW", "6770.TW", "3529.TW", "6239.TW", "8069.TWO", "3034.TW", "3532.TW", "3008.TW", "3189.TW", "5347.TWO",
        "3260.TWO", "6180.TWO", "8046.TW", "2449.TW", "6189.TW", "6278.TW", "4968.TW", "4961.TW", "2498.TW", "2368.TW",
        "2313.TW", "2312.TW", "2367.TW", "6213.TW", "3044.TW", "3019.TW", "2408.TW", "3443.TW", "3661.TW", "6669.TW",
        "3036.TW", "2383.TW", "2323.TW", "2404.TW", "2455.TW", "3583.TW", "4906.TW", "5269.TW", "5483.TWO", "6488.TWO",
        "6147.TWO", "8299.TWO", "3558.TWO", "8064.TWO", "8936.TWO", "1504.TW", "1514.TW", "2002.TW", "2027.TW", "2006.TW",
        "1609.TW", "1603.TW", "2912.TW", "9945.TW", "2618.TW", "2610.TW", "1101.TW", "1102.TW", "1301.TW", "1303.TW"
    ]
    backup_list = [{'code': c, 'name': c.replace('.TW', '')} for c in backup_codes]
    headers = {'User-Agent': 'Mozilla/5.0'}

    # 嘗試抓取更多股票 (HiStock 全部排行)
    try:
        url_histock = "https://histock.tw/stock/rank.aspx?p=all" 
        r = requests.get(url_histock, headers=headers, timeout=6)
        dfs = pd.read_html(r.text)
        df = dfs[0]
        col_code = [c for c in df.columns if '代號' in str(c)][0]
        col_name = [c for c in df.columns if '股票' in str(c) or '名稱' in str(c)][0]
        stock_list = []
        for index, row in df.iterrows():
            code = ''.join([c for c in str(row[col_code]) if c.isdigit()])
            name = str(row[col_name])
            if len(code) == 4:
                stock_list.append({'code': f"{code}.TW", 'name': name})
        
        # 為了效能，我們取前 300~400 檔有量的股票進行掃描
        # 如果全部抓 2000 檔，Streamlit 會超時
        if len(stock_list) > 100:
            return stock_list[:400], "✅ 擴大掃描市場熱門股 (前400檔)"
    except Exception:
        pass

    return backup_list, "⚠️ 外部連線受阻，啟用備援名單"

# --- 2. 技術指標計算 (含 SAR) ---
def calculate_indicators(df):
    df['Low_9'] = df['Low'].rolling(9).min()
    df['High_9'] = df['High'].rolling(9).max()
    df['RSV'] = (df['Close'] - df['Low_9']) / (df['High_9'] - df['Low_9']) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()

    # SAR 計算
    high = df['High']
    low = df['Low']
    close = df['Close']
    sar = [0.0] * len(df)
    trend = [0] * len(df) 
    af = 0.02
    max_af = 0.2
    
    trend[0] = 1 if close[0] > close[0] else -1
    sar[0] = low[0] if trend[0] == 1 else high[0]
    ep = high[0] if trend[0] == 1 else low[0]
    
    for i in range(1, len(df)):
        sar[i] = sar[i-1] + af * (ep - sar[i-1])
        if trend[i-1] == 1:
            if low[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep
                ep = low[i]
                af = 0.02
            else:
                trend[i] = 1
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + 0.02, max_af)
                sar[i] = min(sar[i], low[i-1], low[i-2] if i>1 else low[i-1])
        else:
            if high[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep
                ep = high[i]
                af = 0.02
            else:
                trend[i] = -1
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + 0.02, max_af)
                sar[i] = max(sar[i], high[i-1], high[i-2] if i>1 else high[i-1])
    df['SAR'] = sar
    return df

# --- 3. 核心策略邏輯 (計分制) ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return 0, []

    today = df.iloc[-1]
    prev = df.iloc[-2]

    # 🔥【門神檢查】流動性過濾 🔥
    # 規則改為：成交量 > 1000張 OR 爆量 1.5 倍
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    min_volume = 1000000 # 1000張
    if today['Close'] > 500: min_volume = 500000
    
    # 如果量不夠大，但也沒爆量，就淘汰
    if (today['Volume'] < min_volume) and (not is_volume_surge):
        return 0, [] # 淘汰

    reasons = []
    score = 0 # Miniko 分數
    
    # --------------------------------
    # ✅ 網子 A: 權證大戶 (權重最高)
    # --------------------------------
    # 權證做多 500萬 -> 估現貨 > 2000萬
    estimated_turnover = today['Close'] * today['Volume']
    is_warrant_whale = estimated_turnover > 20000000
    is_attacking = today['Close'] > prev['Close'] 
    
    if is_warrant_whale and is_attacking:
        score += 25 # 高分
        reasons.append("🔥權證大戶(>500萬)")
    
    if is_volume_surge:
        score += 15
        reasons.append("籌碼爆量(>1.5倍)")

    # --------------------------------
    # ✅ 網子 B: 型態
    # --------------------------------
    # 咕嚕咕嚕
    kd_low_zone = today['K'] < 50 
    k_hook_up = (today['K'] > prev['K']) or (today['K'] > today['D'])
    price_stable = today['Close'] > today['MA5']
    macd_improving = today['MACD_Hist'] > prev['MACD_Hist']
    
    if kd_low_zone and k_hook_up and price_stable and macd_improving:
        score += 10
        reasons.append("底部咕嚕咕嚕")

    # 高檔強勢
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (abs(price_change_5d) < 0.04):
        score += 10
        reasons.append("高檔強勢整理")

    # --------------------------------
    # ✅ 網子 C: SOP (MACD + SAR + KD)
    # --------------------------------
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    sar_bull = today['Close'] > today['SAR']
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    if macd_flip and sar_bull and kd_cross:
        score += 30 # 最高分指標
        reasons.append("SOP三線合一")

    # --------------------------------
    # ✅ 網子 D: 主力連買 (3-10天)
    # --------------------------------
    recent_data = df.iloc[-10:] 
    is_strong = (recent_data['Close'] >= recent_data['Open']) | (recent_data['Close'] > recent_data['Close'].shift(1).fillna(0))
    consecutive_days = 0
    for x in reversed(is_strong.values):
        if x: consecutive_days += 1
        else: break
            
    if 3 <= consecutive_days <= 10:
        score += 20
        reasons.append(f"主力連買{consecutive_days}天")

    return score, reasons

# --- 4. 執行介面 ---

st.info("💡 擴大掃描全市場，並根據「SOP、權證大戶、主力連買」積分排序，只顯示最強前20檔！")

col1, col2 = st.columns([3, 1])
with col1:
    status_msg = st.empty()
    status_msg.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    with st.spinner("正在進行全市場面試 (擴大掃描)..."):
        top_stocks_info, source_msg = get_market_stocks()
    
    st.caption(f"{source_msg} (共 {len(top_stocks_info)} 檔進入初選)")
    
    candidates = [] # 候選名單
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, stock_info in enumerate(top_stocks_info):
        stock_id = stock_info['code']
        stock_name = stock_info['name']
