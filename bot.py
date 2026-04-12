import ccxt, time, pandas as pd, ta, requests, datetime, os

class SmartBot:
    """
    بوت الوحش V8.0 - نظام النقاط الذكي
    ===================================
    كيف يعمل نظام النقاط:
    - كل مؤشر يعطي نقاط (0-2)
    - إذا مجموع النقاط >= 4 ونفترق عن الاتجاه المعاكس بـ 2 نقطة = دخول
    - هذا يمنع العشوائية ويضمن تكرار الصفقات
    """
    
    def __init__(self):
        self.api_key = os.environ.get('API_KEY')
        self.api_secret = os.environ.get('API_SECRET')
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        
        if not all([self.api_key, self.api_secret, self.tg_token]):
            print("❌ مفاتيح مفقودة!")
            return
        
        self.exchange = ccxt.bingx({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
        # المتغيرات
        self.active_trade = None
        self.day = None
        self.day_trades = 0
        self.day_pnl = 0.0
        self.cooldown = 0
        self.scan_num = 0
        self.report_time = time.time()
        self.last_scan_summary = time.time()
        
        # الإحصائيات
        self.stats = {
            'wins': 0, 'losses': 0, 'timeouts': 0, 
            'scanned': 0, 'no_score': 0, 'qty_zero': 0, 'order_fail': 0
        }
        
        # ======= الإعدادات - سهلة التعديل =======
        self.CFG = {
            'max_daily': 10,         # حد صفقات يومي
            'leverage': 10,          # الرافعة
            'risk_pct': 5.0,         # مخاطرة لكل صفقة %
            'sl_mult': 1.5,          # وقف خسارة = 1.5 × ATR
            'tp_mult': 2.5,          # جني أرباح = 2.5 × ATR
            'min_score': 4,          # حد أدنى للنقاط (4 من 9)
            'score_gap': 2,          # فرق مطلوب بين Long/Short
            'cooldown_sec': 300,     # انتظار بعد خسارة (5 دقائق)
            'partial_at': 1.5,       # إغلاق جزئي عند ربح %
            'trail_after': 1.0,      # trailing stop بعد ربح %
            'max_hold_min': 120,     # أقصى مدة_hold (دقائق)
            'vol_filter': 500000,    # حد أدنى للسيولة $             'max_scan': 40,          # عملات لكل دورة
            'loop_sec': 20,          # وقت الدورة ثواني
            'summary_every': 1800,   # ملخص كل 30 دقيقة
        }
        
        # البدء
        self.tg("🔄 جاري الفحص...")
        self.active_trade = self._load_position()
        self.exchange.load_markets()
        
        bal = self._balance()
        msg  = "🤖 *بوت الوحش V8.0*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "⚙️ *النظام الجديد: نقاط ذكية*\n"
        msg += "• كل مؤشر يعطي نقاط\n"
        msg += "• المجموع يحدد القرار\n"
        msg += "• لا عشوائية - لا تعطيل\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📋 حد يومي: {self.CFG['max_daily']} صفقة\n"
        msg += f"💰 مخاطرة: {self.CFG['risk_pct']}%\n"
        msg += f"⚖️ رافعة: {self.CFG['leverage']}X\n"
        msg += f"📊 نقاط مطلوبة: {self.CFG['min_score']}+\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"💵 رصيد: {bal} USDT"
        self.tg(msg)
        
        if self.active_trade:
            self.tg(f"🧠 استئناف: {self.active_trade['dir']} {self.active_trade['sym']}")
    
    # ================================================================
    #                         TELEGRAM & LOG
    # ================================================================
    
    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}
            )
        except:
            pass
    
    def log(self, msg, notify=False):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        if notify:
            self.tg(msg)
    
    def fmt(self, val, decimals=6):
        """تنسيق الأرقام - يزيل الأصفار الزائدة"""
        if val == 0:
            return "0"
        return f"{val:.{decimals}g}"
    
    # ================================================================
    #                         API CALLS
    # ================================================================
    
    def _api(self, method, *args, **kwargs):
        """استدعاء API مع إعادة المحاولة"""
        for i in range(3):
            try:
                return getattr(self.exchange, method)(*args, **kwargs)
            except Exception as e:
                self.log(f"API {method}: {e}")
                time.sleep(3 * (i + 1))
        return None
    
    def _balance(self):
        b = self._api('fetch_balance', {'type': 'swap'})
        return float(b.get('USDT', {}).get('free', 0)) if b else 0
    
    def _tickers(self):
        return self._api('fetch_tickers')
    
    def _ticker(self, sym):
        return self._api('fetch_ticker', sym)
    
    def _ohlcv(self, sym, tf, limit=60):
        return self._api('fetch_ohlcv', sym, tf, limit=limit)
    
    def _df(self, sym, tf, limit=60):
        """تحويل البيانات لـ DataFrame"""
        data = self._ohlcv(sym, tf, limit)
        if not data or len(data) < limit:
            return None
        return pd.DataFrame(data, columns=['t','o','h','l','c','v'])
    
    def _set_lev(self, sym):
        try:
            self.exchange.set_leverage(
                self.CFG['leverage'], sym, 
                params={'marginMode': 'isolated'}
            )
        except:
            pass
    
    def _order(self, side, sym, qty):
        """تنفيذ أمر سوقي"""
        fn = f'create_market_{side}_order'
        o = self._api(fn, sym, qty)
        if o and o.get('id'):
            self.log(f"✅ أمر منفذ: {o['id']}", notify=True)
            return o
        self.stats['order_fail'] += 1
        self.log(f"❌ فشل الأمر: {side} {sym} qty={self.fmt(qty, 4)}")
        return None
    
    def _load_position(self):
        """تحميل صفقة مفتوحة من المنصة"""
        try:
            positions = self._api('fetch_positions')
            if positions:
                for p in positions:
                    qty = float(p.get('position', p.get('contracts', 0)))
                    if qty > 0:
                        sym = p['symbol']
                        entry = float(p['entryPrice'])
                        side = p.get('side', 'long').lower()
                        d = 'short' if 'short' in side else 'long'
                        self.log(f"🔄 صفقة مفتوحة: {d} {sym}", notify=True)
                        return {
                            'sym': sym, 'dir': d, 'entry': entry,
                            'qty': qty, 'time': time.time(),
                            'strategy': 'استئناف', 'partial': True,
                            'sl': entry * (0.97 if d == 'long' else 1.03),
                            'tp': 0
                        }
        except Exception as e:
            self.log(f"تحميل: {e}")
        return None
    
    # ================================================================
    #                        CALCULATIONS
    # ================================================================
    
    def _calc_qty(self, sym, price, atr):
        """حساب الكمية بناءً على المخاطرة و ATR"""
        bal = self._balance()
        if bal <= 0:
            self.log("❌ رصيد صفر!")
            return 0
        
        sl_dist = self.CFG['sl_mult'] * atr
        if sl_dist <= 0:
            return 0
        
        risk_amount = bal * (self.CFG['risk_pct'] / 100)
        qty = risk_amount / sl_dist
        
        try:
            market = self.exchange.market(sym)
            fq = self.exchange.amount_to_precision(sym, qty)
            
            # التأكد من الحد الأدنى
            mn = market.get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < float(mn):
                fq = self.exchange.amount_to_precision(sym, float(mn) * 1.1)
            
            result = float(fq)
            if result <= 0:
                return 0
            return result
        except Exception as e:
            self.log(f"كمية خطأ: {e}")
            return 0
    
    def _pnl_pct(self, entry, current, direction):
        """حساب نسبة الربح/الخسارة"""
        if direction == 'long':
            return ((current - entry) / entry) * 100
        return ((entry - current) / entry) * 100
    
    # ================================================================
    #                    STRATEGY: SCORING SYSTEM
    # ================================================================
    
    def _score(self, sym):
        """
        نظام النقاط الذكي - يوازن بين الدقة والتكرار
        =================================================
        توزيع النقاط:
        1. اتجاه الساعة (EMA50): 0 أو 2 نقطة
        2. تقاطع EMA 15m: 0 أو 1 أو 2 نقطة
        3. RSI: 0 أو 1 أو 2 نقطة  
        4. MACD: 0 أو 1 نقطة
        5. شمعة قوية: 0 أو 1 نقطة
        6. فوليوم: 0 أو 1 نقطة
        -----------------------------------------
        المجموع الممكن: 9 نقاط
        المطلوب: 4 نقاط + فرق 2 عن المعاكس
        """
        
        df = self._df(sym, '15m', 60)
        df_h = self._df(sym, '1h', 50)
        
        if df is None or df_h is None:
            return None, 0, 0, "بيانات ناقصة"
        
        # === مؤشرات 15m ===
        df['ema9'] = ta.trend.ema_indicator(df['c'], 9)
        df['ema21'] = ta.trend.ema_indicator(df['c'], 21)
        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['atr'] = ta.volatility.AverageTrueRange(
            df['h'], df['l'], df['c'], 14
        ).average_true_range()
        df['vm'] = df['v'].rolling(20).mean()
        df['macd'] = ta.trend.macd_diff(df['c'])
        
        # === مؤشرات 1h ===
        df_h['ema50'] = ta.trend.ema_indicator(df_h['c'], 50)
        
        cur = df.iloc[-1]
        prev = df.iloc[-2]
        cur_h = df_h.iloc[-1]
        
        atr = cur['atr']
        if pd.isna(atr) or atr <= 0:
            return None, 0, 0, "ATR N/A"
        
        L, S = 0, 0  # نقاط
        LR, SR = [], []  # الأسباب للـ Debug
        
        # ──── 1. اتجاه الساعة (2 نقطة) ────
        if not pd.isna(cur_h['ema50']):
            if cur_h['c'] > cur_h['ema50']:
                L += 2
                LR.append("ساعة↑")
            else:
                S += 2
                SR.append("ساعة↓")
        
        # ──── 2. تقاطع/اتجاه EMA (1-2 نقطة) ────
        ema_ok = all(not pd.isna(x) for x in [cur['ema9'], cur['ema21'], prev['ema9'], prev['ema21']])
        if ema_ok:
            # تقاطع جديد = 2 نقاط
            if prev['ema9'] <= prev['ema21'] and cur['ema9'] > cur['ema21']:
                L += 2
                LR.append("تقاطع↑")
            elif prev['ema9'] >= prev['ema21'] and cur['ema9'] < cur['ema21']:
                S += 2
                SR.append("تقاطع↓")
            # اتجاه مستمر = 1 نقطة
            elif cur['ema9'] > cur['ema21']:
                L += 1
            else:
                S += 1
        
        # ──── 3. RSI (1-2 نقطة) ────
        if not pd.isna(cur['rsi']):
            if cur['rsi'] < 35:       # تشبع بيعي = فرصة شراء
                L += 2
                LR.append(f"RSI{cur['rsi']:.0f}")
            elif cur['rsi'] > 65:     # تشبع شرائي = فرصة بيع
                S += 2
                SR.append(f"RSI{cur['rsi']:.0f}")
            elif 40 <= cur['rsi'] < 50:
                L += 1
            elif 50 < cur['rsi'] <= 60:
                S += 1
        
        # ──── 4. MACD (1 نقطة) ────
        if not pd.isna(cur['macd']) and not pd.isna(prev['macd']):
            if cur['macd'] > 0 and cur['macd'] > prev['macd']:
                L += 1
            elif cur['macd'] < 0 and cur['macd'] < prev['macd']:
                S += 1
        
        # ──── 5. شمعة قوية (1 نقطة) ────
        body = abs(cur['c'] - cur['o'])
        rng = cur['h'] - cur['l']
        if rng > 0 and (body / rng) > 0.5:
            if cur['c'] > cur['o']:
                L += 1
                LR.append("شمعة↑")
            else:
                S += 1
                SR.append("شمعة↓")
        
        # ──── 6. فوليوم (1 نقطة) ────
        if not pd.isna(cur['vm']) and cur['v'] > cur['vm']:
            if cur['c'] > cur['o']:
                L += 1
            else:
                S += 1
        
        # === القرار النهائي ===
        min_pts = self.CFG['min_score']
        gap = self.CFG['score_gap']
        
        if L >= min_pts and (L - S) >= gap:
            return 'long', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(LR[:3])
        elif S >= min_pts and (S - L) >= gap:
            return 'short', cur['c'], atr, f"L:{L} S:{S} | " + "+".join(SR[:3])
        
        self.stats['no_score'] += 1
        return None, 0, 0, f"L:{L} S:{S}"
    
    def _ny_signal(self, sym):
        """استراتيجية نيويورك المبسطة - تعمل فقط في وقت محدد"""
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        
        # تحديد ساعة نيويورك (تتغير مع التوقيت الصيفي)
        ny_h = 13 if datetime.datetime(now.year, 3, 14) <= now <= datetime.datetime(now.year, 11, 7) else 14
        ny_time = now.replace(hour=ny_h, minute=30, second=0, microsecond=0)
        
        if now < ny_time:
            return None, 0, 0, "قبل NY"
        if (now - ny_time).total_seconds() > 10800:  # 3 ساعات
            return None, 0, 0, "بعد NY"
        
        df = self._df(sym, '15m', 30)
        if df is None:
            return None, 0, 0, "لا بيانات"
        
        df['ts'] = pd.to_datetime(df['t'], unit='ms')
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        
        # البحث عن شمعة افتتاح نيويورك
        mask = (
            (df['ts'].dt.hour == ny_h) & 
            (df['ts'].dt.minute == 30) & 
            (df['ts'].dt.date == now.date())
        )
        ref = df[mask]
        if ref.empty:
            return None, 0, 0, "لا شمعة NY"
        
        ref_h, ref_l = ref.iloc[0]['h'], ref.iloc[0]['l']
        cur = df.iloc[-1]
        atr = cur['atr']
        
        if pd.isna(atr) or atr <= 0:
            return None, 0, 0, "ATR N/A"
        
        # كسر بسيط - لا شروط إضافية
        if cur['c'] > ref_h:
            return 'long', cur['c'], atr, "NY↑ كسر"
        elif cur['c'] < ref_l:
            return 'short', cur['c'], atr, "NY↓ كسر"
        
        return None, 0, 0, "NY لا كسر"
    
    # ================================================================
    #                     TRADE MANAGEMENT
    # ================================================================
    
    def _open(self, direction, sym, price, atr, strategy, reason):
        """فتح صفقة جديدة"""
        sl_dist = self.CFG['sl_mult'] * atr
        tp_dist = self.CFG['tp_mult'] * atr
        
        sl = price - sl_dist if direction == 'long' else price + sl_dist
        tp = price + tp_dist if direction == 'long' else price - tp_dist
        
        qty = self._calc_qty(sym, price, atr)
        if qty <= 0:
            self.stats['qty_zero'] += 1
            self.log(f"❌ {sym}: كمية = 0")
            return False
        
        self._set_lev(sym)
        
        side = 'buy' if direction == 'long' else 'sell'
        order = self._order(side, sym, qty)
        
        if order:
            self.active_trade = {
                'sym': sym, 'dir': direction, 'entry': price,
                'sl': sl, 'tp': tp, 'qty': qty,
                'strategy': strategy, 'reason': reason,
                'time': time.time(), 'partial': False
            }
            
            self.day_trades += 1
            icon = "🟢" if direction == 'long' else "🔴"
            
            msg  = f"{icon} *صفقة #{self.day_trades}*\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += f"📊 {strategy}\n"
            msg += f"🪙 {sym}\n"
            msg += f"💵 دخول: {self.fmt(price)}\n"
            msg += f"⚖️ كمية: {self.fmt(qty, 4)}\n"
            msg += f"🛑 SL: {self.fmt(sl)} ({self.CFG['sl_mult']}×ATR)\n"
            msg += f"🎯 TP: {self.fmt(tp)} ({self.CFG['tp_mult']}×ATR)\n"
            msg += f"📝 {reason}\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += f"🆔 {order.get('id', '?')}"
            self.tg(msg)
            return True
        
        return False
    
    def _close(self, reason, pct, partial=False):
        """إغلاق الصفقة"""
        if not self.active_trade:
            return
        
        t = self.active_trade
        sym, d = t['sym'], t['dir']
        qty = float(t['qty'])
        
        # الإغلاق الجزئي
        if partial:
            qty = qty / 2
            t['partial'] = True
            t['sl'] = t['entry']  # نقل SL للدخول
        
        close_side = 'sell' if d == 'long' else 'buy'
        
        try:
            fq = float(self.exchange.amount_to_precision(sym, qty))
        except:
            fq = qty
        
        if fq <= 0:
            return
        
        order = self._order(close_side, sym, fq)
        if not order:
            self.tg(f"🚨 فشل إغلاق {d} {sym}")
            return
        
        oid = order.get('id', '?')
        is_loss = pct < 0
        self.day_pnl += pct
        
        if is_loss:
            self.stats['losses'] += 1
            self.cooldown = time.time() + self.CFG['cooldown_sec']
            icon = "📉"
        else:
            self.stats['wins'] += 1
            icon = "🏆"
        
        # إشعار الإغلاق الجزئي
        if partial:
            msg  = "⚡ *إغلاق جزئي 50%*\n"
            msg += f"🪙 {sym} ({d})\n"
            msg += f"💰 {pct:+.2f}%\n"
            msg += f"🛑 SL نقل للدخول\n"
            msg += f"🆔 {oid}"
            self.tg(msg)
            return
        
        # إشعار الإغلاق الكامل
        msg  = f"{icon} *إغلاق صفقة*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 {sym} ({d})\n"
        msg += f"📊 {t['strategy']}\n"
        msg += f"{'💔' if is_loss else '💰'} النتيجة: {pct:+.2f}%\n"
        msg += f"📝 السبب: {reason}\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📊 اليوم: {self.day_trades}/{self.CFG['max_daily']} | صافي: {self.day_pnl:+.2f}%\n"
        msg += f"🆔 {oid}"
        self.tg(msg)
        
        self.active_trade = None
    
    def _manage(self):
        """إدارة الصفقة المفتوحة"""
        t = self.active_trade
        if not t:
            return
        
        sym, d = t['sym'], t['dir']
        ticker = self._ticker(sym)
        if not ticker:
            return
        
        cp = ticker['last']
        ep = t['entry']
        pct = self._pnl_pct(ep, cp, d)
        
        # طباعة الحالة كل دورة
        self.log(f"⏱️ {d} {sym} | {pct:+.2f}%")
        
        # ─── فحص SL ───
        if d == 'long' and cp <= t['sl']:
            self._close("🛑 وقف خسارة", pct)
            return
        if d == 'short' and cp >= t['sl']:
            self._close("🛑 وقف خسارة", pct)
            return
        
        # ─── فحص TP ───
        tp = t.get('tp', 0)
        if tp > 0:
            if d == 'long' and cp >= tp:
                self._close("🎯 جني أرباح", pct)
                return
            if d == 'short' and cp <= tp:
                self._close("🎯 جني أرباح", pct)
                return
        
        # ─── إغلاق جزئي ───
        if pct >= self.CFG['partial_at'] and not t.get('partial'):
            self._close(f"⚡ جزئي @ {pct:.1f}%", pct, partial=True)
            # تقريب الهدف
            if tp > 0 and ep > 0:
                if d == 'long':
                    t['tp'] = ep + (tp - ep) * 0.6
                else:
                    t['tp'] = ep - (ep - tp) * 0.6
            return
        
        # ─── Trailing Stop ───
        if pct >= self.CFG['trail_after']:
            mult = self.CFG['sl_mult'] * 0.01
            if d == 'long':
                new_sl = cp * (1 - mult)
                if new_sl > t['sl']:
                    t['sl'] = new_sl
                    self.log(f"📈 SL متحرك: {self.fmt(new_sl)}")
            else:
                new_sl = cp * (1 + mult)
                if new_sl < t['sl']:
                    t['sl'] = new_sl
                    self.log(f"📉 SL متحرك: {self.fmt(new_sl)}")
        
        # ─── انتهاء الوقت ───
        elapsed = (time.time() - t['time']) / 60
        if elapsed >= self.CFG['max_hold_min']:
            self._close(f"⏳ انتهاء {elapsed:.0f}د", pct)
            self.stats['timeouts'] += 1
            return
    
    # ================================================================
    #                         REPORTS
    # ================================================================
    
    def _report(self):
        """التقرير اليومي"""
        total = self.stats['wins'] + self.stats['losses']
        wr = (self.stats['wins'] / total * 100) if total > 0 else 0
        
        msg  = "📊 *تقرير يومي - الوحش V8.0*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"📋 الصفقات: {self.day_trades}/{self.CFG['max_daily']}\n"
        msg += f"✅ أرباح: {self.stats['wins']}\n"
        msg += f"❌ خسائر: {self.stats['losses']}\n"
        msg += f"⏳ انتهاء: {self.stats['timeouts']}\n"
        msg += f"📈 نسبة فوز: {wr:.1f}%\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += f"🔍 فحص: {self.stats['scanned']} عملة\n"
        msg += f"❌ نقاط منخفضة: {self.stats['no_score']}\n"
        msg += f"⚠️ كمية صفر: {self.stats['qty_zero']}\n"
        msg += f"🚨 فشل أمر: {self.stats['order_fail']}"
        self.tg(msg)
    
    def _summary(self):
        """ملخص دوري كل 30 دقيقة"""
        msg  = f"📊 *ملخص - {self.day_trades}/{self.CFG['max_daily']}*\n"
        msg += f"💰 صافي: {self.day_pnl:+.2f}%\n"
        msg += f"✅{self.stats['wins']} ❌{self.stats['losses']}\n"
        msg += f"🔍 فحص: {self.stats['scanned']} | رفض: {self.stats['no_score']}"
        self.tg(msg)
    
    # ================================================================
    #                         MAIN LOOP
    # ================================================================
    
    def run(self):
        self.tg("🚀 *الوحش V8.0 يعمل!*")
        self.log("🚀 بدء التشغيل...")
        
        while True:
            try:
                # === إعادة تعيين يومي ===
                today = datetime.date.today()
                if self.day != today:
                    if self.day is not None and self.day_trades > 0:
                        self._report()
                    self.day = today
                    self.day_trades = 0
                    self.day_pnl = 0.0
                    self.stats = {k: 0 for k in self.stats}
                    self.cooldown = 0
                    self.log("📅 يوم جديد!", notify=True)
                
                # === حد الصفقات اليومي ===
                if self.day_trades >= self.CFG['max_daily']:
                    self.log(f"⏸️ اكتمل {self.CFG['max_daily']} صفقة - انتظار يوم جديد")
                    time.sleep(600)
                    continue
                
                # === انتظار بعد خسارة ===
                if time.time() < self.cooldown:
                    wait = int(self.cooldown - time.time())
                    if wait % 60 == 0:
                        self.log(f"⏳ انتظار {wait}ث بعد خسارة")
                    time.sleep(30)
                    continue
                
                # === إدارة صفقة مفتوحة ===
                if self.active_trade:
                    self._manage()
                    time.sleep(15)
                    continue
                
                # === البحث عن فرص ===
                self.scan_num += 1
                self.log(f"🔍 دورة #{self.scan_num}")
                
                tickers = self._tickers()
                if not tickers:
                    time.sleep(30)
                    continue
                
                # فلتر العملات
                syms = [
                    s for s, t in tickers.items()
                    if s.endswith('/USDT:USDT')
                    and t.get('quoteVolume')
                    and t.get('last')
                    and t['quoteVolume'] * t['last'] > self.CFG['vol_filter']
                ][:100]
                
                if not syms:
                    time.sleep(60)
                    continue
                
                self.log(f"📊 {len(syms)} عملة مؤهلة")
                
                found = False
                
                for sym in syms[:self.CFG['max_scan']]:
                    self.stats['scanned'] += 1
                    
                    # 1️⃣ نظام النقاط (الأساسي)
                    d, p, atr, reason = self._score(sym)
                    strat = "نقاط ذكية"
                    
                    # 2️⃣ نيويورك (ثانوي - وقت محدد فقط)
                    if not d:
                        d, p, atr, reason = self._ny_signal(sym)
                        strat = "نيويورك"
                    
                    # محاولة الدخول
                    if d and p > 0 and atr > 0:
                        self.log(f"✅ {sym} {d} | {reason}", notify=True)
                        
                        if self._open(d, sym, p, atr, strat, reason):
                            found = True
                            break
                    else:
                        # Debug للعملات الكبيرة فقط
                        if any(x in sym for x in ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']):
                            self.log(f"  {sym}: {reason}")
                
                if not found:
                    self.log("❌ لا فرص في هذه الدورة")
                
                # ملخص دوري
                if time.time() - self.last_scan_summary >= self.CFG['summary_every']:
                    self._summary()
                    self.last_scan_summary = time.time()
                
            except Exception as e:
                self.log(f"⚠️ خطأ: {e}")
                time.sleep(15)
            
            time.sleep(self.CFG['loop_sec'])


if __name__ == "__main__":
    bot = SmartBot()
    if bot.api_key:
        bot.run()
