"""
Tyre degradation model.

Fits a per-compound degradation curve from actual stint data using
constrained least-squares regression:

    lap_time = base_pace + alpha * tyre_age + beta * tyre_age^2
             + gamma * fuel_load + residual

Physical constraints enforced during fitting:
  alpha >= 0  (tyres always degrade linearly)
  beta  >= 0  (degradation accelerates — tyre cliff)
  gamma >= 0  (heavier fuel = slower car)

Outlier-robust: IQR gating removes safety-car / red-flag laps before
fitting, and residual spread is estimated with MAD (median absolute
deviation) rather than plain std.

Public API
    TyreDegradationModel
        .fit(stint_data)                  fit from stint records
        .predict(compound, age, fuel)     single-lap time prediction
        .get_params(compound)             {alpha, beta, gamma, base}
        .residual_std(compound)           noise for MC sampling
        .compounds                        list of fitted compounds
        .driver_pace_offset(code)         per-driver offset from mean
"""
import logging

import numpy as np
from scipy.optimize import least_squares as scipy_lstsq

logger = logging.getLogger(__name__)

DEFAULT_PARAMS = {
    'SOFT':         {'base': 0.0, 'alpha': 0.045, 'beta': 0.0020, 'gamma': 1.2},
    'MEDIUM':       {'base': 0.5, 'alpha': 0.032, 'beta': 0.0010, 'gamma': 1.2},
    'HARD':         {'base': 0.9, 'alpha': 0.018, 'beta': 0.0005, 'gamma': 1.2},
    'INTERMEDIATE': {'base': 2.5, 'alpha': 0.060, 'beta': 0.0028, 'gamma': 0.8},
    'WET':          {'base': 5.0, 'alpha': 0.080, 'beta': 0.0032, 'gamma': 0.8},
}

MIN_POINTS_FOR_FIT = 12


class TyreDegradationModel:
    """Per-compound tyre degradation model fitted from real stint data."""

    def __init__(self):
        self._params = {}
        self._residual_stds = {}
        self._global_base_pace = 90.0
        self._driver_offsets = {}
        self._fitted = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def compounds(self):
        return list(self._params.keys())

    @property
    def fitted(self):
        return self._fitted

    @property
    def global_base_pace(self):
        return self._global_base_pace

    def driver_pace_offset(self, driver_code):
        """Seconds slower than the field median.  Negative = faster."""
        return self._driver_offsets.get(driver_code, 0.0)

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(self, stint_data):
        """
        Fit degradation curves from stint records.

        stint_data: list of dicts  {driver, compound, tyre_age,
                                    lap_time, lap_number, fuel_load}
        """
        if not stint_data:
            logger.warning("No stint data — using empirical defaults")
            self._use_defaults(90.0)
            return self

        all_times = np.array([r['lap_time'] for r in stint_data])

        # ---- outlier gating (IQR * 3) ----
        q1, q3 = np.percentile(all_times, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        clean = [r for r in stint_data if lo <= r['lap_time'] <= hi]
        n_rm = len(stint_data) - len(clean)
        if n_rm:
            logger.info("Outlier filter removed %d laps (%.1f%%)",
                        n_rm, 100 * n_rm / len(stint_data))

        if len(clean) < 20:
            logger.warning("Only %d clean laps — falling back to defaults",
                           len(clean))
            self._use_defaults(float(np.median(all_times)))
            return self

        clean_times = np.array([r['lap_time'] for r in clean])
        self._global_base_pace = float(np.percentile(clean_times, 10))

        # ---- per-driver pace offsets ----
        by_driver = {}
        for rec in clean:
            by_driver.setdefault(rec['driver'], []).append(rec['lap_time'])
        driver_medians = {d: float(np.median(t)) for d, t in by_driver.items()}
        field_median = float(np.median(clean_times))
        self._driver_offsets = {
            d: round(m - field_median, 3) for d, m in driver_medians.items()
        }

        # ---- per-compound constrained fit ----
        by_compound = {}
        for rec in clean:
            by_compound.setdefault(rec['compound'], []).append(rec)

        for compound, recs in by_compound.items():
            self._fit_compound(compound, recs)

        for compound in DEFAULT_PARAMS:
            if compound not in self._params:
                self._params[compound] = dict(DEFAULT_PARAMS[compound])
                self._residual_stds[compound] = 0.3

        self._fitted = True
        return self

    def _fit_compound(self, compound, recs):
        """Constrained least-squares fit for one compound."""
        if len(recs) < MIN_POINTS_FOR_FIT:
            logger.info("%s: only %d points — using defaults",
                        compound, len(recs))
            defaults = DEFAULT_PARAMS.get(compound, DEFAULT_PARAMS['MEDIUM'])
            self._params[compound] = dict(defaults)
            self._residual_stds[compound] = 0.3
            return

        ages  = np.array([r['tyre_age'] for r in recs], dtype=float)
        fuels = np.array([r['fuel_load'] for r in recs], dtype=float)
        times = np.array([r['lap_time'] for r in recs], dtype=float)
        bp = self._global_base_pace

        def residual_fn(p):
            base, alpha, beta, gamma = p
            return times - (bp + base + alpha * ages
                            + beta * ages ** 2 + gamma * fuels)

        defaults = DEFAULT_PARAMS.get(compound, DEFAULT_PARAMS['MEDIUM'])
        x0 = [defaults['base'], defaults['alpha'],
              defaults['beta'], defaults['gamma']]

        try:
            result = scipy_lstsq(
                residual_fn, x0,
                bounds=([-10, 0, 0, 0], [10, 0.5, 0.05, 10]),
                method='trf',
            )
            base, alpha, beta, gamma = result.x
            res = result.fun
            mad = float(np.median(np.abs(res - np.median(res))))
            std = max(mad * 1.4826, 0.1)

            self._params[compound] = {
                'base':  round(float(base), 4),
                'alpha': round(float(alpha), 6),
                'beta':  round(float(beta), 6),
                'gamma': round(float(gamma), 4),
            }
            self._residual_stds[compound] = round(std, 4)

            logger.info("Fitted %s  base=%.2f a=%.4f b=%.6f g=%.3f "
                        "std=%.3f  (n=%d)",
                        compound, base, alpha, beta, gamma, std, len(recs))

        except Exception:
            logger.warning("Fit failed for %s — using defaults",
                           compound, exc_info=True)
            self._params[compound] = dict(defaults)
            self._residual_stds[compound] = 0.3

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, compound, tyre_age, fuel_load=0.5):
        """Predicted lap time in seconds."""
        p = self._params.get(
            compound,
            self._params.get('MEDIUM', DEFAULT_PARAMS['MEDIUM']))
        return (self._global_base_pace
                + p['base']
                + p['alpha'] * tyre_age
                + p['beta'] * (tyre_age ** 2)
                + p['gamma'] * fuel_load)

    def get_params(self, compound):
        return dict(self._params.get(
            compound, DEFAULT_PARAMS.get(compound, DEFAULT_PARAMS['MEDIUM'])))

    def residual_std(self, compound):
        return self._residual_stds.get(compound, 0.3)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _use_defaults(self, base_pace):
        self._global_base_pace = base_pace
        for compound, params in DEFAULT_PARAMS.items():
            self._params[compound] = dict(params)
            self._residual_stds[compound] = 0.3
        self._fitted = True

    def perturbed_copy(self, rng=None):
        """Copy with Gaussian-perturbed params (non-negative enforced)."""
        if rng is None:
            rng = np.random.default_rng()

        m = TyreDegradationModel()
        m._global_base_pace = self._global_base_pace + rng.normal(0, 0.15)
        m._driver_offsets = dict(self._driver_offsets)
        m._fitted = True

        for compound in self._params:
            p = dict(self._params[compound])
            std = self._residual_stds.get(compound, 0.3)

            p['base']  += rng.normal(0, std * 0.4)
            p['alpha']  = max(0, p['alpha'] + rng.normal(0, std * 0.03))
            p['beta']   = max(0, p['beta']  + rng.normal(0, std * 0.003))
            p['gamma']  = max(0, p['gamma'] + rng.normal(0, std * 0.1))

            m._params[compound] = p
            m._residual_stds[compound] = self._residual_stds.get(compound, 0.3)

        return m

    def to_dict(self):
        """JSON-safe serialisation."""
        return {
            'globalBasePace': self._global_base_pace,
            'params': self._params,
            'residualStds': self._residual_stds,
            'driverOffsets': self._driver_offsets,
        }
