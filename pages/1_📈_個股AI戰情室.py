import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈")
st.title("📈 Miniko AI 全台股獵手 (CEO 咕嚕咕嚕版)")

# --- 1. 技術指標計算函數 (電腦需要這些公式才能算出 KD/MACD) ---
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
    
    # 計算 SAR (簡化版，使用簡單邏輯模擬，精確 SAR 需要複雜遞迴)
    # 這裡先用簡單趨勢判斷替代 SAR 功能
    df['MA20'] = df['Close'].rolling(20).mean()
    df['SAR_Signal'] = np.where(df['Close'] > df['MA20'], 1, -1) # 1為多方
    
    return df

# --- 2. Miniko 核心策略邏輯 ---
def check_miniko_strategy(stock_id, df):
    # 確保資料足夠
    if len(df) < 30:
        return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]
    
    # --- 條件 0: 成交量濾網 (Volume Surge) ---
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    # 避免除以 0 錯誤
    if vol_ma5 == 0: vol_ma5 = 1
    
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    # --- 條件 A: 盤感 (底部咕嚕咕嚕 OR 高檔強勢整理) ---
    condition_a = False
    reason_a = ""
    
    # A-1 底部咕嚕咕嚕: KD < 40 且 股價有撐
    recent_low = df['Close'].rolling(5).min().iloc[-1]
    is_low_kd = (today['K'] < 40) and (today['D'] < 40)
    is_supported = today['Close'] >= recent_low
    
    if is_low_kd and is_supported:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD低檔蓄勢)"
        
    # A-2 高檔強勢整理
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    
    if (max_k_recent > 70) and (30 <= today['K'] <= 58) and (price_change_5d > -0.04):
        condition_a = True
        reason_a = "高檔強勢整理 (指標修正價不跌)"

    # --- 條件 B: 標準 SOP (MACD + SAR/趨勢 + KD金叉) ---
    condition_b = False
    
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    trend_bull = today['Close'] > df['MA20'].iloc[-1] # 替代 SAR
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    
    if macd_flip and trend_bull and kd_cross:
        condition_b = True
    
    # --- 綜合判斷 ---
    reasons = []
    if condition_a:
        reasons.append(f"【型態】{reason_a}")
    if condition_b:
        reasons.append("【訊號】MACD翻紅+趨勢多方+KD金叉")
    if is_volume_surge:
        reasons.append("【籌碼】成交量爆增 > 1.5倍")
        
    # 只要 (A 或 B 或 爆量) 成立，我們都顯示出來讓 CEO 判斷
    if condition_a or condition_b or is_volume_surge:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 3. 執行介面 ---

# 讓使用者輸入股票代號 (預設一些熱門股)
default_stocks = "2330.TW, 2317.TW, 2603.TW, 3231.TW, 2454.TW"
user_input = st.text_input("輸入股票代號 (用逗號隔開，例如: 2330.TW, 2603.TW)", default_stocks)

if st.button("🚀 啟動 AI 全自動掃描"):
    stock_list = [x.strip() for x in user_input.split(',')]
    found_stocks = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, stock_id in enumerate(stock_list):
        status_text.text(f"正在分析: {stock_id} ...")
        
        try:
            # 抓取資料
            data = yf.download(stock_id, period="3mo", progress=False)
            
            if len(data) > 0:
                # 處理 MultiIndex (yfinance 新版修正)
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                
                # 計算指標
                data = calculate_indicators(data)
                
                # 執行策略
                is_hit, reason = check_miniko_strategy(stock_id, data)
                
                if is_hit:
                    # 抓取最新收盤價
                    latest_price = data['Close'].iloc[-1]
                    found_stocks.append({
                        "代號": stock_id,
                        "現價": f"{latest_price:.2f}",
                        "入選理由": reason
                    })
        except Exception as e:
            st.error(f"分析 {stock_id} 時發生錯誤: {e}")
            
        # 更新進度條
        progress_bar.progress((i + 1) / len(stock_list))
    
    status_text.text("掃描完成！")
    
    # 顯示結果
    if found_stocks:
        st.success(f"🎉 恭喜！共發現 {len(found_stocks)} 檔符合條件的潛力股！")
        result_df = pd.DataFrame(found_stocks)
        st.table(result_df)
    else:
        st.warning("目前清單中沒有發現符合條件的股票，建議增加掃描範圍！")
