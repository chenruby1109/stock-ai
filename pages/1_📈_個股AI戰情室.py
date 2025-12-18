import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V39.0 權證大戶+主力連買版)")

# --- 1. 智慧抓股引擎 (擴大至前200名 + 抓取名稱) ---
@st.cache_data(ttl=1800)
def get_top_volume_stocks():
    # 備援名單 (含仁寶 2324)
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

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

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
            return stock_list[:200], "✅ 成功抓取前200大熱門股 (將執行嚴格過濾)"
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
                return stock_list[:200], "✅ 成功抓取 Yahoo 熱門榜"
    except Exception:
        pass

    return backup_list, "⚠️ 外部連線受阻，啟用備援名單"

# --- 2. 技術指標計算 ---
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
    return df

# --- 3. 核心策略邏輯 ---
def check_miniko_strategy(stock_id, df):
    if len(df) < 30: return False, "資料不足"

    today = df.iloc[-1]
    prev = df.iloc[-2]

    # 🔥【門神檢查】成交量 < 1000 張直接淘汰 🔥
    min_volume_threshold = 1000000 
    if today['Close'] > 500: min_volume_threshold = 500000 
    if today['Volume'] < min_volume_threshold:
        return False, "成交量不足 (剔除冷門股)"
    
    # --------------------------------
    # 條件 0: 爆量檢查
    # --------------------------------
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.8)
    
    # --------------------------------
    # 條件 A: 嚴格版咕嚕咕嚕
    # --------------------------------
    condition_a = False
    reason_a = ""
    kd_low_zone = today['K'] < 50 
    k_hook_up = (today['K'] > prev['K']) or (today['K'] > today['D'])
    price_stable = today['Close'] > today['MA5']
    macd_improving = today['MACD_Hist'] > prev['MACD_Hist']
    if kd_low_zone and k_hook_up and price_stable and macd_improving:
        condition_a = True
        reason_a = "底部咕嚕咕嚕 (KD勾頭+站上5日線+能量增強)"

    # --------------------------------
    # 條件 B: 高檔強勢整理
    # --------------------------------
    max_k_recent = df['K'].rolling(10).max().iloc[-1]
    price_change_5d = (today['Close'] - df['Close'].iloc[-6]) / df['Close'].iloc[-6]
    if (max_k_recent > 70) and (40 <= today['K'] <= 60) and (abs(price_change_5d) < 0.04):
        condition_a = True
        reason_a = "高檔強勢整理 (KD修正但價穩)"

    # --------------------------------
    # 條件 C: SOP (MACD+Trend+KD)
    # --------------------------------
    condition_b = False
    macd_flip = (prev['MACD_Hist'] < 0) and (today['MACD_Hist'] > 0)
    trend_bull = today['Close'] > df['MA20'].iloc[-1] 
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    if macd_flip and trend_bull and kd_cross:
        condition_b = True
    
    # --------------------------------
    # 條件 D: 主力連買 (連續 3-5 天)
    # --------------------------------
    condition_d = False
    reason_d = ""
    
    # 檢查最近 5 天的資料
    last_5_days = df.iloc[-5:]
    last_4_days = df.iloc[-4:]
    last_3_days = df.iloc[-3:]
    
    # 定義「買進」：收盤 >= 開盤 (紅K) 或者 收盤 > 昨收 (股價漲)
    # 只要符合其中一種型態的連買即可
    
    # 檢查連5
    is_5_red = all(last_5_days['Close'] >= last_5_days['Open'])
    is_5_up = all(last_5_days['Close'] > last_5_days['Close'].shift(1).dropna())
    
    # 檢查連4
    is_4_red = all(last_4_days['Close'] >= last_4_days['Open'])
    is_4_up = all(last_4_days['Close'] > last_4_days['Close'].shift(1).dropna())
    
    # 檢查連3
    is_3_red = all(last_3_days['Close'] >= last_3_days['Open'])
    is_3_up = all(last_3_days['Close'] > last_3_days['Close'].shift(1).dropna())
    
    if (is_5_red or is_5_up):
        condition_d = True
        reason_d = "關鍵主力連續買超 (5日連買)"
    elif (is_4_red or is_4_up):
        condition_d = True
        reason_d = "關鍵主力連續買超 (4日連買)"
    elif (is_3_red or is_3_up):
        condition_d = True
        reason_d = "關鍵主力連續買超 (3日連買)"

    # --------------------------------
    # 條件 E: 權證做多 500萬 (影子追蹤)
    # --------------------------------
    condition_e = False
    reason_e = ""
    
    # 邏輯：
    # 1. 權證做多 500 萬 -> 預估券商避險買入現貨約 2000-3000 萬
    #    設定當日成交金額門檻 > 30,000,000 (3千萬)
    # 2. 必須是攻擊盤 (股價 > 昨收 1%)
    # 3. 12:00前發生? 我們假設若目前總量夠大且爆量，就是盤中發生
    
    estimated_turnover = today['Close'] * today['Volume']
    
    is_big_warrant_hedge = estimated_turnover > 30000000 # 3千萬門檻 (對應權證500萬)
    is_attacking = today['Close'] > prev['Close'] * 1.01 # 漲幅 > 1%
    
    if is_big_warrant_hedge and is_attacking and is_volume_surge:
        condition_e = True
        reason_e = "符合權證大戶進場特徵 (估計權證>500萬)"

    # --------------------------------
    # 綜合決策
    # --------------------------------
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
    if condition_e:
        reasons.append(f"【權證】🔥{reason_e}")
        
    isValid = False
    if condition_a or condition_b or condition_d or condition_e:
        isValid = True
    elif is_volume_surge and is_red_candle:
        isValid = True
        
    if isValid:
        return True, " + ".join(reasons)
    else:
        return False, ""

# --- 4. 執行介面 ---

st.info("💡 策略啟動：1.咕嚕咕嚕/盤整  2.SOP  3.爆量紅K  4.主力連買(3-5日)  5.權證大戶(>500萬)")

col1, col2 = st.columns([3, 1])
with col1:
    status_msg = st.empty()
    status_msg.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動全自動掃描", type="primary")

if scan_btn:
    with st.spinner("正在獲取熱門股 (前200大) 並剔除冷門股..."):
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
        st.success(f"🎉 發現 {len(found_stocks)} 檔符合條件的潛力股！(含主力連買 & 權證大戶)")
        st.dataframe(pd.DataFrame(found_stocks), use_container_width=True)
    else:
        st.warning("太嚴格了？目前熱門股中，沒有發現符合條件的標的。")
