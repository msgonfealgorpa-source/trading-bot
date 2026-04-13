import ccxt, time, pandas as pd, ta, requests, datetime, os, sys, threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class SmartBot:
    """
    بوت الوحش V13.0 (STABLE)
    ==========================
    - لا يوجد Realtime Scanner (سبب المشاكل)
    - مزامنة حقيقية مع المنصة
    - Trailing محسن
    - كود بسيط ونظيف
    """
    
    def __init__(self):
        self.api_key = os.environ.get('API_KEY')
        self.api_secret = os.environ.get('API_SECRET')
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not all([self.api_key, self.api_secret, self.tg_token]):
            print("[FATAL ERROR] Missing API Keys!")
            return
        
        self.exchange = ccxt.bingx({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
        self.trade_lock = threading.Lock()
        self.trade_settings = None
        self.day = None
        self.day_trades = 0
        self.day_pnl = 0.0
        self.scan_num = 0
        self.last_summary = time.time()
        
        self.streak_wins = 0
        self.streak_losses = 0
        self.tilt_until = 0
        self.is_aggressive = False
        
        self.stats = {
            'wins': 0, 'losses': 0, 'timeouts': 0,
            'scanned': 0, 'no_score': 0, 'qty_zero': 0,
            'order_fail': 0, 'tilt_triggered': 0,
            'whale_spotted': 0, 'trail_adjustments': 0,
            'sync_fixes': 0
        }
        
        self.CFG = {
            'max_daily': 5,          # ✅ قللنا العدد للحماية
            'leverage': 10,
            'base_risk_pct': 3.0,    # ✅ قللنا المخاطرة من 5 لـ 3
            'sl_mult': 2.0,          # ✅ وقف أوسع 2.0 بدل 1.5
            'tp_mult': 3.0,          # ✅ هدف أوسع 3.0 بدل 2.5
            'min_score': 5,          # ✅ اشتراط أعلى 5 بدل 4
            'score_gap': 3,          # ✅ فاصل أكبر 3 بدل 2
            'partial_at': 2.0,       # ✅ خروج جزئي بعد 2%
            'trail_after': 2.0,      # ✅ تتبع بعد 2%
            'trail_step': 0.2,       # ✅ خطوة تتبع 0.2%
            'trail_min_move': 0.6,   # ✅ أقل تراجع لتعديل SL
            'max_hold_min': 90,      # ✅ مدة أقصر
            'vol_filter': 1000000,   # ✅ فلتر حجم أعلى
            'max_scan': 25,          # ✅ فحص أقل
            'loop_sec': 15,          # ✅ فحص كل 15 ثانية
            'summary_every': 1800,
            'tilt_after_losses': 2,
            'tilt_duration_min': 30, # ✅ إيقاف أقصر
            'aggression_after_wins': 3,
            'aggression_risk_boost': 1.0,  # ✅ boost أقل
            'whale_level_2': 3.0,
            'whale_level_3': 5.0,
        }
        
        self.tg("🔄 جاري التشغيل...")
        self.exchange.load_markets()
        self._force_sync()
        
        bal = self._balance()
        msg = "🐋 *بوت الوحش V13.0 (STABLE)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🛡️ نسخة مستقرة ومحافظة\n"
        msg += "🔗 مزامنة حقيقية مع المنصة\n"
        msg += "🐢 Trailing بطيء ومحسن\n"
        msg += "📏 شموع مكتملة فقط\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"💳 رصيد: {bal} USDT"
        self.tg(msg)
        
        if self.trade_settings:
            ts = self.trade_settings
            self.tg(f"🧠 مراقبة: {ts['dir']} {ts['sym']}")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except: pass

    def log(self, msg, notify=False, msg_ar=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        if notify:
            self.tg(msg_ar if msg_ar else msg)

    def fmt(self, val, d=6):
        return f"{val:.{d}g}" if val else "0"

    # ================================================================
    #                         API
    # ================================================================

    def _api(self, method, *args, **kwargs):
        for i in range(3):
            try: return getattr(self.exchange, method)(*args, **kwargs)
            except Exception as e:
                self.log(f"API Retry {method}: {str(e)[:50]}")
                time.sleep(3 * (i + 1))
        return None

    def _balance(self):
        b = self._api('fetch_balance', {'type': 'swap'})
        return float(b.get('USDT', {}).get('free', 0)) if b else 0

    def _tickers(self): return self._api('fetch_tickers')
    def _ticker(self, sym): return self._api('fetch_ticker', sym)
    def _ohlcv(self, sym, tf, limit=60): return self._api('fetch_ohlcv', sym, tf, limit=limit)

    def _df(self, sym, tf, limit=60):
        data = self._ohlcv(sym, tf, limit)
        if not data or len(data) < limit: return None
        return pd.DataFrame(data, columns=['t','o','h','l','c','v'])

    def _set_lev(self, sym, pos_side='LONG'):
        try:
            self.exchange.set_leverage(self.CFG['leverage'], sym, params={'marginMode': 'isolated', 'positionSide': pos_side})
        except: pass

    def _order(self, side, sym, qty, pos_side=None):
        fn = f'create_market_{side}_order'
        params = {'positionSide': pos_side} if pos_side else {}
        try:
            o = getattr(self.exchange, fn)(sym, qty, params=params)
            if o and o.get('id'):
                self.log(f"ORDER OK: {o['id']}", notify=True, msg_ar=f"✅ تنفيذ: {o['id']}")
                return o
        except ccxt.errors.InsufficientFunds:
            self.log("ORDER FAIL: No Funds", notify=True, msg_ar="❌ رصيد غير كافي!")
            self.stats['order_fail'] += 1
        except Exception as e:
            self.log(f"ORDER FAIL: {str(e)[:60]}")
            self.stats['order_fail'] += 1
        return None

    # ================================================================
    #                    🔗 المزامنة الحقيقية
    # ================================================================

    def _get_real_position(self):
        try:
            positions = self._api('fetch_positions')
            if not positions: return None
            for p in positions:
                qty = float(p.get('position', p.get('contracts', 0)))
                if qty > 0:
                    return {
                        'sym': p['symbol'],
                        'dir': 'short' if p.get('positionSide', '').lower() == 'short' else 'long',
                        'entry': float(p['entryPrice']),
                        'qty': qty,
                        'pnl_pct': float(p.get('percentage', 0))
                    }
            return None
        except:
            return None

    def _force_sync(self):
        real = self._get_real_position()
        with self.trade_lock:
            if real:
                sym, d, entry = real['sym'], real['dir'], real['entry']
                if self.trade_settings and (self.trade_settings['sym'] != sym or self.trade_settings['dir'] != d):
                    self.tg(f"🚨 *تناقض وإصلاح!*\nكان: {self.trade_settings.get('dir','?')} {self.trade_settings.get('sym','?')}\nالحقيقة: {d} {sym}")
                    self.stats['sync_fixes'] += 1
                self.trade_settings = {
                    'sym': sym, 'dir': d, 'entry': entry, 'qty': real['qty'],
                    'sl': entry * (0.96 if d == 'long' else 1.04),
                    'tp': 0, 'strategy': 'مستعادة', 'time': time.time(),
                    'partial': False, 'trail_active': False, 'highest_pct': 0
                }
            else:
                if self.trade_settings:
                    self.log(f"SYNC: Cleared ghost {self.trade_settings['sym']}")
                    self.stats['sync_fixes'] += 1
                self.trade_settings = None

    # ================================================================
    #                       الحماية والمخاطرة
    # ================================================================

    def _check_slippage(self, sym, signal_price):
        ticker = self._ticker(sym)
        if not ticker: return True
        diff = abs(ticker['last'] - signal_price) / signal_price * 100
        if diff > 0.5:
            self.log(f"SLIPPAGE BLOCKED: {diff:.2f}%", notify=True, msg_ar=f"🚫 انزلاق {diff:.2f}%")
            return False
        return True

    def _evolve(self, is_win):
        if is_win:
            self.streak_wins += 1; self.streak_losses = 0
            if self.streak_wins >= 3 and not self.is_aggressive:
                self.is_aggressive = True
                self.tg("⚡ وضع الاستغلال!")
        else:
            self.streak_losses += 1; self.streak_wins = 0
            if self.is_aggressive: self.is_aggressive = False
            if self.streak_losses >= 2:
                self.tilt_until = time.time() + 1800
                self.stats['tilt_triggered'] += 1
                self.tg("🛡️ إيقاف 30 دقيقة")

    def _calc_qty(self, sym, price, atr):
        bal = self._balance()
        if bal <= 0: return 0
        sl_dist = self.CFG['sl_mult'] * atr
        if sl_dist <= 0: return 0
        risk = self.CFG['base_risk_pct']
        if self.is_aggressive: risk += self.CFG['aggression_risk_boost']
        qty = (bal * (risk / 100)) / sl_dist
        try:
            fq = self.exchange.amount_to_precision(sym, qty)
            mn = self.exchange.market(sym).get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < float(mn): fq = self.exchange.amount_to_precision(sym, float(mn) * 1.1)
            return float(fq) if float(fq) > 0 else 0
        except: return 0

    def _pnl_pct(self, entry, current, direction):
        return ((current - entry) / entry) * 100 if direction == 'long' else ((entry - current) / entry) * 100

    # ================================================================
    #              📊 نظام النقاط (شموع مكتملة فقط)
    # ================================================================

    def _score(self, sym):
        """
        ✅ يفحص الشموع المكتملة فقط - لا يفحص الشمعة الحالية
        ✅ هذا يمنع الإشارات الكاذبة
        """
        df = self._df(sym, '15m', 60)
        df_h = self._df(sym, '1h', 50)
        if df is None or df_h is None: return None, 0, 0, "No Data", False

        df['ema9'] = ta.trend.ema_indicator(df['c'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['c'], 21)
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        df['vm'] = df['v'].rolling(20).mean()
        df['macd'] = ta.trend.macd_diff(df['c'])
        df_h['ema50'] = ta.trend.ema_indicator(df_h['c'], 50)

        # ✅ نستخدم الشمعة قبل الأخيرة (المكتملة) وليس الحالية
        cur = df.iloc[-2]  # ← آخر شمعة مكتملة
        prev = df.iloc[-3]
        cur_h = df_h.iloc[-1]
        atr = cur['atr']

        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A", False

        L, S = 0, 0
        LR, SR = [], []

        # 1. اتجاه الساعة (وزن 2)
        if not pd.isna(cur_h['ema50']):
            if cur_h['c'] > cur_h['ema50']: L += 2; LR.append("1H↑")
            else: S += 2; SR.append("1H↓")

        # 2. تقاطع EMA (وزن 2)
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']:
                L += 2; LR.append("CROSS↑")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']:
                S += 2; SR.append("CROSS↓")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1

        # 3. RSI (وزن 2)
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 30: L += 2; LR.append(f"RSI{cur['rsi']:.0f}")
            elif cur['rsi'] > 70: S += 2; SR.append(f"RSI{cur['rsi']:.0f}")
            elif cur['rsi'] < 40: L += 1
            elif cur['rsi'] > 60: S += 1

        # 4. MACD (وزن 1)
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1

        # 5. شمعة قوية (وزن 1)
        body = abs(cur['c'] - cur['o'])
        rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.6:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL🟢")
            else: S += 1; SR.append("BEAR🔴")

        # 6. رادار الحيتان (وزن 2-4)
        is_whale = False
        if not pd.isna(cur['vm']) and cur['vm'] > 0:
            vol_ratio = cur['v'] / cur['vm']
            if vol_ratio >= 5.0:
                is_whale = True
                if cur['c'] > cur['o']: L += 4; LR.append(f"🐋{vol_ratio:.0f}x")
                else: S += 4; SR.append(f"🐋{vol_ratio:.0f}x")
            elif vol_ratio >= 3.0:
                is_whale = True
                if cur['c'] > cur['o']: L += 2; LR.append(f"🐋{vol_ratio:.0f}x")
                else: S += 2; SR.append(f"🐋{vol_ratio:.0f}x")

        if is_whale: self.stats['whale_spotted'] += 1

        # ✅ اشتراطات صارمة
        min_pts = self.CFG['min_score']
        gap = self.CFG['score_gap']

        if L >= min_pts and (L - S) >= gap:
            return 'long', cur['c'], atr, f"L:{L}-S:{S} " + "+".join(LR), is_whale
        elif S >= min_pts and (S - L) >= gap:
            return 'short', cur['c'], atr, f"L:{L}-S:{S} " + "+".join(SR), is_whale

        self.stats['no_score'] += 1
        return None, 0, 0, f"L:{L}-S:{S}", False

    # ================================================================
    #                   فتح وإغلاق الصفقات
    # ================================================================

    def _open(self, direction, sym, price, atr, reason, is_whale=False):
        # ✅ تحقق: لا صفقة فعلية
        if self._get_real_position():
            self.log(f"BLOCKED: Position already exists")
            return False

        if not self._check_slippage(sym, price): return False

        sl_dist = self.CFG['sl_mult'] * atr
        tp_dist = self.CFG['tp_mult'] * atr
        sl = price - sl_dist if direction == 'long' else price + sl_dist
        tp = price + tp_dist if direction == 'long' else price - tp_dist

        qty = self._calc_qty(sym, price, atr)
        if qty <= 0: self.stats['qty_zero'] += 1; return False

        side = 'buy' if direction == 'long' else 'sell'
        pos_side = 'LONG' if direction == 'long' else 'SHORT'

        self._set_lev(sym, pos_side)
        time.sleep(0.5)

        order = self._order(side, sym, qty, pos_side=pos_side)
        if not order: return False

        # ✅ تحقق من المنصة
        time.sleep(2)
        real = self._get_real_position()
        if not real:
            self.tg(f"🚨 أمر وهمي! {sym}")
            self.stats['order_fail'] += 1
            return False

        if real['dir'] != direction:
            self.tg(f"🚨 اتجاه خاطئ! طلب:{direction} فعلي:{real['dir']}")
            self._force_close(sym)
            return False

        with self.trade_lock:
            self.trade_settings = {
                'sym': sym, 'dir': direction, 'entry': real['entry'],
                'qty': real['qty'], 'sl': sl, 'tp': tp,
                'strategy': '🐋حوت' if is_whale else 'نقاط',
                'reason': reason, 'time': time.time(),
                'partial': False, 'trail_active': False, 'highest_pct': 0
            }
            self.day_trades += 1

        icon = "🟢" if direction == 'long' else "🔴"
        msg = f"{icon} *صفقة #{self.day_trades}*\n"
        msg += f"🪙 {sym}\n"
        msg += f"💵 {self.fmt(real['entry'])} | ⚖️ {self.fmt(real['qty'], 4)}\n"
        msg += f"🛑 {self.fmt(sl)} | 🎯 {self.fmt(tp)}\n"
        msg += f"📝 {reason}\n🆔 {order.get('id','?')}"
        self.tg(msg)
        return True

    def _force_close(self, sym):
        try:
            real = self._get_real_position()
            if not real or real['sym'] != sym: return
            d = real['dir']
            pos_side = 'LONG' if d == 'long' else 'SHORT'
            qty = float(self.exchange.amount_to_precision(sym, real['qty']))
            if qty > 0:
                self._order('sell' if d == 'long' else 'buy', sym, qty, pos_side=pos_side)
            with self.trade_lock:
                self.trade_settings = None
        except Exception as e:
            self.log(f"FORCE CLOSE ERR: {e}")

    def _close(self, reason, pct, partial=False):
        with self.trade_lock:
            if not self.trade_settings: return
            t = self.trade_settings.copy()
            sym, d, qty = t['sym'], t['dir'], float(t['qty'])
            if partial:
                qty /= 2
                t['partial'] = True
                t['sl'] = t['entry']
                self.trade_settings = t

        pos_side = 'LONG' if d == 'long' else 'SHORT'
        try: fq = float(self.exchange.amount_to_precision(sym, qty))
        except: fq = qty
        if fq <= 0: return

        order = self._order('sell' if d == 'long' else 'buy', sym, fq, pos_side=pos_side)
        if not order:
            self.tg(f"🚨 فشل إغلاق {d} {sym}")
            return

        if partial:
            self.tg(f"⚡ جزئي 50% {sym} | {pct:+.2f}%")
            return

        with self.trade_lock:
            self._evolve(pct >= 0)
            self.day_pnl += pct
            if pct >= 0: self.stats['wins'] += 1
            else: self.stats['losses'] += 1
            self.trade_settings = None

        icon = "🏆" if pct >= 0 else "📉"
        self.tg(f"{icon} {sym} ({d}) | {pct:+.2f}%\n📝 {reason} | صافي: {self.day_pnl:+.2f}%")

    # ================================================================
    #                      إدارة الصفقة
    # ================================================================

    def _manage(self):
        # ✅ اسأل المنصة أولاً
        real = self._get_real_position()

        with self.trade_lock:
            s = self.trade_settings.copy() if self.trade_settings else None

        # ✅ لا يوجد شيء في المنصة
        if not real:
            if s:
                self.log(f"SYNC: Position closed externally {s['sym']}")
                with self.trade_lock: self.trade_settings = None
            return

        sym, d, entry, pnl = real['sym'], real['dir'], real['entry'], real['pnl_pct']

        # ✅ تناقض
        if s and (s['sym'] != sym or s['dir'] != d):
            self.tg(f"🚨 تناقض! محلي:{s['dir']} فعلي:{d}")
            with self.trade_lock:
                self.trade_settings = {
                    'sym': sym, 'dir': d, 'entry': entry, 'qty': real['qty'],
                    'sl': entry * (0.96 if d == 'long' else 1.04),
                    'tp': 0, 'strategy': 'مصححة', 'time': time.time(),
                    'partial': False, 'trail_active': False, 'highest_pct': 0
                }
            s = self.trade_settings.copy()

        # ✅ صفقة بدون إعدادات
        if not s:
            self.tg(f"🔗 مستعادة: {d} {sym} | {pnl:+.2f}%")
            with self.trade_lock:
                self.trade_settings = {
                    'sym': sym, 'dir': d, 'entry': entry, 'qty': real['qty'],
                    'sl': entry * (0.96 if d == 'long' else 1.04),
                    'tp': 0, 'strategy': 'مستعادة', 'time': time.time(),
                    'partial': False, 'trail_active': False, 'highest_pct': 0
                }
            s = self.trade_settings.copy()

        ticker = self._ticker(sym)
        if not ticker: return
        cp = ticker['last']

        # ✅ طباعة الحقيقة
        self.log(f"GUARD: {d} {sym} | {pnl:+.2f}% REAL | SL:{s['sl']:.1f}")

        # ✅ فحص SL
        if d == 'long' and cp <= s['sl']: self._close("🛑 SL", pnl); return
        if d == 'short' and cp >= s['sl']: self._close("🛑 SL", pnl); return

        # ✅ فحص TP
        tp = s.get('tp', 0)
        if tp > 0:
            if d == 'long' and cp >= tp: self._close("🎯 TP", pnl); return
            if d == 'short' and cp <= tp: self._close("🎯 TP", pnl); return

        # ✅ تحديث أعلى ربح
        with self.trade_lock:
            if self.trade_settings and pnl > self.trade_settings.get('highest_pct', 0):
                self.trade_settings['highest_pct'] = pnl

        with self.trade_lock:
            if not self.trade_settings: return

            # ✅ خروج جزئي
            if pnl >= self.CFG['partial_at'] and not self.trade_settings.get('partial'):
                self.trade_settings['partial'] = True
                self.trade_settings['sl'] = self.trade_settings['entry']
                self._close("⚡ جزئي", pnl, partial=True)
                if tp > 0 and entry > 0:
                    if d == 'long': self.trade_settings['tp'] = entry + (tp - entry) * 0.6
                    else: self.trade_settings['tp'] = entry - (entry - tp) * 0.6
                return

            # ✅ Trailing Stop محسن
            highest = self.trade_settings.get('highest_pct', 0)

            if pnl >= self.CFG['trail_after']:
                if not self.trade_settings.get('trail_active'):
                    self.trade_settings['trail_active'] = True
                    self.log(f"TRAIL ON at {pnl:.2f}%", notify=True, msg_ar=f"🐢 تتبع عند {pnl:.2f}%")

                drawdown = highest - pnl
                if drawdown >= self.CFG['trail_min_move']:
                    step = self.CFG['trail_step']
                    if d == 'long':
                        new_sl = cp * (1 - step / 100)
                        if new_sl > self.trade_settings['sl']:
                            self.trade_settings['sl'] = new_sl
                            self.stats['trail_adjustments'] += 1
                    else:
                        new_sl = cp * (1 + step / 100)
                        if new_sl < self.trade_settings['sl']:
                            self.trade_settings['sl'] = new_sl
                            self.stats['trail_adjustments'] += 1

            # ✅ انتهاء الوقت
            elapsed = (time.time() - self.trade_settings['time']) / 60
            if elapsed >= self.CFG['max_hold_min']:
                self._close(f"⏳ {elapsed:.0f}د", pnl)
                self.stats['timeouts'] += 1

    # ================================================================
    #                         التشغيل
    # ================================================================

    def _guard_loop(self):
        self.log("GUARD STARTED", notify=True, msg_ar="🛡️ حارس الصفقات!")
        sync_count = 0
        while True:
            try:
                sync_count += 1
                if sync_count >= 20:  # مزامنة كل 20 ثانية
                    self._force_sync()
                    sync_count = 0
                self._manage()
            except Exception as e:
                self.log(f"GUARD ERR: {e}")
            time.sleep(1)

    def _summary(self):
        total = self.stats['wins'] + self.stats['losses']
        wr = (self.stats['wins'] / total * 100) if total > 0 else 0
        self.tg(f"📊 {self.day_trades}/{self.CFG['max_daily']} | {wr:.0f}% | صافي:{self.day_pnl:+.2f}% | 🐋{self.stats['whale_spotted']}")

    def run(self):
        self.tg("🐋 *V13.0 STABLE يعمل!*")
        threading.Thread(target=self._guard_loop, daemon=True).start()

        while True:
            try:
                today = datetime.date.today()
                if self.day != today:
                    if self.day and self.day_trades > 0: self._summary()
                    with self.trade_lock:
                        self.day = today
                        self.day_trades = 0
                        self.day_pnl = 0.0
                        self.stats = {k: 0 for k in self.stats}
                        self.streak_wins = 0
                        self.streak_losses = 0
                        self.tilt_until = 0
                        self.is_aggressive = False
                    self.log("NEW DAY", notify=True, msg_ar="📅 يوم جديد!")

                with self.trade_lock:
                    has = self.trade_settings is not None

                if has or self.day_trades >= self.CFG['max_daily']:
                    time.sleep(600 if self.day_trades >= self.CFG['max_daily'] else 15)
                    continue

                if time.time() < self.tilt_until:
                    time.sleep(60)
                    continue

                self.scan_num += 1
                tickers = self._tickers()
                if not tickers:
                    time.sleep(30)
                    continue

                syms = [s for s, t in tickers.items()
                        if s.endswith('/USDT:USDT')
                        and t.get('quoteVolume')
                        and t.get('last')
                        and t['quoteVolume'] * t['last'] > self.CFG['vol_filter']][:80]

                if not syms:
                    time.sleep(60)
                    continue

                self.log(f"SCAN #{self.scan_num} | 🐋{self.stats['whale_spotted']}")

                found = False
                for sym in syms[:self.CFG['max_scan']]:
                    self.stats['scanned'] += 1
                    d, p, atr, reason, is_whale = self._score(sym)

                    if d and p > 0 and atr > 0:
                        with self.trade_lock:
                            can = self.trade_settings is None
                        if can and self._open(d, sym, p, atr, reason, is_whale):
                            found = True
                            break

                if not found:
                    self.log("NO SIGNALS")

                if time.time() - self.last_summary >= self.CFG['summary_every']:
                    self._summary()
                    self.last_summary = time.time()

            except Exception as e:
                self.log(f"ERR: {e}")
                time.sleep(15)

            time.sleep(self.CFG['loop_sec'])

if __name__ == "__main__":
    bot = SmartBot()
    if bot.api_key:
        bot.run()
