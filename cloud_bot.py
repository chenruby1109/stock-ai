# ===============================================
# 🛠️ 工具函式修正：支援多重時間框架 (Daily, 60m, Weekly)
# ===============================================
def get_data(symbol, period="1y", interval="1d"):
    """
    獲取指定時間頻率的K線數據
    預設: 日線 (1d/1y)
    支援: 60分K (60m/1mo), 週線 (1wk/2y)
    """
    try:
        # 嘗試上市
        ticker = yf.Ticker(symbol + ".TW")
        df = ticker.history(period=period, interval=interval)
        
        # 如果上市抓不到，嘗試上櫃
        if df.empty:
            ticker = yf.Ticker(symbol + ".TWO")
            df = ticker.history(period=period, interval=interval)
        
        if df.empty: return None
        return df
    except: return None

# ==========================================
# 🅱️ 模式 B: 盤中哨兵 (全功能戰略版 - 含MTF多週期分析)
# ==========================================
def run_monitor():
    print("👀 Miniko 盤中哨兵模式啟動 (已校正 UTC+8)...")
    print("🚀 功能: [即時訊號] + [10:20/12:00 戰報] + [13:31 收盤建議]")
    print("📈 升級: [17:01] 包含 日線/60分K/週線 完整多週期分析")
    
    alert_history = {} 
    
    schedule_tasks = {
        "10:20": "strategy",
        "12:00": "strategy",
        "13:31": "closing",
        "17:01": "chips_mtf"  # 更新任務名稱，代表多週期分析
    }
    scheduled_report_sent = {t: False for t in schedule_tasks}

    while True: 
        now_tw = datetime.utcnow() + timedelta(hours=8)
        now_str = now_tw.strftime('%H:%M')
        weekday = now_tw.weekday()

        # 工作日與時間判斷
        is_working_day = (0 <= weekday <= 4)
        is_active_hours = is_working_day and (8 <= now_tw.hour <= 17)
        is_trading_hours = is_working_day and (
            (now_tw.hour == 9) or 
            (now_tw.hour > 9 and now_tw.hour < 13) or 
            (now_tw.hour == 13 and now_tw.minute <= 30)
        )

        # 休眠判斷
        if not is_active_hours:
            print(f"\r💤 [{now_str}] 休市中 (Miniko 下班)...", end="")
            if now_str == "00:00":
                for t in schedule_tasks: scheduled_report_sent[t] = False
            time.sleep(60) 
            continue 

        # ================= 工作時段邏輯 =================
        status_msg = "交易中" if is_trading_hours else "盤後待命"
        print(f"\r🔄 [{now_str}] {status_msg} - 監控掃描中...", end="")
        
        # --- 🕒 定時報告處理 ---
        if now_str in schedule_tasks and not scheduled_report_sent[now_str]:
            report_type = schedule_tasks[now_str]
            print(f"\n⏰ 時間到 ({now_str})！正在生成 {report_type} 報告...")
            
            report_content = ""
            # 設定標題
            if report_type == "strategy":
                report_content = f"🔔 <b>Miniko {now_str} 盤中戰略推演</b> 🔔\n\n"
            elif report_type == "closing":
                report_content = f"🌅 <b>Miniko 13:31 收盤定一定心丸</b> 🌅\n\n"
            elif report_type == "chips_mtf":
                report_content = f"🥡 <b>Miniko 17:01 全方位多週期戰報</b> 🥡\n<i>(日線/60分K/週線 交叉分析)</i>\n\n"

            has_data = False

            for code, name in WATCH_LIST.items():
                try:
                    # 1. 基礎日線資料 (所有報告都需要)
                    df_day = get_data(code, period="1y", interval="1d")
                    if df_day is None: continue
                    df_day = calc_indicators(df_day)
                    today = df_day.iloc[-1]
                    
                    report_content += f"<b>📌 {name} ({code})</b>\n"
                    
                    # 2. 根據報告類型生成內容
                    if report_type == "strategy":
                        strat = analyze_strategy(df_day)
                        report_content += f"🛒 建議買點: {strat['buy_agg']:.1f}(激) / {strat['buy_con']:.1f}(穩)\n"
                        report_content += f"🎲 預估勝率: {strat['win_rate']}%\n"
                        report_content += f"🌊 目前趨勢: {'多頭' if today['Close']>today['MA20'] else '整理/空頭'}\n"

                    elif report_type == "closing":
                        strat = analyze_strategy(df_day)
                        report_content += f"💰 收盤確認: {today['Close']}\n"
                        report_content += f"🎯 明日佈局: 若回測 {strat['buy_con']:.1f} 可低接\n"
                        report_content += f"📊 停損建議: 跌破 {today['MA20']:.1f} 減碼\n"

                    elif report_type == "chips_mtf":
                        # === 獲取多週期數據 ===
                        # 60分K (看近1個月資料，分析短線轉折)
                        df_60m = get_data(code, period="1mo", interval="60m")
                        df_60m = calc_indicators(df_60m)
                        
                        # 週線 (看近2年資料，分析長線保護)
                        df_week = get_data(code, period="2y", interval="1wk")
                        df_week = calc_indicators(df_week)
                        
                        # === 分析邏輯 ===
                        # 日線分析 (籌碼與趨勢)
                        vol_ratio = today['Volume'] / today['Vol_MA5'] if today['Vol_MA5'] > 0 else 0
                        day_trend = "多頭排列" if today['MA20'] > today['MA60'] else "整理/偏空"
                        
                        # 60分K分析 (短線動能)
                        k60, d60 = df_60m.iloc[-1]['K'], df_60m.iloc[-1]['D']
                        short_signal = "短線過熱" if k60 > 80 else "短線超賣(反彈機會)" if k60 < 20 else "中性震盪"
                        
                        # 週線分析 (長線趨勢)
                        week_trend = "長線多頭" if df_week.iloc[-1]['Close'] > df_week.iloc[-1]['MA20'] else "長線需保守"
                        
                        # === 組合報告 ===
                        report_content += f"🔹 <b>日線結構</b>: {day_trend} | 量能 {vol_ratio:.1f}倍\n"
                        report_content += f"🔸 <b>60分短波</b>: KD({int(k60)}/{int(d60)}) -> {short_signal}\n"
                        report_content += f"📅 <b>週線格局</b>: {week_trend} (收盤 {df_week.iloc[-1]['Close']:.1f})\n"
                        
                        # 總結建議
                        if "多頭" in day_trend and "多頭" in week_trend:
                            advice = "🔥 <b>強力持有/拉回找買點</b>"
                        elif k60 < 20 and "多頭" in week_trend:
                            advice = "✅ <b>長多短空，黃金買點浮現</b>"
                        elif "空" in day_trend and "空" in week_trend:
                            advice = "⚠️ <b>趨勢偏空，反彈減碼</b>"
                        else:
                            advice = "👀 <b>區間震盪，高出低進</b>"
                        
                        report_content += f"💡 <b>AI總結</b>: {advice}\n"

                    report_content += f"------------------\n"
                    has_data = True
                except Exception as e:
                    print(f"Error generating report for {code}: {e}")
            
            if has_data:
                send_telegram(report_content)
            
            scheduled_report_sent[now_str] = True 
        
        # 每日重置 10:20 flag (雙重保險)
        if now_str == "09:00": scheduled_report_sent["10:20"] = False

        # --- 🔥 [即時] 訊號監控邏輯 (維持不變) ---
        if is_trading_hours:
            for code, name in WATCH_LIST.items():
                try:
                    # 冷卻檢查
                    last_sent_time = alert_history.get(code)
                    if last_sent_time and (datetime.utcnow() - last_sent_time).seconds < 3600:
                        continue

                    df = get_data(code) # 預設日線
                    if df is None: continue
                    df = calc_indicators(df)
                    signals = check_conditions(df, code, name)
                    
                    if signals:
                        today = df.iloc[-1]
                        prev = df.iloc[-2]
                        pct = ((today['Close'] - prev['Close']) / prev['Close']) * 100
                        icon = "🔺" if pct > 0 else "💚" if pct < 0 else "➖"
                        
                        msg = f"🚨 <b>Miniko 盤中訊號快報</b> 🚨\n\n"
                        msg += f"<b>{name} ({code})</b> 觸發條件！\n"
                        msg += f"💰 現價: {today['Close']} {icon} ({pct:+.2f}%)\n"
                        msg += f"📊 量能: {int(today['Volume']/1000)} 張\n"
                        msg += f"---------------------\n"
                        msg += "\n".join([f"{s}" for s in signals])
                        msg += f"\n---------------------\n"
                        msg += f"<i>(觸發時間: {now_str})</i>"
                        
                        send_telegram(msg)
                        alert_history[code] = datetime.utcnow()
                except: pass
            
        time.sleep(30)
