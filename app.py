"""
Smart Portfolio Optimizer — Flask API & Web Server
Serves the interactive dashboard and provides JSON API endpoints with SSE streaming.
"""

import json
import traceback
import queue
import threading

from flask import Flask, jsonify, request, render_template, Response, stream_with_context
from flask_cors import CORS
from optimizer import PortfolioOptimizer
import yfinance as yf

app = Flask(__name__)
CORS(app)


# ── Pages ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Main Optimization (standard POST) ───────────────────────────

@app.route("/api/optimize", methods=["POST"])
def optimize():
    """Full optimization with all strategies, simulation, backtest, and analytics."""
    try:
        data = request.get_json()
        result = _run_optimization(data)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── SSE Streaming Optimization ──────────────────────────────────

@app.route("/api/stream-optimize", methods=["POST"])
def stream_optimize():
    """
    Server-Sent Events endpoint for optimization with progress updates.
    Emits: downloading, computing, simulating, optimizing, done.
    """
    data = request.get_json()

    def generate():
        progress_queue = queue.Queue()

        def progress_callback(stage, message):
            progress_queue.put({"stage": stage, "message": message})

        def run():
            try:
                result = _run_optimization(data, progress_callback)
                progress_queue.put({"stage": "done", "data": result})
            except Exception as e:
                progress_queue.put({"stage": "error", "message": str(e)})

        thread = threading.Thread(target=run)
        thread.start()

        while True:
            try:
                msg = progress_queue.get(timeout=120)
                stage = msg.get("stage", "")
                if stage == "done":
                    yield f"event: done\ndata: {json.dumps(msg['data'])}\n\n"
                    break
                elif stage == "error":
                    yield f"event: error\ndata: {json.dumps({'error': msg['message']})}\n\n"
                    break
                else:
                    yield f"event: progress\ndata: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield f"event: error\ndata: {json.dumps({'error': 'Optimization timed out'})}\n\n"
                break

        thread.join(timeout=5)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Shared optimization logic ───────────────────────────────────

def _run_optimization(data: dict, progress_callback=None) -> dict:
    tickers = data.get("tickers", ["AAPL", "MSFT", "GOOGL"])
    start_date = data.get("start_date", "2020-01-01")
    end_date = data.get("end_date", "2025-01-01")
    risk_free_rate = float(data.get("risk_free_rate", 0.01))
    num_portfolios = int(data.get("num_portfolios", 5000))
    raw_bounds = data.get("bounds")
    views = data.get("views")            # B-L views
    confidences = data.get("confidences") # B-L confidences
    sectors = data.get("sectors")         # {ticker: sector}
    sector_bounds = data.get("sector_bounds")  # {sector: [min, max]}
    cost_bps = float(data.get("cost_bps", 0))
    rebalance_freq = data.get("rebalance_freq", "quarterly")

    bounds = None
    if raw_bounds:
        bounds = [(b[0], b[1]) for b in raw_bounds]

    # Convert sector_bounds from lists to tuples
    if sector_bounds:
        sector_bounds = {k: tuple(v) for k, v in sector_bounds.items()}

    # Initialize optimizer
    optimizer = PortfolioOptimizer(
        tickers, start_date, end_date, risk_free_rate,
        progress_callback=progress_callback,
    )

    # Run all strategies
    strategies = optimizer.get_all_strategies(
        bounds=bounds,
        views=views,
        confidences=confidences,
        sectors=sectors,
        sector_bounds=sector_bounds,
    )

    # Monte Carlo simulation
    simulation = optimizer.simulate_portfolios(num_portfolios)

    # Metrics + growth + backtest for each strategy
    if progress_callback:
        progress_callback("metrics", "Computing performance metrics...")

    metrics = {}
    growth = {}
    backtests = {}
    for name, strat in strategies.items():
        metrics[name] = optimizer.compute_metrics(strat["weights"], cost_bps)
        growth[name] = optimizer.growth_of_10k(strat["weights"], cost_bps)
        backtests[name] = optimizer.backtest(
            strat["weights"], rebalance_freq, cost_bps
        )

    # Correlation + asset analytics
    correlation = optimizer.get_correlation_matrix()
    asset_analytics = optimizer.get_asset_analytics()

    return {
        "strategies": strategies,
        "simulation": simulation,
        "metrics": metrics,
        "growth": growth,
        "backtests": backtests,
        "correlation": correlation,
        "asset_analytics": asset_analytics,
        "tickers": tickers,
    }


# ── Validate tickers ─────────────────────────────────────────────

@app.route("/api/validate", methods=["POST"])
def validate_tickers():
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
    print("\n🚀 Smart Portfolio Optimizer v2")
    print("   Dashboard: http://localhost:5000\n")
    app.run(debug=True, port=5000, threaded=True)
