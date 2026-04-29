import time, pandas as pd, ta, requests, datetime, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBot:
    """
    بوت القناص V16 (النسخة المنظمة - 10 إشارات يومياً)
    ======================================================
    - جلسة صباحية: 5 إشارات (تبدأ 08:00 كل نصف ساعة)
    - جلسة مسائية: 5 إشارات (تبدأ 17:00 كل نصف ساعة)
    - إصلاح خلل التوقيت (فحص ديناميكي بدل النوم الثابت)
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')

        if not self.tg_token or not self.tg_chat:
            print("[FATAL ERROR] Missing TELEGRAM_TOKEN or CHAT_ID!")
            return

        self.TZ = ZoneInfo("Africa/Tripoli")

        self.SYMBOLS_MAP = {
            'EUR/CHF': 'EUR/CHF OTC', 'EUR/GBP': 'EUR/GBP OTC',
            'AUD/CAD': 'AUD/CAD OTC', 'AUD/CHF': 'AUD/CHF OTC',
            'NZD/CAD': 'NZD/CAD OTC', 'EUR/AUD': 'EUR/AUD OTC',
            'GBP/CAD': 'GBP/CAD OTC', 'GBP/CHF': 'GBP/CHF OTC',
            'EUR/CAD': 'EUR/CAD OTC', 'AUD/NZD': 'AUD/NZD OTC',
            'NZD/CHF': 'NZD/CHF OTC', 'CAD/CHF': 'CAD/CHF OTC',
        }

        # ===== إعدادات الجلسات (بالوقت المحلي ليبيا) =====
        # تحويل الأوقات إلى دقائق (08:00 = 480 دقيقة)
        self.morning_slots = [480, 510, 540, 570, 600] # 08:00, 08:30, 09:00, 09:30, 10:00
        self.evening_slots = [1020, 1050, 1080, 1110, 1140] # 17:00, 17:30, 18:00, 18:30, 19:00
        self.all_slots = self.morning_slots + self.evening_slots

        self.completed_windows = set() # لتتبع النوافذ اللي تم إطلاق إشارة فيها
        self.daily_signal_count = 0
        self.current_day = datetime.datetime.now(self.TZ).day

        self.stage_memory = {}
        self.stage_time = {}
        self.last_signal_time = {}
        self.stats = {'signals_sent': 0, 'stage1_hits': 0}
        self.report_time = time.time()
        self.COOLDOWN_SEC = 180
        self.STAGE_TIMEOUT = 900
        
        self.last_checked_minute = -1 # لمنع فحص نفس الدقيقة مرتين

        msg  = "🧠 *بوت القناص V16 (المنظم)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "📅 الجدول اليومي:\n"
        msg += "☀️ صباحي: 08:00 - 10:00 (5 إشارات)\n"
        msg += "🌙 مسائي: 17:00 - 19:00 (5 إشارات)\n"
        msg += "⏱️ الفاصل: نصف ساعة بين كل إشارة\n"
        msg += "🚀 وضع الاستراحة مفعل..."
        self.tg(msg)

    def _get_time(self):
        return datetime.datetime.now(self.TZ)

    def _get_time_str(self):
        return self._get_time().strftime("%H:%M:%S")

    async def tg(self, msg):
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
    #               حساب أوقات النوم والانتظار
    # ================================================================

    def _get_current_slot_minutes(self):
        now = self._get_time()
        return now.hour * 60 + now.minute

    def _get_next_slot_time(self):
        current_mins = self._get_current_slot_minutes()
        for slot in self.all_slots:
            if slot > current_mins:
                return slot
        # إذا انتهت كل الأوقات، انتظر صباح اليوم التالي
        return self.morning_slots[0] + (24 * 60)

    def _get_session_name(self, slot_mins):
        if slot_mins in self.morning_slots:
            idx = self.morning_slots.index(slot_mins) + 1
            return f"☀️ صباحية - النافذة {idx}/5"
        else:
            idx = self.evening_slots.index(slot_mins) + 1
            return f"🌙 مسائية - النافذة {idx}/5"

    # ================================================================
    #    جلب البيانات وتحليلها (نفس المنطق المُصلح سابقاً)
    # ================================================================

    def _fetch_single(self, sym):
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        params = {'fsym': base, 'tsym': quote, 'limit': 30}
        try:
            r = requests.get(url, params=params, timeout=5)
            d = r.json()
            if d.get('Response') == 'Success':
                raw = d.get('Data', {}).get('Data', [])
                if raw:
                    df = pd.DataFrame(raw, columns=['time', 'open', 'high', 'low', 'close', 'volumeto'])
                    df['time'] = pd.to_datetime(df['time'], unit='ms')
                    return sym, df
        except:
            pass
        return sym, None

    def _get_all_data_parallel(self):
        data_dict = {}
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(self._fetch_single, sym): sym for sym in self.SYMBOLS_MAP.keys()}
            for future in as_completed(futures):
                sym, df = future.result()
                if df is not None:
                    data_dict[sym] = df
        return data_dict

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

            # المرحلة 2
            current_stage = self.stage_memory.get(api_sym)

            if current_stage == 'PUT_READY':
                cross_down = (prev['ema10'] >= prev['ema20']) and (cur['ema10'] < cur['ema20'])
                if cross_down:
                    self.stage_memory[api_sym] = None
                    return 'PUT', price, "تقاطع EMA"
                    
            elif current_stage == 'CALL_READY':
                cross_up = (prev['ema10'] <= prev['ema20']) and (cur['ema10'] > cur['ema20'])
                if cross_up:
                    self.stage_memory[api_sym] = None
                    return 'CALL', price, "تقاطع EMA"

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
        msg += f"⏱️ الانتهاء: *{expiry_time.strftime('%H:%M:%S')}*\n"
        msg += f"💵 السعر: `{price:.5f}`\n"
        msg += f"━━━━━━━━━━━━━━━━"
        
        self.tg(msg)
        self.log(f">>>> SIGNAL FIRED: {qx_sym} {direction} | {session_name}")

    # ================================================================
    #               التشغيل الرئيسي (المنظم)
    # ================================================================

    def run(self):
        self.log("SNIPER V16 STARTED - Organized Scheduler Active")
        self.log("========================================")

        while True:
            try:
                now = self._get_time()
                current_mins = now.hour * 60 + now.minute
                current_sec = now.second

                # 1. إعادة تعيين العداد في منتصف الليل
                if now.day != self.current_day:
                    self.current_day = now.day
                    self.daily_signal_count = 0
                    self.completed_windows = set()
                    self.stage_memory = {} # مسح ذاكرة المرحلة الأولى لليوم الجديد
                    self.log("🔄 يوم جديد! تم إعادة تعيين العداد (0/10).")
                    self.tg("🌅 *صباح الخير*\n━━━━━━━━━━━━━━━━\n🔄 بدء يوم جديد\nالهدف: 10 إشارات دقيقة\n━━━━━━━━━━━━━━━━")

                # 2. إذا أكملنا 10 إشارات، خذ استراحة حتى الصباح
                if self.daily_signal_count >= 10:
                    if current_mins < self.morning_slots[0]:
                        pass # لا تزال في فترة الصباح، استمر لأسفل
                    else:
                        self.log("🏆 تم إنجاز هدف الـ 10 إشارات! البوت في استراحة حتى الغد...")
                        time.sleep(300) # نم 5 دقائق ثم افحص مرة أخرى
                        continue

                # 3. البحث عن النافذة الحالية
                current_slot = None
                for slot in self.all_slots:
                    if slot <= current_mins < slot + 30:
                        current_slot = slot
                        break

                # 4. إذا لم نكن في أي نافذة (وقت استراحة)
                if current_slot is None:
                    next_slot_mins = self._get_next_slot_time()
                    next_hour = next_slot_mins // 60
                    next_min = next_slot_mins % 60
                    session_name = self._get_session_name(next_slot_mins)
                    
                    # Log every 15 mins
                    if current_min % 15 == 0 and current_sec < 2:
                        self.log(f"⏳ استراحة... الجلسة القادمة: {session_name} الساعة {next_hour:02d}:{next_min:02d}")
                    
                    time.sleep(60)
                    continue

                # 5. إذا كنا في نافذة، ولكننا أطلقنا فيها إشارة مسبقاً
                if current_slot in self.completed_windows:
                    next_slot_mins = self._get_next_slot_time()
                    next_hour = next_slot_mins // 60
                    next_min = next_slot_mins % 60
                    session_name = self._get_session_name(next_slot_mins)
                    
                    # نم حتى بداية النافذة التالية
                    sleep_sec = (next_slot_mins - current_mins) * 60 - current_sec
                    self.log(f"✅ تم إطلاق إشارة في هذه النافذة. النوم حتى {next_hour:02d}:{next_min:02d}...")
                    time.sleep(max(sleep_sec, 10))
                    continue

                # 6. نحن الآن في نافذة صالحة ولم نطلق إشارة بعد
                session_name = self._get_session_name(current_slot)
                
                # الفحص الديناميكي: نفحص في الثواني (55 إلى 05) من كل دقيقة
                if not (current_sec >= 55 or current_sec <= 5):
                    time.sleep(1)
                    continue

                # منع الفحص لنفس الدقيقة مرتين
                if current_mins == self.last_checked_minute and current_sec >= 5:
                    time.sleep(1)
                    continue

                self.last_checked_minute = current_mins
                self.log(f"🔍 فحص نشط... ({session_name})")

                # جلب وتحليل البيانات
                data_dict = self._get_all_data_parallel()
                
                for api_sym, df in data_dict.items():
                    if api_sym in self.last_signal_time:
                        if time.time() - self.last_signal_time[api_sym] < self.COOLDOWN_SEC:
                            continue

                    direction, price, confirmation = self._analyze_symbol(api_sym, df)
                    
                    if direction and price > 0:
                        qx_sym = self.SYMBOLS_MAP[api_sym]
                        self._send_signal(api_sym, qx_sym, direction, price, confirmation, session_name)
                        self.completed_windows.add(current_slot) # قفل هذه النافذة
                        break # أوقف البحث عن إشارات أخرى في هذه النافذة

                time.sleep(2)

            except Exception as e:
                self.log(f"ERR: {e}")
                time.sleep(10)


if __name__ == "__main__":
    bot = QuotexSniperBot()
    if bot.tg_token:
        bot.run()
