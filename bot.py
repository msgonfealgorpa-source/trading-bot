import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBotV15:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        self.TZ = ZoneInfo("Africa/Tripoli")

        # توسيع خريطة الأزواج (التركيز على الأزواج الحقيقية التي تتطابق مع API)
        self.SYMBOLS_MAP = {
            # العملات الرقمية (دقيقة جداً)
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)', 
            'BNB/USDT': 'BNBUSD(t)', 'SOL/USDT': 'SOLUSD(t)',
            'XRP/USDT': 'XRPUSD(t)', 'DOGE/USDT': 'DOGEUSD(t)',
            'ADA/USDT': 'ADAUSD(t)', 'TRX/USDT': 'TRXUSD(t)',
            'LTC/USDT': 'LTCUSD(t)', 'DOT/USDT': 'DOTUSD(t)',
            # أزواج الفوركس (تأخر بسيط مقبول)
            'EUR/USD': 'EUR/USD OTC', 'GBP/USD': 'GBP/USD OTC',
            'USD/JPY': 'USD/JPY OTC', 'AUD/USD': 'AUD/USD OTC',
            'USD/CAD': 'USD/CAD OTC', 'EUR/GBP': 'EUR/GBP OTC'
        }

        self.last_signal_time = {}
        self.pending_results = []
        self.stats = {'win': 0, 'loss': 0}
        self.processing = False # لمنع تكرار العملية في نفس الثانية

        msg = "🚀 *تم تشغيل القناص V15 (نسخة التصحيح الذكي)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "📈 الاستراتيجية: تقاطع Stochastic (K & D)\n"
        msg += "🔍 تصفية: الشموع المكتملة فقط\n"
        msg += "⏱️ مدة الصفقة: 2 دقيقة\n"
        msg += "━━━━━━━━━━━━━━━━"
        self.tg(msg)

    def tg(self, msg):
        try:
            requests.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                         data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=5)
        except: pass

    def _get_data(self, sym):
        base, quote = sym.split('/')
        url = "https://min-api.cryptocompare.com/data/v2/histominute"
        try:
            r = requests.get(url, params={'fsym': base, 'tsym': quote, 'limit': 50}, timeout=10)
            data = r.json()
            if data.get('Response') == 'Success':
                df = pd.DataFrame(data['Data']['Data'])
                return df
        except: return None
        return None

    def _check_result(self):
        now = time.time()
        for job in self.pending_results[:]:
            # يجب أن نعطي وقتاً للـ API حتى يتوفر لديه شمعة الدقيقة الـ 2
            if now >= job['expiry'] + 5: 
                df = self._get_data(job['api_sym'])
                if df is not None and len(df) > 0:
                    # البحث عن شمعة الإغلاق بالزمن الدقيق (تقريباً)
                    target_time = job['entry_candle_time'] + 120 # دقيقتان بالثواني
                    exit_candle = df[df['time'] == target_time]
                    
                    if not exit_candle.empty:
                        exit_price = exit_candle.iloc[0]['close']
                    else:
                        # إذا لم يجدها بالضبط بسبب تأخير API، يأخذ أقرب شمعة مكتملة سابقة
                        exit_price = df.iloc[-2]['close']

                    entry_price = job['entry_price']
                    direction = job['direction']
                    
                    win = False
                    if direction == 'CALL' and exit_price > entry_price: win = True
                    if direction == 'PUT' and exit_price < entry_price: win = True

                    res_icon = "✅ ربح (WIN)" if win else "❌ خسارة (LOSS)"
                    if win: self.stats['win'] += 1 
                    else: self.stats['loss'] += 1
                    
                    msg = f"🏁 *نتيجة صفقة {job['qx_sym']}*\n"
                    msg += f"━━━━━━━━━━━━━━━━\n"
                    msg += f"💰 الدخول: `{entry_price}` | الإغلاق: `{exit_price}`\n"
                    msg += f"📊 النتيجة: *{res_icon}*\n"
                    msg += f"🏆 الإحصائيات: {self.stats['win']}W - {self.stats['loss']}L"
                    self.tg(msg)
                    self.pending_results.remove(job)

    def run(self):
        print("Bot is running... Waiting for closed candles...")
        while True:
            now_dt = datetime.datetime.now(self.TZ)
            
            # ⚠️ التعديل الأهم: ننتظر الثانية 03 فقط لضمان أن الشمعة السابقة أغلقت تماماً في API
            if now_dt.second == 3 and not self.processing:
                self.processing = True
                self._check_result() 
                
                for api_sym, qx_sym in self.SYMBOLS_MAP.items():
                    if time.time() - self.last_signal_time.get(api_sym, 0) < 180: continue

                    df = self._get_data(api_sym)
                    if df is None or len(df) < 20: continue

                    stoch = ta.momentum.StochasticOscillator(
                        high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3
                    )
                    k = stoch.stoch().dropna()
                    d = stoch.stoch_signal().dropna()
                    
                    # نستخدم الشمعة المكتملة [-2] والشمعة التي قبلها [-3]
                    k_cur, d_cur = k.iloc[-2], d.iloc[-2]
                    k_prev, d_prev = k.iloc[-3], d.iloc[-3]

                    direction = None
                    # منطق التقاطع الصحيح
                    if k_prev > d_prev and k_cur < d_cur and k_cur > 70:
                        direction = 'PUT'
                    elif k_prev < d_prev and k_cur > d_cur and k_cur < 30:
                        direction = 'CALL'

                    if direction:
                        # سعر إغلاق الشمعة المكتملة
                        price = df.iloc[-2]['close'] 
                        entry_candle_time = df.iloc[-2]['time']
                        
                        self.last_signal_time[api_sym] = time.time()
                        
                        icon = "🟢" if direction == 'CALL' else "🔴"
                        msg = f"{icon} *إشارة {direction} مؤكدة*\n"
                        msg += f"━━━━━━━━━━━━━━━━\n"
                        msg += f"🪙 الزوج: *{qx_sym}*\n"
                        msg += f"💵 الدخول: `{price}`\n"
                        msg += f"⏱️ المدة: دقيقتان\n"
                        msg += f"⚡ التقاطع على شمعة مكتملة ✅"
                        self.tg(msg)

                        self.pending_results.append({
                            'api_sym': api_sym, 'qx_sym': qx_sym,
                            'entry_price': price, 'direction': direction,
                            'entry_candle_time': entry_candle_time,
                            'expiry': time.time() + 125 
                        })
                        time.sleep(0.5)

                # انتظار حتى نتجاوز الثانية 03 لكي لا يعيد التشغيل مرة أخرى
                time.sleep(3) 
                self.processing = False
            else:
                time.sleep(0.5)

if __name__ == "__main__":
    bot = QuotexSniperBotV15()
    bot.run()
