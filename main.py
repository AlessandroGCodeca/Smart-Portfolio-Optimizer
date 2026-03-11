"""
Smart Portfolio Optimizer — CLI Entry Point
Run portfolio optimization and display results in the terminal.
"""

import numpy as np
from optimizer import PortfolioOptimizer

# ── User Configuration ───────────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
START_DATE = "2020-01-01"
END_DATE = "2025-01-01"
RISK_FREE_RATE = 0.01
NUM_PORTFOLIOS = 10000

# ── Run Optimizer ────────────────────────────────────────────────────
print("Smart Portfolio Optimizer")
print("=" * 50)
print(f"Tickers : {', '.join(TICKERS)}")
print(f"Period  : {START_DATE} → {END_DATE}")
print(f"Rf rate : {RISK_FREE_RATE:.2%}")
print(f"Sims    : {NUM_PORTFOLIOS:,}\n")

optimizer = PortfolioOptimizer(TICKERS, START_DATE, END_DATE, RISK_FREE_RATE)
strategies = optimizer.get_all_strategies()

STRATEGY_LABELS = {
    "max_sharpe": "📈 Max Sharpe Ratio",
    "min_volatility": "🛡️  Min Volatility",
    "risk_parity": "⚖️  Risk Parity",
    "equal_weight": "📊 Equal Weight",
    "max_return": "🚀 Max Return",
}

for key, label in STRATEGY_LABELS.items():
    s = strategies[key]
    metrics = optimizer.compute_metrics(s["weights"])
    print(f"\n{label}")
    print("-" * 40)
    print(f"  Return     : {s['return']:>8.2%}")
    print(f"  Volatility : {s['volatility']:>8.2%}")
    print(f"  Sharpe     : {s['sharpe']:>8.3f}")
    print(f"  Sortino    : {metrics['sortino']:>8.3f}")
    print(f"  Max DD     : {metrics['max_drawdown']:>8.2%}")
    print(f"  Calmar     : {metrics['calmar']:>8.3f}")
    print(f"  Weights:")
    for ticker, weight in zip(TICKERS, s["weights"]):
        bar = "█" * int(weight * 30)
        print(f"    {ticker:>5s}  {weight:>6.1%}  {bar}")

print(f"\n{'=' * 50}")
print("Run `python app.py` for the interactive web dashboard.")
