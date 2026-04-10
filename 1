import ccxt
import time
import pandas as pd
import ta # Technical Analysis library
import requests
import datetime # لاستخدام التواريخ والأوقات للتقارير

# ==========================================
# ⚙️ الفئة المساعدة لتتبع الأداء (Performance Tracker)
# ==========================================
class PerformanceTracker:
    def __init__(self, telegram_token, chat_id, exchange_client):
        self.trades_log = []
        self.TELEGRAM_TOKEN = telegram_token
        self.CHAT_ID = chat_id
        self.exchange = exchange_client # للوصول إلى دقة الكميات والمعلومات الأساسية
        self.send_telegram = lambda msg: self._send_telegram(msg) # ربط مباشر

    def _send_telegram(self, message):
        """يرسل رسالة إلى تلجرام."""
        try:
            url = f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={'chat_id': self.CHAT_ID, 'text': message, 'parse_mode': 'Markdown'})
        except Exception as e:
            print(f"❌ خطأ في إرسال التلجرام (Tracker): {e}")

    def log_trade(self, symbol, entry_price, exit_price, quantity, is_profit, profit_pct, reason):
        """يسجل تفاصيل الصفقة."""
        # الحصول على دقة الكمية قبل التسجيل
        formatted_quantity = self.exchange.amount_to_precision(symbol, quantity)
        
        self.trades_log.append({
            'timestamp': datetime.datetime.now(),
            'symbol': symbol,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': float(formatted_quantity), # تسجيل الكمية المصقولة
            'is_profit': is_profit,
            'profit_pct': profit_pct,
            'reason': reason
        })
        print(f"Trade Logged: {symbol} | Profit: {profit_pct:.2f}% | Reason: {reason}")

    def get_stats(self):
        """يحسب الإحصائيات من سجل الصفقات."""
        if not self.trades_log:
            return {
                "total_trades": 0, "win_rate": 0, "total_profit_sum_pct": 0,
                "avg_profit_pct_wins": 0, "avg_loss_pct_losses": 0, "best_trade_pct": 0,
                "worst_trade_pct": 0
            }

        total_trades = len(self.trades_log)
        winning_trades = [t for t in self.trades_log if t['is_profit']]
        losing_trades = [t for t in self.trades_log if not t['is_profit']]

        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        
        all_profit_pct = [t['profit_pct'] for t in self.trades_log]
        total_profit_sum_pct = sum(all_profit_pct) # مجموع النسب المئوية

        avg_profit_pct_wins = sum([t['profit_pct'] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
        avg_loss_pct_losses = sum([t['profit_pct'] for t in losing_trades]) / len(losing_trades) if losing_trades else 0

        best_trade_pct = max(all_profit_pct) if all_profit_pct else 0
        worst_trade_pct = min(all_profit_pct) if all_profit_pct else 0

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_profit_sum_pct": total_profit_sum_pct,
            "avg_profit_pct_wins": avg_profit_pct_wins,
            "avg_loss_pct_losses": avg_loss_pct_losses,
            "best_trade_pct": best_trade_pct,
            "worst_trade_pct": worst_trade_pct
        }

    def _generate_daily_report(self):
        """ينشئ نص التقرير اليومي."""
        stats = self.get_stats()
        report = f"📊 *تقرير أداء البوت اليومي*\n\n"
        report += f"📅 التاريخ: {datetime.date.today().strftime('%Y-%m-%d')}\n"
        report += f"🚀 إجمالي الصفقات: {stats['total_trades']}\n"
        report += f"🏆 نسبة الفوز (Win Rate): {stats['win_rate']:.2f}%\n"
        report += f"📈 إجمالي الربح (Sum %): {stats['total_profit_sum_pct']:.2f}%\n"
        report += f"💰 متوسط ربح الصفقة الرابحة: {stats['avg_profit_pct_wins']:.2f}%\n"
        report += f"💸 متوسط خسارة الصفقة الخاسرة: {stats['avg_loss_pct_losses']:.2f}%\n"
        report += f"🌟 أفضل صفقة: {stats['best_trade_pct']:.2f}%\n"
        report += f"❌ أسوأ صفقة: {stats['worst_trade_pct']:.2f}%\n\n"
        
        # عرض تفاصيل أفضل وأسوأ صفقات (بناءً على الربح/الخسارة)
        if self.trades_log:
            best_strat_trade = max(self.trades_log, key=lambda t: t['profit_pct'])
            worst_strat_trade = min(self.trades_log, key=lambda t: t['profit_pct'])
            report += f"✨ **أفضل صفقة:** {best_strat_trade['symbol']} ({best_strat_trade['profit_pct']:.2f}%) - السبب: {best_strat_trade['reason']}\n"
            report += f"⚠️ **أسوأ صفقة:** {worst_strat_trade['symbol']} ({worst_strat_trade['profit_pct']:.2f}%) - السبب: {worst_strat_trade['reason']}\n"

        return report
        
    def send_daily_report(self):
        """يرسل التقرير اليومي عبر تلجرام."""
        report = self._generate_daily_report()
        self.send_telegram(report)
        # إعادة تعيين سجل الصفقات الصفقات لليوم الحالي فقط (للاحتفاظ بسجل يومي)
        self.trades_log = [t for t in self.trades_log if t['timestamp'].date() == datetime.date.today()]

# ==========================================
# 🤖 البوت الرئيسي LegendaryBot
# ==========================================
class LegendaryBot:
    def __init__(self):
        # ==========================================
        # ⚙️ الإعدادات والمفاتيح
        # ==========================================
        self.API_KEY = 'egAeFM8kVEn7YRKPIHRpJGpDW4GFuHRDHFnRmRqdEWcZxPRAb0qHbvd6T6X3MC94Ffqfgc4BSv9mxbBPXSQ'
        self.API_SECRET = 'OC7UgGik9WOSjUI6r4AvbqfZIq9O9BrjzC2LRrott95Ewcu2jQHRnjCNQj8sn9ZdKIsAf9ioAkp89xs1e7g'
        
        self.TELEGRAM_TOKEN = '8744586010:AAET91PN6ApW3FiX4WU1nSH_F5xoHuzIQKk'
        self.CHAT_ID = '7520475220'
        
        # إعدادات إدارة المخاطر
        self.RISK_PER_TRADE_PCT = 1.5           # 1.5% من رأس المال لكل صفقة (تم زيادتها قليلاً)
        self.STOP_LOSS_ATR_MULTIPLIER = 2.5     # مضاعف ATR لوقف الخسارة (تم زيادته ليكون أكثر أماناً)
        self.MAX_CONSECUTIVE_LOSSES = 3         # الحد الأقصى للخسائر المتتالية قبل تقليل حجم الصفقة
        self.LOSS_SIZE_REDUCTION_FACTOR = 0.5   # تقليل حجم الصفقة إلى 50% بعد الخسائر المتتالية
        self.DAILY_LOSS_LIMIT_PCT = 3.0         # 3% من رأس المال كحد خسارة يومي

        # إعدادات الدخول والخروج
        self.ENTRY_CONFIRMATION_TimEframe = '15m' # الفريم للدخول
        self.DIRECTION_CONFIRMATION_TimEframe = '1h' # الفريم لتأكيد الاتجاه

        self.INITIAL_TRADE_AMOUNT_USD = 100     # قيمة أولية تقريبية للدخول (سيتم حساب الكمية بدقة لاحقاً)
        self.STOP_LOSS_PCT = -2.5               # وقف الخسارة الصارم (backup, ليس الأساسي)
        self.TAKE_PROFIT_PCT = 5.0              # الهدف الأساسي
        self.TRAILING_ACTIVATE_PCT = 2.5        # تفعيل ملاحقة الأرباح بعد 2.5% ربح (تم زيادته قليلاً)
        self.TRAILING_DROP_PCT = 0.5            # نسبة تراجع السعر المسموح بها في التريلينغ ستوب (من القمة)

        # إعدادات الاستقرار
        self.MAX_RETRIES = 7 # زيادة الحد الأقصى للمحاولات
        self.RETRY_DELAY = 7 # زيادة مدة الانتظار بين المحاولات

        # إعدادات اختيار العملات
        self.MIN_VOLUME_24H = 5000000 # الحد الأدنى لحجم التداول اليومي (5 مليون دولار)
        self.MIN_PRICE_CHANGE_PCT_DAY = 1.5 # الحد الأدنى للتغير في السعر بالنسبة المئوية خلال 24 ساعة

        # تهيئة المكونات
        self.exchange = ccxt.bingx({
            'apiKey': self.API_KEY,
            'secret': self.API_SECRET,
            'enableRateLimit': True, # مهم جداً للامتثال لحدود الطلبات API
            'options': {'defaultType': 'spot'},
            'rateLimit': 2000 # ضبط معالج RiotLimit ليكون ألطف (2000ms = 2s)
        })
        
        self.active_trade = None # لتخزين معلومات الصفقة الحالية
        self.consecutive_losses = 0 # عداد الخسائر المتتالية
        self.daily_loss = 0.0       # مقدار الخسارة اليومية
        self.last_trade_date = None # لتتبع تاريخ آخر يوم تم فيه التداول
        self.last_report_time = datetime.datetime.now() # لتتبع وقت آخر تقرير أرسل
        
        # تهيئة متتبع الأداء مع تمرير عميل الصرف
        self.performance_tracker = PerformanceTracker(self.TELEGRAM_TOKEN, self.CHAT_ID, self.exchange)

        self.send_telegram("✨ *نظام Sniper Pro Pro Legend بدأ العمل بالتحسينات الاحترافية!*")
        self._load_markets() # تحميل الأسواق

    def _send_telegram(self, message):
        """وظيفة مساعدة لإرسال رسائل تلجرام."""
        self.performance_tracker._send_telegram(message)

    def _load_markets(self):
        """تحميل معلومات الأسواق من المنصة."""
        try:
            self.exchange.load_markets()
            print("✅ تم تحميل معلومات الأسواق بنجاح.")
        except Exception as e:
            error_msg = f"🚨 *خطأ فادح:* فشل تحميل أسواق المنصة: {e}. سيتم إعادة المحاولة..."
            self._send_telegram(error_msg)
            print(error_msg)
            # إعادة المحاولة لضمان استمرار التشغيل
            time.sleep(10)
            self._load_markets()

    # ==========================================
    # 🔄 دوال مساعدة للتعامل مع ccxt مع إعادة المحاولة
    # ==========================================
    def _fetch_with_retry(self, method, *args, **kwargs):
        """يحاول استدعاء دالة من ccxt مع إعادة المحاولة عند الفشل."""
        for i in range(self.MAX_RETRIES):
            try:
                # استخدام getattr لاستدعاء الدالة المطلوبة
                result = getattr(self.exchange, method)(*args, **kwargs)
                # قد تعيد بعض الدوال (مثل fetch_ticker) None عند الفشل أو عدم وجود بيانات
                if result is None and method not in ['fetch_trades', 'fetch_orders']: # تجاهل None إذا كان متوقعاً
                    if i == self.MAX_RETRIES - 1:
                        self._send_telegram(f"🚨 *فشل متكرر في استدعاء {method} (No Data Received): {args}")
                    if i > 0: # لتجنب الطباعة المتكررة في أول محاولة
                        print(f"⚠️ {method} ({args}): No data received. Retrying ({i+1}/{self.MAX_RETRIES})...")
                    time.sleep(self.RETRY_DELAY * (i + 1))
                    continue # جرب المحاولة التالية
                return result # إرجاع النتيجة إذا كانت ناجحة
                
            except (ccxt.NetworkError, ccxt.ExchangeError, ccxt.RequestTimeout, ccxt.BadSymbol) as e:
                error_msg = f"⚠️ فشل استدعاء {method} ({args}): {e}. المحاولة {i+1}/{self.MAX_RETRIES}..."
                print(error_msg)
                if i == self.MAX_RETRIES - 1:
                    self._send_telegram(f"🚨 *فشل متكرر في استدعاء {method}.*")
                time.sleep(self.RETRY_DELAY * (i + 1))
            except Exception as e: # لأي أخطاء غير متوقعة
                error_msg = f"❌ خطأ غير متوقع في {method} ({args}): {e}. المحاولة {i+1}/{self.MAX_RETRIES}..."
                print(error_msg)
                if i == self.MAX_RETRIES - 1:
                    self._send_telegram(f"🚨 *خطأ فادح غير متوقع في {method}.*")
                time.sleep(self.RETRY_DELAY * (i + 1))
        return None # إرجاع None بعد فشل جميع المحاولات

    def _fetch_ohlcv(self, symbol, timeframe, limit):
        """جلب OHLCV مع إعادة المحاولة."""
        return self._fetch_with_retry('fetch_ohlcv', symbol, timeframe, limit=limit)

    def _fetch_ticker(self, symbol):
        """جلب معلومات التداول (ticker) مع إعادة المحاولة."""
        return self._fetch_with_retry('fetch_ticker', symbol)

    def _create_order(self, order_type, symbol, qty, price=None, params={}):
        """إنشاء أمر مع إعادة المحاولة."""
        method = f'create_market_{order_type}_order' if price is None else f'create_limit_{order_type}_order'
        args = [symbol, qty]
        if price is not None:
            args.append(price)
        
        order = self._fetch_with_retry(method, *args, params=params)
        if order and order.get('id'): # التأكد من أن الأمر تم بنجاح (عاد بمعرف)
            print(f"✅ تم تنفيذ الأمر {order_type} لـ {symbol}: ID {order.get('id')}")
            return order
        else:
            self._send_telegram(f"⚠️ *فشل تنفيذ الأمر {order_type} لـ {symbol} بعد عدة محاولات.*")
            return None
            
    def _fetch_balance(self):
        """جلب الرصيد مع إعادة المحاولة."""
        return self._fetch_with_retry('fetch_balance')
        
    def _fetch_tickers(self):
        """جلب جميع معلومات الأصول (tickers) مع إعادة المحاولة."""
        return self._fetch_with_retry('fetch_tickers')

    # ==========================================
    # 🧠 التحليل الفني (مع فلترة الحالة/الفريمات)
    # ==========================================
    def _get_market_regime(self, symbol, timeframe='1h'):
        """يحدد حالة السوق (ترند صاعد، تذبذب، إلخ)."""
        bars = self._fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        if not bars: 
            print(f"Warning: No OHLCV data for {symbol} on {timeframe} in _get_market_regime.")
            return "neutral"
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        df['ema100'] = ta.trend.ema_indicator(df['c'], window=100)
        df['ema200'] = ta.trend.ema_indicator(df['c'], window=200)
        
        bb = ta.volatility.BollingerBands(df['c'], window=20, window_dev=2)
        df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['c'] * 100

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        is_uptrend = last['c'] > last['ema100'] and last['ema100'] > last['ema200'] and last['ema100'] > prev['ema100']
        # تعديل شرط التذبذب ليكون أكثر حساسية
        is_sideways = (last['bb_width'] < 5) and (abs(last['c'] - last['ema100']) < (last['c'] * 0.01)) # مثال
        is_high_risk = last['bb_width'] > 10 # مثال

        if is_uptrend: return "uptrend"
        elif is_sideways: return "sideways"
        elif is_high_risk: return "high_risk"
        else: return "neutral"

    def _analyze_market(self, symbol, timeframe):
        """تحليل السوق على فريم معين مع إرجاع إشارة الدخول."""
        bars = self._fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
        if not bars: 
            print(f"Warning: No OHLCV data for {symbol} on {timeframe} in _analyze_market.")
            return False, 0, 0
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        # المؤشرات العامّة
        df['ema200'] = ta.trend.ema_indicator(df['c'], window=200)
        df['rsi'] = ta.momentum.rsi(df['c'], window=14)
        df['macd'] = ta.trend.macd_diff(df['c'])
        bb = ta.volatility.BollingerBands(df['c'], window=20, window_dev=2)
        df['bb_lower'] = bb.bollinger_lband()
        df['vol_ma'] = df['v'].rolling(20).mean()
        df['atr'] = ta.volatility.AverageTrueRange(df['h'], df['l'], df['c'], window=14).average_true_range()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        entry_signal = False
        
        # ---- شروط الدخول (مثال لفريم 15m) ----
        if timeframe == self.ENTRY_CONFIRMATION_TimEframe:
            # 1. فلتر الحركة المنخفضة (Low Movement Filter)
            if last['atr'] is not None and (last['h'] - last['l']) < (last['atr'] * 0.5):
                 print(f"Info: Low movement on {symbol} ({timeframe}). Skipping entry.")
                 return False, 0, 0

            # 2. تأكيد الحجم (Volume Spike)
            volume_spike = last['v'] > (last['vol_ma'] * 1.5) # استخدام 1.5 بدلاً من 1.5 ليتوافق مع الكود الأصلي
            
            # 3. تأكيد حركة السعر (Price Action Confirmation)
            #   - رفض الدخول في الشموع الضعيفة: مثال، شمعة تدل على ضعف الزخم
            #   - مثال: الشمعة السابقة كانت هابطة، والشمعه الحالية إيجابية لكن حجمها صغير
            price_action_confirmation = True
            # شمعة ضعيفة: طول جسمها أقل من نص ATR (إذا كان ATR متاحاً)
            if last['atr'] is not None and (last['h'] - last['l']) < (last['atr'] * 0.5): 
                price_action_confirmation = False
                
            # شروط الدخول الأساسية
            trend_up_short = last['c'] > last['ema200']
            # تعديل Oversold Bounce ليكون أكثر دقة
            oversold_bounce = (prev['c'] < prev['bb_lower']) and (last['c'] > last['bb_lower']) # السعر يرتد فوق الـ BB Lower
            rsi_good = 35 < last['rsi'] < 55
            macd_cross = last['macd'] > prev['macd']
            
            # الشرط المدمج:
            if (trend_up_short and 
                oversold_bounce and 
                rsi_good and 
                macd_cross and 
                volume_spike and 
                price_action_confirmation):
                
                entry_signal = True
        
        return entry_signal, last['c'], last['rsi']

    # ==========================================
    # 💰 إدارة المخاطر (Risk Engine)
    # ==========================================
    def _calculate_atr(self, symbol, timeframe='15m', period=14):
        """يحسب ATR للسعر."""
        bars = self._fetch_ohlcv(symbol, timeframe=timeframe, limit=period + 5)
        if not bars or len(bars) < period: 
            print(f"Warning: Not enough data to calculate ATR for {symbol}. Required: {period}, Available: {len(bars) if bars else 0}")
            return None
        df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
        
        atr_indicator = ta.volatility.AverageTrueRange(high=df['h'], low=df['l'], close=df['c'], window=period)
        atr_value = atr_indicator.average_true_range().iloc[-1]
        # التحقق من أن ATR قيمة موجبة وليست NaN
        if pd.isna(atr_value) or atr_value <= 0:
            print(f"Warning: Calculated ATR is invalid ({atr_value}) for {symbol}.")
            return None
        return atr_value

    def _get_free_balance(self, currency='USDT'):
        """يحصل على الرصيد الحر بعملة معينة."""
        balance = self._fetch_balance()
        if balance and currency in balance:
            return float(balance[currency].get('free', 0))
        print(f"Warning: Could not fetch free balance for {currency}.")
        return 0.0

    def _calculate_order_qty(self, symbol, entry_price):
        """يحسب كمية الشراء بناءً على إدارة المخاطر."""
        total_balance = self._get_free_balance()
        if total_balance == 0:
            self._send_telegram("⚠️ *رصيد USDT غير كافٍ أو لا يمكن الوصول إليه.*")
            return 0

        atr_value = self._calculate_atr(symbol, timeframe=self.ENTRY_CONFIRMATION_TimEframe)
        if atr_value is None:
            self._send_telegram(f"⚠️ *تعذر حساب ATR لـ {symbol}، تخطي الصفقة.*")
            return 0

        # تحديد حجم المخاطرة لهذه الصفقة
        current_risk_per_trade = self.RISK_PER_TRADE_PCT
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            current_risk_per_trade *= self.LOSS_SIZE_REDUCTION_FACTOR
            self._send_telegram(f"📉 *تقليل حجم الصفقة لـ {symbol} بسبب خسائر متتالية.*")

        risk_amount_usd = total_balance * (current_risk_per_trade / 100)
        
        # تحديد وقف الخسارة الديناميكي
        stop_loss_distance_usd = self.STOP_LOSS_ATR_MULTIPLIER * atr_value
        stop_loss_price = entry_price - stop_loss_distance_usd
        
        # التأكد من أن وقف الخسارة ليس صفراً أو سالباً وأن مسافة وقف الخسارة منطقية
        if stop_loss_price <= 0 or stop_loss_distance_usd <= 0:
            self._send_telegram(f"⚠️ *سعر أو مسافة وقف الخسارة غير صالحة لـ {symbol} (SL Price: {stop_loss_price:.4f}, Distance: {stop_loss_distance_usd:.4f}). تخطي الصفقة.*")
            return 0
            
        qty_to_buy = risk_amount_usd / stop_loss_distance_usd
        
        # الحصول على دقة الكمية من المنصة
        try:
            market_info = self.exchange.market(symbol)
            # كمية مصقولة (rounded)
            formatted_qty = self.exchange.amount_to_precision(symbol, qty_to_buy)
            # التحقق من الحد الأدنى للكمية
            min_qty = market_info.get('limits', {}).get('amount', {}).get('min')
            if min_qty and float(formatted_qty) < min_qty:
                print(f"Warning: Calculated quantity {formatted_qty} is below minimum ({min_qty}) for {symbol}. Adjusting quantity.")
                formatted_qty = self.exchange.amount_to_precision(symbol, min_qty)

        except Exception as e:
            print(f"Error getting market precision for {symbol}: {e}. Using default formatting.")
            formatted_qty = self.exchange.amount_to_precision(symbol, qty_to_buy)

        if float(formatted_qty) <= 0:
            self._send_telegram(f"⚠️ *الكمية المحسوبة صفراً أو سالبة لـ {symbol} ({formatted_qty}). تخطي الصفقة.*")
            return 0
            
        return float(formatted_qty)

    # ==========================================
    # 💰 التنفيذ والإغلاق الذكي
    # ==========================================
    def _close_trade(self, reason, profit_pct, is_loss=False):
        """يغلق الصفقة الحالية ويرسل تقريراً."""
        if not self.active_trade: return False

        symbol = self.active_trade['symbol']
        
        # الحصول على الكمية الفعلية الموجودة في المحفظة
        coin = symbol.split('/')[0]
        balance = self._fetch_balance()
        if not balance or coin not in balance or balance[coin].get('free', 0) <= 0:
            self._send_telegram(f"⚠️ *لا يمكن العثور على رصيد حر لـ {coin} لإنهاء صفقة {symbol}.)*")
            # قد يكون هناك خطأ، لذا نعيد تعيين الحالة لتجنب مشاكل لاحقة
            self.active_trade = None 
            return False
        
        qty_to_sell = balance[coin]['free']
        formatted_qty = float(self.exchange.amount_to_precision(symbol, qty_to_sell))

        if formatted_qty <= 0:
            self._send_telegram(f"⚠️ *كمية البيع 0 أو أقل لـ {symbol}. لا يمكن إغلاق الصفقة.*")
            self.active_trade = None # إعادة تعيين إذا كان هناك مشكلة في الكمية
            return False

        # جلب السعر الحالي عند الإغلاق
        ticker = self._fetch_ticker(symbol)
        if not ticker:
            self._send_telegram(f"⚠️ *فشل جلب سعر {symbol} عند محاولة الإغلاق (استخدام سعر الدخول كتقدير).*)")
            # استخدام سعر الدخول كتقدير إذا فشل جلب السعر الفعلي
            exit_price = self.active_trade['entry']
        else:
            exit_price = ticker['last']

        # تنفيذ أمر البيع
        sell_order = self._create_order('sell', symbol, formatted_qty)
        if not sell_order:
            self._send_telegram(f"🚨 *فشل تنفيذ أمر البيع لـ {symbol}، قد تحتاج إلى إغلاق يدوي.*")
            return False

        # تسجيل الصفقة في متتبع الأداء
        self.performance_tracker.log_trade(
            symbol=symbol,
            entry_price=self.active_trade['entry'],
            exit_price=exit_price,
            quantity=formatted_qty,
            is_profit=(profit_pct > 0),
            profit_pct=profit_pct,
            reason=reason
        )
        
        # تحديث حالة الخسائر
        if is_loss:
            self.consecutive_losses += 1
            # حساب الخسارة اليومية كنسبة مئوية من الرصيد الكلي
            total_balance = self._get_free_balance()
            if total_balance > 0:
                self.daily_loss += (abs(profit_pct) / 100) * (self._get_free_balance() / total_balance * 100) # نسبة الخسارة بالنسبة للرصيد الحالي
            else:
                self.daily_loss += abs(profit_pct) #fallback
                
            self._send_telegram(f"📉 الخسائر المتتالية: {self.consecutive_losses}/{self.MAX_CONSECUTIVE_LOSSES}. إجمالي الخسارة اليومية: {self.daily_loss:.2f}%")
        else:
            self.consecutive_losses = 0 # إعادة تعيين عند الربح
            
        # إرسال تقرير إغلاق الصفقة
        msg = f"✅ *تم إغلاق الصفقة بنجاح*\n"
        msg += f"🪙 العملة: {symbol}\n"
        msg += f"🎯 السبب: {reason}\n"
        msg += f"💰 النتيجة: {profit_pct:.2f}%\n"
        msg += f"💵 الكمية المباعة: {formatted_qty:.6f} | سعر الخروج الفعلي: {exit_price:.4f}\n"
        msg += f"💸 سعر الدخول: {self.active_trade['entry']:.4f}"
        self._send_telegram(msg)
        print(msg)
        
        # إعادة تعيين حالة التداول
        self.active_trade = None
        # self.highest_profit = 0.0 # لا نريد إعادة تعيين أعلى ربح هنا، لتتبع المسار
        
        return True

    # ==========================================
    # 🔄 المحرك الرئيسي للتداول
    # ==========================================
    def run(self):
        """الدالة الرئيسية التي تدير دورة التداول."""
        self._send_telegram("🚀 *نظام Sniper Pro Pro Legend بدأ العمل!*")
        
        while True:
            current_date_today = datetime.date.today()
            # إعادة تعيين الخسارة اليومية إذا بدأ يوم جديد
            if self.last_trade_date != current_date_today:
                self.daily_loss = 0.0
                self.last_trade_date = current_date_today
                self._send_telegram(f"🗓️ *بدأ يوم تداول جديد. تم إعادة تعيين الخسارة اليومية.*")

            try:
                # --- التحقق من حد الخسارة اليومي قبل أي تداول ---
                if self.daily_loss >= self.DAILY_LOSS_LIMIT_PCT:
                    print(f"Daily loss limit ({self.DAILY_LOSS_LIMIT_PCT}%) reached. Stopping trading for today.")
                    self._send_telegram(f"🛑 **تم الوصول إلى حد الخسارة اليومي. إيقاف التداول لهذا اليوم.**")
                    time.sleep(3600) # إيقاف لمدة ساعة أو حتى إعادة تعيين اليوم
                    continue

                if not self.active_trade:
                    # ---- البحث عن صفقة جديدة ----
                    tickers_data = self._fetch_tickers()
                    if not tickers_data:
                        print("❌ فشل جلب قائمة الأصول (tickers). الانتظار والمحاولة مجدداً.")
                        self._send_telegram("⚠️ *فشل جلب قائمة الأصول. الانتظار والمحاولة مجدداً.*")
                        time.sleep(30)
                        continue
                        
                    # --- فلترة العملات بناءً على السيولة والحركة ---
                    filtered_symbols = []
                    for symbol, ticker_info in tickers_data.items():
                        # التأكد من أنها عملة USDT وأن لها بيانات سعر وتداول
                        if (symbol.endswith('/USDT') and 
                            ':' not in symbol and 
                            ticker_info and 
                            ticker_info.get('baseVolume') and # حجم التداول بالعملة الأساسية
                            ticker_info.get('quoteVolume') and # حجم التداول بالعملة المقتبسة (USDT)
                            ticker_info.get('last')):
                            
                            volume_24h = ticker_info.get('quoteVolume', 0) * ticker_info.get('last', 0) # تقدير حجم 24h
                            price_change_pct_day = ticker_info.get('change', 0) # تغير السعر خلال اليوم
                            
                            if (volume_24h > self.MIN_VOLUME_24H and 
                                abs(price_change_pct_day) > self.MIN_PRICE_CHANGE_PCT_DAY):
                                filtered_symbols.append(symbol)

                    # اختيار أفضل 30 عملة للتحليل (ممكن تخصيص هذا)
                    symbols_to_analyze = filtered_symbols[:30]
                    if not symbols_to_analyze:
                        print("No suitable symbols found based on liquidity and volatility filters. Waiting...")
                        time.sleep(60) # انتظار أطول إذا لم يتم العثور على فرص
                        continue
                    
                    # --- بدء التحليل للعملات المفلترة ---
                    for symbol in symbols_to_analyze:
                        # 1. فلتر حالة السوق (Market Regime Filter) - استخدام اتجاه 1h
                        market_regime = self._get_market_regime(symbol, timeframe=self.DIRECTION_CONFIRMATION_TimEframe)
                        if market_regime != "uptrend":
                            continue # تخطي إذا لم يكن السوق في حالة ترند صاعد

                        # 2. تأكيد الاتجاه على الفريم الأعلى (Multi-Timeframe Confirmation)
                        is_uptrend_long, _, _ = self._analyze_market(symbol, timeframe=self.DIRECTION_CONFIRMATION_TimEframe)
                        if not is_uptrend_long:
                            continue
                        
                        # 3. تحليل الدخول على الفريم الأصغر (Entry Quality Filter)
                        is_good_entry, price, rsi_value = self._analyze_market(symbol, timeframe=self.ENTRY_CONFIRMATION_TimEframe)
                        
                        if is_good_entry:
                            # 4. حساب كمية الصفقة بناءً على إدارة المخاطر
                            quantity_to_buy = self._calculate_order_qty(symbol, price)
                            if quantity_to_buy <= 0:
                                continue # تخطي إذا لم يتم حساب الكمية بنجاح

                            # 5. تنفيذ أمر الشراء
                            buy_order = self._create_order('buy', symbol, quantity_to_buy)
                            if buy_order:
                                # حساب وقف الخسارة الأولي مباشرة هنا
                                atr_initial = self._calculate_atr(symbol, self.ENTRY_CONFIRMATION_TimEframe)
                                initial_sl_price = price * (1 - self.STOP_LOSS_ATR_MULTIPLIER * atr_initial / price) if atr_initial else price * (1 - self.STOP_LOSS_PCT/100)
                                
                                # تخزين معلومات الصفقة النشطة
                                self.active_trade = {
                                    'symbol': symbol,
                                    'entry': price,
                                    'stop_loss_price': initial_sl_price, # SL ديناميكي
                                    'initial_stop_loss_price': initial_sl_price, # SL الأولي الثابت (لضمان عدم رجوعه)
                                    'highest_profit_price': price, # لتتبع أعلى سعر وصول إليه الربح
                                }
                                
                                # إرسال رسالة تلجرام عند الدخول
                                msg = f"🎯 *تم قنص فرصة (Managed Risk)!*\n"
                                msg += f"🪙 العملة: {symbol}\n"
                                msg += f"💵 سعر الدخول: {price:.4f}\n"
                                msg += f"⏱️ الفريم: {self.ENTRY_CONFIRMATION_TimEframe}\n"
                                msg += f"📈 اتجاه {self.DIRECTION_CONFIRMATION_TimEframe}: صاعد\n"
                                msg += f"📊 RSI ({self.ENTRY_CONFIRMATION_TimEframe}): {rsi_value:.2f}\n"
                                msg += f"⚖️ حجم الصفقة: {quantity_to_buy:.6f}\n"
                                msg += f"🛑 وقف الخسارة (SL): {self.active_trade['stop_loss_price']:.4f}\n"
                                msg += f"⏳ جاري المراقبة..."
                                self._send_telegram(msg)
                                
                                self.consecutive_losses = 0 # إعادة تعيين الخسائر المتتالية عند فتح صفقة جديدة
                                break # اكتفى بفرصة واحدة في كل دورة بحث
                
                else:
                    # ---- مراقبة الصفقة المفتوحة ----
                    symbol = self.active_trade['symbol']
                    ticker = self._fetch_ticker(symbol)
                    if not ticker:
                        print(f"⚠️ فشل جلب سعر {symbol} لمراقبته. إعادة المحاولة.")
                        self._send_telegram(f"⚠️ *فشل جلب سعر {symbol} للمراقبة.*")
                        # قد يكون هناك مشكلة مؤقتة، من الأفضل إبقاء الصفقة نشطة
                        continue # تجاهل هذه الدورة

                    current_price = ticker['last']
                    entry_price = self.active_trade['entry']
                    current_profit_pct = ((current_price - entry_price) / entry_price) * 100

                    # تحديث أعلى سعر تم الوصول إليه للـ Trailing Stop
                    if current_price > self.active_trade['highest_profit_price']:
                        self.active_trade['highest_profit_price'] = current_price
                    highest_profit_pct = ((self.active_trade['highest_profit_price'] - entry_price) / entry_price) * 100
                    
                    print(f"⏱️ مراقبة {symbol} | الربح: {current_profit_pct:.2f}% | أعلى ربح: {highest_profit_pct:.2f}% | SL: {self.active_trade['stop_loss_price']:.4f}", end='\r')

                    # 1. التحقق من وقف الخسارة الديناميكي (ATR-based SL)
                    # التأكد من أن SL الفعلي (current stop_loss_price) أكبر من SL الأولي (initial_stop_loss_price)
                    # لا تسمح لـ SL بالعودة للأسفل بعد أن تم رفعه
                    safe_stop_loss = max(self.active_trade['stop_loss_price'], self.active_trade['initial_stop_loss_price'])
                    
                    if current_price <= safe_stop_loss:
                        self._close_trade("🛑 ضرب وقف الخسارة (ATR)", current_profit_pct, is_loss=True)
                        continue # انتهت دورة المراقبة هذه

                    # 2. التحقق من حد الخسارة اليومي (تم التحقق منه في بداية الدورة)

                    # 3. التحقق من الهدف الأساسي (Take Profit)
                    if current_profit_pct >= self.TAKE_PROFIT_PCT:
                        self._close_trade("🏆 تحقيق الهدف الأساسي", current_profit_pct, is_loss=False)
                        continue

                    # 4. تحسين ملاحقة الأرباح (ATR-based Trailing Stop)
                    if highest_profit_pct >= self.TRAILING_ACTIVATE_PCT:
                        atr_value = self._calculate_atr(symbol, self.ENTRY_CONFIRMATION_TimEframe)
                        if atr_value:
                            # استخدام TRAILING_DROP_PCT: نسبة من أعلى سعر تم الوصول إليه
                            new_trailing_stop_price_candidate = self.active_trade['highest_profit_price'] * (1 - (self.TRAILING_DROP_PCT / 100))
                            
                            # نرفع نقطة الـ SL فقط إذا كان المستوى الجديد أفضل (أعلى) من SL الحالي
                            # ونتأكد أنه لا ينزل عن الـ SL الأولي
                            new_trailing_stop_price = max(new_trailing_stop_price_candidate, self.active_trade['initial_stop_loss_price'])
                            
                            if new_trailing_stop_price > self.active_trade['stop_loss_price']:
                                self.active_trade['stop_loss_price'] = new_trailing_stop_price
                                self._send_telegram(f"⬆️ **تم تحديث Trailing SL لـ {symbol} إلى:** {self.active_trade['stop_loss_price']:.4f}")

                    # تم التأكد من أن الـ SL لا يتراجع أبداً بفضل استخدام max() مع initial_stop_loss_price
            
            except ccxt.RateLimitExceeded as e:
                print(f"\n❌ Rate Limit Exceeded: {e}. Waiting for {e.retryAfter / 1000:.1f} seconds...")
                self._send_telegram(f"❌ *Rate Limit Exceeded:* Waiting for {e.retryAfter / 1000:.1f} seconds...")
                time.sleep(e.retryAfter / 1000 if e.retryAfter else 60) # الانتظار للمدة المحددة أو 60 ثانية
            except ccxt.NetworkError as e:
                print(f"\n❌ خطأ شبكة: {e}. محاولة إعادة الاتصال بعد 30 ثانية...")
                self._send_telegram(f"❌ *خطأ في الشبكة:* {e}. جاري إعادة المحاولة...")
                time.sleep(30)
            except ccxt.ExchangeError as e:
                print(f"\n❌ خطأ في المنصة: {e}. جاري المحاولة...")
                self._send_telegram(f"❌ *خطأ في المنصة:* {e}. جاري المحاولة...")
                time.sleep(15)
            except Exception as e: # للأخطاء العامة
                print(f"\n⚠️ خطأ غير متوقع في حلقة التشغيل: {e}")
                self._send_telegram(f"⚠️ *خطأ فادح غير متوقع في Bot:* {e}\nجاري المحاولة لتجاوز الخطأ...")
                time.sleep(15) # انتظر قليلاً قبل الدورة التالية
            
            # تأخير بين الدورات (تم تعديله ليتم خارج كتل except)
            time.sleep(15)

            # إرسال التقرير اليومي (مثلاً كل 24 ساعة)
            now = datetime.datetime.now()
            if (now - self.last_report_time).total_seconds() >= 24 * 60 * 60: # 24 ساعة
                self.performance_tracker.send_daily_report()
                self.last_report_time = now


if __name__ == "__main__":
    bot = LegendaryBot()
    bot.run()
