import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# 設定頁面標題
st.set_page_config(page_title="Miniko AI 戰情室", page_icon="📈", layout="wide")
st.title("📈 Miniko AI 全台股獵手 (V44.0 多源聚合渦輪版)")

# --- 1. 智慧抓股引擎 (多源頭聚合：HiStock + Yahoo上市 + Yahoo上櫃) ---
@st.cache_data(ttl=1800)
def get_market_stocks():
    # 用於儲存結果的字典 (使用字典可自動去重複: code -> name)
    stock_map = {}
    
    # 偽裝瀏覽器 Header
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    # ------------------------------------------------
    # 來源 A: HiStock (嗨投資) - 通常最穩定
    # ------------------------------------------------
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
            if len(code) == 4:
                stock_map[f"{code}.TW"] = name # 存入字典
    except Exception as e:
        print(f"HiStock error: {e}")

    # ------------------------------------------------
    # 來源 B: Yahoo 股市 (上市 TAI)
    # ------------------------------------------------
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
    except Exception as e:
        print(f"Yahoo TAI error: {e}")

    # ------------------------------------------------
    # 來源 C: Yahoo 股市 (上櫃 TWO) - 抓OTC飆股
    # ------------------------------------------------
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
                    # 上櫃股票代號在 yfinance 也是 .TW (大部分) 或 .TWO，這裡統一先試 .TW
                    # 註：yfinance 台股上櫃通常也吃 .TW，若不行可試 .TWO，但在批次下載中混合比較麻煩
                    # 我們這裡先假設 .TW，因為大部份資料源通用
                    if not name: name = code
                    stock_map[f"{code}.TW"] = name
    except Exception as e:
        print(f"Yahoo TWO error: {e}")

    # ------------------------------------------------
    # 備援名單 (如果上面都抓不到，至少要有這些)
    # ------------------------------------------------
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
    
    # 確保備援名單也在裡面
    for c in backup_codes:
        if c not in stock_map:
            stock_map[c] = c.replace('.TW', '')

    # 轉回 List 格式 [{'code':..., 'name':...}]
    final_list = [{'code': k, 'name': v} for k, v in stock_map.items()]
    
    # 限制數量 (避免雲端當機，取前 350 檔)
    # 通常三個來源加起來會有 200-300 檔不重複的
    return final_list[:350], f"✅ 成功聚合多源頭數據 (共 {len(final_list)} 檔)"

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
        # MA
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        # SAR (快速模擬: 趨勢向上且MACD紅柱)
        df['SAR_Bull'] = (df['Close'] > df['MA20']) & (df['MACD_Hist'] > 0)
        return df
    except:
        return pd.DataFrame()

# --- 3. 核心策略 (計分) ---
def check_miniko_strategy(stock_id, df):
    if df is None or len(df) < 30: return 0, []
    if df.isnull().values.any():
        df = df.fillna(method='ffill').fillna(method='bfill')

    today = df.iloc[-1]
    prev = df.iloc[-2]

    # 🔥 流動性過濾 🔥
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    if vol_ma5 == 0: vol_ma5 = 1
    is_volume_surge = today['Volume'] > (vol_ma5 * 1.5)
    
    min_volume = 1000000 # 1000張
    if today['Close'] > 500: min_volume = 500000
    
    # 沒量又沒爆量 -> 淘汰
    if (today['Volume'] < min_volume) and (not is_volume_surge):
        return 0, []

    score = 0
    reasons = []
    
    # ✅ A. 權證/爆量
    # 權證門檻：做多500萬 -> 估現貨 > 2000萬
    estimated_turnover = today['Close'] * today['Volume']
    is_warrant_whale = estimated_turnover > 20000000
    is_attacking = today['Close'] > prev['Close'] 
    
    if is_warrant_whale and is_attacking:
        score += 25
        reasons.append("🔥權證大戶(>500萬)")
    if is_volume_surge:
        score += 15
        reasons.append(f"爆量({int(today['Volume']/vol_ma5)}倍)")

    # ✅ B. 型態
    # 咕嚕咕嚕
    kd_low = today['K'] < 50
    k_hook = (today['K'] > prev['K'])
    if kd_low and k_hook and (today['Close'] > today['MA5']):
        score += 10
        reasons.append("咕嚕咕嚕")
    # 高檔整理
    max_k = df['K'].rolling(10).max().iloc[-1]
    if (max_k > 70) and (40 <= today['K'] <= 60):
        score += 10
        reasons.append("高檔盤整")

    # ✅ C. SOP (MACD + SAR + KD)
    macd_flip = (prev['MACD_Hist'] <= 0) and (today['MACD_Hist'] > 0)
    kd_cross = (prev['K'] < prev['D']) and (today['K'] > today['D'])
    sar_bull = today.get('SAR_Bull', False)
    
    if macd_flip and sar_bull and kd_cross:
        score += 30
        reasons.append("SOP三線合一")

    # ✅ D. 主力連買 (3~10天)
    recent_closes = df['Close'].iloc[-10:].values
    recent_opens = df['Open'].iloc[-10:].values
    consecutive = 0
    # 倒序檢查
    for i in range(len(recent_closes)-1, 0, -1):
        # 條件：收紅K 或 比昨天高
        if (recent_closes[i] >= recent_opens[i]) or (recent_closes[i] > recent_closes[i-1]):
            consecutive += 1
        else:
            break
    
    if 3 <= consecutive <= 10:
        score += 20
        reasons.append(f"主力連買{consecutive}天")

    return score, reasons

# --- 4. 執行介面 ---

st.info("💡 聚合「Yahoo上市/上櫃 + HiStock」多重資料源，執行「Miniko 嚴選策略」與菁英排序。")

col1, col2 = st.columns([3, 1])
with col1:
    status_msg = st.empty()
    status_msg.write("Miniko 準備就緒...")
with col2:
    scan_btn = st.button("🚀 啟動渦輪掃描", type="primary")

if scan_btn:
    with st.spinner("1. 正在從多個來源獲取熱門股名單..."):
        top_stocks_info, source_msg = get_market_stocks()
    st.caption(f"{source_msg}")

    # --- 批次下載 ---
    tickers = [x['code'] for x in top_stocks_info]
    
    status_text = st.empty()
    status_text.text(f"2. 正在一次性下載 {len(tickers)} 檔股票數據...")
    progress_bar = st.progress(0)
    
    try:
        # 下載數據
        bulk_data = yf.download(tickers, period="3mo", group_by='ticker', threads=True, progress=False)
        
        candidates = []
        total_stocks = len(tickers)
        
        for i, stock_info in enumerate(top_stocks_info):
            code = stock_info['code']
            name = stock_info['name']
            
            try:
                # 兼容 yfinance 不同版本的資料結構
                if isinstance(bulk_data.columns, pd.MultiIndex):
                     df = bulk_data[code].copy()
                else:
                     # 只有一檔時的情況
                     df = bulk_data.copy()

                if df.empty or 'Close' not in df.columns or df['Close'].isnull().all():
                    continue
                    
                df = calculate_indicators(df)
                score, reasons = check_miniko_strategy(code, df)
                
                if score > 0:
                    latest_price = df['Close'].iloc[-1]
                    vol = df['Volume'].iloc[-1] / 1000
                    prev_close = df['Close'].iloc[-2]
                    pct_change = (latest_price - prev_close) / prev_close * 100
                    color = "🔴" if pct_change > 0 else "🟢"
                    
                    candidates.append({
                        "代號": code,
                        "名稱": name,
                        "現價": f"{latest_price:.2f} ({color} {pct_change:.1f}%)",
                        "成交量": f"{int(vol)}張",
                        "Miniko分數": score,
                        "入選理由": " + ".join(reasons)
                    })
            except Exception:
                continue 
            
            if i % 10 == 0:
                progress_bar.progress((i + 1) / total_stocks)
                status_text.text(f"3. AI 分析中... ({i}/{total_stocks})")

        progress_bar.progress(1.0)
        status_text.text("分析完成！")
        
        if candidates:
            df_candidates = pd.DataFrame(candidates)
            df_candidates = df_candidates.sort_values(by="Miniko分數", ascending=False)
            final_list = df_candidates.head(20).reset_index(drop=True)
            
            st.success(f"🎉 掃描完成！為您精選 Top 20 菁英股 (含權證/主力/爆量/SOP)")
            st.dataframe(final_list, use_container_width=True)
        else:
            st.warning("今日市況極度冷清，未發現符合條件標的。")
            
    except Exception as e:
        st.error(f"數據下載異常: {e}")
