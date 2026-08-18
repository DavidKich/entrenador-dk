#!/usr/bin/env python3
"""
build_data.py — Combina plan (TrainingPeaks CSV), metricas de recuperacion
(Garmin CSV) y actividades reales (Strava JSON) en un solo data.json que
consume render_html.py.

Uso:
    python build_data.py \
        --trainingpeaks trainingpeaks.csv \
        --garmin garmin.csv \
        --strava strava.json \
        [--daily-log daily-log.md] \
        [--race-date 2026-09-27] \
        [--goal-time 3:40:00] \
        [--out data.json]

Formatos de entrada esperados (ver README.md para detalle y alias de columnas):

  TrainingPeaks CSV (el plan — que toca cada dia):
    date, title, workout_type, planned_distance_km, planned_duration_min,
    planned_tss, notes

  Garmin CSV (sueno / HRV / Body Battery / estres):
    date, sleep_hours, sleep_score, hrv, body_battery, stress_avg, symptoms

  Strava JSON (formato de mcp__Strava__list_activities): lista de actividades
  (o {"activities": [...]}), cada una con id/name/description/sport_type/
  start_date_local y datos resumen de distancia, tiempo, relative_effort,
  kudos_count, pr_count, achievement_count. El parser acepta tanto campos
  anidados bajo "summary" como aplanados en el objeto raiz.

Nada de esto usa el TSS de TrainingPeaks como metrica de carga dia a dia:
la carga semanal se deriva del esfuerzo (Relative Effort) de Strava, tal
como pide la seccion 4 del brief y la seccion 3.4 del spec del dashboard.
"""

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------

def _get(d, *keys, default=None):
    """Busca la primera key presente (case-insensitive) en un dict."""
    lower = {str(k).strip().lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, ""):
            return v
    return default


def _to_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return default


def parse_date(v):
    """Acepta 'YYYY-MM-DD' o timestamps ISO ('...T07:00:00')."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = s[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def iso_week_start(d):
    return d - timedelta(days=d.weekday())  # lunes


# ---------------------------------------------------------------------------
# 1. TrainingPeaks CSV -> plan por dia
# ---------------------------------------------------------------------------

QUALITY_KEYWORDS = [
    "tempo", "umbral", "threshold", "interval", "intervalo", "series",
    "fartlek", "vo2", "repeticiones", "cuestas", "hill",
]
STRENGTH_KEYWORDS = ["strength", "fuerza", "gym", "gimnasio", "weight"]
REST_KEYWORDS = ["rest", "descanso", "off"]
LONG_RUN_KEYWORDS = ["long run", "rodaje largo", "larga", "long"]


def load_trainingpeaks(path):
    plan_by_date = {}
    if not path:
        return plan_by_date
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = parse_date(_get(row, "date", "workoutday"))
            if not d:
                continue
            planned_distance_km = _to_float(
                _get(row, "planned_distance_km", "plannedDistanceKM", "distanceplanned")
            )
            planned_duration_min = _to_float(
                _get(row, "planned_duration_min", "plannedDurationMin", "timeplanned")
            )
            planned_tss = _to_float(_get(row, "planned_tss", "plannedTSS", "tssplanned"))
            plan_by_date[d.isoformat()] = {
                "title": _get(row, "title", default=""),
                "workout_type": _get(row, "workout_type", "type", default=""),
                "planned_distance_km": planned_distance_km,
                "planned_duration_min": planned_duration_min,
                "planned_tss": planned_tss,  # solo referencia, no se usa para la grafica de carga
                "notes": _get(row, "notes", "description", "coachcomments", default=""),
            }
    return plan_by_date


# ---------------------------------------------------------------------------
# 2. Garmin CSV -> metricas de recuperacion por dia
# ---------------------------------------------------------------------------

def load_garmin(path):
    garmin_by_date = {}
    if not path:
        return garmin_by_date
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = parse_date(_get(row, "date"))
            if not d:
                continue
            garmin_by_date[d.isoformat()] = {
                "sleep_hours": _to_float(_get(row, "sleep_hours", "sleep")),
                "sleep_score": _to_float(_get(row, "sleep_score")),
                "hrv": _to_float(_get(row, "hrv", "hrv_ms")),
                "body_battery": _to_float(_get(row, "body_battery", "body_battery_am")),
                "stress_avg": _to_float(_get(row, "stress_avg", "stress")),
                "symptoms": _get(row, "symptoms", "notas", default="") or "",
            }
    return garmin_by_date


# ---------------------------------------------------------------------------
# 3. Strava JSON -> actividades reales por dia
# ---------------------------------------------------------------------------

def _activity_field(act, *keys, default=None):
    summary = act.get("summary", {}) if isinstance(act.get("summary"), dict) else {}
    for k in keys:
        if k in act and act[k] not in (None, ""):
            return act[k]
        if k in summary and summary[k] not in (None, ""):
            return summary[k]
    return default


def load_strava(path):
    activities_by_date = defaultdict(list)
    if not path:
        return activities_by_date
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        activities = raw.get("activities", raw.get("data", []))
    else:
        activities = raw

    for act in activities:
        start = act.get("start_date_local") or act.get("start_date")
        d = parse_date(start)
        if not d:
            continue

        distance_m = _to_float(_activity_field(act, "distance_m", "distance"), default=0.0)
        moving_s = _to_float(_activity_field(act, "moving_time_s", "moving_time"), default=0.0)
        elapsed_s = _to_float(_activity_field(act, "elapsed_time_s", "elapsed_time"), default=moving_s)
        relative_effort = _to_float(
            _activity_field(act, "relative_effort", "suffer_score", "effort_score")
        )
        kudos = int(_to_float(_activity_field(act, "kudos_count", "kudos"), default=0) or 0)
        pr_count = int(_to_float(_activity_field(act, "pr_count", "pr_effort_count"), default=0) or 0)
        achievements = int(
            _to_float(_activity_field(act, "achievement_count"), default=0) or 0
        )
        avg_speed = _to_float(_activity_field(act, "avg_speed_mps", "average_speed"))

        distance_km = round(distance_m / 1000.0, 2) if distance_m else 0.0
        moving_min = round(moving_s / 60.0, 1) if moving_s else 0.0

        pace_min_per_km = None
        if distance_km and moving_min:
            pace_min_per_km = round(moving_min / distance_km, 2)

        activities_by_date[d.isoformat()].append({
            "id": act.get("id"),
            "name": act.get("name", ""),
            "description": act.get("description", "") or "",
            "sport_type": act.get("sport_type") or act.get("type") or "",
            "start_date_local": start,
            "distance_km": distance_km,
            "moving_time_min": moving_min,
            "elapsed_time_min": round(elapsed_s / 60.0, 1) if elapsed_s else moving_min,
            "pace_min_per_km": pace_min_per_km,
            "avg_speed_mps": avg_speed,
            "relative_effort": relative_effort,
            "kudos": kudos,
            "pr_count": pr_count,
            "achievement_count": achievements,
        })
    return activities_by_date


# ---------------------------------------------------------------------------
# 4. daily-log.md (opcional) -> registro de recomendaciones por checkpoint
# ---------------------------------------------------------------------------

DAY_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})", re.MULTILINE)
CHECKPOINT_HEADER_RE = re.compile(r"^###\s*(.+)$", re.MULTILINE)


def load_daily_log(path):
    """Parsea un daily-log.md con formato:

        ## 2026-08-10
        ### Manana
        texto...
        ### Mediodia
        texto...
        ### Noche
        texto...

    en {date: [{"checkpoint": "Manana", "text": "..."}, ...]}
    """
    log_by_date = {}
    if not path:
        return log_by_date
    with open(path, encoding="utf-8") as f:
        content = f.read()

    day_matches = list(DAY_HEADER_RE.finditer(content))
    for i, m in enumerate(day_matches):
        d = m.group(1)
        start = m.end()
        end = day_matches[i + 1].start() if i + 1 < len(day_matches) else len(content)
        block = content[start:end]

        cp_matches = list(CHECKPOINT_HEADER_RE.finditer(block))
        entries = []
        if cp_matches:
            for j, cm in enumerate(cp_matches):
                cp_name = cm.group(1).strip()
                cstart = cm.end()
                cend = cp_matches[j + 1].start() if j + 1 < len(cp_matches) else len(block)
                text = block[cstart:cend].strip()
                if text:
                    entries.append({"checkpoint": cp_name, "text": text})
        else:
            text = block.strip()
            if text:
                entries.append({"checkpoint": "Resumen del dia", "text": text})
        log_by_date[d] = entries
    return log_by_date


# ---------------------------------------------------------------------------
# 5. Clasificacion de sesiones (seccion 4 del brief)
# ---------------------------------------------------------------------------

def classify_session(plan, activities):
    """Devuelve uno de: long_run, quality, easy, strength, rest, other."""
    title_notes = ""
    workout_type = ""
    planned_duration = None
    if plan:
        title_notes = f"{plan.get('title','')} {plan.get('notes','')}".lower()
        workout_type = (plan.get("workout_type") or "").lower()
        planned_duration = plan.get("planned_duration_min")

    if any(k in workout_type for k in STRENGTH_KEYWORDS) or any(
        k in title_notes for k in STRENGTH_KEYWORDS
    ):
        return "strength"

    if any(k in workout_type for k in REST_KEYWORDS) and not activities:
        return "rest"

    if any(k in title_notes for k in QUALITY_KEYWORDS):
        return "quality"

    if planned_duration and planned_duration >= 90:
        return "long_run"
    if any(k in title_notes for k in LONG_RUN_KEYWORDS):
        return "long_run"

    if not plan and not activities:
        return "rest"

    if activities:
        primary = max(activities, key=lambda a: a.get("moving_time_min") or 0)
        sport = (primary.get("sport_type") or "").lower()
        if any(k in sport for k in STRENGTH_KEYWORDS) or "weighttraining" in sport:
            return "strength"
        if (primary.get("moving_time_min") or 0) >= 90:
            return "long_run"
        name_desc = f"{primary.get('name','')} {primary.get('description','')}".lower()
        if any(k in name_desc for k in QUALITY_KEYWORDS):
            return "quality"
        if "run" in sport or "ride" in sport or "swim" in sport:
            return "easy"

    if workout_type:
        return "easy"

    return "other"


# ---------------------------------------------------------------------------
# 6. Sugerencia de sauna / cold plunge (seccion 4 del brief)
# ---------------------------------------------------------------------------

SAFETY_NOTE = (
    "Orientacion general basada en literatura de recuperacion deportiva, no "
    "consejo medico. Si tienes mareo, sintomas de enfermedad, o alguna "
    "condicion cardiaca, de presion o circulatoria, consultalo con un "
    "profesional antes de sauna o cold plunge."
)


def days_to_race(d, race_date):
    return (race_date - d).days


def suggest_recovery(d, session_type, symptoms, race_date, week_recovery_count, is_evening_strength=False):
    """Devuelve dict con la sugerencia de recuperacion para el dia `d`.

    Sigue la logica de la seccion 4 del brief:
    - nunca recomendar si hay sintomas (bandera para consultar medico)
    - contrast therapy / sauna sola / cold plunge sola son todas validas
    - horario preferido: manana, despues de entrenar
    - en taper (ultimas 1-2 semanas) se reduce frecuencia
    - despues de sesion de fuerza: cold plunge el mismo dia puede atenuar
      adaptacion -> se sugiere para el dia siguiente en vez de hoy
    - despues de carrera larga o sesion de calidad de resistencia: cold
      plunge o contrast el mismo dia son buenas opciones (evidencia menos
      concluyente de que atenue adaptacion en resistencia pura)
    """
    if symptoms:
        return {
            "recommendation": "consulta_medica",
            "timing": None,
            "detail": (
                f"Reportaste: \"{symptoms}\". No se sugiere sauna ni cold "
                "plunge hoy — consulta a un profesional antes de continuar "
                "con el protocolo."
            ),
            "safety_note": SAFETY_NOTE,
        }

    dtr = days_to_race(d, race_date)
    in_taper = 0 <= dtr <= 14

    if in_taper:
        if session_type in ("rest", "easy"):
            return {
                "recommendation": "sauna",
                "timing": "manana",
                "detail": (
                    "Semana de taper: se reduce frecuencia de calor/frio. "
                    "Sauna sola (10-20 min) por la manana, sin cold plunge, "
                    "para no sumar fatiga por calor cerca de la carrera."
                ),
                "safety_note": SAFETY_NOTE,
            }
        return {
            "recommendation": "ninguna",
            "timing": None,
            "detail": (
                "Semana de taper: se evita sauna/cold plunge hoy — el "
                "cuerpo esta en fase de afinar, no de generar mas estres."
            ),
            "safety_note": SAFETY_NOTE,
        }

    if session_type == "strength":
        return {
            "recommendation": "sauna_hoy",
            "timing": "manana",
            "detail": (
                "Dia de fuerza: cold plunge inmediato puede atenuar la "
                "adaptacion de hipertrofia — mas conservador dejarlo para "
                "manana. Si quieres, sauna sola hoy esta bien para relajar."
            ),
            "safety_note": SAFETY_NOTE,
        }

    if session_type in ("quality", "long_run"):
        if week_recovery_count >= 4:
            return {
                "recommendation": "ninguna",
                "timing": None,
                "detail": "Ya van 4 sesiones de recuperacion por calor/frio esta semana — sin necesidad de mas hoy.",
                "safety_note": SAFETY_NOTE,
            }
        if is_evening_strength:
            timing = "noche"
            detail = (
                "Sesion de calidad/larga: contrast therapy o cold plunge "
                "el mismo dia ayuda a acelerar la recuperacion. Si es de "
                "noche, termina el ciclo con al menos 2 horas de margen "
                "antes de dormir."
            )
        else:
            timing = "manana"
            detail = (
                "Sesion de calidad/larga: contrast therapy (sauna 10-20 "
                "min + cold plunge 1-5 min, 2-4 ciclos terminando en frio) "
                "o cold plunge solo ayudan a acelerar la recuperacion antes "
                "de la siguiente sesion importante."
            )
        return {
            "recommendation": "contrast",
            "timing": timing,
            "detail": detail,
            "safety_note": SAFETY_NOTE,
        }

    if session_type in ("easy", "rest"):
        if week_recovery_count >= 4:
            return {
                "recommendation": "ninguna",
                "timing": None,
                "detail": "Ya van 4 sesiones de recuperacion por calor/frio esta semana — dia libre de protocolo.",
                "safety_note": SAFETY_NOTE,
            }
        return {
            "recommendation": "sauna_o_contrast",
            "timing": "manana",
            "detail": (
                "Dia facil o de descanso: buen momento por defecto para "
                "sauna sola (relajacion/sueno) o contrast therapy completa, "
                "por la manana despues de entrenar (o en la manana si es "
                "descanso)."
            ),
            "safety_note": SAFETY_NOTE,
        }

    return {
        "recommendation": "ninguna",
        "timing": None,
        "detail": "Sin sesion clasificada hoy — sin sugerencia especifica.",
        "safety_note": SAFETY_NOTE,
    }


# ---------------------------------------------------------------------------
# 7. Ensamblado principal
# ---------------------------------------------------------------------------

def build(trainingpeaks_path, garmin_path, strava_path, daily_log_path, race_date, goal_time, sleep_goal=(7, 8)):
    plan_by_date = load_trainingpeaks(trainingpeaks_path)
    garmin_by_date = load_garmin(garmin_path)
    strava_by_date = load_strava(strava_path)
    log_by_date = load_daily_log(daily_log_path)

    all_dates = sorted(
        set(plan_by_date) | set(garmin_by_date) | set(strava_by_date) | set(log_by_date)
    )
    if not all_dates:
        raise SystemExit("No se encontro ninguna fecha en las fuentes provistas.")

    # promedio de HRV de los ultimos 7 dias (excluyendo el dia actual) para
    # detectar caidas marcadas, tal como pide la seccion 4 del brief.
    hrv_series = {d: garmin_by_date[d].get("hrv") for d in garmin_by_date if garmin_by_date[d].get("hrv") is not None}

    def hrv_7d_avg(d_str):
        d = parse_date(d_str)
        window = []
        for i in range(1, 8):
            prev = (d - timedelta(days=i)).isoformat()
            if prev in hrv_series:
                window.append(hrv_series[prev])
        return round(statistics.mean(window), 1) if window else None

    days = {}
    week_recovery_counts = defaultdict(int)

    for d_str in all_dates:
        d = parse_date(d_str)
        plan = plan_by_date.get(d_str)
        activities = strava_by_date.get(d_str, [])
        garmin = garmin_by_date.get(d_str)

        session_type = classify_session(plan, activities)
        completed = bool(activities)

        has_evening_strength_note = False
        if plan and plan.get("notes"):
            has_evening_strength_note = "noche" in plan["notes"].lower() or "tarde" in plan["notes"].lower()

        week_key = iso_week_start(d).isoformat()

        symptoms = (garmin or {}).get("symptoms", "") if garmin else ""

        suggestion = suggest_recovery(
            d, session_type, symptoms, race_date,
            week_recovery_counts[week_key],
            is_evening_strength=has_evening_strength_note,
        )
        if suggestion["recommendation"] not in ("ninguna", "consulta_medica"):
            week_recovery_counts[week_key] += 1

        hrv_avg_7d = hrv_7d_avg(d_str)
        fatigue_flag = False
        if garmin and garmin.get("hrv") is not None and hrv_avg_7d is not None:
            hrv_drop = (hrv_avg_7d - garmin["hrv"]) / hrv_avg_7d if hrv_avg_7d else 0
            if hrv_drop >= 0.12 and (garmin.get("body_battery") or 100) < 40:
                fatigue_flag = True

        primary_activity = None
        if activities:
            primary_activity = max(activities, key=lambda a: a.get("moving_time_min") or 0)

        days[d_str] = {
            "date": d_str,
            "days_to_race": days_to_race(d, race_date),
            "plan": plan,
            "activities": activities,
            "primary_activity": primary_activity,
            "completed": completed,
            "session_type": session_type,
            "garmin": garmin,
            "hrv_7d_avg": hrv_avg_7d,
            "fatigue_flag": fatigue_flag,
            "recovery_suggestion": suggestion,
            "recommendations_log": log_by_date.get(d_str, []),
        }

    # --- agregados semanales (para 3.1 resumen y 3.4 grafica de carga) ---
    weeks_map = defaultdict(lambda: {
        "planned_km": 0.0, "actual_km": 0.0, "total_relative_effort": 0.0,
        "sleep_hours": [], "days": [],
    })
    for d_str, day in days.items():
        wk = iso_week_start(parse_date(d_str)).isoformat()
        w = weeks_map[wk]
        w["days"].append(d_str)
        if day["plan"] and day["plan"].get("planned_distance_km"):
            w["planned_km"] += day["plan"]["planned_distance_km"]
        for act in day["activities"]:
            w["actual_km"] += act.get("distance_km") or 0.0
            if act.get("relative_effort"):
                w["total_relative_effort"] += act["relative_effort"]
        if day["garmin"] and day["garmin"].get("sleep_hours") is not None:
            w["sleep_hours"].append(day["garmin"]["sleep_hours"])

    weeks = []
    for wk_start in sorted(weeks_map):
        w = weeks_map[wk_start]
        wk_end = (parse_date(wk_start) + timedelta(days=6)).isoformat()
        avg_sleep = round(statistics.mean(w["sleep_hours"]), 2) if w["sleep_hours"] else None
        weeks.append({
            "week_start": wk_start,
            "week_end": wk_end,
            "planned_km": round(w["planned_km"], 1),
            "actual_km": round(w["actual_km"], 1),
            "total_relative_effort": round(w["total_relative_effort"], 1),
            "avg_sleep_hours": avg_sleep,
            "days": sorted(w["days"]),
        })

    # --- resumen de semana actual (3.1) ---
    today = date.today()
    current_week_key = iso_week_start(today).isoformat()
    current_week = next((w for w in weeks if w["week_start"] == current_week_key), None)
    if current_week is None and weeks:
        current_week = weeks[-1]

    semaforo = "en_linea"
    if current_week and current_week["planned_km"] > 0:
        ratio = current_week["actual_km"] / current_week["planned_km"]
        if ratio < 0.85:
            semaforo = "atrasado"
        elif ratio > 1.15:
            semaforo = "adelantado"

    week_summary = {
        "days_to_race": days_to_race(today, race_date),
        "semaforo": semaforo,
        "planned_km": current_week["planned_km"] if current_week else 0,
        "actual_km": current_week["actual_km"] if current_week else 0,
        "avg_sleep_hours": current_week["avg_sleep_hours"] if current_week else None,
        "sleep_goal": list(sleep_goal),
        "week_start": current_week["week_start"] if current_week else None,
    }

    # --- tabla de sesiones recientes (3.5) ---
    recent_sessions = []
    for d_str in sorted(days, reverse=True):
        day = days[d_str]
        for act in day["activities"]:
            recent_sessions.append({
                "date": d_str,
                "session_type": day["session_type"],
                "name": act.get("name"),
                "sport_type": act.get("sport_type"),
                "distance_km": act.get("distance_km"),
                "pace_min_per_km": act.get("pace_min_per_km"),
                "relative_effort": act.get("relative_effort"),
                "pr_count": act.get("pr_count"),
                "kudos": act.get("kudos"),
                "achievement_count": act.get("achievement_count"),
            })
    recent_sessions = recent_sessions[:20]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "race_date": race_date.isoformat(),
        "goal_time": goal_time,
        "sleep_goal_hours": list(sleep_goal),
        "week_summary": week_summary,
        "weeks": weeks,
        "days": days,
        "recent_sessions": recent_sessions,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trainingpeaks", required=True, help="CSV de plan de TrainingPeaks")
    ap.add_argument("--garmin", required=True, help="CSV de metricas de Garmin")
    ap.add_argument("--strava", required=True, help="JSON de actividades de Strava")
    ap.add_argument("--daily-log", default=None, help="daily-log.md opcional (registro de checkpoints)")
    ap.add_argument("--race-date", default="2026-09-27", help="Fecha del maraton, YYYY-MM-DD")
    ap.add_argument("--goal-time", default="3:40:00", help="Tiempo objetivo del maraton")
    ap.add_argument("--out", default="data.json", help="Ruta de salida")
    args = ap.parse_args()

    race_date = parse_date(args.race_date)
    if not race_date:
        raise SystemExit(f"--race-date invalido: {args.race_date}")

    data = build(
        args.trainingpeaks, args.garmin, args.strava, args.daily_log,
        race_date, args.goal_time,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"OK: {len(data['days'])} dias, {len(data['weeks'])} semanas -> {args.out}")


if __name__ == "__main__":
    main()
