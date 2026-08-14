from __future__ import annotations

import math


BLOOD_MOON_TARGET = 2520.0
DAY_UNITS = 360.0
SECONDS_PER_UNIT = 4.0


def _seconds(units: float) -> int:
    """Round upward so the interface never announces the event too early."""
    return max(0, math.ceil(units * SECONDS_PER_UNIT))


def _clock_label(value: float) -> str:
    total_minutes = int((value % DAY_UNITS) * 4.0) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def blood_moon_status(flags: dict[str, object]) -> dict[str, object]:
    """Project the next scheduled Blood Moon from BOTW's saved WorldMgr state.

    WM_BloodyMoonTimer and WM_Time use a 0..360 day scale.  One unit is four
    seconds of active gameplay.  Once the moon timer reaches 2520, WorldMgr
    schedules WM_BloodyDay at a midnight; the cutscene runs at the following
    permitted midnight.  Menus, cutscenes, sleeping and prohibited locations
    can therefore delay the real-world event without making the saved values
    inaccurate.
    """
    if not bool(flags.get("FirstTouchdown")):
        return {
            "available": False,
            "status": "not_started",
            "status_label": "Disponible après avoir quitté le plateau du Prélude",
            "accuracy_label": "Compteur interne non démarré",
        }

    timer = flags.get("WM_BloodyMoonTimer")
    game_time = flags.get("WM_Time")
    if not isinstance(timer, (int, float)) or not isinstance(game_time, (int, float)):
        return {
            "available": False,
            "status": "missing_data",
            "status_label": "Compteur interne absent de cette sauvegarde",
            "accuracy_label": "Estimation indisponible",
        }
    timer = max(0.0, float(timer))
    game_time = float(game_time) % DAY_UNITS
    reserve = flags.get("WM_bloodyEndReserveTimer", 0)
    reserve = float(reserve) if isinstance(reserve, (int, float)) else 0.0
    just_occurred = reserve > 0
    scheduled = bool(flags.get("WM_BloodyDay")) and not just_occurred

    if scheduled:
        # At 00:00 a newly set WM_BloodyDay targets the *next* midnight.
        until_event_units = DAY_UNITS - game_time
        if until_event_units <= 0.001:
            until_event_units = DAY_UNITS
        until_threshold_units = 0.0
        until_scheduled_units = 0.0
        status = "scheduled"
        status_label = "Lune de sang programmée pour le prochain minuit autorisé"
    else:
        until_threshold_units = max(0.0, BLOOD_MOON_TARGET - timer)
        projected_time = (game_time + until_threshold_units) % DAY_UNITS
        until_schedule_midnight = (DAY_UNITS - projected_time) % DAY_UNITS
        if until_schedule_midnight < 0.001:
            until_schedule_midnight = 0.0
        until_scheduled_units = until_threshold_units + until_schedule_midnight
        until_event_units = until_scheduled_units + DAY_UNITS
        status = "just_occurred" if just_occurred else "counting"
        status_label = (
            "La lune de sang vient d’avoir lieu - nouveau cycle démarré"
            if just_occurred else "Compteur interne en progression"
        )

    inhibited = bool(flags.get("BloodyMoonProhibition") or
                     flags.get("IsInHyruleCastleArea"))
    return {
        "available": True,
        "status": status,
        "status_label": status_label,
        "scheduled": scheduled,
        "may_be_delayed": inhibited,
        "timer_value": round(timer, 3),
        "timer_target": BLOOD_MOON_TARGET,
        "timer_progress_percent": round(min(100.0, 100.0 * timer / BLOOD_MOON_TARGET), 2),
        "game_time_value": round(game_time, 3),
        "game_time_label": _clock_label(game_time),
        "active_seconds_until_threshold": _seconds(until_threshold_units),
        "active_seconds_until_scheduled": _seconds(until_scheduled_units),
        "active_seconds_until_event": _seconds(until_event_units),
        "accuracy": "exact_saved_state_projection",
        "accuracy_label": "Valeurs exactes de la dernière sauvegarde • projection en jeu actif",
        "explanation": (
            "Les menus, cinématiques et phases de sommeil ne font pas avancer le compteur. "
            "Un sanctuaire, une créature divine, le château d’Hyrule ou certains événements "
            "peuvent reporter le déclenchement, qui sera recalculé à la prochaine sauvegarde."
        ),
    }