/**
 * Smart Portfolio Optimizer — Frontend Application
 * Handles form input, API communication, and chart rendering.
 */

// ── Strategy Metadata ──────────────────────────────────────────
const STRATEGIES = {
    max_sharpe:    { label: 'Max Sharpe Ratio', icon: '📈', color: '#6366f1', colorBg: 'rgba(99,102,241,0.12)' },
    min_volatility:{ label: 'Min Volatility',   icon: '🛡️', color: '#06b6d4', colorBg: 'rgba(6,182,212,0.12)' },
    risk_parity:   { label: 'Risk Parity',      icon: '⚖️', color: '#f59e0b', colorBg: 'rgba(245,158,11,0.12)' },
    equal_weight:  { label: 'Equal Weight',      icon: '📊', color: '#8b5cf6', colorBg: 'rgba(139,92,246,0.12)' },
    max_return:    { label: 'Max Return',        icon: '🚀', color: '#ef4444', colorBg: 'rgba(239,68,68,0.12)' },
};

// ── DOM References ─────────────────────────────────────────────
const tickerInput     = document.getElementById('ticker-input');
const tickerPills     = document.getElementById('ticker-pills');
const startDate       = document.getElementById('start-date');
const endDate         = document.getElementById('end-date');
const rfSlider        = document.getElementById('risk-free-rate');
const rfValue         = document.getElementById('rf-value');
const numPortfolios   = document.getElementById('num-portfolios');
const optimizeBtn     = document.getElementById('optimize-btn');
const btnText         = optimizeBtn.querySelector('.btn-text');
const btnLoader       = optimizeBtn.querySelector('.btn-loader');
const errorBanner     = document.getElementById('error-banner');
const errorMessage    = document.getElementById('error-message');
const errorClose      = document.getElementById('error-close');
const resultsContainer = document.getElementById('results-container');
const frontierChart   = document.getElementById('frontier-chart');
const strategyCards   = document.getElementById('strategy-cards');
const metricsBody     = document.getElementById('metrics-body');

// ── Tickers State ──────────────────────────────────────────────
let tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'];

function renderPills() {
    tickerPills.innerHTML = '';
    tickers.forEach(t => {
        const pill = document.createElement('span');
        pill.className = 'ticker-pill';
        pill.innerHTML = `${t} <span class="remove">✕</span>`;
        pill.addEventListener('click', () => {
            tickers = tickers.filter(x => x !== t);
            renderPills();
        });
        tickerPills.appendChild(pill);
    });
}

tickerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        addTicker();
    }
});

tickerInput.addEventListener('blur', addTicker);

function addTicker() {
    const val = tickerInput.value.trim().replace(/,/g, '').toUpperCase();
    if (val && !tickers.includes(val)) {
        tickers.push(val);
        renderPills();
    }
    tickerInput.value = '';
}

// Click on wrapper focuses input
document.querySelector('.ticker-input-wrapper').addEventListener('click', (e) => {
    if (e.target === tickerInput) return;
    tickerInput.focus();
});

// Slider
rfSlider.addEventListener('input', () => {
    rfValue.textContent = (parseFloat(rfSlider.value) * 100).toFixed(1) + '%';
});

// Error handling
errorClose.addEventListener('click', () => { errorBanner.style.display = 'none'; });

function showError(msg) {
    errorMessage.textContent = msg;
    errorBanner.style.display = 'flex';
    errorBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hideError() {
    errorBanner.style.display = 'none';
}

// ── Optimize Button ────────────────────────────────────────────
optimizeBtn.addEventListener('click', runOptimization);

async function runOptimization() {
    hideError();

    if (tickers.length < 2) {
        showError('Please add at least 2 ticker symbols.');
        return;
    }

    // Set loading state
    optimizeBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'inline-flex';

    try {
        const response = await fetch('/api/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tickers: tickers,
                start_date: startDate.value,
                end_date: endDate.value,
                risk_free_rate: parseFloat(rfSlider.value),
                num_portfolios: parseInt(numPortfolios.value),
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Optimization failed.');
        }

        renderResults(data);
    } catch (err) {
        showError(err.message || 'Network error. Is the server running?');
    } finally {
        optimizeBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
}

// ── Render Results ─────────────────────────────────────────────
function renderResults(data) {
    resultsContainer.style.display = 'block';
    renderFrontierChart(data);
    renderStrategyCards(data);
    renderMetricsTable(data);

    // Scroll to results
    document.getElementById('chart-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Efficient Frontier Chart ───────────────────────────────────
function renderFrontierChart(data) {
    const sim = data.simulation;
    const strategies = data.strategies;

    // Scatter cloud
    const scatterTrace = {
        x: sim.volatility.map(v => v * 100),
        y: sim.returns.map(r => r * 100),
        mode: 'markers',
        type: 'scattergl',
        marker: {
            size: 4,
            color: sim.sharpe,
            colorscale: [
                [0, '#1e1b4b'],
                [0.25, '#4338ca'],
                [0.5, '#6366f1'],
                [0.75, '#06b6d4'],
                [1, '#22d3ee'],
            ],
            colorbar: {
                title: { text: 'Sharpe', font: { color: '#94a3b8', size: 11 } },
                tickfont: { color: '#64748b', size: 10 },
                thickness: 14,
                outlinewidth: 0,
                bgcolor: 'rgba(0,0,0,0)',
            },
            opacity: 0.5,
            line: { width: 0 },
        },
        text: sim.sharpe.map((s, i) =>
            `Sharpe: ${s.toFixed(3)}<br>Return: ${(sim.returns[i]*100).toFixed(2)}%<br>Vol: ${(sim.volatility[i]*100).toFixed(2)}%`
        ),
        hoverinfo: 'text',
        name: 'Simulated',
        showlegend: false,
    };

    // Strategy markers
    const stratTraces = Object.entries(strategies).map(([key, s]) => {
        const meta = STRATEGIES[key];
        return {
            x: [s.volatility * 100],
            y: [s.return * 100],
            mode: 'markers+text',
            type: 'scatter',
            marker: {
                size: 16,
                color: meta.color,
                symbol: 'star',
                line: { width: 2, color: '#fff' },
            },
            text: [meta.icon],
            textposition: 'top center',
            textfont: { size: 16 },
            name: meta.label,
            hovertemplate:
                `<b>${meta.label}</b><br>` +
                `Return: ${(s.return * 100).toFixed(2)}%<br>` +
                `Volatility: ${(s.volatility * 100).toFixed(2)}%<br>` +
                `Sharpe: ${s.sharpe.toFixed(3)}<extra></extra>`,
        };
    });

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter, sans-serif', color: '#94a3b8' },
        xaxis: {
            title: { text: 'Volatility (%)', font: { size: 13 } },
            gridcolor: 'rgba(255,255,255,0.04)',
            zerolinecolor: 'rgba(255,255,255,0.06)',
            ticksuffix: '%',
        },
        yaxis: {
            title: { text: 'Expected Return (%)', font: { size: 13 } },
            gridcolor: 'rgba(255,255,255,0.04)',
            zerolinecolor: 'rgba(255,255,255,0.06)',
            ticksuffix: '%',
        },
        legend: {
            bgcolor: 'rgba(0,0,0,0)',
            font: { size: 11, color: '#94a3b8' },
            orientation: 'h',
            y: -0.18,
            x: 0.5,
            xanchor: 'center',
        },
        margin: { t: 20, r: 40, b: 80, l: 60 },
        hoverlabel: {
            bgcolor: '#1a2332',
            bordercolor: '#334155',
            font: { family: 'Inter, sans-serif', size: 12, color: '#f1f5f9' },
        },
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        displaylogo: false,
    };

    Plotly.newPlot(frontierChart, [scatterTrace, ...stratTraces], layout, config);
}

// ── Strategy Cards ─────────────────────────────────────────────
function renderStrategyCards(data) {
    strategyCards.innerHTML = '';
    const tickerList = data.tickers;

    Object.entries(data.strategies).forEach(([key, s]) => {
        const meta = STRATEGIES[key];
        const card = document.createElement('div');
        card.className = 'strategy-card';
        card.style.setProperty('--card-accent', meta.color);
        card.style.setProperty('--card-accent-bg', meta.colorBg);

        const donutId = `donut-${key}`;

        card.innerHTML = `
            <div class="card-header">
                <span class="card-icon">${meta.icon}</span>
                <span class="card-name">${meta.label}</span>
            </div>
            <div class="card-stats">
                <div class="stat">
                    <div class="stat-value">${(s.return * 100).toFixed(1)}%</div>
                    <div class="stat-label">Return</div>
                </div>
                <div class="stat">
                    <div class="stat-value">${(s.volatility * 100).toFixed(1)}%</div>
                    <div class="stat-label">Risk</div>
                </div>
                <div class="stat">
                    <div class="stat-value">${s.sharpe.toFixed(2)}</div>
                    <div class="stat-label">Sharpe</div>
                </div>
            </div>
            <div class="card-donut" id="${donutId}"></div>
        `;

        strategyCards.appendChild(card);

        // Render donut chart
        renderDonut(donutId, tickerList, s.weights, meta.color);
    });
}

function renderDonut(containerId, labels, values, accentColor) {
    const colors = generatePalette(accentColor, labels.length);

    const trace = {
        labels: labels,
        values: values.map(v => (v * 100).toFixed(1)),
        type: 'pie',
        hole: 0.55,
        textinfo: 'label+percent',
        textposition: 'outside',
        textfont: { size: 10, color: '#94a3b8', family: 'Inter, sans-serif' },
        marker: {
            colors: colors,
            line: { color: '#111827', width: 2 },
        },
        hovertemplate: '<b>%{label}</b><br>%{percent}<extra></extra>',
        sort: false,
    };

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        showlegend: false,
        margin: { t: 5, r: 30, b: 5, l: 30 },
        hoverlabel: {
            bgcolor: '#1a2332',
            bordercolor: '#334155',
            font: { family: 'Inter, sans-serif', size: 12, color: '#f1f5f9' },
        },
    };

    Plotly.newPlot(containerId, [trace], layout, {
        responsive: true,
        displayModeBar: false,
    });
}

function generatePalette(baseColor, count) {
    // Generate a palette by rotating hue from the base accent color
    const base = hexToHSL(baseColor);
    const palette = [];
    for (let i = 0; i < count; i++) {
        const hue = (base.h + (i * 360 / count)) % 360;
        palette.push(`hsl(${hue}, ${Math.max(base.s - 10, 40)}%, ${Math.min(base.l + 10, 65)}%)`);
    }
    return palette;
}

function hexToHSL(hex) {
    let r = parseInt(hex.slice(1, 3), 16) / 255;
    let g = parseInt(hex.slice(3, 5), 16) / 255;
    let b = parseInt(hex.slice(5, 7), 16) / 255;
    let max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h, s, l = (max + min) / 2;

    if (max === min) {
        h = s = 0;
    } else {
        let d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
            case g: h = ((b - r) / d + 2) / 6; break;
            case b: h = ((r - g) / d + 4) / 6; break;
        }
        h *= 360;
    }
    return { h: Math.round(h), s: Math.round(s * 100), l: Math.round(l * 100) };
}

// ── Metrics Table ──────────────────────────────────────────────
function renderMetricsTable(data) {
    metricsBody.innerHTML = '';

    Object.entries(data.strategies).forEach(([key, s]) => {
        const meta = STRATEGIES[key];
        const m = data.metrics[key];

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <span class="strategy-badge">
                    <span class="badge-dot" style="background:${meta.color}"></span>
                    ${meta.label}
                </span>
            </td>
            <td class="metric-mono ${m.annual_return >= 0 ? 'metric-positive' : 'metric-negative'}">
                ${(m.annual_return * 100).toFixed(2)}%
            </td>
            <td class="metric-mono">${(m.annual_volatility * 100).toFixed(2)}%</td>
            <td class="metric-mono">${m.sharpe.toFixed(3)}</td>
            <td class="metric-mono">${m.sortino.toFixed(3)}</td>
            <td class="metric-mono metric-negative">${(m.max_drawdown * 100).toFixed(1)}%</td>
            <td class="metric-mono">${m.calmar.toFixed(3)}</td>
        `;
        metricsBody.appendChild(row);
    });
}

// ── Init ───────────────────────────────────────────────────────
renderPills();
