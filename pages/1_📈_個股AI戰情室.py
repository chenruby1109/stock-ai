import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V32.0 永不斷線版)")

# --- 1. 智慧抓股引擎 (含自動備援機制) ---
@st.cache_data(ttl=3600)
def get_top_volume_stocks():
    # 定義 B 計畫名單：台灣50 + 中型100 成分股 (涵蓋市場最熱門標的)
    # 這是為了防止 Yahoo 阻擋爬蟲時，系統還能運作
    backup_list = [
        "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", "2615.TW", 
        "2382.TW", "2357.TW", "3231.TW", "2379.TW", "2345.TW", "3037.TW", "2356.TW", "2353.TW",
        "3034.TW", "3008.TW", "3045.TW", "2412.TW", "2881.TW", "2882.TW", "2891.TW", "2886.TW",
        "2884.TW", "2885.TW", "1101.TW", "2002.TW", "1605.TW", "2327.TW", "2409.TW", "3481.TW",
        "2376.TW", "2377.TW", "3017.TW", "2368.TW", "3035.TW", "6669.TW", "6505.TW", "1301.TW",
        "1303.TW", "1326.TW", "2912.TW", "9910.TW", "5871.TW", "2892.TW", "5880.TW", "2880.TW",
        "2883.TW", "2887.TW", "2890.TW", "2408.TW", "6239.TW", "2313.TW", "6269.TW", "5347.TWO"
    ]
    
    try:
        # 嘗試去抓 Yahoo 排行榜
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        r = requests.get(url, headers=headers, timeout=5)
        
        # 檢查是否被擋
        if "Table" not in r.text and "table" not in r.text:
            raise ValueError("Yahoo blocked the request")

        dfs = pd.read_html(r.text)
        df = dfs[0]
        
        # 找出正確欄位
        target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
        stock_ids = []
        for item in df[target_col]:
            code = ''.join([c for c in str(item) if c.isdigit()])
            if len(code) == 4:
                stock_ids.append(f"{code}.TW")
        
        if len(stock_ids) > 10:
            return stock_ids[:100], "✅ 成功抓取 Yahoo 即時成交量榜單"
        else:
            return backup_list, "⚠️ 抓取數量過少，已切換至備援熱門股名單"

    except Exception as e:
        # 只要失敗，直接回傳備用名單，不顯示錯誤給使用者，保持體驗流暢
        return backup_list, "⚠️ 交易所連線受阻，已自動切換至「權值+熱門股」備援名單"

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

# --- 3. 核心策略邏輯 (保留您要的嚴格版) ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 爆量檢查 (1.8倍)
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.8)
    
    # 條件 A: 嚴格版咕嚕咕嚕
    condition_a = False
    reason_a = ""
    
    # K < 50 且 勾頭 (K > prev_K)
    kd_low_zone = today['K'] < 50 
    k_hook_up = (today['K'] > prev['K']) or (today['K'] > today['D'])
    # 止跌 (站上5日線)
    price_stable = today['Close'] > today['MA5']
    # 能量增強 (綠柱縮短)
    macd_improving = today['MACD_Hist'] > prev['MACD_Hist']
    
    if kd_low_zone and k_hook_up and price_stable and macd_improving:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD勾頭+站上5日線+能量增強)"

    # 條件 B: 嚴格版高檔強勢整理
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (abs(price_change_5d) < 0.03):
        condition_a = True
        reason_a = "高檔強勢整理 (KD修正但價穩)"

    # 條件 C: SOP (MACD翻紅+趨勢多+KD金叉)
    condition_b = False
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    trend_bull = today['Close'] > df['MA20'].iloc[-1] 
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    if macd_flip and trend_bull and kd_cross:
        condition_b = True
    
    # 綜合判斷
    reasons = []
    is_red_candle = today['Close'] >= today['Open']
    
    if is_volume_surge and is_red_candle:
         reasons.append("【籌碼】爆量紅K (量增 > 1.8倍)")
    
    if condition_a:
        reasons.append(f"【型態】{reason_a}")
    if condition_b:
        reasons.append("【訊號】SOP買點 (MACD翻紅+KD金叉)")
        
    isValid = False
    if condition_a or condition_b:
        isValid = True
    elif is_volume_surge and is_red_candle:
        isValid = True
        
    if isValid:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 4. 執行介面 ---

st.info("💡 系統預設抓取「即時熱門榜」，若遇連線阻擋將自動切換至「權值熱門股名單」，確保分析不中斷。")

col1, col2 = st.columns([3, 1])
with col1:
    status_header = st.empty()
    status_header.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    # 1. 取得名單 (含自動備援)
    with st.spinner("正在獲取股票清單..."):
        top_stocks, source_msg = get_top_volume_stocks()
    
    st.caption(source_msg) # 顯示目前的資料來源
    st.write(f"共鎖定 {len(top_stocks)} 檔股票，開始 AI 嚴格篩選...")
    
    found_stocks = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 2. 執行迴圈
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
    
    # 3. 顯示結果
    if found_stocks:
        st.success(f"🎉 掃描完成！發現 {len(found_stocks)} 檔符合「Miniko 嚴格版」條件的個股！")
        st.dataframe(pd.DataFrame(found_stocks), use_container_width=True)
    else:
        st.warning("太嚴格了？目前的清單中，沒有發現符合「底部轉強」或「SOP」的標的，建議明天開盤再試！")
