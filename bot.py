import ccxt, time, pandas as pd, ta, requests, datetime

class Tracker:
    def __init__(self, t, c, ex):
        self.log, self.T, self.C, self.ex = [], t, c, ex
    def send(self, m):
        try: requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage", data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'})
        except: pass
    def add(self, s, ep, xp, q, p, r):
        self.log.append({'t': datetime.datetime.now(), 's': s, 'ep': ep, 'xp': xp, 'q': float(self.ex.amount_to_precision(s, q)), 'p': p, 'r': r})
    def report(self):
        if not self.log: return
        w = [t for t in self.log if t['p'] > 0]; l = [t for t in self.log if t['p'] <= 0]
        m = f"📊 *تقرير اليوم*\nالصفقات: {len(self.log)}\nالفوز: {(len(w)/len(self.log))*100:.1f}%\nإجمالي الربح: {sum(t['p'] for t in self.log):.2f}%\nأفضل صفقة: {max(self.log, key=lambda x: x['p'])['s']} ({max(t['p'] for t in self.log):.2f}%)"
        self.send(m); self.log = [t for t in self.log if t['t'].date() == datetime.date.today()]

class Bot:
    def __init__(self):
        self.K = 'egAeFM8kVEn7YRKPIHRpJGpDW4GFuHRDHFnRmRqdEWcZxPRAb0qHbvd6T6X3MC94Ffqfgc4BSv9mxbBPXSQ'
        self.S = 'OC7UgGik9WOSjUI6r4AvbqfZIq9O9BrjzC2LRrott95Ewcu2jQHRnjCNQj8sn9ZdKIsAf9ioAkp89xs1e7g'
        self.TT = '8744586010:AAET91PN6ApW3FiX4WU1nSH_F5xoHuzIQKk'
        self.CH = '7520475220'
        self.ex = ccxt.bingx({'apiKey': self.K, 'secret': self.S, 'enableRateLimit': True, 'options': {'defaultType': 'spot'}, 'rateLimit': 2000})
        self.trk = Tracker(self.TT, self.CH, self.ex)
        self.trade = None; self.losses = 0; self.dloss = 0.0; self.date = None; self.rtime = datetime.datetime.now()
        self.send("✨ *النسخة الوحشية V2.0 بدأت!*"); 
        print("جاري تحميل الأسواق، يرجى الانتظار...")
        self.ex.load_markets()
        print("✅ تم تحميل الأسواق بنجاح!")

    def send(self, m): self.trk.send(m)
    def retry(self, fn, *a, **k):
        for i in range(7):
            try:
                r = getattr(self.ex, fn)(*a, **k)
                return r if r is not None or fn in ['fetch_trades'] else None
            except Exception as e:
                print(f"⚠️ خطأ في {fn}: {e}"); time.sleep(7 * (i + 1))
        return None
    def ohlcv(self, s, tf, l): return self.retry('fetch_ohlcv', s, tf, limit=l)
    def tick(self, s): return self.retry('fetch_ticker', s)
    def bal(self): return self.retry('fetch_balance')
    def ticks(self): return self.retry('fetch_tickers')
    def order(self, t, s, q):
        o = self.retry(f'create_market_{t}_order', s, q)
        return o if o and o.get('id') else None

    def get_btc_rsi(self):
        b = self.ohlcv('BTC/USDT', '15m', 15)
        if not b: return 50
        return ta.momentum.rsi(pd.DataFrame(b, columns=['t','o','h','l','c','v'])['c'], window=14).iloc[-1]

    def regime(self, s):
        b = self.ohlcv(s, '1h', 100)
        if not b: return "neutral"
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])
        df['e1'] = ta.trend.ema_indicator(df['c'], 100); df['e2'] = ta.trend.ema_indicator(df['c'], 200)
        bb = ta.volatility.BollingerBands(df['c'], 20, 2); df['bw'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['c'] * 100
        l = df.iloc[-1]; p = df.iloc[-2]
        if l['c'] > l['e1'] and l['e1'] > l['e2'] and l['e1'] > p['e1']: return "uptrend"
        if l['bw'] < 5: return "sideways"
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
            if reg == "uptrend":
                cond = l['c'] > l['e2'] and (p['c'] < p['bbl']) and (l['c'] > l['bbl']) and 35 < l['rsi'] < 55 and l['macd'] > p['macd'] and vs
                if cond: return True, l['c'], l['rsi'], l['bbl'], l['bbh']
            elif reg == "sideways":
                if l['c'] <= l['bbl'] and vs: return True, l['c'], l['rsi'], l['bbl'], l['bbh']
        return False, 0, 0, 0, 0

    def calc_qty(self, s, p):
        b = float(self.bal().get('USDT', {}).get('free', 0))
        if b == 0: return 0
        bars = self.ohlcv(s, '15m', 19)
        if not bars: return 0
        atr = ta.volatility.AverageTrueRange(high=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['h'], low=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['l'], close=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['c'], window=14).average_true_range().iloc[-1]
        if pd.isna(atr) or atr <= 0: return 0
        risk = b * (0.75 if self.losses >= 3 else 1.5) / 100
        sl_dist = 2.5 * atr
        if p - sl_dist <= 0: return 0
        qty = risk / sl_dist
        try:
            m = self.ex.market(s); fq = self.ex.amount_to_precision(s, qty)
            mn = m.get('limits', {}).get('amount', {}).get('min')
            if mn and float(fq) < mn: fq = self.ex.amount_to_precision(s, mn)
        except: fq = self.ex.amount_to_precision(s, qty)
        return float(fq) if float(fq) > 0 else 0

    def close(self, reason, pct, loss=False):
        if not self.trade: return
        s = self.trade['s']; c = s.split('/')[0]; b = self.bal()
        if not b or c not in b or b[c].get('free', 0) <= 0: self.trade = None; return
        q = float(self.ex.amount_to_precision(s, b[c]['free']))
        if q <= 0: self.trade = None; return
        t = self.tick(s); xp = self.trade['e'] if not t else t['last']
        if not self.order('sell', s, q): self.send(f"🚨 فشل إغلاق {s}"); return
        self.trk.add(s, self.trade['e'], xp, q, pct, reason)
        if loss:
            self.losses += 1; tb = float(self.bal().get('USDT', {}).get('free', 0))
            self.dloss += (abs(pct)/100)*tb if tb > 0 else abs(pct)
            self.send(f"📉 خسارة {s}: {pct:.2f}%")
        else:
            self.losses = 0; self.send(f"🏆 ربح {s}: {pct:.2f}% | {reason}")
        self.trade = None

    def run(self):
        self.send("🚀 *الوحش V2 جاهز للقنص!*")
        print("\n==================================================")
        print("🚀 تم بدء حلقة التداول بنجاح. البوت يفكر الآن...")
        print("==================================================\n")
        while True:
            if self.date != datetime.date.today(): self.dloss = 0.0; self.date = datetime.date.today()
            try:
                if self.dloss >= 3.0: self.send("🛑 حد الخسارة اليومي"); time.sleep(3600); continue
                if not self.trade:
                    print("🔍 [1/3] جاري فحص نبض البيتكوين...")
                    btc_rsi = self.get_btc_rsi()
                    print(f"📊 نبض البيتكوين (RSI): {btc_rsi:.1f}")
                    if btc_rsi < 40: 
                        print("🛑 البيتكوين ينهار! تجاهل كل الفرص والانتظار 60 ثانية...\n")
                        time.sleep(60); continue
                    
                    print("🌐 [2/3] جاري جلب عملات السوق (قد يستغرق 30 ثانية على الهاتف)...")
                    tk = self.ticks()
                    if not tk: 
                        print("❌ فشل جلب العملات، إعادة المحاولة بعد 30 ثانية...\n")
                        time.sleep(30); continue
                    
                    syms = [s for s, i in tk.items() if s.endswith('/USDT') and ':' not in s and i.get('quoteVolume') and i.get('last') and (i['quoteVolume']*i['last'] > 5000000) and abs(i.get('change', 0)) > 1.5][:30]
                    print(f"✅ [3/3] تم العثور على {len(syms)} عملة قوية. جاري التحليل الفني لكل عملة...")
                    
                    if not syms:
                        print("💤 السوق هادئ جداً أو لا توجد عملات مطابقة. الانتظار 60 ثانية...\n")
                        time.sleep(60); continue
                    
                    for s in syms:
                        print(f"-> تحليل {s}...", end='\r')
                        rg = self.regime(s)
                        if rg not in ["uptrend", "sideways"]: continue
                        ok, p, rsi, bbl, bbh = self.analyze(s, '15m', rg)
                        if ok:
                            q = self.calc_qty(s, p)
                            if q <= 0: continue
                            if self.order('buy', s, q):
                                atr = ta.volatility.AverageTrueRange(high=pd.DataFrame(self.ohlcv(s, '15m', 19), columns=['t','o','h','l','c','v'])['h'], low=pd.DataFrame(self.ohlcv(s, '15m', 19), columns=['t','o','h','l','c','v'])['l'], close=pd.DataFrame(self.ohlcv(s, '15m', 19), columns=['t','o','h','l','c','v'])['c'], window=14).average_true_range().iloc[-1]
                                sl = p * (1 - 2.5 * atr / p) if not pd.isna(atr) else p * 0.975
                                self.trade = {'s': s, 'e': p, 'sl': sl, 'isl': sl, 'hp': p, 'time': time.time(), 'rg': rg, 'bbh': bbh}
                                mode = "ترند صاعد 🚀" if rg=="uptrend" else "تذبذب سكالبينج 🔄"
                                self.send(f"🎯 *قنص ({mode})*\n🪙 {s}\n💵 {p:.4f}\n⚖️ {q:.6f}\n🛑 SL: {sl:.4f}")
                                print(f"\n🎯 🎯 🎯 تم فتح صفقة على {s}! الدخول في وضع المراقبة...\n")
                                self.losses = 0; break
                    print("انتهت دورة البحث، بدء دورة جديدة...\n")
                else:
                    s = self.trade['s']; t = self.tick(s)
                    if not t: time.sleep(15); continue
                    cp = t['last']; ep = self.trade['e']; pp = ((cp - ep) / ep) * 100
                    if cp > self.trade['hp']: self.trade['hp'] = cp
                    hpp = ((self.trade['hp'] - ep) / ep) * 100
                    print(f"⏱️ مراقبة {s} | الربح الحالي: {pp:.2f}% | أعلى ربح: {hpp:.2f}% | SL: {self.trade['sl']:.4f}     ", end='\r')
                    
                    ssl = max(self.trade['sl'], self.trade['isl'])
                    if cp <= ssl: self.close("🛑 ضرب وقف الخسارة", pp, True); continue
                    if time.time() - self.trade['time'] > 3600 and pp < 1.0: self.close("⏳ انتهاء الوقت (نوم)", pp, True); continue
                    if self.trade['rg'] == "uptrend" and pp >= 5.0: self.close("🏆 هدف الترند", pp, False); continue
                    if self.trade['rg'] == "sideways" and cp >= self.trade['bbh']: self.close("🔄 سكالبينج (ضرب السقف)", pp, False); continue
                    
                    if pp > 1.5:
                        bars = self.ohlcv(s, '15m', 15)
                        if bars:
                            rsi_now = ta.momentum.rsi(pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['c'], 14).iloc[-1]
                            if rsi_now > 75 and bars[-1]['c'] < bars[-2]['c']: self.close("🧠 خروج ذكي (RSI قمة)", pp, False); continue
                            
                    if hpp >= 2.5:
                        atr = ta.volatility.AverageTrueRange(high=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['h'], low=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['l'], close=pd.DataFrame(bars, columns=['t','o','h','l','c','v'])['c'], window=14).average_true_range().iloc[-1] if bars else None
                        if atr:
                            nsl = self.trade['hp'] * (1 - 0.5 / 100)
                            if nsl > self.trade['sl']: self.trade['sl'] = nsl
            except Exception as e: 
                print(f"\n⚠️ خطأ عام: {e}\n")
                time.sleep(15)
            time.sleep(15)
            if (datetime.datetime.now() - self.rtime).total_seconds() >= 86400: self.trk.report(); self.rtime = datetime.datetime.now()

if __name__ == "__main__": Bot().run()
