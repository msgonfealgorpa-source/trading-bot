"""
🖥️ Sniper Admin Panel V9.2
✅ دخول بمفتاح الأدمن (ADMIN_KEY من متغيرات البيئة — يُضبط في Railway)
✅ تصميم احترافي عصري: شريط جانبي + بطاقات زجاجية + إشعارات Toast
✅ مراقبة شاملة: كل ما يفعله البوت (مسح/صفقات/إشارات/أخطاء/مطوّر/أداء)
✅ إجراءات فعلية من اللوحة: إيقاف/استئناف، إغلاق صفقة/الكل، مزامنة الستوبات،
   مصالحة ذاتية، تعديل الإعدادات والمطوّر — كلها تُسجّل في سجل الأحداث
"""

import os
import hmac
import json
import time
import aiosqlite
from aiohttp import web

PANEL_START = time.time()
ADMIN_KEY = os.environ.get('ADMIN_KEY', '').strip()

NOTIFY_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, kind TEXT, title TEXT, body TEXT, level TEXT
)"""

# ═══════════════════ صفحة الدخول ═══════════════════
LOGIN_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔐 دخول الأدمن — القناص</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Tajawal',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0a0f1a;overflow:hidden}
.bg{position:fixed;inset:0;background:
radial-gradient(ellipse at 25% 25%,rgba(0,212,170,.12) 0%,transparent 55%),
radial-gradient(ellipse at 75% 75%,rgba(139,92,246,.12) 0%,transparent 55%);pointer-events:none}
.card{position:relative;background:rgba(17,24,39,.85);backdrop-filter:blur(20px);
border:1px solid rgba(255,255,255,.08);border-radius:24px;padding:44px 40px;width:380px;
box-shadow:0 25px 80px rgba(0,0,0,.55);animation:up .5s ease}
@keyframes up{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:translateY(0)}}
.lock{width:72px;height:72px;margin:0 auto 20px;border-radius:20px;display:flex;align-items:center;justify-content:center;
font-size:34px;background:linear-gradient(135deg,#00d4aa,#0e9488);box-shadow:0 10px 30px rgba(0,212,170,.35)}
h1{text-align:center;font-size:22px;margin-bottom:6px;color:#f1f5f9}
p.sub{text-align:center;color:#94a3b8;font-size:13px;margin-bottom:26px}
.inp{width:100%;padding:14px 16px;background:rgba(10,15,26,.8);border:1px solid #2d3748;border-radius:12px;
color:#f1f5f9;font-family:inherit;font-size:15px;letter-spacing:2px;text-align:center;transition:.25s;outline:none}
.inp:focus{border-color:#00d4aa;box-shadow:0 0 0 3px rgba(0,212,170,.15)}
.btn{width:100%;margin-top:16px;padding:14px;border:none;border-radius:12px;font-family:inherit;font-weight:800;font-size:15px;
cursor:pointer;background:linear-gradient(135deg,#00d4aa,#0e9488);color:#fff;transition:.25s}
.btn:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(0,212,170,.3)}
.btn:active{transform:translateY(0)}
.err{display:none;margin-top:14px;padding:11px;border-radius:10px;background:rgba(239,68,68,.12);
border:1px solid rgba(239,68,68,.35);color:#fca5a5;font-size:13px;text-align:center}
.foot{margin-top:24px;text-align:center;color:#64748b;font-size:11px}
</style>
</head>
<body>
<div class="bg"></div>
<div class="card">
  <div class="lock">🎯</div>
  <h1>القناص الأسطوري</h1>
  <p class="sub">منطقة الأدمن — أدخل مفتاح الدخول للمتابعة</p>
  <input class="inp" id="key" type="password" placeholder="••••••••••••" autofocus
         onkeydown="if(event.key==='Enter')doLogin()">
  <button class="btn" onclick="doLogin()">🔓 دخول</button>
  <div class="err" id="err">❌ مفتاح غير صحيح — حاول مجدداً</div>
  <div class="foot">🔥 Sniper Panel V9.2 — الوصول مقيّد</div>
</div>
<script>
async function doLogin(){
  const k = document.getElementById('key').value.trim();
  if(!k) return;
  try{
    const r = await fetch('/api/auth',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:k})});
    const d = await r.json();
    if(d.ok){
      localStorage.setItem('snip_admin_key', k);
      location.reload();
    } else {
      document.getElementById('err').style.display='block';
    }
  }catch(e){
    document.getElementById('err').textContent='⚠️ تعذر الاتصال: '+e.message;
    document.getElementById('err').style.display='block';
  }
}
</script>
</body>
</html>"""

# ═══════════════════ صفحة اللوحة ═══════════════════
PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎯 لوحة أدمن القناص V9.2</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0f1a;--bg2:#0f1522;--card:#131b2c;--card2:#182136;--bord:rgba(255,255,255,.07);
--txt:#f1f5f9;--sub:#8b9bb4;--green:#00d4aa;--blue:#3b82f6;--purple:#8b5cf6;
--orange:#f97316;--red:#ef4444;--yellow:#eab308}
body{font-family:'Tajawal',sans-serif;background:var(--bg);color:var(--txt);min-height:100vh}
.hidden{display:none!important}
.bgfx{position:fixed;inset:0;background:
radial-gradient(ellipse at 15% 10%,rgba(0,212,170,.06) 0%,transparent 50%),
radial-gradient(ellipse at 85% 90%,rgba(139,92,246,.06) 0%,transparent 50%);pointer-events:none;z-index:0}
/* ── الهيكل: شريط جانبي ── */
.wrap{position:relative;z-index:1;display:flex;min-height:100vh}
.side{width:230px;flex-shrink:0;background:var(--bg2);border-left:1px solid var(--bord);
padding:18px 14px;display:flex;flex-direction:column;gap:6px;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:11px;padding:6px 8px 18px;border-bottom:1px solid var(--bord);margin-bottom:14px}
.brand-ic{width:42px;height:42px;border-radius:13px;background:linear-gradient(135deg,#00d4aa,#0e9488);
display:flex;align-items:center;justify-content:center;font-size:21px;box-shadow:0 8px 20px rgba(0,212,170,.3)}
.brand h1{font-size:17px}
.brand span{font-size:10.5px;color:var(--sub)}
.nav{display:flex;flex-direction:column;gap:5px;flex:1}
.nvi{display:flex;align-items:center;gap:11px;padding:12px 14px;border:none;background:transparent;
color:var(--sub);font-family:inherit;font-size:14px;font-weight:600;border-radius:12px;cursor:pointer;
transition:.2s;text-align:right;width:100%}
.nvi:hover{background:rgba(255,255,255,.04);color:var(--txt)}
.nvi.act{background:linear-gradient(135deg,rgba(0,212,170,.16),rgba(0,212,170,.05));
color:var(--green);box-shadow:inset 3px 0 0 var(--green)}
.nvi .bdg{margin-right:auto;background:rgba(59,130,246,.2);color:#93c5fd;font-size:10.5px;
padding:2px 8px;border-radius:20px;font-weight:700}
.side-ft{font-size:10.5px;color:#4b5a72;text-align:center;padding-top:12px;border-top:1px solid var(--bord)}
.main{flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:50;background:rgba(10,15,26,.85);backdrop-filter:blur(14px);
border-bottom:1px solid var(--bord);padding:13px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.topbar h2{font-size:18px}
.tb-sp{flex:1}
.badge{display:flex;align-items:center;gap:8px;padding:8px 15px;border-radius:50px;font-size:12.5px;font-weight:700}
.badge.on{background:rgba(0,212,170,.12);border:1px solid rgba(0,212,170,.3);color:var(--green)}
.badge.off{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:var(--red)}
.dot{width:8px;height:8px;border-radius:50%;background:currentColor;animation:pl 2s infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.35}}
button{font-family:inherit}
.abtn{padding:9px 16px;border-radius:10px;font-weight:700;font-size:12.5px;cursor:pointer;border:none;transition:.2s}
.abtn:hover{transform:translateY(-1px)}
.a-g{background:linear-gradient(135deg,#00d4aa,#0e9488);color:#fff}
.a-o{background:rgba(249,115,22,.14);color:#fdba74;border:1px solid rgba(249,115,22,.35)}
.a-r{background:rgba(239,68,68,.14);color:#fca5a5;border:1px solid rgba(239,68,68,.35)}
.a-s{background:rgba(255,255,255,.06);color:var(--sub);border:1px solid var(--bord)}
.content{padding:22px;max-width:1250px;width:100%;margin:0 auto}
.tc{display:none}
.tc.act{display:block;animation:fi .3s}
@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
/* ── بطاقات ── */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(195px,1fr));gap:14px;margin-bottom:18px}
.card{background:linear-gradient(160deg,var(--card),var(--bg2));border:1px solid var(--bord);border-radius:18px;
padding:19px;position:relative;overflow:hidden;transition:.3s}
.card:hover{transform:translateY(-3px);border-color:rgba(0,212,170,.3);box-shadow:0 14px 35px rgba(0,0,0,.35)}
.card::before{content:'';position:absolute;top:-35px;left:-35px;width:110px;height:110px;border-radius:50%;filter:blur(45px);opacity:.16}
.card.g::before{background:var(--green)}.card.b::before{background:var(--blue)}.card.p::before{background:var(--purple)}
.card.o::before{background:var(--orange)}.card.y::before{background:var(--yellow)}.card.r::before{background:var(--red)}
.card .l{font-size:12.5px;color:var(--sub);display:flex;align-items:center;gap:7px}
.card .v{font-size:28px;font-weight:800;margin:8px 0 3px}
.card .s{font-size:11px;color:var(--sub);padding-top:8px;border-top:1px solid var(--bord);margin-top:8px}
.card.g .v{color:var(--green)}.card.b .v{color:#93c5fd}.card.p .v{color:#c4b5fd}
.card.o .v{color:#fdba74}.card.y .v{color:#fde68a}.card.r .v{color:#fca5a5}
.pos{color:var(--green)!important}.neg{color:var(--red)!important}
.sec{background:linear-gradient(160deg,var(--card),var(--bg2));border:1px solid var(--bord);
border-radius:18px;padding:20px;margin-bottom:18px}
.sec-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:15px;flex-wrap:wrap;gap:10px}
.sec-h h3{font-size:15.5px}
.sec-h .hint{font-size:11.5px;color:var(--sub)}
table{width:100%;border-collapse:collapse}
th{text-align:right;padding:9px 8px;color:var(--sub);font-size:11px;border-bottom:1px solid var(--bord);font-weight:600}
td{padding:11px 8px;font-size:13px;border-bottom:1px solid rgba(255,255,255,.04)}
tr:hover td{background:rgba(0,212,170,.03)}
.xbtn{padding:6px 12px;border-radius:8px;font-size:11.5px;font-weight:700;cursor:pointer;
background:rgba(239,68,68,.12);color:#fca5a5;border:1px solid rgba(239,68,68,.3);transition:.2s}
.xbtn:hover{background:rgba(239,68,68,.25)}
.tag{padding:3px 10px;border-radius:7px;font-size:11px;font-weight:700;display:inline-block}
.tag.buy{background:rgba(0,212,170,.14);color:var(--green)}
.tag.sell{background:rgba(239,68,68,.14);color:#fca5a5}
.tag.win{background:rgba(16,185,129,.14);color:#34d399}
.tag.loss{background:rgba(239,68,68,.14);color:#fca5a5}
.tag.open{background:rgba(234,179,8,.14);color:#fde68a}
.tag.info{background:rgba(59,130,246,.14);color:#93c5fd}
.empty{text-align:center;color:var(--sub);padding:28px;font-size:13.5px}
/* ── سجل الأحداث ── */
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{padding:6px 14px;border-radius:20px;font-size:12px;font-weight:700;cursor:pointer;
background:rgba(255,255,255,.05);border:1px solid var(--bord);color:var(--sub);transition:.2s}
.chip.act{background:rgba(0,212,170,.15);border-color:rgba(0,212,170,.4);color:var(--green)}
.feed{display:flex;flex-direction:column;gap:9px;max-height:580px;overflow-y:auto;padding-left:4px}
.nt{display:flex;gap:12px;padding:13px 14px;background:var(--card2);border-radius:13px;
border-right:4px solid transparent;animation:fi .3s}
.nt.trade{border-right-color:var(--green)}.nt.partial{border-right-color:var(--blue)}
.nt.close{border-right-color:var(--purple)}.nt.error{border-right-color:var(--red)}
.nt.tuner{border-right-color:var(--orange)}.nt.info{border-right-color:#64748b}
.nt.system{border-right-color:var(--yellow)}
.nt-ic{width:37px;height:37px;border-radius:11px;display:flex;align-items:center;justify-content:center;
font-size:16px;flex-shrink:0;background:rgba(255,255,255,.05)}
.nt-b{flex:1;min-width:0}
.nt-t{font-size:13.5px;font-weight:700;margin-bottom:3px}
.nt-x{font-size:12px;color:var(--sub);line-height:1.65;white-space:pre-wrap;word-break:break-word}
.nt-tm{font-size:10px;color:#5b6b85;direction:ltr;text-align:right;margin-top:5px}
/* ── صحة ── */
.hg{display:flex;flex-direction:column;gap:9px}
.hi{display:flex;align-items:center;gap:12px;background:var(--card2);padding:12px 14px;border-radius:12px}
.hd2{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.hd2.ok{background:#10b981;box-shadow:0 0 10px rgba(16,185,129,.5)}
.hd2.bad{background:var(--red);box-shadow:0 0 10px rgba(239,68,68,.5)}
.hd2.warn{background:var(--yellow)}
.hn{font-size:13px;font-weight:600}
.hs{font-size:11px;color:var(--sub)}
.kv{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:13.5px}
.kv:last-child{border:none}
.kv b{color:var(--green)}
.kv b.neg{color:var(--red)}
.bar{display:flex;height:7px;border-radius:4px;overflow:hidden;margin-top:12px;background:var(--bg2);gap:2px}
.bar div{flex:1}
/* ── نماذج ── */
.frm{display:flex;flex-direction:column;gap:13px}
.frow{display:flex;align-items:center;justify-content:space-between;gap:14px}
.frow label{font-size:13px;color:var(--sub);font-weight:600}
.finp{width:170px;padding:10px 13px;background:var(--bg2);border:1px solid var(--bord);border-radius:10px;
color:var(--txt);font-family:inherit;font-size:13.5px;outline:none;transition:.2s;text-align:center}
.finp:focus{border-color:var(--green);box-shadow:0 0 0 3px rgba(0,212,170,.12)}
.tgl{position:relative;width:46px;height:25px;background:var(--bord);border-radius:20px;cursor:pointer;transition:.25s;flex-shrink:0}
.tgl.on{background:var(--green)}
.tgl::after{content:'';position:absolute;top:3px;right:3px;width:19px;height:19px;border-radius:50%;
background:#fff;transition:.25s}
.tgl.on::after{transform:translateX(-21px)}
.abtns{display:flex;gap:9px;flex-wrap:wrap}
.statline{display:flex;gap:22px;flex-wrap:wrap;margin-bottom:16px;font-size:12.5px;color:var(--sub)}
.statline b{color:var(--txt)}
/* ── Toast ── */
#toasts{position:fixed;bottom:20px;right:20px;z-index:999;display:flex;flex-direction:column;gap:9px}
.toast{padding:13px 18px;border-radius:13px;font-size:13px;font-weight:700;max-width:330px;
animation:tin .3s;box-shadow:0 12px 35px rgba(0,0,0,.45);border-right:4px solid}
.toast.ok{background:#0c2b24;border-color:#10b981;color:#6ee7b7}
.toast.err{background:#2b0f14;border-color:#ef4444;color:#fca5a5}
.toast.inf{background:#101b2e;border-color:#3b82f6;color:#93c5fd}
@keyframes tin{from{opacity:0;transform:translateX(30px)}to{opacity:1;transform:translateX(0)}}
.sbar{background:var(--card2);border:1px solid var(--bord);border-radius:12px;padding:10px 16px;
margin-bottom:16px;display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--sub);flex-wrap:wrap}
.sbar b{color:var(--green)}
@media(max-width:900px){
.side{width:66px;padding:14px 8px}
.brand div,.nvi span,.side-ft{display:none}
.nvi{justify-content:center;padding:13px}
.nvi .bdg{display:none}
.card .v{font-size:23px}
}
</style>
</head>
<body>
<div class="bgfx"></div>

<div class="wrap">
  <!-- ══ الشريط الجانبي ══ -->
  <aside class="side">
    <div class="brand">
      <div class="brand-ic">🎯</div>
      <div><h1>القناص الأسطوري</h1><span>لوحة الأدمن V9.2</span></div>
    </div>
    <nav class="nav">
      <button class="nvi act" onclick="sw('overview',this)">📊 <span>نظرة عامة</span></button>
      <button class="nvi" onclick="sw('trades',this)">📂 <span>الصفقات</span></button>
      <button class="nvi" onclick="sw('signals',this)">📡 <span>الإشارات</span></button>
      <button class="nvi" onclick="sw('performance',this)">📅 <span>الأداء اليومي</span></button>
      <button class="nvi" onclick="sw('tuner',this)">🧠 <span>المطوّر التكيفي</span></button>
      <button class="nvi" onclick="sw('system',this)">⚙️ <span>النظام والتحكم</span></button>
    </nav>
    <div class="side-ft">🔥 Sniper Panel V9.2<br>حماية بمفتاح الأدمن</div>
  </aside>

  <!-- ══ المحتوى ══ -->
  <div class="main">
    <header class="topbar">
      <h2 id="pageTitle">📊 نظرة عامة</h2>
      <div class="tb-sp"></div>
      <div class="badge on" id="liveB"><span class="dot"></span><span id="liveT">البوت حي ✓</span></div>
      <button class="abtn a-g" onclick="loadAll(true)">🔄 تحديث</button>
      <button class="abtn a-s" id="logoutBtn" onclick="doLogout()" title="تسجيل الخروج">🚪</button>
    </header>

    <div class="content">
      <div class="sbar">⏱️ آخر تحديث: <b id="lastUpd">—</b> • تحديث تلقائي كل 10 ثوانٍ • 🔒 جلسة أدمن آمنة</div>

      <!-- ══ نظرة عامة ══ -->
      <div class="tc act" id="t-overview">
        <div class="statline">
          <span>⚙️ الوضع: <b id="ovMode">—</b></span>
          <span>🔍 آخر مسح: <b id="ovScan">—</b></span>
          <span>⏱️ مدة التشغيل: <b id="ovUp">—</b></span>
        </div>
        <div class="grid">
          <div class="card g"><div class="l">💵 الرصيد المتاح</div><div class="v" id="balance">$0</div><div class="s" id="modeSub">—</div></div>
          <div class="card b"><div class="l">📈 ربح/خسارة اليوم</div><div class="v" id="dayPnl">$0</div><div class="s" id="dayWl">—</div></div>
          <div class="card p"><div class="l">🏆 نسبة الفوز الإجمالية</div><div class="v" id="wrAll">—</div><div class="s" id="allWl">—</div></div>
          <div class="card o"><div class="l">📂 صفقات مفتوحة</div><div class="v" id="openC">0</div><div class="s" id="scanT">—</div></div>
          <div class="card y"><div class="l">🧠 فوز آخر 10</div><div class="v" id="wr10">—</div><div class="s" id="tunerS">—</div></div>
        </div>
        <div class="grid" style="grid-template-columns:1.6fr 1fr">
          <div class="sec"><div class="sec-h"><h3>📂 الصفقات المفتوحة الآن</h3><span class="hint">ربح/خسارة حيّة من السوق</span></div><div id="openBox"></div></div>
          <div class="sec"><div class="sec-h"><h3>🛡️ صحة النظام</h3></div><div class="hg" id="healthBox">—</div></div>
        </div>
        <div class="sec">
          <div class="sec-h"><h3>🔔 سجل الأحداث المباشر</h3>
            <div class="chips" id="ovChips">
              <button class="chip act" onclick="setFeedFilter('all',this)">الكل</button>
              <button class="chip" onclick="setFeedFilter('trade',this)">صفقات</button>
              <button class="chip" onclick="setFeedFilter('error',this)">أخطاء</button>
              <button class="chip" onclick="setFeedFilter('info',this)">نظام</button>
            </div>
          </div>
          <div class="feed" id="liveFeed" style="max-height:340px"></div>
        </div>
      </div>

      <!-- ══ الصفقات ══ -->
      <div class="tc" id="t-trades">
        <div class="sec"><div class="sec-h"><h3>📂 المفتوحة الآن</h3><span class="hint">زر 🔴 يغلق الصفقة فوراً بسعر السوق</span></div><div id="openBox2"></div></div>
        <div class="sec"><div class="sec-h"><h3>🏁 آخر الصفقات المغلقة</h3></div><div id="closedBox"></div></div>
      </div>

      <!-- ══ الإشارات ══ -->
      <div class="tc" id="t-signals">
        <div class="sec"><div class="sec-h"><h3>📡 سجل الإشارات</h3><span class="hint">كل إشارة مرّت بفلاتر البوت — النتيجة تُحدَّث عند الإغلاق</span></div><div id="sigBox"></div></div>
      </div>

      <!-- ══ الأداء ══ -->
      <div class="tc" id="t-performance">
        <div class="sec"><div class="sec-h"><h3>📅 اليوم الحالي</h3></div><div id="todayBox">—</div></div>
        <div class="sec"><div class="sec-h"><h3>🗓️ آخر 14 يوماً</h3></div><div id="daysBox">—</div></div>
        <div class="sec"><div class="sec-h"><h3>🏆 الإجماليات عبر التاريخ</h3></div><div id="aggBox">—</div></div>
      </div>

      <!-- ══ المطوّر ══ -->
      <div class="tc" id="t-tuner">
        <div class="grid" style="grid-template-columns:1fr 1fr">
          <div class="sec">
            <div class="sec-h"><h3>🧠 التحكم بالمطوّر التكيفي</h3></div>
            <div class="frm">
              <div class="frow"><label>الحد الأدنى للتقييم (6-8)</label>
                <input class="finp" id="tMinScore" type="number" min="6" max="8" step="1"></div>
              <div class="frow"><label>نسبة القرب من OB (1.5% - 4.5%)</label>
                <input class="finp" id="tProx" type="number" min="1.5" max="4.5" step="0.5"></div>
              <div class="frow"><label>ستوكاستك صارم</label>
                <div class="tgl" id="tStoch" onclick="this.classList.toggle('on')"></div></div>
              <button class="abtn a-g" style="align-self:flex-start" onclick="saveTuner()">💾 حفظ إعدادات المطوّر</button>
            </div>
          </div>
          <div class="sec">
            <div class="sec-h"><h3>📈 آخر 20 نتيجة</h3></div>
            <div id="tunerH">—</div><div class="bar" id="tunerBar"></div>
            <div style="margin-top:14px" id="tunerLive"></div>
          </div>
        </div>
      </div>

      <!-- ══ النظام ══ -->
      <div class="tc" id="t-system">
        <div class="grid" style="grid-template-columns:1fr 1fr">
          <div>
            <div class="sec">
              <div class="sec-h"><h3>⚙️ إعدادات التداول</h3><span class="hint">تُطبَّق فوراً على الدورات القادمة</span></div>
              <div class="frm">
                <div class="frow"><label>الهامش لكل صفقة ($)</label>
                  <input class="finp" id="sTradeSize" type="number" min="1" max="1000" step="1"></div>
                <div class="frow"><label>أقصى صفقات متزامنة (1-10)</label>
                  <input class="finp" id="sMaxOpen" type="number" min="1" max="10" step="1"></div>
                <button class="abtn a-g" style="align-self:flex-start" onclick="saveSettings()">💾 حفظ الإعدادات</button>
              </div>
              <div style="margin-top:16px" id="setBox"></div>
            </div>
            <div class="sec">
              <div class="sec-h"><h3>⚡ إجراءات فورية</h3></div>
              <div class="abtns">
                <button class="abtn a-s" onclick="act('refresh-balance','تم تحديث الرصيد',true)">💵 تحديث الرصيد</button>
                <button class="abtn a-s" onclick="syncStops()">🛡️ مزامنة الستوبات</button>
                <button class="abtn a-s" onclick="act('reconcile','بدأت المصالحة الذاتية',false)">🧾 مصالحة ذاتية</button>
                <button class="abtn a-o" id="pauseBtn" onclick="togglePause()">⏸️ إيقاف مؤقت</button>
                <button class="abtn a-r" onclick="closeAll()">🛑 إغلاق كل الصفقات</button>
              </div>
              <p style="color:var(--sub);font-size:11.5px;margin-top:12px;line-height:1.7">
              ℹ️ الستوبات على المنصة تبقى فعالة دائماً وتحمي المراكز حتى عند إيقاف التداول.<br>
              ⚠️ كل إجراء يُسجَّل في سجل الأحداث ولا يمكن التراجع عنه.</p>
            </div>
          </div>
          <div>
            <div class="sec"><div class="sec-h"><h3>🚨 سجل الأخطاء الحالية</h3></div><div id="errBox">—</div></div>
            <div class="sec"><div class="sec-h"><h3>🔔 آخر الأحداث</h3></div><div class="feed" id="sysFeed" style="max-height:400px"></div></div>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>

<div id="toasts"></div>

<script>
const PAGE_TITLES = {overview:'📊 نظرة عامة', trades:'📂 الصفقات', signals:'📡 الإشارات',
performance:'📅 الأداء اليومي', tuner:'🧠 المطوّر التكيفي', system:'⚙️ النظام والتحكم'};
let lastNid = 0, feedFilter = 'all', allNotifs = [], timer = null;

function key(){ return localStorage.getItem('snip_admin_key') || ''; }
function doLogout(){ localStorage.removeItem('snip_admin_key'); location.reload(); }

async function api(path, opts){
  opts = opts || {};
  opts.headers = Object.assign({'X-Admin-Key': key()}, opts.headers||{});
  if(opts.body && typeof opts.body === 'object'){
    opts.headers['Content-Type']='application/json';
    opts.body = JSON.stringify(opts.body);
  }
  const c = new AbortController();
  const t = setTimeout(()=>c.abort(), 8000);
  try{
    const res = await fetch(path, Object.assign({signal:c.signal, cache:'no-store'}, opts));
    if(res.status === 401){ localStorage.removeItem('snip_admin_key'); location.reload(); throw new Error('انتهت الجلسة'); }
    if(!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  }finally{ clearTimeout(t); }
}

function toast(msg, kind){
  kind = kind || 'ok';
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(()=>{ el.style.opacity='0'; el.style.transition='opacity .4s'; setTimeout(()=>el.remove(), 400); }, 3800);
}

function sw(name, el){
  document.querySelectorAll('.tc').forEach(x=>x.classList.remove('act'));
  document.querySelectorAll('.nvi').forEach(x=>x.classList.remove('act'));
  document.getElementById('t-'+name).classList.add('act');
  el.classList.add('act');
  document.getElementById('pageTitle').textContent = PAGE_TITLES[name] || '';
}
function mo(v){return (v>=0?'+':'−') + '$' + Math.abs(v).toFixed(2)}
function sg(v,d){d=d||1;return (v>=0?'+':'−') + v.toFixed(d)}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function ago(ts){ const s=Math.max(0,Math.floor(Date.now()/1000 - ts)); if(s<60) return s+' ث'; if(s<3600) return Math.floor(s/60)+' د'; return Math.floor(s/3600)+' س'; }

const KM = {trade:['trade','🟢'],partial:['partial','🎯'],close:['close','🏁'],
error:['error','🚨'],tuner:['tuner','🧠'],info:['info','ℹ️'],system:['system','⚙️']};

function notifHtml(n){
  const k = KM[n.kind] || KM.info;
  return '<div class="nt '+k[0]+'"><div class="nt-ic">'+k[1]+'</div>'
    + '<div class="nt-b"><div class="nt-t">'+esc(n.title)+'</div>'
    + (n.body?'<div class="nt-x">'+esc(n.body)+'</div>':'')
    + '<div class="nt-tm">'+n.time+'</div></div></div>';
}
function renderFeed(){
  const items = allNotifs.filter(n => feedFilter==='all'
    || (feedFilter==='trade' && ['trade','partial','close'].includes(n.kind))
    || (feedFilter==='error' && n.kind==='error')
    || (feedFilter==='info' && ['info','system','tuner'].includes(n.kind)));
  const h = items.slice(0, 60).map(notifHtml).join('') || '<div class="empty">لا أحداث بعد</div>';
  document.getElementById('liveFeed').innerHTML = h;
  document.getElementById('sysFeed').innerHTML = h;
}
function setFeedFilter(f, el){
  feedFilter = f;
  document.querySelectorAll('#ovChips .chip').forEach(c=>c.classList.remove('act'));
  el.classList.add('act');
  renderFeed();
}

async function loadAll(manual){
  const ov = await api('/api/overview');
  document.getElementById('lastUpd').textContent =
    new Date().toLocaleTimeString('ar',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  document.getElementById('balance').textContent = '$' + (+ov.balance).toFixed(2);
  const mode = ov.trade_enabled ? (ov.testnet ? '⚔️ تداول تجريبي 🧪' : '⚔️ تداول حقيقي') : '👁️ مراقبة فقط';
  document.getElementById('ovMode').textContent = mode;
  document.getElementById('ovUp').textContent = ov.uptime + ' دقيقة';
  document.getElementById('modeSub').textContent = ov.leverage+'x • $'+ov.trade_size+' • '+ov.pairs+' زوج';
  const ls = ov.last_scan;
  document.getElementById('ovScan').textContent = ls
    ? ('قبل ' + ago(ls.ts) + ' — فحص ' + ls.scanned + ' زوج، ' + ls.signals + ' إشارة')
    : 'لم يبدأ بعد';

  const dp = ov.today ? ov.today.pnl : 0;
  const dEl = document.getElementById('dayPnl');
  dEl.textContent = mo(dp); dEl.className = 'v ' + (dp>=0?'pos':'neg');
  document.getElementById('dayWl').textContent = ov.today ? (ov.today.wins+'W / '+ov.today.losses+'L') : '—';

  const tot = ov.stats.wins + ov.stats.losses;
  document.getElementById('wrAll').textContent = tot ? Math.round(ov.stats.wins/tot*100)+'%' : '—';
  document.getElementById('allWl').textContent = ov.stats.wins+'W / '+ov.stats.losses+'L';
  document.getElementById('openC').textContent = ov.open_trades;
  document.getElementById('scanT').textContent = 'دورات: '+ov.scans+' • جدولة: 60 ث';
  document.getElementById('wr10').textContent = ov.tuner.winrate || '—';
  document.getElementById('tunerS').textContent = 'عتبة: '+ov.tuner.min_score+'/8';

  const lv = ov.price_age < 120;
  document.getElementById('liveB').className = 'badge ' + (lv?'on':'off');
  document.getElementById('liveT').textContent = lv ? 'البوت حي ✓' : 'توقف الأسعار!';
  document.getElementById('pauseBtn').textContent = ov.trade_enabled ? '⏸️ إيقاف مؤقت' : '▶️ استئناف التداول';

  document.getElementById('healthBox').innerHTML = [
    ['تدفق الأسعار (WebSocket)', lv ? 'متصل ✓' : 'متوقف '+ov.price_age+'ث', lv?'ok':'bad'],
    ['ستوبات المنصة', ov.open_trades>0 ? 'مفعّلة لكل مركز' : 'لا مراكز مفتوحة', 'ok'],
    ['الرصيد المتاح', '$'+(+ov.balance).toFixed(2), ov.balance>=ov.trade_size?'ok':'warn'],
    ['الوضع الحالي', mode, ov.trade_enabled?'ok':'warn'],
    ['أخطاء متراكمة', ov.error_total + ' نوع', ov.error_total>0?'warn':'ok'],
  ].map(h=>'<div class="hi"><div class="hd2 '+h[2]+'"></div><div><div class="hn">'+h[0]+'</div><div class="hs">'+h[1]+'</div></div></div>').join('');

  /* نماذج — تعبئة القيم الحالية */
  document.getElementById('tMinScore').value = ov.tuner.min_score;
  document.getElementById('tProx').value = (+ov.tuner.proximity_pct*100).toFixed(1);
  const stochTgl = document.getElementById('tStoch');
  stochTgl.classList.toggle('on', !!ov.tuner.strict_stoch);
  document.getElementById('sTradeSize').value = ov.trade_size;
  document.getElementById('sMaxOpen').value = ov.max_open;

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

  /* الأداء اليومي */
  const dper = await api('/api/daily');
  const tB = document.getElementById('todayBox');
  if(tB && dper.today){
    const t = dper.today;
    tB.innerHTML = '<div class="grid" style="margin-bottom:0">'
      + '<div class="card '+(t.pnl>=0?'g':'r')+'"><div class="l">💵 نتيجة اليوم</div><div class="v '+(t.pnl>=0?'pos':'neg')+'">'+mo(t.pnl)+'</div></div>'
      + '<div class="card b"><div class="l">📂 صفقات اليوم</div><div class="v">'+t.total+'</div><div class="s">دخلت اليوم: '+(dper.trades_today_live||0)+'</div></div>'
      + '<div class="card g"><div class="l">✅ رابحة</div><div class="v">'+t.wins+'</div></div>'
      + '<div class="card r"><div class="l">❌ خاسرة</div><div class="v">'+t.losses+'</div></div>'
      + '<div class="card y"><div class="l">🏆 نسبة الفوز</div><div class="v">'+(t.winrate!==null&&t.winrate!==undefined?t.winrate+'%':'—')+'</div></div>'
      + '</div>';
  }
  const dB = document.getElementById('daysBox');
  if(dB){
    if(!dper.days || !dper.days.length){ dB.innerHTML = '<div class="empty">لا سجل أيام بعد</div>'; }
    else{
      let h = '<table><tr><th>اليوم</th><th>النتيجة</th><th>✅ رابحة</th><th>❌ خاسرة</th><th>المجموع</th><th>الفوز</th></tr>';
      dper.days.forEach(d=>{
        h += '<tr><td><b>'+d.date+'</b></td>'
          + '<td class="'+(d.pnl>=0?'pos':'neg')+'"><b>'+mo(d.pnl)+'</b></td>'
          + '<td style="color:var(--green)">'+d.wins+'</td>'
          + '<td style="color:var(--red)">'+d.losses+'</td>'
          + '<td>'+d.total+'</td>'
          + '<td>'+(d.winrate!==null&&d.winrate!==undefined?d.winrate+'%':'—')+'</td></tr>';
      });
      dB.innerHTML = h + '</table>';
    }
  }
  const aB = document.getElementById('aggBox');
  if(aB && dper.aggregates){
    const a = dper.aggregates;
    aB.innerHTML =
      '<div class="kv"><span>أيام نشطة</span><b>'+a.active_days+'</b></div>'
      + '<div class="kv"><span>إجمالي الصفقات المغلقة</span><b>'+a.total_closed+'</b></div>'
      + '<div class="kv"><span>رابحة / خاسرة</span><b>'+a.total_wins+' / '+(a.total_closed - a.total_wins)+'</b></div>'
      + '<div class="kv"><span>نسبة الفوز عبر التاريخ</span><b>'+(a.overall_winrate!==null&&a.overall_winrate!==undefined?a.overall_winrate+'%':'—')+'</b></div>'
      + '<div class="kv"><span>إجمالي الربح/الخسارة</span><b class="'+(a.total_pnl>=0?'pos':'neg')+'">'+mo(a.total_pnl)+'</b></div>'
      + (a.best_day?'<div class="kv"><span>🥇 أفضل يوم</span><b>'+a.best_day.date+' ('+mo(a.best_day.pnl)+')</b></div>':'')
      + (a.worst_day?'<div class="kv"><span>💀 أسوأ يوم</span><b>'+a.worst_day.date+' ('+mo(a.worst_day.pnl)+')</b></div>':'');
  }

  /* الإشعارات */
  const nf = await api('/api/notifications?after='+lastNid);
  if(nf.items && nf.items.length){
    lastNid = nf.last_id || lastNid;
    allNotifs = nf.items.concat(allNotifs.filter(n => !nf.items.find(x => x.id === n.id)));
    renderFeed();
  }

  /* المطوّر */
  const tu = ov.tuner;
  document.getElementById('tunerLive').innerHTML =
    '<div class="kv"><span>الحد الأدنى</span><b>'+tu.min_score+' / 8</b></div>'
    + '<div class="kv"><span>نطاق القرب</span><b>'+(tu.proximity_pct*100).toFixed(1)+'%</b></div>'
    + '<div class="kv"><span>ستوك صارم</span><b>'+(tu.strict_stoch?'نعم':'لا')+'</b></div>';
  const hist = await api('/api/tuner-history');
  const th = document.getElementById('tunerH');
  const bar = document.getElementById('tunerBar');
  if(hist && hist.length){
    th.innerHTML = hist.slice().reverse().map(w=>'<span class="tag '+(w?'win':'loss')+'" style="width:28px;text-align:center">'+(w?'✓':'✗')+'</span>').join(' ');
    bar.innerHTML = hist.map(w=>'<div style="background:'+(w?'#10b981':'#ef4444')+'"></div>').join('');
  } else { th.innerHTML='<div class="empty">لا نتائج بعد</div>'; bar.innerHTML=''; }

  /* الأخطاء */
  const er = await api('/api/errors');
  const eb = document.getElementById('errBox');
  const ek = Object.keys(er.errors||{});
  if(!ek.length){ eb.innerHTML='<div class="empty" style="padding:16px">✅ لا أخطاء — كل شيء نظيف</div>'; }
  else{ eb.innerHTML = ek.map(k=>'<div class="kv"><span>'+esc(k)+'</span><b style="color:var(--orange)">×'+er.errors[k]+'</b></div>').join(''); }

  /* الإعدادات المعروضة */
  document.getElementById('setBox').innerHTML =
    '<div class="kv"><span>الوضع</span><b>'+mode+'</b></div>'
    + '<div class="kv"><span>Testnet</span><b>'+(ov.testnet?'🧪 نعم':'لا — حقيقي')+'</b></div>'
    + '<div class="kv"><span>الرافعة</span><b>'+ov.leverage+'x</b></div>'
    + '<div class="kv"><span>النوشنال</span><b>$'+(ov.trade_size*ov.leverage)+'</b></div>'
    + '<div class="kv"><span>أزواج محملة</span><b>'+ov.pairs+'</b></div>';

  if(manual) toast('✓ تم التحديث', 'ok');
}

function renderOpen(tr, boxId){
  const box = document.getElementById(boxId);
  if(!tr || !tr.length){ box.innerHTML = '<div class="empty">لا صفقات مفتوحة — القناص يراقب 🎯</div>'; return; }
  let h = '<table><tr><th>الزوج</th><th>اتجاه</th><th>الدخول</th><th>الحالي</th><th>العائم</th><th>الوقف</th><th>الحالة</th><th></th></tr>';
  tr.forEach(t=>{
    h += '<tr><td><b>'+t.symbol+'</b></td>'
      + '<td><span class="tag '+(t.side==='BUY'?'buy':'sell')+'">'+(t.side==='BUY'?'شراء':'بيع')+'</span></td>'
      + '<td>'+t.entry+'</td><td>'+(t.current!==null?t.current:'—')+'</td>'
      + '<td class="'+((t.pnl||0)>=0?'pos':'neg')+'"><b>'+(t.pnl===null?'—':mo(t.pnl))+'</b></td>'
      + '<td>'+t.sl+'</td>'
      + '<td>'+(t.partial?'<span class="tag info">🎯 جُني + تريلينق</span>':'<span class="tag open">⏳ جارية</span>')+'</td>'
      + '<td><button class="xbtn" onclick="closeOne(\''+t.symbol+'\')">🔴 إغلاق</button></td></tr>';
  });
  box.innerHTML = h + '</table>';
}

/* ── الإجراءات ── */
async function post(path, body){ return await api(path, {method:'POST', body: body||{}}); }

async function closeOne(symbol){
  if(!confirm('⚠️ إغلاق صفقة '+symbol+' فوراً بسعر السوق؟')) return;
  try{
    const r = await post('/api/close-position', {symbol:symbol});
    if(r.ok){ toast('✅ أُغلقت '+symbol, 'ok'); loadAll(); }
    else toast('❌ فشل: '+(r.error||''), 'err');
  }catch(e){ toast('❌ '+e.message, 'err'); }
}
async function closeAll(){
  if(!confirm('⚠️ إغلاق كل الصفقات فوراً بسعر السوق؟ لا رجوع!')) return;
  try{
    const r = await post('/api/close-all');
    toast(r.closed.length ? '✅ أُغلقت: '+r.closed.join(', ') : 'لا صفقات مفتوحة', r.closed.length?'ok':'inf');
    loadAll();
  }catch(e){ toast('❌ '+e.message, 'err'); }
}
async function togglePause(){
  try{
    const ov = await api('/api/overview');
    const r = await post(ov.trade_enabled ? '/api/pause' : '/api/resume');
    toast(r.ok ? (ov.trade_enabled ? '⏸️ أُوقف التداول — المراقبة مستمرة' : '▶️ استؤنف التداول') : '❌ '+(r.error||''), r.ok?'ok':'err');
    loadAll();
  }catch(e){ toast('❌ '+e.message, 'err'); }
}
async function syncStops(){
  try{
    const r = await post('/api/sync-stops');
    toast('🛡️ مُزامن '+r.synced+' ستوب على المنصة', 'ok');
  }catch(e){ toast('❌ '+e.message, 'err'); }
}
async function act(path, msg, isGet){
  try{
    if(isGet){ await api('/api/'+path); } else { await post('/api/'+path); }
    toast('✓ '+msg, 'ok');
    if(!isGet) loadAll();
  }catch(e){ toast('❌ '+e.message, 'err'); }
}
async function saveTuner(){
  try{
    const r = await post('/api/tuner', {
      min_score: parseInt(document.getElementById('tMinScore').value),
      proximity_pct: parseFloat(document.getElementById('tProx').value),
      strict_stoch: document.getElementById('tStoch').classList.contains('on')
    });
    toast(r.ok ? '🧠 حُفظت إعدادات المطوّر' : '❌ '+(r.error||''), r.ok?'ok':'err');
    loadAll();
  }catch(e){ toast('❌ '+e.message, 'err'); }
}
async function saveSettings(){
  try{
    const r = await post('/api/settings', {
      trade_size: parseFloat(document.getElementById('sTradeSize').value),
      max_open: parseInt(document.getElementById('sMaxOpen').value)
    });
    toast(r.ok ? '⚙️ حُفظت الإعدادات' : '❌ '+(r.error||''), r.ok?'ok':'err');
    loadAll();
  }catch(e){ toast('❌ '+e.message, 'err'); }
}

async function boot(){
  try{ await loadAll(); }
  catch(e){
    document.querySelector('.sbar').innerHTML =
      '⚠️ <span style="color:var(--orange)">تعذر جلب البيانات: '+esc(e.message)+' — إعادة كل 5 ثوانٍ</span>';
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


def _key_valid(request):
    if not ADMIN_KEY:
        return True
    k = request.headers.get('X-Admin-Key', '') or request.query.get('key', '') \
        or request.cookies.get('admin_key', '')
    return hmac.compare_digest(str(k), ADMIN_KEY)


@web.middleware
async def auth_middleware(request, handler):
    if request.path == '/api/auth':
        return await handler(request)
    if not _key_valid(request):
        if request.path.startswith('/api/'):
            return web.json_response({'ok': False, 'error': 'مفتاح الأدمن غير صحيح أو مفقود'},
                                     status=401)
        return web.Response(text=LOGIN_PAGE, content_type='text/html')
    return await handler(request)


def create_app(bot):
    def j(data, status=200):
        return web.json_response(data, status=status,
                                 headers={'Cache-Control': 'no-store'})

    async def index(request):
        return web.Response(text=PAGE, content_type='text/html',
                            headers={'Cache-Control': 'no-store, must-revalidate'})

    async def auth(request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not ADMIN_KEY:
            return j({'ok': True, 'open': True})
        if hmac.compare_digest(str(data.get('key', '')), ADMIN_KEY):
            return j({'ok': True})
        return j({'ok': False, 'error': 'مفتاح غير صحيح'}, status=401)

    async def overview(request):
        today = time.strftime('%Y-%m-%d')
        row = await bot.db.get_day_stats(today)
        newest = max((p.get('ts', 0) for p in bot.live_prices.values()), default=0)
        balance = bot._balance_cache[0] if bot._balance_cache[1] > 0 else 0.0
        tuner = bot.tuner
        wr = tuner.recent_winrate(10)
        last_scan = getattr(bot, 'last_scan_info', None)
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
            'error_total': len(bot.error_counts),
            'last_scan': last_scan,
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
        await notify('system', 'تحديث يدوي للرصيد من اللوحة', f'المتاح الآن: ${balance:.2f}')
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

    async def daily_performance(request):
        days = []
        agg_c = agg_p = total_closed = total_wins = 0
        best = worst = None
        try:
            async with aiosqlite.connect(bot.db.db_name) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                        "SELECT date, realized_pnl, wins, losses FROM daily_stats "
                        "ORDER BY date DESC LIMIT 14") as cur:
                    rows = await cur.fetchall()
                for r in rows:
                    w = r['wins'] or 0
                    l = r['losses'] or 0
                    total = w + l
                    days.append({
                        'date': r['date'],
                        'pnl': round(r['realized_pnl'] or 0, 4),
                        'wins': w, 'losses': l, 'total': total,
                        'winrate': round(w / total * 100, 1) if total > 0 else None,
                    })
                async with db.execute(
                        "SELECT COUNT(*) c, COALESCE(SUM(realized_pnl),0) p FROM daily_stats "
                        "WHERE wins + losses > 0") as cur:
                    a = await cur.fetchone()
                    agg_c, agg_p = a['c'], a['p']
                async with db.execute(
                        "SELECT date, realized_pnl FROM daily_stats "
                        "WHERE wins + losses > 0 ORDER BY realized_pnl DESC LIMIT 1") as cur:
                    best = await cur.fetchone()
                async with db.execute(
                        "SELECT date, realized_pnl FROM daily_stats "
                        "WHERE wins + losses > 0 ORDER BY realized_pnl ASC LIMIT 1") as cur:
                    worst = await cur.fetchone()
                async with db.execute(
                        "SELECT COUNT(*) c FROM signal_log WHERE result >= 0") as cur:
                    total_closed = (await cur.fetchone())[0]
                async with db.execute(
                        "SELECT COUNT(*) c FROM signal_log WHERE result = 1") as cur:
                    total_wins = (await cur.fetchone())[0]
        except Exception:
            pass
        today = time.strftime('%Y-%m-%d')
        today_data = next((d for d in days if d['date'] == today), None)
        if not today_data:
            today_data = {'date': today, 'pnl': 0, 'wins': 0, 'losses': 0,
                          'total': 0, 'winrate': None}
        return j({
            'ok': True,
            'today': today_data,
            'days': days,
            'aggregates': {
                'active_days': agg_c,
                'total_pnl': round(agg_p, 4),
                'total_closed': total_closed,
                'total_wins': total_wins,
                'overall_winrate': round(total_wins / total_closed * 100, 1) if total_closed else None,
                'best_day': {'date': best['date'], 'pnl': round(best['realized_pnl'], 4)} if best else None,
                'worst_day': {'date': worst['date'], 'pnl': round(worst['realized_pnl'], 4)} if worst else None,
            },
            'trades_today_live': bot._trades_today(),
        })

    async def notifications(request):
        after = int(request.query.get('after', 0))
        if PANEL_DB:
            return j(await PANEL_DB.get_after(after))
        return j({'items': [], 'last_id': after, 'total_unread': 0})

    async def tuner_history(request):
        return j(list(bot.tuner.results))

    async def errors(request):
        return j({'errors': dict(bot.error_counts)})

    # ── الإجراءات ──
    async def pause(request):
        if bot.TRADE_ENABLED:
            bot.TRADE_ENABLED = False
            await notify('system', '⏸️ أُوقف التداول يدوياً من اللوحة',
                         'البوت في وضع المراقبة — الستوبات على المنصة ما زالت فعالة')
        return j({'ok': True, 'trade_enabled': False})

    async def resume(request):
        if not bot.binance_api_key:
            return j({'ok': False, 'error': 'مفاتيح API ناقصة'}, status=400)
        if not bot.TRADE_ENABLED:
            bot.TRADE_ENABLED = True
            await notify('system', '▶️ استؤنف التداول يدوياً من اللوحة', 'عاد البوت لدخول الصفقات')
        return j({'ok': True, 'trade_enabled': True})

    async def close_one(request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        symbol = str(data.get('symbol', '')).upper().strip()
        trade = bot.active_trades.get(symbol)
        if not trade:
            return j({'ok': False, 'error': 'المركز غير موجود'}, status=404)
        prices = bot.get_price(symbol)
        px = (prices['bid'] if trade['side'] == 'BUY' else prices['ask']) \
            if prices else trade['entry_price']
        ok, fill, pnl_over = await bot._close_position(trade, px)
        if ok:
            await bot._finalize_trade(trade, fill, '🔴 إغلاق يدوي من اللوحة', pnl_over)
            return j({'ok': True})
        return j({'ok': False, 'error': 'فشل الإغلاق — ستوب المنصة يحمي المركز، أعد المحاولة'},
                 status=500)

    async def close_all(request):
        closed = []
        for symbol, t in list(bot.active_trades.items()):
            prices = bot.get_price(symbol)
            px = (prices['bid'] if t['side'] == 'BUY' else prices['ask']) if prices else t['entry_price']
            ok, fill, pnl_over = await bot._close_position(t, px)
            if ok:
                await bot._finalize_trade(t, fill, '🛑 إغلاق شامل طارئ من اللوحة', pnl_over)
                closed.append(symbol)
        await notify('system', '🛑 إغلاق شامل من اللوحة',
                     'أُغلقت: ' + (', '.join(closed) if closed else 'لا مراكز'))
        return j({'ok': True, 'closed': closed})

    async def sync_stops(request):
        synced = 0
        for symbol, t in list(bot.active_trades.items()):
            try:
                prices = bot.get_price(symbol)
                if not prices:
                    continue
                cur = prices['bid'] if t['side'] == 'BUY' else prices['ask']
                if await bot._sync_stop_order(t, cur):
                    synced += 1
                await bot.db.save_trade(t)
            except Exception:
                pass
        await notify('system', '🛡️ مزامنة يدوية للستوبات من اللوحة',
                     f'تمت مزامنة {synced} ستوب على المنصة')
        return j({'ok': True, 'synced': synced})

    async def reconcile(request):
        try:
            await bot.reconcile()
            return j({'ok': True})
        except Exception as e:
            return j({'ok': False, 'error': str(e)[:150]}, status=500)

    async def update_tuner(request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        tuner = bot.tuner
        try:
            if 'min_score' in data:
                tuner.min_score = max(6, min(8, int(data['min_score'])))
            if 'proximity_pct' in data:
                tuner.proximity_pct = max(0.015, min(0.045, float(data['proximity_pct']) / 100))
            if 'strict_stoch' in data:
                tuner.strict_stoch = bool(data['strict_stoch'])
            tuner._clamp()
            await tuner.save()
            await notify('tuner', '🧠 تحديث المطوّر يدوياً من اللوحة', tuner.describe())
            return j({'ok': True, 'describe': tuner.describe()})
        except Exception as e:
            return j({'ok': False, 'error': str(e)[:150]}, status=400)

    async def update_settings(request):
        try:
            data = await request.json()
        except Exception:
            data = {}
        changed = []
        try:
            if 'trade_size' in data:
                v = float(data['trade_size'])
                if 1 <= v <= 1000:
                    bot.TRADE_SIZE_USDT = v
                    changed.append(f'الهامش ${v:.0f}')
            if 'max_open' in data:
                v = int(data['max_open'])
                if 1 <= v <= 10:
                    bot.MAX_OPEN_TRADES = v
                    changed.append(f'متزامنة {v}')
            await notify('system', '⚙️ تحديث إعدادات من اللوحة', ' • '.join(changed) or 'لا تغييرات')
            return j({'ok': True, 'changed': changed})
        except Exception as e:
            return j({'ok': False, 'error': str(e)[:150]}, status=400)

    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get('/', index)
    app.router.add_post('/api/auth', auth)
    app.router.add_get('/api/overview', overview)
    app.router.add_get('/api/balance', refresh_balance)
    app.router.add_get('/api/trades', trades)
    app.router.add_get('/api/closed', closed)
    app.router.add_get('/api/signals', signals)
    app.router.add_get('/api/daily', daily_performance)
    app.router.add_get('/api/notifications', notifications)
    app.router.add_get('/api/tuner-history', tuner_history)
    app.router.add_get('/api/errors', errors)
    app.router.add_post('/api/pause', pause)
    app.router.add_post('/api/resume', resume)
    app.router.add_post('/api/close-position', close_one)
    app.router.add_post('/api/close-all', close_all)
    app.router.add_post('/api/sync-stops', sync_stops)
    app.router.add_post('/api/reconcile', reconcile)
    app.router.add_post('/api/tuner', update_tuner)
    app.router.add_post('/api/settings', update_settings)
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
        if ADMIN_KEY:
            print(f'🖥️ لوحة القناص V9.2 تعمل على المنفذ {port} — حماية بمفتاح الأدمن ✓')
        else:
            print(f'🖥️ لوحة القناص V9.2 تعمل على المنفذ {port} — ⚠️ بدون مفتاح (اضبط ADMIN_KEY)')
        return True
    except Exception as e:
        print(f'⚠️ فشل اللوحة (البوت يكمل عمله): {e}')
        return False
