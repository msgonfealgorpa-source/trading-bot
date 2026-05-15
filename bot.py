"""
═══════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V3.0 — النسخة الاحترافية العالمية 🔥
═══════════════════════════════════════════════════════════════
  ✅ WebSockets للبيانات اللحظية (Trailing Stop فائق السرعة)
  ✅ Asyncio لفحص 50 عملة في نفس اللحظة
  ✅ تحليل متعدد الأطر الزمنية (4H للاتجاه + 15m للدخول)
  ✅ دمج مفهوم الأوردر بلوك (Order Blocks - SMC)
  ✅ نظام تسجيل أخطاء احترافي (Logging) مع تنبيهات تيليجرام
  ✅ وضع الفحص الرجعي (Backtesting Mode)
═══════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging
import pandas as pd
import ta
import hmac
import hashlib
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import websockets

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ═══ إعداد نظام التسجيل الاحترافي (Logging) ═══
logger = logging.getLogger('SniperBot')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# ملف لحفظ السجلات
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# طباعة في الكونسول
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class TelegramLoggingHandler(logging.Handler):
    """إرسال الأخطاء الحرجة للتيليجرام"""
    def __init__(self, bot_instance):
        super().__init__()
        self.bot = bot_instance

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            msg = f"🚨 *خطأ حرج في البوت:*\n```\n{self.format(record)[:500]}\n```"
            asyncio.ensure_future(self.bot.tg(msg))

class LegendarySniperBotV3:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')

        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.BACKTEST_MODE = os.environ.get('BACKTEST_MODE', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '2'))
        self.MIN_SCORE_TO_TRADE = int(os.environ.get('MIN_SCORE', '6')) # تم رفعه لوجود SMC
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '3'))
        self.MIN_TRADE_USDT = float(os.environ.get('MIN_TRADE_USDT', '10'))

        self.TZ = ZoneInfo("Africa/Tripoli")
        self.usdt_pairs = []
        self.known_symbols = set()
        self.active_trades = {}
        self.stats = {'total_scans': 0, 'signals_found': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0'}
        self.step_sizes_cache = {}
        
        # WebSockets & Async
        self.ws_url = "wss://stream.binance.com:9443/ws"
        self.live_prices = {} # تخزين الأسعار اللحظية
        self.session = None

        # ربط نظام التسجيل مع التيليجرام
        tg_handler = TelegramLoggingHandler(self)
        tg_handler.setLevel(logging.ERROR)
        logger.addHandler(tg_handler)

        mode = "🧪 وضع الفحص الرجعي (Backtest)" if self.BACKTEST_MODE else ("⚔️ تداول تلقائي" if self.TRADE_ENABLED else "👁️ مراقبة فقط")
        logger.info(f"🔥 القناص الأسطوري V3.0 بدأ التشغيل — الوضع: {mode}")

    # ═══════════════════════════════════════════════════
    #          وحدة تيليجرام (Async) - مصلحة
    # ═══════════════════════════════════════════════════
    async def tg(self, msg):
        try:
            # حماية: إذا كانت الجلسة لم تُنشأ بعد، لا تحاول الإرسال لتجنب الانهيار
            if not self.session: return
            if not self.tg_token or not self.tg_chat: return
            
            if len(msg) > 4000:
                for i in range(0, len(msg), 4000):
                    await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                            data={'chat_id': self.tg_chat, 'text': msg[i:i+4000], 'parse_mode': 'Markdown'})
                    await asyncio.sleep(0.5)
            else:
                await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                        data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'})
        except Exception as e:
            logger.error(f"فشل إرسال رسالة تيليجرام: {e}")

    # ═══════════════════════════════════════════════════
    #     وحدة بينانس API الأساسية (Async)
    # ═══════════════════════════════════════════════════
    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(self.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    async def _binance_request(self, method, endpoint, params=None, signed=False):
        try:
            base = "https://api.binance.com"
            url = f"{base}{endpoint}"
            headers = {}
            if signed:
                if not self.binance_api_key: return None
                params = self._sign(params or {})
                headers = {'X-MBX-APIKEY': self.binance_api_key}

            async with self.session.request(method, url, params=params, headers=headers) as r:
                if r.status == 200: return await r.json()
                elif r.status == 429: 
                    logger.warning("تم حظر الطلب مؤقتاً (429)، انتظار 10 ثوان...")
                    await asyncio.sleep(10); return None
                else: 
                    logger.error(f"خطأ API بينانس: {r.status} - {await r.text()}")
                    return None
        except Exception as e:
            logger.error(f"استثناء في طلب بينانس: {e}")
            return None

    # ═══════════════════════════════════════════════════
    #       تحميل الأزواج وحجوم الخطوات
    # ═══════════════════════════════════════════════════
    async def load_market_data(self):
        data = await self._binance_request('GET', '/api/v3/exchangeInfo')
        if not data: return
        new_pairs, new_symbols_set = [], set()
        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING':
                new_pairs.append({'symbol': s['symbol'], 'baseAsset': s['baseAsset']})
                new_symbols_set.add(s['symbol'])
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE':
                        self.step_sizes_cache[s['symbol']] = float(f['stepSize'])
        
        if self.known_symbols and (new_symbols_set - self.known_symbols):
            new_coins = new_symbols_set - self.known_symbols
            msg = "🆕 *عملات مدرجة حديثاً!*\n" + "\n".join([f"⚡ `{c}`" for c in new_coins])
            await self.tg(msg)

        self.usdt_pairs = new_pairs
        self.known_symbols = new_symbols_set
        logger.info(f"تم تحميل {len(self.usdt_pairs)} زوج.")

    # ═══════════════════════════════════════════════════
    #       جلب الشموع (Async) لأطر زمنية متعددة
    # ═══════════════════════════════════════════════════
    async def get_klines(self, symbol, interval='15m', limit=100):
        data = await self._binance_request('GET', '/api/v3/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_vol', 'taker_buy_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            return df
        return None

    # ═══════════════════════════════════════════════════
    #     خوارزمية الأوردر بلوك (SMC)
    # ═══════════════════════════════════════════════════
    def detect_order_blocks(self, df, is_bullish_trend):
        """
        كشف مناطق العرض والطلب (Order Blocks)
        إذا كان الاتجاه صعودي، نبحث عن آخر أوردر بلوك صعودي (طلب) لنشتري منه.
        """
        if df is None or len(df) < 10: return None
        
        # الأوردر بلوك الصعودي: آخر شمعة هابطة قبل دفع صعودي قوي
        if is_bullish_trend:
            for i in range(len(df)-1, 3, -1):
                prev_candle = df.iloc[i-1]
                curr_candle = df.iloc[i]
                # إذا كانت الشمعة السابقة هابطة والشمعة الحالية صعودية قوية (هيكل كسر)
                if prev_candle['close'] < prev_candle['open'] and curr_candle['close'] > prev_candle['high']:
                    ob_high = prev_candle['high']
                    ob_low = prev_candle['low']
                    return {'type': 'bullish', 'high': ob_high, 'low': ob_low}
        
        # الأوردر بلوك الهبوطي: آخر شمعة صاعدة قبل دفع هبوطي قوي
        elif not is_bullish_trend:
            for i in range(len(df)-1, 3, -1):
                prev_candle = df.iloc[i-1]
                curr_candle = df.iloc[i]
                if prev_candle['close'] > prev_candle['open'] and curr_candle['close'] < prev_candle['low']:
                    ob_high = prev_candle['high']
                    ob_low = prev_candle['low']
                    return {'type': 'bearish', 'high': ob_high, 'low': ob_low}
                    
        return None

    # ═══════════════════════════════════════════════════
    #     التحليل متعدد الأطر الزمنية والمؤشرات (معدل)
    # ═══════════════════════════════════════════════════
    async def analyze_coin(self, symbol):
        try:
            # 1. إطار 4 ساعات لتحديد الاتجاه العام
            df_4h = await self.get_klines(symbol, '4h', 50)
            if df_4h is None or len(df_4h) < 50: return None
            
            ema50_calc = ta.trend.EMAIndicator(df_4h['close'], window=50).ema_indicator()
            if ema50_calc.isna().iloc[-1]: return None
            ema50_4h = ema50_calc.iloc[-1]
            is_bullish_trend = df_4h.iloc[-1]['close'] > ema50_4h

            # 2. إطار 15 دقيقة لنقطة الدخول الدقيقة والمؤشرات
            df_15m = await self.get_klines(symbol, '15m', 100)
            if df_15m is None or len(df_15m) < 50: return None

            price = df_15m.iloc[-1]['close']
            result = {'symbol': symbol, 'price': price, 'score': 0, 'signals': [], 'direction': None, 'ob_zone': None}

            # ═══ المؤشرات التقليدية (الأساس) ═══
            rsi_val = ta.momentum.RSIIndicator(df_15m['close'], window=14).rsi().iloc[-1]
            if is_bullish_trend and rsi_val < 35: 
                result['score'] += 2; result['signals'].append(f"📈 RSI تشبع بيعي ({rsi_val:.0f})")

            macd_ind = ta.trend.MACD(df_15m['close'])
            if macd_ind.macd().iloc[-1] > macd_ind.macd_signal().iloc[-1] and macd_ind.macd().iloc[-2] <= macd_ind.macd_signal().iloc[-2]:
                result['score'] += 2; result['signals'].append("📈 MACD تقاطع صعودي")

            ema9, ema21 = ta.trend.EMAIndicator(df_15m['close'], window=9).ema_indicator(), ta.trend.EMAIndicator(df_15m['close'], window=21).ema_indicator()
            if ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2]:
                result['score'] += 2; result['signals'].append("📈 EMA تقاطع صعودي")

            vol_avg = df_15m['volume'].rolling(20).mean().iloc[-1]
            if df_15m.iloc[-1]['volume'] > vol_avg * 2: 
                result['score'] += 2; result['signals'].append("🔥 حجم عالي")

            # ═══ الأوردر بلوك SMC (التأكيد المعزز) ═══
            ob = self.detect_order_blocks(df_15m, is_bullish_trend)
            if ob and is_bullish_trend and ob['type'] == 'bullish':
                # هل السعر يرتد من منطقة الطلب الآن؟
                if ob['low'] <= price <= ob['high'] * 1.01:
                    result['score'] += 4  # نقاط تأكيدية قوية!
                    result['signals'].append("🧠 ارتداد من Order Block (فرصة ذهبية!)")
                    result['ob_zone'] = ob
            
            # نفس المنطق للبيع
            elif ob and not is_bullish_trend and ob['type'] == 'bearish':
                if ob['high'] >= price >= ob['low'] * 0.99:
                    result['score'] -= 4
                    result['signals'].append("🧠 ارتداد من Order Block هبوطي")

            # تحديد الاتجاه بناءً على مجموع النقاط (الأساس + التأكيد)
            # الحد الأدنى الافتراضي 5 أو 6
            if is_bullish_trend and result['score'] >= self.MIN_SCORE_TO_TRADE: 
                result['direction'] = 'BUY'
            elif not is_bullish_trend and result['score'] <= -self.MIN_SCORE_TO_TRADE: 
                result['direction'] = 'SELL'

            return result
        except Exception as e:
            logger.error(f"خطأ في تحليل {symbol}: {e}")
            return None

    # ═══════════════════════════════════════════════════
    #     WebSockets لمراقبة الأسعار لحظياً (Trailing)
    # ═══════════════════════════════════════════════════
    async def websocket_listener(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    # الاشتراك في تحديثات جميع الأزواج (Mini Ticker)
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": ["!miniTicker@arr"],
                        "id": 1
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("✅ متصل بـ WebSockets لبينانس (أسعار لحظية)")
                    
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if isinstance(data, list):
                            for t in data:
                                self.live_prices[t['s']] = float(t['c']) # تحديث السعر اللحظي
            except Exception as e:
                logger.error(f"خطأ في WebSocket: {e}. إعادة الاتصال بعد 5 ثوان...")
                await asyncio.sleep(5)

    # ═══════════════════════════════════════════════════
    #    مراقبة الصفقات بالوقف المتحرك (Trailing) فائق السرعة
    # ═══════════════════════════════════════════════════
    async def monitor_trades(self):
        if not self.active_trades: return

        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            current_price = self.live_prices.get(symbol)
            
            if not current_price: continue # لا يوجد سعر لحظي بعد
            
            entry_price = trade['entry_price']
            if current_price > trade['highest_price']: trade['highest_price'] = current_price
            current_profit_pct = ((current_price - entry_price) / entry_price) * 100

            closed, close_reason = False, ""

            if current_price <= trade['stop_loss'] and not trade['trailing_active']:
                closed, close_reason = True, "🛑 ضرب وقف الخسارة"
            elif current_price >= trade['take_profit'] and not trade['trailing_active']:
                trade['trailing_active'] = True
                trade['stop_loss'] = entry_price * 1.005
                await self.tg(f"⚡ *تفعيل الوقف المتحرك! `{symbol}`*\n🛑 الوقف الجديد: `{trade['stop_loss']:.6f}`")
                self._save_active_trades()
            elif trade['trailing_active']:
                new_sl = trade['highest_price'] * (1 - trade['trailing_distance_pct'] / 100)
                if new_sl > trade['stop_loss']: trade['stop_loss'] = new_sl
                if current_price <= trade['stop_loss']:
                    closed, close_reason = True, "🔄 وقف متحرك حافظ على الأرباح!"

            if closed:
                step_size = self.step_sizes_cache.get(symbol, 1)
                qty = self.adjust_quantity(trade['quantity'], step_size)
                # بيع فعلي
                if self.TRADE_ENABLED:
                    result = await self._binance_request('POST', '/api/v3/order', {'symbol': symbol, 'side': 'SELL', 'type': 'MARKET', 'quantity': qty}, signed=True)
                
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                if pnl_pct > 0: self.stats['wins'] += 1
                else: self.stats['losses'] += 1

                await self.tg(f"🏁 *إغلاق `{symbol}`*\n{close_reason}\n💵 النتيجة: `{pnl_pct:+.2f}%`")
                del self.active_trades[symbol]
                self._save_active_trades()

    def adjust_quantity(self, quantity, step_size):
        if step_size >= 1: return math.floor(quantity)
        precision = len(str(step_size).rstrip('0').split('.')[-1])
        return math.floor(quantity * (10 ** precision)) / (10 ** precision)

    # ═══════════════════════════════════════════════════
    #          المسح المتوازي (Asyncio)
    # ═══════════════════════════════════════════════════
    async def scan_market(self):
        logger.info("🔍 بدء المسح المتوازي للسوق...")
        tasks = []
        # فحص أبرز 50 عملة مثلاً، أو الكل إذا أردت
        pairs_to_scan = [p['symbol'] for p in self.usdt_pairs[:50] if p['symbol'] not in self.active_trades]
        
        for sym in pairs_to_scan:
            tasks.append(self.analyze_coin(sym))
        
        results = await asyncio.gather(*tasks)
        signals = [r for r in results if r and abs(r['score']) >= self.MIN_SCORE_TO_TRADE]
        
        if signals:
            signals.sort(key=lambda x: x['score'], reverse=True)
            msg = "⚡ *فرص قوية مكتشفة!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for a in signals[:3]: 
                dir_emoji = "🟢" if a['direction'] == 'BUY' else "🔴"
                msg += f"{dir_emoji} `{a['symbol']}` | نقاط: *{a['score']}* | {a['signals'][0]}\n"
            await self.tg(msg)
            # تنفيذ أقوى إشارة
            if self.TRADE_ENABLED and signals[0]['direction'] == 'BUY':
                await self.execute_trade(signals[0])

    # ═══════════════════════════════════════════════════
    #          تنفيذ الصفقات (Async)
    # ═══════════════════════════════════════════════════
    async def execute_trade(self, analysis):
        symbol = analysis['symbol']
        price = analysis['price']
        
        balance_data = await self._binance_request('GET', '/api/v3/account', signed=True)
        usdt_balance = 0
        if balance_data:
            for b in balance_data.get('balances', []):
                if b['asset'] == 'USDT': usdt_balance = float(b['free'])
        
        trade_amount = usdt_balance * (self.RISK_PER_TRADE_PCT / 100)
        if trade_amount < self.MIN_TRADE_USDT: return

        # حساب ATR للوقف المرن
        df = await self.get_klines(symbol, '15m', 30)
        atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
        atr_pct = (atr / price) * 100
        
        sl_price = price * (1 - (atr_pct * 1.5) / 100)
        tp_price = price * (1 + (atr_pct * 3.0) / 100)
        trailing_dist = atr_pct * 1.5

        result = await self._binance_request('POST', '/api/v3/order', {
            'symbol': symbol, 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': round(trade_amount, 2)
        }, signed=True)

        if result and result.get('status') == 'FILLED':
            self.stats['trades_executed'] += 1
            fill_price = float(result['fills'][0]['price'])
            fill_qty = float(result['fills'][0]['qty'])
            
            self.active_trades[symbol] = {
                'entry_price': fill_price, 'quantity': fill_qty,
                'stop_loss': sl_price, 'take_profit': tp_price,
                'trailing_distance_pct': trailing_dist,
                'highest_price': fill_price, 'trailing_active': False,
                'entry_time': time.time()
            }
            self._save_active_trades()
            await self.tg(f"✅ *شراء `{symbol}`*\n💵 الدخول: `{fill_price:.4f}`\n🛑 SL: `{sl_price:.4f}`\n🎯 TP: `{tp_price:.4f}`")

    # ═══════════════════════════════════════════════════
    #       وضع الفحص الرجعي (Backtesting)
    # ═══════════════════════════════════════════════════
    async def run_backtest(self, symbol='BTCUSDT'):
        logger.info(f"🧪 بدء وضع الفحص الرجعي على {symbol}...")
        # جلب 1000 شمعة لـ 15 دقيقة (حوالي 10 أيام)
        df_15m = await self.get_klines(symbol, '15m', 1000)
        df_4h = await self.get_klines(symbol, '4h', 500)
        
        if df_15m is None: return

        wins, losses = 0, 0
        for i in range(100, len(df_15m)):
            current_candle = df_15m.iloc[i]
            historical_df = df_15m.iloc[i-100:i]
            
            # محاكاة الاتجاه والتحليل
            ema50 = ta.trend.EMAIndicator(historical_df['close'], window=50).ema_indicator().iloc[-1]
            is_bullish = historical_df.iloc[-1]['close'] > ema50
            
            # محاكاة الأوردر بلوك والمؤشرات
            ob = self.detect_order_blocks(historical_df, is_bullish)
            price = current_candle['close']
            
            score = 0
            if ob and is_bullish and ob['type'] == 'bullish' and ob['low'] <= price <= ob['high']:
                score += 5
            
            rsi = ta.momentum.RSIIndicator(historical_df['close'], window=14).rsi().iloc[-1]
            if is_bullish and rsi < 35: score += 3
            
            if score >= self.MIN_SCORE_TO_TRADE:
                # افتراض صفقة شراء، نرى ماذا يحدث في الـ 12 شمعة القادمة (3 ساعات)
                future_prices = df_15m.iloc[i:i+12]['high']
                if not future_prices.empty:
                    tp = price * 1.03
                    sl = price * 0.98
                    hit_tp, hit_sl = False, False
                    for fp in future_prices:
                        if fp >= tp: hit_tp = True; break
                        if fp <= sl: hit_sl = True; break
                    if hit_tp: wins += 1
                    elif hit_sl: losses += 1
        
        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0
        msg = f"🧪 *نتيجة الفحص الرجعي (Backtest)*\n🪙 العملة: {symbol}\n✅ رابحة: {wins}\n❌ خاسرة: {losses}\n📊 نسبة النجاح: {win_rate:.2f}%"
        await self.tg(msg)
        logger.info(msg)

    # ═══════════════════════════════════════════════════
    #          حفظ واسترجاع الصفقات
    # ═══════════════════════════════════════════════════
    def _save_active_trades(self):
        try:
            with open('active_trades.json', 'w') as f: json.dump(self.active_trades, f)
        except Exception as e:
            logger.error(f"فشل حفظ الصفقات: {e}")

    def _load_active_trades(self):
        try:
            if os.path.exists('active_trades.json'):
                with open('active_trades.json', 'r') as f: self.active_trades = json.load(f)
        except Exception as e:
            logger.error(f"فشل تحميل الصفقات: {e}")
            self.active_trades = {}

    # ═══════════════════════════════════════════════════
    #          القلب النابض (Main Async Loop)
    # ═══════════════════════════════════════════════════
    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.load_market_data()
        self._load_active_trades()
        
        await self.tg("🔥 *القناص الأسطوري V3.0 بدأ العمل!*\n🚀 يعمل بـ WebSockets + Asyncio")

        if self.BACKTEST_MODE:
            await self.run_backtest('BTCUSDT')
            await self.session.close()
            return

        # تشغيل الـ WebSockets في الخلفية
        asyncio.create_task(self.websocket_listener())

        scan_counter = 0
        try:
            while True:
                scan_counter += 1
                # مراقبة الصفقات كل ثانية بناءً على WebSockets
                await self.monitor_trades()
                
                # مسح السوق كل 15 دقيقة (900 ثانية)
                if scan_counter % 900 == 0:
                    await self.scan_market()
                
                await asyncio.sleep(1) # سرعة فائقة بدل دقيقة
        except Exception as e:
            logger.critical(f"انهيار النظام الرئيسي: {e}")
        finally:
            await self.session.close()

    def start(self):
        asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperBotV3()
    bot.start()
