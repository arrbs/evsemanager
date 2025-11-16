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
    <title>EVSE LCARS Console</title>
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
    <link href=\"https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600&family=Space+Grotesk:wght@400;500&display=swap\" rel=\"stylesheet\">
    <script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js\"></script>
    <style>
        :root {
            --lcars-bg: #050408;
            --lcars-panel: #0f0c1a;
            --lcars-dark: #120d1f;
            --lcars-amber: #f7a21c;
            --lcars-pink: #f04c7c;
            --lcars-cyan: #5de0ec;
            --lcars-violet: #b48bff;
            --lcars-muted: #8f8ba5;
            --lcars-text: #f4f2ff;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: 'Rajdhani', 'Space Grotesk', 'Segoe UI', sans-serif;
            background: radial-gradient(circle at 20% 20%, rgba(244,162,28,0.12), transparent 55%),
                        radial-gradient(circle at 70% 0%, rgba(93,224,236,0.18), transparent 50%),
                        var(--lcars-bg);
            color: var(--lcars-text);
        }
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background-image: linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px),
                              linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px);
            background-size: 120px 120px;
            pointer-events: none;
        }
        main {
            padding: clamp(16px, 4vw, 48px);
        }
        .lcars-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            gap: 12px;
        }
        .lcars-title {
            font-size: clamp(28px, 5vw, 54px);
            letter-spacing: 0.32em;
            color: var(--lcars-amber);
        }
        .lcars-header::after {
            content: '';
            flex: 1;
            height: 6px;
            background: linear-gradient(90deg, var(--lcars-amber), var(--lcars-pink));
            border-radius: 999px;
            margin-left: 18px;
        }
        .status-badge {
            padding: 12px 20px;
            border-radius: 999px;
            background: var(--lcars-panel);
            border: 2px solid var(--lcars-pink);
            letter-spacing: 0.3em;
            font-size: 12px;
        }
        .mode-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 11px;
            letter-spacing: 0.3em;
            background: rgba(93,224,236,0.15);
            border: 1px solid rgba(93,224,236,0.5);
            color: var(--lcars-cyan);
            margin-bottom: 18px;
            text-transform: uppercase;
        }
        .mode-chip.probe {
            background: rgba(240,76,124,0.15);
            border-color: rgba(240,76,124,0.6);
            color: var(--lcars-pink);
        }
        .lcars-grid {
            display: grid;
            grid-template-columns: minmax(240px, 280px) minmax(320px, 1fr) minmax(260px, 320px);
            gap: 20px;
        }
        .lcars-stack, .lcars-bridge, .lcars-side {
            display: flex;
            flex-direction: column;
            gap: 18px;
        }
        .stack-segment {
            background: var(--lcars-panel);
            padding: 18px;
            border-radius: 32px 12px 12px 32px;
            border-left: 12px solid var(--lcars-amber);
            border-right: 2px solid rgba(255,255,255,0.08);
            min-height: 80px;
        }
        .segment-title {
            font-size: 11px;
            letter-spacing: 0.4em;
            text-transform: uppercase;
            color: var(--lcars-muted);
        }
        .segment-value {
            font-size: 28px;
            letter-spacing: 0.2em;
            margin-top: 6px;
        }
        .segment-subtext {
            font-size: 13px;
            color: var(--lcars-muted);
            min-height: 18px;
        }
        .segment-foot {
            margin-top: 10px;
        }
        .lcars-rail {
            display: flex;
            gap: 8px;
            flex-wrap: nowrap;
            overflow-x: auto;
            padding: 6px;
            background: var(--lcars-dark);
            border-radius: 32px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .rail-step {
            flex: 1;
            min-width: 80px;
            padding: 10px 12px;
            border-radius: 18px;
            text-align: center;
            background: rgba(255,255,255,0.04);
            border: 1px solid transparent;
            transition: transform 0.2s ease;
        }
        .rail-step.active {
            background: var(--lcars-amber);
            color: #130a05;
            border-color: rgba(0,0,0,0.2);
        }
        .rail-step.target {
        .auto-status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 10px;
        }
        .status-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 14px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.15);
            letter-spacing: 0.25em;
            font-size: 11px;
            text-transform: uppercase;
            background: rgba(255,255,255,0.05);
        }
        .status-chip.active {
            border-color: var(--lcars-amber);
            color: var(--lcars-amber);
        }
        .status-chip.alert {
            border-color: var(--lcars-pink);
            color: var(--lcars-pink);
        }
            border-color: var(--lcars-pink);
        }
        .rail-step small {
            display: block;
            letter-spacing: 0.2em;
            font-size: 11px;
            color: rgba(255,255,255,0.6);
        }
        .panel {
            background: var(--lcars-panel);
            border-radius: 28px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.08);
            position: relative;
            overflow: hidden;
        }
        .panel::after {
            content: '';
            position: absolute;
            inset: 6px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.05);
            pointer-events: none;
        }
        .panel-title {
            font-size: 12px;
            letter-spacing: 0.5em;
            text-transform: uppercase;
            margin-bottom: 12px;
            color: var(--lcars-muted);
        }
        .metric-board {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
        }
        .metric {
            background: rgba(255,255,255,0.02);
            border-radius: 16px;
            padding: 12px 14px;
            border: 1px solid rgba(255,255,255,0.04);
        }
        .metric span:first-child {
            font-size: 11px;
            letter-spacing: 0.3em;
            color: var(--lcars-muted);
        }
        .metric strong {
            display: block;
            font-size: clamp(16px, 2.8vw, 26px);
            margin-top: 6px;
            letter-spacing: 0.15em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .auto-help {
            margin-top: 12px;
            font-size: 13px;
            color: var(--lcars-muted);
            line-height: 1.4;
        }
        .timeline-list {
            list-style: none;
            margin: 0;
            padding: 0;
            max-height: 220px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .timeline-list li {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            background: rgba(0,0,0,0.18);
            border-radius: 14px;
            padding: 10px 12px;
            font-size: 13px;
        }
        .constraint-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .constraint {
            padding: 10px 14px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.07);
            background: rgba(255,255,255,0.03);
            letter-spacing: 0.2em;
            font-size: 11px;
            text-transform: uppercase;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .constraint.alert {
            border-color: var(--lcars-pink);
            color: var(--lcars-pink);
        }
        .battery-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }
        .battery-aura {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }
        .battery-beacon {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.2);
            box-shadow: 0 0 12px rgba(255,255,255,0.15);
            position: relative;
            transition: box-shadow 0.3s ease, background 0.3s ease, border-color 0.3s ease;
        }
        .battery-beacon::after {
            content: '';
            position: absolute;
            inset: 6px;
            border-radius: 50%;
            background: rgba(255,255,255,0.2);
        }
        .battery-beacon.charging {
            background: rgba(93,224,236,0.2);
            border-color: #5de0ec;
            box-shadow: 0 0 20px rgba(93,224,236,0.45);
        }
        .battery-beacon.discharging {
            background: rgba(240,76,124,0.18);
            border-color: var(--lcars-pink);
            box-shadow: 0 0 20px rgba(240,76,124,0.4);
        }
        .battery-beacon-label {
            display: flex;
            flex-direction: column;
        }
        .battery-beacon-label span {
            display: block;
            font-size: 9px;
            letter-spacing: 0.35em;
            color: var(--lcars-muted);
        }
        .battery-beacon-label strong {
            letter-spacing: 0.25em;
            font-size: 16px;
        }
        canvas { width: 100% !important; height: 220px !important; }
        @media (max-width: 1100px) {
            .lcars-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <main>
        <div class=\"lcars-header\">
            <div class=\"lcars-title\">EVSE LCARS</div>
            <div class=\"status-badge\" id=\"status-chip\">INITIALIZING</div>
        </div>
        <div class=\"lcars-grid\">
            <section class=\"lcars-stack\">
                <div class=\"stack-segment\">
                    <div class=\"segment-title\">MODE</div>
                    <div class=\"segment-value\">
                        <span id=\"mode-value\">AUTO</span>
                        <span class=\"mode-chip\" id=\"mode-region-chip\">MAIN</span>
                    </div>
                    <div class=\"segment-subtext\" id=\"mode-subtext\">Deterministic FSM</div>
                    <div class=\"segment-foot\">
                        <span class=\"mode-chip\" id=\"mode-state-chip\">IDLE</span>
                    </div>
                </div>
                <div class=\"stack-segment\">
                    <div class=\"segment-title\">STATE</div>
                    <div class=\"segment-value\" id=\"auto-state\">IDLE</div>
                    <div class=\"segment-subtext\" id=\"state-help\">Awaiting telemetry</div>
                </div>
                <div class=\"stack-segment\">
                    <div class=\"segment-title\">CHARGER</div>
                    <div class=\"segment-value\" id=\"charger-status\">UNKNOWN</div>
                    <div class=\"segment-subtext\" id=\"limiter-label\">CLEAR</div>
                </div>
                <div class=\"stack-segment\">
                    <div class=\"segment-title\">CURRENT / TARGET</div>
                    <div class=\"segment-value\"><span id=\"current-amps\">0 A</span> · <span id=\"target-amps\">0 A</span></div>
                    <div class=\"segment-subtext\" id=\"step-indicator\">EVSE STEP 0</div>
                </div>
            </section>
            <section class=\"lcars-bridge\">
                <div class=\"lcars-rail\" id=\"step-rail\"></div>
                <article class=\"panel\">
                    <div class=\"panel-title\">ENERGY SYNTHESIS</div>
                    <canvas id=\"energy-chart\"></canvas>
                    <div class=\"metric-board\" style=\"margin-top:14px;\">
                        <div class=\"metric\"><span>AVAILABLE</span><strong id=\"available-chip\">-- W</strong></div>
                        <div class=\"metric\"><span>PV ARRAY</span><strong id=\"pv-chip\">-- W</strong></div>
                        <div class=\"metric\"><span>INVERTER</span><strong id=\"load-chip\">-- W</strong></div>
                        <div class=\"metric\"><span>EV DRAW</span><strong id=\"ev-draw-chip\">-- W</strong></div>
                    </div>
                </article>
                <article class=\"panel\">
                    <div class=\"panel-title\">TEMPORAL TRACE</div>
                    <ul class=\"timeline-list\" id=\"timeline\"></ul>
                </article>
            </section>
            <section class=\"lcars-side\">
                <article class=\"panel\">
                    <div class=\"panel-title\">AUTO LOGIC</div>
                    <div class=\"auto-status-row\">
                        <span class=\"status-chip\" id=\"fsm-status-chip\">FSM | IDLE</span>
                        <span class=\"status-chip\" id=\"evse-status-chip\">EVSE | UNKNOWN</span>
                    </div>
                    <p class=\"auto-help\" id=\"auto-help\">State narrative will appear here.</p>
                </article>
                <article class=\"panel\">
                    <div class=\"panel-title\">CONSTRAINT STACK</div>
                    <div class=\"constraint-list\" id=\"constraint-chips\"></div>
                </article>
                <article class=\"panel\">
                    <div class=\"panel-title\">BATTERY + GUARD</div>
                    <div class=\"battery-aura\">
                        <div class=\"battery-beacon\" id=\"battery-beacon\"></div>
                        <div class=\"battery-beacon-label\">
                            <span>FLOW</span>
                            <strong id=\"battery-beacon-label\">IDLE</strong>
                        </div>
                    </div>
                    <div class="battery-grid">
                        <div class="metric"><span>SOC</span><strong id="battery-soc">-- %</strong></div>
                        <div class="metric"><span>POWER</span><strong id="battery-power">-- W</strong></div>
                        <div class="metric"><span>GUARD</span><strong id="battery-guard">-- %</strong></div>
                    </div>
                </article>
            </section>
        </div>
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
                        { label: 'Available', data: [], borderColor: '#f7a21c', backgroundColor: 'rgba(247,162,28,0.15)', fill: true, tension: 0.35 },
                        { label: 'PV', data: [], borderColor: '#5de0ec', borderDash: [8,4], tension: 0.35 },
                        { label: 'EV Draw', data: [], borderColor: '#f04c7c', tension: 0.35 }
                    ]
                },
                options: {
                    animation: false,
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { 
                            labels: { 
                                color: 'rgba(244,242,255,0.8)', 
                                font: { family: 'Rajdhani', size: 11 }
                            } 
                        } 
                    },
                    scales: {
                        x: {
                            display: false
                        },
                        y: { 
                            ticks: { 
                                color: 'rgba(244,242,255,0.6)',
                                font: { size: 10 }
                            }, 
                            grid: { color: 'rgba(255,255,255,0.05)' } 
                        }
                    }
                }
            });
        }

        function fmt(value, suffix = '') {
            if (typeof value !== 'number' || Number.isNaN(value)) return `--${suffix}`;
            return `${Math.round(value)}${suffix}`;
        }

        function findStepIndex(steps, amps) {
            if (!steps?.length || amps == null) return -1;
            const rounded = Math.round(amps);
            return steps.findIndex(step => Math.round(step.amps) === rounded);
        }

        function renderRail(steps, currentAmps, targetAmps) {
            const rail = document.getElementById('step-rail');
            rail.innerHTML = '';
            if (!steps?.length) {
                rail.innerHTML = '<div class="rail-step">NO STEPS</div>';
                return;
            }
            const currentIndex = findStepIndex(steps, currentAmps);
            const targetIndex = findStepIndex(steps, targetAmps);
            steps.forEach((step, index) => {
                const div = document.createElement('div');
                div.className = 'rail-step';
                if (index === currentIndex) div.classList.add('active');
                if (index === targetIndex && index !== currentIndex) div.classList.add('target');
                div.innerHTML = `<small>${index}</small>${step.amps}A`;
                rail.appendChild(div);
            });
            const indicator = document.getElementById('step-indicator');
            indicator.textContent = currentIndex >= 0 ? `STEP ${currentIndex}` : 'STEP ?';
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
                const payload = `Avail ${fmt(sample.available, 'W')} / Curr ${fmt(sample.current, 'W')} / Target ${fmt(sample.target, 'W')}`;
                const li = document.createElement('li');
                li.innerHTML = `<span>${label}</span><span>${payload}</span>`;
                list.appendChild(li);
            });
        }

        function updateConstraints(limiting) {
            const host = document.getElementById('constraint-chips');
            host.innerHTML = '';
            if (!limiting?.length) {
                const span = document.createElement('div');
                span.className = 'constraint';
                span.textContent = 'CLEAR CHANNEL';
                host.appendChild(span);
                return;
            }
            limiting.forEach(item => {
                const span = document.createElement('div');
                span.className = 'constraint alert';
                span.textContent = item.replace(/_/g, ' ');
                host.appendChild(span);
            });
        }

        function pumpChart(history, availablePower, pvPower, chargingPower) {
            if (!energyChart) return;
            // Use empty strings as labels since x-axis is hidden
            const labels = history.map(() => '');
            energyChart.data.labels = labels;
            energyChart.data.datasets[0].data = history.map(sample => sample.available ?? availablePower ?? null);
            energyChart.data.datasets[1].data = history.map(sample => sample.pv ?? pvPower ?? null);
            energyChart.data.datasets[2].data = history.map(sample => sample.current ?? chargingPower ?? null);
            energyChart.update('none');
        }

        function updateMetrics(data) {
            document.getElementById('status-chip').textContent = (data.status || 'idle').toUpperCase();
            document.getElementById('mode-value').textContent = (data.mode || 'auto').toUpperCase();
            document.getElementById('auto-state').textContent = data.auto_state_label || '--';
            document.getElementById('state-help').textContent = data.auto_state_help || 'Awaiting telemetry';
            document.getElementById('charger-status').textContent = (data.charger_status || '--').toUpperCase();
            document.getElementById('limiter-label').textContent = (data.limiting_factors?.[0] || 'Clear channel').replace(/_/g, ' ');
            document.getElementById('current-amps').textContent = `${data.current_amps ?? 0} A`;
            document.getElementById('target-amps').textContent = `${data.target_current ?? 0} A`;
            document.getElementById('auto-help').textContent = data.auto_state_help || 'No guidance available.';
            updateModeChips(data);
            updateStatusChips(data);
        }

        function updateModeChips(data) {
            const regionChip = document.getElementById('mode-region-chip');
            const modeStateChip = document.getElementById('mode-state-chip');
            const modeSubtext = document.getElementById('mode-subtext');
            if (regionChip) {
                const region = (data.region || 'main').toUpperCase();
                regionChip.textContent = region;
                regionChip.classList.toggle('probe', region === 'PROBE');
            }
            if (modeStateChip) {
                const state = (data.mode_state || '--').replace(/_/g, ' ').toUpperCase();
                modeStateChip.textContent = state;
            }
            if (modeSubtext) {
                modeSubtext.textContent = data.mode_state ? data.mode_state.replace(/_/g, ' ').toUpperCase() : 'DETERMINISTIC FSM';
            }
        }

        function updateStatusChips(data) {
            const fsmChip = document.getElementById('fsm-status-chip');
            if (fsmChip) {
                fsmChip.textContent = `FSM | ${(data.auto_state_label || '--').toUpperCase()}`;
                fsmChip.classList.remove('active', 'alert');
                if ((data.auto_state || '').includes('charging')) {
                    fsmChip.classList.add('active');
                }
            }
            const evseChip = document.getElementById('evse-status-chip');
            if (evseChip) {
                const evseState = (data.charger_status || 'unknown').toUpperCase();
                evseChip.textContent = `EVSE | ${evseState}`;
                evseChip.classList.remove('active', 'alert');
                const normalized = evseState.toLowerCase();
                if (/(ready|charging|active)/.test(normalized)) {
                    evseChip.classList.add('active');
                }
                if (/(fault|error|unavailable)/.test(normalized)) {
                    evseChip.classList.add('alert');
                }
            }
        }

        function updateEnergyChips(data) {
            document.getElementById('available-chip').textContent = fmt(data.available_power, ' W');
            const pv = data.pv_power_w ?? data.total_pv_power;
            document.getElementById('pv-chip').textContent = fmt(pv, ' W');
            document.getElementById('load-chip').textContent = fmt(data.inverter_power, ' W');
            document.getElementById('ev-draw-chip').textContent = fmt(data.charging_power, ' W');
        }

        function updateBattery(data) {
            const battery = data.battery || {};
            const beacon = document.getElementById('battery-beacon');
            const beaconLabel = document.getElementById('battery-beacon-label');
            const direction = (battery.direction || 'idle').toLowerCase();
            if (beacon) {
                beacon.classList.remove('charging', 'discharging');
                if (direction === 'charging') {
                    beacon.classList.add('charging');
                } else if (direction === 'discharging') {
                    beacon.classList.add('discharging');
                }
            }
            if (beaconLabel) {
                const label = direction === 'charging' ? 'IN' : direction === 'discharging' ? 'OUT' : 'IDLE';
                beaconLabel.textContent = label;
            }
            document.getElementById('battery-soc').textContent = battery.soc != null ? `${battery.soc.toFixed(1)} %` : '-- %';
            document.getElementById('battery-power').textContent = battery.power != null ? `${Math.round(battery.power)} W` : '-- W';
            document.getElementById('battery-guard').textContent = `${data.battery_priority_soc ?? '--'} %`;
        }

        function applyData(data) {
            updateMetrics(data);
            updateConstraints(data.limiting_factors || []);
            updateBattery(data);
            updateEnergyChips(data);

            const map = data.energy_map || {};
            renderRail(map.evse_steps || [], data.current_amps, data.target_current);
            updateTimeline(map.history || []);
            pumpChart(map.history || [], data.available_power, data.pv_power_w || data.total_pv_power, data.charging_power);
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
