# Smart Portfolio Optimizer

A **full-stack portfolio optimization platform** built with Modern Portfolio Theory (MPT). Fetches real stock data, runs multiple optimization strategies, and visualizes results through a premium interactive web dashboard.

<p align="center">
  <img src="docs/dashboard.png" alt="Dashboard Preview" width="800">
</p>

## ✨ Features

### Optimization Strategies
| Strategy | Description |
|----------|-------------|
| 📈 **Max Sharpe Ratio** | Maximize risk-adjusted return |
| 🛡️ **Min Volatility** | Minimize portfolio risk |
| ⚖️ **Risk Parity** | Equalize each asset's risk contribution |
| 📊 **Equal Weight** | Benchmark 1/n allocation |
| 🚀 **Max Return** | Maximize expected return (aggressive) |

### Performance Metrics
- **Sharpe Ratio** — risk-adjusted return
- **Sortino Ratio** — downside-risk-adjusted return
- **Max Drawdown** — largest peak-to-trough decline
- **Calmar Ratio** — return vs. max drawdown

### Interactive Dashboard
- 🎨 Premium dark-mode glassmorphism UI
- 📊 Interactive Plotly.js efficient frontier chart
- 🍩 Donut weight allocation charts per strategy
- 📋 Side-by-side strategy comparison cards
- 🎚️ Configurable tickers, dates, risk-free rate, and simulation count

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/AlessandroGCodeca/Smart-Portfolio-Optimizer.git
cd Smart-Portfolio-Optimizer
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the Web Dashboard

```bash
python app.py
# → Open http://localhost:5000
```

### Run CLI Mode

```bash
python main.py
```

---

## 🏗️ Project Structure

```
Smart-Portfolio-Optimizer/
├── optimizer.py          # Core optimization engine (MPT + scipy)
├── app.py                # Flask API server
├── main.py               # CLI entry point
├── requirements.txt      # Python dependencies
├── templates/
│   └── index.html        # Dashboard HTML
└── static/
    ├── css/
    │   └── style.css     # Dark-mode theme
    └── js/
        └── app.js        # Frontend logic + Plotly.js charts
```

## 📐 Modern Portfolio Theory Math

| Concept | Formula |
|---------|---------|
| Expected Return | $\mu = \frac{1}{N} \sum_{i=1}^{N} r_i$ |
| Portfolio Volatility | $\sigma_p = \sqrt{w^T \Sigma w}$ |
| Sharpe Ratio | $S = \frac{\mu_p - r_f}{\sigma_p}$ |
| Risk Parity | $RC_i = w_i \cdot (\Sigma w)_i / \sigma_p = \sigma_p / n$ |

## 🛠️ Tech Stack

- **Backend:** Python, Flask, NumPy, Pandas, SciPy, yfinance
- **Frontend:** HTML5, CSS3, JavaScript, Plotly.js
- **Data Source:** Yahoo Finance (via yfinance)

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
