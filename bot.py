import ccxt, time, pandas as pd, ta, requests, datetime, os, sys, threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class SmartBot:
    """
    بوت الوحش V10.0 (الوحش متعدد المسارات - Multi-Threaded)
    ========================================================
    التحديثات:
    1. مسار منفصل (Thread) لإدارة الصفقات يعمل كل 1 ثانية.
    2. درع حماية من الانزلاق السعري (Slippage).
    3. استخدام Thread Lock لمنع تضارب البيانات.
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
        
        # ===== قفل البيانات (يمنع تضارب المسارات) =====
        self.trade_lock = threading.Lock()
        
        self.active_trade = None
        self.day = None
        self.day_trades = 0
        self.day_pnl = 0.0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_scan_summary = time.time()
        
        # المتغيرات التطورية
        self.streak_wins = 0
        self.streak_losses = 0
        self.tilt_until = 0
        self.is_aggressive = False
        
        self.stats = {
            'wins': 0, 'losses': 0, 'timeouts': 0, 
            'scanned': 0, 'no_score': 0, 'qty_zero': 0, 
            'order_fail': 0, 'tilt_triggered': 0, 'slippage_blocked': 0
        }
        
        self.CFG = {
            'max_daily': 10,
            'leverage': 10,
            'base_risk_pct': 5.0,
            'sl_mult': 1.5,
            'tp_mult': 2.5,
            'min_score': 4,
            'score_gap': 2,
            'cooldown_sec': 300,
            'partial_at': 1.5,
            'trail_after': 1.0,
            'max_hold_min': 120,
            'vol_filter': 500000,
            'max_scan': 40,
            'loop_sec': 20,       # وقت نوم مسار البحث
            'summary_every': 1800,
            # ======= إعدادات التطور والحماية =======
            'tilt_after_losses': 2,
            'tilt_duration_min': 60,
            'aggression_after_wins': 3,
            'aggression_risk_boost': 2.0,
            'vol_multiplier_danger': 2.0,
            'max_slippage_pct': 0.5,  # أقصى انزلاق مسموح به 0.5%
        }
        
        self.tg("🔄 جاري الفحص...")
        self.active_trade = self._load_position()
        self.exchange.load_markets()
        
        bal = self._balance()
        msg  = "⚡ *بوت الوحش V10.0 (Multi-Thread)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🛡️ حارس صفقات (1 ثانية)\n"
        msg += "🚫 حماية من الانزلاق السعري\n"
        msg += f"💳 رصيد: {bal} USDT"
        self.tg(msg)
        
        if self.active_trade:
            self.tg(f"🧠 استئناف: {self.active_trade['dir']} {self.active_trade['sym']}")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except Exception as e:
            pass

    def log(self, msg_en, notify=False, msg_ar=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg_en}") 
        if notify:
            self.tg(msg_ar if msg_ar else msg_en)
    
    def fmt(self, val, decimals=6):
        if val == 0: return "0"
        return f"{val:.{decimals}g}"
    
    # ================================================================
    #                         API CALLS
    # ================================================================
    
    def _api(self, method, *args, **kwargs):
        for i in range(3):
            try:
                return getattr(self.exchange, method)(*args, **kwargs)
            except Exception as e:
                self.log(f"API Retry {method}: {str(e)[:50]}")
                time.sleep(3 * (i + 1))
        return None
    
    def _balance(self):
        b = self._api('fetch_balance', {'type': 'swap'})
        return float(b.get('USDT', {}).get('free', 0)) if b else 0
    
    def _tickers(self): return self._api('fetch_tickers')
    def _ticker(self, sym): return self._api('fetch_ticker', sym)
    
    def _ohlcv(self, sym, tf, limit=60):
        return self._api('fetch_ohlcv', sym, tf, limit=limit)
    
    def _df(self, sym, tf, limit=60):
        data = self._ohlcv(sym, tf, limit)
        if not data or len(data) < limit:
            return None
        return pd.DataFrame(data, columns=['t','o','h','l','c','v'])
    
    def _set_lev(self, sym, pos_side='LONG'):
        try:
            self.exchange.set_leverage(
                self.CFG['leverage'], sym, 
                params={'marginMode': 'isolated', 'positionSide': pos_side}
            )
        except Exception as e:
            self.log(f"LEV WARNING: {str(e)[:50]}")

    def _order(self, side, sym, qty, pos_side=None):
        fn = f'create_market_{side}_order'
        params = {}
        if pos_side:
            params['positionSide'] = pos_side
            
        try:
            o = getattr(self.exchange, fn)(sym, qty, params=params)
            if o and o.get('id'):
                self.log(f"ORDER SUCCESS: ID={o['id']}", notify=True, msg_ar=f"✅ تنفيذ: {o['id']}")
                return o
            else:
                self.log(f"ORDER NO ID: {o}")
        except ccxt.errors.InsufficientFunds as e:
            self.log(f"ORDER FAIL: No Funds", notify=True, msg_ar="❌ رصيد غير كافي!")
            self.stats['order_fail'] += 1
            return None
        except ccxt.errors.ExchangeError as e:
            self.log(f"ORDER FAIL: Exchange - {str(e)[:60]}", notify=True, msg_ar=f"❌ خطأ منصة: {str(e)[:60]}")
            self.stats['order_fail'] += 1
            return None
        except Exception as e:
            self.log(f"ORDER FAIL: {str(e)[:60]}")
            self.stats['order_fail'] += 1
            return None
        
        self.stats['order_fail'] += 1
        return None
    
    def _load_position(self):
        try:
            positions = self._api('fetch_positions')
            if positions:
                for p in positions:
                    qty = float(p.get('position', p.get('contracts', 0)))
                    if qty > 0:
                        sym = p['symbol']
                        entry = float(p['entryPrice'])
                        pos_side = p.get('positionSide', '').lower()
                        d = 'short' if pos_side == 'short' else 'long'
                        self.log(f"RESUMING: {d} {sym}", notify=True, msg_ar=f"🔄 استئناف: {d} {sym}")
                        return {
                            'sym': sym, 'dir': d, 'entry': entry,
                            'qty': qty, 'time': time.time(),
                            'strategy': 'استئناف', 'partial': True,
                            'sl': entry * (0.97 if d == 'long' else 1.03), 'tp': 0
                        }
        except Exception as e:
            self.log(f"LOAD POS ERROR: {e}")
        return None

    # ================================================================
    #          🚫 درع حماية الانزلاق السعري (Slippage Shield)
    # ================================================================

    def _check_slippage(self, sym, signal_price):
        """
        يمنع الدخول إذا انحرف السعر كثيراً عن سعر الإشارة أثناء التقلبات.
        """
        ticker = self._ticker(sym)
        if not ticker:
            return True # إذا فشل جلب السعر، ندخل على مسؤوليتنا
            
        current_price = ticker['last']
        diff_pct = abs(current_price - signal_price) / signal_price * 100
        
        if diff_pct > self.CFG['max_slippage_pct']:
            self.stats['slippage_blocked'] += 1
            self.log(f"SLIPPAGE BLOCKED: Signal={self.fmt(signal_price)} | Current={self.fmt(current_price)} | Diff={diff_pct:.2f}%", 
                     notify=True, 
                     msg_ar=f"🚫 انزلاق سعري محظور!\nالفرق: {diff_pct:.2f}%\nسعر الإشارة: {self.fmt(signal_price)}\nالسعر الحالي: {self.fmt(current_price)}")
            return False
            
        return True

    # ================================================================
    #               🧠 النظام التطوري (الذكاء الديناميكي)
    # ================================================================

    def _evolve_after_close(self, is_win):
        if is_win:
            self.streak_wins += 1
            self.streak_losses = 0
            if self.streak_wins >= self.CFG['aggression_after_wins'] and not self.is_aggressive:
                self.is_aggressive = True
                self.tg(f"⚡ *وضع الاستغلال مفعّل!*\n📈 تم رفع المخاطرة إلى {self.CFG['base_risk_pct'] + self.CFG['aggression_risk_boost']}%")
        else:
            self.streak_losses += 1
            self.streak_wins = 0
            if self.is_aggressive:
                self.is_aggressive = False
                self.log("AGGRESSION OFF", notify=True, msg_ar="🛑 إلغاء وضع الاستغلال")
            if self.streak_losses >= self.CFG['tilt_after_losses']:
                self.tilt_until = time.time() + (self.CFG['tilt_duration_min'] * 60)
                self.stats['tilt_triggered'] += 1
                self.tg(f"🛡️ *وضع الوقاية (Anti-Tilt)*\n⏸️ إيقاف لمدة {self.CFG['tilt_duration_min']} دقيقة")

    def _get_dynamic_risk(self, sym, atr):
        risk = self.CFG['base_risk_pct']
        if self.is_aggressive:
            risk += self.CFG['aggression_risk_boost']
        
        try:
            df = self._df(sym, '1h', 50)
            if df is not None:
                atr_series = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
                cur_atr = atr_series.iloc[-1]
                avg_atr = atr_series.iloc[-20:].mean()
                
                if not pd.isna(cur_atr) and not pd.isna(avg_atr) and avg_atr > 0:
                    if (cur_atr / avg_atr) >= self.CFG['vol_multiplier_danger']:
                        risk *= 0.6
                        self.log(f"VOLATILITY ALERT: Risk reduced to {risk:.1f}%")
        except: pass
        return risk

    # ================================================================
    #                        CALCULATIONS
    # ================================================================
    
    def _calc_qty(self, sym, price, atr):
        bal = self._balance()
        if bal <= 0: return 0
        sl_dist = self.CFG['sl_mult'] * atr
        if sl_dist <= 0: return 0
        
        risk_pct = self._get_dynamic_risk(sym, atr)
        risk_amount = bal * (risk_pct / 100)
        qty = risk_amount / sl_dist
        
        try:
            market = self.exchange.market(sym)
            fq = self.exchange.amount_to_precision(sym, qty)
            mn = market.get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < float(mn):
                fq = self.exchange.amount_to_precision(sym, float(mn) * 1.1)
            result = float(fq)
            return result if result > 0 else 0
        except Exception as e:
            return 0
    
    def _pnl_pct(self, entry, current, direction):
        if direction == 'long': return ((current - entry) / entry) * 100
        return ((entry - current) / entry) * 100
    
    # ================================================================
    #                    STRATEGY: SCORING SYSTEM
    # ================================================================
    
    def _score(self, sym):
        df = self._df(sym, '15m', 60)
        df_h = self._df(sym, '1h', 50)
        if df is None or df_h is None: return None, 0, 0, "Data N/A"
        
        df['ema9'] = ta.trend.ema_indicator(df['c'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['c'], 21)
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        df['vm'] = df['v'].rolling(20).mean()
        df['macd'] = ta.trend.macd_diff(df['c'])
        df_h['ema50'] = ta.trend.ema_indicator(df_h['c'], 50)
        
        cur = df.iloc[-1]; prev = df.iloc[-2]; cur_h = df_h.iloc[-1]
        atr = cur['atr']
        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A"
        
        L, S = 0, 0; LR, SR = [], []
        
        if not pd.isna(cur_h['ema50']):
            if cur_h['c'] > cur_h['ema50']: L += 2; LR.append("1H_UP")
            else: S += 2; SR.append("1H_DN")
        
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']: L += 2; LR.append("CROSS_UP")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']: S += 2; SR.append("CROSS_DN")
            elif cur['ema9'] > cur['ema21']: L += 1
            else: S += 1
        
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 35: L += 2; LR.append(f"RSI_{cur['rsi']:.0f}")
            elif cur['rsi'] > 65: S += 2; SR.append(f"RSI_{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50: L += 1
            elif 50 < cur['rsi'] <= 60: S += 1
        
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']: L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']: S += 1
        
        body = abs(cur['c'] - cur['o']); rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.5:
            if cur['c'] > cur['o']: L += 1; LR.append("BULL_CANDLE")
            else: S += 1; SR.append("BEAR_CANDLE")
        
        if not pd.isna(cur['vm']) and cur['v'] > cur['vm']:
            if cur['c'] > cur['o']: L += 1
            else: S += 1
        
        min_pts = self.CFG['min_score']; gap = self.CFG['score_gap']
        if L >= min_pts and (L - S) >= gap: return 'long', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(LR[:3])
        elif S >= min_pts and (S - L) >= gap: return 'short', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(SR[:3])
        
        self.stats['no_score'] += 1
        return None, 0, 0, f"L:{L} S:{S}"
    
    def _ny_signal(self, sym):
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        ny_h = 13 if datetime.datetime(now.year, 3, 14) <= now <= datetime.datetime(now.year, 11, 7) else 14
        ny_time = now.replace(hour=ny_h, minute=30, second=0, microsecond=0)
        if now < ny_time: return None, 0, 0, "Pre-NY"
        if (now - ny_time).total_seconds() > 10800: return None, 0, 0, "Post-NY"
        
        df = self._df(sym, '15m', 30)
        if df is None: return None, 0, 0, "No Data"
        df['ts'] = pd.to_datetime(df['t'], unit='ms')
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        mask = (df['ts'].dt.hour == ny_h) & (df['ts'].dt.minute == 30) & (df['ts'].dt.date == now.date())
        ref = df[mask]
        if ref.empty: return None, 0, 0, "No NY Candle"
        
        ref_h, ref_l = ref.iloc[0]['h'], ref.iloc[0]['l']
        cur = df.iloc[-1]; atr = cur['atr']
        if pd.isna(atr) or atr <= 0: return None, 0, 0, "ATR N/A"
        if cur['c'] > ref_h: return 'long', cur['c'], atr, "NY_UP"
        elif cur['c'] < ref_l: return 'short', cur['c'], atr, "NY_DN"
        return None, 0, 0, "No Break"
    
    # ================================================================
    #                     TRADE MANAGEMENT
    # ================================================================
    
    def _open(self, direction, sym, price, atr, strategy, reason):
        # 🚫 فحص الانزلاق السعري أولاً
        if not self._check_slippage(sym, price):
            return False
            
        sl_dist = self.CFG['sl_mult'] * atr
        tp_dist = self.CFG['tp_mult'] * atr
        sl = price - sl_dist if direction == 'long' else price + sl_dist
        tp = price + tp_dist if direction == 'long' else price - tp_dist
        
        qty = self._calc_qty(sym, price, atr)
        if qty <= 0:
            self.stats['qty_zero'] += 1
            return False
        
        side = 'buy' if direction == 'long' else 'sell'
        pos_side = 'LONG' if direction == 'long' else 'SHORT'
        
        self._set_lev(sym, pos_side)
        time.sleep(1)
        
        order = self._order(side, sym, qty, pos_side=pos_side)
        
        if order:
            # استخدام القفل عند تعديل المتغيرات المشتركة
            with self.trade_lock:
                self.active_trade = {
                    'sym': sym, 'dir': direction, 'entry': price,
                    'sl': sl, 'tp': tp, 'qty': qty,
                    'strategy': strategy, 'reason': reason,
                    'time': time.time(), 'partial': False
                }
                self.day_trades += 1
            
            icon = "🟢" if direction == 'long' else "🔴"
            mode = "⚡AGGRESSIVE" if self.is_aggressive else "🛡️NORMAL"
            
            msg  = f"{icon} *صفقة #{self.day_trades}*\n"
            msg += f"🪙 {sym} | {strategy}\n"
            msg += f"💵 دخول: {self.fmt(price)}\n"
            msg += f"🛑 SL: {self.fmt(sl)} | 🎯 TP: {self.fmt(tp)}\n"
            msg += f"🧠 {mode}\n🆔 {order.get('id', '?')}"
            self.tg(msg)
            return True
        
        # محاولة بالحد الأدنى
        try:
            market = self.exchange.market(sym)
            mn = float(market.get('limits', {}).get('amount', {}).get('min', 0))
            if mn > 0:
                order2 = self._order(side, sym, mn * 1.1, pos_side=pos_side)
                if order2:
                    with self.trade_lock:
                        self.active_trade = {
                            'sym': sym, 'dir': direction, 'entry': price,
                            'sl': sl, 'tp': tp, 'qty': mn * 1.1,
                            'strategy': strategy + " (MIN)", 'reason': reason,
                            'time': time.time(), 'partial': False
                        }
                        self.day_trades += 1
                    self.tg(f"🟢 صفقة (حد أدنى) {sym}\n🆔 {order2.get('id')}")
                    return True
        except: pass
        return False
    
    def _close(self, reason, pct, partial=False):
        # نسخ البيانات داخل القفل لمنع تضارب البيانات
        with self.trade_lock:
            if not self.active_trade: return
            t = self.active_trade.copy()
            sym, d = t['sym'], t['dir']
            qty = float(t['qty'])
            
            if partial:
                qty = qty / 2
                t['partial'] = True
                t['sl'] = t['entry']
                self.active_trade = t
        
        close_side = 'sell' if d == 'long' else 'buy'
        pos_side = 'LONG' if d == 'long' else 'SHORT'
        
        try:
            fq = float(self.exchange.amount_to_precision(sym, qty))
        except:
            fq = qty
        
        if fq <= 0: return
        
        order = self._order(close_side, sym, fq, pos_side=pos_side)
        if not order:
            self.tg(f"🚨 فشل إغلاق {d} {sym}")
            return
        
        oid = order.get('id', '?')
        is_loss = pct < 0
        
        if partial:
            self.tg(f"⚡ إغلاق جزئي 50% {sym} | {pct:+.2f}%\n🆔 {oid}")
            return
        
        # تحرير الصفقة وإضافة النتائج
        with self.trade_lock:
            self._evolve_after_close(not is_loss)
            self.day_pnl += pct
            if is_loss: self.stats['losses'] += 1
            else: self.stats['wins'] += 1
            self.active_trade = None
        
        icon = "🏆" if not is_loss else "📉"
        msg  = f"{icon} *إغلاق صفقة*\n"
        msg += f"🪙 {sym} ({d}) | {pct:+.2f}%\n"
        msg += f"📝 {reason} | W{self.streak_wins} L{self.streak_losses}\n"
        msg += f"📊 صافي اليوم: {self.day_pnl:+.2f}%\n🆔 {oid}"
        self.tg(msg)
    
    def _manage(self):
        """إدارة الصفقة - يُستدعى الآن كل ثانية واحدة"""
        with self.trade_lock:
            if not self.active_trade: return
            t = self.active_trade.copy()
        
        sym, d = t['sym'], t['dir']
        ticker = self._ticker(sym)
        if not ticker: return
        
        cp = ticker['last']; ep = t['entry']
        pct = self._pnl_pct(ep, cp, d)
        self.log(f"GUARD: {d} {sym} | PnL: {pct:+.2f}%")
        
        if d == 'long' and cp <= t['sl']: self._close("🛑 SL", pct); return
        if d == 'short' and cp >= t['sl']: self._close("🛑 SL", pct); return
        
        tp = t.get('tp', 0)
        if tp > 0:
            if d == 'long' and cp >= tp: self._close("🎯 TP", pct); return
            if d == 'short' and cp <= tp: self._close("🎯 TP", pct); return
        
        # عمليات تحتاج تحديث في الذاكرة (تتم داخل القفل)
        with self.trade_lock:
            if not self.active_trade: return
            
            if pct >= self.CFG['partial_at'] and not self.active_trade.get('partial'):
                self.active_trade['partial'] = True
                self.active_trade['sl'] = self.active_trade['entry']
                # استدعاء الإغلاق الجزئي خارج القفل حتى لا يتم حبس المسار
                self._close(f"⚡ جزئي @ {pct:.1f}%", pct, partial=True)
                
                if tp > 0 and ep > 0:
                    if d == 'long': self.active_trade['tp'] = ep + (tp - ep) * 0.6
                    else: self.active_trade['tp'] = ep - (ep - tp) * 0.6
                return
            
            # Trailing Stop
            if pct >= self.CFG['trail_after']:
                mult = self.CFG['sl_mult'] * 0.01
                if d == 'long':
                    new_sl = cp * (1 - mult)
                    if new_sl > self.active_trade['sl']: self.active_trade['sl'] = new_sl
                else:
                    new_sl = cp * (1 + mult)
                    if new_sl < self.active_trade['sl']: self.active_trade['sl'] = new_sl
            
            # انتهاء الوقت
            elapsed = (time.time() - self.active_trade['time']) / 60
            if elapsed >= self.CFG['max_hold_min']:
                self._close(f"⏳ انتهاء {elapsed:.0f}د", pct)
                self.stats['timeouts'] += 1
    
    # ================================================================
    #                 🛡️ مسار الحارس (يعمل كل ثانية)
    # ================================================================
    
    def _guard_loop(self):
        """
        مسار (Thread) منفصل لا ينام إلا ثانية واحدة.
        وظيفته الوحيدة هي حماية الصفقة المفتوحة وتنفيذ أوامر الخروج فوراً.
        """
        self.log("GUARD THREAD STARTED (1s interval)", notify=True, msg_ar="🛡️ تم تفعيل حارس الصفقات!")
        while True:
            try:
                self._manage()
            except Exception as e:
                self.log(f"GUARD ERROR: {e}")
            time.sleep(1) # فحص كل ثانية!

    # ================================================================
    #                         REPORTS
    # ================================================================
    
    def _report(self):
        total = self.stats['wins'] + self.stats['losses']
        wr = (self.stats['wins'] / total * 100) if total > 0 else 0
        msg  = "⚡ *تقرير V10.0 (Multi-Thread)*\n"
        msg += f"📋 صفقات: {self.day_trades}/{self.CFG['max_daily']}\n"
        msg += f"✅{self.stats['wins']} ❌{self.stats['losses']} | {wr:.1f}%\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        msg += f"🛡️ وقاية: {self.stats['tilt_triggered']}\n"
        msg += f"🚫 انزلاق محظور: {self.stats['slippage_blocked']}"
        self.tg(msg)
    
    def _summary(self):
        mode = "⚡استغلال" if self.is_aggressive else "🛡️عادي"
        msg = f"📊 {self.day_trades}/{self.CFG['max_daily']} | صافي: {self.day_pnl:+.2f}% | {mode}"
        self.tg(msg)
    
    # ================================================================
    #              🏹 مسار الصياد (البحث عن صفقات جديدة)
    # ================================================================
    
    def run(self):
        self.tg("⚡ *الوحش V10.0 (Multi-Thread) يعمل!*")
        
        # 1. تشغيل مسار الحارس في الخلفية
        guard_thread = threading.Thread(target=self._guard_loop, daemon=True)
        guard_thread.start()
        
        # 2. المسار الرئيسي يبحث عن صفقات
        self.log("HUNTER THREAD STARTED (20s interval)", notify=True, msg_ar="🏹 تم تفعيل مسار الصيد!")
        
        while True:
            try:
                today = datetime.date.today()
                if self.day != today:
                    if self.day is not None and self.day_trades > 0: self._report()
                    with self.trade_lock:
                        self.day = today
                        self.day_trades = 0
                        self.day_pnl = 0.0
                        self.stats = {k: 0 for k in self.stats}
                        self.streak_wins = 0
                        self.streak_losses = 0
                        self.tilt_until = 0
                        self.is_aggressive = False
                    self.log("NEW DAY RESET", notify=True, msg_ar="📅 يوم جديد!")
                
                # التحقق من وجود صفقة مفتوحة (بأمان عبر القفل)
                with self.trade_lock:
                    has_trade = self.active_trade is not None
                
                if has_trade or self.day_trades >= self.CFG['max_daily']:
                    if self.day_trades >= self.CFG['max_daily']: time.sleep(600)
                    else: time.sleep(self.CFG['loop_sec'])
                    continue
                
                if time.time() < self.tilt_until:
                    time.sleep(60)
                    continue
                
                self.scan_num += 1
                self.log(f"SCAN #{self.scan_num}")
                
                tickers = self._tickers()
                if not tickers: time.sleep(30); continue
                
                syms = [s for s, t in tickers.items() if s.endswith('/USDT:USDT') and t.get('quoteVolume') and t.get('last') and t['quoteVolume'] * t['last'] > self.CFG['vol_filter']][:100]
                if not syms: time.sleep(60); continue
                
                self.log(f"SCANNING {len(syms)}...")
                found = False
                
                for sym in syms[:self.CFG['max_scan']]:
                    self.stats['scanned'] += 1
                    
                    d, p, atr, reason = self._score(sym)
                    strat = "نقاط ذكية"
                    if not d:
                        d, p, atr, reason = self._ny_signal(sym)
                        strat = "نيويورك"
                    
                    if d and p > 0 and atr > 0:
                        self.log(f"SIGNAL: {sym} {d.upper()}", notify=True, msg_ar=f"✅ فرصة: {sym} {d.upper()}")
                        
                        # التحقق مرة أخرى قبل الدخول (لأن الحارس ربما أغلق صفقة سابقة فجأة)
                        with self.trade_lock:
                            can_open = self.active_trade is None
                        
                        if can_open and self._open(d, sym, p, atr, strat, reason):
                            found = True
                            break
                
                if not found: self.log("NO SIGNALS")
                
                if time.time() - self.last_scan_summary >= self.CFG['summary_every']:
                    self._summary()
                    self.last_scan_summary = time.time()
                
            except Exception as e:
                self.log(f"HUNTER ERROR: {e}")
                time.sleep(15)
            
            time.sleep(self.CFG['loop_sec'])

if __name__ == "__main__":
    bot = SmartBot()
    if bot.api_key:
        bot.run()
