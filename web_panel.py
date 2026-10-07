"""
🖥️ لوحة القناص V9 — من الصفر
✅ دخول مباشر بلا مفتاح (الحماية = سرية رابط Railway)
✅ عرض كل إجراء صغير وكبير يقوم به البوت
✅ لا تعليق أبداً: كل طلب له مهلة 6 ثوانٍ + فشل مرئي بلا دائرة أبدية
✅ لا أخطاء جافاسكريبت: مراجعة سطر سطر
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
<title>🎯 القناص V9</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0f1a;--bg2:#111827;--card:#1a2234;--bord:#2d3748;--txt:#f1f5f9;--sub:#94a3b8;
--green:#00d4aa;--blue:#3b82f6;--purple:#8b5cf6;--orange:#f97316;--red:#ef4444;--yellow:#eab308}
body{font-family:'Tajawal',sans-serif;background:var(--bg);color:var(--txt);min-height:100vh}
.bg{position:fixed;inset:0;background:
radial-gradient(ellipse at 20% 20%,rgba(0,212,170,.07) 0%,transparent 50%),
radial-gradient(ellipse at 80% 80%,rgba(139,92,246,.07) 0%,transparent 50%);pointer-events:none;z-index:0}
.hidden{display:none!important}
/* Header */
.hd{background:var(--bg2);border-bottom:1px solid var(--bord);padding:12px 16px;position:sticky;top:0;z-index:100}
.hd-in{max-width:1400px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.logo{display:flex;align-items:center;gap:12px}
.logo-ic{width:45px;height:45px;background:linear-gradient(135deg,#00d4aa,#00a080);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px}
.logo h1{font-size:21px;background:linear-gradient(135deg,var(--green),var(--blue));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo span{font-size:11px;color:var(--sub);display:block}
.badge{display:flex;align-items:center;gap:8px;padding:8px 16px;background:rgba(0,212,170,.15);
border:1px solid rgba(0,212,170,.3);border-radius:50px;font-size:13px;color:var(--green)}
.badge.off{background:rgba(239,68,68,.15);border-color:rgba(239,68,68,.3);color:var(--red)}
.dot{width:8px;height:8px;background:var(--green);border-radius:50%;animation:pl 2s infinite}
.badge.off .dot{background:var(--red)}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.4}}
button{font-family:inherit}
.act{padding:10px 18px;border:none;border-radius:10px;font-weight:700;cursor:pointer;font-size:13px;transition:.3s}
.btn-g{background:linear-gradient(135deg,#00d4aa,#00a080);color:#fff}
.btn-r{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.4)}
.btn-s{background:rgba(255,255,255,.08);color:var(--sub);border:1px solid var(--bord)}
/* Layout */
main{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:16px}
.tabs{display:flex;gap:5px;margin-bottom:18px;border-bottom:1px solid var(--bord);overflow-x:auto;padding-bottom:2px}
.tab{padding:12px 18px;border:none;background:transparent;color:var(--sub);cursor:pointer;font-weight:600;
font-size:14px;border-radius:10px 10px 0 0;transition:.2s;white-space:nowrap;position:relative}
.tab.act{color:var(--green);background:rgba(0,212,170,.1)}
.tab.act::after{content:'';position:absolute;bottom:-2px;right:0;left:0;height:2px;background:var(--green)}
.tc{display:none}
.tc.act{display:block;animation:fi .3s}
@keyframes fi{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
/* Cards */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:14px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--bord);border-radius:16px;padding:20px;position:relative;overflow:hidden;transition:.3s}
.card:hover{border-color:rgba(0,212,170,.3)}
.card::before{content:'';position:absolute;top:0;right:0;width:100px;height:100px;border-radius:50%;filter:blur(50px);opacity:.12}
.card.g::before{background:var(--green)}.card.b::before{background:var(--blue)}.card.p::before{background:var(--purple)}
.card.o::before{background:var(--orange)}.card.y::before{background:var(--yellow)}
.card .l{font-size:13px;color:var(--sub)}
.card .v{font-size:30px;font-weight:800;margin:8px 0 4px}
.card .s{font-size:11px;color:var(--sub);padding-top:8px;border-top:1px solid var(--bord);margin-top:8px}
.card.g .v{color:var(--green)}.card.b .v{color:var(--blue)}.card.p .v{color:var(--purple)}
.card.o .v{color:var(--orange)}.card.y .v{color:var(--yellow)}
.pos{color:var(--green)!important}.neg{color:var(--red)!important}
/* Sections */
.sec{background:var(--card);border:1px solid var(--bord);border-radius:16px;padding:20px;margin-bottom:20px}
.sec h3{margin-bottom:14px;font-size:16px}
/* Tables */
table{width:100%;border-collapse:collapse}
th{text-align:right;padding:9px;color:var(--sub);font-size:11px;border-bottom:1px solid var(--bord)}
td{padding:11px 9px;font-size:13px;border-bottom:1px solid rgba(255,255,255,.04)}
tr:hover td{background:rgba(0,212,170,.03)}
.tag{padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;display:inline-block}
.tag.buy{background:rgba(0,212,170,.15);color:var(--green)}
.tag.sell{background:rgba(239,68,68,.15);color:var(--red)}
.tag.win{background:rgba(16,185,129,.15);color:#10b981}
.tag.loss{background:rgba(239,68,68,.15);color:var(--red)}
.tag.open{background:rgba(245,158,11,.15);color:#f59e0b}
.tag.info{background:rgba(59,130,246,.15);color:var(--blue)}
.tag.ok{background:rgba(16,185,129,.15);color:#10b981}
.empty{text-align:center;color:var(--sub);padding:30px;font-size:14px}
/* Feed */
.feed{display:flex;flex-direction:column;gap:9px;max-height:560px;overflow-y:auto;padding-left:4px}
.nt{display:flex;gap:12px;padding:13px;background:var(--bg2);border-radius:12px;border-right:4px solid transparent;animation:fi .3s}
.nt.trade{border-right-color:var(--green)}.nt.partial{border-right-color:var(--blue)}
.nt.close{border-right-color:var(--purple)}.nt.error{border-right-color:var(--red)}
.nt.tuner{border-right-color:var(--orange)}.nt.info{border-right-color:var(--sub)}
.nt-ic{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.nt.trade .nt-ic{background:rgba(0,212,170,.15)}.nt.partial .nt-ic{background:rgba(59,130,246,.15)}
.nt.close .nt-ic{background:rgba(139,92,246,.15)}.nt.error .nt-ic{background:rgba(239,68,68,.15)}
.nt.tuner .nt-ic{background:rgba(249,115,22,.15)}.nt.info .nt-ic{background:rgba(148,163,184,.15)}
.nt-b{flex:1;min-width:0}
.nt-t{font-size:14px;font-weight:700;margin-bottom:3px}
.nt-x{font-size:12px;color:var(--sub);line-height:1.6;white-space:pre-wrap;word-break:break-word}
.nt-tm{font-size:10px;color:var(--sub);opacity:.7;direction:ltr;text-align:right;margin-top:4px}
/* Health */
.hg{display:flex;flex-direction:column;gap:10px}
.hi{display:flex;align-items:center;gap:12px;background:var(--bg2);padding:13px;border-radius:12px}
.hd2{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.hd2.ok{background:#10b981;box-shadow:0 0 10px rgba(16,185,129,.5)}
.hd2.bad{background:var(--red);box-shadow:0 0 10px rgba(239,68,68,.5)}
.hd2.warn{background:var(--yellow)}
.hn{font-size:13px;font-weight:600}
.hs{font-size:11px;color:var(--sub)}
.kv{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:14px}
.kv:last-child{border-bottom:none}
.kv b{color:var(--green)}
.bar{display:flex;height:6px;border-radius:3px;overflow:hidden;margin-top:10px;background:var(--bg2)}
.foot{text-align:center;padding:18px;color:var(--sub);font-size:12px;border-top:1px solid var(--bord);margin-top:18px}
.arow{display:flex;gap:10px;flex-wrap:wrap}
/* Status bar */
.sbar{background:var(--bg2);border:1px solid var(--bord);border-radius:12px;padding:10px 16px;
margin-bottom:16px;display:flex;align-items:center;gap:10px;font-size:13px;color:var(--sub)}
.sbar b{color:var(--green)}
@media(max-width:768px){.card .v{font-size:24px}.tab{padding:10px 12px;font-size:12px}}
</style>
</head>
<body>
<div class="bg"></div>

<header class="hd"><div class="hd-in">
  <div class="logo">
    <div class="logo-ic">🎯</div>
    <div><h1>القناص الأسطوري</h1><span id="modeTxt">V9 — شاشة العمليات</span></div>
  </div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <div class="badge" id="liveB"><span class="dot"></span><span id="liveT">البوت حي ✓</span></div>
    <button class="act btn-g" onclick="loadAll()">🔄 تحديث</button>
  </div>
</div></header>

<main>
<div class="sbar">⏱️ آخر تحديث: <b id="lastUpd">الآن</b> • التحديث التلقائي كل 10 ثوانٍ</div>

<div class="tabs">
  <button class="tab act" onclick="sw('overview',this)">📊 نظرة عامة</button>
  <button class="tab" onclick="sw('trades',this)">📂 الصفقات</button>
  <button class="tab" onclick="sw('signals',this)">📡 الإشارات</button>
  <button class="tab" onclick="sw('notifications',this)">🔔 الإشعارات <span id="nCount" class="tag ok" style="padding:1px 7px;font-size:10px">0</span></button>
  <button class="tab" onclick="sw('tuner',this)">🧠 المطوّر</button>
  <button class="tab" onclick="sw('system',this)">⚙️ النظام</button>
</div>

<!-- نظرة عامة -->
<div class="tc act" id="t-overview">
  <div class="grid">
    <div class="card g"><div class="l">💵 الرصيد</div><div class="v" id="balance">$0</div><div class="s" id="modeSub">—</div></div>
    <div class="card b"><div class="l">📈 ربح اليوم</div><div class="v" id="dayPnl">$0</div><div class="s" id="dayWl">—</div></div>
    <div class="card p"><div class="l">🏆 نسبة الفوز</div><div class="v" id="wrAll">—</div><div class="s" id="allWl">—</div></div>
    <div class="card o"><div class="l">📂 مفتوحة</div><div class="v" id="openC">0</div><div class="s" id="scanT">—</div></div>
    <div class="card y"><div class="l">🧠 فوز آخر 10</div><div class="v" id="wr10">—</div><div class="s" id="tunerS">—</div></div>
  </div>
  <div class="grid" style="grid-template-columns:2fr 1fr">
    <div class="sec"><h3>📂 الصفقات المفتوحة</h3><div id="openBox"></div></div>
    <div class="sec"><h3>🛡️ الحمايات</h3><div class="hg" id="healthBox">—</div></div>
  </div>
  <div class="sec"><h3>🔔 آخر الأحداث</h3><div class="feed" id="liveFeed" style="max-height:300px"></div></div>
</div>

<!-- الصفقات -->
<div class="tc" id="t-trades">
  <div class="sec"><h3>📂 المفتوحة الآن</h3><div id="openBox2"></div></div>
  <div class="sec"><h3>🏁 المغلقة</h3><div id="closedBox"></div></div>
</div>

<!-- الإشارات -->
<div class="tc" id="t-signals">
  <div class="sec"><h3>📡 سجل الإشارات</h3><div id="sigBox"></div></div>
</div>

<!-- الإشعارات -->
<div class="tc" id="t-notifications">
  <div class="sec"><h3>🔔 كل ما يقوم به البوت</h3><div class="feed" id="notifFeed"></div></div>
</div>

<!-- المطوّر -->
<div class="tc" id="t-tuner">
  <div class="grid" style="grid-template-columns:1fr 1fr">
    <div class="sec"><h3>🧠 الحالة</h3><div id="tunerSt">—</div></div>
    <div class="sec"><h3>📈 آخر 20 نتيجة</h3><div id="tunerH">—</div><div class="bar" id="tunerBar"></div></div>
  </div>
</div>

<!-- النظام -->
<div class="tc" id="t-system">
  <div class="grid" style="grid-template-columns:1fr 1fr">
    <div class="sec"><h3>⚙️ الإعدادات</h3><div id="setBox">—</div></div>
    <div>
      <div class="sec"><h3>🚨 الأخطاء</h3><div id="errBox">—</div></div>
      <div class="sec"><h3>⚡ طوارئ</h3>
        <div class="arow">
          <button class="act btn-s" id="pauseBtn" onclick="togglePause()">⏸️ إيقاف مؤقت</button>
          <button class="act btn-r" onclick="closeAll()">🛑 إغلاق الكل</button>
        </div>
        <p style="color:var(--sub);font-size:11px;margin-top:10px;line-height:1.6">
        ⚠️ الحماية عبر سرية الرابط — لا تشاركه!<br>المراكز محمية بستوب المنصة دائماً.</p>
      </div>
    </div>
  </div>
</div>

<div class="foot">🔥 القناص الأسطوري V9 — شاشة العمليات | الحماية عبر سرية الرابط</div>
</main>

<script>
let lastNid = 0;
let timer = null;

async function api(path){
  const c = new AbortController();
  const t = setTimeout(()=>c.abort(), 6000);   /* مهلة 6 ثوان — لا تعليق أبداً */
  try{
    const res = await fetch(path, {signal:c.signal, cache:'no-store'});
    if(!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  }finally{ clearTimeout(t); }
}
function sw(name, el){
  document.querySelectorAll('.tc').forEach(x=>x.classList.remove('act'));
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('act'));
  document.getElementById('t-'+name).classList.add('act');
  el.classList.add('act');
}
function mo(v){return (v>=0?'+':'') + '$' + Math.abs(v).toFixed(2)}
function sg(v,d){d=d||1;return (v>=0?'+':'') + v.toFixed(d)}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')}

const KM = {trade:['trade','🟢'],partial:['partial','🎯'],close:['close','🏁'],
error:['error','🚨'],tuner:['tuner','🧠'],info:['info','ℹ️'],system:['info','⚙️']};

async function loadAll(){
  const ov = await api('/api/overview');

  document.getElementById('lastUpd').textContent =
    new Date().toLocaleTimeString('ar',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  document.getElementById('balance').textContent = '$' + (+ov.balance).toFixed(2);
  const mode = ov.trade_enabled ? (ov.testnet ? '⚔️ تداول تجريبي 🧪' : '⚔️ تداول حقيقي') : '👁️ مراقبة';
  document.getElementById('modeTxt').textContent = mode + ' • V9';
  document.getElementById('modeSub').textContent = ov.leverage+'x • $'+ov.trade_size+' • '+ov.pairs+' زوج';

  const dp = ov.today ? ov.today.pnl : 0;
  const dEl = document.getElementById('dayPnl');
  dEl.textContent = mo(dp); dEl.className = 'v ' + (dp>=0?'pos':'neg');
  document.getElementById('dayWl').textContent = ov.today ? (ov.today.wins+'W / '+ov.today.losses+'L') : '—';

  const tot = ov.stats.wins + ov.stats.losses;
  document.getElementById('wrAll').textContent = tot ? Math.round(ov.stats.wins/tot*100)+'%' : '—';
  document.getElementById('allWl').textContent = ov.stats.wins+'W / '+ov.stats.losses+'L';
  document.getElementById('openC').textContent = ov.open_trades;
  document.getElementById('scanT').textContent = 'دورات: '+ov.scans+' • تشغيل: '+ov.uptime+'د';
  document.getElementById('wr10').textContent = ov.tuner.winrate || '—';
  document.getElementById('tunerS').textContent = 'عتبة: '+ov.tuner.min_score;

  const lv = ov.price_age < 120;
  document.getElementById('liveB').className = 'badge' + (lv?'':' off');
  document.getElementById('liveT').textContent = lv ? 'البوت حي ✓' : 'توقف الأسعار!';

  document.getElementById('healthBox').innerHTML = [
    ['تدفق الأسعار', lv ? 'متصل ✓' : 'متوقف '+ov.price_age+'ث', lv?'ok':'bad'],
    ['ستوبات المنصة', ov.open_trades>0 ? 'مفعّلة' : 'لا مراكز', 'ok'],
    ['الرصيد', '$'+(+ov.balance).toFixed(2), ov.balance>=ov.trade_size?'ok':'warn'],
    ['الوضع', mode, ov.trade_enabled?'ok':'warn'],
  ].map(h=>'<div class="hi"><div class="hd2 '+h[2]+'"></div><div><div class="hn">'+h[0]+'</div><div class="hs">'+h[1]+'</div></div></div>').join('');

  const tr = await api('/api/trades');
  renderOpen(tr,'openBox'); renderOpen(tr,'openBox2');

  const cl = await api('/api/closed');
  const cb = document.getElementById('closedBox');
  if(!cl.length){ cb.innerHTML = '<div class="empty">لا صفقات مغلقة بعد</div>'; }
  else{
    let h = '<table><tr><th>الوقت</th><th>الزوج</th><th>اتجاه</th><th>النتيجة</th><th>تقييم</th></tr>';
    cl.forEach(c=>{
      h += '<tr><td>'+c.time+'</td><td><b>'+c.symbol+'</b></td>'
        + '<td><span class="tag '+(c.direction==='BUY'?'buy':'sell')+'">'+(c.direction==='BUY'?'شراء':'بيع')+'</span></td>'
        + '<td class="'+(c.pnl>=0?'pos':'neg')+'"><b>'+mo(c.pnl)+'</b> ('+sg(c.pnl_pct)+'%)</td>'
        + '<td>'+(c.score?c.score+'/8':'—')+'</td></tr>';
    });
    cb.innerHTML = h + '</table>';
  }

  const sig = await api('/api/signals');
  const sb = document.getElementById('sigBox');
  if(!sig.length){ sb.innerHTML = '<div class="empty">القناص يراقب السوق — لا إشارات بعد</div>'; }
  else{
    let h = '<table><tr><th>الوقت</th><th>الزوج</th><th>اتجاه</th><th>تقييم</th><th>الزناد</th><th>النتيجة</th></tr>';
    sig.forEach(s=>{
      const r = s.result===1?'<span class="tag win">ربح</span>':s.result===0?'<span class="tag loss">خسارة</span>':'<span class="tag open">جارية</span>';
      h += '<tr><td>'+s.time+'</td><td><b>'+s.symbol+'</b></td>'
        + '<td><span class="tag '+(s.direction==='BUY'?'buy':'sell')+'">'+(s.direction==='BUY'?'شراء':'بيع')+'</span></td>'
        + '<td><b>'+s.score+'/8</b></td><td>'+(s.trigger==='sweep'?'⚡ تصفية':'🔄 اختبار')+'</td><td>'+r+'</td></tr>';
    });
    sb.innerHTML = h + '</table>';
  }

  const nf = await api('/api/notifications?after='+lastNid);
  if(nf.items && nf.items.length){
    lastNid = nf.last_id || lastNid;
    document.getElementById('nCount').textContent = nf.total_unread || nf.items.length;
    const feed = document.getElementById('notifFeed');
    const lf = document.getElementById('liveFeed');
    let html = '';
    nf.items.forEach(n=>{
      const k = KM[n.kind] || KM.info;
      html += '<div class="nt '+k[0]+'"><div class="nt-ic">'+k[1]+'</div>'
        + '<div class="nt-b"><div class="nt-t">'+esc(n.title)+'</div>'
        + (n.body?'<div class="nt-x">'+esc(n.body)+'</div>':'')
        + '<div class="nt-tm">'+n.time+'</div></div></div>';
    });
    feed.innerHTML = html + feed.innerHTML;
    lf.innerHTML = html + lf.innerHTML;
    while(lf.children.length>15) lf.removeChild(lf.lastChild);
    while(feed.children.length>150) feed.removeChild(feed.lastChild);
  }

  const tu = ov.tuner;
  document.getElementById('tunerSt').innerHTML =
    '<div class="kv"><span>الحد الأدنى للتقييم</span><b>'+tu.min_score+' / 8</b></div>'
    + '<div class="kv"><span>نطاق القرب</span><b>'+(tu.proximity_pct*100).toFixed(1)+'%</b></div>'
    + '<div class="kv"><span>ستوك صارم</span><b>'+(tu.strict_stoch?'نعم':'لا')+'</b></div>'
    + '<div class="kv"><span>فوز آخر 10</span><b>'+(tu.winrate||'غير كافٍ')+'</b></div>';
  const hist = await api('/api/tuner-history');
  const th = document.getElementById('tunerH');
  const bar = document.getElementById('tunerBar');
  if(hist && hist.length){
    th.innerHTML = hist.map(w=>'<span class="tag '+(w?'win':'loss')+'" style="width:26px;text-align:center">'+(w?'✓':'✗')+'</span>').join(' ');
    bar.innerHTML = hist.map(w=>'<div style="flex:1;background:'+(w?'#10b981':'#ef4444')+'"></div>').join('');
  } else { th.innerHTML='<div class="empty">لا نتائج بعد</div>'; bar.innerHTML=''; }

  const er = await api('/api/errors');
  const eb = document.getElementById('errBox');
  const ek = Object.keys(er.errors||{});
  if(!ek.length){ eb.innerHTML='<div class="empty" style="padding:16px">✅ لا أخطاء — كل شيء نظيف</div>'; }
  else{ eb.innerHTML = ek.map(k=>'<div class="kv"><span>'+esc(k)+'</span><b style="color:var(--orange)">×'+er.errors[k]+'</b></div>').join(''); }

  document.getElementById('setBox').innerHTML =
    '<div class="kv"><span>الوضع</span><b>'+mode+'</b></div>'
    + '<div class="kv"><span>Testnet</span><b>'+(ov.testnet?'🧪 نعم':'لا — حقيقي')+'</b></div>'
    + '<div class="kv"><span>الرافعة</span><b>'+ov.leverage+'x</b></div>'
    + '<div class="kv"><span>الهامش</span><b>$'+ov.trade_size+'</b></div>'
    + '<div class="kv"><span>النوشنال</span><b>$'+(ov.trade_size*ov.leverage)+'</b></div>'
    + '<div class="kv"><span>المتزامنة</span><b>'+ov.max_open+'</b></div>'
    + '<div class="kv"><span>أزواج محملة</span><b>'+ov.pairs+'</b></div>';

  const pb = document.getElementById('pauseBtn');
  pb.textContent = ov.trade_enabled ? '⏸️ إيقاف مؤقت' : '▶️ استئناف';
}

function renderOpen(tr, boxId){
  const box = document.getElementById(boxId);
  if(!tr || !tr.length){ box.innerHTML = '<div class="empty">لا صفقات مفتوحة — القناص يراقب</div>'; return; }
  let h = '<table><tr><th>الزوج</th><th>اتجاه</th><th>الدخول</th><th>الحالي</th><th>العائم</th><th>الوقف</th><th>الحالة</th></tr>';
  tr.forEach(t=>{
    h += '<tr><td><b>'+t.symbol+'</b></td>'
      + '<td><span class="tag '+(t.side==='BUY'?'buy':'sell')+'">'+(t.side==='BUY'?'شراء':'بيع')+'</span></td>'
      + '<td>'+t.entry+'</td><td>'+(t.current!==null?t.current:'—')+'</td>'
      + '<td class="'+((t.pnl||0)>=0?'pos':'neg')+'"><b>'+(t.pnl===null?'—':mo(t.pnl))+'</b></td>'
      + '<td>'+t.sl+'</td>'
      + '<td>'+(t.partial?'<span class="tag info">🎯 جُني+تريلينق</span>':'<span class="tag open">⏳ جارية</span>')+'</td></tr>';
  });
  box.innerHTML = h + '</table>';
}

async function togglePause(){
  try{
    const ov = await api('/api/overview');
    await fetch(ov.trade_enabled ? '/api/pause' : '/api/resume', {method:'POST'});
    loadAll();
  }catch(e){ alert('فشل: '+e.message); }
}
async function closeAll(){
  if(!confirm('⚠️ إغلاق كل الصفقات فوراً بسعر السوق؟')) return;
  try{
    const r = await (await fetch('/api/close-all',{method:'POST'})).json();
    alert('أُغلق: ' + (r.closed.length ? r.closed.join(', ') : 'لا شيء'));
    loadAll();
  }catch(e){ alert('فشل: '+e.message); }
}

/* ✅ التشغيل: فوري + فشل مرئي بلا دائرة أبدية */
async function boot(){
  try{
    await loadAll();
  }catch(e){
    document.querySelector('.sbar').innerHTML =
      '⚠️ <span style="color:var(--orange)">تعذر جلب البيانات: '+esc(e.message)+' — إعادة محاولة كل 5 ثوانٍ</span>';
  }
  if(!timer) timer = setInterval(()=>loadAll().catch(e=>console.error(e)), 10000);
}
boot();
</script>
</body>
</html>"""


# ═══════════════════ Backend ═══════════════════
class PanelDB:
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
    if PANEL_DB:
        await PANEL_DB.add(kind, title, body, level)


def create_app(bot):
    def j(data, status=200):
        return web.json_response(data, status=status,
                                 headers={'Cache-Control': 'no-store'})

    async def index(request):
        return web.Response(text=PAGE, content_type='text/html',
                            headers={'Cache-Control': 'no-store, must-revalidate'})

    async def overview(request):
        today = time.strftime('%Y-%m-%d')
        row = await bot.db.get_day_stats(today)
        newest = max((p.get('ts', 0) for p in bot.live_prices.values()), default=0)
        balance = bot._balance_cache[0] if bot._balance_cache[1] > 0 else 0.0
        tuner = bot.tuner
        wr = tuner.recent_winrate(10)
        return j({
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

    async def refresh_balance(request):
        try:
            balance = await bot.get_available_usdt()
        except Exception:
            balance = 0.0
        return j({'ok': True, 'balance': round(balance, 2)})

    async def trades(request):
        out = []
        for symbol, t in list(bot.active_trades.items()):
            prices = bot.get_price(symbol)
            cur = pnl = None
            if prices:
                cur = prices['bid'] if t['side'] == 'BUY' else prices['ask']
                diff = (cur - t['entry_price']) if t['side'] == 'BUY' else (t['entry_price'] - cur)
                pnl = diff * t['quantity'] + t.get('realized_pnl', 0.0)
            out.append({
                'symbol': symbol, 'side': t['side'], 'entry': round(t['entry_price'], 6),
                'current': round(cur, 6) if cur else None,
                'pnl': round(pnl, 4) if pnl is not None else None,
                'sl': round(t['sl'], 6),
                'partial': bool(t.get('partial_closed', False)),
            })
        return j(out)

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
                        'score': r['score'],
                    })
        except Exception:
            pass
        return j(out)

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
                        'result': r['result'],
                        'pnl': round(r['pnl'], 4) if r['pnl'] is not None else None,
                    })
        except Exception:
            pass
        return j(out)

    async def notifications(request):
        after = int(request.query.get('after', 0))
        if PANEL_DB:
            return j(await PANEL_DB.get_after(after))
        return j({'items': [], 'last_id': after, 'total_unread': 0})

    async def tuner_history(request):
        return j(list(bot.tuner.results))

    async def errors(request):
        return j({'errors': dict(bot.error_counts)})

    async def pause(request):
        bot.TRADE_ENABLED = False
        return j({'ok': True})

    async def resume(request):
        if not bot.binance_api_key:
            return j({'ok': False, 'error': 'مفاتيح API ناقصة'}, status=400)
        bot.TRADE_ENABLED = True
        return j({'ok': True})

    async def close_all(request):
        closed = []
        for symbol, t in list(bot.active_trades.items()):
            prices = bot.get_price(symbol)
            px = (prices['bid'] if t['side'] == 'BUY' else prices['ask']) if prices else t['entry_price']
            ok, fill, pnl_over = await bot._close_position(t, px)
            if ok:
                await bot._finalize_trade(t, fill, 'إغلاق طارئ من اللوحة', pnl_over)
                closed.append(symbol)
        return j({'ok': True, 'closed': closed})

    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/api/overview', overview)
    app.router.add_get('/api/balance', refresh_balance)
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
    try:
        PANEL_DB = PanelDB(bot.db.db_name)
        await PANEL_DB.init()
        app = create_app(bot)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get('PORT', '8080'))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f'🖥️ لوحة القناص V9 تعمل على المنفذ {port} — دخول مباشر')
        return True
    except Exception as e:
        print(f'⚠️ فشل اللوحة (البوت يكمل عمله): {e}')
        return False
