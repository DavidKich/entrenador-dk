#!/usr/bin/env python3
"""
fetch_data.py — Trae datos reales de Garmin Connect (recuperacion +
actividades) y (best-effort) TrainingPeaks, y los deja en formato listo
para build_data.py.

Disenado para correr en GitHub Actions cada 6 horas (ver
.github/workflows/update-dashboard.yml), pero tambien corre en local para
probar. Todas las credenciales se leen UNICAMENTE de variables de entorno
-- nunca se hardcodean, nunca se imprimen, nunca se guardan en un archivo
que se vaya a commitear.

Variables de entorno esperadas:
  GARMIN_USER, GARMIN_PASS                (obligatorias)
  TRAININGPEAKS_USER, TRAININGPEAKS_PASS  (opcionales)

Politica de fallos (a peticion explicita, ver README):
  - Si falla Garmin: el script se detiene con exit code 1 y un error
    visible (::error:: en la sintaxis de anotaciones de GitHub Actions)
    -- es la fuente que mas importa, no se debe generar un dashboard con
    datos viejos sin que quede claro que algo se rompio.
  - Si falla TrainingPeaks (integracion no oficial, mas fragil, y el plan
    cambia poco): se avisa con ::warning:: pero el script sigue. Se
    reusa el plan de la ultima corrida exitosa leyendo el data.json ya
    commiteado en el repo, en vez de dejar el plan vacio.

Salida (en --out-dir, por defecto "live/" -- ver .gitignore, no se
commitea el contenido crudo, solo el data.json/dashboard.html finales):
  live/garmin.csv
  live/garmin_activities.json
  live/trainingpeaks.csv

Uso local:
    export GARMIN_USER=... GARMIN_PASS=...
    python fetch_data.py
"""

import argparse
import csv
import json
import os
import pathlib
import sys
from datetime import date, datetime, timedelta

import requests


TP_FIELDS = ["date", "title", "workout_type", "planned_distance_km", "planned_duration_min", "planned_tss", "notes"]
GARMIN_FIELDS = ["date", "sleep_hours", "sleep_score", "hrv", "body_battery", "stress_avg", "symptoms"]


def warn(msg):
    print(f"::warning::{msg}")


def fail(msg):
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def require_env(name):
    v = os.environ.get(name)
    if not v:
        fail(f"Falta la variable de entorno {name}. Configurala como GitHub Actions secret "
             "(o export local para pruebas) -- ver README.md.")
    return v


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Garmin Connect (via la libreria no oficial `garminconnect`)
# ---------------------------------------------------------------------------

def login_garmin(email, password):
    from garminconnect import Garmin

    client = Garmin(email, password)
    try:
        client.login()
    except Exception as e:
        raise RuntimeError(
            f"login fallido ({e}). Si tu cuenta de Garmin tiene verificacion en "
            "dos pasos (2FA) activada, el login automatico no puede completarla "
            "-- usa una cuenta sin 2FA para este proposito, o desactivalo."
        ) from e
    return client


def fetch_garmin(client, start, end, out_path):
    """Trae sueno / HRV / Body Battery / estres dia por dia.

    Nota: los nombres de campo dentro de las respuestas de Garmin
    Connect (dailySleepDTO, hrvSummary, bodyBatteryValuesArray, etc.)
    vienen de la forma en que la libreria garminconnect expone hoy la
    API interna de Garmin -- pueden cambiar si Garmin actualiza su API
    o la libreria se actualiza. Cada metrica esta en su propio
    try/except para que un cambio de forma en UNA metrica no tire todo
    el dia ni la corrida completa.
    """
    rows = []
    d = start
    while d <= end:
        ds = d.isoformat()
        row = {"date": ds, "sleep_hours": "", "sleep_score": "", "hrv": "", "body_battery": "", "stress_avg": "", "symptoms": ""}

        try:
            sleep = client.get_sleep_data(ds) or {}
            dto = sleep.get("dailySleepDTO", {}) or {}
            secs = dto.get("sleepTimeSeconds")
            if secs:
                row["sleep_hours"] = round(secs / 3600, 2)
            score = ((dto.get("sleepScores") or {}).get("overall") or {}).get("value")
            if score is not None:
                row["sleep_score"] = score
        except Exception as e:
            warn(f"Garmin sueno {ds}: {e}")

        try:
            hrv = client.get_hrv_data(ds) or {}
            val = (hrv.get("hrvSummary") or {}).get("lastNightAvg")
            if val is not None:
                row["hrv"] = val
        except Exception as e:
            warn(f"Garmin HRV {ds}: {e}")

        try:
            bb = client.get_body_battery(ds, ds)
            if bb and isinstance(bb, list):
                arr = (bb[0] or {}).get("bodyBatteryValuesArray") or []
                vals = [v[1] for v in arr if isinstance(v, list) and len(v) > 1 and v[1] is not None]
                if vals:
                    row["body_battery"] = vals[0]
        except Exception as e:
            warn(f"Garmin body battery {ds}: {e}")

        try:
            stress = client.get_stress_data(ds) or {}
            avg = stress.get("avgStressLevel")
            if avg is not None and avg >= 0:
                row["stress_avg"] = avg
        except Exception as e:
            warn(f"Garmin estres {ds}: {e}")

        rows.append(row)
        d += timedelta(days=1)

    write_csv(out_path, rows, GARMIN_FIELDS)
    return len(rows)


# ---------------------------------------------------------------------------
# Garmin Connect -- actividades reales completadas (reemplaza a Strava)
# ---------------------------------------------------------------------------

# Normaliza el typeKey interno de Garmin a los mismos valores que build_data.py
# ya sabe clasificar (ver STRENGTH_KEYWORDS / "run"|"ride"|"swim" en build_data.py).
GARMIN_SPORT_MAP = {
    "running": "Run", "trail_running": "Run", "treadmill_running": "Run",
    "cycling": "Ride", "road_biking": "Ride", "indoor_cycling": "Ride", "mountain_biking": "Ride",
    "lap_swimming": "Swim", "open_water_swimming": "Swim",
    "strength_training": "WeightTraining",
    "walking": "Walk", "hiking": "Hike",
}


def fetch_garmin_activities(client, start, end, out_path):
    """Trae actividades completadas dia por dia (nombre, distancia, ritmo,
    tipo, esfuerzo) via `get_activities_by_date` -- reemplaza lo que antes
    daba Strava. `activityTrainingLoad` es el proxy de Garmin para carga /
    esfuerzo relativo por sesion (equivalente al Relative Effort de Strava).
    """
    raw = client.get_activities_by_date(start.isoformat(), end.isoformat())

    out = []
    for a in raw:
        type_key = ((a.get("activityType") or {}).get("typeKey") or "").lower()
        sport_type = GARMIN_SPORT_MAP.get(type_key, type_key.title() or "Other")

        relative_effort = a.get("activityTrainingLoad")
        if relative_effort is None:
            aerobic = a.get("aerobicTrainingEffect") or 0
            anaerobic = a.get("anaerobicTrainingEffect") or 0
            relative_effort = round((aerobic + anaerobic) * 10, 1) or None

        out.append({
            "id": a.get("activityId"),
            "name": a.get("activityName", ""),
            "description": "",
            "sport_type": sport_type,
            "start_date_local": (a.get("startTimeLocal") or "").replace(" ", "T"),
            "summary": {
                "distance_m": a.get("distance"),
                "moving_time_s": a.get("movingDuration") or a.get("duration"),
                "elapsed_time_s": a.get("elapsedDuration") or a.get("duration"),
                "elevation_gain_m": a.get("elevationGain"),
                "avg_speed_mps": a.get("averageSpeed"),
                "max_speed_mps": a.get("maxSpeed"),
                "calories": a.get("calories"),
                "relative_effort": relative_effort,
            },
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"activities": out}, f, ensure_ascii=False, indent=2)
    return len(out)


# ---------------------------------------------------------------------------
# TrainingPeaks -- NO OFICIAL, best-effort (ver aviso en el docstring del
# modulo y en el README). TrainingPeaks no publica una API para cuentas
# individuales; esto reproduce el login/consulta que usa su propia web app,
# obtenido por ingenieria inversa de la comunidad. Puede romperse sin aviso
# si TrainingPeaks cambia su sitio -- por eso NO es una fuente fatal.
# ---------------------------------------------------------------------------

TP_OAUTH_URL = os.environ.get("TRAININGPEAKS_OAUTH_URL", "https://oauth.trainingpeaks.com/oauth/token")
TP_API_BASE = os.environ.get("TRAININGPEAKS_API_BASE", "https://tpapi.trainingpeaks.com")
# client_id publico usado historicamente por la web app de TrainingPeaks
# (no es secreto -- viaja en el JS de su propio sitio) -- reportado por
# proyectos no oficiales de la comunidad. NO esta verificado para la fecha
# de hoy; si TrainingPeaks lo rota, sobreescribe con el secret
# TRAININGPEAKS_CLIENT_ID.
TP_CLIENT_ID = os.environ.get("TRAININGPEAKS_CLIENT_ID", "xc7bMHms2vpwsvbGpaqm9tdIVwn5DXie")


def fetch_trainingpeaks(username, password, start, end, out_path):
    session = requests.Session()

    resp = session.post(TP_OAUTH_URL, data={
        "grant_type": "password",
        "username": username,
        "password": password,
        "client_id": TP_CLIENT_ID,
    }, timeout=20)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = session.get(f"{TP_API_BASE}/users/v3/user", headers=headers, timeout=20)
    me.raise_for_status()
    athlete_id = me.json()["user"]["userId"]

    wk = session.get(
        f"{TP_API_BASE}/fitness/v1/athletes/{athlete_id}/workouts/{start.isoformat()}/{end.isoformat()}",
        headers=headers, timeout=20,
    )
    wk.raise_for_status()
    workouts = wk.json()
    if not isinstance(workouts, list):
        raise RuntimeError(f"forma de respuesta inesperada (no es una lista): {type(workouts)}")

    rows = []
    for w in workouts:
        d = (w.get("workoutDay") or "")[:10]
        if not d:
            continue
        planned_distance_m = w.get("distancePlanned")
        planned_hours = w.get("totalTimePlanned")
        rows.append({
            "date": d,
            "title": w.get("title") or "",
            "workout_type": w.get("workoutTypeValueId") or w.get("workoutType") or "",
            "planned_distance_km": round(planned_distance_m / 1000, 2) if planned_distance_m else "",
            "planned_duration_min": round(planned_hours * 60, 1) if planned_hours else "",
            "planned_tss": w.get("tssPlanned") or "",
            "notes": w.get("coachComments") or w.get("description") or "",
        })

    write_csv(out_path, rows, TP_FIELDS)
    return len(rows)


def fallback_trainingpeaks_csv(previous_data_path, out_path):
    """Cuando falla el fetch de TrainingPeaks, reconstruye el CSV del plan
    a partir del ultimo data.json commiteado (que ya vive en el repo, asi
    que persiste entre corridas del Action aunque live/ no se commitee)."""
    rows = []
    if previous_data_path.exists():
        try:
            prev = json.loads(previous_data_path.read_text(encoding="utf-8"))
            for d, day in sorted((prev.get("days") or {}).items()):
                plan = day.get("plan")
                if not plan:
                    continue
                rows.append({
                    "date": d,
                    "title": plan.get("title", ""),
                    "workout_type": plan.get("workout_type", ""),
                    "planned_distance_km": plan.get("planned_distance_km") or "",
                    "planned_duration_min": plan.get("planned_duration_min") or "",
                    "planned_tss": plan.get("planned_tss") or "",
                    "notes": plan.get("notes", ""),
                })
        except Exception as e:
            warn(f"No se pudo leer {previous_data_path} para reusar el plan anterior: {e}")
    write_csv(out_path, rows, TP_FIELDS)
    return len(rows)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="live", help="Carpeta de salida (no se commitea, ver .gitignore)")
    ap.add_argument("--days", type=int, default=35, help="Dias hacia atras a traer de Garmin (recuperacion + actividades)")
    ap.add_argument("--plan-days-ahead", type=int, default=14, help="Dias hacia adelante a traer del plan de TrainingPeaks")
    ap.add_argument("--previous-data", default="data.json", help="data.json ya commiteado, usado como respaldo si falla TrainingPeaks")
    ap.add_argument("--skip-garmin", action="store_true",
                     help="No trae datos de Garmin (recuperacion + actividades) -- no exige GARMIN_USER/GARMIN_PASS. Util para probar TrainingPeaks solo.")
    ap.add_argument("--skip-trainingpeaks", action="store_true",
                     help="No trae el plan de TrainingPeaks -- no exige TRAININGPEAKS_USER/TRAININGPEAKS_PASS ni reusa el plan anterior. Util para probar Garmin solo.")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    today = date.today()
    start = today - timedelta(days=args.days)

    if args.skip_garmin:
        print("Garmin: --skip-garmin, se omite.")
    else:
        garmin_user = require_env("GARMIN_USER")
        garmin_pass = require_env("GARMIN_PASS")
        try:
            client = login_garmin(garmin_user, garmin_pass)
            n = fetch_garmin(client, start, today, out_dir / "garmin.csv")
            print(f"Garmin OK: {n} dias -> {out_dir / 'garmin.csv'}")
            n = fetch_garmin_activities(client, start, today, out_dir / "garmin_activities.json")
            print(f"Garmin actividades OK: {n} actividades -> {out_dir / 'garmin_activities.json'}")
        except Exception as e:
            fail(f"Fallo Garmin Connect: {e}")

    if args.skip_trainingpeaks:
        print("TrainingPeaks: --skip-trainingpeaks, se omite.")
    else:
        tp_user = os.environ.get("TRAININGPEAKS_USER")
        tp_pass = os.environ.get("TRAININGPEAKS_PASS")
        tp_out = out_dir / "trainingpeaks.csv"
        if not tp_user or not tp_pass:
            warn("TRAININGPEAKS_USER/TRAININGPEAKS_PASS no configurados -- se reusa el plan anterior.")
            n = fallback_trainingpeaks_csv(pathlib.Path(args.previous_data), tp_out)
            print(f"TrainingPeaks: sin credenciales, {n} sesiones reusadas del data.json anterior -> {tp_out}")
        else:
            try:
                n = fetch_trainingpeaks(tp_user, tp_pass, start, today + timedelta(days=args.plan_days_ahead), tp_out)
                print(f"TrainingPeaks OK: {n} sesiones -> {tp_out}")
            except Exception as e:
                warn(f"Fallo TrainingPeaks (integracion no oficial, puede romperse sin aviso "
                     f"si cambian su sitio): {e}. Se reusa el plan de la ultima corrida exitosa.")
                n = fallback_trainingpeaks_csv(pathlib.Path(args.previous_data), tp_out)
                print(f"TrainingPeaks: {n} sesiones reusadas del data.json anterior -> {tp_out}")

    print("fetch_data.py: listo.")


if __name__ == "__main__":
    main()
