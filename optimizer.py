"""
Smart Portfolio Optimizer — Core Engine
Implements Modern Portfolio Theory with multiple optimization strategies
including Black-Litterman, Hierarchical Risk Parity, and sector constraints.
"""

import hashlib
import os
import pickle
import time
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform
from typing import Optional
import statsmodels.api as sm


# ═══════════════════════════════════════════════════════════════════
#  Data Cache
# ═══════════════════════════════════════════════════════════════════

class DataCache:
    """File-based cache for yfinance downloads. TTL = 1 hour."""

    CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "portfolio_optimizer")
    TTL = 3600  # seconds

    @classmethod
    def _key(cls, tickers: list[str], start: str, end: str) -> str:
        raw = f"{','.join(sorted(tickers))}|{start}|{end}"
        return hashlib.md5(raw.encode()).hexdigest()

    @classmethod
    def get(cls, tickers: list[str], start: str, end: str) -> Optional[pd.DataFrame]:
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        path = os.path.join(cls.CACHE_DIR, f"{cls._key(tickers, start, end)}.pkl")
        if os.path.exists(path):
            age = time.time() - os.path.getmtime(path)
            if age < cls.TTL:
                with open(path, "rb") as f:
                    return pickle.load(f)
        return None

    @classmethod
    def put(cls, tickers: list[str], start: str, end: str, data: pd.DataFrame):
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        path = os.path.join(cls.CACHE_DIR, f"{cls._key(tickers, start, end)}.pkl")
        with open(path, "wb") as f:
            pickle.dump(data, f)


# ═══════════════════════════════════════════════════════════════════
#  Fama-French Data Cache
# ═══════════════════════════════════════════════════════════════════

class FFCache:
    """File-based cache for Fama-French factor data."""
    CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "portfolio_optimizer", "ff")
    
    @classmethod
    def get(cls, dataset: str, start: str, end: str) -> Optional[pd.DataFrame]:
        key = hashlib.md5(f"{dataset}|{start}|{end}".encode()).hexdigest()
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        path = os.path.join(cls.CACHE_DIR, f"{key}.pkl")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return pickle.load(f)
        return None

    @classmethod
    def put(cls, dataset: str, start: str, end: str, data: pd.DataFrame):
        key = hashlib.md5(f"{dataset}|{start}|{end}".encode()).hexdigest()
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        path = os.path.join(cls.CACHE_DIR, f"{key}.pkl")
        with open(path, "wb") as f:
            pickle.dump(data, f)



# ═══════════════════════════════════════════════════════════════════
#  Portfolio Optimizer
# ═══════════════════════════════════════════════════════════════════

class PortfolioOptimizer:
    """
    Portfolio optimization engine.

    Strategies: Max Sharpe, Min Volatility, Risk Parity, Equal Weight,
    Max Return, Black-Litterman, Hierarchical Risk Parity.
    Supports sector constraints and transaction cost modeling.
    """

    TRADING_DAYS = 252

    def __init__(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        risk_free_rate: float = 0.01,
        progress_callback=None,
    ):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.risk_free_rate = risk_free_rate
        self._progress = progress_callback or (lambda *a: None)

        self._progress("downloading", "Fetching market data...")
        self.data = self._fetch_data()

        self._progress("computing", "Computing returns & covariance...")
        self.daily_returns = self._calculate_returns()
        self.expected_returns = self.daily_returns.mean() * self.TRADING_DAYS
        self.cov_matrix = self.daily_returns.cov() * self.TRADING_DAYS

    # ── Data fetching ────────────────────────────────────────────

    def _fetch_data(self) -> pd.DataFrame:
        """Fetch historical adjusted-close prices, with caching."""
        cached = DataCache.get(self.tickers, self.start_date, self.end_date)
        if cached is not None:
            return cached

        df = yf.download(self.tickers, start=self.start_date, end=self.end_date)
        if "Adj Close" in df.columns.get_level_values(0):
            price = df["Adj Close"]
        else:
            price = df["Close"]
        result = price.dropna()
        DataCache.put(self.tickers, self.start_date, self.end_date, result)
        return result

    def _calculate_returns(self) -> pd.DataFrame:
        return self.data.pct_change().dropna()

    # ── Portfolio math ───────────────────────────────────────────

    def _portfolio_return(self, weights: np.ndarray, mu: np.ndarray = None) -> float:
        if mu is None:
            mu = self.expected_returns.values
        return float(np.dot(weights, mu))

    def _portfolio_volatility(self, weights: np.ndarray) -> float:
        return float(np.sqrt(weights.T @ self.cov_matrix.values @ weights))

    def _portfolio_sharpe(self, weights: np.ndarray, mu: np.ndarray = None) -> float:
        ret = self._portfolio_return(weights, mu)
        vol = self._portfolio_volatility(weights)
        return (ret - self.risk_free_rate) / vol if vol > 0 else 0.0

    @staticmethod
    def _make_bounds(n: int, bounds: Optional[list[tuple[float, float]]] = None):
        return bounds if bounds else [(0.0, 1.0)] * n

    @staticmethod
    def _weight_constraint(weights: np.ndarray) -> float:
        return float(np.sum(weights) - 1.0)

    def _build_sector_constraints(
        self,
        sectors: dict[str, str],
        sector_bounds: dict[str, tuple[float, float]],
    ) -> list[dict]:
        """Build scipy constraint dicts for sector-level weight limits."""
        constraints = []
        if not sectors or not sector_bounds:
            return constraints

        # Group ticker indices by sector
        sector_groups: dict[str, list[int]] = {}
        for i, t in enumerate(self.tickers):
            sec = sectors.get(t, "Other")
            sector_groups.setdefault(sec, []).append(i)

        for sec, indices in sector_groups.items():
            if sec in sector_bounds:
                lo, hi = sector_bounds[sec]
                # Sum of weights in sector >= lo
                constraints.append({
                    "type": "ineq",
                    "fun": lambda w, idx=indices, lb=lo: float(np.sum(w[idx]) - lb),
                })
                # Sum of weights in sector <= hi
                constraints.append({
                    "type": "ineq",
                    "fun": lambda w, idx=indices, ub=hi: float(ub - np.sum(w[idx])),
                })
        return constraints

    # ── Monte Carlo simulation ───────────────────────────────────

    def simulate_portfolios(self, num_portfolios: int = 10000) -> dict:
        self._progress("simulating", f"Simulating {num_portfolios:,} portfolios...")
        n = len(self.tickers)
        all_weights = np.random.dirichlet(np.ones(n), size=num_portfolios)
        mu = self.expected_returns.values
        returns_arr = all_weights @ mu
        vol_arr = np.array([self._portfolio_volatility(w) for w in all_weights])
        sharpe_arr = (returns_arr - self.risk_free_rate) / vol_arr
        return {
            "returns": returns_arr.tolist(),
            "volatility": vol_arr.tolist(),
            "sharpe": sharpe_arr.tolist(),
            "weights": all_weights.tolist(),
        }

    # ── Analytical strategies ────────────────────────────────────

    def _optimize(
        self,
        objective: str,
        bounds=None,
        mu: np.ndarray = None,
        extra_constraints: list[dict] = None,
    ) -> dict:
        n = len(self.tickers)
        x0 = np.ones(n) / n
        bnd = self._make_bounds(n, bounds)
        constraints = [{"type": "eq", "fun": self._weight_constraint}]
        if extra_constraints:
            constraints.extend(extra_constraints)

        if objective == "max_sharpe":
            fun = lambda w: -self._portfolio_sharpe(w, mu)
        elif objective == "min_volatility":
            fun = lambda w: self._portfolio_volatility(w)
        elif objective == "max_return":
            fun = lambda w: -self._portfolio_return(w, mu)
        else:
            raise ValueError(f"Unknown objective: {objective}")

        result = minimize(
            fun, x0, method="SLSQP", bounds=bnd, constraints=constraints,
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        weights = np.maximum(result.x, 0)
        weights /= weights.sum()
        ret = self._portfolio_return(weights, mu)
        vol = self._portfolio_volatility(weights)
        return {
            "weights": weights.tolist(),
            "return": ret,
            "volatility": vol,
            "sharpe": (ret - self.risk_free_rate) / vol if vol > 0 else 0.0,
        }

    def max_sharpe(self, bounds=None, sectors=None, sector_bounds=None) -> dict:
        sc = self._build_sector_constraints(sectors or {}, sector_bounds or {})
        return self._optimize("max_sharpe", bounds, extra_constraints=sc)

    def min_volatility(self, bounds=None, sectors=None, sector_bounds=None) -> dict:
        sc = self._build_sector_constraints(sectors or {}, sector_bounds or {})
        return self._optimize("min_volatility", bounds, extra_constraints=sc)

    def max_return(self, bounds=None, sectors=None, sector_bounds=None) -> dict:
        sc = self._build_sector_constraints(sectors or {}, sector_bounds or {})
        return self._optimize("max_return", bounds, extra_constraints=sc)

    def equal_weight(self) -> dict:
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
        n = len(self.tickers)
        target_rc = 1.0 / n
        cov = self.cov_matrix.values

        def rp_obj(w):
            w = np.maximum(w, 1e-10)
            pv = np.sqrt(w @ cov @ w)
            mc = cov @ w
            rc = w * mc / pv
            return np.sum((rc - target_rc * pv) ** 2)

        x0 = np.ones(n) / n
        bnd = self._make_bounds(n, bounds)
        result = minimize(
            rp_obj, x0, method="SLSQP", bounds=bnd,
            constraints=[{"type": "eq", "fun": self._weight_constraint}],
            options={"ftol": 1e-12, "maxiter": 1000},
        )
        weights = np.maximum(result.x, 0)
        weights /= weights.sum()
        ret = self._portfolio_return(weights)
        vol = self._portfolio_volatility(weights)
        return {
            "weights": weights.tolist(),
            "return": ret,
            "volatility": vol,
            "sharpe": (ret - self.risk_free_rate) / vol if vol > 0 else 0.0,
        }

    # ── Black-Litterman ──────────────────────────────────────────

    def black_litterman(
        self,
        views: list[dict],
        confidences: list[float] = None,
        tau: float = 0.05,
        bounds=None,
        sectors=None,
        sector_bounds=None,
    ) -> dict:
        """
        Black-Litterman model.

        Args:
            views: list of {ticker: str, expected_return: float} (absolute views)
            confidences: per-view confidence 0–1 (default: 0.5 each)
            tau: scaling factor for uncertainty in equilibrium (default 0.05)
        """
        n = len(self.tickers)
        cov = self.cov_matrix.values

        # Market-cap implied equilibrium returns (use equal-weight as proxy)
        delta = 2.5  # risk aversion coefficient
        w_mkt = np.ones(n) / n
        pi = delta * cov @ w_mkt  # equilibrium excess returns

        if not views:
            # No views → just optimize on equilibrium returns
            sc = self._build_sector_constraints(sectors or {}, sector_bounds or {})
            return self._optimize("max_sharpe", bounds, mu=pi, extra_constraints=sc)

        # Build P (pick matrix) and Q (view returns)
        k = len(views)
        P = np.zeros((k, n))
        Q = np.zeros(k)
        if confidences is None:
            confidences = [0.5] * k

        ticker_idx = {t: i for i, t in enumerate(self.tickers)}
        for j, view in enumerate(views):
            t = view.get("ticker", "")
            if t in ticker_idx:
                P[j, ticker_idx[t]] = 1.0
                Q[j] = view["expected_return"]

        # Omega: diagonal uncertainty matrix (lower confidence → higher variance)
        omega_diag = np.array([
            tau * (P[j] @ cov @ P[j].T) / max(c, 0.01)
            for j, c in enumerate(confidences)
        ])
        Omega = np.diag(omega_diag)

        # Black-Litterman posterior expected returns
        tau_cov = tau * cov
        tau_cov_inv = np.linalg.inv(tau_cov)
        Omega_inv = np.linalg.inv(Omega)

        posterior_mu = np.linalg.inv(tau_cov_inv + P.T @ Omega_inv @ P) @ \
                       (tau_cov_inv @ pi + P.T @ Omega_inv @ Q)

        # Optimize using posterior expected returns
        sc = self._build_sector_constraints(sectors or {}, sector_bounds or {})
        return self._optimize("max_sharpe", bounds, mu=posterior_mu, extra_constraints=sc)

    # ── Hierarchical Risk Parity ─────────────────────────────────

    def hrp(self) -> dict:
        """
        Hierarchical Risk Parity allocation.
        Uses correlation-based clustering and inverse-variance weighting.
        """
        corr = self.daily_returns.corr().values
        cov = self.cov_matrix.values
        n = len(self.tickers)

        # 1. Correlation distance matrix
        dist = np.sqrt(0.5 * (1 - corr))
        np.fill_diagonal(dist, 0)
        condensed = squareform(dist)
        link = linkage(condensed, method="single")

        # 2. Quasi-diagonalize
        sort_ix = list(leaves_list(link))

        # 3. Recursive bisection
        weights = np.ones(n)

        def _bisect(indices):
            if len(indices) <= 1:
                return
            mid = len(indices) // 2
            left = indices[:mid]
            right = indices[mid:]

            # Cluster variance (inverse-variance weighting)
            def _cluster_var(idx):
                sub_cov = cov[np.ix_(idx, idx)]
                inv_diag = 1.0 / np.diag(sub_cov)
                w = inv_diag / inv_diag.sum()
                return w @ sub_cov @ w

            v_left = _cluster_var(left)
            v_right = _cluster_var(right)

            alpha = 1 - v_left / (v_left + v_right)
            for i in left:
                weights[i] *= alpha
            for i in right:
                weights[i] *= (1 - alpha)

            _bisect(left)
            _bisect(right)

        _bisect(sort_ix)
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

    # ── Get all strategies ───────────────────────────────────────

    def get_all_strategies(
        self,
        bounds=None,
        views=None,
        confidences=None,
        sectors=None,
        sector_bounds=None,
    ) -> dict:
        self._progress("optimizing", "Running optimization strategies...")
        result = {
            "max_sharpe": self.max_sharpe(bounds, sectors, sector_bounds),
            "min_volatility": self.min_volatility(bounds, sectors, sector_bounds),
            "risk_parity": self.risk_parity(bounds),
            "equal_weight": self.equal_weight(),
            "max_return": self.max_return(bounds, sectors, sector_bounds),
            "hrp": self.hrp(),
        }
        if views:
            result["black_litterman"] = self.black_litterman(
                views, confidences, bounds=bounds,
                sectors=sectors, sector_bounds=sector_bounds,
            )
        return result

    # ── Performance metrics ──────────────────────────────────────

    def compute_metrics(self, weights, cost_bps: float = 0) -> dict:
        """Compute performance metrics with optional transaction cost."""
        w = np.array(weights)
        portfolio_daily = (self.daily_returns * w).sum(axis=1)

        # Apply simple cost drag if provided
        if cost_bps > 0:
            daily_cost = (cost_bps / 10000) / self.TRADING_DAYS
            portfolio_daily = portfolio_daily - daily_cost

        ann_return = float(portfolio_daily.mean() * self.TRADING_DAYS)
        ann_vol = float(portfolio_daily.std() * np.sqrt(self.TRADING_DAYS))
        sharpe = (ann_return - self.risk_free_rate) / ann_vol if ann_vol > 0 else 0.0

        downside = portfolio_daily[portfolio_daily < 0]
        downside_std = float(downside.std() * np.sqrt(self.TRADING_DAYS)) if len(downside) > 0 else 0.0
        sortino = (ann_return - self.risk_free_rate) / downside_std if downside_std > 0 else 0.0

        cum = (1 + portfolio_daily).cumprod()
        running_max = cum.cummax()
        drawdowns = (cum - running_max) / running_max
        max_dd = float(drawdowns.min())
        calmar = ann_return / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0

        # Historical VaR and CVaR (95% confidence)
        var_95 = float(np.percentile(portfolio_daily, 5))
        tail_returns = portfolio_daily[portfolio_daily <= var_95]
        cvar_95 = float(tail_returns.mean()) if len(tail_returns) > 0 else var_95

        return {
            "annual_return": round(ann_return, 6),
            "annual_volatility": round(ann_vol, 6),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "max_drawdown": round(max_dd, 4),
            "calmar": round(calmar, 4),
            "var_95": round(var_95, 6),
            "cvar_95": round(cvar_95, 6),
        }

    # ── Growth of $10K ───────────────────────────────────────────

    def growth_of_10k(self, weights, cost_bps: float = 0) -> dict:
        """Cumulative $10K growth for a given allocation."""
        w = np.array(weights)
        portfolio_daily = (self.daily_returns * w).sum(axis=1)
        if cost_bps > 0:
            daily_cost = (cost_bps / 10000) / self.TRADING_DAYS
            portfolio_daily = portfolio_daily - daily_cost

        cum = (1 + portfolio_daily).cumprod() * 10000
        dates = [d.strftime("%Y-%m-%d") for d in cum.index]
        return {"dates": dates, "values": cum.tolist()}

    # ── Rebalancing backtest ─────────────────────────────────────

    def backtest(
        self,
        weights: list[float],
        rebalance_freq: str = "quarterly",
        cost_bps: float = 0,
    ) -> dict:
        """
        Walk-forward backtest with periodic rebalancing and transaction costs.
        Returns cumulative values, drawdown, and rolling Sharpe.
        """
        w_target = np.array(weights)
        daily_ret = self.daily_returns.values
        dates = self.daily_returns.index
        n_days = len(dates)
        n_assets = len(self.tickers)

        # Map rebalance frequency
        freq_map = {"monthly": "ME", "quarterly": "QE", "yearly": "YE"}
        pd_freq = freq_map.get(rebalance_freq, "QE")

        rebal_dates = set(
            pd.Series(dates, index=dates).groupby(pd.Grouper(freq=pd_freq)).last().dropna().values
        )

        portfolio_value = 10000.0
        current_weights = w_target.copy()
        values = [portfolio_value]
        total_cost = 0.0

        for i in range(n_days):
            # Daily return
            day_ret = daily_ret[i]
            port_ret = np.dot(current_weights, day_ret)
            portfolio_value *= (1 + port_ret)

            # Update weights (drift)
            current_weights = current_weights * (1 + day_ret)
            w_sum = current_weights.sum()
            if w_sum > 0:
                current_weights /= w_sum

            # Rebalance check
            if dates[i] in rebal_dates and i < n_days - 1:
                turnover = np.sum(np.abs(current_weights - w_target))
                cost = portfolio_value * turnover * (cost_bps / 10000)
                portfolio_value -= cost
                total_cost += cost
                current_weights = w_target.copy()

            values.append(portfolio_value)

        values = values[1:]  # align with dates
        values_series = pd.Series(values, index=dates)

        # Drawdown
        running_max = values_series.cummax()
        drawdown = ((values_series - running_max) / running_max).tolist()

        # Rolling Sharpe (63-day ≈ quarterly)
        daily_rets = values_series.pct_change().dropna()
        rolling_sharpe_series = (
            daily_rets.rolling(63).mean() / daily_rets.rolling(63).std()
        ) * np.sqrt(self.TRADING_DAYS)
        rolling_sharpe = rolling_sharpe_series.fillna(0).tolist()
        # Pad front to match length
        rolling_sharpe = [0.0] * (len(values) - len(rolling_sharpe)) + rolling_sharpe

        date_strs = [d.strftime("%Y-%m-%d") for d in dates]
        return {
            "dates": date_strs,
            "cumulative": values,
            "drawdown": drawdown,
            "rolling_sharpe": rolling_sharpe,
            "total_cost": round(total_cost, 2),
        }

    # ── Correlation matrix ───────────────────────────────────────

    def get_correlation_matrix(self) -> dict:
        corr = self.daily_returns.corr()
        return {
            "tickers": self.tickers,
            "matrix": corr.values.tolist(),
        }

    # ── Individual asset analytics ───────────────────────────────

    def get_asset_analytics(self) -> dict:
        result = {}
        for t in self.tickers:
            rets = self.daily_returns[t]
            ann_ret = float(rets.mean() * self.TRADING_DAYS)
            ann_vol = float(rets.std() * np.sqrt(self.TRADING_DAYS))
            sharpe = (ann_ret - self.risk_free_rate) / ann_vol if ann_vol > 0 else 0.0
            prices = self.data[t]
            result[t] = {
                "return": round(ann_ret, 6),
                "volatility": round(ann_vol, 6),
                "sharpe": round(sharpe, 4),
                "prices": {
                    "dates": [d.strftime("%Y-%m-%d") for d in prices.index],
                    "values": prices.tolist(),
                },
            }
        return result

    # ── Legacy compat ────────────────────────────────────────────

    def get_optimal_portfolios(self, results: dict) -> dict:
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

    # ── Advanced Risk & Wealth Forecasting ───────────────────────

    def wealth_forecast(self, weights: list[float], years: int = 10, initial_capital: float = 10000, num_paths: int = 1000) -> dict:
        """
        Monte Carlo Wealth Forecasting using Geometric Brownian Motion (GBM).
        Returns 10th, 50th, and 90th percentile projected wealth paths.
        """
        w = np.array(weights)
        port_ret = (self.daily_returns * w).sum(axis=1)
        
        mu = port_ret.mean() * self.TRADING_DAYS
        sigma = port_ret.std() * np.sqrt(self.TRADING_DAYS)
        
        dt = 1 / self.TRADING_DAYS
        n_steps = int(years * self.TRADING_DAYS)
        
        # GBM paths: log-normal simulation
        drift = (mu - 0.5 * sigma**2) * dt
        shock = sigma * np.sqrt(dt) * np.random.normal(size=(n_steps, num_paths))
        returns = np.exp(drift + shock)
        paths = np.vstack([np.ones(num_paths), returns]).cumprod(axis=0) * initial_capital
        
        # Percentiles across simulated paths over time
        p10 = np.percentile(paths, 10, axis=1)
        p50 = np.percentile(paths, 50, axis=1)
        p90 = np.percentile(paths, 90, axis=1)
        
        # Generate future business dates for x-axis
        last_date = self.daily_returns.index[-1]
        future_dates = pd.bdate_range(start=last_date, periods=n_steps+1)
        date_strs = [d.strftime("%Y-%m-%d") for d in future_dates]
        
        return {
            "dates": date_strs,
            "p10": p10.tolist(),
            "p50": p50.tolist(),
            "p90": p90.tolist()
        }

    # ── Factor Analysis (Fama-French) ────────────────────────────

    def factor_analysis(self, weights: list[float]) -> dict:
        """
        Decompose portfolio returns using the Fama-French 3-Factor model.
        Requires network connection to fetch from Kenneth French data library via pandas_datareader.
        """
        w = np.array(weights)
        port_ret = (self.daily_returns * w).sum(axis=1)
        
        start = port_ret.index[0].strftime("%Y-%m-%d")
        end = port_ret.index[-1].strftime("%Y-%m-%d")
        
        # Fetch from cache or download from Fama-French
        ff = FFCache.get("F-F_Research_Data_Factors_daily", start, end)
        if ff is None:
            self._progress("downloading", "Fetching Fama-French 3-Factor data...")
            try:
                url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
                df_ff = pd.read_csv(url, skiprows=4, index_col=0)
                # Ensure the index is treated as string before parsing (handles NaN noise at the bottom of the CSV)
                df_ff.index = pd.to_datetime(df_ff.index.astype(str), format='%Y%m%d', errors='coerce')
                df_ff = df_ff.dropna()
                ff = df_ff / 100.0  # FF data is provided as percentages (e.g., 1.5 instead of 0.015)
                
                FFCache.put("F-F_Research_Data_Factors_daily", start, end, ff)
            except Exception as e:
                return {"error": f"Failed to fetch factor data: {str(e)}"}
        
        # Align port_ret and FF data on overlapping dates
        aligned = pd.concat([port_ret.rename("Port"), ff], axis=1).dropna()
        if len(aligned) < 30:
            return {"error": "Not enough overlapping data for factor analysis (need at least 30 days)."}
            
        y = aligned["Port"] - aligned["RF"]
        # Standard 3 factors
        cols = [c for c in aligned.columns if c in ["Mkt-RF", "SMB", "HML"]]
        if not cols:
            return {"error": "Could not extract standard Fama-French columns."}
            
        X = aligned[cols]
        X = sm.add_constant(X)
        
        # OLS Regression
        model = sm.OLS(y, X).fit()
        
        exposures = {}
        for factor in cols:
            exposures[factor] = round(model.params.get(factor, 0.0), 3)
            
        return {
            "r_squared": round(model.rsquared, 3),
            "alpha_annualized": round(model.params.get("const", 0.0) * self.TRADING_DAYS, 4),
            "exposures": exposures,
            "pvalues": {f: round(model.pvalues.get(f, 1.0), 3) for f in cols}
        }

