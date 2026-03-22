"""
Flask Blueprint: simulation endpoint.

    POST /api/simulate — accept modified pit strategy, return simulated
                         race trace with uncertainty bands.

Request body:
    {
      "year": 2024,
      "round": 1,
      "strategy": {
        "driverCode": "VER",
        "pitStops": [
          {"lap": 18, "fromCompound": "MEDIUM", "toCompound": "HARD", "duration_s": 22},
          {"lap": 40, "fromCompound": "HARD", "toCompound": "SOFT", "duration_s": 22}
        ]
      }
    }

Response: Full race data JSON with the target driver's laps replaced by
simulated values, annotated with p5/p25/p50/p75/p95 percentile bands.
"""
import traceback
from flask import Blueprint, request as flask_request

from services.data_loader import load_race_data, get_stint_data
from models.tyre_degradation import TyreDegradationModel
from services.uncertainty import run_monte_carlo
from utils.export import json_response, error_response

simulate_bp = Blueprint('simulate', __name__)

_model_cache = {}


def _get_tyre_model(year, rnd):
    """Fit (or retrieve cached) tyre model for a race."""
    key = f"{year}-{rnd}"
    if key not in _model_cache:
        stint_data = get_stint_data(year, rnd)
        model = TyreDegradationModel().fit(stint_data)
        _model_cache[key] = model
    return _model_cache[key]


@simulate_bp.route('/api/simulate', methods=['POST'])
def api_simulate():
    try:
        body = flask_request.get_json(force=True)
        year = int(body['year'])
        rnd = int(body['round'])
        strategy = body['strategy']

        if 'driverCode' not in strategy or 'pitStops' not in strategy:
            return error_response(
                "strategy must include 'driverCode' and 'pitStops'", 400)

        race_data = load_race_data(year, rnd)
        tyre_model = _get_tyre_model(year, rnd)

        n_samples = int(body.get('nSamples', 200))
        n_samples = max(10, min(n_samples, 500))

        result = run_monte_carlo(race_data, strategy, tyre_model, n_samples)

        result['tyreModel'] = tyre_model.to_dict()

        return json_response(result)

    except KeyError as e:
        return error_response(f'Missing field: {e}', 400)
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e))
