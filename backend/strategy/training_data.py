from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .features import (
    build_lap_features,
    infer_pit_laps_from_stints,
    infer_team_by_driver,
    map_driver_laps,
    map_driver_trace,
    norm_code,
    to_float,
    to_int,
)


def _is_valid_training_lap(row: Dict[str, Any]) -> bool:
    lt = to_float(row.get("lap_time_sec"))
    lap = to_int(row.get("lap"))
    if lt is None or lap is None:
        return False
    if lt <= 0 or lap <= 0:
        return False
    # Exclude obvious pit/out anomalies for first pass.
    if lt < 60 or lt > 200:
        return False
    return True


def build_training_rows_from_race(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build supervised rows for local lap residual target.

    target_residual_sec = lap_time_sec - median(driver clean lap time)
    """
    meta = payload.get("meta") or {}
    laps_clean = payload.get("laps_clean") or []
    stints_clean = payload.get("stints_clean") or []
    race_trace = payload.get("race_trace") or []
    teams = infer_team_by_driver(laps_clean)
    drivers = sorted({norm_code(r.get("driver")) for r in laps_clean if norm_code(r.get("driver"))})

    total_laps = 0
    for row in laps_clean:
        lap = to_int(row.get("lap"), 0) or 0
        total_laps = max(total_laps, lap)

    all_rows: List[Dict[str, Any]] = []
    for code in drivers:
        driver_laps = map_driver_laps(laps_clean, code)
        if not driver_laps:
            continue
        trace_map = map_driver_trace(race_trace, code)
        pit_laps = set(infer_pit_laps_from_stints(stints_clean, code))
        clean_times = [
            to_float(r.get("lap_time_sec"))
            for r in driver_laps
            if _is_valid_training_lap(r) and (to_int(r.get("lap")) not in pit_laps)
        ]
        clean_times = [x for x in clean_times if x is not None]
        if len(clean_times) < 8:
            continue
        baseline = sorted(clean_times)[len(clean_times) // 2]
        orig_pit = min(pit_laps) if pit_laps else 0

        for row in driver_laps:
            if not _is_valid_training_lap(row):
                continue
            lap = to_int(row.get("lap"), 0) or 0
            lt = to_float(row.get("lap_time_sec"), 0.0) or 0.0
            position = to_int(row.get("position"))
            stint = to_int(row.get("stint"), 1) or 1
            tyre_age = to_int(row.get("tyre_age"), 1) or 1
            comp = str(row.get("compound") or "UNKNOWN").upper()
            gap = trace_map.get(lap)
            pit_this_lap = lap in pit_laps
            laps_since_pit = 0 if pit_this_lap else tyre_age
            raw, vec = build_lap_features(
                meta=meta,
                driver=code,
                team=teams.get(code),
                lap_number=lap,
                total_laps=total_laps,
                stint_number=stint,
                tyre_compound=comp,
                tyre_age=tyre_age,
                gap_to_leader=gap,
                gap_ahead=None,
                gap_behind=None,
                position=position,
                pit_this_lap=pit_this_lap,
                is_in_lap=pit_this_lap,
                is_out_lap=False,
                laps_since_pit=laps_since_pit,
                original_pit_lap=orig_pit,
                simulated_pit_lap=orig_pit,
                pit_shift=0,
                safety_car_flag=0,
                vsc_flag=0,
            )
            target_residual = lt - baseline
            all_rows.append(
                {
                    "raw_features": raw,
                    "model_features": vec,
                    "target_lap_time_sec": lt,
                    "target_residual_sec": float(target_residual),
                    "driver": code,
                    "lap": lap,
                }
            )
    return all_rows


def build_training_dataset_from_payloads(payloads: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for payload in payloads:
        out.extend(build_training_rows_from_race(payload))
    return out


def load_payloads_from_cache_dir(cache_dir: str) -> List[Dict[str, Any]]:
    base = Path(cache_dir)
    payloads: List[Dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return payloads


def train_pace_model_from_dataset(rows: List[Dict[str, Any]], output_path: str) -> Dict[str, float]:
    """
    Train a simple baseline regressor and save via joblib.

    Returns {"mae": ..., "rmse": ..., "n_rows": ...}
    """
    if not rows:
        raise ValueError("No rows provided")
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        from sklearn.model_selection import train_test_split
        import joblib  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Training requires scikit-learn + joblib (`pip install scikit-learn joblib`)."
        ) from exc

    X = [r["model_features"] for r in rows]
    y = [r["target_residual_sec"] for r in rows]
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    model = GradientBoostingRegressor(random_state=42)
    model.fit(X_train, y_train)
    pred = model.predict(X_val)
    mae = float(mean_absolute_error(y_val, pred))
    try:
        rmse = float(mean_squared_error(y_val, pred, squared=False))
    except TypeError:
        rmse = float(math.sqrt(mean_squared_error(y_val, pred)))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out)
    return {"mae": mae, "rmse": rmse, "n_rows": float(len(rows))}
