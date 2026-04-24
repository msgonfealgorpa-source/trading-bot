import ccxt, time, pandas as pd, ta, requests, datetime, os, sys, threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexMonsterBot:
    """
    بوت الوحش V11.0 (Quotex Binary Signals Edition)
    =================================================
    - مصدر البيانات: Binance API (Real-time)
    - الهدف: إشارات ثنائية (CALL/PUT) لمنصة كوتكس.
    - ميزة جديدة: التحقق الذاتي من دقة الإشارة لتفعيل Anti-Tilt.
    """
    
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return
        
        # ربط بـ Binance بدون مفاتيح (لأننا نقرأ البيانات فقط)
        self.exchange = ccxt.bybit({'enableRateLimit': True})
        
        # قائمة الأزواج المدعومة في كوتكس (مقسمة: بينانس -> كوتكس)
        self.QUOTEX_WHITELIST = {
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)', 
            'BNB/USDT': 'BNBUSD(t)', 'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 'DOGE/USDT': 'DOGEUSD(t)',
            'LTC/USDT': 'LTCUSD(t)', 'ADA/USDT': 'ADAUSD(t)',
            'MATIC/USDT': 'MATICUSD(t)', 'AVAX/USDT': 'AVAXUSD(t)',
            'DOT/USDT': 'DOTUSD(t)', 'LINK/USDT': 'LINKUSD(t)',
            'EUR/USDT': 'EURUSD(t)', 'GBP/USDT': 'GBPUSD(t)'
        }
        
        self.trade_lock = threading.Lock()
        self.day = None
        self.day_signals = 0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_signal_time = 0
        self.cooldown_sec = 120 # مهلة بين الإشارات لتجنب التشتيت
        
        self.streak_losses = 0
        self.tilt_until = 0
        
        self.stats = {
            'signals_sent': 0, 'scanned': 0, 'no_score': 0, 
            'whale_spotted': 0, 'choppy_blocked': 0, 'tilt_triggered': 0
        }
        
        self.CFG = {
            'max_daily_signals': 15,
            'min_score': 5,
            'score_gap': 2,
            'loop_sec': 15,
            'summary_every': 1800,
            # ======= إعدادات الحماية =======
            'tilt_after_losses': 3,
            'tilt_duration_min': 45,
            # ======= إعدادات رادار الحيتان =======
            'whale_level_1': 1.5,
            'whale_level_2': 3.0,
            'whale_level_3': 5.0,
            # ======= فلتر التذبذب (Bollinger Width) =======
            'min_bb_width_pct': 0.1 
        }
        
        self.tg("🔄 جاري التشغيل وربط بينانس...")
        try:
            self.exchange.load_markets()
            self.tg("✅ تم الربط بنجاح!")
        except Exception as e:
            self.tg(f"❌ فشل الربط: {e}")
            return

        msg  = "🐋 *بوت الوحش V11.0 (Quotex Edition)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "📡 مصدر البيانات: Binance Real-time\n"
        msg += "🎯 الهدف: إشارات كوتكس (Binary)\n"
        msg += "🚫 فلتر التذبذب (Chop Filter) مفعّل\n"
        msg += "🧠 تحقق ذاتي (Auto Anti-Tilt)\n"
        msg += f"📋 مراقبة {len(self.QUOTEX_WHITELIST)} زوج لكوتكس"
        self.tg(msg)

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except: pass

    def log(self, msg_en, notify=False, msg_ar=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg_en}") 
        if notify:
            self.tg(msg_ar if msg_ar else msg_en)

    # ================================================================
    #                         API & DATA
    # ================================================================
    
    def _ticker(self, sym): 
        try: return self.exchange.fetch_ticker(sym)
        except: return None

    def _df(self, sym, tf, limit=60):
        try:
            data = self.exchange.fetch_ohlcv(sym, tf, limit=limit)
            if not data or len(data) < limit: return None
            return pd.DataFrame(data, columns=['t','o','h','l','c','v'])
        except: return None
    
    # ================================================================
    #     🧠 استراتيجية الثنائيات + رادار الحيتان + فلتر التذبذب
    # ================================================================
    
    def _score_binary(self, sym):
        # نجلب فريم 1 دقيقة و 5 دقائق لضمان الدقة
        df_1m = self._df(sym, '1m', 50)
        df_5m = self._df(sym, '5m', 50)
        if df_1m is None or df_5m is None: return None, "No Data", 0, False
        
        # مؤشرات الفريم الصغير (1 دقيقة)
        df_1m['ema9'] = ta.trend.ema_indicator(df_1m['c'], 9)
        df_1m['ema21'] = ta.trend.ema_indicator(df_1m['c'], 21)
        df_1m['rsi'] = ta.momentum.rsi(df_1m['c'], 14)
        df_1m['macd'] = ta.trend.macd_diff(df_1m['c'])
        df_1m['vm'] = df_1m['v'].rolling(20).mean()
        
        # مؤشرات الفريم الكبير (5 دقائق) - لتحديد الاتجاه العام
        df_5m['ema50'] = ta.trend.ema_indicator(df_5m['c'], 50)
        
        # فلتر التذبذب (Bollinger Bands Width) على فريم 5 دقائق
        bb = ta.volatility.BollingerBands(df_5m['c'], 20, 2)
        df_5m['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg() * 100
        
        cur = df_1m.iloc[-1]; prev = df_1m.iloc[-2]; cur_5m = df_5m.iloc[-1]
        
        # 🚫 فلتر التذبذب: منع الإشارات إذا كان السوق جانبي جداً
        if not pd.isna(cur_5m['bb_width']) and cur_5m['bb_width'] < self.CFG['min_bb_width_pct']:
            self.stats['choppy_blocked'] += 1
            return None, "Choppy Market", 0, False
            
        L, S = 0, 0; LR, SR = [], []
        is_whale = False
        
        # 1. الاتجاه العام (5m EMA 50) - شرط أساسي قوي
        if not pd.isna(cur_5m['ema50']):
            if cur_5m['c'] > cur_5m['ema50']: L += 2; LR.append("5M_UP")
            else: S += 2; SR.append("5M_DN")
        
        # 2. تقاطع EMA (1m)
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']: L += 3; LR.append("CROSS_UP")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']: S += 3; SR.append("CROSS_DN")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1
            
        # 3. RSI (1m)
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 30: L += 2; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 70: S += 2; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50: L += 1
            elif 50 < cur['rsi'] <= 60: S += 1
            
        # 4. MACD (1m)
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1
            
        # 5. شمعة قوية (1m)
        body = abs(cur['c'] - cur['o']); rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.6:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CAND")
            else: S += 1; SR.append("BEAR_CAND")
        
        # ===== 🐋 6. رادار الحيتان (Volume Spike) =====
        if not pd.isna(cur['vm']) and cur['vm'] > 0:
            vol_ratio = cur['v'] / cur['vm']
            
            if vol_ratio >= self.CFG['whale_level_3']:
                is_whale = True
                if cur['c'] > cur['o']: L += 4; LR.append(f"🐋WHALE_{vol_ratio:.0f}x")
                else: S += 4; SR.append(f"🐋WHALE_{vol_ratio:.0f}x")
            elif vol_ratio >= self.CFG['whale_level_2']:
                is_whale = True
                if cur['c'] > cur['o']: L += 3; LR.append(f"🐋WHALE_{vol_ratio:.0f}x")
                else: S += 3; SR.append(f"🐋WHALE_{vol_ratio:.0f}x")
            elif vol_ratio >= self.CFG['whale_level_1']:
                if cur['c'] > cur['o']: L += 1; LR.append(f"VOL_{vol_ratio:.1f}x")
                else: S += 1; SR.append(f"VOL_{vol_ratio:.1f}x")
        
        if is_whale: self.stats['whale_spotted'] += 1
        
        min_pts = self.CFG['min_score']; gap = self.CFG['score_gap']
        
        # تحديد المدة المقترحة بناءً على سبب الدخول
        duration = 5 # الافتراضي
        if is_whale: duration = 1 # حركة الحوت سريعة
        if "CROSS" in str(LR) or "CROSS" in str(SR): duration = 3
        
        if L >= min_pts and (L - S) >= gap: 
            return 'CALL', f"L:{L} S:{S} | " + "+".join(LR[:3]), duration, is_whale
        elif S >= min_pts and (S - L) >= gap: 
            return 'PUT', f"L:{L} S:{S} | " + "+".join(SR[:3]), duration, is_whale
            
        self.stats['no_score'] += 1
        return None, f"L:{L} S:{S}", 0, False

    # ================================================================
    #             إدارة الإشارات و التحقق الذاتي (Anti-Tilt)
    # ================================================================

    def _send_signal(self, b_sym, q_sym, direction, reason, duration, is_whale):
        price = 0
        ticker = self._ticker(b_sym)
        if ticker: price = ticker['last']
        
        self.stats['signals_sent'] += 1
        self.last_signal_time = time.time()
        
        with self.trade_lock:
            self.day_signals += 1
            
        icon = "🟢" if direction == 'CALL' else "🔴"
        whale_tag = "\n🐋 تدفق حيتان قوي!" if is_whale else ""
        
        msg  = f"🚀 *إشارة كوتكس (Quotex)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{q_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}* {icon}\n"
        msg += f"⏱️ المدة المقترحة: *{duration} دقائق*\n"
        msg += f"💵 سعر الدخول: `{price}`\n"
        msg += f"🧠 الأسباب: `{reason}`{whale_tag}\n"
        msg += "━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        
        # 🔥 بدء خيط التحقق الذاتي في الخلفية
        threading.Thread(target=self._validate_signal_outcome, args=(b_sym, direction, price, duration), daemon=True).start()

    def _validate_signal_outcome(self, sym, direction, entry_price, duration):
        """خيط خلفي ينتظر انتهاء مدة الإشارة ثم يفحص النتيجة لتغذية نظام Anti-Tilt"""
        time.sleep(duration * 60) # انتظر مدة الصفقة
        ticker = self._ticker(sym)
        if not ticker or entry_price == 0: return
        
        current_price = ticker['last']
        is_win = False
        if direction == 'CALL' and current_price > entry_price: is_win = True
        if direction == 'PUT' and current_price < entry_price: is_win = True
        
        self.log(f"Validation: {sym} {direction} -> {'WIN' if is_win else 'LOSS'}")
        
        if not is_win:
            self.streak_losses += 1
            if self.streak_losses >= self.CFG['tilt_after_losses']:
                self.tilt_until = time.time() + (self.CFG['tilt_duration_min'] * 60)
                self.stats['tilt_triggered'] += 1
                self.tg(f"🛡️ *Anti-Tilt مفعّل!* \nإيقاف الإشارات لمدة {self.CFG['tilt_duration_min']} دقيقة بسبب ضعف دقة السوق الحالي.")
        else:
            self.streak_losses = 0

    # ================================================================
    #                         MAIN RUN LOOP
    # ================================================================
    
    def _report(self):
        msg  = "📊 *تقرير إشارات اليوم (Quotex)*\n"
        msg += f"🚀 إشارات مُرسلة: {self.day_signals}/{self.CFG['max_daily_signals']}\n"
        msg += f"🐋 حيتان رصدت: {self.stats['whale_spotted']}\n"
        msg += f"🚫 تم حظر (تذبذب): {self.stats['choppy_blocked']}\n"
        msg += f"🛡️ مرات الإيقاف (Tilt): {self.stats['tilt_triggered']}"
        self.tg(msg)

    def run(self):
        self.tg("🐋 *مسار الصيد بدأ!*")
        self.log("HUNTER STARTED", notify=True, msg_ar="🏹 جاري مراقبة أزواج كوتكس!")
        
        while True:
            try:
                today = datetime.date.today()
                if self.day != today:
                    if self.day is not None and self.day_signals > 0: self._report()
                    with self.trade_lock:
                        self.day = today; self.day_signals = 0
                        self.stats = {k: 0 for k in self.stats}
                        self.streak_losses = 0; self.tilt_until = 0
                    self.log("NEW DAY RESET", notify=True, msg_ar="📅 يوم جديد، تم تصفير الإحصائيات!")
                
                # التحقق من الحد اليومي
                if self.day_signals >= self.CFG['max_daily_signals']:
                    time.sleep(600); continue
                
                # التحقق من نظام Anti-Tilt
                if time.time() < self.tilt_until:
                    time.sleep(60); continue
                
                # التحقق من مهلة التبريد بين الإشارات
                if time.time() - self.last_signal_time < self.cooldown_sec:
                    time.sleep(10); continue
                
                self.scan_num += 1
                found = False
                
                # المرور على القائمة البيضاء فقط
                for b_sym, q_sym in self.QUOTEX_WHITELIST.items():
                    self.stats['scanned'] += 1
                    
                    direction, reason, duration, is_whale = self._score_binary(b_sym)
                    
                    if direction:
                        self.log(f"SIGNAL FOUND: {q_sym} {direction} | {reason}")
                        self._send_signal(b_sym, q_sym, direction, reason, duration, is_whale)
                        found = True
                        break # أرسل إشارة واحدة فقط في الدورة لتجنب التشتيت
                
                if not found and self.scan_num % 10 == 0: 
                    self.log(f"SCAN #{self.scan_num} | No Signals | Whales: {self.stats['whale_spotted']}")
                    
                if time.time() - self.report_time >= self.CFG['summary_every']:
                    self._report(); self.report_time = time.time()
                    
            except Exception as e: 
                self.log(f"HUNTER ERR: {e}")
                time.sleep(15)
            
            time.sleep(self.CFG['loop_sec'])

if __name__ == "__main__":
    bot = QuotexMonsterBot()
    if bot.tg_token:
        bot.run()
