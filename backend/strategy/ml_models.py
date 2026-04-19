from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional


MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
PACE_MODEL_PATH = MODEL_DIR / "pace_model.joblib"
PIT_LOSS_MODEL_PATH = MODEL_DIR / "pit_loss_model.joblib"


def _load_joblib(path: Path) -> Any:
    try:
        import joblib  # type: ignore
    except Exception:
        return None
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_default_pace_model() -> Any:
    model = _load_joblib(PACE_MODEL_PATH)
    if model is None:
        print(f"[ML] pace model unavailable at {PACE_MODEL_PATH}; fallback heuristics enabled")
    return model


@lru_cache(maxsize=1)
def _load_default_pit_loss_model() -> Any:
    model = _load_joblib(PIT_LOSS_MODEL_PATH)
    if model is None:
        print(f"[ML] pit-loss model unavailable at {PIT_LOSS_MODEL_PATH}; fallback heuristics enabled")
    return model


def load_pace_model(model_path: Optional[str] = None) -> Any:
    if model_path:
        path = Path(model_path)
        model = _load_joblib(path)
        if model is None:
            print(f"[ML] pace model unavailable at {path}; fallback heuristics enabled")
        return model
    return _load_default_pace_model()


def load_pit_loss_model(model_path: Optional[str] = None) -> Any:
    if model_path:
        path = Path(model_path)
        model = _load_joblib(path)
        if model is None:
            print(f"[ML] pit-loss model unavailable at {path}; fallback heuristics enabled")
        return model
    return _load_default_pit_loss_model()


def predict_pace_delta(model: Any, feature_vector: List[float]) -> Optional[float]:
    """
    Returns predicted lap-time residual seconds, or None if model unavailable/failed.
    """
    if model is None:
        return None
    try:
        pred = model.predict([feature_vector])
        return float(pred[0])
    except Exception:
        return None


def predict_pit_loss(model: Any, feature_vector: List[float]) -> Optional[float]:
    if model is None:
        return None
    try:
        pred = model.predict([feature_vector])
        return float(pred[0])
    except Exception:
        return None


def model_available(model: Any) -> bool:
    return model is not None
