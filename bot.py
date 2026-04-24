import time, pandas as pd, ta, requests, datetime, os, sys, threading, numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexMonsterBot:
    """
    بوت الوحش V11.0 (Quotex Binary Signals Edition)
    =================================================
    - مصدر البيانات: CryptoCompare API (مجاني، بلا حجب جغرافي، يعمل على أي سيرفر)
    - الهدف: إشارات ثنائية (CALL/PUT) لمنصة كوتكس.
    """
    
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return
        
        # قائمة الأزواج المدعومة في كوتكس
        self.QUOTEX_WHITELIST = {
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)', 
            'BNB/USDT': 'BNBUSD(t)', 'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 'DOGE/USDT': 'DOGEUSD(t)',
            'LTC/USDT': 'LTCUSD(t)', 'ADA/USDT': 'ADAUSD(t)',
            'MATIC/USDT': 'MATICUSD(t)', 'AVAX/USDT': 'AVAXUSD(t)',
            'DOT/USDT': 'DOTUSD(t)', 'LINK/USDT': 'LINKUSD(t)'
        }
        
        self.trade_lock = threading.Lock()
        self.day = None
        self.day_signals = 0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_signal_time = 0
        self.cooldown_sec = 120 
        
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
            'tilt_after_losses': 3,
            'tilt_duration_min': 45,
            'whale_level_1': 1.5,
            'whale_level_2': 3.0,
            'whale_level_3': 5.0,
            'min_bb_width_pct': 0.1 
        }
        
        self.tg("🔄 جاري التشغيل...")
        self.tg("✅ تم الربط بـ CryptoCompare (بلا حجب جغرافي)!")

        msg  = "🐋 *بوت الوحش V11.0 (Quotex Edition)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "📡 مصدر البيانات: CryptoCompare Global\n"
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
    #              API & DATA (CryptoCompare - No Geo-Block)
    # ================================================================
    
    def _fetch_ticker(self, sym):
        """يجلب السعر الحالي فقط"""
        base, quote = sym.split('/')
        url = f"https://min-api.cryptocompare.com/data/price?fsym={base}&tsyms={quote}"
        try:
            r = requests.get(url, timeout=5)
            d = r.json()
            price = d.get(quote, 0)
            if price > 0: return {'last': price}
        except: pass
        return None

    def _fetch_ohlcv(self, sym, limit=300):
        """يجلب الشموع الخام من CryptoCompare"""
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        params = {'fsym': base, 'tsym': quote, 'limit': limit}
        try:
            r = requests.get(url, params=params, timeout=10)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                formatted = [[c['time']*1000, c['open'], c['high'], c['low'], c['close'], c['volumeto']] for c in raw]
                df = pd.DataFrame(formatted, columns=['t','o','h','l','c','v'])
                if len(df) >= limit: return df
        except: pass
        return None

    def _get_data(self, sym):
        """يجلب دفعة واحدة ويقسمها بذكاء لـ 1 دقيقة و 5 دقائق"""
        df_raw = self._fetch_ohlcv(sym, 300)
        if df_raw is None: return None, None
        
        df_1m = df_raw.iloc[-60:] 
        
        # تحويل ذكي لفريم 5 دقائق بدون إرسال طلب API إضافي
        try:
            df_raw['ts'] = pd.to_datetime(df_raw['t'], unit='ms')
            df_5m = df_raw.set_index('ts').resample('5min').agg({
                'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last', 'v': 'sum'
            }).dropna().reset_index()
            df_5m['t'] = df_5m['index'].astype(np.int64) // 10**6
            df_5m = df_5m.iloc[-60:]
        except:
            df_5m = None
            
        return df_1m, df_5m
    
    # ================================================================
    #     🧠 الاستراتيجية + رادار الحيتان + فلتر التذبذب
    # ================================================================
    
    def _score_binary(self, sym):
        df_1m, df_5m = self._get_data(sym)
        if df_1m is None or df_5m is None: return None, "No Data", 0, False
        
        df_1m['ema9'] = ta.trend.ema_indicator(df_1m['c'], 9)
        df_1m['ema21'] = ta.trend.ema_indicator(df_1m['c'], 21)
        df_1m['rsi'] = ta.momentum.rsi(df_1m['c'], 14)
        df_1m['macd'] = ta.trend.macd_diff(df_1m['c'])
        df_1m['vm'] = df_1m['v'].rolling(20).mean()
        
        df_5m['ema50'] = ta.trend.ema_indicator(df_5m['c'], 50)
        
        bb = ta.volatility.BollingerBands(df_5m['c'], 20, 2)
        df_5m['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg() * 100
        
        cur = df_1m.iloc[-1]; prev = df_1m.iloc[-2]; cur_5m = df_5m.iloc[-1]
        
        if not pd.isna(cur_5m['bb_width']) and cur_5m['bb_width'] < self.CFG['min_bb_width_pct']:
            self.stats['choppy_blocked'] += 1
            return None, "Choppy Market", 0, False
            
        L, S = 0, 0; LR, SR = [], []
        is_whale = False
        
        if not pd.isna(cur_5m['ema50']):
            if cur_5m['c'] > cur_5m['ema50']: L += 2; LR.append("5M_UP")
            else: S += 2; SR.append("5M_DN")
        
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']: L += 3; LR.append("CROSS_UP")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']: S += 3; SR.append("CROSS_DN")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1
            
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 30: L += 2; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 70: S += 2; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50: L += 1
            elif 50 < cur['rsi'] <= 60: S += 1
            
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1
            
        body = abs(cur['c'] - cur['o']); rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.6:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CAND")
            else: S += 1; SR.append("BEAR_CAND")
        
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
        
        duration = 5
        if is_whale: duration = 1
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
        ticker = self._fetch_ticker(b_sym)
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
        threading.Thread(target=self._validate_signal_outcome, args=(b_sym, direction, price, duration), daemon=True).start()

    def _validate_signal_outcome(self, sym, direction, entry_price, duration):
        time.sleep(duration * 60)
        ticker = self._fetch_ticker(sym)
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
                
                if self.day_signals >= self.CFG['max_daily_signals']:
                    time.sleep(600); continue
                
                if time.time() < self.tilt_until:
                    time.sleep(60); continue
                
                if time.time() - self.last_signal_time < self.cooldown_sec:
                    time.sleep(10); continue
                
                self.scan_num += 1
                found = False
                
                for b_sym, q_sym in self.QUOTEX_WHITELIST.items():
                    self.stats['scanned'] += 1
                    
                    direction, reason, duration, is_whale = self._score_binary(b_sym)
                    
                    if direction:
                        self.log(f"SIGNAL FOUND: {q_sym} {direction} | {reason}")
                        self._send_signal(b_sym, q_sym, direction, reason, duration, is_whale)
                        found = True
                        break
                
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
