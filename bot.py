import ccxt, time, pandas as pd, ta, requests, datetime, os

class Tracker:
    def __init__(self, t, c, ex): self.log, self.T, self.C, self.ex = [], t, c, ex
    def send(self, m):
        try: requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage", data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'})
        except: pass
    def add(self, s, d, ep, xp, q, p, r):
        self.log.append({'t': datetime.datetime.now(), 's': s, 'd': d, 'ep': ep, 'xp': xp, 'q': float(self.ex.amount_to_precision(s, q)), 'p': p, 'r': r})
    def report(self):
        if not self.log: return
        w = [t for t in self.log if t['p'] > 0]
        m = f"📊 *تقرير العقود*\nالصفقات: {len(self.log)}\nالفوز: {(len(w)/len(self.log))*100:.1f}%\nالربح: {sum(t['p'] for t in self.log):.2f}%"
        self.send(m); self.log = [t for t in self.log if t['t'].date() == datetime.date.today()]

class FuturesBot:
    def __init__(self):
        # 🔒 قراءة المفاتيح من السيرفر بشكل آمن
        self.K = os.environ.get('API_KEY')
        self.S = os.environ.get('API_SECRET')
        self.TT = os.environ.get('TELEGRAM_TOKEN')
        self.CH = os.environ.get('CHAT_ID')
        
        if not self.K or not self.S or not self.TT: 
            print("❌ خطأ: المفاتيح غير موجودة! (تأكد من اعدادات Railway)")
            return

        self.ex = ccxt.bingx({'apiKey': self.K, 'secret': self.S, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}, 'rateLimit': 2000})
        self.trk = Tracker(self.TT, self.CH, self.ex)
        self.trade = None; self.losses = 0; self.dloss = 0.0; self.date = None; self.rtime = datetime.datetime.now()
        self.LEVERAGE = 10 
        
        self.send("🔄 جاري التحقق من الصفقات المفتوحة...")
        self.trade = self.load_state_from_exchange() # 🧠 ذاكرة السيرفر
        
        msg = "✨ *بوت الوحش V4 (Long/Short + ميزات مجنونة)*\n"
        msg += "📋 المخاطرة: 8% | الرافعة: 10X"
        self.send(msg)
        print("جاري تحميل أسواق العقود...")
        self.ex.load_markets(); print("✅ تم التحميل!")
        if self.trade: self.send(f"🧠 *تم استئناف صفقة: {self.trade['d']} {self.trade['s']}*")

    def send(self, m): self.trk.send(m)
    def retry(self, fn, *a, **k):
        for i in range(5):
            try:
                r = getattr(self.ex, fn)(*a, **k)
                return r if r is not None else None
            except Exception as e:
                print(f"Err {fn}: {e}"); time.sleep(5 * (i + 1))
        return None
    def ohlcv(self, s, tf, l): return self.retry('fetch_ohlcv', s, tf, limit=l)
    def tick(self, s): return self.retry('fetch_ticker', s)
    def bal(self): return self.retry('fetch_balance')
    def ticks(self): return self.retry('fetch_tickers')
    
    def setup_futures(self, s, d):
        try: self.ex.set_leverage(self.LEVERAGE, s, params={'marginMode': 'isolated'})
        except: pass

    def order(self, t, s, q):
        o = self.retry(f'create_market_{t}_order', s, q)
        return o if o and o.get('id') else None

    # 🧠 ذاكرة الاستضافة السحابية
    def load_state_from_exchange(self):
        try:
            positions = self.retry('fetch_positions')
            if positions:
                for pos in positions:
                    qty = float(pos.get('position', pos.get('contracts', 0)))
                    if qty > 0:
                        sym = pos['symbol']; entry = float(pos['entryPrice'])
                        side = pos.get('side', 'long').lower()
                        d = 'short' if 'short' in side else 'long'
                        return {'s': sym, 'd': d, 'e': entry, 'sl': entry*(0.97 if d=='long' else 1.03), 'isl': entry*(0.97 if d=='long' else 1.03), 'hp': entry, 'lp': entry, 'time': time.time(), 'q': qty, 'pyramided': True, 'partial_closed': True}
        except Exception as e: print(f"Err load state: {e}")
        return None

    def get_btc_rsi(self):
        b = self.ohlcv('BTC/USDT:USDT', '15m', 15)
        if not b: return 50
        return ta.momentum.rsi(pd.DataFrame(b, columns=['t','o','h','l','c','v'])['c'], window=14).iloc[-1]

    def regime(self, s):
        b = self.ohlcv(s, '1h', 100)
        if not b: return "neutral"
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['e1'] = ta.trend.ema_indicator(df['c'], 100); df['e2'] = ta.trend.ema_indicator(df['c'], 200)
        l = df.iloc[-1]; p = df.iloc[-2]
        if l['c'] > l['e1'] and l['e1'] > l['e2'] and l['e1'] > p['e1']: return "uptrend"
        if l['c'] < l['e1'] and l['e1'] < l['e2'] and l['e1'] < p['e1']: return "downtrend"
        return "neutral"

    def analyze(self, s, tf, reg):
        b = self.ohlcv(s, tf, 200)
        if not b: return False, 0, 0, 0, 0
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['e2'] = ta.trend.ema_indicator(df['c'], 200); df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['macd'] = ta.trend.macd_diff(df['c']); df['vm'] = df['v'].rolling(20).mean()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        bb = ta.volatility.BollingerBands(df['c'], 20, 2)
        df['bbl'] = bb.bollinger_lband(); df['bbh'] = bb.bollinger_hband()
        l = df.iloc[-1]; p = df.iloc[-2]
        if tf == '15m':
            if l['atr'] is None: return False, 0, 0, 0, 0
            vs = l['v'] > (l['vm'] * 1.5)
            # 🦈 Liquidity Grab (ذيل الشمعة)
            prev_body = abs(p['o'] - p['c'])
            
            if reg == "uptrend":
                prev_wick_low = min(p['o'], p['c']) - p['l']
                is_grab = (prev_wick_low > prev_body * 1.5) and (p['l'] < p['bbl'])
                cond = l['c'] > l['e2'] and is_grab and (l['c'] > l['bbl']) and 35 < l['rsi'] < 55 and l['macd'] > p['macd'] and vs and (l['c'] > l['o'])
                if cond: return True, l['c'], l['rsi'], l['bbl'], l['bbh']
            elif reg == "downtrend":
                prev_wick_high = p['h'] - max(p['o'], p['c'])
                is_grab = (prev_wick_high > prev_body * 1.5) and (p['h'] > p['bbh'])
                cond = l['c'] < l['e2'] and is_grab and (l['c'] < l['bbh']) and 45 < l['rsi'] < 65 and l['macd'] < p['macd'] and vs and (l['c'] < l['o'])
                if cond: return True, l['c'], l['rsi'], l['bbl'], l['bbh']
        return False, 0, 0, 0, 0

    def calc_qty(self, s, p):
        b = float(self.bal().get('USDT', {}).get('free', 0))
        if b == 0: return 0
        bars = self.ohlcv(s, '15m', 19)
        if not bars: return 0
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range().iloc[-1]
        if pd.isna(atr) or atr <= 0: return 0
        
        # ✅ تصحيح المخاطرة 8% والمعادلة
        risk = b * (0.75 if self.losses >= 3 else 8.0) / 100
        sl_dist = 2.5 * atr
        if sl_dist <= 0: return 0
        qty = risk / sl_dist # الحساب الدقيق
        
        try:
            m = self.ex.market(s); fq = self.ex.amount_to_precision(s, qty)
            mn = m.get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < mn: fq = self.ex.amount_to_precision(s, mn)
        except: fq = self.ex.amount_to_precision(s, qty)
        return float(fq) if float(fq) > 0 else 0

    def close(self, reason, pct, loss=False, partial=False):
        if not self.trade: return
        s = self.trade['s']; d = self.trade['d']
        q = float(self.trade['q'])
        if partial: q = q / 2.0
        
        close_type = 'sell' if d == 'long' else 'buy'
        fq = float(self.ex.amount_to_precision(s, q))
        if fq <= 0: return
        
        t = self.tick(s); xp = self.trade['e'] if not t else t['last']
        if not self.order(close_type, s, fq): self.send(f"🚨 فشل إغلاق {d} {s}"); return
        
        if partial:
            self.trade['q'] = str(float(self.trade['q']) - fq)
            self.trade['partial_closed'] = True
            self.trade['sl'] = self.trade['e'] # تحريك الوقف للدخول
            self.send(f"⚡ *إغلاق جزئي (50%)*\n🪙 {s} ({d})\n💰 secured: {pct:.2f}%\n🛑 SL للدخول")
            return

        self.trk.add(s, d, self.trade['e'], xp, q, pct, reason)
        if loss:
            self.losses += 1; tb = float(self.bal().get('USDT', {}).get('free', 0))
            self.dloss += (abs(pct)/100)*tb if tb > 0 else abs(pct)
            self.send(f"📉 خسارة {d} {s}: {pct:.2f}%")
        else:
            self.losses = 0; self.send(f"🏆 ربح {d} {s}: {pct:.2f}% | {reason}")
        self.trade = None

    def run(self):
        self.send("🚀 *الوحش V4 جاهز على السيرفر!*")
        print("\n🚀 بدء حلقة العقود الآجلة (8% Risk, 10X Leverage)...")
        while True:
            if self.date != datetime.date.today(): self.dloss = 0.0; self.date = datetime.date.today()
            try:
                if self.dloss >= 20.0: self.send("🛑 حد خسارة يومي 20% (بسبب الرافعة)"); time.sleep(3600); continue
                if not self.trade:
                    print("🔍 جاري فحص البيتكوين والعملات...")
                    btc_rsi = self.get_btc_rsi()
                    if btc_rsi < 40 or btc_rsi > 60: 
                        print(f"⚠️ البيتكين متطرف (RSI: {btc_rsi:.1f}). تجاهل."); time.sleep(60); continue
                    tk = self.ticks()
                    if not tk: time.sleep(30); continue
                    syms = [s for s, i in tk.items() if s.endswith('/USDT:USDT') and i.get('quoteVolume') and i.get('last') and (i['quoteVolume']*i['last'] > 1000000)][:100]
                    if not syms: time.sleep(60); continue
                    for s in syms:
                        print(f"-> تحليل {s}...", end='\r')
                        rg = self.regime(s)
                        if rg not in ["uptrend", "downtrend"]: continue
                        ok, p, rsi, bbl, bbh = self.analyze(s, '15m', rg)
                        if ok:
                            q = self.calc_qty(s, p)
                            if q <= 0: continue
                            direction = 'long' if rg == "uptrend" else 'short'
                            self.setup_futures(s, direction)
                            if self.order('buy' if direction == 'long' else 'sell', s, q):
                                bars = self.ohlcv(s, '15m', 19)
                                df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                                atr = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=14).average_true_range().iloc[-1]
                                if direction == 'long': sl = p * (1 - 2.5 * atr / p) if not pd.isna(atr) else p * 0.975
                                else: sl = p * (1 + 2.5 * atr / p) if not pd.isna(atr) else p * 1.025
                                
                                self.trade = {'s': s, 'd': direction, 'e': p, 'sl': sl, 'isl': sl, 'hp': p, 'lp': p, 'time': time.time(), 'q': q, 'pyramided': False, 'partial_closed': False}
                                emoji = "🟢LONG" if direction == 'long' else "🔴SHORT"
                                self.send(f"{emoji} *عقد جديد*\n🪙 {s}\n💵 {p:.4f}\n⚖️ {q:.4f}\n🛑 SL: {sl:.4f}")
                                print(f"\n🎯 تم فتح {emoji} على {s}!\n")
                                self.losses = 0; break
                else:
                    s = self.trade['s']; d = self.trade['d']; t = self.tick(s)
                    if not t: time.sleep(15); continue
                    cp = t['last']; ep = self.trade['e']
                    pp = ((cp - ep) / ep * 100) if d == 'long' else ((ep - cp) / ep * 100)
                    if d == 'long' and cp > self.trade['hp']: self.trade['hp'] = cp
                    if d == 'short' and cp < self.trade['lp']: self.trade['lp'] = cp
                    hpp = ((self.trade['hp'] - ep) / ep * 100) if d == 'long' else ((ep - self.trade['lp']) / ep * 100)
                    print(f"⏱️ {d} {s} | الربح: {pp:.2f}% | SL: {self.trade['sl']:.4f}     ", end='\r')
                    
                    ssl = self.trade['sl']
                    if d == 'long' and cp <= ssl: self.close("🛑 SL Long", pp, True); continue
                    if d == 'short' and cp >= ssl: self.close("🛑 SL Short", pp, True); continue
                    
                    # 🦈 Volume Climax
                    bars = self.ohlcv(s, '15m', 20)
                    if bars:
                        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
                        vol_ma = df['v'].rolling(20).mean().iloc[-1]
                        if df.iloc[-1]['v'] > (vol_ma * 4): self.close("🔥 انفجار فوليوم", pp, False); continue

                    # ⏳ وقف زمني
                    if time.time() - self.trade['time'] > 3600 and abs(pp) < 1.0: self.close("⏳ انتهاء الوقت", pp, pp<0); continue
                    
                    # ⚡ الإغلاق الجزئي
                    if pp >= 3.0 and not self.trade.get('partial_closed'):
                        self.close("⚡ جزئي 50%", pp, partial=True); continue
                    
                    # 🚀 التعزيز
                    if pp >= 2.0 and not self.trade.get('pyramided'):
                        add_q = self.calc_qty(s, cp)
                        if add_q > 0:
                            o_type = 'buy' if d == 'long' else 'sell'
                            if self.order(o_type, s, add_q):
                                self.trade['pyramided'] = True
                                self.trade['q'] = str(float(self.trade['q']) + add_q)
                                self.send(f"🚀 *تعزيز!* {s}\nمضاعفة العقد: {self.trade['q']}")
                                time.sleep(2); continue

                    # 🎯 هدف نهائي 10%
                    if pp >= 10.0: self.close("🎯 الهدف 10%", pp, False); continue
                    
                    # التريلينغ ستوب
                    if hpp >= 2.5:
                        if d == 'long':
                            nsl = self.trade['hp'] * (1 - 0.5 / 100)
                            if nsl > self.trade['sl']: self.trade['sl'] = nsl
                        elif d == 'short':
                            nsl = self.trade['lp'] * (1 + 0.5 / 100)
                            if nsl < self.trade['sl']: self.trade['sl'] = nsl
                            
            except Exception as e: print(f"\n⚠️ Err: {e}"); time.sleep(15)
            time.sleep(15)
            if (datetime.datetime.now() - self.rtime).total_seconds() >= 86400: self.trk.report(); self.rtime = datetime.datetime.now()

if __name__ == "__main__": FuturesBot().run()
