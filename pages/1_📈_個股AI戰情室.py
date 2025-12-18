import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V34.0 百大備援版)")

# --- 1. 智慧抓股引擎 (含 100 檔擴充名單) ---
@st.cache_data(ttl=3600)
def get_top_volume_stocks():
    # B 計畫：擴充至 100 檔權值與熱門股，確保連線受阻時仍有充足標的
    backup_list = [
        # --- 半導體 & 電子權值 ---
        "2330.TW", "2317.TW", "2454.TW", "2303.TW", "2308.TW", "3711.TW", "3034.TW", "2379.TW", "3661.TW", "3443.TW",
        "2344.TW", "2408.TW", "2337.TW", "6770.TW", "8016.TW", "8299.TWO", "6488.TWO", "5483.TWO", "3105.TWO", "3035.TW",
        # --- AI 伺服器 & 電腦週邊 ---
        "2382.TW", "3231.TW", "2357.TW", "6669.TW", "2356.TW", "2301.TW", "4938.TW", "2353.TW", "2324.TW", "2376.TW",
        "2377.TW", "3017.TW", "6239.TW", "3013.TW", "8114.TW", "3324.TWO",
        # --- PCB & 網通 & 零組件 ---
        "3037.TW", "2313.TW", "8046.TW", "3189.TW", "2368.TW", "2449.TW", "6271.TW", "2492.TW", "3044.TW", "5347.TWO",
        "2455.TW", "6278.TW", "4958.TW", "9802.TW",
        # --- 面板 & 光電 ---
        "2409.TW", "3481.TW", "3008.TW",
        # --- 航運 & 航空 ---
        "2603.TW", "2609.TW", "2615.TW", "2610.TW", "2618.TW", "2637.TW", "2606.TW", "2605.TW",
        # --- 金融 & 壽險 ---
        "2881.TW", "2882.TW", "2891.TW", "2886.TW", "2884.TW", "2885.TW", "2892.TW", "5880.TW", "2880.TW", "2883.TW",
        "2887.TW", "2890.TW", "5871.TW", "2801.TW", "2834.TW", "2888.TW",
        # --- 重電 & 綠能 & 線纜 ---
        "1503.TW", "1504.TW", "1513.TW", "1519.TW", "1605.TW", "1609.TW", "6806.TW", "9958.TW",
        # --- 傳產龍頭 (塑化/鋼鐵/水泥/汽車) ---
        "1101.TW", "1102.TW", "1216.TW", "1301.TW", "1303.TW", "1326.TW", "1402.TW", "2002.TW", "2014.TW", "2027.TW",
        "2201.TW", "2207.TW", "2105.TW", "2912.TW", "9910.TW", "9904.TW", "9945.TW",
        # --- 電信 ---
        "2412.TW", "3045.TW", "4904.TW"
    ]
    
    try:
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        r = requests.get(url, headers=headers, timeout=5)
        
        if "Table" not in r.text and "table" not in r.text:
            raise ValueError("Blocked")

        dfs = pd.read_html(r.text)
        df = dfs[0]
        
        target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
        stock_ids = []
        for item in df[target_col]:
            code = ''.join([c for c in str(item) if c.isdigit()])
            if len(code) == 4:
                stock_ids.append(f"{code}.TW")
        
        # 這裡改為：如果抓到的少於 10 檔，就用備援；如果成功抓到，就用抓到的
        if len(stock_ids) > 10:
            return stock_ids[:100], "✅ 成功抓取 Yahoo 即時榜單"
        else:
            return backup_list, "⚠️ 抓取數量過少，啟用百大備援名單"

    except Exception:
        return backup_list, "⚠️ 交易所連線受阻，已啟用「百大權值+熱門股」備援名單"

# --- 2. 技術指標計算 ---
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
    
    # 均線
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    
    return df

# --- 3. 核心策略邏輯 ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]
    
    # --- 條件 0: 爆量檢查 ---
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.8)
    
    # --- 條件 A: 嚴格版咕嚕咕嚕 ---
    condition_a = False
    reason_a = ""
    
    kd_low_zone = today['K'] < 50 
    k_hook_up = (today['K'] > prev['K']) or (today['K'] > today['D'])
    price_stable = today['Close'] > today['MA5']
    macd_improving = today['MACD_Hist'] > prev['MACD_Hist']
    
    if kd_low_zone and k_hook_up and price_stable and macd_improving:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD勾頭+站上5日線+能量增強)"

    # --- 條件 B: 嚴格版高檔強勢整理 ---
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (abs(price_change_5d) < 0.04):
        condition_a = True
        reason_a = "高檔強勢整理 (KD修正但價穩)"

    # --- 條件 C: SOP (MACD翻紅+趨勢多+KD金叉) ---
    condition_b = False
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    trend_bull = today['Close'] > df['MA20'].iloc[-1] 
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    if macd_flip and trend_bull and kd_cross:
        condition_b = True
    
    # --- 條件 D: 主力鐵底連買 (新功能) ---
    condition_d = False
    reason_d = ""
    
    recent_high_10 = df['High'].rolling(10).max().iloc[-1]
    recent_low_10 = df['Low'].rolling(10).min().iloc[-1]
    # 避免除以0
    if recent_low_10 == 0: recent_low_10 = 0.01
    
    box_range = (recent_high_10 - recent_low_10) / recent_low_10
    
    last_3_days = df.iloc[-3:]
    three_red_soldiers = all(last_3_days['Close'] >= last_3_days['Open'])
    three_days_up = (df['Close'].iloc[-1] >= df['Close'].iloc[-2]) and \
                    (df['Close'].iloc[-2] >= df['Close'].iloc[-3])
    
    # 震幅小於 6% 且 (連三紅 或 連三漲)
    if (box_range < 0.06) and (three_red_soldiers or three_days_up):
        condition_d = True
        reason_d = "主力鐵底護盤 (平台整理+連3日買盤)"

    # --- 綜合決策 ---
    reasons = []
    is_red_candle = today['Close'] >= today['Open']
    
    if is_volume_surge and is_red_candle:
         reasons.append("【籌碼】爆量紅K (量增>1.8倍)")
    
    if condition_a:
        reasons.append(f"【型態】{reason_a}")
    if condition_b:
        reasons.append("【訊號】SOP買點 (MACD翻紅+KD金叉)")
    if condition_d:
        reasons.append(f"【主力】{reason_d}")
        
    isValid = False
    if condition_a or condition_b or condition_d:
        isValid = True
    elif is_volume_surge and is_red_candle:
        isValid = True
        
    if isValid:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 4. 執行介面 ---

st.info("💡 系統條件：1. 咕嚕咕嚕/高檔整理  2. SOP  3. 爆量紅K  4. 主力鐵底護盤")

col1, col2 = st.columns([3, 1])
with col1:
    status_msg = st.empty()
    status_msg.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    # 顯示目前使用的名單來源
    with st.spinner("正在獲取股票清單..."):
        top_stocks, source_msg = get_top_volume_stocks()
    
    st.caption(f"{source_msg} (共 {len(top_stocks)} 檔)")
    
    found_stocks = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, stock_id in enumerate(top_stocks):
        status_text.text(f"正在分析 ({i+1}/{len(top_stocks)}): {stock_id}")
        
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
                        "現價": f"{latest_price:.2f} ({color_icon} {pct_change:.1f}%)",
                        "成交量": f"{int(vol)}張",
                        "入選理由": reason
                    })
        except Exception:
            continue
            
        progress_bar.progress((i + 1) / len(top_stocks))
    
    status_text.text("掃描完成！")
    
    if found_stocks:
        st.success(f"🎉 發現 {len(found_stocks)} 檔符合條件的潛力股！")
        st.dataframe(pd.DataFrame(found_stocks), use_container_width=True)
    else:
        st.warning("太嚴格了？目前清單中，沒有發現符合條件的標的。")
