import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
from scipy.signal import argrelextrema

# --- 網頁設定 ---
st.set_page_config(page_title="Miniko AI 戰略指揮室", page_icon="⚡", layout="wide")

# --- CSS 美化 ---
st.markdown("""
<style>
    .big-font { font-size:28px !important; font-weight: bold; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dee2e6; }
    .buy-signal { border-left: 5px solid #28a745; background-color: #d4edda; padding: 15px; border-radius: 5px; }
    .sell-signal { border-left: 5px solid #dc3545; background-color: #f8d7da; padding: 15px; border-radius: 5px; }
    .neutral-signal { border-left: 5px solid #6c757d; background-color: #e2e3e5; padding: 15px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-font">⚡ Miniko AI 戰略指揮室 (V17.0)</p>', unsafe_allow_html=True)

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 戰情設定")
    stock_id = st.text_input("輸入代號 (如 2330, 3231)", value="2330")
    run_btn = st.button("🚀 啟動戰略分析", type="primary")
    st.markdown("---")
    st.info("💡 V17 特點：新增 3 大黃金切割點位與詳細進場解說。")

# --- 核心函數 (沿用 V16 防斷線機制) ---

def safe_fetch(ticker_obj, period, interval):
    try:
        df = ticker_obj.history(period=period, interval=interval)
        time.sleep(0.3) # 防斷線緩衝
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_data(symbol):
    try:
        if not symbol.endswith(".TW") and not symbol.endswith(".TWO"):
            test_symbol = symbol + ".TW"
        else:
            test_symbol = symbol

        ticker = yf.Ticker(test_symbol)
        
        # 1. 日線 (大趨勢)
        df_d = safe_fetch(ticker, "1y", "1d")
        if df_d.empty:
            test_symbol = symbol + ".TWO"
            ticker = yf.Ticker(test_symbol)
            df_d = safe_fetch(ticker, "1y", "1d")
        
        if df_d.empty: return None, None, None, None

        # 2. 60分 (波段)
        df_60 = safe_fetch(ticker, "1mo", "60m")
        # 3. 30分 (進場)
        df_30 = safe_fetch(ticker, "5d", "30m")

        return df_d, df_60, df_30, test_symbol
    except:
        return None, None, None, None

def calc_indicators(df):
    if df is None or df.empty: return df
    # MA
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    # KD
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    df['RSV'] = df['RSV'].fillna(50)
    k, d = [50], [50]
    for rsv in df['RSV']:
        k.append(k[-1]*2/3 + rsv*1/3)
        d.append(d[-1]*2/3 + k[-1]*1/3)
    df['K'] = k[1:]
    return df

def get_fibonacci(df):
    # 抓近半年高低點
    high = df['High'].iloc[-120:].max()
    low = df['Low'].iloc[-120:].min()
    diff = high - low
    
    # 計算回檔支撐 (由高往下算)
    sup_0382 = high - (diff * 0.382)
    sup_0500 = high - (diff * 0.5)
    sup_0618 = high - (diff * 0.618)
    
    return high, low, sup_0382, sup_0500, sup_0618

def get_wave_code(price, ma60, ma20, k_val):
    w1 = "3" if price > ma60 else "C"
    w2 = "iii" if price > ma20 else "iv"
    w3 = "b" if k_val < 50 else "c"
    return f"{w1}-{w2}-{w3}"

# --- 主程式 ---
if run_btn:
    with st.spinner(f"正在部署 {stock_id} 戰略數據..."):
        df_d, df_60, df_30, symbol = get_data(stock_id)
        
        if df_d is None:
            st.error("❌ 連線逾時，請等待 5 秒後重試。")
        else:
            # 計算
            df_d = calc_indicators(df_d)
            if df_60 is not None: df_60 = calc_indicators(df_60)
            if df_30 is not None: df_30 = calc_indicators(df_30)
            
            # 數據提取
            price = df_d['Close'].iloc[-1]
            ma20 = df_d['MA20'].iloc[-1]
            ma60 = df_d['MA60'].iloc[-1]
            k_val = df_d['K'].iloc[-1]
            
            # 費波納契
            high_p, low_p, fib_0382, fib_0500, fib_0618 = get_fibonacci(df_d)
            wave_code = get_wave_code(price, ma60, ma20, k_val)
            
            # --- AI 戰術邏輯 (V17 核心) ---
            trend = "多頭" if price > ma60 else "空頭"
            signal_class = "neutral-signal"
            
            if trend == "多頭":
                if k_val < 30:
                    strategy = "強力做多 (Long)"
                    desc = "主升段回檔至超賣區，配合費波納契支撐，是極佳的低接機會。"
                    entry_guide = f"""
                    1. **第一筆單 (30%)**: 現價 {price} 可先試單。
                    2. **第二筆單 (70%)**: 掛在 0.618 黃金支撐 {fib_0618:.2f} 附近。
                    3. **觀察訊號**: 等待 30分K 出現「紅K吞噬」確認止跌。
                    """
                    target = high_p
                    stop = fib_0618 * 0.95
                    signal_class = "buy-signal"
                elif k_val > 70:
                    strategy = "多頭過熱 (Wait)"
                    desc = "趨勢雖偏多，但短線乖離過大，不建議追價，等待回測 0.382。"
                    entry_guide = f"目前不宜進場，建議掛單在 {fib_0382:.2f} 等待接回。"
                    target = high_p * 1.1
                    stop = ma20
                else:
                    strategy = "多頭震盪 (Hold)"
                    desc = "多頭格局不變，持股續抱，空手者觀望。"
                    entry_guide = "區間操作，低買高賣。"
                    target = high_p
                    stop = ma60
            else: # 空頭
                if k_val > 70:
                    strategy = "強力做空 (Short)"
                    desc = "空頭反彈至壓力區，KD高檔鈍化，是放空良機。"
                    entry_guide = f"""
                    1. **進場點**: 反彈至 MA20 ({ma20:.2f}) 附近空。
                    2. **目標**: 下看前波低點 {low_p:.2f}。
                    3. **防守**: 站上 MA60 停損。
                    """
                    target = low_p
                    stop = ma60
                    signal_class = "sell-signal"
                else:
                    strategy = "空頭下跌中 (Wait)"
                    desc = "正在下跌，不要隨意接刀，等待止跌訊號。"
                    entry_guide = "空手者保持觀望，勿搶反彈。"
                    target = low_p * 0.9
                    stop = price * 1.05

            # --- UI 顯示 ---
            st.success(f"✅ 代號: {symbol} | 現價: {price} | 趨勢: {trend}")
            
            # 1. 戰術面板
            st.markdown(f"""
            <div class="{signal_class}">
                <h3>🤖 AI 指令: {strategy}</h3>
                <p><b>波浪座標:</b> {wave_code}</p>
                <p>{desc}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # 2. 詳細進場說明
            with st.expander("📖 查看詳細 AI 進場/出場 戰術說明", expanded=True):
                st.markdown(f"#### 🎯 操作建議")
                st.markdown(entry_guide)
                col_t1, col_t2 = st.columns(2)
                col_t1.metric("🏁 目標獲利價", f"{target:.2f}")
                col_t2.metric("🛑 停損防守價", f"{stop:.2f}")

            # 3. 三大黃金費波納契點位
            st.subheader("📏 費波納契 (Fibonacci) 三大關卡")
            f1, f2, f3 = st.columns(3)
            f1.metric("壓力/淺回檔 (0.382)", f"{fib_0382:.2f}", delta="第一關")
            f2.metric("中性分界 (0.500)", f"{fib_0500:.2f}", delta="第二關")
            f3.metric("黃金支撐 (0.618)", f"{fib_0618:.2f}", delta="強力防守")
            
            # 4. 圖表
            st.markdown("---")
            tab1, tab2 = st.tabs(["日線趨勢", "60分波段"])
            with tab1:
                st.line_chart(df_d['Close'])
            with tab2:
                if df_60 is not None:
                    st.line_chart(df_60['Close'])
