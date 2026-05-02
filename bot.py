import time, pandas as pd, ta, requests, datetime, os, sys
from zoneinfo import ZoneInfo

# ضبط الترميز لليونيكود
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

class QuotexSniperBotV15:
    """
    بوت القناص V15 - استراتيجية تقاطع الستوكاستيك + متابعة النتائج
    ========================================================
    - الإشارة: تقاطع خطوط K و D داخل مناطق التشبع.
    - المتابعة: فحص النتيجة بعد 2 دقيقة تلقائياً.
    - الدقة: مزامنة كاملة مع بداية الدقيقة.
    """

    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN')
        self.tg_chat = os.environ.get('CHAT_ID')
        self.TZ = ZoneInfo("Africa/Tripoli")

        # خريطة الأزواج
        self.SYMBOLS_MAP = {
            'BTC/USDT': 'BTCUSD(t)', 'ETH/USDT': 'ETHUSD(t)',
            'EUR/USD': 'EUR/USD OTC', 'GBP/USD': 'GBP/USD OTC',
            'USD/JPY': 'USD/JPY OTC', 'AUD/USD': 'AUD/USD OTC',
            'USD/CAD': 'USD/CAD OTC', 'EUR/GBP': 'EUR/GBP OTC'
        }

        self.last_signal_time = {}
        self.pending_results = [] # لمتابعة الصفقات المفتوحة
        self.stats = {'win': 0, 'loss': 0, 'total': 0}

        msg = "🚀 *تم تشغيل القناص V15 (النسخة الاحترافية)*\n"
        msg += "━━━━━━━━━━━━━━━━\n"
        msg += "📈 الاستراتيجية: تقاطع Stochastic (K & D)\n"
        msg += "⏱️ مدة الصفقة: 2 دقيقة\n"
        msg += "🎯 نظام متابعة الأرباح: نشط ✅\n"
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
        """فحص الصفقات التي انتهت مدتها"""
        now = time.time()
        for job in self.pending_results[:]:
            if now >= job['expiry']:
                df = self._get_data(job['api_sym'])
                if df is not None:
                    exit_price = df.iloc[-1]['close']
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
                    msg += f"💰 السعر عند الدخول: `{entry_price}`\n"
                    msg += f"📉 السعر عند الإغلاق: `{exit_price}`\n"
                    msg += f"📊 النتيجة: *{res_icon}*\n"
                    msg += f"🏆 الإحصائيات: {self.stats['win']}W - {self.stats['loss']}L"
                    self.tg(msg)
                    self.pending_results.remove(job)

    def run(self):
        print("Bot is running... Syncing with clock...")
        while True:
            # 1. المزامنة مع الثانية 00 لضمان الدخول المبكر
            now = datetime.datetime.now(self.TZ)
            if now.second >= 55 or now.second <= 2:
                self._check_result() # فحص النتائج القديمة أولاً
                
                for api_sym, qx_sym in self.SYMBOLS_MAP.items():
                    # كول داون 3 دقائق
                    if time.time() - self.last_signal_time.get(api_sym, 0) < 180: continue

                    df = self._get_data(api_sym)
                    if df is None or len(df) < 20: continue

                    # حساب الستوكاستيك
                    stoch = ta.momentum.StochasticOscillator(
                        high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3
                    )
                    k = stoch.stoch()
                    d = stoch.stoch_signal()
                    
                    k_cur, d_cur = k.iloc[-1], d.iloc[-1]
                    k_prev, d_prev = k.iloc[-2], d.iloc[-2]

                    direction = None
                    # منطق التقاطع: الهبوط (K يقطع D لتحت وهو فوق 70)
                    if k_prev > d_prev and k_cur < d_cur and k_cur > 70:
                        direction = 'PUT'
                    # منطق التقاطع: الصعود (K يقطع D لفوق وهو تحت 30)
                    elif k_prev < d_prev and k_cur > d_cur and k_cur < 30:
                        direction = 'CALL'

                    if direction:
                        price = df.iloc[-1]['close']
                        self.last_signal_time[api_sym] = time.time()
                        
                        # إرسال الإشارة
                        icon = "🟢" if direction == 'CALL' else "🔴"
                        msg = f"{icon} *إشارة {direction} مؤكدة*\n"
                        msg += f"━━━━━━━━━━━━━━━━\n"
                        msg += f"🪙 الزوج: *{qx_sym}*\n"
                        msg += f"💵 الدخول: `{price}`\n"
                        msg += f"⏱️ المدة: دقيقتان\n"
                        msg += f"⚡ التقاطع: تم التأكيد داخل منطقة التشبع"
                        self.tg(msg)

                        # إضافة الصفقات للمتابعة
                        self.pending_results.append({
                            'api_sym': api_sym, 'qx_sym': qx_sym,
                            'entry_price': price, 'direction': direction,
                            'expiry': time.time() + 125 # دقيقتين + هامش 5 ثواني
                        })
                        time.sleep(1) # منع تداخل الطلبات

                time.sleep(10) # انتظار بعيداً عن رأس الدقيقة لتقليل الضغط
            else:
                time.sleep(1)

if __name__ == "__main__":
    bot = QuotexSniperBotV15()
    bot.run()
