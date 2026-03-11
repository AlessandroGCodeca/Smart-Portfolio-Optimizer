"""
Smart Portfolio Optimizer — Flask API & Web Server
Serves the interactive dashboard and provides JSON API endpoints.
"""

import traceback
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from optimizer import PortfolioOptimizer
import yfinance as yf

app = Flask(__name__)
CORS(app)


# ── Pages ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main dashboard."""
    return render_template("index.html")


# ── API Endpoints ────────────────────────────────────────────────────

@app.route("/api/optimize", methods=["POST"])
def optimize():
    """
    Run portfolio optimization.

    Request JSON:
        tickers: list[str]          — stock symbols
        start_date: str             — YYYY-MM-DD
        end_date: str               — YYYY-MM-DD
        risk_free_rate: float       — e.g. 0.01
        num_portfolios: int         — simulation count (default 5000)
        bounds: list[[min, max]]    — optional per-asset weight bounds

    Response JSON:
        strategies: dict            — results for each strategy
        simulation: dict            — Monte Carlo scatter data
        metrics: dict               — performance metrics per strategy
        tickers: list[str]
    """
    try:
        data = request.get_json()
        tickers = data.get("tickers", ["AAPL", "MSFT", "GOOGL"])
        start_date = data.get("start_date", "2020-01-01")
        end_date = data.get("end_date", "2025-01-01")
        risk_free_rate = float(data.get("risk_free_rate", 0.01))
        num_portfolios = int(data.get("num_portfolios", 5000))
        raw_bounds = data.get("bounds", None)

        bounds = None
        if raw_bounds:
            bounds = [(b[0], b[1]) for b in raw_bounds]

        # Initialize optimizer
        optimizer = PortfolioOptimizer(tickers, start_date, end_date, risk_free_rate)

        # Run all strategies
        strategies = optimizer.get_all_strategies(bounds)

        # Run Monte Carlo simulation
        simulation = optimizer.simulate_portfolios(num_portfolios)

        # Compute metrics for each strategy
        metrics = {}
        for name, strat in strategies.items():
            metrics[name] = optimizer.compute_metrics(strat["weights"])

        return jsonify({
            "strategies": strategies,
            "simulation": simulation,
            "metrics": metrics,
            "tickers": tickers,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/validate", methods=["POST"])
def validate_tickers():
    """
    Validate ticker symbols.

    Request JSON:  { "tickers": ["AAPL", "XYZ"] }
    Response JSON: { "valid": ["AAPL"], "invalid": ["XYZ"] }
    """
    try:
        data = request.get_json()
        tickers = data.get("tickers", [])
        valid, invalid = [], []

        for t in tickers:
            try:
                info = yf.Ticker(t).info
                if info and info.get("regularMarketPrice") is not None:
                    valid.append(t.upper())
                else:
                    invalid.append(t.upper())
            except Exception:
                invalid.append(t.upper())

        return jsonify({"valid": valid, "invalid": invalid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("\n🚀 Smart Portfolio Optimizer")
    print("   Dashboard: http://localhost:5000\n")
    app.run(debug=True, port=5000)
