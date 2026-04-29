import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V17 (النسخة النهائية - TwelveData & Engulfing)
    =============================================================
    - مصدر البيانات: Twelve Data API (فوركس حقيقي).
    - فلتر إلزامي: شمعة الابتلاعية (Engulfing).
    - نظام توقيت دقيق: الإشارة في الثانية 58.
    - محترم للحدود المجانية: 8 طلبات كحد أقصى في الدقيقة.
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        self.twelve_api_key = os.environ.get('TWELVE_DATA_API_KEY')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return
        if not self.twelve_api_key:
            print("[FATAL ERROR] Missing TWELVE_DATA_API_KEY!")
            return

        self.TZ = ZoneInfo("Africa/Tripoli")

        # أزواج الفوركس الحقيقية فقط (بدون OTC)
        self.SYMBOLS_MAP = {
            'EUR/USD': 'EUR/USD',
            'GBP/JPY': 'GBP/JPY',
            'USD/CAD': 'USD/CAD',
            'EUR/GBP': 'EUR/GBP',
            'USD/CHF': 'USD/CHF',
            'AUD/USD': 'AUD/USD',
            'GBP/USD': 'GBP/USD'
        }

        self.pair_list = list(self.SYMBOLS_MAP.keys())

        # ===== إعدادات الجلسات =====
        self.morning_slots = [480, 510, 540, 570, 600]
        self.evening_slots = [1020, 1050, 1080, 1110, 1140]
        self.all_slots = self.morning_slots + self.evening_slots

        self.completed_windows = set()
        self.daily_signal_count = 0
        self.current_day = datetime.datetime.now(self.TZ).day

        self.stage_memory = {}
        self.stage_time = {}
        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'stage1_hits': 0}
        self.report_time = time.time()
        self.COOLDOWN_SEC = 180
        self.STAGE_TIMEOUT = 900
        
        self.last_checked_minute = -1

        # متغيرات نظام التحديث الخلفي للبيانات (Background Fetcher)
        self.latest_data = {}
        self.api_cycle_index = 0
        self.last_api_call_time = 0

        # اختبار الاتصال عند الإطلاق
        if self._test_connection():
            self.log("Connected to TwelveData Successfully")
            msg  = "🧠 *بوت القناص V17 (النهائي)*\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += "✅ تم الاتصال بـ TwelveData\n"
            msg += "📈 7 أزواج فوركس حقيقية\n"
            msg += "🔥 فلتر الشموع الابتلاعية: مفعّل\n"
            msg += "📅 الصباح: 08:00 - 10:00\n"
            msg += "📅 المساء: 17:00 - 19:00\n"
            msg += "━━━━━━━━━━━━━━━━\n"
            msg += "🚀 جاهز للعمل..."
            self.tg(msg)
        else:
            self.log("Failed to connect to TwelveData!")
            self.tg("❌ *فشل الاتصال*\n━━━━━━━━━━━━━━━━\nتأكد من صحة `TWELVE_DATA_API_KEY`")

    def _get_time(self):
        return datetime.datetime.now(self.TZ)

    def _get_time_str(self):
        return self._get_time().strftime("%H:%M:%S")

    def tg(self, msg):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'},
                timeout=5
            )
        except:
            pass

    def log(self, msg):
        print(f"[{self._get_time_str()}] {msg}")

    # ================================================================
    #                   الربط بـ Twelve Data
    # ================================================================

    def _test_connection(self):
        sym = self.pair_list[0]
        df = self._fetch_twelve_data(sym)
        if df is not None:
            self.latest_data[sym] = df
            return True
        return False

    def _fetch_twelve_data(self, sym):
        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': sym,
            'interval': '1min',
            'outputsize': 30,
            'apikey': self.twelve_api_key
        }
        try:
            r = requests.get(url, params=params, timeout=5)
            d = r.json()
            if 'values' in d and len(d['values']) >= 25:
                raw = d['values']
                raw.reverse() # Twelve Data ترسل الأحدث أولاً، نعكسها للمكتبة
                df = pd.DataFrame(raw, columns=['datetime', 'open', 'high', 'low', 'close'])
                df['time'] = pd.to_datetime(df['datetime'])
                df = df.drop(columns=['datetime'])
                return df
        except Exception as e:
            self.log(f"API Err {sym}: {str(e)[:30]}")
        return None

    # ================================================================
    #               أدوات الجدولة الزمنية
    # ================================================================

    def _get_current_slot_minutes(self):
        now = self._get_time()
        return now.hour * 60 + now.minute

        def _get_next_slot_time(self):
        current_mins = self._get_current_slot_minutes()
        # البحث عن أقرب جلسة قادمة في نفس اليوم
        for slot in self.all_slots:
            if slot > current_mins:
                return slot
        # إذا لم يجد (يعني انتهت جلسات اليوم)، نعود لأول جلسة في صباح اليوم التالي (480 = 08:00)
        return self.morning_slots[0]

    def _get_session_name(self, slot_mins):
        if slot_mins in self.morning_slots:
            idx = self.morning_slots.index(slot_mins) + 1
            return f"☀️ صباحية - النافذة {idx}/5"
        else:
            idx = self.evening_slots.index(slot_mins) + 1
            return f"🌙 مسائية - النافذة {idx}/5"

    # ================================================================
    #      الاستراتيجية (ستوكاستيك + تقاطع + ابتلاعية إلزامية)
    # ================================================================

    def _analyze_symbol(self, api_sym, df):
        if df is None or len(df) < 25: return None, 0, ""

        try:
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}).copy()
            df['ema10'] = ta.trend.ema_indicator(df['Close'], window=10)
            df['ema20'] = ta.trend.ema_indicator(df['Close'], window=20)
            stoch = ta.momentum.StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
            df['stoch_k'] = stoch.stoch()

            cur = df.iloc[-1]
            prev = df.iloc[-2]
            price = cur['Close']

            if pd.isna(cur['ema10']) or pd.isna(cur['stoch_k']): return None, price, ""

            now = time.time()
            if api_sym in self.stage_memory and self.stage_memory[api_sym] is not None:
                if now - self.stage_time.get(api_sym, 0) > self.STAGE_TIMEOUT:
                    self.stage_memory[api_sym] = None

            stoch_k_cur = cur['stoch_k']

            # المرحلة 1
            if (stoch_k_cur > 70 and self.stage_memory.get(api_sym) != 'PUT_READY'):
                self.stage_memory[api_sym] = 'PUT_READY'
                self.stage_time[api_sym] = now
                self.stats['stage1_hits'] += 1

            if (stoch_k_cur < 30 and self.stage_memory.get(api_sym) != 'CALL_READY'):
                self.stage_memory[api_sym] = 'CALL_READY'
                self.stage_time[api_sym] = now
                self.stats['stage1_hits'] += 1

            # حساب الشمعة الابتلاعية (Engulfing)
            is_bearish_engulfing = (cur['Close'] < cur['Open']) and (prev['Close'] > prev['Open']) and (cur['Open'] >= prev['Close']) and (cur['Close'] <= prev['Open'])
            is_bullish_engulfing = (cur['Close'] > cur['Open']) and (prev['Close'] < prev['Open']) and (cur['Open'] <= prev['Close']) and (cur['Close'] >= prev['Open'])

            # المرحلة 2 (لا يتم إطلاق الإشارة إلا بتوافر الابتلاعية مع التقاطع)
            current_stage = self.stage_memory.get(api_sym)

            if current_stage == 'PUT_READY':
                cross_down = (prev['ema10'] >= prev['ema20']) and (cur['ema10'] < cur['ema20'])
                if cross_down and is_bearish_engulfing:
                    self.stage_memory[api_sym] = None
                    return 'PUT', price, "تقاطع + شمعة ابتلاعية 🔥"
                    
            elif current_stage == 'CALL_READY':
                cross_up = (prev['ema10'] <= prev['ema20']) and (cur['ema10'] > cur['ema20'])
                if cross_up and is_bullish_engulfing:
                    self.stage_memory[api_sym] = None
                    return 'CALL', price, "تقاطع + شمعة ابتلاعية 🔥"

        except:
            pass
        return None, 0, ""

    def _send_signal(self, api_sym, qx_sym, direction, price, confirmation, session_name):
        self.stats['signals_sent'] += 1
        self.last_signal_time[api_sym] = time.time()
        self.daily_signal_count += 1

        icon = "🟢" if direction == 'CALL' else "🔴"
        arrow = "⬆️" if direction == 'CALL' else "⬇️"
        now_libya = self._get_time()
        expiry_time = now_libya + datetime.timedelta(minutes=2)

        msg  = f"⚡ *إشارة {direction} {arrow}*\n"
        msg += f"━━━━━━━━━━━━━━━━\n"
        msg += f"🪙 الزوج: *{qx_sym}*\n"
        msg += f"📊 الجلسة: *{session_name}*\n"
        msg += f"🎯 إشارة رقم: *{self.daily_signal_count}/10*\n"
        msg += f"🔑 التأكيد: *{confirmation}*\n"
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}*\n"
        msg += f"💵 السعر: `{price:.5f}`\n"
        msg += f"━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        self.log(f">>>> SIGNAL: {qx_sym} {direction} | {session_name}")

    # ================================================================
    #               التشغيل الرئيسي (المحرك الذكي)
    # ================================================================

    def run(self):
        self.log("SNIPER V17 STARTED - TwelveData & Engulfing Filter")
        self.log("========================================")

        while True:
            try:
                now = self._get_time()
                current_mins = now.hour * 60 + now.minute
                current_sec = now.second

                # ==========================================
                # 0. محرك تحديث البيانات الخلفي (8 ثواني بين كل طلب)
                # ==========================================
                if time.time() - self.last_api_call_time >= 8:
                    sym_to_fetch = self.pair_list[self.api_cycle_index % len(self.pair_list)]
                    df = self._fetch_twelve_data(sym_to_fetch)
                    if df is not None:
                        self.latest_data[sym_to_fetch] = df
                    self.api_cycle_index += 1
                    self.last_api_call_time = time.time()

                # ==========================================
                # 1. إعادة تعيين العداد في منتصف الليل
                # ==========================================
                if now.day != self.current_day:
                    self.current_day = now.day
                    self.daily_signal_count = 0
                    self.completed_windows = set()
                    self.stage_memory = {} 
                    self.log("🔄 يوم جديد! تم إعادة تعيين العداد (0/10).")
                    self.tg("🌅 *صباح الخير*\n━━━━━━━━━━━━━━━━\n🔄 بدء يوم جديد\nالهدف: 10 إشارات دقيقة\n━━━━━━━━━━━━━━━━")

                # ==========================================
                # 2. إذا أكملنا 10 إشارات (استراحة مع بقاء التحديث)
                # ==========================================
                if self.daily_signal_count >= 10:
                    if current_mins < self.morning_slots[0]:
                        pass 
                    else:
                        if current_mins % 15 == 0 and current_sec < 2:
                            self.log("🏆 تم إنجاز الهدف! البوت في استراحة حتى الغد...")
                        time.sleep(10) # نوم قصير لنبقي محرك البيانات يعمل
                        continue

                # ==========================================
                # 3. البحث عن النافذة الحالية
                # ==========================================
                current_slot = None
                for slot in self.all_slots:
                    if slot <= current_mins < slot + 30:
                        current_slot = slot
                        break

                # ==========================================
                # 4. وقت الاستراحة (ليس في أي نافذة)
                # ==========================================
                if current_slot is None:
                    next_slot_mins = self._get_next_slot_time()
                    next_hour = next_slot_mins // 60
                    next_min = next_slot_mins % 60
                    session_name = self._get_session_name(next_slot_mins)
                    
                    if current_mins % 15 == 0 and current_sec < 2:
                        self.log(f"⏳ استراحة... الجلسة القادمة: {session_name} الساعة {next_hour:02d}:{next_min:02d}")
                    
                    time.sleep(10)
                    continue

                # ==========================================
                # 5. النافذة مكتملة (تم إطلاق إشارة بها)
                # ==========================================
                if current_slot in self.completed_windows:
                    time.sleep(10)
                    continue

                # ==========================================
                # 6. نحن في نافذة صالحة - الفحص في الثانية 58 فقط
                # ==========================================
                session_name = self._get_session_name(current_slot)
                
                if current_sec == 58:
                    if current_mins != self.last_checked_minute:
                        self.last_checked_minute = current_mins
                        self.log(f"🔥 [الثانية 58] تحليل البيانات... ({session_name})")
                        
                        for api_sym in self.pair_list:
                            if api_sym not in self.latest_data:
                                continue
                            if api_sym in self.last_signal_time:
                                if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                                    continue

                            df = self.latest_data[api_sym]
                            direction, price, confirmation = self._analyze_symbol(api_sym, df)
                            
                            if direction and price > 0:
                                qx_sym = self.SYMBOLS_MAP[api_sym]
                                self._send_signal(api_sym, qx_sym, direction, price, confirmation, session_name)
                                self.completed_windows.add(current_slot)
                                break 

                time.sleep(1) # دورة سريعة جداً لضمان عدم تفويت الثانية 58

            except Exception as e:
                self.log(f"ERR: {e}")
                time.sleep(10)


if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token and bot.twelve_api_key:
        bot.run()
