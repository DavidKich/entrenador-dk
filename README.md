# entrenador-dk

Dashboard web del entrenador virtual de maraton. Combina el plan de
TrainingPeaks, la recuperacion de Garmin y las actividades reales de Strava
en un dashboard HTML autocontenido (sin dependencias externas).

Reglas de entrenamiento/nutricion/recuperacion: `entrenador-virtual-maraton.md`
(fuera de este repo). Spec funcional del dashboard: `spec-dashboard-web.md`
(fuera de este repo).

## Scripts

### `build_data.py`

Combina las 3 fuentes en `data.json`.

```
python build_data.py \
  --trainingpeaks trainingpeaks.csv \
  --garmin garmin.csv \
  --strava strava.json \
  [--daily-log daily-log.md] \
  [--race-date 2026-09-27] \
  [--goal-time 3:40:00] \
  [--out data.json]
```

**TrainingPeaks CSV** (el plan — que toca cada dia, no se usa como carga
dia a dia):
`date, title, workout_type, planned_distance_km, planned_duration_min, planned_tss, notes`

**Garmin CSV** (sueno / HRV / Body Battery / estres):
`date, sleep_hours, sleep_score, hrv, body_battery, stress_avg, symptoms`

`symptoms` es opcional — si tiene texto, el dia nunca sugiere sauna/cold
plunge y en vez de eso marca "consulta a un profesional", segun la regla de
seguridad de la seccion 4 del brief.

**Strava JSON** (formato de `mcp__Strava__list_activities`): lista de
actividades, o `{"activities": [...]}`. Cada actividad con
`id, name, description, sport_type, start_date_local` y datos resumen de
distancia/tiempo/`relative_effort`/`kudos_count`/`pr_count`/`achievement_count`
(anidados en `summary` o aplanados — el parser acepta ambos).

`--daily-log` es opcional: si le pasas la bitacora `MaratonCoach/daily-log.md`
del agente (con headers `## YYYY-MM-DD` y sub-headers `### Mañana` /
`### Mediodía` / `### Noche`), esos textos alimentan el "registro de
recomendaciones del dia" (seccion 3.3 del spec). Sin este archivo, esa
seccion queda vacia por dia.

### `render_html.py`

Lee `data.json` y genera `dashboard.html` (CSS/JS inline, sin CDN).

```
python render_html.py --data data.json --out dashboard.html
```

## Datos de ejemplo

`mock/` tiene un set de datos ficticios (4 semanas, incluye un dia con
sintomas reportados, un dia con caida marcada de HRV/Body Battery, y una
sesion no ejecutada) para probar el pipeline sin datos reales:

```
python build_data.py --trainingpeaks mock/trainingpeaks.csv --garmin mock/garmin.csv --strava mock/strava.json --daily-log mock/daily-log.md --out data.json
python render_html.py --data data.json --out dashboard.html
```

## Hosting

Vercel se conecta manualmente desde vercel.com importando este repo — no
esta configurado desde el pipeline. Cada `push` a este repo con un
`dashboard.html` actualizado dispara un redeploy automatico una vez
conectado.
