import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

# --- 網頁設定 ---
st.set_page_config(page_title="Miniko AI 智能選股", page_icon="📈")

# --- 標題區 ---
st.title("⚡ Miniko AI 智能選股 (穩定版)")
st.markdown("輸入代號，AI 立即幫您計算波浪座標與買賣點。")

# --- 側邊欄輸入 ---
stock_id = st.text_input("請輸入股票代號 (例如: 8028, 2330)", value="8028")
run_btn = st.button("🚀 開始 AI 運算")

# --- 核心工具：使用 yfinance 套件 ---
def get_data_safe(symbol):
    try:
        # 自動補上 .TW
        if not symbol.endswith(".TW") and not symbol.endswith(".TWO"):
            # 先試試看 .TW
            test_ticker = yf.Ticker(symbol + ".TW")
            hist = test_ticker.history(period="5d")
            if not hist.empty:
                return hist, symbol + ".TW"
            else:
                # 沒資料，改試 .TWO
                return yf.Ticker(symbol + ".TWO").history(period="1mo", interval="60m"), symbol + ".TWO"
        else:
            return yf.Ticker(symbol).history(period="1mo", interval="60m"), symbol

    except Exception as e:
        st.error(f"連線錯誤: {e}")
        return None, symbol

def analyze_stock(df):
    if df is None or df.empty: return None
    
    # 簡單的技術指標計算
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

# --- 主程式 ---
if run_btn:
    with st.spinner(f'正在連線抓取 {stock_id} ...'):
        # 1. 抓取資料
        df, real_symbol = get_data_safe(stock_id)
        
        if df is None or df.empty:
            st.error(f"❌ 找不到 {stock_id} 的資料，請確認代號正確 (或是剛開盤資料延遲)。")
        else:
            # 2. 運算
            df = analyze_stock(df)
            price = df['Close'].iloc[-1]
            k_val = df['K'].iloc[-1]
            ma60 = df['MA60'].iloc[-1]
            
            # 3. 判斷
            direction = "觀望"
            color = "gray"
            if price > ma60 and k_val < 30:
                direction = "🚀 強力做多"
                color = "green"
            elif price < ma60 and k_val > 70:
                direction = "🐻 強力做空"
                color = "red"
            
            # 4. 顯示結果
            st.success(f"成功抓取: {real_symbol} | 現價: {price:.2f}")
            col1, col2 = st.columns(2)
            col1.metric("AI 指令", direction)
            col2.metric("KD 值", f"{k_val:.1f}")
            
            # 畫圖
            st.line_chart(df['Close'])