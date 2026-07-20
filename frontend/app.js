// Allow pointing this static frontend at a different backend without a rebuild:
// open index.html?api=http://localhost:8124 once and it's remembered.
(function () {
    const params = new URLSearchParams(location.search);
    if (params.has('api')) localStorage.setItem('api_base', params.get('api'));
})();
const API_BASE = localStorage.getItem('api_base') || '';

const TIMEFRAMES = ['15m', '1h', '4h', '1d', '1w'];
const TF_LABELS = { '15m': '15 דק', '1h': 'שעה', '4h': '4 שעות', '1d': 'יומי', '1w': 'שבועי' };

let symbols = [];
let currentSymbol = null;
let currentTf = '1h';
let mainChart = null, mainSeries = null;
let miniCharts = {};
let seasonBucket = 'month';

async function api(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`${path} -> ${res.status}`);
    return res.json();
}

function fmtPrice(v) {
    if (v == null) return '—';
    return v >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 2 }) : v.toFixed(4);
}

function impactClass(v) {
    return ['bullish', 'bearish', 'neutral'].includes(v) ? v : 'neutral';
}

function impactLabel(v) {
    return { bullish: 'עולה', bearish: 'יורד', neutral: 'ניטרלי' }[v] || v;
}

// ---- Symbol tabs ----------------------------------------------------------

async function initSymbols() {
    symbols = await api('/api/symbols');
    const tabsEl = document.getElementById('symbol-tabs');
    tabsEl.innerHTML = '';
    symbols.forEach((s, i) => {
        const btn = document.createElement('button');
        btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
        btn.textContent = s.label;
        btn.onclick = () => selectSymbol(s.symbol);
        btn.dataset.symbol = s.symbol;
        tabsEl.appendChild(btn);
    });
    currentSymbol = symbols[0].symbol;
}

function selectSymbol(symbol) {
    currentSymbol = symbol;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.symbol === symbol));
    refreshAll();
}

// ---- Timeframe selector ----------------------------------------------------

function initTfSelector() {
    const el = document.getElementById('tf-selector');
    el.innerHTML = '';
    TIMEFRAMES.forEach(tf => {
        const btn = document.createElement('button');
        btn.className = 'tf-btn' + (tf === currentTf ? ' active' : '');
        btn.textContent = TF_LABELS[tf];
        btn.dataset.tf = tf;
        btn.onclick = () => {
            currentTf = tf;
            document.querySelectorAll('.tf-btn').forEach(b => b.classList.toggle('active', b.dataset.tf === tf));
            loadMainChart();
            loadZones();
        };
        el.appendChild(btn);
    });
}

// ---- Charts ----------------------------------------------------------------

function candlesToSeries(rows) {
    return rows.map(r => ({ time: r.ts, open: r.open, high: r.high, low: r.low, close: r.close }));
}

function makeChart(container, height) {
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height,
        layout: { background: { color: 'transparent' }, textColor: '#8892b0' },
        grid: { vertLines: { color: 'rgba(255,255,255,.04)' }, horzLines: { color: 'rgba(255,255,255,.04)' } },
        rightPriceScale: { borderColor: '#23234a' },
        timeScale: { borderColor: '#23234a', timeVisible: true },
    });
    const series = chart.addCandlestickSeries({
        upColor: '#2ecc71', downColor: '#ff4d5e', borderVisible: false,
        wickUpColor: '#2ecc71', wickDownColor: '#ff4d5e',
    });
    return { chart, series };
}

async function loadMainChart() {
    const container = document.getElementById('main-chart');
    if (!mainChart) {
        const created = makeChart(container, container.clientHeight || 420);
        mainChart = created.chart;
        mainSeries = created.series;
        new ResizeObserver(() => {
            mainChart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
        }).observe(container);
    }
    try {
        const rows = await api(`/api/candles/${currentSymbol}/${currentTf}?limit=500`);
        mainSeries.setData(candlesToSeries(rows));
        mainChart.timeScale().fitContent();
        if (rows.length) {
            document.getElementById('current-price').textContent = fmtPrice(rows[rows.length - 1].close);
            const label = symbols.find(s => s.symbol === currentSymbol)?.label || '';
            document.getElementById('current-symbol-label').textContent = label;
        } else {
            document.getElementById('current-price').textContent = '—';
        }
    } catch (e) {
        console.error('loadMainChart', e);
    }
}

async function loadMiniGrid() {
    const grid = document.getElementById('mini-grid');
    grid.innerHTML = '';
    miniCharts = {};
    for (const tf of TIMEFRAMES) {
        if (tf === currentTf) continue;
        const wrap = document.createElement('div');
        wrap.className = 'mini-chart-wrap';
        wrap.innerHTML = `<div class="label">${TF_LABELS[tf]}</div><div class="mini-chart"></div>`;
        grid.appendChild(wrap);
        const container = wrap.querySelector('.mini-chart');
        const { chart, series } = makeChart(container, 110);
        new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth })).observe(container);
        miniCharts[tf] = { chart, series, container };
        try {
            const rows = await api(`/api/candles/${currentSymbol}/${tf}?limit=150`);
            series.setData(candlesToSeries(rows));
            chart.timeScale().fitContent();
        } catch (e) { /* symbol/timeframe may not have data yet */ }
    }
}

async function loadZones() {
    const el = document.getElementById('zones-list');
    try {
        const zones = await api(`/api/zones/${currentSymbol}/${currentTf}`);
        if (mainSeries) {
            (mainSeries._priceLines || []).forEach(pl => mainSeries.removePriceLine(pl));
            mainSeries._priceLines = [];
        }
        if (!zones.length) {
            el.innerHTML = '<div class="empty-state">אין עדיין מספיק נתונים לזיהוי איזורים בטווח זמן זה</div>';
            return;
        }
        el.innerHTML = '';
        zones.slice(0, 8).forEach(z => {
            const row = document.createElement('div');
            row.className = `zone-row ${z.kind}`;
            row.innerHTML = `<span>${z.kind === 'resistance' ? '🔴 התנגדות' : '🟢 תמיכה'} — ${fmtPrice(z.level)}</span>
                              <span class="zone-strength">${z.touches} מגעים</span>`;
            el.appendChild(row);
            if (mainSeries) {
                const line = mainSeries.createPriceLine({
                    price: z.level,
                    color: z.kind === 'resistance' ? '#ff4d5e' : '#2ecc71',
                    lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
                });
                mainSeries._priceLines = mainSeries._priceLines || [];
                mainSeries._priceLines.push(line);
            }
        });
    } catch (e) {
        el.innerHTML = '<div class="empty-state">שגיאה בטעינת איזורים</div>';
    }
}

// ---- Institutional panel ---------------------------------------------------

async function loadInstitutional() {
    const el = document.getElementById('institutional-panel');
    try {
        const data = await api(`/api/institutional/${currentSymbol}`);
        if (!data || !data.narrative) {
            el.innerHTML = '<div class="empty-state">הניתוח המוסדי עדיין לא זמין — יתעדכן בסבב הקרוב</div>';
            return;
        }
        el.innerHTML = `
            <div class="inst-bias">💼 ${data.cot_bias || ''}</div>
            <div class="inst-structure">📐 ${data.smc_structure || ''}</div>
            <div class="inst-narrative">${data.narrative}</div>
            <div class="inst-updated">עודכן: ${data.updated_at || ''}</div>
        `;
    } catch (e) {
        el.innerHTML = '<div class="empty-state">שגיאה בטעינה</div>';
    }
}

// ---- Seasonality ------------------------------------------------------------

function initSeasonTabs() {
    const el = document.getElementById('season-tabs');
    el.innerHTML = '';
    [['month', 'לפי חודש'], ['weekday', 'לפי יום בשבוע']].forEach(([key, label]) => {
        const btn = document.createElement('button');
        btn.className = 'tf-btn' + (key === seasonBucket ? ' active' : '');
        btn.textContent = label;
        btn.onclick = () => {
            seasonBucket = key;
            document.querySelectorAll('#season-tabs .tf-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadSeasonality();
        };
        el.appendChild(btn);
    });
}

async function loadSeasonality() {
    const el = document.getElementById('season-bars');
    try {
        const rows = await api(`/api/seasonality/${currentSymbol}/${seasonBucket}`);
        if (!rows.length) {
            el.innerHTML = '<div class="empty-state">אין עדיין מספיק היסטוריה לניתוח עונתיות</div>';
            return;
        }
        const maxAbs = Math.max(...rows.map(r => Math.abs(r.avg_return))) || 1;
        el.innerHTML = '';
        rows.forEach(r => {
            const pct = (r.avg_return * 100).toFixed(2);
            const widthPct = Math.min(50, (Math.abs(r.avg_return) / maxAbs) * 50);
            const row = document.createElement('div');
            row.className = 'season-row';
            row.innerHTML = `
                <span>${r.bucket_value}</span>
                <div class="season-track">
                    <div class="season-mid"></div>
                    <div class="season-fill ${r.avg_return >= 0 ? 'pos' : 'neg'}" style="width:${widthPct}%"></div>
                </div>
                <span style="color:${r.avg_return >= 0 ? 'var(--green)' : 'var(--red)'}">${pct}%</span>
            `;
            el.appendChild(row);
        });
    } catch (e) {
        el.innerHTML = '<div class="empty-state">שגיאה בטעינה</div>';
    }
}

// ---- News feed (SSE + initial load) ----------------------------------------

function renderNewsItem(item) {
    const div = document.createElement('div');
    div.className = `news-item ${item.urgency || 'low'}`;
    div.innerHTML = `
        <div class="news-headline">${item.headline || item.title}</div>
        <div>${item.analysis || ''}</div>
        <div class="news-meta">
            <span class="impact-tag ${impactClass(item.gold_impact)}">זהב: ${impactLabel(item.gold_impact)}</span>
            <span class="impact-tag ${impactClass(item.silver_impact)}">כסף: ${impactLabel(item.silver_impact)}</span>
            <span class="impact-tag ${impactClass(item.bitcoin_impact)}">ביטקוין: ${impactLabel(item.bitcoin_impact)}</span>
            <span>${item.source || ''}</span>
        </div>
    `;
    return div;
}

async function loadInitialNews() {
    const el = document.getElementById('news-feed');
    try {
        const rows = await api('/api/news?limit=30');
        if (!rows.length) {
            el.innerHTML = '<div class="empty-state">אין עדיין חדשות — הסוכן סורק כל כמה דקות</div>';
            return;
        }
        el.innerHTML = '';
        rows.forEach(item => el.appendChild(renderNewsItem(item)));
    } catch (e) {
        el.innerHTML = '<div class="empty-state">שגיאה בטעינת חדשות</div>';
    }
}

function connectNewsStream() {
    const es = new EventSource(`${API_BASE}/stream/news`);
    es.onmessage = (event) => {
        const item = JSON.parse(event.data);
        const el = document.getElementById('news-feed');
        if (el.querySelector('.empty-state')) el.innerHTML = '';
        el.prepend(renderNewsItem(item));
    };
    es.onerror = () => { /* browser auto-reconnects EventSource */ };
}

// ---- Orchestration ----------------------------------------------------------

async function refreshAll() {
    await loadMainChart();
    await loadMiniGrid();
    await loadZones();
    await loadInstitutional();
    await loadSeasonality();
}

function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js').catch((e) => console.warn('SW registration failed', e));
    }
}

async function main() {
    registerServiceWorker();
    await initSymbols();
    initTfSelector();
    initSeasonTabs();
    await refreshAll();
    await loadInitialNews();
    connectNewsStream();
    setInterval(refreshAll, 60_000);
}

main();
