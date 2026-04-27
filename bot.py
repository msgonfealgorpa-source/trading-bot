import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V13.0 (SMA Cross + Stochastic)
    ==========================================
    - الاستراتيجية: تقاطع SMA10/SMA20 مع فلتر Stochastic 70/30
    - PUT: تقاطع هبوطي + Stoch فوق 70
    - CALL: تقاطع صعودي + Stoch تحت 30
    - مدة الصفقة: دقيقتان
    - الفريم: 1 دقيقة
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return

        self.TZ = ZoneInfo("Africa/Tripoli")

        self.SYMBOLS_MAP = {
            # ======= الكريبتو =======
            'BTC/USDT': 'BTCUSD(t)',
            'ETH/USDT': 'ETHUSD(t)',
            'BNB/USDT': 'BNBUSD(t)',
            'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)',
            'DOGE/USDT': 'DOGEUSD(t)',
            'ADA/USDT': 'ADAUSD(t)',
            # ======= أزواج الفوركس / OTC =======
            'EUR/USD': 'EUR/USD OTC',
            'GBP/USD': 'GBP/USD OTC',
            'USD/JPY': 'USD/JPY OTC',
            'AUD/USD': 'AUD/USD OTC',
            'USD/CAD': 'USD/CAD OTC',
            'EUR/GBP': 'EUR/GBP OTC',
            'NZD/USD': 'NZD/USD OTC',
            'EUR/JPY': 'EUR/JPY OTC',
            'GBP/CAD': 'GBP/CAD OTC',
        }

        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'scans': 0}
        self.report_time = time.time()
        self.COOLDOWN_SEC = 150  # دقيقتان ونصف مهلة بين الإشارات

        msg  = "🎯 *بوت القناص V13*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.SYMBOLS_MAP)} زوج\n"
        msg += "🧠 الاستراتيجية:\n"
        msg += "1️⃣ `SMA 10` 🔴 (أحمر)\n"
        msg += "2️⃣ `SMA 20` 🟡 (أصفر)\n"
        msg += "3️⃣ `Stochastic` فلتر 70/30\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🔴 *هبوط*: تقاطع لتحت + ستوك فوق 70\n"
        msg += "🟢 *صعود*: تقاطع لفوق + ستوك تحت 30\n"
        msg += "⏱️ مدة الصفقة: *دقيقتان*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🚀 جاهز للعمل..."
        self.tg(msg)

    def _get_time(self):
        return datetime.datetime.now(self.TZ).strftime("%H:%M:%S")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'},
                timeout=5
            )
        except Exception as e:
            print(f"[{self._get_time()}] TG Error: {e}")

    def log(self, msg):
        ts = self._get_time()
        print(f"[{ts}] {msg}")

    # ================================================================
    #                   جلب بيانات الدقيقة الواحدة
    # ================================================================

    def _get_1m_data(self, sym):
        """يجلب 100 شمعة دقيقة - كافية لحساب SMA 20 و Stochastic 14"""
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        params = {'fsym': base, 'tsym': quote, 'limit': 100}

        try:
            r = requests.get(url, params=params, timeout=10)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                if not raw:
                    return None
                df = pd.DataFrame(raw, columns=['time', 'open', 'high', 'low', 'close', 'volumeto'])
                df['time'] = pd.to_datetime(df['time'], unit='ms')
                return df
        except Exception as e:
            self.log(f"Data Err {sym}: {str(e)[:40]}")
        return None

    # ================================================================
    #      🎯 استراتيجية تقاطع الموفينج + فلتر الستوكاستيك
    # ================================================================

    def _analyze_symbol(self, df):
        if df is None or len(df) < 25:
            return None, 0

        try:
            df = df.rename(columns={
                'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close'
            }).copy()

            # SMA 10 (الخط الأحمر في كوتيكس)
            df['sma10'] = ta.trend.sma_indicator(df['Close'], window=10)

            # SMA 20 (الخط الأصفر في كوتيكس)
            df['sma20'] = ta.trend.sma_indicator(df['Close'], window=20)

            # Stochastic (14, 3, 3) - نفس الإعدادات في كوتيكس
            stoch = ta.momentum.StochasticOscillator(
                high=df['High'], low=df['Low'], close=df['Close'],
                window=14, smooth_window=3
            )
            df['stoch_k'] = stoch.stoch()
            df['stoch_d'] = stoch.stoch_signal()

            cur = df.iloc[-1]
            prev = df.iloc[-2]
            price = cur['Close']

            # التحقق من عدم وجود قيم فارغة
            if pd.isna(cur['sma10']) or pd.isna(cur['sma20']) or pd.isna(cur['stoch_k']):
                return None, price

            # ==========================================
            # 🔴 إشارة هبوط (PUT)
            # شرط: SMA 10 يقطع SMA 20 للأسفل + الستوكاستيك فوق 70
            # ==========================================
            cross_down = (prev['sma10'] >= prev['sma20']) and (cur['sma10'] < cur['sma20'])
            stoch_over70 = cur['stoch_k'] > 70

            if cross_down and stoch_over70:
                self.log(f"  >> PUT detected: SMA10={cur['sma10']:.5f} crossed under SMA20={cur['sma20']:.5f} | Stoch={cur['stoch_k']:.1f}")
                return 'PUT', price

            # ==========================================
            # 🟢 إشارة صعود (CALL)
            # شرط: SMA 10 يقطع SMA 20 للأعلى + الستوكاستيك تحت 30
            # ==========================================
            cross_up = (prev['sma10'] <= prev['sma20']) and (cur['sma10'] > cur['sma20'])
            stoch_under30 = cur['stoch_k'] < 30

            if cross_up and stoch_under30:
                self.log(f"  >> CALL detected: SMA10={cur['sma10']:.5f} crossed over SMA20={cur['sma20']:.5f} | Stoch={cur['stoch_k']:.1f}")
                return 'CALL', price

        except Exception as e:
            return None, 0

        return None, 0

    # ================================================================
    #                            إرسال الإشارة
    # ================================================================

    def _send_signal(self, api_sym, qx_sym, direction, price):
        self.stats['signals_sent'] += 1
        self.last_signal_time[api_sym] = time.time()

        icon = "🟢" if direction == 'CALL' else "🔴"
        arrow = "⬆️" if direction == 'CALL' else "⬇️"
        now_libya = datetime.datetime.now(self.TZ)
        expiry_time = now_libya + datetime.timedelta(minutes=2)

        # تحديد عدد الخانات العشرية
        decimals = 5 if 'USD' in api_sym and 'USDT' not in api_sym else 2

        msg  = f"{icon} *إشارة {direction} {arrow}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}* (2 دقيقة)\n"
        msg += f"💵 السعر: `{price:.{decimals}f}`\n"
        msg += f"🧠 `SMA10 × SMA20 + Stoch`\n"
        msg += f"━━━━━━━━━━━━━━━━"

        self.tg(msg)
        self.log(f">>>> SIGNAL FIRED: {qx_sym} {direction} @ {price:.{decimals}f}")

    # ================================================================
    #                            التشغيل الرئيسي
    # ================================================================

    def run(self):
        self.log("SNIPER V13 STARTED - SMA Cross + Stochastic Filter")
        self.log(f"Monitoring {len(self.SYMBOLS_MAP)} pairs on 1-minute timeframe...")

        while True:
            try:
                self.stats['scans'] += 1
                cycle_signals = 0

                for api_sym, qx_sym in self.SYMBOLS_MAP.items():

                    # حماية الـ Cooldown
                    if api_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                            continue

                    # 1. جلب البيانات
                    df = self._get_1m_data(api_sym)
                    if df is None:
                        continue

                    # 2. تحليل الاستراتيجية
                    direction, price = self._analyze_symbol(df)

                    # 3. إطلاق الإشارة
                    if direction and price > 0:
                        self._send_signal(api_sym, qx_sym, direction, price)
                        cycle_signals += 1

                    # مهلة صغيرة بين كل زوج
                    time.sleep(0.8)

                # تقرير ساعة
                if time.time() - self.report_time >= 3600:
                    self.tg(
                        f"📊 *تقرير ساعة*\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"🔍 عدد الفحوصات: {self.stats['scans']}\n"
                        f"🎯 إشارات أُطلقت: {self.stats['signals_sent']}\n"
                        f"━━━━━━━━━━━━━━━━"
                    )
                    self.report_time = time.time()

                if cycle_signals > 0:
                    self.log(f"Cycle done - {cycle_signals} signal(s) this round")
                else:
                    self.log("Cycle done - no signals (waiting for crossover + stoch filter)...")

            except Exception as e:
                self.log(f"MAIN LOOP ERR: {e}")
                time.sleep(10)

            # انتظار 30 ثانية لأن الفريم دقيقة واحدة
            time.sleep(30)


if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
