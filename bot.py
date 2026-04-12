import ccxt, time, pandas as pd, ta, requests, datetime, os
from typing import Optional, Tuple

class Tracker:
    def __init__(self, t, c, ex): 
        self.log, self.T, self.C, self.ex = [], t, c, ex
        self.debug_enabled = True

    def send(self, m):
        try: 
            requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage", 
                         data={'chat_id': self.C, 'text': m, 'parse_mode': 'Markdown'})
        except Exception as e: 
            print(f"TG Error: {e}")

    def debug(self, msg: str, send_to_tg: bool = False):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        print(full_msg)
        if send_to_tg and self.debug_enabled:
            if "❌" in msg or "✅" in msg or "🎯" in msg or "⚠️" in msg:
                self.send(msg)

    def add(self, s, d, ep, xp, q, p, r):
        self.log.append({'t': datetime.datetime.now(), 's': s, 'd': d, 'ep': ep, 'xp': xp, 
                        'q': q, 'p': p, 'r': r})

    def report(self):
        if not self.log: 
            self.send("📊 لا توجد صفقات اليوم")
            return
        w = [t for t in self.log if t['p'] > 0]
        total_profit = sum(t['p'] for t in self.log)
        m = f"📊 *تقرير الوحش V8.0*\n"
        m += f"📋 عدد الصفقات اليوم: {len(self.log)}\n"
        m += f"✅ دقة الفوز: {(len(w)/len(self.log))*100:.1f}%\n"
        m += f"💰 الربح الإجمالي: {total_profit:.2f}%\n"
        self.send(m)
        self.log = [t for t in self.log if t['t'].date() == datetime.date.today()]


class FuturesBot:
    def __init__(self):
        self.K = os.environ.get('API_KEY')
        self.S = os.environ.get('API_SECRET')
        self.TT = os.environ.get('TELEGRAM_TOKEN')
        self.CH = os.environ.get('CHAT_ID')
        
        self.ex = ccxt.bingx({
            'apiKey': self.K, 'secret': self.S, 
            'enableRateLimit': True, 
            'options': {'defaultType': 'swap'}, 
            'rateLimit': 1500
        })  
        self.trk = Tracker(self.TT, self.CH, self.ex)  
        self.trade = None
        self.losses = 0
        self.dloss = 0.0
        self.date = datetime.date.today()
        self.rtime = datetime.datetime.now()
        
        self.LEVERAGE = 10   
        self.RISK_PCT = 8.0 # نسبة الدخول من المحفظة
        
        self.send("🚀 *بدء تشغيل الوحش V8.0 (القناص المتسلسل)*\nمتوسط الهدف: 10 صفقات دقيقة يومياً.")
        self.ex.load_markets()

    def send(self, m): self.trk.send(m)

    def retry(self, fn, *a, **k):  
        for i in range(3):  
            try:  
                r = getattr(self.ex, fn)(*a, **k)  
                return r if r is not None else None  
            except Exception as e:  
                time.sleep(2)  
        return None  

    def ohlcv(self, s, tf, l): return self.retry('fetch_ohlcv', s, tf, limit=l)  
    def tick(self, s): return self.retry('fetch_ticker', s)  
    def ticks(self): return self.retry('fetch_tickers')  

    def bal(self):   
        b = self.retry('fetch_balance', {'type': 'swap'})  
        return float(b.get('USDT', {}).get('free', 0)) if b else 0  

    def setup_futures(self, s):  
        try: self.ex.set_leverage(self.LEVERAGE, s, params={'marginMode': 'isolated'})
        except: pass  

    def order(self, t, s, q):  
        o = self.retry(f'create_market_{t}_order', s, q)
        return o if o and o.get('id') else None

    def regime(self, s) -> str:
        """تحديد الاتجاه على فريم 15 دقيقة لسرعة الاستجابة"""
        b = self.ohlcv(s, '15m', 200)  
        if not b: return "neutral"  
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])  
        df['ema50'] = ta.trend.ema_indicator(df['c'], 50)
        df['ema200'] = ta.trend.ema_indicator(df['c'], 200)  
        l = df.iloc[-1]
        
        if l['ema50'] > l['ema200'] and l['c'] > l['ema200']: return "uptrend"  
        if l['ema50'] < l['ema200'] and l['c'] < l['ema200']: return "downtrend"  
        return "neutral"

    def analyze_bollinger_bounce(self, s, reg) -> Tuple[bool, float, float, str]:
        """استراتيجية الارتداد من البولينجر (دقة عالية + تكرار جيد)"""
        b = self.ohlcv(s, '15m', 50)  
        if not b: return False, 0, 0, "No Data"
        
        df = pd.DataFrame(b, columns=['t','o','h','l','c','v'])  
        df['rsi'] = ta.momentum.rsi(df['c'], 14)  
        bb = ta.volatility.BollingerBands(df['c'], 20, 2)  
        df['bbl'] = bb.bollinger_lband()
        df['bbh'] = bb.bollinger_hband()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()
        
        l = df.iloc[-1]
        p = df.iloc[-2]
        
        if pd.isna(l['atr']): return False, 0, 0, "No ATR"

        # Long: الترند صاعد، الشمعة السابقة أو الحالية لمست السفلي، الشمعة الحالية خضراء
        if reg == "uptrend":
            if (p['l'] <= p['bbl'] or l['l'] <= l['bbl']) and l['c'] > l['o'] and l['rsi'] < 55:
                return True, l['c'], l['atr'], 'long'
                
        # Short: الترند هابط، الشمعة السابقة أو الحالية لمست العلوي، الشمعة الحالية حمراء
        elif reg == "downtrend":
            if (p['h'] >= p['bbh'] or l['h'] >= l['bbh']) and l['c'] < l['o'] and l['rsi'] > 45:
                return True, l['c'], l['atr'], 'short'

        return False, 0, 0, ""

    def calc_qty(self, s, p, atr) -> float:  
        b = self.bal()  
        if b <= 0: return 0
        
        risk = b * (self.RISK_PCT / 100)
        sl_dist = 2.0 * atr # مسافة الوقف بناءً على التذبذب
        if sl_dist <= 0: return 0
        
        qty = risk / sl_dist
        
        try:
            fq = self.ex.amount_to_precision(s, qty)
            return float(fq)
        except:
            return 0

    def close(self, reason: str, pct: float, loss: bool = False):
        if not self.trade: return
        s, d, q = self.trade['s'], self.trade['d'], float(self.trade['q'])
        
        close_type = 'sell' if d == 'long' else 'buy'
        fq = float(self.ex.amount_to_precision(s, q))
        
        t = self.tick(s)
        xp = self.trade['e'] if not t else t['last']
        
        if fq > 0 and self.order(close_type, s, fq):
            self.trk.add(s, d, self.trade['e'], xp, q, pct, reason)
            
            emoji = "📉 *خسارة*" if loss else "🏆 *ربح*"
            msg = f"{emoji}\n🪙 {s} ({d})\n🎯 النتيجة: {pct:.2f}%\n📝 السبب: {reason}"
            self.send(msg)
            
            if loss: 
                self.losses += 1
                self.dloss += abs(pct)
            else: 
                self.losses = 0
            
            self.trade = None # تحرير البوت ليدخل صفقة جديدة

    def run(self):
        while True:
            if self.date != datetime.date.today():
                self.trk.report()
                self.dloss = 0.0
                self.date = datetime.date.today()
            
            try:
                if self.dloss >= 25.0:
                    self.trk.debug("⏸️ حد الخسارة اليومي.. إيقاف لساعة")
                    time.sleep(3600)
                    continue
                
                # --- حالة البحث عن صفقة جديدة ---
                if not self.trade:
                    tk = self.ticks()
                    if not tk: 
                        time.sleep(15)
                        continue
                    
                    # اختيار أفضل 70 عملة من حيث السيولة
                    syms = [s for s, i in tk.items() if s.endswith('/USDT:USDT') and (i.get('quoteVolume',0) * i.get('last',0) > 1000000)][:70]
                    
                    for s in syms:
                        rg = self.regime(s)
                        if rg == "neutral": continue
                        
                        ok, price, atr, direction = self.analyze_bollinger_bounce(s, rg)
                        
                        if ok:
                            q = self.calc_qty(s, price, atr)
                            if q > 0:
                                self.setup_futures(s)
                                if self.order('buy' if direction == 'long' else 'sell', s, q):
                                    sl_dist = 2.0 * atr
                                    sl = price - sl_dist if direction == 'long' else price + sl_dist
                                    tp = price + (4.0 * atr) if direction == 'long' else price - (4.0 * atr) # الهدف ضعف الوقف
                                    
                                    self.trade = {
                                        's': s, 'd': direction, 'e': price, 'sl': sl, 'tp': tp,
                                        'hp': price, 'lp': price, 'time': time.time(), 'q': q,
                                        'breakeven': False
                                    }
                                    
                                    msg = f"🎯 *صفقة جديدة*\n🪙 {s} ({direction})\n💵 الدخول: {price:.4f}\n🛑 الوقف: {sl:.4f}"
                                    self.send(msg)
                                    break # الخروج من حلقة البحث والتركيز على الصفقة
                    
                # --- حالة متابعة الصفقة المفتوحة ---
                else:
                    s = self.trade['s']
                    d = self.trade['d']
                    t = self.tick(s)
                    if not t: 
                        time.sleep(10)
                        continue
                        
                    cp = t['last']
                    ep = self.trade['e']
                    pp = ((cp - ep) / ep * 100) if d == 'long' else ((ep - cp) / ep * 100)
                    
                    if d == 'long' and cp > self.trade['hp']: self.trade['hp'] = cp
                    if d == 'short' and cp < self.trade['lp']: self.trade['lp'] = cp
                    
                    hpp = ((self.trade['hp'] - ep) / ep * 100) if d == 'long' else ((ep - self.trade['lp']) / ep * 100)

                    # 1. فحص ضرب وقف الخسارة
                    if (d == 'long' and cp <= self.trade['sl']) or (d == 'short' and cp >= self.trade['sl']):
                        self.close("ضرب وقف الخسارة", pp, loss=True)
                        continue
                        
                    # 2. فحص ضرب الهدف (Take Profit)
                    if (d == 'long' and cp >= self.trade['tp']) or (d == 'short' and cp <= self.trade['tp']):
                        self.close("ضرب الهدف المعين", pp, loss=False)
                        continue

                    # 3. تأمين الدخول (Breakeven) بعد ربح 1.5%
                    if hpp >= 1.5 and not self.trade['breakeven']:
                        self.trade['sl'] = ep # وضع الوقف على الدخول
                        self.trade['breakeven'] = True
                        self.trk.debug(f"🛡️ تم تأمين الصفقة على نقطة الدخول")

                    # 4. الوقف المتحرك المريح (Trailing Stop) بعد ربح 3%
                    if hpp >= 3.0:
                        trail_pct = 1.5 / 100 # مسافة الوقف المتحرك 1.5%
                        if d == 'long':
                            nsl = self.trade['hp'] * (1 - trail_pct)
                            if nsl > self.trade['sl']: self.trade['sl'] = nsl
                        else:
                            nsl = self.trade['lp'] * (1 + trail_pct)
                            if nsl < self.trade['sl']: self.trade['sl'] = nsl

                    # 5. إنهاء الصفقات المملة (Timeout) بعد 4 ساعات
                    if time.time() - self.trade['time'] > 14400:
                        self.close("إنهاء الوقت (السعر لا يتحرك)", pp, loss=(pp < 0))
                        continue

            except Exception as e:
                self.trk.debug(f"⚠️ خطأ: {e}")
            
            time.sleep(10)

if __name__ == "__main__":
    bot = FuturesBot()
    bot.run()
