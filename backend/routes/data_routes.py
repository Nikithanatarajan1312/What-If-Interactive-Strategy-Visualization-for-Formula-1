"""
Flask Blueprint: data endpoints.

    GET /api/races               — list available races
    GET /api/race/<year>/<rnd>   — full race data (drivers, laps, pits, events)
    GET /api/drivers/<year>/<rnd> — driver list with team colors
"""
import traceback
from flask import Blueprint

from services.data_loader import get_available_races, load_race_data
from utils.export import json_response, error_response

data_bp = Blueprint('data', __name__)


@data_bp.route('/api/races', methods=['GET'])
def api_races():
    try:
        return json_response(get_available_races())
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e))


@data_bp.route('/api/race/<int:year>/<int:rnd>', methods=['GET'])
def api_race(year, rnd):
    try:
        data = load_race_data(year, rnd)
        return json_response(data)
    except KeyError as e:
        return error_response(str(e), 404)
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e))


@data_bp.route('/api/drivers/<int:year>/<int:rnd>', methods=['GET'])
def api_drivers(year, rnd):
    try:
        data = load_race_data(year, rnd)
        drivers = [
            {
                'code': d['code'],
                'name': d['name'],
                'team': d['team'],
                'color': d['color'],
            }
            for d in data['drivers']
        ]
        return json_response(drivers)
    except KeyError as e:
        return error_response(str(e), 404)
    except Exception as e:
        traceback.print_exc()
        return error_response(str(e))
