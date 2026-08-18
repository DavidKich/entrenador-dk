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

### `fetch_data.py`

Trae datos reales de Garmin Connect, Strava y (best-effort) TrainingPeaks, y
los deja listos para `build_data.py`. Pensado para correr en GitHub Actions
cada 6 horas (ver abajo), pero tambien corre en local para probar.

**Credenciales solo por variable de entorno — nunca en el codigo, nunca en
un archivo que se commitee** (ver `.gitignore`):

```
export GARMIN_USER=tu-correo@ejemplo.com
export GARMIN_PASS=tu-password
export STRAVA_CLIENT_ID=...
export STRAVA_CLIENT_SECRET=...
export STRAVA_REFRESH_TOKEN=...
# opcionales -- si no estan, se reusa el plan de la ultima corrida exitosa:
export TRAININGPEAKS_USER=tu-correo@ejemplo.com
export TRAININGPEAKS_PASS=tu-password

python fetch_data.py
python build_data.py --trainingpeaks live/trainingpeaks.csv --garmin live/garmin.csv --strava live/strava.json --out data.json
python render_html.py --data data.json --out dashboard.html
```

**Politica de fallos:**
- Garmin o Strava fallan → el script se detiene (`exit 1`), no se toca
  `data.json`/`dashboard.html`. Son las fuentes que mas importan.
- TrainingPeaks falla → solo se avisa (es una integracion no oficial, mas
  fragil, y el plan cambia poco) y se reusa el plan de la ultima corrida
  exitosa leyendo el `data.json` ya commiteado, en vez de dejarlo vacio.

**Garmin y 2FA:** si tu cuenta tiene verificacion en dos pasos activada, el
login automatico no la puede completar. Usa una cuenta de Garmin sin 2FA
para esto, o desactivalo en la cuenta que uses.

**TrainingPeaks (best-effort, no oficial):** TrainingPeaks no publica una
API para cuentas individuales — `fetch_data.py` reproduce el login/consulta
que usa su propia web app (ingenieria inversa de la comunidad). Puede
romperse sin aviso si TrainingPeaks cambia su sitio; por eso su fallo no
detiene el resto del pipeline. Pruebalo en local primero (`python
fetch_data.py`) para confirmar que sigue funcionando antes de confiar en el
cron.

## Automatizacion (GitHub Actions)

`.github/workflows/update-dashboard.yml` corre cada 6 horas (y tambien se
puede disparar manualmente desde la pestaña **Actions** del repo → *Actualizar
dashboard* → *Run workflow*): ejecuta `fetch_data.py` → `build_data.py` →
`render_html.py`, y si `data.json`/`dashboard.html` cambiaron, hace commit y
push automaticamente (eso dispara el redeploy en Vercel).

### Configurar los secrets

Los secrets se configuran una sola vez, directamente en GitHub (yo no los
necesito ni los veo): en el repo, **Settings → Secrets and variables →
Actions → New repository secret**, y agrega uno por uno:

| Secret | Obligatorio | De donde sale |
|---|---|---|
| `GARMIN_USER` | Si | El correo con el que entras a Garmin Connect |
| `GARMIN_PASS` | Si | Tu password de Garmin Connect (cuenta sin 2FA, ver arriba) |
| `STRAVA_CLIENT_ID` | Si | Ver "Obtener credenciales de Strava" abajo |
| `STRAVA_CLIENT_SECRET` | Si | Ver "Obtener credenciales de Strava" abajo |
| `STRAVA_REFRESH_TOKEN` | Si | Ver "Obtener credenciales de Strava" abajo |
| `TRAININGPEAKS_USER` | No | El correo con el que entras a TrainingPeaks |
| `TRAININGPEAKS_PASS` | No | Tu password de TrainingPeaks |

### Obtener credenciales de Strava

Strava si tiene una API oficial (a diferencia de TrainingPeaks), pero usa
OAuth2 en vez de usuario/password, asi que hay un paso manual de
autorizacion **una sola vez**:

1. Ve a <https://www.strava.com/settings/api> y crea una aplicacion (el
   nombre/website/callback domain no importan mucho para uso personal — como
   callback domain puedes poner `localhost`). Te da un **Client ID** y un
   **Client Secret** → esos van directo a los secrets `STRAVA_CLIENT_ID` /
   `STRAVA_CLIENT_SECRET`.
2. Abre esta URL en el navegador, remplazando `TU_CLIENT_ID` (deja el resto
   igual):
   ```
   https://www.strava.com/oauth/authorize?client_id=TU_CLIENT_ID&redirect_uri=http://localhost&response_type=code&scope=activity:read_all
   ```
3. Autoriza la app. Te va a redirigir a una URL tipo
   `http://localhost/?state=&code=ABC123...&scope=...` que probablemente
   marque error de conexion en el navegador — no importa, lo que necesitas
   es el valor de `code=` en esa URL.
4. Cambia ese `code` por un `refresh_token` corriendo esto (con `curl`, o
   pidele a Claude Code que lo corra por ti si le pasas el `code`):
   ```
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=TU_CLIENT_ID \
     -d client_secret=TU_CLIENT_SECRET \
     -d code=EL_CODE_DEL_PASO_3 \
     -d grant_type=authorization_code
   ```
   La respuesta trae un `refresh_token` → eso va al secret
   `STRAVA_REFRESH_TOKEN`.

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
`dashboard.html` actualizado (ya sea manual o desde el GitHub Action de
arriba) dispara un redeploy automatico una vez conectado.

## Seguridad (repo publico)

- Ninguna credencial vive en el codigo ni en archivos commiteados —
  `fetch_data.py` solo lee de variables de entorno, y en GitHub Actions esas
  variables vienen de *Secrets* (nunca se imprimen en los logs).
- `.gitignore` bloquea `live/` (los CSV/JSON crudos de cada corrida) y
  cualquier archivo que luzca a credencial/token/sesion, para que no se suba
  por accidente.
- El Action usa el `GITHUB_TOKEN` que GitHub genera automaticamente para
  cada corrida (con permiso `contents: write`) para hacer el commit/push —
  no hace falta crear ni guardar un token de acceso personal.
