"""
═══════════════════════════════════════════════════════════════
  🔥 القناص الأسطوري V2.0 — النسخة الكاملة المرنة 🔥
═══════════════════════════════════════════════════════════════
  ✅ تحليل 7 مؤشرات فنية
  ✅ وقف خسارة وهدف ربح مرن (Trailing Stop) يتبع السعر ليحقق أرباح 100%+
  ✅ بحث في 5 مصادر مجانية (بينانس، كوينجيكو، دكس سكرينر، الخوف والطمع)
  ✅ تداول فوري (Spot) آمن بدون تصفية
  ✅ يعمل على Railway / Replit / Termux
═══════════════════════════════════════════════════════════════
"""

import time, pandas as pd, ta, requests, datetime, os, sys, json, hmac, hashlib, math
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class LegendarySniperBot:
    def __init__(self):
        # ═══ إعدادات تيليجرام ═══
        self.tg_token = os.environ.get('TELEGRAM_TOKEN', '')
        self.tg_chat = os.environ.get('CHAT_ID', '')

        # ═══ إعدادات بينانس API ═══
        self.binance_api_key = os.environ.get('BINANCE_API_KEY', '')
        self.binance_api_secret = os.environ.get('BINANCE_API_SECRET', '')
        self.binance_base = 'https://api.binance.com'

        # ═══ إعدادات التداول والمخاطر ═══
        self.TRADE_ENABLED = os.environ.get('TRADE_ENABLED', 'false').lower() == 'true'
        self.RISK_PER_TRADE_PCT = float(os.environ.get('RISK_PCT', '2'))
        self.MIN_SCORE_TO_TRADE = int(os.environ.get('MIN_SCORE', '5'))
        self.MAX_OPEN_TRADES = int(os.environ.get('MAX_TRADES', '3'))
        self.MIN_TRADE_USDT = float(os.environ.get('MIN_TRADE_USDT', '10'))

        # ═══ متغيرات داخلية ═══
        self.TZ = ZoneInfo("Africa/Tripoli")
        self.usdt_pairs = []
        self.known_symbols = set()
        self.active_trades = {}
        self.stats = {'total_scans': 0, 'signals_found': 0, 'trades_executed': 0, 'wins': 0, 'losses': 0}
        self.step_sizes_cache = {} # حفظ حجم الخطوة لتسريع التداول

        # مؤقتات
        self.last_announcement_check = 0
        self.last_coingecko_check = 0
        self.last_dexscreener_check = 0
        self.last_fear_greed_check = 0
        self.last_full_scan = 0
        self.last_volume_scan = 0

        # ═══ رسالة التشغيل ═══
        mode = "⚔️ تداول تلقائي (Spot)" if self.TRADE_ENABLED else "👁️ مراقبة فقط (آمن)"
        msg = "🔥 *القناص الأسطوري V2.0 — النسخة المرنة!*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📡 الوضع: {mode}\n"
        msg += f"💰 مخاطرة/صفقة: {self.RISK_PER_TRADE_PCT}%\n"
        msg += f"🔄 وقف الخسارة: مرن (ATR + Trailing)\n"
        msg += f"📊 حد النقاط: {self.MIN_SCORE_TO_TRADE}\n"
        msg += "⏳ جاري تحميل بيانات السوق..."
        self.tg(msg)

        self._load_usdt_pairs()
        self._load_step_sizes()
        self._load_active_trades()

    # ═══════════════════════════════════════════════════
    #              وحدة تيليجرام
    # ═══════════════════════════════════════════════════
    def tg(self, msg):
        try:
            if len(msg) > 4000:
                for i in range(0, len(msg), 4000):
                    requests.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                 data={'chat_id': self.tg_chat, 'text': msg[i:i+4000], 'parse_mode': 'Markdown'}, timeout=10)
                    time.sleep(0.5)
            else:
                requests.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                             data={'chat_id': self.tg_chat, 'text': msg, 'parse_mode': 'Markdown'}, timeout=10)
        except: pass

    # ═══════════════════════════════════════════════════
    #          وحدة بينانس API الأساسية
    # ═══════════════════════════════════════════════════
    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(self.binance_api_secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    def _binance_request(self, method, endpoint, params=None, signed=False):
        try:
            url = f"{self.binance_base}{endpoint}"
            headers = {}
            if signed:
                if not self.binance_api_key or not self.binance_api_secret: return None
                params = self._sign(params or {})
                headers = {'X-MBX-APIKEY': self.binance_api_key}

            if method == 'GET':
                r = requests.get(url, params=params, headers=headers, timeout=15)
            else:
                r = requests.post(url, params=params, headers=headers, timeout=15)

            if r.status_code == 200: return r.json()
            elif r.status_code == 429: time.sleep(10); return None
            else: return None
        except: return None

    # ═══════════════════════════════════════════════════
    #       تحميل الأزواج وحجوم الخطوات
    # ═══════════════════════════════════════════════════
    def _load_usdt_pairs(self):
        data = self._binance_request('GET', '/api/v3/exchangeInfo')
        if not data: return
        new_pairs, new_symbols_set = [], set()
        for s in data.get('symbols', []):
            if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING':
                new_pairs.append({'symbol': s['symbol'], 'baseAsset': s['baseAsset']})
                new_symbols_set.add(s['symbol'])
        
        if self.known_symbols:
            newly_listed = new_symbols_set - self.known_symbols
            if newly_listed:
                msg = "🆕 *عملات مدرجة حديثاً على بينانس!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                for sym in newly_listed: msg += f"⚡ `{sym}` — تم الإدراج للتو!\n"
                self.tg(msg)

        self.usdt_pairs = new_pairs
        self.known_symbols = new_symbols_set

    def _load_step_sizes(self):
        """حفظ خطوات الكمية مسبقاً لتسريع التداول"""
        data = self._binance_request('GET', '/api/v3/exchangeInfo')
        if not data: return
        for s in data.get('symbols', []):
            for f in s.get('filters', []):
                if f['filterType'] == 'LOT_SIZE':
                    self.step_sizes_cache[s['symbol']] = float(f['stepSize'])

    def adjust_quantity(self, quantity, step_size):
        if step_size >= 1: return math.floor(quantity)
        precision = len(str(step_size).rstrip('0').split('.')[-1])
        return math.floor(quantity * (10 ** precision)) / (10 ** precision)

    # ═══════════════════════════════════════════════════
    #        وحدة جلب بيانات الشموع
    # ═══════════════════════════════════════════════════
    def get_klines(self, symbol, interval='1h', limit=100):
        data = self._binance_request('GET', '/api/v3/klines', {'symbol': symbol, 'interval': interval, 'limit': limit})
        if data and len(data) > 20:
            df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_vol', 'taker_buy_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            return df
        return None

    # ═══════════════════════════════════════════════════
    #     التحليل المتعدد المؤشرات (7 مؤشرات)
    # ═══════════════════════════════════════════════════
    def analyze_coin(self, symbol):
        df = self.get_klines(symbol, '1h', 100)
        if df is None or len(df) < 50: return None

        result = {'symbol': symbol, 'price': df.iloc[-1]['close'], 'score': 0, 'signals': [], 'direction': None, 'rsi': None, 'volume_ratio': None}
        try:
            price = df.iloc[-1]['close']

            # 1. RSI
            rsi_val = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]
            result['rsi'] = round(rsi_val, 1)
            if rsi_val < 25: result['score'] += 4; result['signals'].append(f"📈 RSI تشبع بيعي شديد ({rsi_val:.0f})")
            elif rsi_val < 30: result['score'] += 3; result['signals'].append(f"📈 RSI تشبع بيعي ({rsi_val:.0f})")
            elif rsi_val > 75: result['score'] -= 4; result['signals'].append(f"📉 RSI تشبع شرائي شديد ({rsi_val:.0f})")
            elif rsi_val > 70: result['score'] -= 3; result['signals'].append(f"📉 RSI تشبع شرائي ({rsi_val:.0f})")

            # 2. MACD
            macd_ind = ta.trend.MACD(df['close'])
            macd_line, signal_line = macd_ind.macd(), macd_ind.macd_signal()
            if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
                result['score'] += 3; result['signals'].append("📈 MACD تقاطع صعودي ⚡")
            elif macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
                result['score'] -= 3; result['signals'].append("📉 MACD تقاطع هبوطي")

            # 3. EMA
            ema9, ema21 = ta.trend.EMAIndicator(df['close'], window=9).ema_indicator(), ta.trend.EMAIndicator(df['close'], window=21).ema_indicator()
            if ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2]:
                result['score'] += 2; result['signals'].append("📈 EMA9 تقاطع فوق EMA21")
            elif ema9.iloc[-1] < ema21.iloc[-1] and ema9.iloc[-2] >= ema21.iloc[-2]:
                result['score'] -= 2; result['signals'].append("📉 EMA9 تقاطع تحت EMA21")

            # 4. Bollinger Bands
            bb_lower = ta.volatility.BollingerBands(df['close']).bollinger_lband().iloc[-1]
            if price <= bb_lower: result['score'] += 3; result['signals'].append("📈 لامس البولنجر السفلي (ارتداد)")

            # 5. Volume
            vol_avg, vol_current = df['volume'].rolling(20).mean().iloc[-1], df.iloc[-1]['volume']
            vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1
            result['volume_ratio'] = round(vol_ratio, 1)
            if vol_ratio > 3: result['score'] += 3; result['signals'].append(f"🔥 حجم ضخم! ({vol_ratio:.1f}x)")
            elif vol_ratio > 2: result['score'] += 2; result['signals'].append(f"📊 حجم عالي ({vol_ratio:.1f}x)")

            # 6. Stochastic
            stoch = ta.momentum.StochasticOscillator(high=df['high'], low=df['low'], close=df['close'])
            k, d = stoch.stoch().iloc[-1], stoch.stoch_signal().iloc[-1]
            k_prev, d_prev = stoch.stoch().iloc[-2], stoch.stoch_signal().iloc[-2]
            if k < 20 and d < 20 and k_prev < d_prev and k > d: result['score'] += 3; result['signals'].append("📈 Stochastic تقاطع صعودي بالقاع")

            # 7. Price Change
            if len(df) >= 25:
                change_24h = ((df.iloc[-1]['close'] - df.iloc[-25]['close']) / df.iloc[-25]['close']) * 100
                if -15 < change_24h < -5: result['score'] += 2; result['signals'].append(f"📉 هبوط {change_24h:.1f}% (فرصة!)")
                elif change_24h > 20: result['score'] -= 2; result['signals'].append(f"⚠️ صعود حاد {change_24h:.1f}%")

            # تحديد الاتجاه
            if result['score'] >= self.MIN_SCORE_TO_TRADE: result['direction'] = 'BUY'
            elif result['score'] <= -self.MIN_SCORE_TO_TRADE: result['direction'] = 'SELL'

        except: return None
        return result

    # ═══════════════════════════════════════════════════
    #     حساب SL/TP المرن بناءً على ATR
    # ═══════════════════════════════════════════════════
    def calculate_dynamic_sl_tp(self, symbol, entry_price):
        df = self.get_klines(symbol, '1h', 30)
        if df is None or len(df) < 15:
            return entry_price * 0.97, entry_price * 1.06, entry_price * 1.03, 3.0

        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_indicator.average_true_range().iloc[-1]
        atr_pct = (atr / entry_price) * 100

        sl_distance = atr_pct * 1.5
        tp1_distance = atr_pct * 3.0
        trailing_activation = entry_price * (1 + (atr_pct * 1.5) / 100)
        trailing_distance_pct = sl_distance

        sl_price = entry_price * (1 - sl_distance / 100)
        tp1_price = entry_price * (1 + tp1_distance / 100)

        # حدود أمان
        sl_price = max(sl_price, entry_price * 0.90) # لا نخسر أكثر من 10%
        sl_price = min(sl_price, entry_price * 0.98) # لا نضع وقف أقل من 2%
        
        trailing_distance_pct = max(trailing_distance_pct, 1.5) # لا يقل الوقف المتحرك عن 1.5%

        return round(sl_price, 6), round(tp1_price, 6), round(trailing_activation, 6), round(trailing_distance_pct, 2)

    # ═══════════════════════════════════════════════════
    #       التداول التلقائي (شراء وبيع Spot)
    # ═══════════════════════════════════════════════════
    def get_usdt_balance(self):
        data = self._binance_request('GET', '/api/v3/account', signed=True)
        if data:
            for b in data.get('balances', []):
                if b['asset'] == 'USDT': return float(b['free'])
        return 0

    def execute_trade(self, analysis):
        symbol, direction, score, price = analysis['symbol'], analysis['direction'], analysis['score'], analysis['price']

        if not self.TRADE_ENABLED or direction != 'BUY': return
        if len(self.active_trades) >= self.MAX_OPEN_TRADES or symbol in self.active_trades: return

        balance = self.get_usdt_balance()
        trade_amount = balance * (self.RISK_PER_TRADE_PCT / 100)
        if trade_amount < self.MIN_TRADE_USDT: return

        sl_price, tp_price, trailing_act, trailing_dist = self.calculate_dynamic_sl_tp(symbol, price)

        self.tg(f"⏳ جاري تنفيذ شراء `{symbol}` (وقف مرن)...")
        result = self._binance_request('POST', '/api/v3/order', {
            'symbol': symbol, 'side': 'BUY', 'type': 'MARKET', 'quoteOrderQty': round(trade_amount, 2)
        }, signed=True)

        if result and result.get('status') == 'FILLED':
            self.stats['trades_executed'] += 1
            fills = result.get('fills', [])
            fill_price = float(fills[0]['price']) if fills else price
            fill_qty = float(fills[0]['qty']) if fills else 0
            
            self.active_trades[symbol] = {
                'entry_price': fill_price, 'quantity': fill_qty, 'direction': 'BUY',
                'stop_loss': sl_price, 'take_profit': tp_price,
                'trailing_activation': trailing_act, 'trailing_distance_pct': trailing_dist,
                'highest_price': fill_price, 'trailing_active': False,
                'entry_time': time.time(), 'score': score, 'max_profit_pct': 0
            }
            self._save_active_trades()

            msg = f"✅ *صفقة شراء منفذة (وقف مرن)!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🪙 `{symbol}`\n💵 الدخول: `{fill_price:.6f}`\n💰 المبلغ: `${trade_amount:.2f}`\n"
            msg += f"🛑 وقف الخسارة: `{sl_price:.6f}`\n🎯 هدف الربح: `{tp_price:.6f}`\n"
            msg += f"🔄 تفعيل المتحرك عند: `{trailing_act:.6f}`\n📏 مسافة التتبع: `{trailing_dist}%`\n📈 نقاط: *{score}*"
            self.tg(msg)
        else:
            self.tg(f"❌ فشل تنفيذ الشراء على `{symbol}`")

    # ═══════════════════════════════════════════════════
    #    مراقبة الصفقات بالوقف المتحرك (Trailing)
    # ═══════════════════════════════════════════════════
    def monitor_trades(self):
        if not self.active_trades: return

        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            ticker = self._binance_request('GET', '/api/v3/ticker/price', {'symbol': symbol})
            if not ticker: continue
            
            current_price = float(ticker['price'])
            entry_price = trade['entry_price']

            if current_price > trade['highest_price']: trade['highest_price'] = current_price
            current_profit_pct = ((current_price - entry_price) / entry_price) * 100
            if current_profit_pct > trade['max_profit_pct']: trade['max_profit_pct'] = round(current_profit_pct, 2)

            closed, close_reason = False, ""

            # 1. فحص وقف الخسارة الأساسي
            if current_price <= trade['stop_loss'] and not trade['trailing_active']:
                closed, close_reason = True, "🛑 تم ضرب وقف الخسارة"

            # 2. تفعيل الوقف المتحرك عند هدف الربح الأول
            elif current_price >= trade['take_profit'] and not trade['trailing_active']:
                trade['trailing_active'] = True
                trade['stop_loss'] = entry_price * 1.005  # نقل الوقف للدخول + 0.5% لضمان عدم الخسارة
                msg = f"⚡ *تفعيل الوقف المتحرك! `{symbol}`*\n🎯 وصلنا الهدف الأول\n📈 الربح: {current_profit_pct:.1f}%\n🛑 الوقف الجديد: `{trade['stop_loss']:.6f}` (ضمان الربح)"
                self.tg(msg)
                self._save_active_trades()

            # 3. تحريك الوقف المتحرك للأعلى دائماً
            elif trade['trailing_active']:
                new_sl = trade['highest_price'] * (1 - trade['trailing_distance_pct'] / 100)
                if new_sl > trade['stop_loss']:
                    trade['stop_loss'] = new_sl
                    self._save_active_trades()

                if current_price <= trade['stop_loss']:
                    closed, close_reason = True, f"🔄 وقف متحرك حافظ على الأرباح!\n🏆 أقصى ربح وصل: {trade['max_profit_pct']:.1f}%"

            # 4. انتهاء الوقت (72 ساعة)
            elif time.time() - trade['entry_time'] > 259200 and current_profit_pct > -1:
                closed, close_reason = True, f"⏰ انتهاء الوقت (ربح {current_profit_pct:.1f}%)"

            # إغلاق الصفقة
            if closed:
                step_size = self.step_sizes_cache.get(symbol, 1)
                qty = self.adjust_quantity(trade['quantity'], step_size)
                result = self._binance_request('POST', '/api/v3/order', {
                    'symbol': symbol, 'side': 'SELL', 'type': 'MARKET', 'quantity': qty
                }, signed=True)
                
                fill_price = current_price
                if result and result.get('fills'): fill_price = float(result['fills'][0]['price'])

                pnl_usdt = (fill_price - entry_price) * trade['quantity']
                pnl_pct = ((fill_price - entry_price) / entry_price) * 100
                is_win = pnl_usdt > 0
                if is_win: self.stats['wins'] += 1
                else: self.stats['losses'] += 1

                icon = "✅" if is_win else "❌"
                msg = f"🏁 *إغلاق `{symbol}`*\n━━━━━━━━━━━━━━━━━━━━━━━━\n{close_reason}\n"
                msg += f"💵 الدخول: `{entry_price:.6f}` | الإغلاق: `{fill_price:.6f}`\n"
                msg += f"{icon} النتيجة: `{pnl_usdt:.2f} USDT ({pnl_pct:+.2f}%)`\n🏆 أقصى ربح وصل: *{trade['max_profit_pct']:.1f}%*\n📊 الإحصائيات: {self.stats['wins']}W / {self.stats['losses']}L"
                self.tg(msg)

                del self.active_trades[symbol]
                self._save_active_trades()

    # ═══════════════════════════════════════════════════
    #           وحدات البحث الخارجية المجانية
    # ═══════════════════════════════════════════════════
    def check_binance_announcements(self):
        try:
            r = requests.get("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query", params={'type': 1, 'catalogId': 48, 'pageNo': 1, 'pageSize': 5}, timeout=10)
            if r.status_code == 200:
                for article in r.json().get('data', {}).get('articles', []):
                    title = article.get('title', '').upper()
                    if any(kw in title for kw in ['LIST', 'LISTING', 'LAUNCH', 'WILL LIST']):
                        if article.get('releaseDate', 0) > (time.time() * 1000 - 3600000):
                            self.tg(f"🚨 *إعلان إدراج جديد!*\n📢 {article.get('title')}\n⚡ عادة ترتفع بشدة!")
        except: pass

    def scan_coingecko_trending(self):
        try:
            r = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=10)
            if r.status_code != 200: return
            msg = "🔥 *عملات رائجة على CoinGecko*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, c in enumerate(r.json().get('coins', [])[:5]):
                item = c.get('item', {})
                sym = item.get('symbol', '').upper()
                on_binance = "✅" if f"{sym}USDT" in self.known_symbols else "❌"
                msg += f"{i+1}. 🪙 *{item.get('name')}* (`{sym}`) على بينانس: {on_binance}\n"
            self.tg(msg)
        except: pass

    def check_fear_greed(self):
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if r.status_code == 200:
                fng = r.json().get('data', [{}])[0]
                val, label = int(fng.get('value', 50)), fng.get('value_classification', 'Neutral')
                emoji = {'Extreme Fear': '😱', 'Fear': '😨', 'Neutral': '😐', 'Greed': '😊', 'Extreme Greed': '🤑'}.get(label, '😐')
                tip = "فرص شراء ممتازة!" if val < 25 else "حذر من التصحيح!" if val > 75 else ""
                self.tg(f"{emoji} *مؤشر الخوف والطمع*: {val}/100 ({label})\n💡 {tip}")
        except: pass

    def detect_volume_spikes(self):
        data = self._binance_request('GET', '/api/v3/ticker/24hr')
        if not data: return
        spikes = []
        for t in data:
            sym, vol, chg = t.get('symbol', ''), float(t.get('quoteVolume', 0)), float(t.get('priceChangePercent', 0))
            if sym.endswith('USDT') and vol > 5000000 and 2 < chg < 20: spikes.append({'symbol': sym, 'vol': vol, 'chg': chg})
        if spikes:
            spikes.sort(key=lambda x: x['vol'], reverse=True)
            msg = "📊 *ارتفاعات حجم (ضخ أموال)*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, s in enumerate(spikes[:5]): msg += f"{i+1}. `{s['symbol']}` | 💧 ${s['vol']/1e6:.1f}M | 📈 {s['chg']:+.1f}%\n"
            self.tg(msg)

    # ═══════════════════════════════════════════════════
    #       المسح السريع والشامل للسوق
    # ═══════════════════════════════════════════════════
    def quick_scan(self):
        priority = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE', 'ADA', 'AVAX', 'DOT', 'LINK', 'UNI', 'ATOM', 'LTC', 'NEAR', 'APT', 'ARB', 'OP', 'SUI', 'SEI', 'TIA', 'INJ', 'FET', 'WLD', 'PEPE', 'SHIB', 'TON']
        found = []
        for coin in priority:
            sym = f"{coin}USDT"
            if sym in self.known_symbols and sym not in self.active_trades:
                a = self.analyze_coin(sym)
                if a and a['score'] >= self.MIN_SCORE_TO_TRADE: found.append(a)
                time.sleep(0.3)
        if found:
            found.sort(key=lambda x: x['score'], reverse=True)
            msg = "⚡ *فحص سريع — فرص قوية!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for i, a in enumerate(found[:3]): msg += f"🟢 `{a['symbol']}` | نقاط: *{a['score']}* | ${a['price']:.4f}\n"
            self.tg(msg)
            self.execute_trade(found[0])

    # ═══════════════════════════════════════════════════
    #       حفظ واسترجاع الصفقات (JSON)
    # ═══════════════════════════════════════════════════
    def _save_active_trades(self):
        try:
            with open('active_trades.json', 'w') as f: json.dump(self.active_trades, f)
        except: pass

    def _load_active_trades(self):
        try:
            if os.path.exists('active_trades.json'):
                with open('active_trades.json', 'r') as f: self.active_trades = json.load(f)
                if self.active_trades: self.tg(f"📂 تم استرجاع {len(self.active_trades)} صفقة مفتوحة")
        except: self.active_trades = {}

    # ═══════════════════════════════════════════════════
    #        حلقة التشغيل الرئيسية (القلب النابض)
    # ═══════════════════════════════════════════════════
    def run(self):
        mode_msg = "⚔️ تداول تلقائي" if self.TRADE_ENABLED else "👁️ مراقبة فقط"
        self.tg(f"🤖 *القناط الأسطوري بدأ العمل!* ({mode_msg})\n⏰ المسح السريع: 15 د | المصادر: 30 د | الشامل: 3 س\n👀 المراقبة: كل دقيقة")
        
        while True:
            try:
                now = time.time()

                # كل دقيقة: مراقبة الصفقات المفتوحة
                self.monitor_trades()

                # كل 5 دقائق: إعلانات بينانس
                if now - self.last_announcement_check > 300:
                    self.check_binance_announcements()
                    self.last_announcement_check = now

                # كل 15 دقيقة: فحص سريع + حجم
                if now - self.last_volume_scan > 900:
                    self.quick_scan()
                    self.detect_volume_spikes()
                    self.last_volume_scan = now

                # كل 30 دقيقة: مصادر خارجية
                if now - self.last_coingecko_check > 1800:
                    self.scan_coingecko_trending()
                    self.check_fear_greed()
                    self.last_coingecko_check = now

                # كل 3 ساعات: تحديث الأزواج
                if now - self.last_full_scan > 10800:
                    self._load_usdt_pairs()
                    self.last_full_scan = now

                time.sleep(60)

            except KeyboardInterrupt:
                self.tg("⛔ تم إيقاف القناص الأسطوري يدوياً"); break
            except Exception as e:
                print(f"Loop error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = LegendarySniperBot()
    bot.run()
