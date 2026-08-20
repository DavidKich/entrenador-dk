#!/usr/bin/env python3
"""
render_html.py — Lee data.json (generado por build_data.py) y produce un
dashboard.html autocontenido (CSS y JS inline, sin librerias externas ni
CDN), siguiendo spec-dashboard-web.md.

Visual/UX porteado desde el proyecto de Claude Design "Rediseno dashboard
tipo coach" (Entrenador.dc.html) a JS vanilla — sin runtime de React ni
soporte externo, para mantener el archivo autocontenido. La logica de
interaccion (calendario Dia/Semana/Mes/Personalizado, panel de detalle del
dia, recuperacion) es la misma que ese diseno, alimentada por data.json
real en vez de datos de ejemplo fijos.

Cambios de comportamiento respecto a la version anterior (a peticion del
usuario, tras revisar en movil):
  - Ya no hay tooltip en las celdas del calendario (se quita el problema de
    reposicionamiento en bordes de pantalla). La recomendacion de
    recuperacion de HOY se muestra siempre visible en la tarjeta "HOY", y
    para cualquier otro dia se ve al expandir esa fecha (seccion de
    detalle), igual de accesible sin depender de hover/tap en un chip.
  - El aviso de seguridad se acorta a una sola linea fija en el footer en
    vez de un parrafo largo por tooltip (sigue sin ser un banner arriba
    del calendario, que es lo que pedia evitar el spec original).

Uso:
    python render_html.py --data data.json --out dashboard.html
"""

import argparse
import json


CSS = """
:root{
  --bg:#0A0B0D; --card:#13151A; --text:#F2F3F5; --border:rgba(255,255,255,.06);
}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;overflow-x:hidden;}
body{font-family:Archivo,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-variant-numeric:tabular-nums;font-size:15px;}
a{color:#8FB4FF;text-decoration:none;}
a:hover{color:#B9CEFF;}
input[type=date]{color-scheme:dark;}
.wrap{max-width:580px;margin:0 auto;padding:20px 16px 56px;display:flex;flex-direction:column;gap:26px;}
.cal-cell{transition:opacity .15s;}
"""


def render(data: dict) -> str:
    data_json = json.dumps(data, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Entrenador · Maraton</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script>
const DATA = {data_json};
{JS}
</script>
</body>
</html>
"""
    return html


JS = r"""
const FSANS = "Archivo,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
const FMONO = "'IBM Plex Mono',ui-monospace,Consolas,'Liberation Mono',monospace";

const TYPE = {
  long_run: ['Rodaje largo', '#8FB4FF'],
  quality: ['Calidad', '#FF8A8A'],
  easy: ['Facil', '#7FE7C4'],
  strength: ['Fuerza', '#F0B24A'],
  rest: ['Descanso', '#6B7280'],
  other: ['Otro', '#8A8F98'],
};
const REC_META = {
  contrast: ['Contrast therapy', '#8FB4FF'],
  sauna_o_contrast: ['Sauna o contrast · AM', '#7FE7C4'],
  sauna_hoy: ['Sauna hoy · frio manana', '#F0B24A'],
  sauna: ['Sauna', '#7FE7C4'],
  ninguna: ['Sin protocolo', '#6B7280'],
  consulta_medica: ['Consultar medico', '#FF8A8A'],
};
const SEM_META = {
  en_linea: ['En linea', '#7FE7C4'],
  atrasado: ['Atrasado', '#F0B24A'],
  adelantado: ['Adelantado', '#8FB4FF'],
};
const MONTHS = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
const SAFETY = 'Orientacion general de recuperacion deportiva, no consejo medico.';

function pad(n){ return String(n).padStart(2,'0'); }
function toISO(d){ return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()); }
function fromISO(s){ const p = s.split('-').map(Number); return new Date(p[0], p[1]-1, p[2]); }
function addDays(d,n){ const r = new Date(d); r.setDate(r.getDate()+n); return r; }
function startOfWeek(d){ const r = new Date(d); return addDays(r, -((r.getDay()+6)%7)); }
function shortDate(iso){ if(!iso) return ''; const d = fromISO(iso); return d.getDate()+' '+MONTHS[d.getMonth()]; }
function fmtPace(p){ if(!p) return '—'; const m = Math.floor(p); return m+':'+pad(Math.round((p-m)*60))+'/km'; }
function formatGen(iso){
  if(!iso) return '';
  const [datePart, timePart] = iso.split('T');
  const d = fromISO(datePart);
  const hm = (timePart||'').slice(0,5);
  return d.getDate()+' '+MONTHS[d.getMonth()]+' '+d.getFullYear()+(hm?' · '+hm:'');
}

const allDates = Object.keys(DATA.days).sort();
const activeDates = allDates.filter(d => DATA.days[d].completed || DATA.days[d].garmin);
const TODAY = activeDates.length ? activeDates[activeDates.length-1]
            : (allDates.length ? allDates[allDates.length-1] : toISO(new Date()));

const state = {
  view: 'week',
  ref: TODAY,
  sel: TODAY,
  cs: allDates.length ? allDates[Math.max(0, allDates.length-7)] : TODAY,
  ce: TODAY,
};

function byDate(iso){ return DATA.days[iso]; }

function step(dir){
  const d = fromISO(state.ref);
  let n;
  if(state.view === 'day') n = addDays(d, dir);
  else if(state.view === 'month') n = new Date(d.getFullYear(), d.getMonth()+dir, 1);
  else n = addDays(d, dir*7);
  state.ref = toISO(n);
  if(state.view === 'day') state.sel = state.ref;
  render();
}

function computeVals(){
  const S = DATA.week_summary || {};
  const sem = SEM_META[S.semaforo] || ['—', '#8A8F98'];
  const pct = S.planned_km ? Math.round(S.actual_km / S.planned_km * 100) : 0;

  const ref = fromISO(state.ref);
  let list = [], cols = 'repeat(7,minmax(0,1fr))', dows = ['L','M','X','J','V','S','D'], rangeLabel = '';
  if(state.view === 'day'){
    list = [state.ref]; cols = 'minmax(0,1fr)'; dows = []; rangeLabel = shortDate(state.ref);
  } else if(state.view === 'week'){
    const s = startOfWeek(ref);
    list = Array.from({length:7}, (_,i) => toISO(addDays(s,i)));
    rangeLabel = shortDate(list[0])+' — '+shortDate(list[6]);
  } else if(state.view === 'month'){
    const first = new Date(ref.getFullYear(), ref.getMonth(), 1);
    const gs = startOfWeek(first);
    list = Array.from({length:42}, (_,i) => toISO(addDays(gs,i)));
    rangeLabel = MONTHS[ref.getMonth()]+' '+ref.getFullYear();
  } else {
    const a = fromISO(state.cs), b = fromISO(state.ce);
    const n = Math.max(0, Math.round((b-a)/86400000));
    list = Array.from({length: Math.min(n+1, 63)}, (_,i) => toISO(addDays(a,i)));
    rangeLabel = shortDate(state.cs)+' — '+shortDate(state.ce);
  }

  const cells = list.map(iso => {
    const day = byDate(iso);
    const ty = day ? (TYPE[day.session_type] || TYPE.other) : null;
    const outside = state.view === 'month' && fromISO(iso).getMonth() !== ref.getMonth();
    const isSel = iso === state.sel;
    const act = day && day.primary_activity;
    return {
      iso,
      num: fromISO(iso).getDate(),
      label: ty ? ty[0] : '',
      dot: ty ? ty[1] : 'rgba(255,255,255,.10)',
      eff: act && act.relative_effort ? 'Esf '+Math.round(act.relative_effort)
           : (day && day.plan && day.plan.planned_distance_km ? day.plan.planned_distance_km+' km' : ''),
      effColor: day && day.completed ? '#C7CBD2' : '#7C828C',
      bg: isSel ? '#1C2027' : '#13151A',
      border: isSel ? 'rgba(255,255,255,.28)' : (iso === TODAY ? 'rgba(143,180,255,.45)' : 'rgba(255,255,255,.06)'),
      op: day ? (outside ? 0.35 : 1) : 0.3,
    };
  });

  const td = byDate(TODAY);
  const tdTy = TYPE[td.session_type] || TYPE.other;
  const tdRecMeta = REC_META[td.recovery_suggestion.recommendation] || [td.recovery_suggestion.recommendation, '#8A8F98'];
  const tdAct = td.primary_activity;
  const tdMetrics = [
    {label:'DISTANCIA', val: tdAct && tdAct.distance_km ? tdAct.distance_km+' km' : '—'},
    {label:'RITMO', val: fmtPace(tdAct && tdAct.pace_min_per_km)},
    {label:'ESFUERZO', val: (tdAct && tdAct.relative_effort) ?? '—'},
    {label:'SUEÑO', val: td.garmin ? td.garmin.sleep_hours+'h' : '—', color: td.garmin && td.garmin.sleep_hours >= 7 ? '#7FE7C4' : '#F0B24A'},
  ];

  const sel = byDate(state.sel);
  let selVals = null;
  if(sel){
    const rec = REC_META[sel.recovery_suggestion.recommendation] || [sel.recovery_suggestion.recommendation, '#8A8F98'];
    const g = sel.garmin;
    const act = sel.primary_activity;
    const selTy = TYPE[sel.session_type] || TYPE.other;
    const planKm = sel.plan && sel.plan.planned_distance_km;
    const selPlan = [
      planKm ? 'Plan: '+planKm+' km' : 'Plan: sin kilometraje',
      (sel.plan && sel.plan.notes) || '',
      'Recuperacion: '+rec[0],
    ].filter(Boolean).join(' · ');
    const selMetrics = [
      {label:'SUEÑO', val: g ? g.sleep_hours+'h' : '—', color: g ? (g.sleep_hours >= 7 ? '#7FE7C4' : '#F0B24A') : '#4A4F57'},
      {label:'CALIDAD SUEÑO', val: g ? g.sleep_score : '—'},
      {label:'HRV', val: g ? g.hrv : '—', color: g && sel.hrv_7d_avg && g.hrv < sel.hrv_7d_avg-8 ? '#F0B24A' : '#C7CBD2'},
      {label:'BODY BATTERY', val: g ? g.body_battery : '—', color: g && g.body_battery < 50 ? '#F0B24A' : '#C7CBD2'},
      {label:'ESTRÉS', val: g ? g.stress_avg : '—'},
      {label:'HRV 7 DIAS', val: sel.hrv_7d_avg ?? '—'},
      {label:'REALIZADO', val: act && act.distance_km ? act.distance_km+' km' : (sel.completed ? 'Si' : 'No'), color: sel.completed ? '#7FE7C4' : '#6B7280'},
    ];
    let selWarn = '';
    if(sel.recovery_suggestion.recommendation === 'consulta_medica') selWarn = sel.recovery_suggestion.detail;
    else if(sel.fatigue_flag) selWarn = 'Bandera de fatiga: HRV y Body Battery por debajo de tu linea base. Considera bajar intensidad o revisarlo con tu entrenador.';
    const selLogs = sel.recommendations_log || [];
    selVals = {
      title: (sel.plan && sel.plan.title) || selTy[0],
      date: state.sel,
      plan: selPlan,
      metrics: selMetrics,
      warn: selWarn,
      logs: selLogs,
      logTitle: selLogs.length ? 'REGISTRO DE CHECKPOINTS' : 'SIN CHECKPOINTS REGISTRADOS ESTE DIA',
    };
  }

  const weeks = (DATA.weeks || []).slice(-8);
  const vals = weeks.map(w => w.total_planned_tss || 0);
  const max = Math.max.apply(null, vals) || 1;
  const bars = weeks.map((w,i) => ({
    label: shortDate(w.week_start),
    val: Math.round(vals[i]),
    h: Math.max(6, Math.round(vals[i]/max*104))+'px',
    color: w.week_start === S.week_start ? '#F0B24A' : '#8FB4FF',
  }));
  const weekRows = weeks.map(w => {
    const p = w.planned_km ? Math.round(w.actual_km/w.planned_km*100) : 0;
    return {label: shortDate(w.week_start)+' · plan '+w.planned_km+' km', val: w.actual_km+' km · '+p+'%', bar: Math.min(100,p)+'%', color: p >= 95 ? '#7FE7C4' : '#F0B24A'};
  });

  const sessions = (DATA.recent_sessions || []).slice(0,10).map(s => {
    const ty = TYPE[s.session_type] || TYPE.other;
    const meta = [shortDate(s.date), ty[0], 'esf '+(s.relative_effort ?? '—')]
      .join(' · ');
    return {
      name: s.name || ty[0],
      color: ty[1],
      meta,
      dist: s.distance_km ? s.distance_km+' km' : ty[0],
      pace: fmtPace(s.pace_min_per_km),
    };
  });

  const tabs = [['day','Dia'],['week','Semana'],['month','Mes'],['custom','Rango']].map(t => ({
    key: t[0], label: t[1],
    bg: state.view === t[0] ? '#F2F3F5' : '#13151A',
    color: state.view === t[0] ? '#0A0B0D' : '#8A8F98',
    border: state.view === t[0] ? '#F2F3F5' : 'rgba(255,255,255,.08)',
  }));

  const currentWeek = weeks.find(w => w.week_start === S.week_start);

  return {
    gen: formatGen(DATA.generated_at), dtr: S.days_to_race ?? '—', goal: DATA.goal_time || '',
    raceLabel: DATA.race_date ? shortDate(DATA.race_date)+' '+fromISO(DATA.race_date).getFullYear() : '',
    semLabel: sem[0], semColor: sem[1], semBg: sem[1]+'14', semBorder: sem[1]+'59',
    weekLabel: currentWeek ? shortDate(currentWeek.week_start)+' — '+shortDate(currentWeek.week_end) : '',
    weekActual: S.actual_km ?? 0, weekPlanned: S.planned_km ?? 0, weekPct: pct, weekBar: Math.min(100,pct)+'%',
    weekStats: [
      {label:'SUEÑO PROMEDIO', val: (S.avg_sleep_hours ?? '—')+'h', color: (S.avg_sleep_hours||0) >= 7 ? '#7FE7C4' : '#F0B24A'},
      {label:'HRV 7 DIAS', val: td.hrv_7d_avg ?? '—'},
      {label:'ESFUERZO ACUM.', val: currentWeek ? Math.round(currentWeek.total_relative_effort) : '—'},
    ],
    tdTitle: (td.plan && td.plan.title) || tdTy[0], tdColor: tdTy[1],
    tdPlan: (td.plan && td.plan.planned_distance_km ? td.plan.planned_distance_km+' km planeados' : 'sin kilometraje planeado')
            + (td.plan && td.plan.notes ? ' · '+td.plan.notes : ''),
    tdState: td.completed ? 'Completado' : 'Pendiente', tdStateColor: td.completed ? '#7FE7C4' : '#F0B24A',
    tdMetrics, tdRec: tdRecMeta[0], tdRecColor: tdRecMeta[1], tdRecDetail: td.recovery_suggestion.detail,
    tabs, showCustom: state.view === 'custom', showNav: state.view !== 'custom',
    cs: state.cs, ce: state.ce,
    rangeLabel, gridCols: cols, dows, cells,
    sel: selVals,
    chartUnit: 'TSS planeado (TrainingPeaks)',
    bars, weekRows, sessions,
    legend: Object.keys(TYPE).map(k => ({label: TYPE[k][0], color: TYPE[k][1]})),
    safety: SAFETY,
  };
}

function buildHTML(v){
  const statCard = (m) => `<div style="display:flex;flex-direction:column;gap:4px;padding-top:12px">
    <span style="font:600 18px ${FSANS};color:${m.color||'#F2F3F5'}">${m.val}</span>
    <span style="font:400 9px ${FMONO};letter-spacing:.08em;color:#5E636C">${m.label}</span>
  </div>`;
  const tdMetric = (m) => `<div style="display:flex;flex-direction:column;gap:3px">
    <span style="font:600 17px ${FSANS};color:${m.color||'#F2F3F5'}">${m.val}</span>
    <span style="font:400 9px ${FMONO};letter-spacing:.07em;color:#5E636C">${m.label}</span>
  </div>`;
  const tab = (t) => `<button data-view="${t.key}" style="flex:1;min-width:0;padding:8px 4px;border-radius:10px;border:1px solid ${t.border};background:${t.bg};color:${t.color};font:500 11px ${FMONO};letter-spacing:.04em;cursor:pointer">${t.label}</button>`;
  const dow = (d) => `<span style="font:500 10px ${FMONO};color:#8A8F98;text-align:center;letter-spacing:.08em">${d}</span>`;
  const cell = (c) => `<div class="cal-cell" data-iso="${c.iso}" style="background:${c.bg};border:1px solid ${c.border};border-radius:11px;padding:8px 7px;min-height:74px;cursor:pointer;display:flex;flex-direction:column;gap:5px;opacity:${c.op};min-width:0">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:4px">
      <span style="font:600 13px ${FSANS};color:#F2F3F5">${c.num}</span>
      <span style="width:6px;height:6px;border-radius:50%;background:${c.dot};flex-shrink:0"></span>
    </div>
    <span style="font:400 9px ${FMONO};color:#8A8F98;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${c.label}</span>
    <span style="margin-top:auto;font:500 11px ${FSANS};color:${c.effColor}">${c.eff}</span>
  </div>`;
  const selMetric = (m) => `<div style="display:flex;flex-direction:column;gap:3px">
    <span style="font:600 16px ${FSANS};color:${m.color||'#C7CBD2'}">${m.val}</span>
    <span style="font:400 9px ${FMONO};letter-spacing:.07em;color:#5E636C">${m.label}</span>
  </div>`;
  const logEntry = (l) => `<div style="display:flex;flex-direction:column;gap:5px">
    <span style="font:500 10px ${FMONO};letter-spacing:.08em;color:#8FB4FF">${(l.checkpoint||'').toUpperCase()}</span>
    <span style="font:400 13px/1.55 ${FSANS};color:#C7CBD2">${l.text}</span>
  </div>`;
  const bar = (b) => `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:7px;justify-content:flex-end;height:100%">
    <span style="font:500 11px ${FSANS};color:#C7CBD2">${b.val}</span>
    <div style="width:100%;border-radius:6px 6px 3px 3px;background:${b.color};height:${b.h}"></div>
    <span style="font:400 9px ${FMONO};color:#5E636C">${b.label}</span>
  </div>`;
  const weekRow = (w) => `<div style="display:flex;flex-direction:column;gap:6px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px">
      <span style="font:400 10px ${FMONO};color:#8A8F98">${w.label}</span>
      <span style="font:500 11px ${FMONO};color:${w.color}">${w.val}</span>
    </div>
    <div style="height:4px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden">
      <div style="height:100%;border-radius:999px;background:${w.color};width:${w.bar}"></div>
    </div>
  </div>`;
  const sessionRow = (s) => `<div style="display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid rgba(255,255,255,.05)">
    <span style="width:6px;height:6px;border-radius:50%;background:${s.color};flex-shrink:0"></span>
    <div style="display:flex;flex-direction:column;gap:3px;min-width:0;flex:1">
      <span style="font:500 13px ${FSANS};overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${s.name}</span>
      <span style="font:400 10px ${FMONO};color:#5E636C">${s.meta}</span>
    </div>
    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:3px;flex-shrink:0">
      <span style="font:600 13px ${FSANS}">${s.dist}</span>
      <span style="font:400 10px ${FMONO};color:#8A8F98">${s.pace}</span>
    </div>
  </div>`;
  const legendItem = (l) => `<div style="display:flex;align-items:center;gap:6px">
    <span style="width:6px;height:6px;border-radius:50%;background:${l.color}"></span>
    <span style="font:400 10px ${FMONO};color:#5E636C">${l.label}</span>
  </div>`;

  const selSection = v.sel ? `
  <section style="background:#13151A;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:16px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
      <span style="font:600 16px ${FSANS}">${v.sel.title}</span>
      <span style="font:400 11px ${FMONO};color:#5E636C">${v.sel.date}</span>
    </div>
    <span style="font:400 12px/1.5 ${FSANS};color:#8A8F98">${v.sel.plan}</span>
    <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px 10px">
      ${v.sel.metrics.map(selMetric).join('')}
    </div>
    ${v.sel.warn ? `<span style="font:400 12px/1.5 ${FSANS};color:#F0B24A;background:rgba(240,178,74,.08);border-radius:10px;padding:10px 12px">${v.sel.warn}</span>` : ''}
    <div style="display:flex;flex-direction:column;gap:14px;padding-top:14px;border-top:1px solid rgba(255,255,255,.06)">
      <span style="font:400 9px ${FMONO};letter-spacing:.1em;color:#5E636C">${v.sel.logTitle}</span>
      ${v.sel.logs.map(logEntry).join('') || `<span style="font:400 12px ${FSANS};color:#4A4F57">Sin checkpoints registrados para este dia.</span>`}
    </div>
  </section>` : '';

  const customRange = v.showCustom ? `
    <div style="display:flex;align-items:center;gap:8px">
      <input type="date" id="csInput" value="${v.cs}" style="flex:1;min-width:0;padding:7px 9px;border-radius:9px;border:1px solid rgba(255,255,255,.08);background:#13151A;color:#F2F3F5;font:400 12px ${FMONO}">
      <span style="font:400 11px ${FMONO};color:#5E636C">a</span>
      <input type="date" id="ceInput" value="${v.ce}" style="flex:1;min-width:0;padding:7px 9px;border-radius:9px;border:1px solid rgba(255,255,255,.08);background:#13151A;color:#F2F3F5;font:400 12px ${FMONO}">
    </div>` : '';

  const navRow = v.showNav ? `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <button id="prevBtn" style="width:30px;height:30px;border-radius:9px;border:1px solid rgba(255,255,255,.08);background:#13151A;color:#8A8F98;font:500 15px ${FSANS};cursor:pointer">‹</button>
      <span style="font:500 11px ${FMONO};letter-spacing:.04em;color:#8A8F98;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${v.rangeLabel}</span>
      <button id="nextBtn" style="width:30px;height:30px;border-radius:9px;border:1px solid rgba(255,255,255,.08);background:#13151A;color:#8A8F98;font:500 15px ${FSANS};cursor:pointer">›</button>
    </div>` : '';

  return `
  <header style="display:flex;flex-direction:column;gap:18px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
      <span style="font:500 10px ${FMONO};letter-spacing:.16em;color:#5E636C">ENTRENADOR · MARATON</span>
      <span style="font:400 10px ${FMONO};color:#3F444B">${v.gen}</span>
    </div>
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap">
      <div style="display:flex;align-items:flex-end;gap:14px">
        <span style="font:700 76px/0.82 ${FSANS};letter-spacing:-.04em">${v.dtr}</span>
        <div style="padding-bottom:7px;display:flex;flex-direction:column;gap:4px">
          <span style="font:500 14px ${FSANS};color:#F2F3F5">dias para la carrera</span>
          <span style="font:400 11px ${FMONO};color:#8A8F98">${v.raceLabel} · meta ${v.goal}</span>
        </div>
      </div>
      <span style="font:500 11px ${FMONO};letter-spacing:.06em;padding:5px 11px;border-radius:999px;color:${v.semColor};border:1px solid ${v.semBorder};background:${v.semBg}">${v.semLabel}</span>
    </div>
  </header>

  <section style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <span style="font:500 10px ${FMONO};letter-spacing:.14em;color:#5E636C">SEMANA EN CURSO</span>
      <span style="font:400 10px ${FMONO};color:#5E636C">${v.weekLabel}</span>
    </div>
    <div style="background:#13151A;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:18px 18px 16px;display:flex;flex-direction:column;gap:16px">
      <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:12px">
        <div style="display:flex;align-items:baseline;gap:6px">
          <span style="font:700 40px/1 ${FSANS};letter-spacing:-.02em">${v.weekActual}</span>
          <span style="font:500 15px ${FSANS};color:#6B7280">/ ${v.weekPlanned} km</span>
        </div>
        <span style="font:500 12px ${FMONO};color:#8A8F98">${v.weekPct}% del plan</span>
      </div>
      <div style="height:6px;border-radius:999px;background:rgba(255,255,255,.07);overflow:hidden">
        <div style="height:100%;border-radius:999px;background:${v.semColor};width:${v.weekBar}"></div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding-top:4px;border-top:1px solid rgba(255,255,255,.06)">
        ${v.weekStats.map(statCard).join('')}
      </div>
    </div>
  </section>

  <section style="display:flex;flex-direction:column;gap:10px">
    <span style="font:500 10px ${FMONO};letter-spacing:.14em;color:#5E636C">HOY</span>
    <div style="background:#13151A;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:16px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px">
        <div style="display:flex;flex-direction:column;gap:6px;min-width:0">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="width:7px;height:7px;border-radius:50%;background:${v.tdColor};flex-shrink:0"></span>
            <span style="font:600 19px ${FSANS};letter-spacing:-.01em">${v.tdTitle}</span>
          </div>
          <span style="font:400 12px ${FMONO};color:#8A8F98">${v.tdPlan}</span>
        </div>
        <span style="font:500 11px ${FMONO};color:${v.tdStateColor};white-space:nowrap">${v.tdState}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px">
        ${v.tdMetrics.map(tdMetric).join('')}
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;padding-top:14px;border-top:1px solid rgba(255,255,255,.06)">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font:400 9px ${FMONO};letter-spacing:.1em;color:#5E636C">RECUPERACION</span>
          <span style="font:500 12px ${FSANS};color:${v.tdRecColor}">${v.tdRec}</span>
        </div>
        <span style="font:400 12px/1.5 ${FSANS};color:#8A8F98">${v.tdRecDetail}</span>
      </div>
    </div>
  </section>

  <section style="display:flex;flex-direction:column;gap:10px">
    <span style="font:500 10px ${FMONO};letter-spacing:.14em;color:#5E636C">CALENDARIO</span>
    <div style="display:flex;gap:6px" id="viewTabs">
      ${v.tabs.map(tab).join('')}
    </div>
    ${customRange}
    ${navRow}
    <div style="display:grid;grid-template-columns:${v.gridCols};gap:5px">
      ${v.dows.map(dow).join('')}
    </div>
    <div style="display:grid;grid-template-columns:${v.gridCols};gap:5px" id="calGrid">
      ${v.cells.map(cell).join('')}
    </div>
  </section>

  ${selSection}

  <section style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
      <span style="font:500 10px ${FMONO};letter-spacing:.14em;color:#5E636C">CARGA POR SEMANA</span>
      <span style="font:400 10px ${FMONO};color:#5E636C">${v.chartUnit}</span>
    </div>
    <div style="background:#13151A;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:18px">
      <div style="display:flex;align-items:flex-end;gap:10px;height:150px">
        ${v.bars.map(bar).join('')}
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;padding-top:16px;border-top:1px solid rgba(255,255,255,.06)">
        ${v.weekRows.map(weekRow).join('')}
      </div>
    </div>
  </section>

  <section style="display:flex;flex-direction:column;gap:10px">
    <span style="font:500 10px ${FMONO};letter-spacing:.14em;color:#5E636C">SESIONES RECIENTES</span>
    <div style="background:#13151A;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:6px 18px;display:flex;flex-direction:column">
      ${v.sessions.map(sessionRow).join('') || `<p style="color:#5E636C;font:400 12px ${FSANS};padding:14px 0">Sin sesiones recientes.</p>`}
    </div>
  </section>

  <div style="display:flex;flex-wrap:wrap;gap:12px 16px">
    ${v.legend.map(legendItem).join('')}
  </div>

  <footer style="font:400 10px ${FMONO};color:#3F444B;text-align:center;line-height:1.6">
    entrenador-dk · se actualiza en cada checkpoint<br>${v.safety}
  </footer>
  `;
}

function render(){
  const v = computeVals();
  document.getElementById('app').innerHTML = buildHTML(v);
  wireEvents();
}

function wireEvents(){
  const viewTabs = document.getElementById('viewTabs');
  if(viewTabs) viewTabs.addEventListener('click', e => {
    const btn = e.target.closest('button[data-view]');
    if(!btn) return;
    state.view = btn.dataset.view;
    if(state.view === 'day') state.sel = state.ref;
    render();
  });
  const calGrid = document.getElementById('calGrid');
  if(calGrid) calGrid.addEventListener('click', e => {
    const c = e.target.closest('.cal-cell');
    if(!c) return;
    state.sel = c.dataset.iso;
    render();
  });
  const prevBtn = document.getElementById('prevBtn');
  const nextBtn = document.getElementById('nextBtn');
  if(prevBtn) prevBtn.addEventListener('click', () => step(-1));
  if(nextBtn) nextBtn.addEventListener('click', () => step(1));
  const csInput = document.getElementById('csInput');
  const ceInput = document.getElementById('ceInput');
  if(csInput) csInput.addEventListener('change', e => { state.cs = e.target.value; render(); });
  if(ceInput) ceInput.addEventListener('change', e => { state.ce = e.target.value; render(); });
}

render();
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
