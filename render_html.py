#!/usr/bin/env python3
"""
render_html.py — Lee data.json (generado por build_data.py) y produce un
dashboard.html autocontenido (CSS y JS inline, sin librerias externas ni
CDN), siguiendo spec-dashboard-web.md:

  3.1 Resumen de semana sin scroll
  3.2 Calendario con selector Dia / Semana / Mes / Personalizado
      - aviso de seguridad SOLO en tooltip, nunca como banner fijo
  3.3 Registro de recomendaciones por dia (texto, solo lectura, colapsado
      por defecto en semana/mes, expandible al dar clic)
  3.4 Grafica de carga semanal basada en esfuerzo de Strava (no TSS)
  3.5 Tabla de sesiones recientes con columna de datos Strava

Uso:
    python render_html.py --data data.json --out dashboard.html
"""

import argparse
import json


SESSION_LABELS = {
    "long_run": "Rodaje largo",
    "quality": "Calidad",
    "easy": "Facil",
    "strength": "Fuerza",
    "rest": "Descanso",
    "other": "Otro",
}
SESSION_COLORS = {
    "long_run": "#5b7fff",
    "quality": "#ff5b5b",
    "easy": "#3fbf78",
    "strength": "#c98a3c",
    "rest": "#9b9b9b",
    "other": "#8a6bd6",
}
RECOVERY_LABELS = {
    "contrast": "Contrast",
    "sauna": "Sauna",
    "sauna_o_contrast": "Sauna/Contrast",
    "sauna_hoy_cold_mañana": "Sauna hoy",
    "cold_plunge": "Cold plunge",
    "ninguna": "Sin protocolo",
    "consulta_medica": "Consultar medico",
}
SEMAFORO_LABELS = {
    "en_linea": ("En linea", "#3fbf78"),
    "atrasado": ("Atrasado", "#e0a63f"),
    "adelantado": ("Adelantado", "#5b7fff"),
}

CSS = """
:root{
  --bg:#f5f6f8; --card:#ffffff; --text:#1c1f26; --muted:#6b7280;
  --border:#e5e7eb; --accent:#5b7fff; --radius:14px;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#14161c; --card:#1c1f27; --text:#eef0f4; --muted:#9aa1ae; --border:#2b2f3a; }
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;}
body{
  background:var(--bg); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px; line-height:1.4; padding:10px; max-width:900px; margin:0 auto;
  overflow-x:hidden;
}
h1{font-size:1.05rem; margin:.2rem 0 .6rem; display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:.4rem;}
h1 small{color:var(--muted); font-weight:400; font-size:.7rem;}
h2{font-size:.85rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:1.1rem 0 .4rem;}
.card{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:10px;}

/* 3.1 resumen de semana */
.summary-grid{display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px;}
.stat{background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:8px 6px; text-align:center; min-width:0;}
.stat .value{font-size:1.25rem; font-weight:700; line-height:1.1; overflow-wrap:break-word;}
.stat .label{font-size:.62rem; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; margin-top:2px;}
.badge{display:inline-block; padding:2px 8px; border-radius:999px; font-size:.68rem; font-weight:600; color:#fff;}
@media(max-width:520px){ .summary-grid{grid-template-columns:repeat(2, minmax(0,1fr));} }

/* 3.2 selector de vista */
.view-tabs{display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:6px; margin-bottom:8px;}
.view-tabs button{
  min-width:0; padding:7px 2px; border-radius:10px; border:1px solid var(--border);
  background:var(--card); color:var(--text); font-size:.72rem; cursor:pointer;
}
.view-tabs button.active{background:var(--accent); color:#fff; border-color:var(--accent);}
.custom-range{display:none; gap:6px; margin-bottom:8px; align-items:center; flex-wrap:wrap;}
.custom-range.active{display:flex;}
.custom-range input{padding:5px 6px; border-radius:8px; border:1px solid var(--border); background:var(--card); color:var(--text); font-size:.78rem; max-width:46%;}
.nav-row{display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; gap:6px;}
.nav-row button{background:var(--card); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:4px 10px; cursor:pointer; font-size:.85rem; flex-shrink:0;}
.nav-row .range-label{font-size:.78rem; color:var(--muted); font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0;}

.cal-grid{display:grid; grid-template-columns:repeat(7, minmax(0,1fr)); gap:4px; width:100%;}
.cal-grid.single{grid-template-columns:minmax(0,1fr);}
.dow{font-size:.6rem; color:var(--muted); text-align:center; text-transform:uppercase;}
.day-cell{
  background:var(--card); border:1px solid var(--border); border-radius:10px; padding:4px 3px;
  cursor:pointer; min-height:56px; position:relative; min-width:0;
}
.day-cell.today{border-color:var(--accent); border-width:2px;}
.day-cell.outside{opacity:.35;}
.day-cell .dnum{font-size:.72rem; font-weight:700; display:flex; justify-content:space-between; align-items:center; gap:2px;}
.day-cell .check{color:#3fbf78; font-weight:700; flex-shrink:0;}
.day-cell .stype-dot{width:7px; height:7px; border-radius:50%; display:inline-block; margin-right:3px; flex-shrink:0;}
.day-cell .stype-label{font-size:.6rem; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:block;}
.day-cell .strava-mini{font-size:.58rem; color:var(--muted); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}

.chip{
  display:block; max-width:100%; margin-top:3px; padding:1px 6px; border-radius:999px;
  background:rgba(91,127,255,.15); color:var(--accent); position:relative; cursor:help; z-index:1;
  box-sizing:border-box;
}
.chip.warn{background:rgba(224,90,90,.18); color:#e05a5a;}
.chip .chip-label{display:block; font-size:.58rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
.chip .tooltip{
  display:none; position:absolute; z-index:20; bottom:130%; left:50%; transform:translateX(-50%);
  width:max(160px, min(220px, 70vw)); background:#20232b; color:#f2f3f6; font-size:.68rem; line-height:1.35;
  padding:8px 9px; border-radius:8px; box-shadow:0 6px 18px rgba(0,0,0,.35); text-align:left;
  white-space:normal;
}
.chip .tooltip .safety{display:block; margin-top:6px; padding-top:6px; border-top:1px solid rgba(255,255,255,.15); color:#c9cdd6; font-size:.62rem;}
.chip:hover .tooltip, .chip:focus .tooltip{display:block;}
@media(max-width:480px){
  .day-cell .stype-label, .day-cell .strava-mini, .chip .chip-label{font-size:.54rem;}
  .cal-grid{gap:3px;}
}

.day-detail{margin-top:8px; padding-top:8px; border-top:1px dashed var(--border);}
.day-detail h3{margin:0 0 4px; font-size:.8rem;}
.log-entry{margin-bottom:6px; font-size:.78rem;}
.log-entry .cp{font-weight:700; margin-right:4px;}
.log-entry .txt{color:var(--muted); white-space:pre-wrap;}
.empty-note{color:var(--muted); font-size:.78rem; font-style:italic;}

/* 3.4 grafica de carga */
.chart-wrap{overflow-x:auto;}
svg text{font-family:inherit;}

/* 3.5 tabla */
table{width:100%; border-collapse:collapse; font-size:.75rem;}
th,td{padding:5px 6px; text-align:left; border-bottom:1px solid var(--border); white-space:nowrap;}
th{color:var(--muted); font-weight:600; font-size:.65rem; text-transform:uppercase;}
.table-wrap{overflow-x:auto;}

footer{color:var(--muted); font-size:.65rem; text-align:center; margin:1.2rem 0 .4rem;}
"""


def render(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False)
    generated_at = data.get("generated_at", "")

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Entrenador Virtual — Maraton</title>
<style>{CSS}</style>
</head>
<body>

<h1>🏃 Entrenador Virtual <small>generado {generated_at}</small></h1>

<section id="summary" class="summary-grid"></section>

<h2>Calendario</h2>
<div class="view-tabs" id="viewTabs">
  <button data-view="day">Dia</button>
  <button data-view="week">Semana</button>
  <button data-view="month">Mes</button>
  <button data-view="custom">Personalizado</button>
</div>
<div class="custom-range" id="customRange">
  <input type="date" id="customStart">
  <span>a</span>
  <input type="date" id="customEnd">
</div>
<div class="nav-row" id="navRow">
  <button id="prevBtn">‹</button>
  <span class="range-label" id="rangeLabel"></span>
  <button id="nextBtn">›</button>
</div>
<div class="card">
  <div id="calendar"></div>
  <div id="dayDetail" class="day-detail" style="display:none;"></div>
</div>

<h2>Carga semanal (esfuerzo Strava)</h2>
<div class="card chart-wrap"><div id="chart"></div></div>

<h2>Sesiones recientes</h2>
<div class="card table-wrap">
  <table id="sessionsTable">
    <thead>
      <tr><th>Fecha</th><th>Tipo</th><th>Dist</th><th>Ritmo</th><th>Esfuerzo</th><th>PRs</th><th>Kudos</th></tr>
    </thead>
    <tbody></tbody>
  </table>
</div>

<footer>entrenador-dk · dashboard estatico, se actualiza en cada checkpoint</footer>

<script>
const DATA = {data_json};
const SESSION_LABELS = {json.dumps(SESSION_LABELS, ensure_ascii=False)};
const SESSION_COLORS = {json.dumps(SESSION_COLORS, ensure_ascii=False)};
const RECOVERY_LABELS = {json.dumps(RECOVERY_LABELS, ensure_ascii=False)};
const SEMAFORO_LABELS = {json.dumps(SEMAFORO_LABELS, ensure_ascii=False)};
{JS}
</script>
</body>
</html>
"""
    return html


JS = r"""
function pad(n){ return String(n).padStart(2,'0'); }
function toISO(d){ return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()); }
function fromISO(s){ const [y,m,d]=s.split('-').map(Number); return new Date(y,m-1,d); }
function addDays(d,n){ const r=new Date(d); r.setDate(r.getDate()+n); return r; }
function startOfWeek(d){ const r=new Date(d); const wd=(r.getDay()+6)%7; return addDays(r,-wd); }
function startOfMonth(d){ return new Date(d.getFullYear(), d.getMonth(), 1); }

const allDates = Object.keys(DATA.days).sort();
const activeDates = allDates.filter(d => DATA.days[d].completed || DATA.days[d].garmin);
const latestDate = activeDates.length ? fromISO(activeDates[activeDates.length-1])
                  : (allDates.length ? fromISO(allDates[allDates.length-1]) : new Date());
const todayISO = toISO(latestDate);

const state = {
  view: 'week',
  refDate: new Date(latestDate),
  expanded: null,
  customStart: allDates.length ? allDates[Math.max(0, allDates.length-7)] : todayISO,
  customEnd: todayISO,
};

function renderSummary(){
  const s = DATA.week_summary || {};
  const [semLabel, semColor] = SEMAFORO_LABELS[s.semaforo] || ['—','#888'];
  const sleepGoal = (s.sleep_goal||[7,8]).join('-')+'h';
  const el = document.getElementById('summary');
  el.innerHTML = `
    <div class="stat"><div class="value">${s.days_to_race ?? '—'}</div><div class="label">Dias para la carrera</div></div>
    <div class="stat"><div class="value"><span class="badge" style="background:${semColor}">${semLabel}</span></div><div class="label">Cumplimiento del plan</div></div>
    <div class="stat"><div class="value">${(s.actual_km??0)}<span style="font-size:.6em;color:var(--muted)">/${(s.planned_km??0)}km</span></div><div class="label">KM semana (real/plan)</div></div>
    <div class="stat"><div class="value">${s.avg_sleep_hours ?? '—'}h</div><div class="label">Sueno vs meta ${sleepGoal}</div></div>
  `;
}

function recoveryChip(sug){
  if(!sug) return '';
  const isWarn = sug.recommendation === 'consulta_medica';
  const label = RECOVERY_LABELS[sug.recommendation] || sug.recommendation;
  const timing = sug.timing ? (sug.timing==='manana'?'AM':'PM') : '';
  return `<span class="chip ${isWarn?'warn':''}" tabindex="0">
    <span class="chip-label">${label}${timing?' · '+timing:''}</span>
    <span class="tooltip">${sug.detail||''}<span class="safety">${sug.safety_note||''}</span></span>
  </span>`;
}

function dayCellContent(iso, compact){
  const day = DATA.days[iso];
  const dnum = fromISO(iso).getDate();
  if(!day){
    return `<div class="dnum">${dnum}</div>`;
  }
  const color = SESSION_COLORS[day.session_type] || '#888';
  const label = SESSION_LABELS[day.session_type] || day.session_type;
  const check = day.completed ? '<span class="check">✓</span>' : '';
  let strava = '';
  if(day.primary_activity){
    const a = day.primary_activity;
    const bits = [];
    if(a.relative_effort) bits.push('Esf '+Math.round(a.relative_effort));
    if(a.pr_count) bits.push(a.pr_count+' PR');
    if(a.kudos) bits.push(a.kudos+' 👏');
    if(bits.length) strava = `<div class="strava-mini">${bits.join(' · ')}</div>`;
  }
  return `
    <div class="dnum"><span><span class="stype-dot" style="background:${color}"></span>${dnum}</span>${check}</div>
    <div class="stype-label">${label}</div>
    ${strava}
    ${recoveryChip(day.recovery_suggestion)}
  `;
}

function renderDayDetail(iso){
  const box = document.getElementById('dayDetail');
  const day = DATA.days[iso];
  if(!day){
    box.style.display='none';
    return;
  }
  box.style.display='block';
  const log = day.recommendations_log || [];
  let logHtml = '<p class="empty-note">Sin registro de checkpoints para este dia.</p>';
  if(log.length){
    logHtml = log.map(e => `<div class="log-entry"><span class="cp">${e.checkpoint}:</span><span class="txt">${e.text}</span></div>`).join('');
  }
  const plan = day.plan;
  const planHtml = plan ? `<p style="font-size:.78rem;color:var(--muted)">Plan: ${plan.title||''} ${plan.planned_distance_km?('· '+plan.planned_distance_km+'km'):''}</p>` : '';
  box.innerHTML = `<h3>${iso}${iso===todayISO?' (mas reciente con datos)':''}</h3>${planHtml}${logHtml}`;
}

function renderCalendar(){
  const cal = document.getElementById('calendar');
  const label = document.getElementById('rangeLabel');
  let isoList = [];
  let cols = 7;

  if(state.view === 'day'){
    isoList = [toISO(state.refDate)];
    cols = 1;
    label.textContent = isoList[0];
  } else if(state.view === 'week'){
    const start = startOfWeek(state.refDate);
    isoList = Array.from({length:7}, (_,i)=>toISO(addDays(start,i)));
    label.textContent = isoList[0]+' a '+isoList[6];
  } else if(state.view === 'month'){
    const start = startOfMonth(state.refDate);
    const gridStart = startOfWeek(start);
    isoList = Array.from({length:42}, (_,i)=>toISO(addDays(gridStart,i)));
    label.textContent = state.refDate.toLocaleDateString('es-MX', {month:'long', year:'numeric'});
  } else if(state.view === 'custom'){
    const s = fromISO(state.customStart), e = fromISO(state.customEnd);
    const days = Math.max(0, Math.round((e-s)/86400000));
    isoList = Array.from({length:days+1}, (_,i)=>toISO(addDays(s,i)));
    cols = 7;
    label.textContent = state.customStart+' a '+state.customEnd;
  }

  cal.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'cal-grid' + (cols===1?' single':'');
  cal.appendChild(grid);

  if(cols===7 && state.view!=='day'){
    ['L','M','X','J','V','S','D'].forEach(d=>{
      const dow = document.createElement('div');
      dow.className='dow'; dow.textContent=d;
      grid.appendChild(dow);
    });
  }

  const refMonth = state.refDate.getMonth();
  isoList.forEach(iso=>{
    const cell = document.createElement('div');
    cell.className = 'day-cell';
    if(iso===todayISO) cell.classList.add('today');
    if(state.view==='month' && fromISO(iso).getMonth()!==refMonth) cell.classList.add('outside');
    cell.innerHTML = dayCellContent(iso, cols!==1);
    cell.addEventListener('click', (ev)=>{
      if(ev.target.closest('.chip')) return;
      state.expanded = state.expanded===iso ? null : iso;
      renderDayDetail(state.expanded);
    });
    grid.appendChild(cell);
  });

  if(state.view==='day'){
    state.expanded = isoList[0];
    renderDayDetail(state.expanded);
  } else if(state.expanded && isoList.includes(state.expanded)){
    renderDayDetail(state.expanded);
  } else {
    document.getElementById('dayDetail').style.display='none';
  }
}

function renderChart(){
  const weeks = (DATA.weeks||[]).slice(-8);
  const wrap = document.getElementById('chart');
  if(!weeks.length){ wrap.innerHTML = '<p class="empty-note">Sin datos suficientes.</p>'; return; }

  const w = 560, h = 190, padL = 34, padB = 34, padT = 10;
  const barW = (w - padL - 10) / weeks.length;
  const maxEffort = Math.max(1, ...weeks.map(x=>x.total_relative_effort||0));

  let svg = `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;max-width:${w}px" role="img" aria-label="Carga semanal por esfuerzo de Strava">`;
  // eje
  svg += `<line x1="${padL}" y1="${h-padB}" x2="${w-5}" y2="${h-padB}" stroke="var(--border)" stroke-width="1"/>`;

  weeks.forEach((wk,i)=>{
    const x = padL + i*barW + 4;
    const bw = barW - 8;
    const eff = wk.total_relative_effort||0;
    const bh = (eff/maxEffort) * (h-padT-padB);
    const y = h - padB - bh;
    svg += `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="3" fill="var(--accent)" opacity="0.85"><title>Semana ${wk.week_start}: esfuerzo ${eff}</title></rect>`;
    svg += `<text x="${x+bw/2}" y="${h-padB+13}" font-size="8" fill="var(--muted)" text-anchor="middle">${wk.week_start.slice(5)}</text>`;
    svg += `<text x="${x+bw/2}" y="${y-3}" font-size="8" fill="var(--text)" text-anchor="middle">${Math.round(eff)}</text>`;
  });
  svg += `</svg>`;

  let kmRows = weeks.map(wk => `<tr><td>${wk.week_start}</td><td>${wk.planned_km}km</td><td>${wk.actual_km}km</td></tr>`).join('');
  svg += `<div class="table-wrap"><table><thead><tr><th>Semana</th><th>Plan (TP)</th><th>Real (Strava)</th></tr></thead><tbody>${kmRows}</tbody></table></div>`;

  wrap.innerHTML = svg;
}

function fmtPace(p){
  if(!p) return '—';
  const min = Math.floor(p), sec = Math.round((p-min)*60);
  return min+':'+pad(sec)+'/km';
}

function renderTable(){
  const tbody = document.querySelector('#sessionsTable tbody');
  const rows = (DATA.recent_sessions||[]).map(s=>`
    <tr>
      <td>${s.date}</td>
      <td>${SESSION_LABELS[s.session_type]||s.session_type}</td>
      <td>${s.distance_km??'—'}km</td>
      <td>${fmtPace(s.pace_min_per_km)}</td>
      <td>${s.relative_effort??'—'}</td>
      <td>${s.pr_count||0}</td>
      <td>${s.kudos||0}</td>
    </tr>`).join('');
  tbody.innerHTML = rows || '<tr><td colspan="7" class="empty-note">Sin sesiones recientes.</td></tr>';
}

function setActiveTab(){
  document.querySelectorAll('#viewTabs button').forEach(b=>{
    b.classList.toggle('active', b.dataset.view===state.view);
  });
  document.getElementById('customRange').classList.toggle('active', state.view==='custom');
  document.getElementById('navRow').style.display = state.view==='custom' ? 'none' : 'flex';
}

function step(dir){
  if(state.view==='day') state.refDate = addDays(state.refDate, dir);
  else if(state.view==='week') state.refDate = addDays(state.refDate, dir*7);
  else if(state.view==='month') state.refDate = new Date(state.refDate.getFullYear(), state.refDate.getMonth()+dir, 1);
  renderCalendar();
}

document.getElementById('viewTabs').addEventListener('click', (e)=>{
  const btn = e.target.closest('button');
  if(!btn) return;
  state.view = btn.dataset.view;
  setActiveTab();
  renderCalendar();
});
document.getElementById('prevBtn').addEventListener('click', ()=>step(-1));
document.getElementById('nextBtn').addEventListener('click', ()=>step(1));
document.getElementById('customStart').addEventListener('change', (e)=>{ state.customStart = e.target.value; renderCalendar(); });
document.getElementById('customEnd').addEventListener('change', (e)=>{ state.customEnd = e.target.value; renderCalendar(); });

document.getElementById('customStart').value = state.customStart;
document.getElementById('customEnd').value = state.customEnd;

renderSummary();
setActiveTab();
renderCalendar();
renderChart();
renderTable();
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data.json", help="Ruta a data.json")
    ap.add_argument("--out", default="dashboard.html", help="Ruta de salida del HTML")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    html = render(data)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"OK -> {args.out}")


if __name__ == "__main__":
    main()
