/**
 * Smart Portfolio Optimizer v2 — Frontend Application
 * SSE progress, tabbed results, B-L views, sector constraints,
 * correlation heatmap, asset cards, backtest charts.
 */

// ── Strategy Metadata ──────────────────────────────────────────
const STRATEGIES = {
    max_sharpe:      { label: 'Max Sharpe Ratio', icon: '📈', color: '#6366f1', colorBg: 'rgba(99,102,241,0.12)' },
    min_volatility:  { label: 'Min Volatility',   icon: '🛡️', color: '#06b6d4', colorBg: 'rgba(6,182,212,0.12)' },
    risk_parity:     { label: 'Risk Parity',      icon: '⚖️', color: '#f59e0b', colorBg: 'rgba(245,158,11,0.12)' },
    equal_weight:    { label: 'Equal Weight',      icon: '📊', color: '#8b5cf6', colorBg: 'rgba(139,92,246,0.12)' },
    max_return:      { label: 'Max Return',        icon: '🚀', color: '#ef4444', colorBg: 'rgba(239,68,68,0.12)' },
    hrp:             { label: 'HRP',               icon: '🌳', color: '#10b981', colorBg: 'rgba(16,185,129,0.12)' },
    black_litterman: { label: 'Black-Litterman',   icon: '🧠', color: '#ec4899', colorBg: 'rgba(236,72,153,0.12)' },
};

const PLOTLY_THEME = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Inter, sans-serif', color: '#94a3b8' },
    xaxis: { gridcolor: 'rgba(255,255,255,0.04)', zerolinecolor: 'rgba(255,255,255,0.06)' },
    yaxis: { gridcolor: 'rgba(255,255,255,0.04)', zerolinecolor: 'rgba(255,255,255,0.06)' },
    hoverlabel: { bgcolor: '#1a2332', bordercolor: '#334155', font: { family: 'Inter, sans-serif', size: 12, color: '#f1f5f9' } },
};
const PLOTLY_CONFIG = { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false };

// ── DOM References ─────────────────────────────────────────────
const $ = id => document.getElementById(id);
const tickerInput     = $('ticker-input');
const tickerPills     = $('ticker-pills');
const startDate       = $('start-date');
const endDate         = $('end-date');
const rfSlider        = $('risk-free-rate');
const rfValue         = $('rf-value');
const numPortfolios   = $('num-portfolios');
const costSlider      = $('cost-bps');
const costValue       = $('cost-value');
const rebalanceFreq   = $('rebalance-freq');
const optimizeBtn     = $('optimize-btn');
const btnText         = optimizeBtn.querySelector('.btn-text');
const btnLoader       = optimizeBtn.querySelector('.btn-loader');
const progressContainer = $('progress-container');
const progressMessage   = $('progress-message');
const errorBanner     = $('error-banner');
const errorMessage    = $('error-message');
const errorClose      = $('error-close');
const resultsContainer = $('results-container');

// ── State ──────────────────────────────────────────────────────
let tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'];
let sectorMap = {};  // {ticker: sector}
let lastResultData = null; // Store latest optimization results

// ── Ticker Pills ───────────────────────────────────────────────
function renderPills() {
    tickerPills.innerHTML = '';
    tickers.forEach(t => {
        const pill = document.createElement('span');
        pill.className = 'ticker-pill';
        pill.innerHTML = `${t} <span class="remove">✕</span>`;
        pill.addEventListener('click', () => { tickers = tickers.filter(x => x !== t); renderPills(); updateSectorMappings(); });
        tickerPills.appendChild(pill);
    });
}

tickerInput.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTicker(); } });
tickerInput.addEventListener('blur', addTicker);

function addTicker() {
    const val = tickerInput.value.trim().replace(/,/g, '').toUpperCase();
    if (val && !tickers.includes(val)) { tickers.push(val); renderPills(); updateSectorMappings(); }
    tickerInput.value = '';
}

document.querySelector('.ticker-input-wrapper').addEventListener('click', e => { if (e.target !== tickerInput) tickerInput.focus(); });

// ── Sliders ────────────────────────────────────────────────────
rfSlider.addEventListener('input', () => { rfValue.textContent = (parseFloat(rfSlider.value) * 100).toFixed(1) + '%'; });
costSlider.addEventListener('input', () => { costValue.textContent = costSlider.value + ' bps'; });

// ── Error ──────────────────────────────────────────────────────
errorClose.addEventListener('click', () => { errorBanner.style.display = 'none'; });
function showError(msg) { errorMessage.textContent = msg; errorBanner.style.display = 'flex'; errorBanner.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
function hideError() { errorBanner.style.display = 'none'; }

// ── Tabs ───────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        $(btn.dataset.tab).classList.add('active');
        // Re-trigger plotly relayout for visible charts
        window.dispatchEvent(new Event('resize'));
    });
});

// ── Black-Litterman Views UI ───────────────────────────────────
const blContainer = $('bl-views-container');
$('bl-add-view').addEventListener('click', addBLView);

function addBLView() {
    const row = document.createElement('div');
    row.className = 'bl-view-row';
    const options = tickers.map(t => `<option value="${t}">${t}</option>`).join('');
    row.innerHTML = `
        <div class="input-group" style="margin:0">
            <label>Ticker</label>
            <select class="bl-ticker">${options}</select>
        </div>
        <div class="input-group" style="margin:0">
            <label>Expected Return (%)</label>
            <input type="number" class="bl-return" step="0.1" value="10" placeholder="10">
        </div>
        <div class="input-group" style="margin:0">
            <label>Confidence</label>
            <input type="number" class="bl-confidence" step="0.1" min="0.1" max="1" value="0.5">
        </div>
        <button class="btn-remove" title="Remove">✕</button>
    `;
    row.querySelector('.btn-remove').addEventListener('click', () => row.remove());
    blContainer.appendChild(row);
}

function getBLViews() {
    const rows = blContainer.querySelectorAll('.bl-view-row');
    if (rows.length === 0) return { views: null, confidences: null };
    const views = [], confidences = [];
    rows.forEach(row => {
        views.push({ ticker: row.querySelector('.bl-ticker').value, expected_return: parseFloat(row.querySelector('.bl-return').value) / 100 });
        confidences.push(parseFloat(row.querySelector('.bl-confidence').value));
    });
    return { views, confidences };
}

// ── Sector Constraints UI ──────────────────────────────────────
const sectorMappings = $('sector-mappings-container');
const sectorBoundsContainer = $('sector-bounds-container');
$('sector-refresh').addEventListener('click', refreshSectorBounds);

function updateSectorMappings() {
    sectorMappings.innerHTML = '';
    tickers.forEach(t => {
        const row = document.createElement('div');
        row.className = 'sector-mapping-row';
        row.innerHTML = `
            <span class="ticker-label">${t}</span>
            <input type="text" class="sector-input" data-ticker="${t}" placeholder="e.g. Technology" value="${sectorMap[t] || ''}">
        `;
        row.querySelector('.sector-input').addEventListener('change', e => { sectorMap[t] = e.target.value.trim(); });
        sectorMappings.appendChild(row);
    });
}

function refreshSectorBounds() {
    // Collect unique sectors
    const sectors = [...new Set(Object.values(sectorMap).filter(s => s))];
    sectorBoundsContainer.innerHTML = '';
    sectors.forEach(sec => {
        const row = document.createElement('div');
        row.className = 'sector-bound-row';
        row.innerHTML = `
            <span class="sector-name">${sec}</span>
            <input type="number" class="sec-min" data-sector="${sec}" min="0" max="100" step="1" value="0" placeholder="0">
            <span class="bound-label">Min %</span>
            <input type="number" class="sec-max" data-sector="${sec}" min="0" max="100" step="1" value="100" placeholder="100">
            <span class="bound-label">Max %</span>
        `;
        sectorBoundsContainer.appendChild(row);
    });
}

function getSectorData() {
    const sectors = {};
    const bounds = {};
    sectorMappings.querySelectorAll('.sector-input').forEach(input => {
        const val = input.value.trim();
        if (val) sectors[input.dataset.ticker] = val;
    });
    sectorBoundsContainer.querySelectorAll('.sector-bound-row').forEach(row => {
        const sec = row.querySelector('.sector-name').textContent;
        const min = parseFloat(row.querySelector('.sec-min').value) / 100;
        const max = parseFloat(row.querySelector('.sec-max').value) / 100;
        bounds[sec] = [min, max];
    });
    const hasSectors = Object.keys(sectors).length > 0 && Object.keys(bounds).length > 0;
    return { sectors: hasSectors ? sectors : null, sector_bounds: hasSectors ? bounds : null };
}

// ── Progress ───────────────────────────────────────────────────
const stages = ['downloading', 'computing', 'optimizing', 'simulating', 'metrics'];

function showProgress() {
    progressContainer.style.display = 'block';
    document.querySelectorAll('.progress-step').forEach(s => { s.classList.remove('active', 'done'); });
    progressMessage.textContent = 'Initializing…';
}

function updateProgress(stage, message) {
    progressMessage.textContent = message || stage;
    const idx = stages.indexOf(stage);
    document.querySelectorAll('.progress-step').forEach((step, i) => {
        step.classList.remove('active', 'done');
        if (i < idx) step.classList.add('done');
        else if (i === idx) step.classList.add('active');
    });
}

function hideProgress() { progressContainer.style.display = 'none'; }

// ── Optimization ───────────────────────────────────────────────
optimizeBtn.addEventListener('click', runOptimization);

async function runOptimization() {
    hideError();
    if (tickers.length < 2) { showError('Please add at least 2 ticker symbols.'); return; }

    optimizeBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'inline-flex';
    showProgress();

    const { views, confidences } = getBLViews();
    const { sectors, sector_bounds } = getSectorData();

    const payload = {
        tickers,
        start_date: startDate.value,
        end_date: endDate.value,
        risk_free_rate: parseFloat(rfSlider.value),
        num_portfolios: parseInt(numPortfolios.value),
        cost_bps: parseInt(costSlider.value),
        rebalance_freq: rebalanceFreq.value,
        views, confidences, sectors, sector_bounds,
    };

    try {
        // Try SSE streaming first
        const response = await fetch('/api/stream-optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!response.ok) throw new Error('Server error');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let result = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('event: progress')) continue;
                if (line.startsWith('event: done')) continue;
                if (line.startsWith('event: error')) continue;
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.stage && data.stage !== 'done' && data.stage !== 'error') {
                            updateProgress(data.stage, data.message);
                        } else if (data.error) {
                            throw new Error(data.error);
                        } else if (data.strategies) {
                            result = data;
                        }
                    } catch (e) {
                        if (e.message && !e.message.includes('JSON')) throw e;
                    }
                }
            }
        }

        if (result) {
            renderResults(result);
        } else {
            throw new Error('No results received.');
        }
    } catch (err) {
        // Fallback to standard POST
        try {
            const response = await fetch('/api/optimize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Optimization failed.');
            renderResults(data);
        } catch (err2) {
            showError(err2.message || 'Network error. Is the server running?');
        }
    } finally {
        optimizeBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
        hideProgress();
    }
}

// ── Render Results ─────────────────────────────────────────────
function renderResults(data) {
    lastResultData = data;
    resultsContainer.style.display = 'block';

    // Populate advanced dropdowns
    populateStrategyDropdowns(data);

    // Frontier tab
    renderFrontierChart(data);
    renderStrategyCards(data);
    renderMetricsTable(data);

    // Performance tab
    renderGrowthChart(data);

    // Analysis tab
    renderCorrelationHeatmap(data);
    renderAssetCards(data);

    // Backtest tab
    renderBacktestCharts(data);

    // Activate first tab and scroll
    document.querySelector('.tab-btn[data-tab="tab-frontier"]').click();
    $('results-tabs').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Efficient Frontier ─────────────────────────────────────────
function renderFrontierChart(data) {
    const sim = data.simulation;

    const scatterTrace = {
        x: sim.volatility.map(v => v * 100), y: sim.returns.map(r => r * 100),
        mode: 'markers', type: 'scattergl',
        marker: {
            size: 4, color: sim.sharpe, opacity: 0.5, line: { width: 0 },
            colorscale: [[0,'#1e1b4b'],[0.25,'#4338ca'],[0.5,'#6366f1'],[0.75,'#06b6d4'],[1,'#22d3ee']],
            colorbar: { title: { text: 'Sharpe', font: { color: '#94a3b8', size: 11 } }, tickfont: { color: '#64748b', size: 10 }, thickness: 14, outlinewidth: 0, bgcolor: 'rgba(0,0,0,0)' },
        },
        text: sim.sharpe.map((s, i) => `Sharpe: ${s.toFixed(3)}<br>Return: ${(sim.returns[i]*100).toFixed(2)}%<br>Vol: ${(sim.volatility[i]*100).toFixed(2)}%`),
        hoverinfo: 'text', name: 'Simulated', showlegend: false,
    };

    const stratTraces = Object.entries(data.strategies).map(([key, s]) => {
        const meta = STRATEGIES[key];
        if (!meta) return null;
        return {
            x: [s.volatility * 100], y: [s.return * 100],
            mode: 'markers+text', type: 'scatter',
            marker: { size: 16, color: meta.color, symbol: 'star', line: { width: 2, color: '#fff' } },
            text: [meta.icon], textposition: 'top center', textfont: { size: 14 },
            name: meta.label,
            hovertemplate: `<b>${meta.label}</b><br>Return: ${(s.return*100).toFixed(2)}%<br>Vol: ${(s.volatility*100).toFixed(2)}%<br>Sharpe: ${s.sharpe.toFixed(3)}<extra></extra>`,
        };
    }).filter(Boolean);

    Plotly.newPlot($('frontier-chart'), [scatterTrace, ...stratTraces], {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Volatility (%)', font: { size: 13 } }, ticksuffix: '%' },
        yaxis: { ...PLOTLY_THEME.yaxis, title: { text: 'Expected Return (%)', font: { size: 13 } }, ticksuffix: '%' },
        legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: '#94a3b8' }, orientation: 'h', y: -0.18, x: 0.5, xanchor: 'center' },
        margin: { t: 20, r: 40, b: 80, l: 60 },
    }, PLOTLY_CONFIG);
}

// ── Strategy Cards ─────────────────────────────────────────────
function renderStrategyCards(data) {
    const container = $('strategy-cards');
    container.innerHTML = '';
    Object.entries(data.strategies).forEach(([key, s]) => {
        const meta = STRATEGIES[key];
        if (!meta) return;
        const card = document.createElement('div');
        card.className = 'strategy-card';
        card.style.setProperty('--card-accent', meta.color);
        card.style.setProperty('--card-accent-bg', meta.colorBg);
        const donutId = `donut-${key}`;
        card.innerHTML = `
            <div class="card-header"><span class="card-icon">${meta.icon}</span><span class="card-name">${meta.label}</span></div>
            <div class="card-stats">
                <div class="stat"><div class="stat-value">${(s.return*100).toFixed(1)}%</div><div class="stat-label">Return</div></div>
                <div class="stat"><div class="stat-value">${(s.volatility*100).toFixed(1)}%</div><div class="stat-label">Risk</div></div>
                <div class="stat"><div class="stat-value">${s.sharpe.toFixed(2)}</div><div class="stat-label">Sharpe</div></div>
            </div>
            <div class="card-donut" id="${donutId}"></div>`;
        container.appendChild(card);
        renderDonut(donutId, data.tickers, s.weights, meta.color);
    });
}

function renderDonut(id, labels, values, accent) {
    Plotly.newPlot($(id), [{
        labels, values: values.map(v => (v*100).toFixed(1)), type: 'pie', hole: 0.55,
        textinfo: 'label+percent', textposition: 'outside',
        textfont: { size: 10, color: '#94a3b8', family: 'Inter' },
        marker: { colors: generatePalette(accent, labels.length), line: { color: '#111827', width: 2 } },
        hovertemplate: '<b>%{label}</b><br>%{percent}<extra></extra>', sort: false,
    }], { ...PLOTLY_THEME, showlegend: false, margin: { t: 5, r: 30, b: 5, l: 30 } }, { responsive: true, displayModeBar: false });
}

// ── Metrics Table ──────────────────────────────────────────────
function renderMetricsTable(data) {
    const body = $('metrics-body');
    body.innerHTML = '';
    Object.entries(data.strategies).forEach(([key]) => {
        const meta = STRATEGIES[key];
        if (!meta) return;
        const m = data.metrics[key];
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><span class="strategy-badge"><span class="badge-dot" style="background:${meta.color}"></span>${meta.label}</span></td>
            <td class="metric-mono ${m.annual_return >= 0 ? 'metric-positive' : 'metric-negative'}">${(m.annual_return*100).toFixed(2)}%</td>
            <td class="metric-mono">${(m.annual_volatility*100).toFixed(2)}%</td>
            <td class="metric-mono">${m.sharpe.toFixed(3)}</td>
            <td class="metric-mono">${m.sortino.toFixed(3)}</td>
            <td class="metric-mono metric-negative">${(m.max_drawdown*100).toFixed(1)}%</td>
            <td class="metric-mono">${m.calmar.toFixed(3)}</td>
            <td class="metric-mono metric-negative">${m.var_95 !== undefined ? (m.var_95*100).toFixed(2) + '%' : 'N/A'}</td>
            <td class="metric-mono metric-negative">${m.cvar_95 !== undefined ? (m.cvar_95*100).toFixed(2) + '%' : 'N/A'}</td>`;
        body.appendChild(row);
    });
}

// ── Growth of $10K Chart ───────────────────────────────────────
function renderGrowthChart(data) {
    if (!data.growth) return;
    const traces = Object.entries(data.growth).map(([key, g]) => {
        const meta = STRATEGIES[key];
        if (!meta) return null;
        return {
            x: g.dates, y: g.values, type: 'scatter', mode: 'lines',
            name: meta.label, line: { color: meta.color, width: 2 },
            hovertemplate: `<b>${meta.label}</b><br>%{x}<br>$%{y:,.0f}<extra></extra>`,
        };
    }).filter(Boolean);

    Plotly.newPlot($('growth-chart'), traces, {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Date', font: { size: 13 } } },
        yaxis: { ...PLOTLY_THEME.yaxis, title: { text: 'Portfolio Value ($)', font: { size: 13 } }, tickprefix: '$', tickformat: ',.0f' },
        legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: '#94a3b8' } },
        margin: { t: 20, r: 30, b: 60, l: 70 },
        hovermode: 'x unified',
    }, PLOTLY_CONFIG);
}

// ── Correlation Heatmap ────────────────────────────────────────
function renderCorrelationHeatmap(data) {
    if (!data.correlation) return;
    const { tickers: t, matrix } = data.correlation;
    const textMatrix = matrix.map(row => row.map(v => v.toFixed(2)));

    Plotly.newPlot($('correlation-heatmap'), [{
        z: matrix, x: t, y: t, type: 'heatmap',
        colorscale: [[0,'#1e1b4b'],[0.25,'#312e81'],[0.5,'#4338ca'],[0.75,'#06b6d4'],[1,'#22d3ee']],
        zmin: -1, zmax: 1,
        text: textMatrix, texttemplate: '%{text}', textfont: { size: 11, color: '#f1f5f9' },
        hovertemplate: '<b>%{x} × %{y}</b><br>Correlation: %{z:.3f}<extra></extra>',
        colorbar: { title: { text: 'ρ', font: { color: '#94a3b8' } }, tickfont: { color: '#64748b' }, outlinewidth: 0 },
    }], {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, tickfont: { size: 12, color: '#94a3b8' } },
        yaxis: { ...PLOTLY_THEME.yaxis, tickfont: { size: 12, color: '#94a3b8' }, autorange: 'reversed' },
        margin: { t: 20, r: 80, b: 60, l: 60 },
    }, PLOTLY_CONFIG);
}

// ── Asset Cards ────────────────────────────────────────────────
function renderAssetCards(data) {
    if (!data.asset_analytics) return;
    const container = $('asset-cards');
    container.innerHTML = '';

    Object.entries(data.asset_analytics).forEach(([ticker, info], i) => {
        const card = document.createElement('div');
        card.className = 'asset-card';
        card.style.animationDelay = `${i * 0.08}s`;
        const retPct = (info.return * 100).toFixed(1);
        const isPositive = info.return >= 0;
        const sparkId = `spark-${ticker}`;

        card.innerHTML = `
            <div class="asset-header">
                <span class="asset-ticker">${ticker}</span>
                <span class="asset-badge ${isPositive ? 'positive' : 'negative'}">${isPositive ? '▲' : '▼'} ${retPct}%</span>
            </div>
            <div class="asset-stats">
                <div class="stat"><div class="asset-stat-value">${retPct}%</div><div class="asset-stat-label">Return</div></div>
                <div class="stat"><div class="asset-stat-value">${(info.volatility*100).toFixed(1)}%</div><div class="asset-stat-label">Vol</div></div>
                <div class="stat"><div class="asset-stat-value">${info.sharpe.toFixed(2)}</div><div class="asset-stat-label">Sharpe</div></div>
            </div>
            <div class="asset-sparkline" id="${sparkId}"></div>`;
        container.appendChild(card);

        // Sparkline
        Plotly.newPlot($(sparkId), [{
            x: info.prices.dates, y: info.prices.values,
            type: 'scatter', mode: 'lines',
            line: { color: isPositive ? '#22c55e' : '#ef4444', width: 1.5 },
            fill: 'tozeroy', fillcolor: isPositive ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
            hovertemplate: '%{x}<br>$%{y:.2f}<extra></extra>',
        }], {
            ...PLOTLY_THEME, showlegend: false,
            xaxis: { ...PLOTLY_THEME.xaxis, visible: false },
            yaxis: { ...PLOTLY_THEME.yaxis, visible: false },
            margin: { t: 0, r: 0, b: 0, l: 0 },
        }, { responsive: true, displayModeBar: false });
    });
}

// ── Backtest Charts ────────────────────────────────────────────
function renderBacktestCharts(data) {
    if (!data.backtests) return;

    // Cumulative
    const cumTraces = Object.entries(data.backtests).map(([key, bt]) => {
        const meta = STRATEGIES[key]; if (!meta) return null;
        return { x: bt.dates, y: bt.cumulative, type: 'scatter', mode: 'lines', name: meta.label, line: { color: meta.color, width: 2 }, hovertemplate: `<b>${meta.label}</b><br>%{x}<br>$%{y:,.0f}<extra></extra>` };
    }).filter(Boolean);

    Plotly.newPlot($('backtest-chart'), cumTraces, {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Date', font: { size: 13 } } },
        yaxis: { ...PLOTLY_THEME.yaxis, title: { text: 'Value ($)', font: { size: 13 } }, tickprefix: '$', tickformat: ',.0f' },
        legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: '#94a3b8' } },
        margin: { t: 20, r: 30, b: 60, l: 70 }, hovermode: 'x unified',
    }, PLOTLY_CONFIG);

    // Drawdown
    const ddTraces = Object.entries(data.backtests).map(([key, bt]) => {
        const meta = STRATEGIES[key]; if (!meta) return null;
        return { x: bt.dates, y: bt.drawdown.map(d => d * 100), type: 'scatter', mode: 'lines', name: meta.label, line: { color: meta.color, width: 1.5 }, fill: 'tozeroy', fillcolor: meta.colorBg, hovertemplate: `<b>${meta.label}</b><br>%{x}<br>%{y:.1f}%<extra></extra>` };
    }).filter(Boolean);

    Plotly.newPlot($('drawdown-chart'), ddTraces, {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Date', font: { size: 13 } } },
        yaxis: { ...PLOTLY_THEME.yaxis, title: { text: 'Drawdown (%)', font: { size: 13 } }, ticksuffix: '%' },
        legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: '#94a3b8' } },
        margin: { t: 20, r: 30, b: 60, l: 60 }, hovermode: 'x unified',
    }, PLOTLY_CONFIG);

    // Rolling Sharpe
    const rsTraces = Object.entries(data.backtests).map(([key, bt]) => {
        const meta = STRATEGIES[key]; if (!meta) return null;
        return { x: bt.dates, y: bt.rolling_sharpe, type: 'scatter', mode: 'lines', name: meta.label, line: { color: meta.color, width: 1.5 }, hovertemplate: `<b>${meta.label}</b><br>%{x}<br>Sharpe: %{y:.2f}<extra></extra>` };
    }).filter(Boolean);

    Plotly.newPlot($('rolling-sharpe-chart'), rsTraces, {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Date', font: { size: 13 } } },
        yaxis: { ...PLOTLY_THEME.yaxis, title: { text: 'Rolling Sharpe', font: { size: 13 } } },
        legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: '#94a3b8' } },
        margin: { t: 20, r: 30, b: 60, l: 60 }, hovermode: 'x unified',
        shapes: [{ type: 'line', y0: 0, y1: 0, x0: 0, x1: 1, xref: 'paper', line: { color: 'rgba(255,255,255,0.15)', width: 1, dash: 'dash' } }],
    }, PLOTLY_CONFIG);
}

// ── New Features (Forecast & Factors) ────────────────────────
function populateStrategyDropdowns(data) {
    const forecastSelect = $('forecast-strategy');
    const factorSelect = $('factor-strategy');
    if (!forecastSelect || !factorSelect) return;
    
    forecastSelect.innerHTML = '';
    factorSelect.innerHTML = '';
    
    Object.keys(data.strategies).forEach(key => {
        const meta = STRATEGIES[key];
        if (!meta) return;
        const opt = `<option value="${key}">${meta.label}</option>`;
        forecastSelect.innerHTML += opt;
        factorSelect.innerHTML += opt;
    });
}

const btnRunForecast = $('btn-run-forecast');
if (btnRunForecast) {
    btnRunForecast.addEventListener('click', async () => {
        if (!lastResultData) return;
        const key = $('forecast-strategy').value;
        const years = parseInt($('forecast-years').value);
        const strat = lastResultData.strategies[key];
        
        btnRunForecast.disabled = true;
        btnRunForecast.textContent = 'Simulating...';
        try {
            const payload = {
                tickers: lastResultData.tickers,
                start_date: startDate.value,
                end_date: endDate.value,
                weights: strat.weights,
                years: years
            };
            const res = await fetch('/api/forecast', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const forecastData = await res.json();
            if(!res.ok) throw new Error(forecastData.error);
            renderForecastChart(forecastData, key);
        } catch(err) {
            alert("Forecast Error: " + err.message);
        } finally {
            btnRunForecast.disabled = false;
            btnRunForecast.textContent = 'Simulate';
        }
    });
}

const btnRunFactors = $('btn-run-factors');
if (btnRunFactors) {
    btnRunFactors.addEventListener('click', async () => {
        if (!lastResultData) return;
        const key = $('factor-strategy').value;
        const strat = lastResultData.strategies[key];
        
        btnRunFactors.disabled = true;
        btnRunFactors.textContent = 'Analyzing...';
        try {
            const payload = {
                tickers: lastResultData.tickers,
                start_date: startDate.value,
                end_date: endDate.value,
                weights: strat.weights
            };
            const res = await fetch('/api/factors', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const factorData = await res.json();
            if(!res.ok) throw new Error(factorData.error);
            renderFactorChart(factorData, key);
        } catch(err) {
            alert("Factor Analysis Error: " + err.message);
        } finally {
            btnRunFactors.disabled = false;
            btnRunFactors.textContent = 'Analyze';
        }
    });
}

function renderForecastChart(data, key) {
    const meta = STRATEGIES[key] || {color: '#6366f1'};
    const traces = [
        {
            x: data.dates, y: data.p10, type: 'scatter', mode: 'lines',
            line: {width: 0}, hoverinfo: 'skip', showlegend: false
        },
        {
            x: data.dates, y: data.p90, type: 'scatter', mode: 'lines',
            fill: 'tonexty', fillcolor: Object.assign({}, meta).colorBg || 'rgba(99,102,241,0.15)',
            line: {width: 0}, hoverinfo: 'skip', name: '10th-90th Pct'
        },
        {
            x: data.dates, y: data.p50, type: 'scatter', mode: 'lines',
            line: {color: meta.color, width: 2.5},
            name: 'Median (50th)',
            hovertemplate: '<b>%{x}</b><br>Median: $%{y:,.0f}<extra></extra>'
        }
    ];

    Plotly.newPlot($('forecast-chart'), traces, {
        ...PLOTLY_THEME,
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Date', font: { size: 13 } } },
        yaxis: { ...PLOTLY_THEME.yaxis, title: { text: 'Wealth ($)', font: { size: 13 } }, tickprefix: '$', tickformat: ',.0f' },
        legend: { bgcolor: 'rgba(0,0,0,0)', font: { size: 11, color: '#94a3b8' } },
        margin: { t: 20, r: 30, b: 60, l: 70 }, hovermode: 'x unified',
    }, PLOTLY_CONFIG);
}

function renderFactorChart(data, key) {
    const meta = STRATEGIES[key] || {color: '#6366f1'};
    const factors = data.exposures;
    const names = Object.keys(factors);
    const vals = Object.values(factors);
    const colors = vals.map(v => v >= 0 ? '#22c55e' : '#ef4444');

    const trace = {
        y: names, x: vals, type: 'bar', orientation: 'h',
        marker: {color: colors, line: { width: 0 }},
        hovertemplate: '<b>%{y}</b>: %{x:.2f}<extra></extra>'
    };

    Plotly.newPlot($('factor-chart'), [trace], {
        ...PLOTLY_THEME,
        title: { text: `Annualized Alpha: ${(data.alpha_annualized*100).toFixed(2)}% | R²: ${data.r_squared.toFixed(2)}`, font: { size: 13, color: '#94a3b8' }, y: 0.95 },
        xaxis: { ...PLOTLY_THEME.xaxis, title: { text: 'Factor Exposure (Beta)', font: { size: 12 } } },
        yaxis: { ...PLOTLY_THEME.yaxis, autorange: 'reversed' },
        margin: { t: 40, r: 30, b: 50, l: 80 },
    }, PLOTLY_CONFIG);
}

// ── Utilities ──────────────────────────────────────────────────
function generatePalette(baseColor, count) {
    const base = hexToHSL(baseColor);
    return Array.from({ length: count }, (_, i) => {
        const hue = (base.h + (i * 360 / count)) % 360;
        return `hsl(${hue}, ${Math.max(base.s - 10, 40)}%, ${Math.min(base.l + 10, 65)}%)`;
    });
}

function hexToHSL(hex) {
    let r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255;
    let max = Math.max(r, g, b), min = Math.min(r, g, b), h, s, l = (max + min) / 2;
    if (max === min) { h = s = 0; }
    else { let d = max - min; s = l > 0.5 ? d / (2 - max - min) : d / (max + min); switch (max) { case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break; case g: h = ((b - r) / d + 2) / 6; break; case b: h = ((r - g) / d + 4) / 6; break; } h *= 360; }
    return { h: Math.round(h), s: Math.round(s * 100), l: Math.round(l * 100) };
}

// ── Init ───────────────────────────────────────────────────────
renderPills();
updateSectorMappings();
