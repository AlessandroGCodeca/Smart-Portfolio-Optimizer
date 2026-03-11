"""
Smart Portfolio Optimizer — Unit Tests
Tests for optimization strategies, metrics, and edge cases.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
import pandas as pd

# We need to patch yfinance before importing optimizer
# to avoid actual network calls in tests


def make_mock_data(tickers, days=500):
    """Create fake price data for testing."""
    np.random.seed(42)
    dates = pd.bdate_range("2020-01-01", periods=days)
    data = {}
    for t in tickers:
        returns = np.random.normal(0.0005, 0.02, days)
        prices = 100 * np.cumprod(1 + returns)
        data[t] = prices
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def optimizer():
    """Create a PortfolioOptimizer with mocked data."""
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    mock_data = make_mock_data(tickers)

    with patch("optimizer.yf") as mock_yf, \
         patch("optimizer.DataCache.get", return_value=None), \
         patch("optimizer.DataCache.put"):
        mock_download = MagicMock()
        # Build a MultiIndex DataFrame similar to yfinance output
        columns = pd.MultiIndex.from_product([["Close"], tickers])
        multi_df = pd.DataFrame(mock_data.values, index=mock_data.index, columns=columns)
        mock_yf.download.return_value = multi_df

        from optimizer import PortfolioOptimizer
        opt = PortfolioOptimizer(tickers, "2020-01-01", "2022-01-01")

    return opt


class TestWeightValidity:
    """All strategies must produce weights that sum to ~1.0 and are non-negative."""

    def _check_weights(self, result, n_tickers=5):
        w = np.array(result["weights"])
        assert len(w) == n_tickers
        assert np.all(w >= -1e-8), f"Negative weights: {w}"
        assert abs(w.sum() - 1.0) < 1e-6, f"Weights sum to {w.sum()}"
        assert result["volatility"] > 0
        assert "sharpe" in result

    def test_max_sharpe(self, optimizer):
        self._check_weights(optimizer.max_sharpe())

    def test_min_volatility(self, optimizer):
        self._check_weights(optimizer.min_volatility())

    def test_max_return(self, optimizer):
        self._check_weights(optimizer.max_return())

    def test_equal_weight(self, optimizer):
        result = optimizer.equal_weight()
        self._check_weights(result)
        w = np.array(result["weights"])
        assert np.allclose(w, 1.0 / 5)

    def test_risk_parity(self, optimizer):
        self._check_weights(optimizer.risk_parity())

    def test_hrp(self, optimizer):
        self._check_weights(optimizer.hrp())

    def test_black_litterman_no_views(self, optimizer):
        self._check_weights(optimizer.black_litterman(views=[]))

    def test_black_litterman_with_views(self, optimizer):
        views = [
            {"ticker": "AAPL", "expected_return": 0.15},
            {"ticker": "MSFT", "expected_return": 0.10},
        ]
        result = optimizer.black_litterman(views=views, confidences=[0.8, 0.6])
        self._check_weights(result)


class TestGetAllStrategies:
    """Test the orchestrator method."""

    def test_returns_all_base_strategies(self, optimizer):
        result = optimizer.get_all_strategies()
        expected = {"max_sharpe", "min_volatility", "risk_parity", "equal_weight", "max_return", "hrp"}
        assert expected.issubset(set(result.keys()))

    def test_includes_bl_when_views_provided(self, optimizer):
        views = [{"ticker": "AAPL", "expected_return": 0.12}]
        result = optimizer.get_all_strategies(views=views)
        assert "black_litterman" in result


class TestMetrics:
    """Test performance metric calculations."""

    def test_metrics_structure(self, optimizer):
        w = np.ones(5) / 5
        m = optimizer.compute_metrics(w.tolist())
        assert "annual_return" in m
        assert "annual_volatility" in m
        assert "sharpe" in m
        assert "sortino" in m
        assert "max_drawdown" in m
        assert "calmar" in m

    def test_max_drawdown_is_negative(self, optimizer):
        w = np.ones(5) / 5
        m = optimizer.compute_metrics(w.tolist())
        assert m["max_drawdown"] <= 0

    def test_transaction_cost_reduces_return(self, optimizer):
        w = np.ones(5) / 5
        m_no_cost = optimizer.compute_metrics(w.tolist(), cost_bps=0)
        m_with_cost = optimizer.compute_metrics(w.tolist(), cost_bps=50)
        assert m_with_cost["annual_return"] < m_no_cost["annual_return"]


class TestGrowth:
    """Test $10K growth computation."""

    def test_growth_starts_near_10k(self, optimizer):
        w = np.ones(5) / 5
        g = optimizer.growth_of_10k(w.tolist())
        assert len(g["dates"]) > 0
        assert len(g["values"]) > 0
        assert abs(g["values"][0] - 10000) < 500  # should be close to 10K


class TestBacktest:
    """Test rebalancing backtest."""

    def test_backtest_structure(self, optimizer):
        w = np.ones(5) / 5
        bt = optimizer.backtest(w.tolist(), "quarterly", 10)
        assert "dates" in bt
        assert "cumulative" in bt
        assert "drawdown" in bt
        assert "rolling_sharpe" in bt
        assert "total_cost" in bt
        assert len(bt["dates"]) == len(bt["cumulative"])

    def test_backtest_cost_accounted(self, optimizer):
        w = np.ones(5) / 5
        bt_no_cost = optimizer.backtest(w.tolist(), "quarterly", 0)
        bt_with_cost = optimizer.backtest(w.tolist(), "quarterly", 50)
        assert bt_with_cost["total_cost"] > 0
        assert bt_with_cost["cumulative"][-1] < bt_no_cost["cumulative"][-1]


class TestCorrelation:
    """Test correlation matrix."""

    def test_correlation_structure(self, optimizer):
        c = optimizer.get_correlation_matrix()
        assert len(c["tickers"]) == 5
        assert len(c["matrix"]) == 5
        assert len(c["matrix"][0]) == 5
        # Diagonal should be ~1
        for i in range(5):
            assert abs(c["matrix"][i][i] - 1.0) < 1e-10


class TestAssetAnalytics:
    """Test individual asset analytics."""

    def test_asset_analytics_structure(self, optimizer):
        a = optimizer.get_asset_analytics()
        assert len(a) == 5
        for ticker, info in a.items():
            assert "return" in info
            assert "volatility" in info
            assert "sharpe" in info
            assert "prices" in info
            assert len(info["prices"]["dates"]) > 0


class TestSectorConstraints:
    """Test sector constraint enforcement."""

    def test_constraints_respected(self, optimizer):
        sectors = {"AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "AMZN": "Consumer", "META": "Social"}
        sector_bounds = {"Tech": (0.0, 0.30)}
        result = optimizer.max_sharpe(sectors=sectors, sector_bounds=sector_bounds)
        w = np.array(result["weights"])
        tech_weight = w[0] + w[1] + w[2]  # AAPL + MSFT + GOOGL
        assert tech_weight <= 0.31, f"Tech weight {tech_weight:.4f} exceeds 30% cap"


class TestSimulation:
    """Test Monte Carlo simulation."""

    def test_simulation_size(self, optimizer):
        n = 1000
        sim = optimizer.simulate_portfolios(n)
        assert len(sim["returns"]) == n
        assert len(sim["volatility"]) == n
        assert len(sim["sharpe"]) == n
        assert len(sim["weights"]) == n


class TestEdgeCases:
    """Edge cases."""

    def test_two_tickers(self):
        tickers = ["AAPL", "MSFT"]
        mock_data = make_mock_data(tickers, 100)

        with patch("optimizer.yf") as mock_yf, \
             patch("optimizer.DataCache.get", return_value=None), \
             patch("optimizer.DataCache.put"):
            columns = pd.MultiIndex.from_product([["Close"], tickers])
            multi_df = pd.DataFrame(mock_data.values, index=mock_data.index, columns=columns)
            mock_yf.download.return_value = multi_df

            from optimizer import PortfolioOptimizer
            opt = PortfolioOptimizer(tickers, "2020-01-01", "2020-06-01")

        result = opt.get_all_strategies()
        for key, strat in result.items():
            w = np.array(strat["weights"])
            assert len(w) == 2
            assert abs(w.sum() - 1.0) < 1e-6
