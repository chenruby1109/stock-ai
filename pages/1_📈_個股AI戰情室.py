import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time

# --- 網頁設定 ---
st.set_page_config(page_title="個股 AI 戰情室", page_icon="📈", layout="wide")

# --- CSS 美化 ---
st.markdown("""
<style>
    .big-font { font-size:26px !important; font-weight: bold; }
    .buy-card { border-left: 8px solid #28a745; background-color: #d4edda; padding: 20px; border-radius: 5px; color: #155724; }
    .super-buy-card { border-left: 8px solid #ffc107; background-color: #fff3cd; padding: 20px; border-radius: 5px; color: #856404; border: 2px solid #ffeeba; }
    .sell-card { border-left: 8px solid #dc3545; background-color: #f8d7da; padding: 20px; border-radius: 5px; color: #721c24; }
    .neutral-card { border-left: 8px solid #6c757d; background-color: #e2e3e5; padding: 20px; border-radius: 5px; color: #383d41; }
    .tag { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 14px; margin-right: 5px; font-weight: bold; }
    .tag-blue { background-color: #e3f2fd; color: #0d47a1; border: 1px solid #90caf9; }
    .tag-red { background-color: #fce4ec; color: #c2185b; border: 1px solid #f48fb1; }
    .tag-gold { background-color: #fff9c4; color: #fbc02d; border: 1px solid #fff176; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-font">📈 Miniko AI 戰情室 (V22.0 全方位獵手)</p>', unsafe_allow_html=True)
st.markdown("策略邏輯：**只要滿足「條件一 (型態)」或「條件二 (指標)」任一項，即觸發買訊。**")

# --- 側邊欄 ---
with st.sidebar:
    st.header("🔍 股票設定")
    stock_id = st.text_input("輸入代號 (如 2330, 3231)", value="2330")
    run_btn = st.button("🚀 啟動 AI 掃描", type="primary")

# --- 核心工具 ---
def get_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session

def safe_fetch(symbol, period, interval, session):
    try:
        if not symbol.endswith(".TW") and not symbol.endswith(".TWO"):
            symbol += ".TW"
        ticker = yf.Ticker(symbol, session=session)
        df = ticker.history(period=period, interval=interval)
        time.sleep(0.3)
        if df.empty:
            symbol = symbol.replace(".TW", ".TWO")
            ticker = yf.Ticker(symbol, session=session)
            df = ticker.history(period=period, interval=interval)
        return df, symbol
    except:
        return pd.DataFrame(), symbol

# --- 指標計算 (嚴格遵守您的公式) ---

def calculate_indicators(df):
    # 1. 均線與波動
    df['MA60'] = df['Close'].rolling(60).mean()
    
    # 計算近10日波動率 (最高-最低 / 最低)
    recent = df['High'].rolling(10).max() - df['Low'].rolling(10).min()
    df['Volatility'] = (recent / df['Low'].rolling(10).min()) * 100

    # 2. KD (9,3,3)
    high_9 = df['High'].rolling(9).max()
    low_9 = df['Low'].rolling(9).min()
    rsv = (df['Close'] - low_9) / (high_9 - low_9) * 100
    rsv = rsv.fillna(50)
    k, d = [50], [50]
    for val in rsv:
        k_val = k[-1]*2/3 + val*1/3
        k.append(k_val)
        d.append(d[-1]*2/3 + k_val*1/3)
    df['K'] = k[1:]
    df['D'] = d[1:]

    # 3. MACD (DIF=12-26, MACD=DIF_9, OSC=DIF-MACD)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD_Signal'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['OSC'] = df['DIF'] - df['MACD_Signal']

    # 4. Parabolic SAR
    high, low = df['High'], df['Low']
    sar = [low.iloc[0]]
    bull = True
    ep = high.iloc[0]
    acc = 0.02
    for i in range(1, len(df)):
        prev_sar = sar[-1]
        curr_sar = prev_sar + acc * (ep - prev_sar)
        if bull:
            if low.iloc[i] < curr_sar:
                bull = False
                curr_sar = ep
                ep = low.iloc[i]
                acc = 0.02
            else:
                if high.iloc[i] > ep:
                    ep, acc = high.iloc[i], min(acc + 0.02, 0.2)
        else:
            if high.iloc[i] > curr_sar:
                bull = True
                curr_sar = ep
                ep = high.iloc[i]
                acc = 0.02
            else:
                if low.iloc[i] < ep:
                    ep, acc = low.iloc[i], min(acc + 0.02, 0.2)
        sar.append(curr_sar)
    df['SAR'] = sar
    df['SAR_Bull'] = df['Close'] > df['SAR']
    
    return df

# --- 主程式 ---
if run_btn:
    with st.spinner(f"AI 正在對 {stock_id} 進行雙重策略檢測..."):
        session = get_session()
        df, real_symbol = safe_fetch(stock_id, "1y", "1d", session)
        
        if df.empty:
            st.error("❌ 抓取失敗，請稍後再試。")
        else:
            df = calculate_indicators(df)
            
            # 取得最新數據
            today = df.iloc[-1]
            prev = df.iloc[-2]
            
            # --- 變數準備 ---
            price = today['Close']
            ma60 = today['MA60']
            
            # KD
            k_now = today['K']
            d_now = today['D']
            k_prev = prev['K']
            d_prev = prev['D']
            kd_gold_cross = k_prev < d_prev and k_now > d_now
            
            # MACD
            osc_now = today['OSC']
            osc_prev = prev['OSC']
            osc_flip_up = osc_prev < 0 and osc_now > 0 # 負轉正
            osc_flip_down = osc_prev > 0 and osc_now < 0 # 正轉負
            
            # SAR
            sar_bull = today['SAR_Bull']
            
            # 波動率 (近10日)
            volatility = today['Volatility']
            
            # 歷史高K值 (檢查有沒有從高檔下來)
            high_k_recent = df['K'].iloc[-30:-5].max() 
            
            # --- 核心邏輯：收集所有買進理由 ---
            buy_reasons = []
            sell_reasons = []
            tags = []

            # ==========================================
            # 🔍 條件一：型態學 (咕嚕咕嚕 & 強勢整理)
            # ==========================================
            
            # A. 底部咕嚕咕嚕 (蓄勢待發)
            # 邏輯: K值低 (<30) + 波動小 (<6%)
            if k_now < 30 and volatility < 6:
                buy_reasons.append("🫧 底部咕嚕咕嚕 (蓄勢待發)：低檔鈍化且籌碼穩定，像在冒泡泡。")
                tags.append(("底部冒泡", "blue"))
            
            # B. 高檔強勢整理 (以盤代跌)
            # 邏輯: 多頭(>MA60) + K值回落(30-55) + 波動小 + 之前K在高檔
            if price > ma60 and 30 < k_now < 55 and volatility < 7 and high_k_recent > 70:
                buy_reasons.append("⚓️ 高檔強勢整理：KD修正但價格抗跌，主力洗盤訊號。")
                tags.append(("強勢整理", "blue"))

            # ==========================================
            # 🔍 條件二：指標進出場 (MACD / SAR / KD)
            # ==========================================
            
            # C. 指標完美共振 (MACD正 + SAR多 + KD金叉)
            if osc_now > 0 and sar_bull and kd_gold_cross:
                buy_reasons.append("🚀 指標完美共振：MACD正值 + SAR多方 + KD黃金交叉，強力訊號！")
                tags.append(("三線共振", "gold"))
            
            # D. OSC 翻紅 (單一指標買點)
            elif osc_flip_up:
                buy_reasons.append("📈 MACD 動能轉強：OSC 由負轉正。")
                tags.append(("OSC翻紅", "red"))

            # ==========================================
            # 🔍 賣出條件檢查
            # ==========================================
            if osc_flip_down:
                sell_reasons.append("MACD OSC 由正轉負。")
            if not sar_bull and k_now < d_now and k_now > 70:
                sell_reasons.append("SAR 轉空 且 KD 高檔死叉。")

            # --- 最終判定與顯示 ---
            st.success(f"✅ 代號: {real_symbol} | 現價: {price:.2f}")
            
            # 顯示標籤
            tag_html = ""
            for t_text, t_color in tags:
                tag_html += f'<span class="tag tag-{t_color}">{t_text}</span>'
            if tag_html: st.markdown(tag_html, unsafe_allow_html=True)
            st.write("") # Spacer

            # 決定卡片樣式
            if len(buy_reasons) >= 2:
                # 滿足兩個以上條件 -> 超級買點
                st.markdown(f"""
                <div class="super-buy-card">
                    <h2 style="margin:0;">🔥 AI 判定: 強力買進 (雙重確認)</h2>
                    <p style="font-size:18px; margin-top:10px;"><b>觸發條件：</b></p>
                    <ul>{''.join([f'<li>{r}</li>' for r in buy_reasons])}</ul>
                </div>
                """, unsafe_allow_html=True)
                
            elif len(buy_reasons) == 1:
                # 滿足一個條件 -> 買點
                st.markdown(f"""
                <div class="buy-card">
                    <h2 style="margin:0;">📈 AI 判定: 買入訊號</h2>
                    <p style="font-size:18px; margin-top:10px;"><b>觸發條件：</b></p>
                    <ul><li>{buy_reasons[0]}</li></ul>
                </div>
                """, unsafe_allow_html=True)
                
            elif len(sell_reasons) > 0:
                # 賣出訊號
                st.markdown(f"""
                <div class="sell-card">
                    <h2 style="margin:0;">📉 AI 判定: 賣出訊號</h2>
                    <p style="font-size:18px; margin-top:10px;"><b>觸發條件：</b></p>
                    <ul>{''.join([f'<li>{r}</li>' for r in sell_reasons])}</ul>
                </div>
                """, unsafe_allow_html=True)
                
            else:
                # 觀望
                st.markdown(f"""
                <div class="neutral-card">
                    <h2 style="margin:0;">👀 AI 判定: 觀望</h2>
                    <p>目前未出現明確的「咕嚕咕嚕」型態或「指標共振」訊號。</p>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")
            
            # 數據儀表板
            c1, c2, c3 = st.columns(3)
            
            # KD
            c1.markdown("### 📉 KD 值")
            c1.metric("K", f"{k_now:.1f}", delta="金叉" if k_now>d_now else "死叉")
            if k_now < 30: c1.info("狀態: 低檔 (可能冒泡)")
            elif 30 < k_now < 55: c1.warning("狀態: 中段 (觀察整理)")
            else: c1.error("狀態: 高檔")
            
            # MACD
            c2.markdown("### 📊 MACD (OSC)")
            c2.metric("OSC", f"{osc_now:.2f}", delta="翻紅" if osc_flip_up else "翻綠" if osc_flip_down else None)
            c2.caption(f"DIF: {today['DIF']:.2f}")
            
            # SAR & 波動
            c3.markdown("### 🛡️ SAR / 波動")
            sar_txt = "🟢 多方" if sar_bull else "🔴 空方"
            c3.metric("SAR", sar_txt)
            c3.caption(f"波動率: {volatility:.1f}%")
            if volatility < 6: c3.success("✨ 波動壓縮中")

            # 圖表
            st.markdown("---")
            st.line_chart(df[['Close', 'MA60']])
            st.bar_chart(df['OSC'].tail(60))
