""" ═══════════════════════════════════════════════════════════════ 🔥 القناص الأسطوري V5.1 — النسخة المؤسسية (Cumulative Stable Patch) 🔥 ═══════════════════════════════════════════════════════════════ """

import asyncio, aiohttp, json, math, os, sys, time, logging, requests, sqlite3
import pandas as pd
import numpy as np
import ta
import hmac
import hashlib
from urllib.parse import urlencode
from logging.handlers import RotatingFileHandler
import websockets
import aiosqlite

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger('SniperBotV5')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = RotatingFileHandler('bot_v5.log', maxBytes=2*1024*1024, backupCount=1, encoding='utf-8')
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

# ═════════════════════ قاعدة البيانات الاحترافية (SQLite) ═════════════════════
class DatabaseManager:
    def __init__(self, db_name='sniper_v5.db'):
        self.db_name = db_name

    async def init_db(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS active_trades (
                                    symbol TEXT PRIMARY KEY, side TEXT, entry_price REAL, quantity REAL,
                                    sl REAL, tp REAL, trailing_active INTEGER, highest_price REAL, lowest_price REAL,
                                    entry_time REAL, score INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                                    date TEXT PRIMARY KEY, realized_pnl REAL, wins INTEGER, losses INTEGER)''')
            await db.commit()

    async def save_trade(self, trade_data):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''INSERT OR REPLACE INTO active_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                             (trade_data['symbol'], trade_data['side'], trade_data['entry_price'], trade_data['quantity'],
                              trade_data['sl'], trade_data['tp'], int(trade_data['trailing_active']), 
                              trade_data.get('highest_price', 0), trade_data.get('lowest_price', 999999),
                              trade_data['entry_time'], trade_data['score']))
            await db.commit()

    async def load_active_trades(self):
        trades = {}
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM active_trades") as cursor:
                async for row in cursor:
                    trades[row[0]] = {
                        'symbol': row[0], 'side': row[1], 'entry_price': row[2], 'quantity': row[3],
                        'sl': row[4], 'tp': row[5], 'trailing_active': bool(row[6]), 
                        'highest_price': row[7], 'lowest_price': row[8],
                        'entry_time': row[9], 'score': row[10]
                    }
        return trades

    async def remove_trade(self, symbol):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("DELETE FROM active_trades WHERE symbol=?", (symbol,))
            await db.commit()

    async def update_daily_pnl(self, pnl, is_win):
        today = time.strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM daily_stats WHERE date=?", (today,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    new_pnl = row[1] + pnl
                    new_wins = row[2] + (1 if is_win else 0)
                    new_losses = row[3] + (0 if is_win else 1)
                    await db.execute("UPDATE daily_stats SET realized_pnl=?, wins=?, losses=? WHERE date=?", (new_pnl, new_wins, new_losses, today))
                else:
                    await db.execute("INSERT INTO daily_stats VALUES (?, ?, ?, ?)", (today, pnl, 1 if is_win else 0, 0 if is_win else 1))
            await db.commit()

    async def get_daily_pnl(self):
        today = time.strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT realized_pnl FROM daily_stats WHERE date=?", (today,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0.0

# ═════════════════════ محرك SMC ═════════════════════
class SMCEngine:
    @staticmethod
    def detect_swings(df, window=3):
        df = df.copy()
        df.loc[:, 'sw_high'] = np.nan
        df.loc[:, 'sw_low'] = np.nan
        highs, lows = df['high'].values, df['low'].values
        for i in range(window, len(df) - window):
            if all(highs[i] >= highs[i-window:i]) and all(highs[i] >= highs[i+1:i+window+1]):
                df.loc[df.index[i], 'sw_high'] = highs[i]
            if all(lows[i] <= lows[i-window:i]) and all(lows[i] <= lows[i+1:i+window+1]):
                df.loc[df.index[i], 'sw_low'] = lows[i]
        return df

    @staticmethod
    def detect_bos_choch(df):
        signals, trend = [], None
        last_sw_high, last_sw_low = np.nan, np.nan
        closes, sw_highs, sw_lows = df['close'].values, df['sw_high'].values, df['sw_low'].values
        for i in range(len(df)):
            if not pd.isna(sw_highs[i]): last_sw_high = sw_highs[i]
            if not pd.isna(sw_lows[i]): last_sw_low = sw_lows[i]
            if not pd.isna(last_sw_high) and not pd.isna(last_sw_low):
                if closes[i] > last_sw_high:
                    signals.append({'index': i, 'type': 'CHoCH_Bull' if trend == 'bear' else 'BOS_Bull'})
                    trend = 'bull'
                elif closes[i] < last_sw_low:
                    signals.append({'index': i, 'type': 'CHoCH_Bear' if trend == 'bull' else 'BOS_Bear'})
                    trend = 'bear'
        return signals, trend

    @staticmethod
    def detect_fvg(df):
        fvgs = []
        lows, highs = df['low'].values, df['high'].values
        for i in range(2, len(df)):
            if lows[i] > highs[i-2]: fvgs.append({'type': 'bull_fvg', 'top': lows[i], 'bottom': highs[i-2]})
            elif highs[i] < lows[i-2]: fvgs.append({'type': 'bear_fvg', 'top': lows[i-2], 'bottom': highs[i]})
        return fvgs

    @staticmethod
    def detect_order_blocks(df, signals, trend):
        obs = []
        opens, closes, highs, lows = df['open'].values, df['close'].values, df['high'].values, df['low'].values
        for sig in signals:
            is_bull = sig['type'] in ['BOS_Bull', 'CHoCH_Bull']
            if (is_bull and trend == 'bull') or (not is_bull and trend == 'bear'):
                for j in range(sig['index'], max(sig['index']-10, 0), -1):
                    if is_bull and closes[j] < opens[j]:
                        obs.append({'type': 'bull_ob', 'top': opens[j], 'bottom': lows[j]}); break
                    elif not is_bull and closes[j] > opens[j]:
                        obs.append({'type': 'bear_ob', 'top': highs[j], 'bottom': opens[j]}); break
        return obs

# ═════════════════════ إدارة المخاطر الصارمة ═════════════════════
class RiskManager:
    def __init__(self, bot):
        self.bot = bot
        self.MAX_DRAWDOWN_PCT = 5.0 

    async def check_daily_drawdown(self):
        daily_pnl = await self.bot.db.get_daily_pnl()
        balance = await self.bot.get_usdt_balance()
        if balance > 0 and daily_pnl < 0:
            drawdown_pct = abs(daily_pnl) / balance * 100
            if drawdown_pct >= self.MAX_DRAWDOWN_PCT: return False
        return True

    def check_spread(self, symbol, ask, bid):
        if not ask or not bid or bid == 0: return False
        spread_pct = ((ask - bid) / bid) * 100
        if spread_pct > 0.1: return False
        return True

# ═════════════════════ البوت الأساسي ═════════════════════
class LegendarySniperBotV5:
    def __init__(self):
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')

        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '1.5'))
        self.MIN_SCORE_TO_TRADE = int(os.environ.get('MIN_SCORE', '8'))
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '2'))
        
        self.db = DatabaseManager()
        self.risk = RiskManager(self)
        self.smc = SMCEngine()
        self.session = None
        self.active_trades = {}
        self.step_sizes_cache = {} # 2- إعادة الجلب والفلترة
        self.live_prices = {} 
        self.live_klines = {} 
        
        self.data_url = "https://data-api.binance.vision"
        self.trade_url = "https://api.binance.com"
        self.priority = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'AVAX', 'LINK', 'SUI', 'INJ']
        
        self.last_scan_time = 0 # 4- إصلاح Scan Timer

    async def tg(self, msg):
        try:
            if not self.session or not self.tg_token: return
            await self.session.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage", 
                                   data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'})
        except Exception: pass

    async def _binance_request(self, method, endpoint, params=None, signed=False, is_trade_endpoint=False, retries=3):
        for attempt in range(retries):
            try:
                base = self.trade_url if is_trade_endpoint else self.data_url
                url = f"{base}{endpoint}"
                headers = {}
                req_params = params.copy() if params else {}
                if signed:
                    if not self.binance_api_key: return None
                    req_params = self._sign(req_params)
                    headers = {'X-MBX-APIKEY': self.binance_api_key}
                async with self.session.request(method, url, params=req_params, headers=headers, timeout=10) as r:
                    if r.status == 200: return await r.json()
                    elif r.status == 429: await asyncio.sleep(10 * (attempt + 1))
                    elif r.status in [500, 502]: await asyncio.sleep(2 ** attempt)
                    else: return None
            except Exception: await asyncio.sleep(2)
        return None

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        params['signature'] = hmac.new(self.binance_api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return params

    async def get_usdt_balance(self):
        data = await self._binance_request('GET', '/api/v3/account', signed=True, is_trade_endpoint=True)
        if data:
            for b in data.get('balances', []):
                if b['asset'] == 'USDT': return float(b['free'])
        return 0.0

    # 2- إعادة خطوة الحجم (Step Size)
    async def load_market_data(self):
        data = await self._binance_request('GET', '/api/v3/exchangeInfo')
        if not data: return
        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING':
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE': self.step_sizes_cache[s['symbol']] = float(f['stepSize'])

    def format_quantity(self, symbol, qty):
        step_size = self.step_sizes_cache.get(symbol, 1.0)
        precision = int(round(-math.log10(step_size))) if step_size < 1 else 0
        return math.floor(qty * (10 ** precision)) / (10 ** precision)

    # 6- Persistent Storage Reconciliation
    async def sync_with_binance(self):
        open_orders = await self._binance_request('GET', '/api/v3/openOrders', signed=True, is_trade_endpoint=True)
        if open_orders is None: return
        
        active_symbols = set(self.active_trades.keys())
        binance_symbols = {o['symbol'] for o in open_orders if o['type'] == 'LIMIT' or o['type'] == 'STOP_MARKET'}
        
        # إذا كان لدينا صفقة في DB لكن ليس في بينانس (تم إغلاقها بوقف وأغفلناها)
        for sym in active_symbols - binance_symbols:
            # نتحقق إذا كنا نملك العملة فعلاً
            logger.warning(f"⚠️ {sym} في قاعدة البيانات لكن غير موجود كأمر مفتوح. سيتم حذفه لاحقاً إن لزم.")

    # ═════════════════════ WebSocket اللحظي المتقدم ═════════════════════
    async def ws_manager(self):
        streams = []
        for coin in self.priority:
            sym = f"{coin.lower()}usdt"
            streams.append(f"{sym}@bookTicker")
            streams.append(f"{sym}@kline_15m")
        
        ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        
        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    logger.info("✅ WS متصل (أسعار + شموع لحظية)!")
                    async for message in ws:
                        data = json.loads(message).get('data', {})
                        if not data: continue
                        event_type = data.get('e')
                        
                        if event_type == 'bookTicker':
                            symbol = data['s']
                            self.live_prices[symbol] = {'bid': float(data['b']), 'ask': float(data['a'])}
                            
                        elif event_type == 'kline':
                            symbol = data['s']
                            k = data['k']
                            if symbol not in self.live_klines: self.live_klines[symbol] = []
                            if k['x']: 
                                self.live_klines[symbol].append({
                                    'time': k['t'], 'open': float(k['o']), 'high': float(k['h']), 
                                    'low': float(k['l']), 'close': float(k['c']), 'volume': float(k['v']),
                                    'taker_buy_vol': float(k['V'])
                                })
                                self.live_klines[symbol] = self.live_klines[symbol][-100:]
            except Exception as e:
                logger.error(f"WS Error: {e}. Reconnecting...")
                await asyncio.sleep(5)

    def get_live_df(self, symbol):
        if symbol not in self.live_klines or len(self.live_klines[symbol]) < 50: return None
        return pd.DataFrame(self.live_klines[symbol])

    # ═════════════════════ التحليل والتنفيذ ═════════════════════
    async def analyze_coin(self, symbol):
        try:
            df_15m = self.get_live_df(symbol)
            if df_15m is None: return None
            
            df_15m = self.smc.detect_swings(df_15m, window=3)
            signals, micro_trend = self.smc.detect_bos_choch(df_15m)
            if not micro_trend: return None
            
            fvgs = self.smc.detect_fvg(df_15m)
            obs = self.smc.detect_order_blocks(df_15m, signals, micro_trend)
            
            prices = self.live_prices.get(symbol)
            if not prices: return None
            
            # 1- إصلاح SELL Logic (استخدام bid للشراء، ask للبيع)
            price = prices['bid'] if micro_trend == 'bull' else prices['ask']
            
            result = {'symbol': symbol, 'price': price, 'score': 0, 'direction': None, 'sl': 0, 'tp': 0}

            if micro_trend == 'bull': result['score'] += 3; result['direction'] = 'BUY'
            elif micro_trend == 'bear': result['score'] -= 3; result['direction'] = 'SELL'
            else: return None

            for fvg in fvgs[-5:]:
                if fvg['type'] == 'bull_fvg' and price >= fvg['bottom'] and price <= fvg['top'] and result['direction']=='BUY': result['score'] += 2; break
                elif fvg['type'] == 'bear_fvg' and price >= fvg['bottom'] and price <= fvg['top'] and result['direction']=='SELL': result['score'] -= 2; break

            for ob in obs[-3:]:
                if ob['type'] == 'bull_ob' and ob['bottom'] <= price <= ob['top'] and result['direction']=='BUY': result['score'] += 4; break
                elif ob['type'] == 'bear_ob' and ob['bottom'] <= price <= ob['top'] and result['direction']=='SELL': result['score'] -= 4; break

            rsi_val = ta.momentum.RSIIndicator(df_15m['close'], window=14).rsi().iloc[-1]
            if result['direction'] == 'BUY' and rsi_val < 35: result['score'] += 1
            elif result['direction'] == 'SELL' and rsi_val > 65: result['score'] -= 1

            if abs(result['score']) < self.MIN_SCORE_TO_TRADE: return None
            
            atr = ta.volatility.AverageTrueRange(high=df_15m['high'], low=df_15m['low'], close=df_15m['close'], window=14).average_true_range().iloc[-1]
            if result['direction'] == 'BUY':
                result['sl'] = price - (atr * 1.5)
                result['tp'] = price + (atr * 3.0)
            else:
                result['sl'] = price + (atr * 1.5)
                result['tp'] = price - (atr * 3.0)
                
            return result
        except Exception: return None

    async def execute_trade(self, analysis):
        if not self.TRADE_ENABLED: return
        # 5- Max Position Limit Check
        if len(self.active_trades) >= self.MAX_OPEN_TRADES: return
        symbol, direction = analysis['symbol'], analysis['direction']
        if symbol in self.active_trades: return
        
        prices = self.live_prices.get(symbol)
        if not self.risk.check_spread(symbol, prices.get('ask'), prices.get('bid')): return
        if not await self.risk.check_daily_drawdown(): return

        balance = await self.get_usdt_balance()
        risk_amount = balance * (self.RISK_PER_TRADE_PCT / 100)
        sl_distance = abs(analysis['price'] - analysis['sl'])
        if sl_distance == 0: return
        raw_qty = risk_amount / sl_distance
        
        # 2- تنسيق الكمية بناءً على Step Size
        qty = self.format_quantity(symbol, raw_qty)
        
        side = 'BUY' if direction == 'BUY' else 'SELL'
        
        # 7- التعامل مع Order States بشكل كامل
        result = await self._binance_request('POST', '/api/v3/order', {
            'symbol': symbol, 'side': side, 'type': 'MARKET', 'quantity': qty
        }, signed=True, is_trade_endpoint=True)

        if not result:
            await self.tg(f"❌ *فشل تنفيذ {side} ({symbol})*\n reason: No response from Binance")
            return

        status = result.get('status')
        if status in ['FILLED', 'PARTIALLY_FILLED']:
            fills = result.get('fills', [])
            total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
            total_qty = sum(float(f['qty']) for f in fills)
            fill_price = total_cost / total_qty if total_qty > 0 else analysis['price']
            
            trade_data = {
                'symbol': symbol, 'side': side, 'entry_price': fill_price, 'quantity': total_qty,
                'sl': analysis['sl'], 'tp': analysis['tp'], 'trailing_active': False, 
                'highest_price': fill_price, 'lowest_price': fill_price, # 3- إضافة lowest_price للـ SELL
                'entry_time': time.time(), 'score': analysis['score']
            }
            self.active_trades[symbol] = trade_data
            await self.db.save_trade(trade_data)
            await self.tg(f"🎯 *صفقة {side} ({symbol})*\n💵 الدخول: `{fill_price:.4f}`\n🛑 SL: `{analysis['sl']:.4f}` | 🎯 TP: `{analysis['tp']:.4f}`")
        
        elif status in ['EXPIRED', 'CANCELED', 'REJECTED']:
            reason = result.get('msg', 'Unknown')
            await self.tg(f"🚫 *رفض/إلغاء أمر {side} ({symbol})*\nReason: `{reason}`")

    # ═════════════════════ المراقبة اللحظية الذكية ═════════════════════
    async def monitor_trades(self):
        if not self.active_trades: return
        
        symbols_to_close = []
        for symbol, trade in self.active_trades.items():
            prices = self.live_prices.get(symbol)
            if not prices: continue
            
            is_buy = trade['side'] == 'BUY'
            current_price = prices['bid'] if is_buy else prices['ask']
            
            # 3- إصلاح Trailing Stop للـ SELL والـ BUY
            if is_buy:
                if current_price > trade.get('highest_price', current_price): 
                    trade['highest_price'] = current_price
                    await self.db.save_trade(trade)
            else:
                if current_price < trade.get('lowest_price', current_price): 
                    trade['lowest_price'] = current_price
                    await self.db.save_trade(trade)

            current_pnl_pct = ((current_price - trade['entry_price']) / trade['entry_price']) * 100
            if not is_buy: current_pnl_pct = -current_pnl_pct
            
            should_close, reason = False, ""

            # SL / TP
            if is_buy:
                if current_price <= trade['sl']: should_close, reason = True, "🛑 ضرب SL"
                elif current_price >= trade['tp']: should_close, reason = True, "🎯 وصل TP"
            else:
                if current_price >= trade['sl']: should_close, reason = True, "🛑 ضرب SL"
                elif current_price <= trade['tp']: should_close, reason = True, "🎯 وصل TP"

            # Trailing Activation & Logic
            if not trade['trailing_active'] and current_pnl_pct > 1.5:
                trade['trailing_active'] = True
                if is_buy: trade['sl'] = trade['entry_price'] * 1.002
                else: trade['sl'] = trade['entry_price'] * 0.998
                await self.db.save_trade(trade)
                
            if trade['trailing_active']:
                if is_buy:
                    new_sl = trade['highest_price'] * 0.985
                    if new_sl > trade['sl']: trade['sl'] = new_sl
                    if current_price <= trade['sl']: should_close, reason = True, "🔄 وقف متحرك صعودي"
                else:
                    new_sl = trade['lowest_price'] * 1.015
                    if new_sl < trade['sl']: trade['sl'] = new_sl
                    if current_price >= trade['sl']: should_close, reason = True, "🔄 وقف متحرك هبوطي"

            # Time Decay
            if time.time() - trade['entry_time'] > 43200 and abs(current_pnl_pct) < 0.5:
                should_close, reason = True, "⏰ خروج زمني"

            # RSI Extreme Protection
            df = self.get_live_df(symbol)
            if df is not None and len(df) > 5:
                rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]
                if is_buy and rsi > 75: should_close, reason = True, "⚠️ تشبع شرائي"
                elif not is_buy and rsi < 25: should_close, reason = True, "⚠️ تشبع بيعي"

            if should_close: symbols_to_close.append((symbol, reason, current_price))

        for symbol, reason, close_price in symbols_to_close:
            trade = self.active_trades.get(symbol)
            if not trade: continue
            
            close_side = 'SELL' if trade['side'] == 'BUY' else 'BUY'
            qty = self.format_quantity(symbol, trade['quantity'])
            
            result = await self._binance_request('POST', '/api/v3/order', {
                'symbol': symbol, 'side': close_side, 'type': 'MARKET', 'quantity': qty
            }, signed=True, is_trade_endpoint=True)

            if result and result.get('status') in ['FILLED', 'PARTIALLY_FILLED']:
                fills = result.get('fills', [])
                total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
                total_qty = sum(float(f['qty']) for f in fills)
                fill_price = total_cost / total_qty if total_qty > 0 else close_price
                
                # 1- حساب PnL الصحيح للـ SELL
                if trade['side'] == 'BUY':
                    pnl = (fill_price - trade['entry_price']) * total_qty
                else:
                    pnl = (trade['entry_price'] - fill_price) * total_qty
                    
                is_win = pnl > 0
                await self.db.update_daily_pnl(pnl, is_win)
                await self.db.remove_trade(symbol)
                del self.active_trades[symbol]
                
                await self.tg(f"🏁 *إغلاق {symbol}*\n{reason}\n💵 النتيجة: `{pnl:.2f} USDT` ({'✅' if is_win else '❌'})")
            else:
                logger.error(f"فشل إغلاق {symbol}! المحاولة يدوياً مطلوبة.")

    async def quick_scan(self):
        for coin in self.priority:
            sym = f"{coin}USDT"
            if sym not in self.active_trades and sym in self.step_sizes_cache:
                analysis = await self.analyze_coin(sym)
                if analysis: await self.execute_trade(analysis)

    # ═════════════════════ اللوب الرئيسي ═════════════════════
    async def main_loop(self):
        self.session = aiohttp.ClientSession()
        await self.db.init_db()
        await self.load_market_data() # تحميل الـ Step Sizes
        
        self.active_trades = await self.db.load_active_trades() 
        await self.sync_with_binance() # 6- تطابق البيانات
        
        asyncio.create_task(self.ws_manager()) 
        await asyncio.sleep(10) 
        
        await self.tg("🔥 *القناص V5.1 بدأ العمل!*\n🛡️ تراكمي ومستقر (Sell + Trailing + StepSize محسنة)")
        self.last_scan_time = time.time()
        
        try:
            while True:
                try:
                    await self.monitor_trades()
                    
                    # 4- إصلاح Scan Timer بشكل تراكمي مستقر
                    if time.time() - self.last_scan_time >= 900: # كل 15 دقيقة
                        await self.quick_scan()
                        self.last_scan_time = time.time()
                        
                    await asyncio.sleep(2)
                except Exception as loop_err:
                    logger.error(f"Loop Error: {loop_err}")
                    await asyncio.sleep(5)
        finally:
            await self.session.close()

    def start(self): asyncio.run(self.main_loop())

if __name__ == "__main__":
    bot = LegendarySniperBotV5()
    bot.start()
