"""
🔥 لوحة تحكم القناص — V8.1 OPEN (شاشة العمليات — دخول مباشر بلا مفتاح)
الحماية عبر سرية رابط Railway نفسه (رابط عشوائي طويل لا يعرفه أحد سواك)
"""

import os
import json
import time
import aiosqlite
from aiohttp import web

PANEL_START = time.time()

NOTIFY_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, kind TEXT, title TEXT, body TEXT, level TEXT
)"""

PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎯 القناص — شاشة العمليات</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0f1a;--bg2:#111827;--card:#1a2234;--bord:#2d3748;--txt:#f1f5f9;--sub:#94a3b8;
--green:#00d4aa;--blue:#3b82f6;--purple:#8b5cf6;--orange:#f97316;--red:#ef4444;--yellow:#eab308}
body{font-family:'Tajawal',sans-serif;background:var(--bg);color:var(--txt);min-height:100vh}
.bg-pattern{position:fixed;inset:0;background:
radial-gradient(ellipse at 20% 20%,rgba(0,212,170,.07) 0%,transparent 50%),
radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.07) 0%,transparent 50%);pointer-events:none;z-index:0}
.hidden{display:none!important}
/* Loading */
.loading-overlay{position:fixed;inset:0;background:var(--bg);display:flex;flex-direction:column;
align-items:center;justify-content:center;z-index:1000;gap:15px}
.loading-spinner{width:50px;height:50px;border:4px solid rgba(0,212,170,.2);border-top-color:var(--green);
border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-text{color:var(--sub);font-size:14px}
/* Header */
.header{background:var(--bg2);border-bottom:1px solid var(--bord);padding:1rem 1.5rem;position:sticky;top:0;z-index:100;backdrop-filter:blur(10px)}
.header-content{max-width:1400px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.logo{display:flex;align-items:center;gap:12px}
.logo-icon{width:45px;height:45px;background:linear-gradient(135deg,#00d4aa,#00a080);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px}
.logo h1{font-size:21px;background:linear-gradient(135deg,var(--green),var(--blue));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo span{font-size:11px;color:var(--sub);display:block}
.badge{display:flex;align-items:center;gap:8px;padding:8px 16px;background:rgba(0,212,170,.15);
border:1px solid rgba(0,212,170,.3);border-radius:50px;font-size:13px;color:var(--green)}
.badge.off{background:rgba(239,68,68,.15);border-color:rgba(239,68,68,.3);color:var(--red)}
.dot{width:8px;height:8px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}
.badge.off .dot{background:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
button{font-family:inherit}
.act{padding:10px 18px;border:none;border-radius:10px;font-weight:700;cursor:pointer;font-size:13px;transition:.3s}
.btn-g{background:linear-gradient(135deg,#00d4aa,#00a080);color:#fff}
.btn-g:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(0,212,170,.3)}
.btn-r{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.4)}
.btn-r:hover{background:rgba(239,68,68,.25)}
.btn-s{background:rgba(255,255,255,.08);color:var(--sub);border:1px solid var(--bord)}
.btn-s:hover{background:rgba(255,255,255,.15)}
/* Layout */
main{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:1.5rem}
.tabs{display:flex;gap:5px;margin-bottom:20px;border-bottom:1px solid var(--bord);overflow-x:auto;padding-bottom:2px}
.tab{padding:12px 20px;border:none;background:transparent;color:var(--sub);cursor:pointer;font-weight:600;
font-size:14px;border-radius:10px 10px 0 0;transition:.2s;white-space:nowrap;position:relative}
.tab:hover{color:var(--txt);background:rgba(255,255,255,.05)}
.tab.active{color:var(--green);background:rgba(0,212,170,.1)}
.tab.active::after{content:'';position:absolute;bottom:-2px;right:0;left:0;height:2px;background:var(--green)}
.tab-content{display:none;animation:fadeIn .3s}
.tab-content.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
/* Cards */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--bord);border-radius:16px;padding:22px;position:relative;overflow:hidden;transition:.3s}
.card:hover{transform:translateY(-4px);border-color:rgba(0,212,170,.3)}
.card::before{content:'';position:absolute;top:0;right:0;width:100px;height:100px;border-radius:50%;filter:blur(50px);opacity:.12}
.card.g::before{background:var(--green)} .card.b::before{background:var(--blue)} .card.p::before{background:var(--purple)}
.card.o::before{background:var(--orange)} .card.y::before{background:var(--yellow)}
.card .l{font-size:13px;color:var(--sub);display:flex;align-items:center;gap:8px}
.card .v{font-size:32px;font-weight:800;margin:8px 0 4px}
.card .s{font-size:11px;color:var(--sub);padding-top:10px;border-top:1px solid var(--bord);margin-top:10px}
.cg .v{color:var(--green)} .cb .v{color:var(--blue)} .cp .v{color:var(--purple)} .co .v{color:var(--orange)} .cy .v{color:var(--yellow)}
.pos{color:var(--green)!important} .neg{color:var(--red)!important}
/* Sections */
.section{background:var(--card);border:1px solid var(--bord);border-radius:16px;padding:22px;margin-bottom:24px}
.section h3{margin-bottom:16px;font-size:16px;display:flex;align-items:center;gap:8px}
/* Tables */
table{width:100%;border-collapse:collapse}
th{text-align:right;padding:10px;color:var(--sub);font-size:11px;border-bottom:1px solid var(--bord);text-transform:uppercase;letter-spacing:.5px}
td{padding:12px 10px;font-size:13px;border-bottom:1px solid rgba(255,255,255,.04)}
tr:hover td{background:rgba(0,212,170,.03)}
.tag{padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;display:inline-block}
.tag.buy{background:rgba(0,212,170,.15);color:var(--green)}
.tag.sell{background:rgba(239,68,68,.15);color:var(--red)}
.tag.win{background:rgba(16,185,129,.15);color:#10b981}
.tag.loss{background:rgba(239,68,68,.15);color:var(--red)}
.tag.open{background:rgba(245,158,11,.15);color:#f59e0b}
.tag.info{background:rgba(59,130,246,.15);color:var(--blue)}
.tag.warn{background:rgba(249,115,22,.15);color:var(--orange)}
.tag.err{background:rgba(239,68,68,.15);color:var(--red)}
.tag.ok{background:rgba(16,185,129,.15);color:#10b981}
.empty{text-align:center;color:var(--sub);padding:35px;font-size:14px}
/* Notifications feed */
.feed{display:flex;flex-direction:column;gap:10px;max-height:520px;overflow-y:auto;padding-left:4px}
.feed::-webkit-scrollbar{width:5px}
.feed::-webkit-scrollbar-thumb{background:var(--bord);border-radius:3px}
.notif{display:flex;gap:14px;padding:14px;background:var(--bg2);border-radius:12px;border-right:4px solid transparent;animation:fadeIn .3s}
.notif.trade{border-right-color:var(--green)}
.notif.partial{border-right-color:var(--blue)}
.notif.close{border-right-color:var(--purple)}
.notif.error{border-right-color:var(--red)}
.notif.tuner{border-right-color:var(--orange)}
.notif.info{border-right-color:var(--sub)}
.notif-icon{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0}
.notif.trade .notif-icon{background:rgba(0,212,170,.15)}
.notif.partial .notif-icon{background:rgba(59,130,246,.15)}
.notif.close .notif-icon{background:rgba(139,92,246,.15)}
.notif.error .notif-icon{background:rgba(239,68,68,.15)}
.notif.tuner .notif-icon{background:rgba(249,115,22,.15)}
.notif.info .notif-icon{background:rgba(148,163,184,.15)}
.notif-body{flex:1;min-width:0}
.notif-title{font-size:14px;font-weight:700;margin-bottom:3px}
.notif-text{font-size:12px;color:var(--sub);line-height:1.5;white-space:pre-wrap;word-break:break-word}
.notif-time{font-size:10px;color:var(--sub);opacity:.7;direction:ltr;text-align:right;margin-top:4px}
/* Health */
.health-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.health-item{display:flex;align-items:center;gap:12px;background:var(--bg2);padding:15px;border-radius:12px}
.h-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.h-dot.ok{background:#10b981;box-shadow:0 0 10px rgba(16,185,129,.5)}
.h-dot.bad{background:var(--red);box-shadow:0 0 10px rgba(239,68,68,.5)}
.h-dot.warn{background:var(--yellow)}
.h-name{font-size:13px;font-weight:600}
.h-status{font-size:11px;color:var(--sub)}
.kv{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:14px}
.kv:last-child{border-bottom:none}
.kv b{color:var(--green)}
/* Score bar */
.score-bar{display:flex;height:6px;border-radius:3px;overflow:hidden;margin-top:10px;background:var(--bg2)}
.score-seg{height:100%}
.footer{text-align:center;padding:20px;color:var(--sub);font-size:12px;border-top:1px solid var(--bord);margin-top:20px}
.actions-row{display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:768px){.card .v{font-size:24px}.tabs{gap:2px}.tab{padding:10px 12px;font-size:12px}}
</style>
</head>
<body>
<div class="bg-pattern"></div>

<div class="loading-overlay" id="loadingOverlay">
  <div class="loading-spinner"></div>
  <div class="loading-text">جارِ فتح شاشة العمليات...</div>
</div>

<header class="header"><div class="header-content">
  <div class="logo">
    <div class="logo-icon">🎯</div>
    <div><h1>القناص الأسطوري</h1><span id="modeTxt">شاشة العمليات V8.1</span></div>
  </div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <div class="badge" id="liveBadge"><span class="dot"></span><span id="liveTxt">البوت حي ✓</span></div>
    <button class="act btn-g" onclick="loadAll()">🔄 تحديث</button>
  </div>
</div></header>

<main id="mainContent" class="hidden">

<div class="tabs">
  <button class="tab active" onclick="switchTab('overview',this)">📊 نظرة عامة</button>
  <button class="tab" onclick="switchTab('trades',this)">📂 الصفقات</button>
  <button class="tab" onclick="switchTab('signals',this)">📡 الإشارات</button>
  <button class="tab" onclick="switchTab('notifications',this)">🔔 الإشعارات <span id="notifCount" class="tag ok" style="padding:1px 7px;font-size:10px;margin-right:4px">0</span></button>
  <button class="tab" onclick="switchTab('tuner',this)">🧠 المطوّر التكيفي</button>
  <button class="tab" onclick="switchTab('system',this)">⚙️ النظام</button>
</div>

<!-- ═══════════ نظرة عامة ═══════════ -->
<div class="tab-content active" id="tab-overview">
  <div class="grid">
    <div class="card g"><div class="l">💵 الرصيد المتاح</div><div class="v" id="balance">$0</div><div class="s" id="modeSub">—</div></div>
    <div class="card b"><div class="l">📈 ربح اليوم</div><div class="v" id="dayPnl">$0</div><div class="s" id="dayWl">—</div></div>
    <div class="card p"><div class="l">🏆 نسبة الفوز</div><div class="v" id="wrAll">—</div><div class="s" id="allWl">—</div></div>
    <div class="card o"><div class="l">📂 مفتوحة الآن</div><div class="v" id="openCount">0</div><div class="s" id="scanTxt">—</div></div>
    <div class="card y"><div class="l">🧠 فوز آخر 10</div><div class="v" id="wr10">—</div><div class="s" id="tunerSub">—</div></div>
  </div>

  <div class="grid" style="grid-template-columns:2fr 1fr">
    <div class="section">
      <h3>📂 الصفقات المفتوحة الآن <span style="font-size:11px;color:var(--sub)">(تحديث كل 10 ثوانٍ)</span></h3>
      <div id="openTradesBox"><div class="empty">لا صفقات مفتوحة — القناص يراقب السوق</div></div>
    </div>
    <div class="section">
      <h3>🛡️ حالة الحمايات</h3>
      <div id="healthBox" class="health-grid" style="grid-template-columns:1fr">—</div>
    </div>
  </div>

  <div class="section">
    <h3>🔔 آخر الأحداث الحية</h3>
    <div class="feed" id="liveFeed" style="max-height:300px"></div>
  </div>
</div>

<!-- ═══════════ الصفقات ═══════════ -->
<div class="tab-content" id="tab-trades">
  <div class="section">
    <h3>📂 المفتوحة الآن</h3>
    <div id="tradesOpenBox"><div class="empty">لا صفقات مفتوحة</div></div>
  </div>
  <div class="section">
    <h3>🏁 آخر الصفقات المغلقة</h3>
    <div id="tradesClosedBox"><div class="empty">لا صفقات مغلقة بعد</div></div>
  </div>
</div>

<!-- ═══════════ الإشارات ═══════════ -->
<div class="tab-content" id="tab-signals">
  <div class="section">
    <h3>📡 سجل الإشارات (آخر 50)</h3>
    <div id="signalsBox"><div class="empty">لا إشارات بعد</div></div>
  </div>
</div>

<!-- ═══════════ الإشعارات ═══════════ -->
<div class="tab-content" id="tab-notifications">
  <div class="section">
    <h3>🔔 مركز الإشعارات (كل ما يقوم به البوت)</h3>
    <div class="feed" id="notifFeed"></div>
  </div>
</div>

<!-- ═══════════ المطوّر ═══════════ -->
<div class="tab-content" id="tab-tuner">
  <div class="grid" style="grid-template-columns:1fr 1fr">
    <div class="section">
      <h3>🧠 الحالة الحالية</h3>
      <div id="tunerState">—</div>
    </div>
    <div class="section">
      <h3>📈 سجل آخر 20 نتيجة</h3>
      <div id="tunerHistory">—</div>
      <div class="score-bar" id="tunerBar"></div>
    </div>
  </div>
</div>

<!-- ═══════════ النظام ═══════════ -->
<div class="tab-content" id="tab-system">
  <div class="grid" style="grid-template-columns:1fr 1fr">
    <div class="section">
      <h3>⚙️ الإعدادات الحالية</h3>
      <div id="settingsBox">—</div>
    </div>
    <div>
      <div class="section">
        <h3>🚨 الأخطاء المرصودة</h3>
        <div id="errorsBox">—</div>
      </div>
      <div class="section">
        <h3>⚡ إجراءات الطوارئ</h3>
        <div class="actions-row">
          <button class="act btn-s" id="pauseBtn" onclick="togglePause()">⏸️ إيقاف التداول مؤقتاً</button>
          <button class="act btn-r" onclick="closeAll()">🛑 إغلاق كل الصفقات فوراً</button>
        </div>
        <p style="color:var(--sub);font-size:11px;margin-top:12px;line-height:1.6">
        ⚠️ الإيقاف مؤقت (ذاكرة فقط) — بعد إعادة النشر يعود لمتغيرات البيئة.<br>
        المراكز المفتوحة تبقى مُدارة ومحمية بستوب المنصة حتى أثناء الإيقاف.<br>
        🔒 الحماية عبر سرية هذا الرابط — لا تشاركه مع أحد!</p>
      </div>
    </div>
  </div>
</div>

<div class="footer">🔥 القناص الأسطوري V8.1 — شاشة العمليات الكاملة | كل المراكز محمية بستوب المنصة على Binance</div>
</main>

<script>
let timer = null;
let lastNotifId = 0;

async function api(path, method='GET'){
  const res = await fetch(path, {method});
  if(!res.ok) throw new Error('' + res.status);
  return res.json();
}
function switchTab(name, el){
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  el.classList.add('active');
}
function money(v){return (v>=0?'+':'') + '$' + Math.abs(v).toFixed(2)}
function sign(v,d=1){return (v>=0?'+':'') + v.toFixed(d)}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')}

const KIND_MAP = {
  trade:{cls:'trade',icon:'🟢'}, partial:{cls:'partial',icon:'🎯'},
  close:{cls:'close',icon:'🏁'}, error:{cls:'error',icon:'🚨'},
  tuner:{cls:'tuner',icon:'🧠'}, info:{cls:'info',icon:'ℹ️'},
  system:{cls:'info',icon:'⚙️'}
};

async function loadAll(){
  const ov = await api('/api/overview');

  document.getElementById('balance').textContent = '$' + (+ov.balance).toFixed(2);
  const mode = ov.trade_enabled ? (ov.testnet ? '⚔️ تداول (تجريبي 🧪)' : '⚔️ تداول حقيقي') : '👁️ مراقبة فقط';
  document.getElementById('modeTxt').textContent = mode + ' • V8.1';
  document.getElementById('modeSub').textContent = 'رافعة ' + ov.leverage + 'x • هامش $' + ov.trade_size + ' • ' + ov.pairs + ' زوج';

  const dp = ov.today ? ov.today.pnl : 0;
  const dEl = document.getElementById('dayPnl');
  dEl.textContent = money(dp); dEl.className = 'v ' + (dp>=0?'pos':'neg');
  document.getElementById('dayWl').textContent = ov.today ? (ov.today.wins+'W / '+ov.today.losses+'L اليوم') : '—';

  const tot = ov.stats.wins + ov.stats.losses;
  document.getElementById('wrAll').textContent = tot ? Math.round(ov.stats.wins/tot*100)+'%' : '—';
  document.getElementById('allWl').textContent = ov.stats.wins+'W / '+ov.stats.losses+'L إجمالاً';
  document.getElementById('openCount').textContent = ov.open_trades;
  document.getElementById('scanTxt').textContent = 'دورات: '+ov.scans+' • تشغيل: '+ov.uptime+' دقيقة';
  document.getElementById('wr10').textContent = ov.tuner.winrate || '—';
  document.getElementById('tunerSub').textContent = 'عتبة: '+ov.tuner.min_score+' • قرب: '+(ov.tuner.proximity_pct*100).toFixed(1)+'%';

  const live = ov.price_age < 120;
  document.getElementById('liveBadge').className = 'badge' + (live?'':' off');
  document.getElementById('liveTxt').textContent = live ? 'البوت حي ✓' : 'توقف تدفق الأسعار!';

  const hb = document.getElementById('healthBox');
  hb.innerHTML = [
    ['تدفق الأسعار', live ? 'متصل ✓' : 'متوقف '+ov.price_age+'ث', live?'ok':'bad'],
    ['ستوبات المنصة', ov.open_trades > 0 ? 'مفعّلة' : 'لا مراكز', 'ok'],
    ['الرصيد', '$'+(+ov.balance).toFixed(2), ov.balance >= ov.trade_size ? 'ok' : 'warn'],
    ['وضع التشغيل', mode, ov.trade_enabled?'ok':'warn'],
  ].map(([n,s,c])=>'<div class="health-item"><div class="h-dot '+c+'"></div><div><div class="h-name">'+n+'</div><div class="h-status">'+s+'</div></div></div>').join('');

  const tr = await api('/api/trades');
  renderOpenTrades(tr, 'openTradesBox');
  renderOpenTrades(tr, 'tradesOpenBox');

  const cl = await api('/api/closed');
  const cb = document.getElementById('tradesClosedBox');
  if(!cl.length){ cb.innerHTML = '<div class="empty">لا صفقات مغلقة بعد</div>'; }
  else{
    let h = '<table><tr><th>الوقت</th><th>الزوج</th><th>اتجاه</th><th>النتيجة</th><th>السبب</th><th>التقييم</th></tr>';
    cl.forEach(c=>{
      h += '<tr><td>'+c.time+'</td><td><b>'+c.symbol+'</b></td>'
        + '<td><span class="tag '+(c.direction==='BUY'?'buy':'sell')+'">'+(c.direction==='BUY'?'شراء':'بيع')+'</span></td>'
        + '<td class="'+(c.pnl>=0?'pos':'neg')+'"><b>'+money(c.pnl)+'</b> ('+sign(c.pnl_pct)+'%)</td>'
        + '<td style="font-size:11px;color:var(--sub)">'+c.reason+'</td>'
        + '<td>'+(c.score?c.score+'/8':'—')+'</td></tr>';
    });
    cb.innerHTML = h + '</table>';
  }

  const sig = await api('/api/signals');
  const sb = document.getElementById('signalsBox');
  if(!sig.length){ sb.innerHTML = '<div class="empty">القناص يراقب — لا إشارات بعد</div>'; }
  else{
    let h = '<table><tr><th>الوقت</th><th>الزوج</th><th>اتجاه</th><th>تقييم</th><th>الزناد</th><th>قرب</th><th>ستوك</th><th>حجم</th><th>النتيجة</th></tr>';
    sig.forEach(s=>{
      const res = s.result===1?'<span class="tag win">ربح'+(s.pnl!==null?' '+money(s.pnl):'')+'</span>'
                : s.result===0?'<span class="tag loss">خسارة'+(s.pnl!==null?' '+money(s.pnl):'')+'</span>'
                : '<span class="tag open">جارية</span>';
      h += '<tr><td>'+s.time+'</td><td><b>'+s.symbol+'</b></td>'
        + '<td><span class="tag '+(s.direction==='BUY'?'buy':'sell')+'">'+(s.direction==='BUY'?'شراء':'بيع')+'</span></td>'
        + '<td><b>'+s.score+'/8</b></td><td>'+(s.trigger==='sweep'?'⚡ تصفية':'🔄 إعادة اختبار')+'</td>'
        + '<td>'+s.proximity+'/2</td><td>'+s.stoch+'/2</td><td>'+(s.volume?'+1':'—')+'</td>'
        + '<td>'+res+'</td></tr>';
    });
    sb.innerHTML = h + '</table>';
  }

  const nf = await api('/api/notifications?after='+lastNotifId);
  if(nf.items && nf.items.length){
    lastNotifId = nf.last_id || lastNotifId;
    document.getElementById('notifCount').textContent = nf.total_unread || nf.items.length;
    const feed = document.getElementById('notifFeed');
    const liveF = document.getElementById('liveFeed');
    let html = '';
    nf.items.forEach(n=>{
      const k = KIND_MAP[n.kind] || KIND_MAP.info;
      const item = '<div class="notif '+k.cls+'"><div class="notif-icon">'+k.icon+'</div>'
        + '<div class="notif-body"><div class="notif-title">'+esc(n.title)+'</div>'
        + (n.body ? '<div class="notif-text">'+esc(n.body)+'</div>' : '')
        + '<div class="notif-time">'+n.time+'</div></div></div>';
      html += item;
    });
    feed.innerHTML = html + feed.innerHTML;
    liveF.innerHTML = html + liveF.innerHTML;
    while(liveF.children.length > 15) liveF.removeChild(liveF.lastChild);
    while(feed.children.length > 100) feed.removeChild(feed.lastChild);
  }

  const tu = ov.tuner;
  document.getElementById('tunerState').innerHTML =
    '<div class="kv"><span>الحد الأدنى للتقييم</span><b>'+tu.min_score+' / 8</b></div>'
    + '<div class="kv"><span>نطاق القرب من المنطقة</span><b>'+(tu.proximity_pct*100).toFixed(1)+'%</b></div>'
    + '<div class="kv"><span>استوكاستك صارم</span><b>'+(tu.strict_stoch?'نعم':'لا')+'</b></div>'
    + '<div class="kv"><span>فوز آخر 10 صفقات</span><b>'+(tu.winrate||'غير كافٍ')+'</b></div>';
  const hist = await api('/api/tuner-history');
  const th = document.getElementById('tunerHistory');
  const bar = document.getElementById('tunerBar');
  if(hist.length){
    th.innerHTML = hist.map(w=>'<span class="tag '+(w?'win':'loss')+'" style="width:28px;text-align:center">'+(w?'✓':'✗')+'</span>').join(' ');
    bar.innerHTML = hist.map(w=>'<div class="score-seg" style="flex:1;background:'+(w?'#10b981':'#ef4444')+'"></div>').join('');
  } else { th.innerHTML = '<div class="empty">لا نتائج بعد</div>'; bar.innerHTML=''; }

  const er = await api('/api/errors');
  const eb = document.getElementById('errorsBox');
  const ekeys = Object.keys(er.errors||{});
  if(!ekeys.length){ eb.innerHTML = '<div class="empty" style="padding:20px">✅ لا أخطاء — كل شيء يعمل بنقاء</div>'; }
  else{ eb.innerHTML = ekeys.map(k=>'<div class="kv"><span>'+esc(k)+'</span><b style="color:var(--orange)">تكرار ×'+er.errors[k]+'</b></div>').join(''); }

  document.getElementById('settingsBox').innerHTML =
    '<div class="kv"><span>وضع التشغيل</span><b>'+mode+'</b></div>'
    + '<div class="kv"><span>Testnet (تجريبي)</span><b>'+(ov.testnet?'🧪 نعم':'لا — أموال حقيقية')+'</b></div>'
    + '<div class="kv"><span>الرافعة</span><b>'+ov.leverage+'x</b></div>'
    + '<div class="kv"><span>هامش الصفقة</span><b>$'+ov.trade_size+'</b></div>'
    + '<div class="kv"><span>نوشنال الصفقة</span><b>$'+(ov.trade_size*ov.leverage)+'</b></div>'
    + '<div class="kv"><span>الصفقات المتزامنة</span><b>'+ov.max_open+'</b></div>'
    + '<div class="kv"><span>زوج مُحمّل</span><b>'+ov.pairs+'</b></div>';

  document.getElementById('pauseBtn').textContent = ov.trade_enabled ? '⏸️ إيقاف التداول مؤقتاً' : '▶️ استئناف التداول';
}
function renderOpenTrades(tr, boxId){
  const box = document.getElementById(boxId);
  if(!tr.length){ box.innerHTML = '<div class="empty">لا صفقات مفتوحة — القناص يراقب السوق</div>'; return; }
  let h = '<table><tr><th>الزوج</th><th>اتجاه</th><th>الدخول</th><th>الحالي</th><th>الربح العائم</th><th>الوقف</th><th>الهدف</th><th>الحالة</th></tr>';
  tr.forEach(t=>{
    h += '<tr><td><b>'+t.symbol+'</b></td>'
      + '<td><span class="tag '+(t.side==='BUY'?'buy':'sell')+'">'+(t.side==='BUY'?'شراء':'بيع')+'</span></td>'
      + '<td>'+t.entry+'</td><td>'+(t.current!==null?t.current:'—')+'</td>'
      + '<td class="'+((t.pnl||0)>=0?'pos':'neg')+'"><b>'+(t.pnl===null?'—':money(t.pnl)+' ('+sign(t.pnl_pct)+'%)')+'</b></td>'
      + '<td>'+t.sl+'</td><td>'+(t.tp||'—')+'</td>'
      + '<td>'+(t.partial?'<span class="tag info">🎯 جُني + تريلينق</span>':'<span class="tag open">⏳ جارية</span>')+'</td></tr>';
  });
  box.innerHTML = h + '</table>';
}
async function togglePause(){
  const ov = await api('/api/overview');
  await api(ov.trade_enabled ? '/api/pause' : '/api/resume', 'POST');
  loadAll();
}
async function closeAll(){
  if(!confirm('⚠️ سيتم إغلاق كل الصفقات المفتوحة فوراً بسعر السوق الحالي.\nهل أنت متأكد تماماً؟')) return;
  const r = await api('/api/close-all', 'POST');
  alert('تم إغلاق: ' + (r.closed.length ? r.closed.join(', ') : 'لا شيء كان مفتوحاً'));
  loadAll();
}
/* ✅ دخول مباشر — لا مفتاح */
async function start(){
  try{
    await loadAll();
    document.getElementById('loadingOverlay').classList.add('hidden');
    document.getElementById('mainContent').classList.remove('hidden');
    if(!timer) timer = setInterval(loadAll, 10000);
  }catch(e){
    document.querySelector('.loading-text').textContent =
      'تعذر تحميل البيانات (' + e.message + ') — سيعاد المحاولة تلقائياً';
    setTimeout(start, 5000);
  }
}
start();
</script>
</body>
</html>"""


# ═══════════════════ Backend ═══════════════════
class PanelDB:
    """طبقة إشعارات اللوحة — نفس ملف قاعدة البوت"""
    def __init__(self, db_name):
        self.db_name = db_name

    async def init(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(NOTIFY_SCHEMA)
            await db.commit()

    async def add(self, kind, title, body='', level='info'):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "INSERT INTO notifications (ts, kind, title, body, level) VALUES (?,?,?,?,?)",
                    (time.time(), kind, str(title)[:200], str(body)[:600], level))
                await db.commit()
        except Exception:
            pass

    async def get_after(self, after_id, limit=50):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                        "SELECT id, ts, kind, title, body FROM notifications WHERE id > ? ORDER BY id DESC LIMIT ?",
                        (after_id, limit)) as cur:
                    rows = await cur.fetchall()
                async with db.execute("SELECT COUNT(*) c FROM notifications") as cur:
                    total = (await cur.fetchone())[0]
                return {
                    'items': [{
                        'id': r['id'], 'kind': r['kind'], 'title': r['title'], 'body': r['body'],
                        'time': time.strftime('%m-%d %H:%M:%S', time.localtime(r['ts'])),
                    } for r in reversed(rows)],
                    'last_id': max((r['id'] for r in rows), default=after_id),
                    'total_unread': total,
                }
        except Exception:
            return {'items': [], 'last_id': after_id, 'total_unread': 0}


PANEL_DB = None

async def notify(kind, title, body='', level='info'):
    """الواجهة التي يستدعيها البوت بدل رسائل تلغرام"""
    if PANEL_DB:
        await PANEL_DB.add(kind, title, body, level)


def create_app(bot):
    async def index(request):
        return web.Response(text=PAGE, content_type='text/html')

    async def overview(request):
        today = time.strftime('%Y-%m-%d')
        row = await bot.db.get_day_stats(today)
        newest = max((p.get('ts', 0) for p in bot.live_prices.values()), default=0)
        try:
            balance = await bot.get_available_usdt()
        except Exception:
            balance = 0.0
        tuner = bot.tuner
        wr = tuner.recent_winrate(10)
        return web.json_response({
            'ok': True, 'trade_enabled': bot.TRADE_ENABLED, 'testnet': bot.TESTNET,
            'leverage': bot.LEVERAGE, 'trade_size': bot.TRADE_SIZE_USDT,
            'max_open': bot.MAX_OPEN_TRADES, 'pairs': len(bot.all_futures_pairs),
            'balance': round(balance, 2),
            'today': {'pnl': round(row[0], 4) if row else 0.0,
                      'wins': row[1] if row else 0, 'losses': row[2] if row else 0},
            'stats': dict(bot.stats), 'open_trades': len(bot.active_trades),
            'scans': bot.stats.get('total_scans', 0),
            'uptime': int((time.time() - PANEL_START) / 60),
            'price_age': int(time.time() - newest) if newest else 999999,
            'tuner': {'min_score': tuner.min_score,
                      'proximity_pct': tuner.proximity_pct,
                      'strict_stoch': tuner.strict_stoch,
                      'winrate': (str(int(wr*100))+'%') if wr is not None else None},
        })

    async def trades(request):
        out = []
        for symbol, t in list(bot.active_trades.items()):
            prices = bot.get_price(symbol)
            cur = pnl = pnl_pct = None
            if prices:
                cur = prices['bid'] if t['side'] == 'BUY' else prices['ask']
                diff = (cur - t['entry_price']) if t['side'] == 'BUY' else (t['entry_price'] - cur)
                pnl = diff * t['quantity'] + t.get('realized_pnl', 0.0)
                pnl_pct = (diff / t['entry_price'] * 100 * bot.LEVERAGE) if t['entry_price'] else 0
            out.append({
                'symbol': symbol, 'side': t['side'], 'entry': round(t['entry_price'], 6),
                'current': round(cur, 6) if cur else None,
                'pnl': round(pnl, 4) if pnl is not None else None,
                'pnl_pct': round(pnl_pct, 2) if pnl_pct is not None else None,
                'sl': round(t['sl'], 6), 'tp': round(t['tp'], 6) if t.get('tp') else None,
                'partial': bool(t.get('partial_closed', False)),
            })
        return web.json_response(out)

    async def closed(request):
        out = []
        try:
            async with aiosqlite.connect(bot.db.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                        "SELECT symbol, direction, entry_ts, score, result, pnl "
                        "FROM signal_log WHERE result >= 0 ORDER BY id DESC LIMIT 25") as cur:
                    rows = await cur.fetchall()
                for r in rows:
                    out.append({
                        'symbol': r['symbol'], 'direction': r['direction'],
                        'time': time.strftime('%m-%d %H:%M', time.localtime(r['entry_ts'])),
                        'pnl': round(r['pnl'] or 0, 4),
                        'pnl_pct': round(((r['pnl'] or 0) / bot.TRADE_SIZE_USDT * 100), 1),
                        'reason': '—', 'score': r['score'],
                    })
        except Exception:
            pass
        return web.json_response(out)

    async def signals(request):
        out = []
        try:
            async with aiosqlite.connect(bot.db.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                        "SELECT symbol, direction, entry_ts, score, components, result, pnl "
                        "FROM signal_log ORDER BY id DESC LIMIT 50") as cur:
                    rows = await cur.fetchall()
                for r in rows:
                    comp = {}
                    try: comp = json.loads(r['components'] or '{}')
                    except Exception: pass
                    out.append({
                        'symbol': r['symbol'], 'direction': r['direction'],
                        'time': time.strftime('%m-%d %H:%M', time.localtime(r['entry_ts'])),
                        'score': int(r['score'] or 0), 'trigger': comp.get('trigger', '—'),
                        'proximity': comp.get('proximity', 0), 'stoch': comp.get('stoch', 0),
                        'volume': comp.get('volume', 0),
                        'result': r['result'], 'pnl': round(r['pnl'], 4) if r['pnl'] is not None else None,
                    })
        except Exception:
            pass
        return web.json_response(out)

    async def notifications(request):
        after = int(request.query.get('after', 0))
        if PANEL_DB:
            return web.json_response(await PANEL_DB.get_after(after))
        return web.json_response({'items': [], 'last_id': after, 'total_unread': 0})

    async def tuner_history(request):
        return web.json_response(list(bot.tuner.results))

    async def errors(request):
        return web.json_response({'errors': dict(bot.error_counts)})

    async def pause(request):
        bot.TRADE_ENABLED = False
        return web.json_response({'ok': True})

    async def resume(request):
        if not bot.binance_api_key:
            return web.json_response({'ok': False, 'error': 'مفاتيح API ناقصة'}, status=400)
        bot.TRADE_ENABLED = True
        return web.json_response({'ok': True})

    async def close_all(request):
        closed = []
        for symbol, t in list(bot.active_trades.items()):
            prices = bot.get_price(symbol)
            px = (prices['bid'] if t['side'] == 'BUY' else prices['ask']) if prices else t['entry_price']
            ok, fill, pnl_over = await bot._close_position(t, px)
            if ok:
                await bot._finalize_trade(t, fill, 'إغلاق طارئ من اللوحة', pnl_over)
                closed.append(symbol)
        return web.json_response({'ok': True, 'closed': closed})

    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/api/overview', overview)
    app.router.add_get('/api/trades', trades)
    app.router.add_get('/api/closed', closed)
    app.router.add_get('/api/signals', signals)
    app.router.add_get('/api/notifications', notifications)
    app.router.add_get('/api/tuner-history', tuner_history)
    app.router.add_get('/api/errors', errors)
    app.router.add_post('/api/pause', pause)
    app.router.add_post('/api/resume', resume)
    app.router.add_post('/api/close-all', close_all)
    return app


async def start_web_panel(bot):
    global PANEL_DB
    # ✅ OPEN MODE: لا حاجة لـ ADMIN_KEY — الدخول مباشر عبر رابط Railway السري
    try:
        PANEL_DB = PanelDB(bot.db.db_name)
        await PANEL_DB.init()
        app = create_app(bot)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get('PORT', '8080'))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f'🖥️ لوحة التحكم تعمل على المنفذ {port} (وضع مفتوح)')
        return True
    except Exception as e:
        print(f'⚠️ فشل تشغيل اللوحة (البوت يكمل عمله بلا لوحة): {e}')
        return False
