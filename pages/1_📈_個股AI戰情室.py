import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V31.0 嚴格咕嚕版)")

# --- 1. 自動抓取台股成交量前 100 大 ---
@st.cache_data(ttl=3600) 
def get_top_volume_stocks():
    try:
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        # 嘗試使用 lxml，如果失敗會自動退回到預設解析器
        dfs = pd.read_html(r.text)
        df = dfs[0]
        
        target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
        stock_ids = []
        for item in df[target_col]:
            code = ''.join([c for c in str(item) if c.isdigit()])
            if len(code) == 4:
                stock_ids.append(f"{code}.TW")
        return stock_ids[:100]
    except Exception as e:
        st.error(f"抓取排行榜失敗 (請檢查 lxml 是否安裝): {e}")
        # 如果失敗，回傳空清單，強制使用者看到錯誤，而不是給錯誤的死魚股
        return []

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
    
    # 均線 (用於判斷是否有撐)
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    
    return df

# --- 3. 核心策略邏輯 (修正後的嚴格版) ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]
    
    # --- 條件 0: 爆量檢查 ---
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    # 嚴格定義爆量：比5日均量大 1.8 倍 (原本1.5倍可能太容易達成)
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.8)
    
    # --- 條件 A: 嚴格版咕嚕咕嚕 (底部轉折) ---
    condition_a = False
    reason_a = ""
    
    # 1. KD 位置低，但必須「勾頭」
    # K < 50 (不用太低，40-50之間如果有勾起來也算強)
    kd_low_zone = today['K'] < 50 
    # 關鍵：今天 K > 昨天 K (勾起來了)，或者 K > D (金叉)
    k_hook_up = (today['K'] > prev['K']) or (today['K'] > today['D'])
    
    # 2. 必須有「止跌」跡象
    # 今天收盤價 站上 5日均線 (代表短線有人顧)
    price_stable = today['Close'] > today['MA5']
    
    # 3. 能量累積 (MACD 綠柱縮短)
    # 雖然還是負的，但負的比較少 (prev_hist < today_hist)
    macd_improving = today['MACD_Hist'] > prev['MACD_Hist']
    
    if kd_low_zone and k_hook_up and price_stable and macd_improving:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD勾頭+站上5日線+能量增強)"

    # --- 條件 B: 嚴格版高檔強勢整理 ---
    # K值從高檔回落，但股價死不跌
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    # 過去5天波動極小 (盤整)
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (price_change_5d > -0.03) and (price_change_5d < 0.03):
        condition_a = True # 這裡也算符合盤感
        reason_a = "高檔強勢整理 (KD修正但價穩)"

    # --- 條件 C: 標準 SOP (三線合一) ---
    condition_b = False
    
    # MACD 翻紅
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    # 趨勢多 (站上月線)
    trend_bull = today['Close'] > df['MA20'].iloc[-1] 
    # KD 金叉
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    if macd_flip and trend_bull and kd_cross:
        condition_b = True
    
    # --- 綜合判斷 ---
    reasons = []
    
    # 只有爆量是不夠的，必須搭配至少「不跌」
    # 如果爆量但是收長黑 (Price drop)，那就是出貨，不能選！
    is_red_candle = today['Close'] >= today['Open'] # 雖然爆量，要是紅K才算好事
    
    if is_volume_surge and is_red_candle:
        # 單純爆量紅K，列入觀察，但不一定是咕嚕咕嚕
        reasons.append("【籌碼】爆量紅K (量增 > 1.8倍)")
    
    if condition_a:
        reasons.append(f"【型態】{reason_a}")
    if condition_b:
        reasons.append("【訊號】SOP買點 (MACD翻紅+KD金叉)")
        
    # 最終決策：
    # 1. 符合咕嚕咕嚕 OR
    # 2. 符合 SOP OR
    # 3. 爆量 且 同時符合 (咕嚕咕嚕 或 SOP) -> 這樣才抓爆量，不然單純爆量太雜
    # 修改：您說爆量都要抓進來，但我們過濾掉「爆量長黑」的爛股
    
    isValid = False
    if condition_a or condition_b:
        isValid = True
    elif is_volume_surge and is_red_candle: # 如果只是爆量，要是紅K我才給過
        isValid = True
        
    if isValid:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 4. 執行介面 ---

st.info("💡 系統自動抓取「成交量前 100 大」，並執行 Miniko 嚴格篩選 (剔除無量下跌股)")

col1, col2 = st.columns([3, 1])
with col1:
    st.write("Miniko 正在監控市場...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    # 1. 自動抓榜
    with st.spinner("正在從交易所抓取熱門股名單..."):
        top_stocks = get_top_volume_stocks()
    
    if not top_stocks:
        st.error("無法抓取清單，請確認 requirements.txt 是否已包含 lxml")
    else:
        st.write(f"已取得今日熱門股共 {len(top_stocks)} 檔，開始 AI 篩選...")
        
        found_stocks = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 2. 開始迴圈掃描
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
                        
                        # 簡單的變色邏輯 (漲跌幅)
                        pct_change = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2] * 100
                        color = "🔴" if pct_change > 0 else "🟢"
                        
                        found_stocks.append({
                            "代號": stock_id,
                            "現價": f"{latest_price:.2f} ({color} {pct_change:.1f}%)",
                            "成交量": f"{int(vol)}張",
                            "入選理由": reason
                        })
            except Exception:
                continue
                
            progress_bar.progress((i + 1) / len(top_stocks))
        
        status_text.text("掃描完成！")
        
        if found_stocks:
            st.success(f"🎉 掃描 {len(top_stocks)} 檔，發現 {len(found_stocks)} 檔真正符合「咕嚕咕嚕」或「爆量紅K」的個股！")
            st.dataframe(pd.DataFrame(found_stocks), use_container_width=True)
        else:
            st.warning("太嚴格了？目前前100大中，沒有發現符合「底部轉強」或「SOP」的標的。")
