import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V46.0 SOP優先菁英版)")

# --- 1. 智慧抓股引擎 (全網聚合：Yahoo上市/上櫃 + HiStock) ---
@st.cache_data(ttl=1800)
def get_market_stocks():
    stock_map = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # 來源 A: HiStock (嗨投資)
    try:
        url = "https://histock.tw/stock/rank.aspx?p=all" 
        r = requests.get(url, headers=headers, timeout=5)
        dfs = pd.read_html(r.text)
        df = dfs[0]
        col_code = [c for c in df.columns if '代號' in str(c)][0]
        col_name = [c for c in df.columns if '股票' in str(c) or '名稱' in str(c)][0]
        for index, row in df.iterrows():
            code = ''.join([c for c in str(row[col_code]) if c.isdigit()])
            name = str(row[col_name])
            if len(code) == 4: stock_map[f"{code}.TW"] = name
    except: pass

    # 來源 B: Yahoo 上市
    try:
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        r = requests.get(url, headers=headers, timeout=5)
        if "Table" in r.text or "table" in r.text:
            dfs = pd.read_html(r.text)
            df = dfs[0]
            target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
            for item in df[target_col]:
                item_str = str(item)
                code = ''.join([c for c in item_str if c.isdigit()])
                name = item_str.replace(code, '').strip()
                if len(code) == 4:
                    if not name: name = code
                    stock_map[f"{code}.TW"] = name
    except: pass

    # 來源 C: Yahoo 上櫃 (挖掘OTC飆股)
    try:
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TWO"
        r = requests.get(url, headers=headers, timeout=5)
        if "Table" in r.text or "table" in r.text:
            dfs = pd.read_html(r.text)
            df = dfs[0]
            target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
            for item in df[target_col]:
                item_str = str(item)
                code = ''.join([c for c in item_str if c.isdigit()])
                name = item_str.replace(code, '').strip()
                if len(code) == 4:
                    if not name: name = code
                    stock_map[f"{code}.TW"] = name
    except: pass

    # 備援名單
    backup_codes = [
        "2330.TW", "2317.TW", "2324.TW", "2603.TW", "2609.TW", "3231.TW", "2357.TW", "3037.TW", "2382.TW", "2303.TW", 
        "2454.TW", "2379.TW", "2356.TW", "2615.TW", "3481.TW", "2409.TW", "2376.TW", "2301.TW", "3035.TW", "3017.TW",
        "1513.TW", "1519.TW", "1605.TW", "1503.TW", "2515.TW", "2501.TW", "2881.TW", "2882.TW", "2891.TW", "5880.TW"
    ]
    for c in backup_codes:
        if c not in stock_map: stock_map[c] = c.replace('.TW', '')

    final_list = [{'code': k, 'name': v} for k, v in stock_map.items()]
    # 擴大到前 400 檔以確保能篩出 20 檔 SOP 股
    return final_list[:400], f"✅ 全網聚合完畢 (共 {len(final_list)} 檔熱門股)"

# --- 2. 技術指標計算 ---
def calculate_indicators(df):
    try:
        if df.empty: return df
        # KD
        df['Low_9'] = df['Low'].rolling(9).min()
        df['High_9'] = df['High'].rolling(9).max()
        df['RSV'] = (df['Close'] - df['Low_9']) / (df['High_9'] - df['Low_9']) * 100
        df['K'] = df['RSV'].ewm(com=2).mean()
        df['D'] = df['K'].ewm(com=2).mean()
        
        # MACD
        exp12 = df['Close'].ewm(span=12, adjust=False).mean()
        exp26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = exp12 - exp26
        df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['DIF'] - df['MACD']
        
        # MA & SAR (SAR Bull: Close > MA20 & MACD > 0 模擬多方趨勢)
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['SAR_Bull'] = (df['Close'] > df['MA20']) & (df['MACD_Hist'] > 0)
        return df
    except: return pd.DataFrame()

# --- 3. 核心策略 (SOP 優先計分制) ---
def check_miniko_strategy(stock_id, df):
    if df is None or len(df) < 30: return 0, []
    if df.isnull().values.any():
        df = df.fillna(method='ffill').fillna(method='bfill')

    today = df.iloc[-1]
    prev = df.iloc[-2]

    # 🔥 流動性過濾 🔥
    # 規則：成交量 > 1000張 OR 爆量 1.5 倍
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    min_volume = 1000000 
    if today['Close'] > 500: min_volume = 500000
    
    if (today['Volume'] < min_volume) and (not is_volume_surge):
        return 0, []

    score = 0
    reasons = []
    
    # ✅ C. SOP (MACD + SAR + KD) -> 絕對優先！
    # 如果符合 SOP，直接加 1000 分，確保排在最前面
    macd_flip = (prev['MACD_Hist'] <= 0) and (today['MACD_Hist'] > 0)
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    sar_bull = today.get('SAR_Bull', False)
    
    if macd_flip and sar_bull and kd_cross:
        score += 1000
        reasons.append("👑【SOP】三線合一(絕對優先)")

    # ✅ A. 權證/爆量
    estimated_turnover = today['Close'] * today['Volume']
    is_warrant_whale = estimated_turnover > 20000000 # 估算權證500萬
    is_attacking = today['Close'] > prev['Close'] 
    
    if is_warrant_whale and is_attacking:
        score += 30
        reasons.append("🔥權證大戶(>500萬)")
    if is_volume_surge:
        score += 20
        reasons.append(f"爆量({int(today['Volume']/vol_ma5)}倍)")

    # ✅ B. 型態 (互斥邏輯)
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    is_high_consolidation = False
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (abs(price_change_5d) < 0.04):
        is_high_consolidation = True
        score += 10
        reasons.append("高檔強勢整理")
        
    if not is_high_consolidation:
        kd_low = today['K'] < 50
        k_hook = (today['K'] > prev['K'])
        if kd_low and k_hook and (today['Close'] > today['MA5']):
            score += 10
            reasons.append("底部咕嚕咕嚕")

    # ✅ D. 主力連買 (3~10天)
    recent_closes = df['Close'].iloc[-10:].values
    recent_opens = df['Open'].iloc[-10:].values
    consecutive = 0
    for i in range(len(recent_closes)-1, 0, -1):
        if (recent_closes[i] >= recent_opens[i]) or (recent_closes[i] > recent_closes[i-1]):
            consecutive += 1
        else: break
    
    if 3 <= consecutive <= 10:
        score += 25
        reasons.append(f"主力連買{consecutive}天")

    return score, reasons

# --- 4. 執行介面 ---

st.info("💡 V46.0 策略：優先選拔符合 SOP 之個股，不足 20 檔則由權證大戶與主力連買股補足。")

col1, col2 = st.columns([3, 1])
with col1:
    status_msg = st.empty()
    status_msg.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動菁英掃描", type="primary")

if scan_btn:
    with st.spinner("1. 全網聚合中 (Yahoo/HiStock)..."):
        top_stocks_info, source_msg = get_market_stocks()
    st.caption(f"{source_msg}")

    tickers = [x['code'] for x in top_stocks_info]
    status_text = st.empty()
    status_text.text(f"2. 批次下載 {len(tickers)} 檔數據...")
    progress_bar = st.progress(0)
    
    try:
        bulk_data = yf.download(tickers, period="3mo", group_by='ticker', threads=True, progress=False)
        candidates = []
        total_stocks = len(tickers)
        
        for i, stock_info in enumerate(top_stocks_info):
            code = stock_info['code']
            name = stock_info['name']
            try:
                if isinstance(bulk_data.columns, pd.MultiIndex): df = bulk_data[code].copy()
                else: df = bulk_data.copy()

                if df.empty or 'Close' not in df.columns or df['Close'].isnull().all(): continue
                    
                df = calculate_indicators(df)
                score, reasons = check_miniko_strategy(code, df)
                
                # 只要有分數就暫存，最後再排序取前20
                if score > 0:
                    latest = df['Close'].iloc[-1]
                    vol = df['Volume'].iloc[-1] / 1000
                    chg = (latest - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
                    color = "🔴" if chg > 0 else "🟢"
                    
                    candidates.append({
                        "代號": code, "名稱": name,
                        "現價": f"{latest:.2f} ({color} {chg:.1f}%)",
                        "成交量": f"{int(vol)}張",
                        "Miniko分數": score,
                        "入選理由": " + ".join(reasons)
                    })
            except: continue 
            
            if i % 20 == 0:
                progress_bar.progress((i + 1) / total_stocks)
                status_text.text(f"3. AI 面試中... ({i}/{total_stocks})")

        progress_bar.progress(1.0)
        status_text.text("分析完成！")
        
        if candidates:
            # 依照分數由高到低排序 (SOP股會因為 +1000分 排在最上面)
            df_candidates = pd.DataFrame(candidates).sort_values(by="Miniko分數", ascending=False)
            
            # 強制取前 20 名 (補滿機制)
            final_list = df_candidates.head(20).reset_index(drop=True)
            
            st.success(f"🎉 掃描完成！為您呈獻 Top 20 菁英股 (SOP優先列出)")
            st.dataframe(final_list, use_container_width=True)
        else:
            st.warning("今日市況極度冷清，未發現符合條件標的。")
            
    except Exception as e:
        st.error(f"系統異常: {e}")
