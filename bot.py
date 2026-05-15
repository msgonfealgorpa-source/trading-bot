""" ═══════════════════════════════════════════════════════════════ 🔥 القناص الأسطوري V4.0 — النسخة المؤسسية (Institutional Edition) 🔥 ═══════════════════════════════════════════════════════════════ """

import asyncio, aiohttp, json, math, os, sys, time, logging, requests
import pandas as pd
import numpy as np
import ta
import hmac
import hashlib
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import websockets

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger('SniperBotV4')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('bot_v4.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class TelegramLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            if record.levelno >= logging.ERROR:
                tg_token = os.environ.get('TELEGRAM_TOKEN', '')
                tg_chat = os.environ.get('CHAT_ID', '')
                if tg_token and tg_chat:
                    msg = f"🚨 *خطأ حرج:*\n`\n{self.format(record)[:400]}\n`"
                    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                    requests.post(url, data={'chat_id': tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=5)
        except Exception: pass

tg_handler = TelegramLoggingHandler()
tg_handler.setLevel(logging.ERROR)
logger.addHandler(tg_handler)

# ═════════════════════ محرك SMC (Smart Money Concepts) ═════════════════════
class SMCEngine:
    @staticmethod
    def detect_swings(df, window=3):
        """يكتشف القمم والقيعان (Swing Highs/Lows)"""
        df['sw_high'] = np.nan
        df['sw_low'] = np.nan
        for i in range(window, len(df) - window):
            if all(df['high'].iloc[i] >= df['high'].iloc[i-window:i]) and all(df['high'].iloc[i] >= df['high'].iloc[i+1:i+window+1]):
                df['sw_high'].iloc[i] = df['high'].iloc[i]
            if all(df['low'].iloc[i] <= df['low'].iloc[i-window:i]) and all(df['low'].iloc[i] <= df['low'].iloc[i+1:i+window+1]):
                df['sw_low'].iloc[i] = df['low'].iloc[i]
        return df

    @staticmethod
    def detect_bos_choch(df):
        """يكتشف كسر الهيكل (BOS) وتغيير الشخصية (CHoCH)"""
        signals = []
        last_sw_high = None
        last_sw_low = None
        trend = None # 'bull' or 'bear'
        
        for i in range(len(df)):
            if not pd.isna(df['sw_high'].iloc[i]): last_sw_high = df['sw_high'].iloc[i]
            if not pd.isna(df['sw_low'].iloc[i]): last_sw_low = df['sw_low'].iloc[i]
            
            if last_sw_high and last_sw_low:
                if df['close'].iloc[i] > last_sw_high:
                    if trend == 'bear': signals.append({'index': i, 'type': 'CHoCH_Bull'})
                    else: signals.append({'index': i, 'type': 'BOS_Bull'})
                    trend = 'bull'
                elif df['close'].iloc[i] < last_sw_low:
                    if trend == 'bull': signals.append({'index': i, 'type': 'CHoCH_Bear'})
                    else: signals.append({'index': i, 'type': 'BOS_Bear'})
                    trend = 'bear'
        return signals, trend

    @staticmethod
    def detect_fvg(df):
        """يكتشف فجوات القيمة العادلة (Fair Value Gaps)"""
        fvgs = []
        for i in range(2, len(df)):
            # Bullish FVG
            if df['low'].iloc[i] > df['high'].iloc[i-2]:
                fvgs.append({'index': i-1, 'type': 'bull_fvg', 'top': df['low'].iloc[i], 'bottom': df['high'].iloc[i-2]})
            # Bearish FVG
            elif df['high'].iloc[i] < df['low'].iloc[i-2]:
                fvgs.append({'index': i-1, 'type': 'bear_fvg', 'top': df['low'].iloc[i-2], 'bottom': df['high'].iloc[i]})
        return fvgs

    @staticmethod
    def detect_order_blocks(df, signals, trend):
        """يكتشف Orcer Blocks الاحترافية المرتبطة بكسر الهيكل"""
        obs = []
        for sig in signals:
            if (sig['type'] == 'BOS_Bull' or sig['type'] == 'CHoCH_Bull') and trend == 'bull':
                # البحث عن آخر شمعة هابطة قبل الكسر
                for j in range(sig['index'], max(sig['index']-10, 0), -1):
                    if df['close'].iloc[j] < df['open'].iloc[j]: # شمعة هابطة
                        obs.append({'type': 'bull_ob', 'top': df['open'].iloc[j], 'bottom': df['low'].iloc[j], 'index': j})
                        break
            elif (sig['type'] == 'BOS_Bear' or sig['type'] == 'CHoCH_Bear') and trend == 'bear':
                for j in range(sig['index'], max(sig['index']-10, 0), -1):
                    if df['close'].iloc[j] > df['open'].iloc[j]: # شمعة صاعدة
                        obs.append({'type': 'bear_ob', 'top': df['high'].iloc[j], 'bottom': df['open'].iloc[j], 'index': j})
                        break
        return obs

    @staticmethod
    def calculate_volume_delta(df):
        """يحسب Volume Delta تقريبي من بيانات الكاندلز"""
        df['delta'] = df['taker_buy_vol'] - (df['volume'] - df['taker_buy_vol'])
        df['cum_delta'] = df['delta'].cumsum()
        return df

    @staticmethod
    def is_unmitigated(ob_data, current_price, df, ob_type):
        """يتأكد هل الـ Order Block لم يتم امتصاصه بعد"""
        if ob_type == 'bull_ob':
            return current_price >= ob_data['bottom'] and current_price <= ob_data['top']
        else:
            return current_price >= ob_data['bottom'] and current_price <= ob_data['top']


# ═════════════════════ مدير WebSocket المستقر ═════════════════════
class BinanceWSManager:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.ws_url = "wss://stream.binance.com:9443/ws"
        self.running = False

    async def connect(self):
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("✅ WebSocket متصل بنجاح!")
                    # الاشتراك في بيانات اللحظي لأزواج الأولوية
                    pairs_lower = [c.lower() + "usdt@bookTicker" for c in self.bot.priority]
                    subscribe_msg = {"method": "SUBSCRIBE", "params": pairs_lower, "id": 1}
                    await ws.send(json.dumps(subscribe_msg))
                    
                    while self.running:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        if 's' in data and 'b' in data:
                            self.bot.live_prices[data['s']] = float(data['b']) # تحديث سعر الـ Bid الحي
            except Exception as e:
                logger.error(f"❌ انقطاع WebSocket: {e}. إعادة الاتصال خلال 5 ثواني...")
                await asyncio.sleep(5)

# ═════════════════════ البوت الأساسي ═════════════════════
class LegendarySniperBotV4:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')

        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '1.5')) # خطر أقل للمؤسسي
        self.MIN_SCORE_TO_TRADE = int(os.environ.get('MIN_SCORE', '8')) # نقاط أعلى للدقة
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '2'))
        self.MIN_TRADE_USDT = float(os.environ.get('MIN_TRADE_USDT', '15'))
        
        self.smc = SMCEngine()
        self.ws_manager = BinanceWSManager(self)
        self.TZ = ZoneInfo("Africa/Tripoli")
        self.usdt_pairs = []
        self.known_symbols = set()
        self.active_trades = {}
        self.stats = {'total_scans': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}
        self.step_sizes_cache = {}
        self.live_prices = {}
        self.session = None
        self.high_impact_news_times = [] # أوقات الأخبار القوية
        
        self.data_url = "https://data-api.binance.vision"
        self.trade_url = "https://api.binance.com"
        self.priority = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'AVAX', 'LINK', 'SUI', 'INJ', 'PEPE', 'WLD']
        
        logger.info("🔥 القناص الأسطوري V4.0 (Institutional Edition) بدأ التشغيل")

    async def tg(self, msg):
        try:
            if not self.session or not self.tg_token or not self.tg_chat: return
            if len(msg) > 4000:
                for i in range(0, len(msg), 4000):
                    await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage", data={'chat_id': self.tg_chat, 'text': msg[i:i+4000], 'parse_mode': 'Markdown'})
                    await asyncio.sleep(0.5)
            else:
                await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage", data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'})
        except Exception as e: logger.error(f"فشل إرسال تيليجرام: {e}")

    # ... (دوال الـ API و الـ Sign و load_market_data و get_klines كما هي في النسخة السابقة مع تعديل get_klines لدعم 5m) ...
    async def _binance_request(self, method, endpoint, params=None, signed=False, is_trade_endpoint=False):
        try:
            start_time = time.time()
            base = self.trade_url if is_trade_endpoint else self.data_url
            url = f"{base}{endpoint}"
            headers = {}
            if signed:
                if not self.binance_api_key: return None
                params = self._sign(params or {})
                headers = {'X-MBX-APIKEY': self.binance_api_key}
            async with self.session.request(method, url, params=params, headers=headers) as r:
                latency = time.time() - start_time
                if latency > 2.0: logger.warning(f"⚠️ تأخر API: {latency:.2f}s على {endpoint}")
                if r.status == 200: return await r.json()
                elif r.status == 429: await asyncio.sleep(10); return None
                else: return None
        except Exception as e: logger.error(f"استثناء بينانس: {e}"); return None

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(self.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    async def load_market_data(self):
        data = await self._binance_request('GET', '/api/v3/exchangeInfo')
        if not data:
            try:
                async with self.session.get("https://api.binance.com/api/v3/exchangeInfo") as r:
                    if r.status == 200: data = await r.json()
            except Exception: pass
        if not data: return
        new_pairs, new_symbols_set = [], set()
        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING':
                new_pairs.append({'symbol': s['symbol'], 'baseAsset': s['baseAsset']})
                new_symbols_set.add(s['symbol'])
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE': self.step_sizes_cache[s['symbol']] = float(f['stepSize'])
        self.usdt_pairs = new_pairs; self.known_symbols = new_symbols_set

    async def get_klines(self, symbol, interval='15m', limit=100):
        data = await self._binance_request('GET', '/api/v3/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_vol', 'taker_buy_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume', 'taker_buy_vol']: df[col] = pd.to_numeric(df[col], errors='coerce')
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            return df
        return None

    async def check_economic_news(self):
        """جلب الأخبار المؤثرة وإيقاف التداول وقتها"""
        try:
            async with self.session.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    now = time.time()
                    self.high_impact_news_times = []
                    for event in data:
                        if event.get('impact') == 'High' and event.get('country') in ['USD', 'GBP', 'EUR']:
                            event_time = pd.to_datetime(event['date']).timestamp()
                            # إيقاف التداول 30 دقيقة قبل الخبر وساعة بعده
                            if now < event_time + 3600 and now > event_time - 1800:
                                self.high_impact_news_times.append(event_time)
        except Exception: pass

    def is_news_time_now(self):
        now = time.time()
        for t in self.high_impact_news_times:
            if now > t - 1800 and now < t + 3600: return True
        return False

    async def analyze_coin_smc(self, symbol):
        """التحليل المؤسسي المعتمد على السيولة وبنية السوق"""
        try:
            # 1. تحديد الاتجاه العام (4H)
            df_4h = await self.get_klines(symbol, '4h', 50)
            if df_4h is None or len(df_4h) < 50: return None
            df_4h = self.smc.detect_swings(df_4h, window=3)
            _, macro_trend = self.smc.detect_bos_choch(df_4h)
            if not macro_trend: return None # لا تتداول بدون اتجاه واضح

            # 2. بنية السوق المتوسطة (15m)
            df_15m = await self.get_klines(symbol, '15m', 100)
            if df_15m is None or len(df_15m) < 50: return None
            df_15m = self.smc.calculate_volume_delta(df_15m)
            df_15m = self.smc.detect_swings(df_15m, window=3)
            signals, micro_trend = self.smc.detect_bos_choch(df_15m)
            
            # 3. فجوات السيولة و Order Blocks (15m)
            fvgs = self.smc.detect_fvg(df_15m)
            obs = self.smc.detect_order_blocks(df_15m, signals, micro_trend)
            
            # 4. نقطة الدخول الدقيقة (5m)
            df_5m = await self.get_klines(symbol, '5m', 50)
            if df_5m is None: return None
            df_5m = self.smc.calculate_volume_delta(df_5m)
            price = float(df_5m.iloc[-1]['close'])
            
            result = {'symbol': symbol, 'price': price, 'score': 0, 'signals': [], 'direction': None}

            # تقييم الـ Confluence (التقاء المؤشرات المؤسسية)
            
            # التأكد من توافق الاتجاهين
            if macro_trend == 'bull' and micro_trend == 'bull': result['score'] += 3; result['signals'].append("📈 توافق 4H/15M صعودي")
            elif macro_trend == 'bear' and micro_trend == 'bear': result['score'] -= 3; result['signals'].append("📉 توافق 4H/15M هبوطي")
            else: return None # لا تتداول ضد الاتجاه الأكبر

            # فحص FVG
            for fvg in fvgs[-5:]:
                if fvg['type'] == 'bull_fvg' and price >= fvg['bottom'] and price <= fvg['top']:
                    result['score'] += 2; result['signals'].append("🎯 ارتداد من FVG صعودي"); break
                elif fvg['type'] == 'bear_fvg' and price >= fvg['bottom'] and price <= fvg['top']:
                    result['score'] -= 2; result['signals'].append("🎯 ارتداد من FVG هبوطي"); break

            # فحص Order Block الاحترافي
            for ob in obs[-3:]:
                if ob['type'] == 'bull_ob' and self.smc.is_unmitigated(ob, price, df_15m, 'bull_ob'):
                    result['score'] += 4; result['signals'].append("🧠 دخول من Bullish OB حيوي"); break
                elif ob['type'] == 'bear_ob' and self.smc.is_unmitigated(ob, price, df_15m, 'bear_ob'):
                    result['score'] -= 4; result['signals'].append("🧠 دخول من Bearish OB حيوي"); break

            # Volume Delta (الضغط المؤسسي)
            current_delta = df_5m['delta'].iloc[-1]
            cum_delta = df_5m['cum_delta'].iloc[-3:].mean()
            if micro_trend == 'bull' and current_delta > 0 and cum_delta > 0:
                result['score'] += 2; result['signals'].append("🌊 ضغط شرائي مؤسسي (Delta+)")
            elif micro_trend == 'bear' and current_delta < 0 and cum_delta < 0:
                result['score'] -= 2; result['signals'].append("🌊 ضغط بيعي مؤسسي (Delta-)")

            # مؤشرات مساعدة فقط (RSI للتشبع)
            rsi_val = ta.momentum.RSIIndicator(df_15m['close'], window=14).rsi().iloc[-1]
            if micro_trend == 'bull' and rsi_val < 35: result['score'] += 1
            elif micro_trend == 'bear' and rsi_val > 65: result['score'] -= 1

            # تحديد الاتجاه
            if result['score'] >= self.MIN_SCORE_TO_TRADE: result['direction'] = 'BUY'
            elif result['score'] <= -self.MIN_SCORE_TO_TRADE: result['direction'] = 'SELL'
            
            return result
        except Exception as e:
            logger.error(f"خطأ تحليل SMC لـ {symbol}: {e}")
            return None

    async def calculate_dynamic_sl_tp(self, symbol, entry_price, direction):
        """حساب وقف الخسارة بناءً على حدود الـ OB أو FVG أو ATR"""
        df = await self.get_klines(symbol, '15m', 30)
        if df is None: return entry_price * 0.97, entry_price * 1.06
        atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
        if pd.isna(atr): return entry_price * 0.97, entry_price * 1.06
        
        atr_pct = (atr / entry_price) * 100
        if direction == 'BUY':
            sl_price = entry_price - (atr_pct * 1.5 / 100 * entry_price)
            tp_price = entry_price + (atr_pct * 3.0 / 100 * entry_price)
        else:
            sl_price = entry_price + (atr_pct * 1.5 / 100 * entry_price)
            tp_price = entry_price - (atr_pct * 3.0 / 100 * entry_price)
            
        return round(sl_price, 6), round(tp_price, 6)

    async def execute_trade(self, analysis):
        if not self.TRADE_ENABLED: return
        if self.is_news_time_now():
            logger.info("⏸️ توقف التداول: وقت أخبار اقتصادية قوية!")
            return
            
        symbol, direction, score, price = analysis['symbol'], analysis['direction'], analysis['score'], analysis['price']
        if len(self.active_trades) >= self.MAX_OPEN_TRADES or symbol in self.active_trades: return
        
        balance_data = await self._binance_request('GET', '/api/v3/account', signed=True, is_trade_endpoint=True)
        usdt_balance = 0
        if balance_data:
            for b in balance_data.get('balances', []):
                if b['asset'] == 'USDT': usdt_balance = float(b['free'])
        
        trade_amount = usdt_balance * (self.RISK_PER_TRADE_PCT / 100)
        if trade_amount < self.MIN_TRADE_USDT: return

        sl_price, tp_price = await self.calculate_dynamic_sl_tp(symbol, price, direction)
        
        # استخدام LIMIT ORDER لتقليل السليبيج (نضع سعر ليميت أفضل بقليل من السعر الحالي)
        limit_price = round(price * 1.0001, 6) if direction == 'BUY' else round(price * 0.9999, 6)
        
        side = 'BUY' if direction == 'BUY' else 'SELL'
        result = await self._binance_request('POST', '/api/v3/order', {
            'symbol': symbol, 'side': side, 'type': 'LIMIT', 
            'timeInForce': 'IOC', # Immediate Or Cancel لضمان الدخول السريع أو الإلغاء
            'price': limit_price, 
            'quoteOrderQty': round(trade_amount, 2)
        }, signed=True, is_trade_endpoint=True)

        if result and result.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
            fills = result.get('fills', [])
            fill_price = float(fills[0]['price']) if fills else price
            fill_qty = float(fills[0]['qty']) if fills else 0
            
            self.active_trades[symbol] = {
                'entry_price': fill_price, 'quantity': fill_qty, 'direction': direction,
                'stop_loss': sl_price, 'take_profit': tp_price, 
                'entry_time': time.time(), 'score': score
            }
            self._save_active_trades()
            msg = (f"🎯 *صفقة {direction} منفذة (Institutional)!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                   f"🪙 `{symbol}`\n💵 الدخول: `{fill_price:.6f}` (Limit)\n"
                   f"🛑 SL: `{sl_price:.6f}` | 🎯 TP: `{tp_price:.6f}`\n"
                   f"📊 النقاط: *{score}* | السيولة: ✅")
            await self.tg(msg)

    # ... (دوال monitor_trades و الإغلاق والإحصائيات كما هي مع تعديل دعم SHORT) ...
    
    async def quick_scan(self):
        found = []
        for coin in self.priority:
            sym = f"{coin}USDT"
            if sym in self.known_symbols and sym not in self.active_trades:
                a = await self.analyze_coin_smc(sym)
                if a and abs(a['score']) >= self.MIN_SCORE_TO_TRADE: found.append(a)
                await asyncio.sleep(0.5) # تأخير أكبر لتحليل SMC المعقد
        if found:
            found.sort(key=lambda x: abs(x['score']), reverse=True)
            msg = "⚡ *فحص SMC — فرص مؤسسية!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(found[:3]): msg += f"🟢 `{a['symbol']}` | نقاط: *{a['score']}* | اتجاه: {a['direction']}\n"
            await self.tg(msg)
            await self.execute_trade(found[0])

    def _save_active_trades(self):
        try:
            with open('active_trades.json', 'w') as f: json.dump(self.active_trades, f)
        except Exception: pass

    def _load_active_trades(self):
        try:
            if os.path.exists('active_trades.json'):
                with open('active_trades.json', 'r') as f: self.active_trades = json.load(f)
        except Exception: self.active_trades = {}

    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.load_market_data()
        self._load_active_trades()
        
        # بدء WebSocket في الخلفية
        asyncio.create_task(self.ws_manager.connect())
        await self.tg("🔥 *القناص المؤسسي V4.0 بدأ العمل!*\n🧠 يعمل بـ SMC + Order Flow + WebSocket")
        
        try:
            while True:
                now = time.time()
                # تحديث الأخبار كل ساعة
                if now - getattr(self, 'last_news_check', 0) > 3600:
                    await self.check_economic_news()
                    self.last_news_check = now
                
                # المسح كل 15 دقيقة (لأننا نعتمد على 15m شموع)
                if now - getattr(self, 'last_volume_scan', 0) > 900:
                    await self.quick_scan()
                    self.last_volume_scan = now
                
                await asyncio.sleep(5)
        except Exception as e: logger.critical(f"انهيار النظام: {e}")
        finally: await self.session.close()

    def start(self): asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperBotV4()
    bot.start()
