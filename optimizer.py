"""
Smart Portfolio Optimizer — Core Engine
Implements Modern Portfolio Theory with multiple optimization strategies.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize
from typing import Optional


class PortfolioOptimizer:
    """
    Portfolio optimization engine using Modern Portfolio Theory.

    Supports multiple strategies: Max Sharpe, Min Volatility,
    Risk Parity, Equal Weight, and Max Return. Uses annualized
    metrics (252 trading days) and scipy-based analytical optimization.
    """

    TRADING_DAYS = 252

    def __init__(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        risk_free_rate: float = 0.01,
    ):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.risk_free_rate = risk_free_rate
        self.data = self._fetch_data()
        self.daily_returns = self._calculate_returns()
        self.expected_returns = self.daily_returns.mean() * self.TRADING_DAYS
        self.cov_matrix = self.daily_returns.cov() * self.TRADING_DAYS

    # ── Data fetching ────────────────────────────────────────────────

    def _fetch_data(self) -> pd.DataFrame:
        """Fetch historical adjusted-close prices from Yahoo Finance."""
        df = yf.download(self.tickers, start=self.start_date, end=self.end_date)
        if "Adj Close" in df.columns.get_level_values(0):
            price = df["Adj Close"]
        else:
            price = df["Close"]
        return price.dropna()

    def _calculate_returns(self) -> pd.DataFrame:
        """Calculate daily percentage returns."""
        return self.data.pct_change().dropna()

    # ── Portfolio math helpers ───────────────────────────────────────

    def _portfolio_return(self, weights: np.ndarray) -> float:
        return float(np.dot(weights, self.expected_returns))

    def _portfolio_volatility(self, weights: np.ndarray) -> float:
        return float(np.sqrt(np.dot(weights.T, np.dot(self.cov_matrix, weights))))

    def _portfolio_sharpe(self, weights: np.ndarray) -> float:
        ret = self._portfolio_return(weights)
        vol = self._portfolio_volatility(weights)
        return (ret - self.risk_free_rate) / vol if vol > 0 else 0.0

    @staticmethod
    def _make_bounds(n: int, bounds: Optional[list[tuple[float, float]]] = None):
        """Create per-asset weight bounds. Default: (0, 1) for each."""
        if bounds:
            return bounds
        return [(0.0, 1.0)] * n

    @staticmethod
    def _weight_constraint(weights: np.ndarray) -> float:
        """Equality constraint: weights must sum to 1."""
        return float(np.sum(weights) - 1.0)

    # ── Monte Carlo simulation ───────────────────────────────────────

    def simulate_portfolios(self, num_portfolios: int = 10000) -> dict:
        """
        Generate random portfolios using Dirichlet distribution.
        Returns dict of arrays: returns, volatility, sharpe, weights.
        """
        n = len(self.tickers)
        all_weights = np.random.dirichlet(np.ones(n), size=num_portfolios)

        returns_arr = all_weights @ self.expected_returns.values
        vol_arr = np.array([
            self._portfolio_volatility(w) for w in all_weights
        ])
        sharpe_arr = (returns_arr - self.risk_free_rate) / vol_arr

        return {
            "returns": returns_arr.tolist(),
            "volatility": vol_arr.tolist(),
            "sharpe": sharpe_arr.tolist(),
            "weights": all_weights.tolist(),
        }

    # ── Analytical optimization strategies ───────────────────────────

    def _optimize(
        self,
        objective: str,
        bounds: Optional[list[tuple[float, float]]] = None,
    ) -> dict:
        """
        Run scipy minimization for a given objective.
        objective: 'max_sharpe' | 'min_volatility' | 'max_return'
        """
        n = len(self.tickers)
        x0 = np.ones(n) / n
        bnd = self._make_bounds(n, bounds)
        constraints = [{"type": "eq", "fun": self._weight_constraint}]

        if objective == "max_sharpe":
            fun = lambda w: -self._portfolio_sharpe(w)
        elif objective == "min_volatility":
            fun = lambda w: self._portfolio_volatility(w)
        elif objective == "max_return":
            fun = lambda w: -self._portfolio_return(w)
        else:
            raise ValueError(f"Unknown objective: {objective}")

        result = minimize(
            fun, x0, method="SLSQP", bounds=bnd, constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )

        weights = result.x
        weights = np.maximum(weights, 0)  # clip negatives
        weights /= weights.sum()          # re-normalize

        ret = self._portfolio_return(weights)
        vol = self._portfolio_volatility(weights)

        return {
            "weights": weights.tolist(),
            "return": ret,
            "volatility": vol,
            "sharpe": (ret - self.risk_free_rate) / vol if vol > 0 else 0.0,
        }

    def max_sharpe(self, bounds=None) -> dict:
        """Find the portfolio with the highest Sharpe ratio."""
        return self._optimize("max_sharpe", bounds)

    def min_volatility(self, bounds=None) -> dict:
        """Find the minimum-volatility portfolio."""
        return self._optimize("min_volatility", bounds)

    def max_return(self, bounds=None) -> dict:
        """Find the maximum-return portfolio."""
        return self._optimize("max_return", bounds)

    def equal_weight(self) -> dict:
        """Equal-weight benchmark portfolio (1/n)."""
        n = len(self.tickers)
        weights = np.ones(n) / n
        ret = self._portfolio_return(weights)
        vol = self._portfolio_volatility(weights)
        return {
            "weights": weights.tolist(),
            "return": ret,
            "volatility": vol,
            "sharpe": (ret - self.risk_free_rate) / vol if vol > 0 else 0.0,
        }

    def risk_parity(self, bounds=None) -> dict:
        """
        Risk Parity: equalize each asset's contribution to total risk.
        Minimizes: Σ_i (RC_i − σ_p/n)²  where RC_i = w_i·(Σw)_i / σ_p
        """
        n = len(self.tickers)
        target_rc = 1.0 / n
        cov = self.cov_matrix.values

        def risk_parity_objective(w):
            w = np.maximum(w, 1e-10)
            port_vol = np.sqrt(w @ cov @ w)
            marginal = cov @ w
            risk_contrib = w * marginal / port_vol
            # risk contributions should each equal target_rc of total vol
            return np.sum((risk_contrib - target_rc * port_vol) ** 2)

        x0 = np.ones(n) / n
        bnd = self._make_bounds(n, bounds)
        constraints = [{"type": "eq", "fun": self._weight_constraint}]

        result = minimize(
            risk_parity_objective, x0, method="SLSQP",
            bounds=bnd, constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )

        weights = result.x
        weights = np.maximum(weights, 0)
        weights /= weights.sum()

        ret = self._portfolio_return(weights)
        vol = self._portfolio_volatility(weights)
        return {
            "weights": weights.tolist(),
            "return": ret,
            "volatility": vol,
            "sharpe": (ret - self.risk_free_rate) / vol if vol > 0 else 0.0,
        }

    def get_all_strategies(self, bounds=None) -> dict:
        """Run all optimization strategies and return results."""
        return {
            "max_sharpe": self.max_sharpe(bounds),
            "min_volatility": self.min_volatility(bounds),
            "risk_parity": self.risk_parity(bounds),
            "equal_weight": self.equal_weight(),
            "max_return": self.max_return(bounds),
        }

    # ── Performance metrics ──────────────────────────────────────────

    def compute_metrics(self, weights: np.ndarray | list) -> dict:
        """
        Compute performance metrics for a given weight allocation.
        Returns: annual_return, annual_volatility, sharpe, sortino,
                 max_drawdown, calmar.
        """
        w = np.array(weights)
        portfolio_daily = (self.daily_returns * w).sum(axis=1)

        ann_return = float(portfolio_daily.mean() * self.TRADING_DAYS)
        ann_vol = float(portfolio_daily.std() * np.sqrt(self.TRADING_DAYS))

        # Sharpe
        sharpe = (ann_return - self.risk_free_rate) / ann_vol if ann_vol > 0 else 0.0

        # Sortino (downside deviation)
        downside = portfolio_daily[portfolio_daily < 0]
        downside_std = float(downside.std() * np.sqrt(self.TRADING_DAYS)) if len(downside) > 0 else 0.0
        sortino = (ann_return - self.risk_free_rate) / downside_std if downside_std > 0 else 0.0

        # Max drawdown
        cum = (1 + portfolio_daily).cumprod()
        running_max = cum.cummax()
        drawdowns = (cum - running_max) / running_max
        max_dd = float(drawdowns.min())

        # Calmar
        calmar = ann_return / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0

        return {
            "annual_return": round(ann_return, 6),
            "annual_volatility": round(ann_vol, 6),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "max_drawdown": round(max_dd, 4),
            "calmar": round(calmar, 4),
        }

    # ── Legacy compat ────────────────────────────────────────────────

    def get_optimal_portfolios(self, results: dict) -> dict:
        """Legacy method: find best portfolios from simulation results."""
        max_sharpe_idx = int(np.argmax(results["sharpe"]))
        min_vol_idx = int(np.argmin(results["volatility"]))
        return {
            "max_sharpe": {
                "return": results["returns"][max_sharpe_idx],
                "volatility": results["volatility"][max_sharpe_idx],
                "sharpe": results["sharpe"][max_sharpe_idx],
                "weights": results["weights"][max_sharpe_idx],
            },
            "min_volatility": {
                "return": results["returns"][min_vol_idx],
                "volatility": results["volatility"][min_vol_idx],
                "sharpe": results["sharpe"][min_vol_idx],
                "weights": results["weights"][min_vol_idx],
            },
        }
