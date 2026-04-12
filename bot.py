import ccxt, time, pandas as pd, ta, requests, datetime, os

# ==============================
# 📊 Tracker
# ==============================
class Tracker:
    def __init__(self, t, c, ex):
        self.T, self.C, self.ex = t, c, ex
        self.last_signal_time = time.time()

    def send(self, m):
        try:
            requests.post(f"https://api.telegram.org/bot{self.T}/sendMessage",
                          data={'chat_id': self.C, 'text': m})
        except:
            pass

    def debug(self, msg):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

    def no_signal_alert(self):
        if time.time() - self.last_signal_time > 7200:
            self.send("⚠️ لا توجد صفقات منذ ساعتين")
            self.last_signal_time = time.time()

# ==============================
# 🤖 BOT
# ==============================
class Bot:
    def __init__(self):
        self.K = os.getenv("API_KEY")
        self.S = os.getenv("API_SECRET")
        self.T = os.getenv("TELEGRAM_TOKEN")
        self.C = os.getenv("CHAT_ID")

        self.ex = ccxt.bingx({
            'apiKey': self.K,
            'secret': self.S,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

        self.trk = Tracker(self.T, self.C, self.ex)

        self.trade = None
        self.losses = 0

        # ⚙️ إعدادات متوازنة
        self.LEVERAGE = 10
        self.RISK = 3.0
        self.LIQ_MIN = 500000

        self.ex.load_markets()

        self.trk.send("🚀 Balanced V8 Started")

    # ==========================
    # 📥 Data
    # ==========================
    def ohlcv(self, s):
        return self.ex.fetch_ohlcv(s, '15m', limit=100)

    def ticker(self, s):
        return self.ex.fetch_ticker(s)

    def balance(self):
        b = self.ex.fetch_balance({'type': 'swap'})
        return float(b['USDT']['free'])

    # ==========================
    # 📈 Trend Filter
    # ==========================
    def trend(self, df):
        ema = ta.trend.ema_indicator(df['c'], 200).iloc[-1]
        return "long" if df['c'].iloc[-1] > ema else "short"

    # ==========================
    # 🎯 Strategy
    # ==========================
    def signal(self, s):
        data = self.ohlcv(s)
        if not data:
            return None

        df = pd.DataFrame(data, columns=['t','o','h','l','c','v'])

        df['rsi'] = ta.momentum.rsi(df['c'], 14)
        df['dc_high'] = df['h'].rolling(20).max()
        df['dc_low'] = df['l'].rolling(20).min()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], 14).average_true_range()

        l = df.iloc[-1]
        p = df.iloc[-2]

        trend = self.trend(df)

        # ✅ Donchian + RSI
        if l['c'] > l['dc_high'] and p['c'] <= p['dc_high'] and l['rsi'] > 50 and trend == "long":
            return ("long", l['c'], l['atr'])

        if l['c'] < l['dc_low'] and p['c'] >= p['dc_low'] and l['rsi'] < 50 and trend == "short":
            return ("short", l['c'], l['atr'])

        return None

    # ==========================
    # 💰 Risk
    # ==========================
    def qty(self, s, atr):
        bal = self.balance()
        risk = bal * (self.RISK / 100)

        sl_dist = atr * 2
        q = risk / sl_dist

        return float(self.ex.amount_to_precision(s, q))

    # ==========================
    # 🛒 Order
    # ==========================
    def order(self, side, s, q):
        try:
            return self.ex.create_market_order(s, side, q)
        except:
            return None

    # ==========================
    # 🔄 Run
    # ==========================
    def run(self):
        while True:
            try:
                if not self.trade:
                    tickers = self.ex.fetch_tickers()

                    # ✅ فلتر سيولة
                    symbols = [
                        s for s, i in tickers.items()
                        if s.endswith('/USDT:USDT')
                        and i.get('quoteVolume')
                        and i['quoteVolume'] * i['last'] > self.LIQ_MIN
                    ]

                    # ✅ ترتيب حسب السيولة
                    symbols = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

                    for s in symbols:
                        sig = self.signal(s)

                        if sig:
                            d, price, atr = sig

                            q = self.qty(s, atr)
                            if q <= 0:
                                continue

                            self.ex.set_leverage(self.LEVERAGE, s)

                            o = self.order('buy' if d == 'long' else 'sell', s, q)

                            if o:
                                sl = price - (atr*2) if d == 'long' else price + (atr*2)

                                self.trade = {
                                    's': s,
                                    'd': d,
                                    'e': price,
                                    'sl': sl,
                                    'q': q,
                                    'time': time.time()
                                }

                                self.trk.send(f"🔥 {d.upper()} {s}\n💵 {price}\n🛑 {sl}")
                                self.trk.last_signal_time = time.time()
                                break

                    if not self.trade:
                        self.trk.no_signal_alert()

                else:
                    s = self.trade['s']
                    d = self.trade['d']
                    cp = self.ticker(s)['last']
                    ep = self.trade['e']

                    pnl = ((cp-ep)/ep*100) if d=='long' else ((ep-cp)/ep*100)

                    # SL
                    if (d=='long' and cp <= self.trade['sl']) or (d=='short' and cp >= self.trade['sl']):
                        self.order('sell' if d=='long' else 'buy', s, self.trade['q'])
                        self.trk.send(f"❌ SL {s} {pnl:.2f}%")
                        self.trade = None
                        continue

                    # TP
                    if pnl >= 5:
                        self.order('sell' if d=='long' else 'buy', s, self.trade['q'])
                        self.trk.send(f"🏆 TP {s} {pnl:.2f}%")
                        self.trade = None
                        continue

                time.sleep(45)

            except Exception as e:
                print("Error:", e)
                time.sleep(30)


if __name__ == "__main__":
    bot = Bot()
    bot.run()
