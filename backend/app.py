"""
Flask application — F1 What-If Strategy Visualization API.

Registers two Blueprints:
    data_bp      — GET /api/races, /api/race, /api/drivers   (Shreya)
    simulate_bp  — POST /api/simulate                        (Nikitha)

On startup, seeds the JSON cache from mock-data.json so the server
responds instantly without needing live FastF1 network calls.
"""
import logging
from flask import Flask
from flask_cors import CORS

from routes.data_routes import data_bp
from routes.simulate_routes import simulate_bp
from services.data_loader import seed_cache_from_mock_data

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)

app = Flask(__name__)
CORS(app)

app.register_blueprint(data_bp)
app.register_blueprint(simulate_bp)


@app.before_request
def _first_request_init():
    """Seed cache once on first request (lazy init)."""
    if not getattr(app, '_cache_seeded', False):
        seed_cache_from_mock_data()
        app._cache_seeded = True


if __name__ == '__main__':
    seed_cache_from_mock_data()
    print("Starting F1 Strategy API on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
