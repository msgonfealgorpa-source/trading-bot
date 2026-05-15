"""
═══════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V3.0 — النسخة الكاملة (حساب تجريبي) 🔥
═══════════════════════════════════════════════════════════════
  ✅ Asyncio لفحص 50 عملة في نفس اللحظة
  ✅ تحليل متعدد الأطر الزمنية (4H للاتجاه + 15m للدخول)
  ✅ دمج مفهوم الأوردر بلوك (Order Blocks - SMC)
  ✅ 7 مؤشرات فنية + تحليل كامل للسوق
  ✅ مصادر خارجية (إعلانات بينانس، كوينجيكو، الخوف والطمع، ارتفاعات الحجم)
  ✅ نظام تسجيل أخطاء احترافي (Logging)
  ✅ وقف خسارة وهدف ربح مرن (Trailing Stop)
  ✅ سحب الأسعار اللحظي (Anti-Ban Polling) لتجاوز حظر Railway
═══════════════════════════════════════════════════════════════
"""

import asyncio, aiohttp, json, math, os, sys, time, logging, requests
import pandas as pd
import ta
import hmac
import hashlib
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger('SniperBot')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
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
                    msg = f"🚨 *خطأ حرج:*\n```\n{self.format(record)[:400]}\n```"
                    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                    requests.post(url, data={'chat_id': tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=5)
        except Exception: pass

tg_handler = TelegramLoggingHandler()
tg_handler.setLevel(logging.ERROR)
logger.addHandler(tg_handler)

class LegendarySniperBotV3:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')
        
        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.BACKTEST_MODE = os.environ.get('BACKTEST_MODE', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '2'))
        self.MIN_SCORE_TO_TRADE = int(os.environ.get('MIN_SCORE', '6'))
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '3'))
        self.MIN_TRADE_USDT = float(os.environ.get('MIN_TRADE_USDT', '10'))

        self.TZ = ZoneInfo("Africa/Tripoli")
        self.usdt_pairs = []
        self.known_symbols = set()
        self.active_trades = {}
        self.stats = {'total_scans': 0, 'signals_found': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}
        self.step_sizes_cache = {}
        self.live_prices = {}
        self.session = None
        
        # ═══ روابط الحساب التجريبي (Testnet) ═══
        self.data_url = "https://testnet.binance.vision"
        self.trade_url = "https://testnet.binance.vision"

        # مؤقتات الأحداث
        self.last_announcement_check = 0
        self.last_coingecko_check = 0
        self.last_fear_greed_check = 0
        self.last_volume_scan = 0
        self.last_full_scan = 0

        # عملات المسح السريع
        self.priority = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE', 'ADA', 'AVAX', 'DOT', 'LINK', 'UNI', 'ATOM', 'LTC', 'NEAR', 'APT', 'ARB', 'OP', 'SUI', 'SEI', 'TIA', 'INJ', 'FET', 'WLD', 'PEPE', 'SHIB', 'TON']

        mode = "🧪 تداول تجريبي" if self.TRADE_ENABLED else "👁️ مراقبة فقط"
        logger.info(f"🔥 القناص الأسطوري V3.0 (Testnet) بدأ التشغيل — الوضع: {mode}")

    # ═══════════════════════════════════════════════════
    #          وحدة تيليجرام (Async)
    # ═══════════════════════════════════════════════════
    async def tg(self, msg):
        try:
            if not self.session: return
            if not self.tg_token or not self.tg_chat: return
            if len(msg) > 4000:
                for i in range(0, len(msg), 4000):
                    await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage", data={'chat_id': self.tg_chat, 'text': msg[i:i+4000], 'parse_mode': 'Markdown'})
                    await asyncio.sleep(0.5)
            else:
                await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage", data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'})
        except Exception as e: logger.error(f"فشل إرسال تيليجرام: {e}")

    # ═══════════════════════════════════════════════════
    #     وحدة بينانس API الأساسية (Async)
    # ═══════════════════════════════════════════════════
    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(self.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    async def _binance_request(self, method, endpoint, params=None, signed=False, is_trade_endpoint=False):
        try:
            base = self.trade_url if is_trade_endpoint else self.data_url
            url = f"{base}{endpoint}"
            headers = {}
            if signed:
                if not self.binance_api_key: return None
                params = self._sign(params or {})
                headers = {'X-MBX-APIKEY': self.binance_api_key}
            async with self.session.request(method, url, params=params, headers=headers) as r:
                if r.status == 200: return await r.json()
                elif r.status == 429: await asyncio.sleep(10); return None
                else: return None
        except Exception as e: logger.error(f"استثناء بينانس: {e}"); return None

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
                    if f['filterType'] == 'LOT_SIZE': self.step_sizes_cache[s['symbol']] = float(f['stepSize'])
        
        if self.known_symbols and (new_symbols_set - self.known_symbols):
            new_coins = new_symbols_set - self.known_symbols
            msg = "🆕 *عملات مدرجة حديثاً!*\n" + "\n".join([f"⚡ `{c}`" for c in new_coins])
            await self.tg(msg)

        self.usdt_pairs = new_pairs; self.known_symbols = new_symbols_set
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
        if df is None or len(df) < 10: return None
        if is_bullish_trend:
            for i in range(len(df)-1, 3, -1):
                prev_candle, curr_candle = df.iloc[i-1], df.iloc[i]
                if prev_candle['close'] < prev_candle['open'] and curr_candle['close'] > prev_candle['high']: return {'type': 'bullish', 'high': prev_candle['high'], 'low': prev_candle['low']}
        elif not is_bullish_trend:
            for i in range(len(df)-1, 3, -1):
                prev_candle, curr_candle = df.iloc[i-1], df.iloc[i]
                if prev_candle['close'] > prev_candle['open'] and curr_candle['close'] < prev_candle['low']: return {'type': 'bearish', 'high': prev_candle['high'], 'low': prev_candle['low']}
        return None

    # ═══════════════════════════════════════════════════
    #     التحليل المتعدد المؤشرات (7 مؤشرات + MTF + SMC)
    # ═══════════════════════════════════════════════════
    async def analyze_coin(self, symbol):
        try:
            df_4h = await self.get_klines(symbol, '4h', 50)
            if df_4h is None or len(df_4h) < 50: return None
            ema50_calc = ta.trend.EMAIndicator(df_4h['close'], window=50).ema_indicator()
            if ema50_calc.isna().iloc[-1]: return None
            ema50_4h = ema50_calc.iloc[-1]
            is_bullish_trend = df_4h.iloc[-1]['close'] > ema50_4h

            df_15m = await self.get_klines(symbol, '15m', 100)
            if df_15m is None or len(df_15m) < 50: return None
            price = df_15m.iloc[-1]['close']
            result = {'symbol': symbol, 'price': price, 'score': 0, 'signals': [], 'direction': None, 'rsi': None, 'volume_ratio': None}

            # 1. RSI
            rsi_val = ta.momentum.RSIIndicator(df_15m['close'], window=14).rsi().iloc[-1]
            result['rsi'] = round(rsi_val, 1)
            if is_bullish_trend and rsi_val < 25: result['score'] += 4; result['signals'].append(f"📈 RSI تشبع بيعي شديد ({rsi_val:.0f})")
            elif is_bullish_trend and rsi_val < 35: result['score'] += 2; result['signals'].append(f"📈 RSI تشبع بيعي ({rsi_val:.0f})")
            elif not is_bullish_trend and rsi_val > 75: result['score'] -= 4; result['signals'].append(f"📉 RSI تشبع شرائي شديد ({rsi_val:.0f})")

            # 2. MACD
            macd_ind = ta.trend.MACD(df_15m['close'])
            if macd_ind.macd().iloc[-1] > macd_ind.macd_signal().iloc[-1] and macd_ind.macd().iloc[-2] <= macd_ind.macd_signal().iloc[-2]:
                result['score'] += 3; result['signals'].append("📈 MACD تقاطع صعودي ⚡")
            elif macd_ind.macd().iloc[-1] < macd_ind.macd_signal().iloc[-1] and macd_ind.macd().iloc[-2] >= macd_ind.macd_signal().iloc[-2]:
                result['score'] -= 3; result['signals'].append("📉 MACD تقاطع هبوطي")

            # 3. EMA
            ema9, ema21 = ta.trend.EMAIndicator(df_15m['close'], window=9).ema_indicator(), ta.trend.EMAIndicator(df_15m['close'], window=21).ema_indicator()
            if ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2]:
                result['score'] += 2; result['signals'].append("📈 EMA9 تقاطع فوق EMA21")
            elif ema9.iloc[-1] < ema21.iloc[-1] and ema9.iloc[-2] >= ema21.iloc[-2]:
                result['score'] -= 2; result['signals'].append("📉 EMA9 تقاطع تحت EMA21")

            # 4. Bollinger Bands
            bb = ta.volatility.BollingerBands(df_15m['close'])
            bb_lower = bb.bollinger_lband().iloc[-1]
            if not pd.isna(bb_lower) and price <= bb_lower: result['score'] += 3; result['signals'].append("📈 لامس البولنجر السفلي (ارتداد)")

            # 5. Volume
            vol_avg, vol_current = df_15m['volume'].rolling(20).mean().iloc[-1], df_15m.iloc[-1]['volume']
            vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1
            result['volume_ratio'] = round(vol_ratio, 1)
            if vol_ratio > 3: result['score'] += 3; result['signals'].append(f"🔥 حجم ضخم! ({vol_ratio:.1f}x)")
            elif vol_ratio > 2: result['score'] += 2; result['signals'].append(f"📊 حجم عالي ({vol_ratio:.1f}x)")

            # 6. Stochastic
            stoch = ta.momentum.StochasticOscillator(high=df_15m['high'], low=df_15m['low'], close=df_15m['close'])
            k, d = stoch.stoch().iloc[-1], stoch.stoch_signal().iloc[-1]
            k_prev, d_prev = stoch.stoch().iloc[-2], stoch.stoch_signal().iloc[-2]
            if k < 20 and d < 20 and k_prev < d_prev and k > d: result['score'] += 3; result['signals'].append("📈 Stochastic تقاطع صعودي بالقاع")

            # 7. Price Change
            if len(df_15m) >= 25:
                change_24h = ((df_15m.iloc[-1]['close'] - df_15m.iloc[-25]['close']) / df_15m.iloc[-25]['close']) * 100
                if is_bullish_trend and -15 < change_24h < -5: result['score'] += 2; result['signals'].append(f"📉 هبوط {change_24h:.1f}% (فرصة!)")
                elif not is_bullish_trend and change_24h > 20: result['score'] -= 2; result['signals'].append(f"⚠️ صعود حاد {change_24h:.1f}%")

            # 8. Order Block (SMC)
            ob = self.detect_order_blocks(df_15m, is_bullish_trend)
            if ob and is_bullish_trend and ob['type'] == 'bullish' and ob['low'] <= price <= ob['high'] * 1.01:
                result['score'] += 4; result['signals'].append("🧠 ارتداد من Order Block (فرصة ذهبية!)")
            elif ob and not is_bullish_trend and ob['type'] == 'bearish' and ob['high'] >= price >= ob['low'] * 0.99:
                result['score'] -= 4; result['signals'].append("🧠 ارتداد من Order Block هبوطي")

            # تحديد الاتجاه
            if is_bullish_trend and result['score'] >= self.MIN_SCORE_TO_TRADE: result['direction'] = 'BUY'
            elif not is_bullish_trend and result['score'] <= -self.MIN_SCORE_TO_TRADE: result['direction'] = 'SELL'

            return result
        except Exception as e: logger.error(f"خطأ تحليل {symbol}: {e}"); return None

    # ═══════════════════════════════════════════════════
    #     حساب SL/TP المرن بناءً على ATR
    # ═══════════════════════════════════════════════════
    async def calculate_dynamic_sl_tp(self, symbol, entry_price):
        df = await self.get_klines(symbol, '15m', 30)
        if df is None or len(df) < 15: return entry_price * 0.97, entry_price * 1.06, entry_price * 1.03, 3.0
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_indicator.average_true_range().iloc[-1]
        if pd.isna(atr): return entry_price * 0.97, entry_price * 1.06, entry_price * 1.03, 3.0
        atr_pct = (atr / entry_price) * 100
        sl_distance, tp1_distance = atr_pct * 1.5, atr_pct * 3.0
        trailing_activation = entry_price * (1 + (atr_pct * 1.5) / 100)
        trailing_distance_pct = max(sl_distance, 1.5)
        sl_price = max(min(entry_price * (1 - sl_distance / 100), entry_price * 0.98), entry_price * 0.90)
        tp1_price = entry_price * (1 + tp1_distance / 100)
        return round(sl_price, 6), round(tp1_price, 6), round(trailing_activation, 6), round(trailing_distance_pct, 2)

    # ═══════════════════════════════════════════════════
    #       التداول التلقائي (شراء وبيع Spot)
    # ═══════════════════════════════════════════════════
    async def execute_trade(self, analysis):
        symbol, direction, score, price = analysis['symbol'], analysis['direction'], analysis['score'], analysis['price']
        if not self.TRADE_ENABLED or direction != 'BUY': return
        if len(self.active_trades) >= self.MAX_OPEN_TRADES or symbol in self.active_trades: return
        balance_data = await self._binance_request('GET', '/api/v3/account', signed=True, is_trade_endpoint=True)
        usdt_balance = 0
        if balance_data:
            for b in balance_data.get('balances', []):
                if b['asset'] == 'USDT': usdt_balance = float(b['free'])
        trade_amount = usdt_balance * (self.RISK_PER_TRADE_PCT / 100)
        if trade_amount < self.MIN_TRADE_USDT: return

        sl_price, tp_price, trailing_act, trailing_dist = await self.calculate_dynamic_sl_tp(symbol, price)
        result = await self._binance_request('POST', '/api/v3/order', {'symbol': symbol, 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': round(trade_amount, 2)}, signed=True, is_trade_endpoint=True)

        if result and result.get('status') == 'FILLED':
            self.stats['trades_executed'] += 1
            fills = result.get('fills', [])
            fill_price = float(fills[0]['price']) if fills else price
            fill_qty = float(fills[0]['qty']) if fills else 0
            
            self.active_trades[symbol] = {'entry_price': fill_price, 'quantity': fill_qty, 'direction': 'BUY', 'stop_loss': sl_price, 'take_profit': tp_price, 'trailing_activation': trailing_act, 'trailing_distance_pct': trailing_dist, 'highest_price': fill_price, 'trailing_active': False, 'entry_time': time.time(), 'score': score, 'max_profit_pct': 0}
            self._save_active_trades()
            msg = f"✅ *صفقة شراء منفذة (وقف مرن)!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n🪙 `{symbol}`\n💵 الدخول: `{fill_price:.6f}`\n💰 المبلغ: `${trade_amount:.2f}`\n🛑 وقف الخسارة: `{sl_price:.6f}`\n🎯 هدف الربح: `{tp_price:.6f}`\n📈 نقاط: *{score}*"
            await self.tg(msg)

    # ═══════════════════════════════════════════════════
    #    مراقبة الصفقات بالوقف المتحرك (Trailing)
    # ═══════════════════════════════════════════════════
    async def monitor_trades(self):
        if not self.active_trades: return
        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            current_price = self.live_prices.get(symbol)
            if not current_price: continue
            entry_price = trade['entry_price']
            if current_price > trade['highest_price']: trade['highest_price'] = current_price
            current_profit_pct = ((current_price - entry_price) / entry_price) * 100
            if current_profit_pct > trade.get('max_profit_pct', 0): trade['max_profit_pct'] = round(current_profit_pct, 2)

            closed, close_reason = False, ""
            if current_price <= trade['stop_loss'] and not trade['trailing_active']: closed, close_reason = True, "🛑 تم ضرب وقف الخسارة"
            elif current_price >= trade['take_profit'] and not trade['trailing_active']:
                trade['trailing_active'] = True; trade['stop_loss'] = entry_price * 1.005
                await self.tg(f"⚡ *تفعيل الوقف المتحرك! `{symbol}`*\n🎯 وصلنا الهدف الأول\n🛑 الوقف الجديد: `{trade['stop_loss']:.6f}`")
                self._save_active_trades()
            elif trade['trailing_active']:
                new_sl = trade['highest_price'] * (1 - trade['trailing_distance_pct'] / 100)
                if new_sl > trade['stop_loss']: trade['stop_loss'] = new_sl
                if current_price <= trade['stop_loss']: closed, close_reason = True, f"🔄 وقف متحرك حافظ على الأرباح!\n🏆 أقصى ربح وصل: {trade['max_profit_pct']:.1f}%"
            elif time.time() - trade['entry_time'] > 259200 and current_profit_pct > -1: closed, close_reason = True, f"⏰ انتهاء الوقت (ربح {current_profit_pct:.1f}%)"

            if closed:
                step_size = self.step_sizes_cache.get(symbol, 1)
                precision = len(str(step_size).rstrip('0').split('.')[-1]) if step_size < 1 else 0
                qty = math.floor(trade['quantity'] * (10 ** precision)) / (10 ** precision)
                result = await self._binance_request('POST', '/api/v3/order', {'symbol': symbol, 'side': 'SELL', 'type': 'MARKET', 'quantity': qty}, signed=True, is_trade_endpoint=True)
                
                fill_price = current_price
                if result and result.get('fills'): fill_price = float(result['fills'][0]['price'])
                pnl_usdt = (fill_price - entry_price) * trade['quantity']
                pnl_pct = ((fill_price - entry_price) / entry_price) * 100
                is_win = pnl_usdt > 0
                if is_win: self.stats['wins'] += 1
                else: self.stats['losses'] += 1
                icon = "✅" if is_win else "❌"
                msg = f"🏁 *إغلاق `{symbol}`*\n━━━━━━━━━━━━━━━━━━━━━━━━\n{close_reason}\n💵 الدخول: `{entry_price:.6f}` | الإغلاق: `{fill_price:.6f}`\n{icon} النتيجة: `{pnl_usdt:.2f} USDT ({pnl_pct:+.2f}%)`\n🏆 أقصى ربح وصل: *{trade['max_profit_pct']:.1f}%*\n📊 الإحصائيات: {self.stats['wins']}W / {self.stats['losses']}L"
                await self.tg(msg)
                del self.active_trades[symbol]; self._save_active_trades()

    # ═══════════════════════════════════════════════════
    #           وحدات البحث الخارجية المجانية
    # ═══════════════════════════════════════════════════
    async def check_binance_announcements(self):
        try:
            async with self.session.get("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query", params={'type': 1, 'catalogId': 48, 'pageNo': 1, 'pageSize': 5}, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    for article in data.get('data', {}).get('articles', []):
                        title = article.get('title', '').upper()
                        if any(kw in title for kw in ['LIST', 'LISTING', 'LAUNCH', 'WILL LIST']):
                            if article.get('releaseDate', 0) > (time.time() * 1000 - 3600000):
                                await self.tg(f"🚨 *إعلان إدراج جديد!*\n📢 {article.get('title')}\n⚡ عادة ترتفع بشدة!")
        except Exception: pass

    async def scan_coingecko_trending(self):
        try:
            async with self.session.get("https://api.coingecko.com/api/v3/search/trending", timeout=10) as r:
                if r.status != 200: return
                data = await r.json()
                msg = "🔥 *عملات رائجة على CoinGecko*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for i, c in enumerate(data.get('coins', [])[:5]):
                    item = c.get('item', {}); sym = item.get('symbol', '').upper()
                    on_binance = "✅" if f"{sym}USDT" in self.known_symbols else "❌"
                    msg += f"{i+1}. 🪙 *{item.get('name')}* (`{sym}`) على بينانس: {on_binance}\n"
                await self.tg(msg)
        except Exception: pass

    async def check_fear_greed(self):
        try:
            async with self.session.get("https://api.alternative.me/fng/?limit=1", timeout=10) as r:
                if r.status == 200:
                    fng = (await r.json()).get('data', [{}])[0]
                    val, label = int(fng.get('value', 50)), fng.get('value_classification', 'Neutral')
                    emoji = {'Extreme Fear': '😱', 'Fear': '😨', 'Neutral': '😐', 'Greed': '😊', 'Extreme Greed': '🤑'}.get(label, '😐')
                    tip = "فرص شراء ممتازة!" if val < 25 else "حذر من التصحيح!" if val > 75 else ""
                    await self.tg(f"{emoji} *مؤشر الخوف والطمع*: {val}/100 ({label})\n💡 {tip}")
        except Exception: pass

    async def detect_volume_spikes(self):
        data = await self._binance_request('GET', '/api/v3/ticker/24hr')
        if not data: return
        spikes = []
        for t in data:
            sym, vol, chg = t.get('symbol', ''), float(t.get('quoteVolume', 0)), float(t.get('priceChangePercent', 0))
            if sym.endswith('USDT') and vol > 5000000 and 2 < chg < 20: spikes.append({'symbol': sym, 'vol': vol, 'chg': chg})
        if spikes:
            spikes.sort(key=lambda x: x['vol'], reverse=True)
            msg = "📊 *ارتفاعات حجم (ضخ أموال)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, s in enumerate(spikes[:5]): msg += f"{i+1}. `{s['symbol']}` | 💧 ${s['vol']/1e6:.1f}M | 📈 {s['chg']:+.1f}%\n"
            await self.tg(msg)

    # ═══════════════════════════════════════════════════
    #       المسح السريع والشامل للسوق
    # ═══════════════════════════════════════════════════
    async def quick_scan(self):
        found = []
        for coin in self.priority:
            sym = f"{coin}USDT"
            if sym in self.known_symbols and sym not in self.active_trades:
                a = await self.analyze_coin(sym)
                if a and a['score'] >= self.MIN_SCORE_TO_TRADE: found.append(a)
                await asyncio.sleep(0.3)
        if found:
            found.sort(key=lambda x: x['score'], reverse=True)
            msg = "⚡ *فحص سريع — فرص قوية!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(found[:3]): msg += f"🟢 `{a['symbol']}` | نقاط: *{a['score']}* | ${a['price']:.4f}\n"
            await self.tg(msg)
            await self.execute_trade(found[0])

    # ═══════════════════════════════════════════════════
    #       حفظ واسترجاع الصفقات (JSON)
    # ═══════════════════════════════════════════════════
    def _save_active_trades(self):
        try:
            with open('active_trades.json', 'w') as f: json.dump(self.active_trades, f)
        except Exception: pass

    def _load_active_trades(self):
        try:
            if os.path.exists('active_trades.json'):
                with open('active_trades.json', 'r') as f: self.active_trades = json.load(f)
                if self.active_trades: logger.info(f"📂 تم استرجاع {len(self.active_trades)} صفقة مفتوحة")
        except Exception: self.active_trades = {}

    # ═══════════════════════════════════════════════════
    # بديل WebSockets: سحب الأسعار اللحظية لتجاوز الحظر
    # ═══════════════════════════════════════════════════
    async def price_poller(self):
        logger.info("🔄 بدء سحب الأسعار اللحظية عبر REST API...")
        while True:
            try:
                data = await self._binance_request('GET', '/api/v3/ticker/price')
                if data:
                    for item in data: self.live_prices[item['symbol']] = float(item['price'])
            except Exception as e: logger.error(f"خطأ في سحب الأسعار: {e}")
            await asyncio.sleep(3)

    # ═══════════════════════════════════════════════════
    #          القلب النابض (Main Async Loop)
    # ═══════════════════════════════════════════════════
    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.load_market_data()
        self._load_active_trades()
        await self.tg("🔥 *القناص الأسطوري V3.0 بدأ العمل! (Testnet Demo)*\n🚀 يعمل بـ Asyncio + Anti-Ban Polling")
        
        asyncio.create_task(self.price_poller())
        
        try:
            while True:
                now = time.time()
                await self.monitor_trades()

                if now - self.last_announcement_check > 300:
                    await self.check_binance_announcements(); self.last_announcement_check = now

                if now - self.last_volume_scan > 900:
                    await self.quick_scan(); await self.detect_volume_spikes(); self.last_volume_scan = now

                if now - self.last_coingecko_check > 1800:
                    await self.scan_coingecko_trending(); await self.check_fear_greed(); self.last_coingecko_check = now

                if now - self.last_full_scan > 10800:
                    await self.load_market_data(); self.last_full_scan = now

                await asyncio.sleep(2)
        except Exception as e: logger.critical(f"انهيار النظام الرئيسي: {e}")
        finally: await self.session.close()

    def start(self): asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperBotV3()
    bot.start()
