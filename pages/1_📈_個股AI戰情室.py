import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V41.0 SOP完全體版)")

# --- 1. 智慧抓股引擎 (前200大) ---
@st.cache_data(ttl=1800)
def get_top_volume_stocks():
    # 備援名單
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
        if len(stock_list) > 50:
            return stock_list[:200], "✅ 成功抓取前200大 (來源: HiStock)"
    except Exception:
        pass

    try:
        url_yahoo = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        r = requests.get(url_yahoo, headers=headers, timeout=5)
        if "Table" in r.text or "table" in r.text:
            dfs = pd.read_html(r.text)
            df = dfs[0]
            target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
            stock_list = []
            for item in df[target_col]:
                item_str = str(item)
                code = ''.join([c for c in item_str if c.isdigit()])
                name = item_str.replace(code, '').strip()
                if len(code) == 4:
                    if not name: name = code
                    stock_list.append({'code': f"{code}.TW", 'name': name})
            if len(stock_list) > 10:
                return stock_list[:200], "✅ 成功抓取前200大 (來源: Yahoo)"
    except Exception:
        pass

    return backup_list, "⚠️ 外部連線受阻，啟用備援名單"

# --- 2. 技術指標計算 (含 SAR 演算法) ---
def calculate_indicators(df):
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
    
    # MA
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()

    # --- Parabolic SAR 計算 (手刻版) ---
    # 這是標準 SAR 算法，無需外掛套件
    high = df['High']
    low = df['Low']
    close = df['Close']
    sar = [0.0] * len(df)
    trend = [0] * len(df) # 1 for up, -1 for down
    af = 0.02
    max_af = 0.2
    
    # 初始化
    trend[0] = 1 if close[0] > close[0] else -1 # 簡單初始化
    sar[0] = low[0] if trend[0] == 1 else high[0]
    ep = high[0] if trend[0] == 1 else low[0]
    
    for i in range(1, len(df)):
        sar[i] = sar[i-1] + af * (ep - sar[i-1])
        
        if trend[i-1] == 1: # 上升趨勢
            if low[i] < sar[i]: # 轉折向下
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
        else: # 下降趨勢
            if high[i] > sar[i]: # 轉折向上
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

# --- 3. 核心策略邏輯 (四網合一) ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]

    # 🔥【門神檢查】流動性過濾 🔥
    # 1000張 = 1,000,000 股
    min_volume_threshold = 1000000 
    if today['Close'] > 500: min_volume_threshold = 500000 
    
    if today['Volume'] < min_volume_threshold:
        return False, "量能不足 (剔除冷門股)"
    
    reasons = []

    # --------------------------------
    # ✅ 網子 A: 爆量 OR 權證大戶
    # --------------------------------
    # 1. 爆量 (1.5倍)
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    # 2. 權證做多 500萬 (預估現貨成交 > 2500萬)
    # 避險倍數約 4-6 倍，設定現貨門檻 2500萬
    estimated_turnover = today['Close'] * today['Volume']
    is_warrant_whale = estimated_turnover > 25000000
    
    is_attacking = today['Close'] > prev['Close'] # 必須是漲的
    
    if is_attacking and (is_volume_surge or is_warrant_whale):
        tag = "爆量" if is_volume_surge else "權證大戶"
        reasons.append(f"【網子A】{tag}攻擊 (量增或金額大)")

    # --------------------------------
    # ✅ 網子 B: 型態 (咕嚕咕嚕 OR 高檔強勢)
    # --------------------------------
    # 咕嚕咕嚕: KD低檔 + 勾頭 + 站上MA5
    kd_low_zone = today['K'] < 50 
    k_hook_up = (today['K'] > prev['K']) or (today['K'] > today['D'])
    price_stable = today['Close'] > today['MA5']
    macd_improving = today['MACD_Hist'] > prev['MACD_Hist']
    if kd_low_zone and k_hook_up and price_stable and macd_improving:
        reasons.append("【網子B】底部咕嚕咕嚕 (蓄勢待發)")

    # 高檔強勢: K值高檔回落但價穩
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (abs(price_change_5d) < 0.04):
        reasons.append("【網子B】高檔強勢整理 (價穩待噴)")

    # --------------------------------
    # ✅ 網子 C: SOP (MACD + SAR + KD)
    # --------------------------------
    # 1. MACD 翻紅 (DIF - MACD 由負轉正)
    # 注意：有時候是 DIF 穿越 MACD，有時候是柱狀體翻正，這裡用柱狀體最直觀
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    
    # 2. SAR 轉多 (股價站上 SAR)
    # 如果股價 > SAR，代表 SAR 紅點點在下面 (多方)
    sar_bull = today['Close'] > today['SAR']
    
    # 3. KD 金叉
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    # 嚴格要求：三者同時成立
    if macd_flip and sar_bull and kd_cross:
        reasons.append("【網子C】SOP標準買點 (MACD翻紅+SAR多+KD金叉)")

    # --------------------------------
    # ✅ 網子 D: 主力連買 (3-10天)
    # --------------------------------
    # 掃描過去 10 天
    recent_data = df.iloc[-10:] 
    # 定義強勢天：收紅K 或 收漲
    is_strong = (recent_data['Close'] >= recent_data['Open']) | (recent_data['Close'] > recent_data['Close'].shift(1).fillna(0))
    
    # 計算連續天數
    consecutive_days = 0
    for x in reversed(is_strong.values):
        if x: consecutive_days += 1
        else: break
            
    if 3 <= consecutive_days <= 10:
        reasons.append(f"【網子D】主力連續買超 ({consecutive_days}連買)")

    # --------------------------------
    # 最終決策：只要有任何一個理由，就抓！
    # --------------------------------
    if len(reasons) > 0:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 4. 執行介面 ---

st.info("💡 四網合一策略：A.爆量/權證  B.咕嚕/盤整  C.SOP(MACD+SAR+KD)  D.主力連買(3-10天)")

col1, col2 = st.columns([3, 1])
with col1:
    status_msg = st.empty()
    status_msg.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    with st.spinner("正在撒網捕捉 (前200大)..."):
        top_stocks_info, source_msg = get_top_volume_stocks()
    
    st.caption(f"{source_msg} (掃描範圍: {len(top_stocks_info)} 檔)")
    
    found_stocks = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, stock_info in enumerate(top_stocks_info):
        stock_id = stock_info['code']
        stock_name = stock_info['name']
        
        status_text.text(f"正在分析 ({i+1}/{len(top_stocks_info)}): {stock_id} {stock_name}")
        
        try:
            data = yf.download(stock_id, period="3mo", progress=False)
            
            if len(data) > 0:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                
                data = calculate_indicators(data)
                is_hit, reason = check_miniko_strategy(stock_id, data)
                
                if is_hit:
                    latest_price = data['Close'].iloc[-1]
                    vol = data['Volume'].iloc[-1] / 1000 
                    
                    pct_change = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2] * 100
                    color_icon = "🔴" if pct_change > 0 else "🟢"
                    
                    found_stocks.append({
                        "代號": stock_id,
                        "名稱": stock_name,
                        "現價": f"{latest_price:.2f} ({color_icon} {pct_change:.1f}%)",
                        "成交量": f"{int(vol)}張",
                        "入選理由": reason
                    })
        except Exception:
            continue
            
        progress_bar.progress((i + 1) / len(top_stocks_info))
    
    status_text.text("掃描完成！")
    
    if found_stocks:
        st.success(f"🎉 成功捕捉 {len(found_stocks)} 檔符合條件的個股！")
        st.dataframe(pd.DataFrame(found_stocks), use_container_width=True)
    else:
        st.warning("太嚴格了？目前前200大中，沒有發現符合條件的標的。")
