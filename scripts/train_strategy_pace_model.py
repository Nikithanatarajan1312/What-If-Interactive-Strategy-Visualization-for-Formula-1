#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train baseline pace residual model.")
    parser.add_argument("--cache-dir", default="data/cache", help="Directory of cached race JSON files")
    parser.add_argument(
        "--output",
        default="backend/strategy/artifacts/pace_model.joblib",
        help="Model artifact path",
    )
    args = parser.parse_args()

    from backend.strategy.training_data import (
        build_training_dataset_from_payloads,
        load_payloads_from_cache_dir,
    )

    payloads = load_payloads_from_cache_dir(args.cache_dir)
    rows = build_training_dataset_from_payloads(payloads)
    if not rows:
        raise SystemExit("No training rows built. Check cache dir and payload quality.")

    clean_rows = []
    for r in rows:
        x = r["model_features"]
        yv = float(r["target_residual_sec"])
        if not math.isfinite(yv):
            continue
        if any((not math.isfinite(float(v))) for v in x):
            continue
        clean_rows.append(r)

    if not clean_rows:
        raise SystemExit("No finite training rows after cleaning.")

    X = [r["model_features"] for r in clean_rows]
    y = [r["target_residual_sec"] for r in clean_rows]

    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        from sklearn.model_selection import train_test_split
    except Exception as exc:
        raise SystemExit(
            "scikit-learn is required for training script. Install with `pip install scikit-learn joblib`."
        ) from exc

    try:
        import joblib  # type: ignore
    except Exception as exc:
        raise SystemExit("joblib is required. Install with `pip install joblib`.") from exc

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    model = GradientBoostingRegressor(random_state=42)
    model.fit(X_train, y_train)
    pred = model.predict(X_val)
    mae = mean_absolute_error(y_val, pred)
    try:
        rmse = mean_squared_error(y_val, pred, squared=False)
    except TypeError:
        # Older/newer sklearn variants may not expose `squared=`.
        rmse = math.sqrt(mean_squared_error(y_val, pred))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_path)
    print(f"Rows: {len(clean_rows)} (from {len(rows)} raw)")
    print(f"Saved: {out_path}")
    print(f"MAE: {mae:.4f} sec")
    print(f"RMSE: {rmse:.4f} sec")


if __name__ == "__main__":
    main()
