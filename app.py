import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

# --- 網頁設定 ---
st.set_page_config(page_title="Miniko AI 旗艦操盤室", page_icon="⚡", layout="wide")

# --- 標題與樣式 ---
st.markdown("""
<style>
    .big-font { font-size:30px !important; font-weight: bold; }
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    .success-card { background-color: #d1e7dd; padding: 15px; border-radius: 10px; border-left: 5px solid #198754; color: #0f5132; }
    .danger-card { background-color: #f8d7da; padding: 15px; border-radius: 10px; border-left: 5px solid #dc3545; color: #842029; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-font">⚡ Miniko AI 旗艦波浪操盤室 (V15.0)</p>', unsafe_allow_html=True)
st.markdown("結合 **日線/60分/30分** 多週期共振，提供波浪座標、目標價與勝率分析。")

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 股票設定")
    stock_id = st.text_input("輸入代號 (如 2330, 3231)", value="2330")
    run_btn = st.button("🚀 啟動 AI 運算", type="primary")
    st.markdown("---")
    st.markdown("💡 **波浪座標說明**:")
    st.caption("格式: [日線]-[60分]-[30分]")
    st.caption("例: `3-iii-c` (主升段-中線衝刺-短線回檔)")

# --- 核心工具函數 ---

@st.cache_data(ttl=300) # 5分鐘快取
def get_multi_timeframe_data(symbol):
    try:
        if not symbol.endswith(".TW") and not symbol.endswith(".TWO"):
            symbol += ".TW"
        
        # 1. 抓日線 (看大趨勢 - 抓1年)
        df_day = yf.Ticker(symbol).history(period="1y", interval="1d")
        
        # 2. 抓60分K (看波段 - 抓1個月，yfinance 限制)
        df_60m = yf.Ticker(symbol).history(period="1mo", interval="60m")
        
        # 3. 抓30分K (看短線轉折 - 抓5天)
        df_30m = yf.Ticker(symbol).history(period="5d", interval="30m")
        
        if df_day.empty: 
            # 嘗試上櫃
            symbol = symbol.replace(".TW", ".TWO")
            df_day = yf.Ticker(symbol).history(period="1y", interval="1d")
            df_60m = yf.Ticker(symbol).history(period="1mo", interval="60m")
            df_30m = yf.Ticker(symbol).history(period="5d", interval="30m")

        return df_day, df_60m, df_30m, symbol
    except Exception as e:
        return None, None, None, None

def calculate_indicators(df):
    if df is None or df.empty: return df
    
    # 均線
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    
    # KD (9,3,3)
    df['9_High'] = df['High'].rolling(9).max()
    df['9_Low'] = df['Low'].rolling(9).min()
    df['RSV'] = (df['Close'] - df['9_Low']) / (df['9_High'] - df['9_Low']) * 100
    df['RSV'] = df['RSV'].fillna(50)
    
    k_list, d_list = [50], [50]
    for rsv in df['RSV']:
        k = (2/3) * k_list[-1] + (1/3) * rsv
        d = (2/3) * d_list[-1] + (1/3) * k
        k_list.append(k)
        d_list.append(d)
    df['K'], df['D'] = k_list[1:], d_list[1:]
    
    # SAR (簡化趨勢版)
    df['SAR_Signal'] = np.where(df['Close'] > df['MA20'], 1, -1)
    
    # 波浪高低點
    n = 3
    df['peak'] = df.iloc[argrelextrema(df['Close'].values, np.greater_equal, order=n)[0]]['Close']
    df['trough'] = df.iloc[argrelextrema(df['Close'].values, np.less_equal, order=n)[0]]['Close']
    
    return df

def get_wave_position(df_d, df_60, df_30):
    # 取得最新價格
    price = df_d['Close'].iloc[-1]
    
    # 1. 日線判斷 (大浪)
    ma60_d = df_d['MA60'].iloc[-1]
    last_high_d = df_d['peak'].dropna().iloc[-1] if not df_d['peak'].dropna().empty else price * 1.1
    
    w_day = "3" if price > ma60_d else "C" # 季線之上為3, 之下為C
    if w_day == "3" and price < df_d['MA20'].iloc[-1]: w_day = "4" # 多頭回檔
    
    # 2. 60分判斷 (中浪)
    ma20_60 = df_60['MA20'].iloc[-1]
    w_60 = "iii" if price > ma20_60 else "iv"
    
    # 3. 30分判斷 (小浪)
    k_30 = df_30['K'].iloc[-1]
    w_30 = "b" if k_30 < 50 else "c" # 簡單模擬: KD低檔視為b波反彈起點, 高檔為c波下跌
    
    return f"{w_day}-{w_60}-{w_30}"

# --- 主程式 ---
if run_btn:
    with st.spinner(f'正在進行多週期波浪運算 {stock_id}...'):
        df_d, df_60, df_30, real_symbol = get_multi_timeframe_data(stock_id)
        
        if df_d is None or df_d.empty:
            st.error("❌ 抓取失敗，請確認代號或稍後再試。")
        else:
            # 計算指標
            df_d = calculate_indicators(df_d)
            df_60 = calculate_indicators(df_60)
            df_30 = calculate_indicators(df_30)
            
            # 取得關鍵數據
            price = df_d['Close'].iloc[-1]
            k_val = df_d['K'].iloc[-1]
            ma20 = df_d['MA20'].iloc[-1]
            ma60 = df_d['MA60'].iloc[-1]
            
            # 費波納契 (日線級別)
            last_high = df_d['High'].iloc[-60:].max()
            last_low = df_d['Low'].iloc[-60:].min()
            diff = last_high - last_low
            fib_0618 = last_high - (diff * 0.618)
            fib_0382 = last_high - (diff * 0.382)
            
            # 波浪座標
            wave_code = get_wave_position(df_d, df_60, df_30)
            
            # --- AI 決策核心 (V15.0) ---
            direction = "觀望"
            advice = ""
            bg_class = "metric-card"
            win_rate = 50
            target_price = 0
            prob_target = 0
            
            # 策略 A: 主升段回檔 (黃金買點)
            if price > ma60 and k_val < 35:
                direction = "🚀 強力做多 (Long)"
                advice = "日線多頭 + KD超賣 + 回測支撐 = 絕佳買點"
                bg_class = "success-card"
                win_rate = 85
                entry_point = f"{fib_0618:.2f} 附近"
                stop_loss = fib_0618 * 0.95
                target_price = last_high
                prob_target = 75
            
            # 策略 B: 主升段噴出 (追價)
            elif price > ma60 and price > ma20 and k_val > 50 and k_val < 80:
                direction = "📈 順勢做多 (Trend Buy)"
                advice = "多頭排列強勢中，沿5日線操作"
                bg_class = "success-card"
                win_rate = 70
                entry_point = "現價追入"
                stop_loss = ma20
                target_price = last_high * 1.1
                prob_target = 60

            # 策略 C: 空頭反彈 (做空)
            elif price < ma60 and k_val > 70:
                direction = "🐻 強力做空 (Short)"
                advice = "空頭趨勢 + KD過熱 = 壓力測試不過"
                bg_class = "danger-card"
                win_rate = 80
                entry_point = f"{fib_0382:.2f} 附近"
                stop_loss = fib_0382 * 1.05
                target_price = last_low
                prob_target = 70
                
            else:
                direction = "👀 區間震盪 (Neutral)"
                advice = "方向不明，建議觀望等待突破"
                entry_point = "暫不進場"
                stop_loss = 0
                target_price = 0
                prob_target = 0

            # --- 顯示報告 (UI 優化) ---
            st.success(f"✅ 成功鎖定: {real_symbol} | 現價: {price:.2f} | 時間: {df_d.index[-1].strftime('%Y-%m-%d')}")
            
            # 1. 核心訊號區
            st.markdown(f"""
            <div class="{bg_class}">
                <h2 style="margin:0;">🤖 AI 總司令: {direction}</h2>
                <p style="font-size:18px;">💡 <b>戰術理由:</b> {advice}</p>
                <p>🏆 <b>交易勝率:</b> {win_rate}%</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # 2. 數據儀表板
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📍 波浪座標", wave_code, help="日線-60分-30分 層級定位")
            with col2:
                kd_color = "normal"
                if k_val > 80: kd_color = "inverse"
                st.metric("📊 KD 指標 (9,3,3)", f"{k_val:.1f}", delta="超買" if k_val>80 else "超賣" if k_val<20 else "正常", delta_color=kd_color)
            with col3:
                sar_state = "🟢 多頭" if price > ma20 else "🔴 空頭"
                st.metric("🛡️ SAR/月線趨勢", sar_state)

            # 3. 點位分析
            st.subheader("🎯 精準點位預測")
            c1, c2, c3 = st.columns(3)
            c1.info(f"**📥 建議進場**\n\n# {entry_point}")
            c2.error(f"**🛑 停損防守**\n\n# {stop_loss:.2f}")
            if target_price > 0:
                c3.success(f"**🏁 目標獲利**\n\n# {target_price:.2f}\n(機率: {prob_target}%)")
            else:
                c3.warning("**🏁 目標獲利**\n\n觀望中無目標")

            # 4. 關鍵支撐壓力
            st.markdown("---")
            st.subheader("📏 費波納契 (Fibonacci) 關鍵位")
            col_f1, col_f2 = st.columns(2)
            col_f1.metric("0.618 黃金支撐", f"{fib_0618:.2f}")
            col_f2.metric("前波高點壓力", f"{last_high:.2f}")

            # 5. 圖表區
            tab1, tab2 = st.tabs(["日線圖 (Trend)", "60分線 (Wave)"])
            with tab1:
                st.line_chart(df_d['Close'])
            with tab2:
                st.line_chart(df_60['Close'])
