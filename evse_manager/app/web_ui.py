"""Cyberpunk-inspired visualization for the deterministic EVSE controller."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

FALLBACK_PAYLOAD = {
    "status": "idle",
    "mode": "auto",
    "auto_state_label": "Idle",
    "charger_status": "unknown",
    "current_amps": 0,
    "target_current": 0,
    "available_power": 0,
    "inverter_power": 0,
    "pv_power_w": 0,
    "battery_priority_soc": 95,
    "limiting_factors": [],
    "battery": {"soc": None, "power": None, "direction": "idle"},
    "energy_map": {
        "history": [],
        "evse_steps": [],
        "current_watts": 0,
        "target_watts": 0,
    },
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>EVSE Neural Grid</title>
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
    <link href=\"https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Space+Grotesk:wght@400;500;600&display=swap\" rel=\"stylesheet\">
    <script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js\"></script>
    <style>
        :root {
            --accent: #66fcf1;
            --accent-2: #ff00b8;
            --panel: rgba(8, 10, 32, 0.85);
            --stroke: rgba(102, 252, 241, 0.25);
            --text: #e6f7ff;
            --muted: #7f9fa8;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: 'Space Grotesk', 'Segoe UI', system-ui, sans-serif;
            background: radial-gradient(circle at 18% 18%, rgba(102,252,241,0.12), transparent 45%),
                        radial-gradient(circle at 82% 12%, rgba(255,0,184,0.18), transparent 50%),
                        #020210;
            color: var(--text);
        }
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background-image: linear-gradient(rgba(102,252,241,0.08) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(102,252,241,0.06) 1px, transparent 1px);
            background-size: 80px 80px;
            pointer-events: none;
            opacity: 0.4;
        }
        main {
            position: relative;
            z-index: 1;
            padding: 40px clamp(16px, 5vw, 72px) 80px;
        }
        header {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 32px;
        }
        .logo {
            font-family: 'Orbitron', sans-serif;
            letter-spacing: 0.28em;
            font-size: clamp(26px, 4vw, 46px);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo::before {
            content: '';
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: var(--accent);
            box-shadow: 0 0 16px var(--accent);
        }
        .status-chip {
            padding: 10px 18px;
            border-radius: 999px;
            border: 1px solid var(--stroke);
            background: rgba(4, 10, 30, 0.8);
            letter-spacing: 0.18em;
            font-size: 12px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 24px;
        }
        .card {
            background: var(--panel);
            border: 1px solid var(--stroke);
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 0 32px rgba(0,0,0,0.45);
            position: relative;
            overflow: hidden;
        }
        .card::after {
            content: '';
            position: absolute;
            inset: 1px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.05);
            pointer-events: none;
        }
        h2 {
            margin: 0 0 16px;
            font-family: 'Orbitron', sans-serif;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--muted);
        }
        .core-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
        }
        .metric-label { font-size: 11px; color: var(--muted); }
        .metric-value {
            font-size: 26px;
            font-family: 'Orbitron', sans-serif;
            margin-top: 4px;
            letter-spacing: 0.1em;
        }
        .bar-track {
            margin-top: 10px;
            height: 12px;
            border-radius: 999px;
            background: rgba(255,255,255,0.08);
            overflow: hidden;
        }
        .bar-fill {
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, var(--accent), var(--accent-2));
            width: 0%;
            transition: width 0.4s ease;
        }
        .timeline {
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-height: 240px;
            overflow-y: auto;
        }
        .timeline li {
            padding: 10px 14px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            background: rgba(255,255,255,0.02);
            display: flex;
            justify-content: space-between;
            gap: 12px;
            font-size: 13px;
        }
        .chip-row { display: flex; flex-wrap: wrap; gap: 10px; }
        .chip {
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.1);
            letter-spacing: 0.16em;
            font-size: 10px;
            text-transform: uppercase;
        }
        .chip.alert { border-color: #ff4d82; color: #ffb3cd; }
        canvas { width: 100% !important; height: 220px !important; }
        footer {
            margin-top: 32px;
            text-align: center;
            font-size: 12px;
            letter-spacing: 0.2em;
            color: rgba(230,247,255,0.6);
        }
    </style>
</head>
<body>
    <main>
        <header>
            <div class=\"logo\">EVSE NEURAL GRID</div>
            <div class=\"status-chip\" id=\"status-chip\">INITIALIZING</div>
        </header>
        <section class=\"grid\">
            <article class=\"card\">
                <h2>State Core</h2>
                <div class=\"core-stats\">
                    <div>
                        <div class=\"metric-label\">Mode</div>
                        <div class=\"metric-value\" id=\"mode-value\">AUTO</div>
                    </div>
                    <div>
                        <div class=\"metric-label\">State</div>
                        <div class=\"metric-value\" id=\"auto-state\">IDLE</div>
                    </div>
                    <div>
                        <div class=\"metric-label\">Status</div>
                        <div class=\"metric-value\" id=\"charger-status\">UNKNOWN</div>
                    </div>
                    <div>
                        <div class=\"metric-label\">Limiter</div>
                        <div class=\"metric-value\" id=\"limiter-label\">CLEAR</div>
                    </div>
                </div>
                <div style=\"margin-top:20px; display:grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap:14px;\">
                    <div>
                        <div class=\"metric-label\">Current</div>
                        <div class=\"metric-value\" id=\"current-amps\">0 A</div>
                        <div class=\"bar-track\"><div class=\"bar-fill\" id=\"current-bar\"></div></div>
                    </div>
                    <div>
                        <div class=\"metric-label\">Target</div>
                        <div class=\"metric-value\" id=\"target-amps\">0 A</div>
                        <div class=\"bar-track\"><div class=\"bar-fill\" id=\"target-bar\"></div></div>
                    </div>
                </div>
            </article>
            <article class=\"card\">
                <h2>Energy Streams</h2>
                <canvas id=\"energy-chart\"></canvas>
                <div class=\"chip-row\" style=\"margin-top:16px;\">
                    <span class=\"chip\" id=\"pv-chip\">PV -- W</span>
                    <span class=\"chip\" id=\"available-chip\">AVAILABLE -- W</span>
                    <span class=\"chip\" id=\"load-chip\">INVERTER -- W</span>
                </div>
            </article>
            <article class=\"card\">
                <h2>Timeline</h2>
                <ul class=\"timeline\" id=\"timeline\"></ul>
            </article>
            <article class=\"card\">
                <h2>Battery Stack</h2>
                <div class=\"core-stats\">
                    <div>
                        <div class=\"metric-label\">SOC</div>
                        <div class=\"metric-value\" id=\"battery-soc\">-- %</div>
                    </div>
                    <div>
                        <div class=\"metric-label\">Power</div>
                        <div class=\"metric-value\" id=\"battery-power\">-- W</div>
                    </div>
                    <div>
                        <div class=\"metric-label\">Flow</div>
                        <div class=\"metric-value\" id=\"battery-direction\">--</div>
                    </div>
                    <div>
                        <div class=\"metric-label\">Guard</div>
                        <div class=\"metric-value\" id=\"battery-guard\">-- %</div>
                    </div>
                </div>
                <div style=\"margin-top:18px;\">
                    <div class=\"metric-label\">Limiting Factors</div>
                    <div class=\"chip-row\" id=\"limit-chips\" style=\"margin-top:10px;\"></div>
                </div>
            </article>
        </section>
        <footer>deterministic solar control • neon rev 1</footer>
    </main>
    <script>
        const FALLBACK = {{ fallback_json | safe }};
        const ingressMatch = window.location.pathname.match(/^\/api\/hassio_ingress\/[A-Za-z0-9_-]+/);
        const basePath = ingressMatch ? ingressMatch[0] : '';
        const apiFetch = (path, options) => fetch(`${basePath}${path}`, options);
        let energyChart;

        function initChart() {
            const ctx = document.getElementById('energy-chart');
            if (!ctx) return;
            energyChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Available', data: [], borderColor: '#66fcf1', backgroundColor: 'rgba(102,252,241,0.15)', fill: true, tension: 0.35 },
                        { label: 'PV', data: [], borderColor: '#ff00b8', borderDash: [6,4], tension: 0.35 },
                        { label: 'Charging', data: [], borderColor: '#ffd369', tension: 0.35 }
                    ]
                },
                options: {
                    animation: false,
                    plugins: { legend: { labels: { color: 'rgba(230,247,255,0.8)' } } },
                    scales: {
                        x: { ticks: { color: 'rgba(230,247,255,0.6)' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        y: { ticks: { color: 'rgba(230,247,255,0.6)' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                    }
                }
            });
        }

        function fmt(value, suffix = '') {
            if (typeof value !== 'number' || Number.isNaN(value)) return `--${suffix}`;
            return `${Math.round(value)}${suffix}`;
        }

        function pct(value) {
            return Math.min(100, Math.max(0, value));
        }

        function updateBars(currentWatts, targetWatts, steps) {
            const max = steps?.length ? steps[steps.length - 1].watts : 6000;
            document.getElementById('current-bar').style.width = `${pct((currentWatts / (max || 1)) * 100)}%`;
            document.getElementById('target-bar').style.width = `${pct((targetWatts / (max || 1)) * 100)}%`;
        }

        function updateTimeline(history) {
            const list = document.getElementById('timeline');
            list.innerHTML = '';
            if (!history?.length) {
                list.innerHTML = '<li><span>No telemetry yet</span><span>--</span></li>';
                return;
            }
            history.slice(-8).reverse().forEach(sample => {
                const ts = sample.ts ? new Date(sample.ts) : null;
                const label = ts ? ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--';
                const payload = `Avail ${fmt(sample.available, 'W')} · Curr ${fmt(sample.current, 'W')} · Target ${fmt(sample.target, 'W')}`;
                const li = document.createElement('li');
                li.innerHTML = `<span>${label}</span><span>${payload}</span>`;
                list.appendChild(li);
            });
        }

        function updateChips(limiting, available, pv, inverter) {
            const chips = document.getElementById('limit-chips');
            chips.innerHTML = '';
            if (!limiting?.length) {
                chips.innerHTML = '<span class=\"chip\">Clear</span>';
            } else {
                limiting.forEach(item => {
                    const span = document.createElement('span');
                    span.className = 'chip alert';
                    span.textContent = item.replace(/_/g, ' ');
                    chips.appendChild(span);
                });
            }
            document.getElementById('pv-chip').textContent = `PV ${fmt(pv, ' W')}`;
            document.getElementById('available-chip').textContent = `Available ${fmt(available, ' W')}`;
            document.getElementById('load-chip').textContent = `Inverter ${fmt(inverter, ' W')}`;
            document.getElementById('limiter-label').textContent = limiting?.[0]?.replace(/_/g, ' ') || 'CLEAR';
        }

        function pumpChart(history, availablePower, pvPower, chargingPower) {
            if (!energyChart) return;
            const labels = history.map(sample => sample.ts || '');
            energyChart.data.labels = labels;
            energyChart.data.datasets[0].data = history.map(sample => sample.available ?? availablePower ?? null);
            energyChart.data.datasets[1].data = history.map(sample => sample.pv ?? pvPower ?? null);
            energyChart.data.datasets[2].data = history.map(sample => sample.current ?? chargingPower ?? null);
            energyChart.update('none');
        }

        function applyData(data) {
            document.getElementById('status-chip').textContent = (data.status || 'idle').toUpperCase();
            document.getElementById('mode-value').textContent = (data.mode || 'auto').toUpperCase();
            document.getElementById('auto-state').textContent = data.auto_state_label || '--';
            document.getElementById('charger-status').textContent = (data.charger_status || '--').toUpperCase();
            document.getElementById('current-amps').textContent = `${data.current_amps ?? 0} A`;
            document.getElementById('target-amps').textContent = `${data.target_current ?? 0} A`;

            const map = data.energy_map || {};
            updateBars(map.current_watts || 0, map.target_watts || 0, map.evse_steps || []);
            updateTimeline(map.history || []);
            updateChips(data.limiting_factors || [], data.available_power, data.pv_power_w || data.total_pv_power, data.inverter_power);
            pumpChart(map.history || [], data.available_power, data.pv_power_w || data.total_pv_power, data.charging_power);

            const battery = data.battery || {};
            document.getElementById('battery-soc').textContent = battery.soc != null ? `${battery.soc.toFixed(1)} %` : '-- %';
            document.getElementById('battery-power').textContent = battery.power != null ? `${Math.round(battery.power)} W` : '-- W';
            document.getElementById('battery-direction').textContent = (battery.direction || '--').toUpperCase();
            document.getElementById('battery-guard').textContent = `${data.battery_priority_soc ?? '--'} %`;
        }

        async function fetchStatus() {
            try {
                const response = await apiFetch('/api/status');
                if (!response.ok) throw new Error('bad status');
                applyData(await response.json());
            } catch (error) {
                console.error('Status fetch failed', error);
                applyData(FALLBACK);
            }
        }

        initChart();
        fetchStatus();
        setInterval(fetchStatus, 2000);
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    """Render the neon dashboard."""

    return render_template_string(HTML_TEMPLATE, fallback_json=json.dumps(FALLBACK_PAYLOAD))


def _fallback_payload():
    """Return a deep copy of the fallback payload so callers can mutate safely."""

    return deepcopy(FALLBACK_PAYLOAD)


def _load_ui_state_payload():
    """Load the persisted UI state, tolerating empty or partially-written files."""

    data_file = Path("/data/ui_state.json")
    if not data_file.exists():
        return _fallback_payload()
    try:
        raw = data_file.read_text(encoding="utf-8").strip()
    except OSError as exc:  # file temporarily unavailable, etc.
        app.logger.warning("Unable to read ui_state.json (%s); serving fallback", exc)
        return _fallback_payload()
    if not raw:
        app.logger.warning("ui_state.json empty; serving fallback")
        return _fallback_payload()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        app.logger.warning("ui_state.json invalid JSON (%s); serving fallback", exc)
        return _fallback_payload()


@app.route("/api/status")
def api_status():
    """Return the latest controller snapshot or a deterministic fallback."""

    return jsonify(_load_ui_state_payload())


def run_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    """Run the Flask development server (used outside Gunicorn)."""

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_server()
