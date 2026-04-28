import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V14 (تقاطع متتابع - المرحلتين)
    =============================================
    المرحلة 1: الستوكاستيك يدخل منطقة التشبع (فوق 70 أو تحت 30)
    المرحلة 2: بعد شمعات، الموفينج افرج 10 يقطع 20 → إشارة
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return

        self.TZ = ZoneInfo("Africa/Tripoli")

        self.SYMBOLS_MAP = {
            'BTC/USDT': 'BTCUSD(t)',
            'ETH/USDT': 'ETHUSD(t)',
            'BNB/USDT': 'BNBUSD(t)',
            'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)',
            'DOGE/USDT': 'DOGEUSD(t)',
            'ADA/USDT': 'ADAUSD(t)',
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

        # ===== ذاكرة المرحلتين لكل زوج =====
        # المفتاح: اسم الزوج
        # القيمة: 'PUT_READY' أو 'CALL_READY' أو None
        self.stage_memory = {}
        # لحفظ وقت دخول المرحلة 1 لكل زوج (عشان نلغي بعد 15 دقيقة)
        self.stage_time = {}

        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'stage1_hits': 0, 'scans': 0}
        self.report_time = time.time()
        self.COOLDOWN_SEC = 180  # 3 دقائق مهلة بين الإشارات
        self.STAGE_TIMEOUT = 900  # 15 دقيقة أقصى انتظار للمرحلة 2

        msg  = "🎯 *بوت القناص V14 (المرحلتين)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.SYMBOLS_MAP)} زوج\n"
        msg += "🧠 الاستراتيجية (تقاطع متتابع):\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "📍 *المرحلة 1*: ستوكاستيك يدخل تشبع\n"
        msg += "   🔴 فوق 70 → جاهز لهبوط\n"
        msg += "   🟢 تحت 30 → جاهز لصعود\n"
        msg += "📍 *المرحلة 2*: موفينج يقطع بعده\n"
        msg += "   SMA10 🔴 يقطع SMA20 🟡 لتحت\n"
        msg += "   SMA10 🔴 يقطع SMA20 🟡 لفوق\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "⏱️ مدة الصفقة: *دقيقتان*\n"
        msg += "⏳ أقصى انتظار: *15 دقيقة*\n"
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
    #      🎯 استراتيجية المرحلتين المتتابعتين
    # ================================================================

    def _analyze_symbol(self, api_sym, qx_sym, df):
        """
        يعيد 3 قيم:
        - direction: 'CALL' أو 'PUT' أو None
        - price: السعر الحالي
        - stage_msg: رسالة توضيحية عن المرحلة الحالية
        """
        stage_msg = None

        if df is None or len(df) < 25:
            return None, 0, "بيانات غير كافية"

        try:
            df = df.rename(columns={
                'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close'
            }).copy()

            # حساب المؤشرات
            df['sma10'] = ta.trend.sma_indicator(df['Close'], window=10)
            df['sma20'] = ta.trend.sma_indicator(df['Close'], window=20)

            stoch = ta.momentum.StochasticOscillator(
                high=df['High'], low=df['Low'], close=df['Close'],
                window=14, smooth_window=3
            )
            df['stoch_k'] = stoch.stoch()
            df['stoch_d'] = stoch.stoch_signal()

            cur = df.iloc[-1]
            prev = df.iloc[-2]
            price = cur['Close']

            if pd.isna(cur['sma10']) or pd.isna(cur['sma20']) or pd.isna(cur['stoch_k']):
                return None, price, "بيانات ناقصة (NaN)"

            now = time.time()

            # ==========================================
            # التحقق من انتهاء صلاحية المرحلة 1
            # ==========================================
            if api_sym in self.stage_memory and self.stage_memory[api_sym] is not None:
                elapsed = now - self.stage_time.get(api_sym, 0)
                if elapsed > self.STAGE_TIMEOUT:
                    old_stage = self.stage_memory[api_sym]
                    self.stage_memory[api_sym] = None
                    stage_msg = f"⏰ انتهت صلاحية المرحلة1 ({old_stage}) بعد {elapsed/60:.0f} دقيقة - إعادة تعيين"
                    return None, price, stage_msg

            # ==========================================
            # المرحلة 1: فحص الستوكاستيك
            # ==========================================

            stoch_k_cur = cur['stoch_k']
            stoch_k_prev = prev['stoch_k']

            # --- هبوط: ستوك يكسر فوق 70 ---
            stoch_broke_above70 = (stoch_k_prev <= 70) and (stoch_k_cur > 70)
            stoch_already_above70 = (stoch_k_cur > 70) and (self.stage_memory.get(api_sym) != 'PUT_READY')

            if stoch_broke_above70 or stoch_already_above70:
                self.stage_memory[api_sym] = 'PUT_READY'
                self.stage_time[api_sym] = now
                self.stats['stage1_hits'] += 1
                stage_msg = f"🔴 المرحلة1: ستوك دخل فوق 70 ({stoch_k_cur:.1f}) → ينتظر تقاطع موفينج لتحت"
                return None, price, stage_msg

            # --- صعود: ستوك يكسر تحت 30 ---
            stoch_broke_below30 = (stoch_k_prev >= 30) and (stoch_k_cur < 30)
            stoch_already_below30 = (stoch_k_cur < 30) and (self.stage_memory.get(api_sym) != 'CALL_READY')

            if stoch_broke_below30 or stoch_already_below30:
                self.stage_memory[api_sym] = 'CALL_READY'
                self.stage_time[api_sym] = now
                self.stats['stage1_hits'] += 1
                stage_msg = f"🟢 المرحلة1: ستوك دخل تحت 30 ({stoch_k_cur:.1f}) → ينتظر تقاطع موفينج لفوق"
                return None, price, stage_msg

            # ==========================================
            # المرحلة 2: فحص تقاطع الموفينج افرج
            # (فقط إذا كنا في المرحلة 1)
            # ==========================================

            current_stage = self.stage_memory.get(api_sym)

            if current_stage == 'PUT_READY':
                # ننتظر SMA10 يقطع SMA20 لتحت
                cross_down = (prev['sma10'] >= prev['sma20']) and (cur['sma10'] < cur['sma20'])
                if cross_down:
                    # نجح! إشارة هبوط
                    self.stage_memory[api_sym] = None  # مسح الذاكرة
                    stage_msg = f"🎯 المرحلة2: تقاطع هبوطي مؤكد! SMA10={cur['sma10']:.5f} قطع SMA20={cur['sma20']:.5f}"
                    return 'PUT', price, stage_msg
                else:
                    # لا يزال ينتظر
                    dist = abs(cur['sma10'] - cur['sma20'])
                    stage_msg = f"🔴 ينتظر تقاطع هبوطي... الفرق بين الموفينجين: {dist:.5f}"

            elif current_stage == 'CALL_READY':
                # ننتظر SMA10 يقطع SMA20 لفوق
                cross_up = (prev['sma10'] <= prev['sma20']) and (cur['sma10'] > cur['sma20'])
                if cross_up:
                    # نجح! إشارة صعود
                    self.stage_memory[api_sym] = None
                    stage_msg = f"🎯 المرحلة2: تقاطع صعودي مؤكد! SMA10={cur['sma10']:.5f} قطع SMA20={cur['sma20']:.5f}"
                    return 'CALL', price, stage_msg
                else:
                    dist = abs(cur['sma10'] - cur['sma20'])
                    stage_msg = f"🟢 ينتظر تقاطع صعودي... الفرق بين الموفينجين: {dist:.5f}"

            else:
                stage_msg = f"⏳ ستوك خارج المناطق ({stoch_k_cur:.1f}) - ينتظر دخول منطقة تشبع"

        except Exception as e:
            return None, 0, f"خطأ تحليل: {str(e)[:30]}"

        return None, 0, stage_msg

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

        decimals = 5 if 'USD' in api_sym and 'USDT' not in api_sym else 2

        msg  = f"{icon} *إشارة {direction} {arrow}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}* (2 دقيقة)\n"
        msg += f"💵 السعر: `{price:.{decimals}f}`\n"
        msg += f"🧠 `تقاطع متتابع (مرحلتين)`\n"
        msg += f"━━━━━━━━━━━━━━━━"

        self.tg(msg)
        self.log(f">>>> SIGNAL FIRED: {qx_sym} {direction} @ {price:.{decimals}f}")

    # ================================================================
    #                            التشغيل الرئيسي
    # ================================================================

    def run(self):
        self.log("SNIPER V14 STARTED - Two-Stage Sequential Strategy")
        self.log(f"Monitoring {len(self.SYMBOLS_MAP)} pairs on 1-minute timeframe...")
        self.log("========================================")

        while True:
            try:
                self.stats['scans'] += 1
                active_stages = 0
                cycle_signals = 0

                for api_sym, qx_sym in self.SYMBOLS_MAP.items():

                    # حماية الـ Cooldown بعد إشارة
                    if api_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                            continue

                    # جلب البيانات
                    df = self._get_1m_data(api_sym)
                    if df is None:
                        continue

                    # التحليل بمرحلتيه
                    direction, price, stage_msg = self._analyze_symbol(api_sym, qx_sym, df)

                    # طباعة حالة كل زوج (مختصرة)
                    if stage_msg:
                        short_sym = api_sym.split('/')[0]
                        if 'المرحلة1' in stage_msg or '🎯' in stage_msg or '⏰' in stage_msg:
                            self.log(f"  [{short_sym}] {stage_msg}")
                        elif self.stage_memory.get(api_sym):
                            active_stages += 1

                    # إطلاق الإشارة إذا اكتملت المرحلتين
                    if direction and price > 0:
                        self._send_signal(api_sym, qx_sym, direction, price)
                        cycle_signals += 1

                    time.sleep(0.5)

                # ملخص الدورة
                self.log(f"--- دورة #{self.stats['scans']} | مراقب نشط: {active_stages} | إشارات: {cycle_signals} ---")

                # تقرير ساعة لتيليجرام
                if time.time() - self.report_time >= 3600:
                    self.tg(
                        f"📊 *تقرير ساعة - V14*\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"🔍 فحوصات: {self.stats['scans']}\n"
                        f"📍 مراحل أولى: {self.stats['stage1_hits']}\n"
                        f"🎯 إشارات أُطلقت: {self.stats['signals_sent']}\n"
                        f"⏳ مراقب نشط الآن: {active_stages}\n"
                        f"━━━━━━━━━━━━━━━━"
                    )
                    self.report_time = time.time()

            except Exception as e:
                self.log(f"MAIN LOOP ERR: {e}")
                time.sleep(10)

            # انتظار 30 ثانية
            time.sleep(30)


if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
