import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V14.0 (SMA Cross + Stochastic Cross + Session Filter)
    ================================================================
    - كسر SMA10 × SMA20 يجب أن يصاحبه كسر Stochastic K×D
    - الستوكاستيك: الكسر فوق 70 لهبوط، تحت 30 لصعود
    - فلتر أوقات التداول: جلسة لندن + نيويورك فقط
    - فلتر أخبار: يتجنب الأخبار المتوسطة والعالية الأهمية
    - مدة الصفقة: دقيقتان
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

        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'scans': 0, 'skipped_session': 0, 'skipped_news': 0}
        self.report_time = time.time()
        self.news_cache = []
        self.news_cache_time = 0
        self.COOLDOWN_SEC = 180

        # أوقات التداول الجيدة (بتوقيت ليبيا GMT+2)
        # جلسة لندن: 09:00 - 13:00
        # جلسة نيويورك: 15:30 - 21:00
        # التداخل (الأفضل): 15:30 - 17:00
        self.GOOD_SESSIONS = [
            (9, 0, 13, 0),      # لندن
            (15, 30, 21, 0),    # نيويورك
        ]

        msg  = "🎯 *بوت القناص V14*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🕐 التوقيت: ليبيا (GMT+2)\n"
        msg += f"📋 مراقبة {len(self.SYMBOLS_MAP)} زوج\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "🧠 *الاستراتيجية:*\n"
        msg += "1️⃣ `SMA 10` 🔴 يكسر `SMA 20` 🟡\n"
        msg += "2️⃣ `Stoch K` يكسر `Stoch D`\n"
        msg += "   🔴 فوق 70 كسر لاسفل = هبوط\n"
        msg += "   🟢 تحت 30 كسر لاعلى = صعود\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "⏰ *اوقات العمل:*\n"
        msg += "🇬🇧 لندن: 09:00 - 13:00\n"
        msg += "🇺🇸 نيويورك: 15:30 - 21:00\n"
        msg += "📰 فلتر اخبار: مفعل ✅\n"
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
    #                   فلتر أوقات التداول
    # ================================================================

    def _is_good_session(self):
        """يتحقق هل الوقت الحالي ضمن أوقات التداول الجيدة"""
        now = datetime.datetime.now(self.TZ)
        h, m = now.hour, now.minute
        current_min = h * 60 + m

        for start_h, start_m, end_h, end_m in self.GOOD_SESSIONS:
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m
            if start_min <= current_min < end_min:
                return True, "لندن" if start_h == 9 else "نيويورك"

        return False, None

    # ================================================================
    #                   فلتر الأخبار
    # ================================================================

    def _fetch_news(self):
        """يجلب أخبار الأسبوع من Faireconomy (مجاني، بدون API key)"""
        try:
            r = requests.get(
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                self.news_cache = data
                self.news_cache_time = time.time()
                self.log(f"News updated: {len(data)} events loaded")
                return data
        except Exception as e:
            self.log(f"News fetch err: {str(e)[:40]}")
        return self.news_cache

    def _is_news_safe(self):
        """يتحقق هل السوق آمن (لا أخبار مهمة خلال 30 دقيقة)"""
        now = datetime.datetime.now(self.TZ)

        # تحديث الكاش كل 15 دقيقة
        if time.time() - self.news_cache_time > 900:
            self._fetch_news()

        if not self.news_cache:
            return True, None

        for n in self.news_cache:
            try:
                # وقت الخبر بـ UTC
                news_str = n.get('date', '')
                if not news_str:
                    continue

                # تحويل إلى توقيت ليبيا
                news_utc = datetime.datetime.strptime(
                    news_str[:19], '%Y-%m-%dT%H:%M:%S'
                ).replace(tzinfo=ZoneInfo("UTC"))
                news_libya = news_utc.astimezone(self.TZ)

                # الفرق بالدقائق بين الآن ووقت الخبر
                diff_min = (news_libya - now).total_seconds() / 60

                # إذا كان الخبر خلال 30 دقيقة القادمة
                if -5 < diff_min < 30:
                    impact = n.get('impact', '').strip()
                    # تجنب الأخبار المتوسطة والعالية
                    if impact in ['High', 'Medium', 'HIGH', 'MEDIUM']:
                        title = n.get('title', 'Unknown')
                        return False, title

            except Exception:
                continue

        return True, None

    # ================================================================
    #                   جلب بيانات الدقيقة
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
    #      🎯 الاستراتيجية: كسر مزدوج (موفينج + ستوكاستيك)
    # ================================================================

    def _analyze_symbol(self, df):
        if df is None or len(df) < 25:
            return None, 0

        try:
            df = df.rename(columns={
                'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close'
            }).copy()

            # SMA 10 (أحمر) و SMA 20 (أصفر)
            df['sma10'] = ta.trend.sma_indicator(df['Close'], window=10)
            df['sma20'] = ta.trend.sma_indicator(df['Close'], window=20)

            # Stochastic (14, 3, 3)
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
                return None, price

            # === كسر الموفينج ===
            ma_cross_down = (prev['sma10'] >= prev['sma20']) and (cur['sma10'] < cur['sma20'])
            ma_cross_up = (prev['sma10'] <= prev['sma20']) and (cur['sma10'] > cur['sma20'])

            # === كسر الستوكاستيك ===
            stoch_cross_down = (prev['stoch_k'] >= prev['stoch_d']) and (cur['stoch_k'] < cur['stoch_d'])
            stoch_cross_up = (prev['stoch_k'] <= prev['stoch_d']) and (cur['stoch_k'] > cur['stoch_d'])

            # ==========================================
            # 🔴 هبوط (PUT)
            # كسر موفينج لتحت + كسر ستوكاستيك لتحت فوق منطقة 70
            # ==========================================
            if ma_cross_down and stoch_cross_down and prev['stoch_k'] > 70:
                self.log(
                    f"  >> PUT: MA10({cur['sma10']:.5f})xMA20({cur['sma20']:.5f}) DOWN "
                    f"+ Stoch K({prev['stoch_k']:.1f})xD({prev['stoch_d']:.1f}) DOWN above 70"
                )
                return 'PUT', price

            # ==========================================
            # 🟢 صعود (CALL)
            # كسر موفينج لفوق + كسر ستوكاستيك لفوق تحت منطقة 30
            # ==========================================
            if ma_cross_up and stoch_cross_up and prev['stoch_k'] < 30:
                self.log(
                    f"  >> CALL: MA10({cur['sma10']:.5f})xMA20({cur['sma20']:.5f}) UP "
                    f"+ Stoch K({prev['stoch_k']:.1f})xD({prev['stoch_d']:.1f}) UP below 30"
                )
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

        decimals = 5 if 'USD' in api_sym and 'USDT' not in api_sym else 2

        # تحديد الجلسة الحالية
        is_session, session_name = self._is_good_session()

        msg  = f"{icon} *إشارة {direction} {arrow}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الاتجاه: *{direction}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}* (2 دقيقة)\n"
        msg += f"💵 السعر: `{price:.{decimals}f}`\n"
        msg += f"🧠 `SMA10xSMA20 + Stoch Cross`\n"
        msg += f"🌍 الجلسة: *{session_name}*\n"
        msg += f"📰 الأخبار: آمنة ✅\n"
        msg += f"━━━━━━━━━━━━━━━━"

        self.tg(msg)
        self.log(f">>>> SIGNAL: {qx_sym} {direction} @ {price:.{decimals}f}")

    # ================================================================
    #                    إشعار تجاهل الإشارة
    # ================================================================

    def _notify_skipped(self, reason, detail=""):
        """يرسل إشعار صامت عند تجاهل إشارة بسبب فلتر"""
        now = self._get_time()
        if reason == 'news':
            self.log(f"⛔ BLOCKED by NEWS: {detail}")
        elif reason == 'session':
            self.stats['skipped_session'] += 1

    # ================================================================
    #                            التشغيل الرئيسي
    # ================================================================

    def run(self):
        self.log("SNIPER V14 STARTED - Double Cross + Session + News Filter")
        self.log(f"Monitoring {len(self.SYMBOLS_MAP)} pairs on 1-minute timeframe...")

        # جلب الأخبار عند البدء
        self._fetch_news()

        while True:
            try:
                self.stats['scans'] += 1
                cycle_signals = 0

                # === الفحص الأول: هل نحن في وقت تداول جيد؟ ===
                is_session, session_name = self._is_good_session()
                if not is_session:
                    self._notify_skipped('session')
                    # خارج أوقات التداول: ننتظر دقيقة ونرجع نتحقق
                    time.sleep(60)
                    continue

                # === الفحص الثاني: هل هناك أخبار قريبة؟ ===
                is_safe, news_title = self._is_news_safe()
                if not is_safe:
                    self.stats['skipped_news'] += 1
                    self._notify_skipped('news', news_title)
                    # أخبار قريبة: ننتظر 5 دقائق ونرجع نتحقق
                    self.tg(
                        f"⛔ *إشارات متوقفة مؤقتاً*\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"📰 سبب: خبر قادم\n"
                        f"📝 {news_title}\n"
                        f"⏳ ستعود بعد 5 دقائق..."
                    )
                    time.sleep(300)
                    continue

                # === كل شيء جيد - نحلل الأزواج ===
                for api_sym, qx_sym in self.SYMBOLS_MAP.items():

                    if api_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                            continue

                    df = self._get_1m_data(api_sym)
                    if df is None:
                        continue

                    direction, price = self._analyze_symbol(df)

                    if direction and price > 0:
                        self._send_signal(api_sym, qx_sym, direction, price)
                        cycle_signals += 1

                    time.sleep(0.8)

                # تقرير ساعة
                if time.time() - self.report_time >= 3600:
                    self.tg(
                        f"📊 *تقرير ساعة*\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"🔍 فحوصات: {self.stats['scans']}\n"
                        f"🎯 إشارات: {self.stats['signals_sent']}\n"
                        f"⛔ محجوبة (خارج جلسة): {self.stats['skipped_session']}\n"
                        f"📰 محجوبة (أخبار): {self.stats['skipped_news']}\n"
                        f"━━━━━━━━━━━━━━━━"
                    )
                    self.report_time = time.time()

                if cycle_signals > 0:
                    self.log(f"Cycle done - {cycle_signals} signal(s)")
                else:
                    self.log("Cycle done - no valid double-cross signals")

            except Exception as e:
                self.log(f"MAIN LOOP ERR: {e}")
                time.sleep(10)

            # فحص كل 30 ثانية داخل أوقات التداول
            time.sleep(30)

    def _is_good_session(self):
        now = datetime.datetime.now(self.TZ)
        h, m = now.hour, now.minute
        current_min = h * 60 + m

        for start_h, start_m, end_h, end_m in self.GOOD_SESSIONS:
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m
            if start_min <= current_min < end_min:
                return True, "لندن 🇬🇧" if start_h == 9 else "نيويورك 🇺🇸"

        return False, None


if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
