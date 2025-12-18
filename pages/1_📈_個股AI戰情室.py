import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V30.0 全自動抓榜版)")

# --- 1. 自動抓取台股成交量前 100 大 (新增功能) ---
@st.cache_data(ttl=3600) # 設定快取，避免重複一直抓
def get_top_volume_stocks():
    try:
        # 抓取 Yahoo 股市的成交量排行
        url = "https://tw.stock.yahoo.com/rank/volume?exchange=TAI"
        # 使用 pandas 快速爬取網頁表格
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        r = requests.get(url, headers=headers)
        dfs = pd.read_html(r.text)
        
        # 通常排行榜在第一個表格
        df = dfs[0]
        
        # 處理欄位，取出股票代號
        # Yahoo 的欄位通常是 "股號/名稱"，我們只需要取出數字部分
        # 假設欄位名稱包含 "股號" 或 "名稱"
        target_col = [c for c in df.columns if '股號' in c or '名稱' in c][0]
        
        # 提取代號 (例如 "2330台積電" -> "2330")
        # 這裡做一點文字處理確保只拿到代號
        stock_ids = []
        for item in df[target_col]:
            # 取出字串中的數字部分
            code = ''.join([c for c in str(item) if c.isdigit()])
            if len(code) == 4: # 確保是 4 位數股票代號
                stock_ids.append(f"{code}.TW")
        
        return stock_ids[:100] # 只取前 100 名
    except Exception as e:
        st.error(f"抓取排行榜失敗，改用預設清單: {e}")
        return ["2330.TW", "2317.TW", "2603.TW", "2609.TW", "3231.TW", "2454.TW", "2303.TW"]

# --- 2. 技術指標計算函數 ---
def calculate_indicators(df):
    # 計算 KD
    df['Low_9'] = df['Low'].rolling(9).min()
    df['High_9'] = df['High'].rolling(9).max()
    df['RSV'] = (df['Close'] - df['Low_9']) / (df['High_9'] - df['Low_9']) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    
    # 計算 MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['DIF'] - df['MACD']
    
    # 計算 SAR 趨勢 (簡化版: 價格 > 20日線)
    df['MA20'] = df['Close'].rolling(20).mean()
    
    return df

# --- 3. Miniko 核心策略邏輯 (咕嚕咕嚕 + SOP) ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]
    
    # --- 條件 0: 成交量檢查 ---
    # 這裡我們已經是從前100大抓進來的，所以本身量就大
    # 但我們還是標記一下「突然爆量」的個股 (比5日均量大1.5倍)
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    # --- 條件 A: 盤感 (底部咕嚕咕嚕 OR 高檔強勢整理) ---
    condition_a = False
    reason_a = ""
    
    # A-1 底部咕嚕咕嚕: KD < 40 (低檔) 且 股價沒破底 (有撐)
    recent_low = df['Close'].rolling(5).min().iloc[-1]
    is_low_kd = (today['K'] < 40) and (today['D'] < 40)
    # 容許一點點跌破誤差，或者收盤價守住前低
    is_supported = today['Close'] >= (recent_low * 0.98) 
    
    if is_low_kd and is_supported:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD低檔蓄勢)"
        
    # A-2 高檔強勢整理: K值曾高過70，現在回檔到30-58，但股價跌幅 < 4%
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (30 <= today['K'] <= 58) and (price_change_5d > -0.04):
        condition_a = True
        reason_a = "高檔強勢整理 (指標修正價不跌)"

    # --- 條件 B: 標準 SOP (MACD翻紅 + 趨勢多 + KD金叉) ---
    condition_b = False
    
    # MACD 柱狀體翻紅
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    # 趨勢多方 (這裡用 MA20 模擬 SAR 概念)
    trend_bull = today['Close'] > df['MA20'].iloc[-1] 
    # KD 金叉 (今天或昨天發生都算)
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    if macd_flip and trend_bull and kd_cross:
        condition_b = True
    
    # --- 綜合判斷 ---
    reasons = []
    if condition_a:
        reasons.append(f"【型態】{reason_a}")
    if condition_b:
        reasons.append("【訊號】MACD翻紅+SAR多方+KD金叉")
    if is_volume_surge:
        reasons.append("【籌碼】成交量突增(爆量)")
        
    # 邏輯：(符合 Miniko盤感 OR 符合 SOP) 就可以選出
    # 爆量是加分項，如果只是爆量但型態不對，您可以決定要不要看(這裡設定為要)
    if condition_a or condition_b or is_volume_surge:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 4. 執行介面 ---

st.info("💡 系統將自動抓取「今日台股成交量前 100 大」進行分析，您不需手動輸入。")

col1, col2 = st.columns([3, 1])
with col1:
    st.write("Miniko 正在監控市場...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    # 1. 自動抓榜
    with st.spinner("正在從交易所抓取熱門股名單..."):
        top_stocks = get_top_volume_stocks()
    
    st.write(f"已取得今日熱門股共 {len(top_stocks)} 檔，開始 AI 篩選...")
    
    found_stocks = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 2. 開始迴圈掃描
    for i, stock_id in enumerate(top_stocks):
        status_text.text(f"正在分析 ({i+1}/{len(top_stocks)}): {stock_id}")
        
        try:
            # 抓取最近 3 個月資料
            data = yf.download(stock_id, period="3mo", progress=False)
            
            if len(data) > 0:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                
                data = calculate_indicators(data)
                is_hit, reason = check_miniko_strategy(stock_id, data)
                
                if is_hit:
                    latest_price = data['Close'].iloc[-1]
                    vol = data['Volume'].iloc[-1] / 1000 # 換算成張數
                    found_stocks.append({
                        "代號": stock_id,
                        "現價": f"{latest_price:.2f}",
                        "成交量(張)": f"{int(vol)}",
                        "入選理由": reason
                    })
        except Exception as e:
            continue
            
        progress_bar.progress((i + 1) / len(top_stocks))
    
    status_text.text("掃描完成！")
    
    # 3. 顯示結果
    if found_stocks:
        st.success(f"🎉 掃描了 {len(top_stocks)} 檔熱門股，發現 {len(found_stocks)} 檔符合條件！")
        result_df = pd.DataFrame(found_stocks)
        st.dataframe(result_df, use_container_width=True)
    else:
        st.warning("太嚴格了？目前前100大熱門股中，沒有符合條件的標的。")
