"""
Web UI for EVSE Manager
Provides Ingress-enabled web interface for monitoring and control.
"""
import logging
import os
import json
from flask import Flask, render_template_string, jsonify, request
from pathlib import Path


app = Flask(__name__)
logger = logging.getLogger(__name__)


# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EVSE Manager</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
        }
        .header-tagline { color:#777; font-size:13px; }
        body.mode-auto .header {
            box-shadow: 0 4px 25px rgba(76, 175, 80, 0.35);
            border: 2px solid rgba(76, 175, 80, 0.4);
        }
        h1 { color: #333; margin-bottom: 6px; }
        .header-meta {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
        }
        .status-active { background: #4caf50; color: white; }
        .status-idle { background: #999; color: white; }
        .status-fault { background: #f44336; color: white; }
        .mode-chip {
            padding: 6px 16px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            box-shadow: 0 4px 14px rgba(0,0,0,0.08);
        }
        .mode-chip.auto { background: linear-gradient(135deg, #4caf50, #2e7d32); color: white; }
        .mode-chip.manual { background: #e0e0e0; color: #424242; }
        .state-chip {
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: none;
            background: #eef2ff;
            color: #3f51b5;
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            display: none;
        }
        .state-chip.charging { background: #e6f4ea; color: #1b5e20; }
        .state-chip.waiting_for_solar { background: #fff6e0; color: #d48806; }
        .state-chip.waiting_for_battery { background: #f3e5f5; color: #6a1b9a; }
        .state-chip.manual_priority { background: #ffe0e0; color: #c62828; }
        .state-chip.waiting_for_vehicle { background: #e0f2ff; color: #0277bd; }
        .state-chip.vehicle_waiting { background: #fff3cd; color: #a66f00; }
        .state-chip.blocked_charger { background: #fdecea; color: #c62828; }
        .state-chip.vehicle_full { background: #ede7f6; color: #4527a0; }
        .state-chip.ready { background: #e8f5e9; color: #2e7d32; }
        .state-chip.idle { background: #f5f5f5; color: #666; }
        .state-chip.inverter_limit { background: #fdecea; color: #c62828; }
        .hero-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .hero-card {
            padding: 24px;
            border-radius: 16px;
            background: white;
            box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        }
        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
        }
        .hero-title { font-size: 16px; text-transform: uppercase; letter-spacing: 0.1em; color: #777; }
        .hero-status { font-size: 28px; font-weight: 700; color: #222; margin-top: 6px; }
        .hero-pills { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
        .hero-metrics {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        .hero-metric {
            flex: 1;
            min-width: 180px;
            background: #f7f8fa;
            border-radius: 12px;
            padding: 16px;
        }
        .hero-value {
            font-size: 32px;
            font-weight: 700;
            color: #111;
            display: flex;
            align-items: baseline;
            gap: 6px;
        }
        
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
        }
        .metric-grid.three { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
        .card-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .battery-priority-pill {
            padding: 6px 12px;
            border-radius: 999px;
            background: #ede7f6;
            color: #4527a0;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .controls-card { padding: 24px; }
        .control-body { display: flex; flex-direction: column; gap: 18px; margin-top: 16px; }
        .action-row { display: flex; gap: 12px; flex-wrap: wrap; }
        .alert-banner {
            display: none;
            margin-top: 16px;
            padding: 14px 16px;
            border-radius: 10px;
            background: #fff4e5;
            color: #a66300;
            font-weight: 600;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: box-shadow 0.3s ease, border-color 0.3s ease;
        }
        .card h2 { color: #333; font-size: 18px; margin-bottom: 15px; }
        .card-warning {
            border: 2px solid #ff9800;
            box-shadow: 0 4px 20px rgba(255,152,0,0.3);
        }
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        .metric.metric-explained { align-items: flex-start; }
        .metric.metric-explained .metric-value { margin-left: auto; }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #666; font-size: 14px; }
        .metric-value { color: #333; font-size: 20px; font-weight: 600; }
        .metric-unit { color: #999; font-size: 14px; margin-left: 4px; }
        
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            position: relative;
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .btn-primary { background: #2196f3; color: white; }
        .btn-primary:hover:not(:disabled) { background: #1976d2; }
        .btn-success { background: #4caf50; color: white; }
        .btn-success:hover:not(:disabled) { background: #388e3c; }
        .btn-danger { background: #f44336; color: white; }
        .btn-danger:hover:not(:disabled) { background: #d32f2f; }
        .btn-secondary { background: #999; color: white; }
        .btn-secondary:hover:not(:disabled) { background: #777; }
        
        select {
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            min-width: 120px;
        }
        
        .session-list {
            max-height: 400px;
            overflow-y: auto;
        }
        .session-item {
            padding: 12px;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }
        .session-item:last-child { border-bottom: none; }
        .session-id { color: #2196f3; font-weight: 600; }
        .session-stats { color: #666; margin-top: 4px; }
        
        .loading { text-align: center; padding: 40px; color: #999; }
        .toast {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 999;
            min-width: 220px;
            max-width: 320px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }
        .error { background: #ffebee; color: #c62828; padding: 15px; border-radius: 8px; }
        .success { background: #e8f5e9; color: #2e7d32; padding: 15px; border-radius: 8px; }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            50% { box-shadow: 0 4px 20px rgba(255,152,0,0.4); }
        }
        .pill-toggle {
            display: inline-flex;
            border: 1px solid #ddd;
            border-radius: 999px;
            overflow: hidden;
            background: white;
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.06);
        }
        .pill-toggle button {
            border: none;
            background: transparent;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            cursor: pointer;
            color: #777;
            transition: background 0.2s, color 0.2s;
        }
        .pill-toggle button.active {
            background: #222;
            color: white;
        }
        .pill-toggle button:not(.active):hover {
            background: rgba(0,0,0,0.05);
            color: #333;
        }
        .flag-control {
            display: inline-flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 8px 14px;
            border: 1px solid #eee;
            border-radius: 999px;
            background: #f8f8f8;
            min-width: auto;
            flex: 0 0 auto;
        }
        .threshold-control {
            flex-wrap: wrap;
            border-radius: 16px;
            gap: 16px;
        }
        .flag-text { display: flex; flex-direction: column; }
        .flag-stack { display: flex; flex-direction: row; gap: 12px; width: auto; align-items: center; flex: 0 0 auto; }
        .flag-title { font-size: 14px; font-weight: 600; color: #333; }
        .flag-subtitle { font-size: 11px; color: #777; margin-top: 2px; max-width: 220px; }
        .threshold-inputs {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .threshold-inputs input[type="number"] {
            width: 80px;
            padding: 8px 10px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
        }
        .threshold-inputs .threshold-unit {
            font-size: 14px;
            font-weight: 600;
            color: #555;
        }
        .metric-subtext { display: block; font-size: 12px; color: #888; margin-top: 4px; max-width: 220px; }
        .chip-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
        .chip {
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            background: #eee;
            color: #555;
        }
        .chip-warning { background: #fff3cd; color: #856404; }
        .chip-danger { background: #fdecea; color: #c62828; }
        .status-note {
            margin-top: 14px;
            padding: 14px 16px;
            border-radius: 10px;
            font-size: 13px;
            background: #f5f0ff;
            color: #4a2b8c;
            display: none;
        }
        .manual-only {
            display: none;
            flex-direction: column;
            gap: 6px;
        }
        .manual-label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #777; }
        .manual-only select { width: 100%; }
        body.mode-manual .manual-only { display: flex; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>⚡ EVSE Manager</h1>
                <div class="header-tagline">Smart solar charging controller</div>
            </div>
        </div>
        
        <div id="error-message" class="error toast" style="display: none;"></div>
        <div id="success-message" class="success toast" style="display: none;"></div>

        <div id="intention-panel" class="card" style="display: none; background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); color: white; margin-bottom: 20px; animation: pulse 2s ease-in-out infinite;">
            <h2 style="color: white; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 24px;">⏱️</span>
                <span>Grace Period Active</span>
            </h2>
            <div style="margin-top: 15px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 6px;">
                <div style="font-size: 18px; font-weight: 600; margin-bottom: 10px;">
                    Will stop charging in <span id="grace-countdown" style="font-size: 28px; font-weight: 700;">--</span>
                </div>
                <div style="font-size: 14px; opacity: 0.9;">
                    Reason: <span id="grace-reason">Insufficient solar power</span>
                </div>
                <div style="margin-top: 10px; height: 8px; background: rgba(255,255,255,0.3); border-radius: 4px; overflow: hidden;">
                    <div id="grace-progress" style="height: 100%; background: white; transition: width 1s linear;"></div>
                </div>
            </div>
        </div>
        
        <div id="learning-banner" class="card" style="display: none; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; margin-bottom: 20px;">
            <h2 style="color: white;">🎓 Adaptive Learning Active</h2>
            <div class="metric" style="border-bottom-color: rgba(255,255,255,0.2);">
                <span class="metric-label" style="color: rgba(255,255,255,0.9);">Progress</span>
                <span class="metric-value" style="color: white;">
                    <span id="learning-progress">0</span> / <span id="learning-total">20</span>
                    <span class="metric-unit">sessions</span>
                </span>
            </div>
            <div class="metric" style="border-bottom: none;">
                <span class="metric-label" style="color: rgba(255,255,255,0.9);">Current Best Score</span>
                <span class="metric-value" style="color: white;" id="learning-best-score">-</span>
            </div>
            <div style="margin-top: 10px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 6px; font-size: 14px;">
                <strong>Testing:</strong> <span id="learning-current-params">-</span>
            </div>
        </div>
        
        <div id="learning-complete" class="card" style="display: none; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; margin-bottom: 20px;">
            <h2 style="color: white;">✅ Learning Complete!</h2>
            <div style="margin-top: 10px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 6px;">
                <div style="font-size: 16px; font-weight: 600; margin-bottom: 10px;">Optimal Settings Found:</div>
                <div id="optimal-settings" style="font-size: 14px; line-height: 1.8;"></div>
            </div>
        </div>
        
        <div class="hero-grid">
            <div class="card hero-card">
                <div class="hero-top">
                    <div>
                        <div class="hero-title">Live Session</div>
                        <div class="hero-status" id="charger-status">-</div>
                    </div>
                    <div class="hero-pills">
                        <span class="mode-chip manual" id="mode-chip">MODE</span>
                        <span class="state-chip" id="auto-state-chip"></span>
                        <span class="status-badge" id="status-badge">Loading...</span>
                    </div>
                </div>
                <div class="hero-metrics">
                    <div class="hero-metric">
                        <div class="metric-label">Current</div>
                        <div class="hero-value">
                            <span id="current-amps">-</span>
                            <span class="metric-unit">A</span>
                        </div>
                        <div class="metric-subtext">Target <span id="target-current-hero">-</span>A</div>
                    </div>
                    <div class="hero-metric">
                        <div class="metric-label">Charging Power</div>
                        <div class="hero-value">
                            <span id="charging-power">-</span>
                            <span class="metric-unit">W</span>
                        </div>
                        <div class="metric-subtext">Mode <span id="mode">-</span></div>
                    </div>
                    <div class="hero-metric">
                        <div class="metric-label">Session Energy</div>
                        <div class="hero-value">
                            <span id="session-energy">-</span>
                            <span class="metric-unit">kWh</span>
                        </div>
                        <div class="metric-subtext">Duration <span id="session-duration">-</span> • Solar <span id="session-solar">-</span>%</div>
                    </div>
                </div>
            </div>
            <div class="card battery-card" id="battery-card">
                <div class="card-heading">
                    <h2>House Battery</h2>
                    <span class="battery-priority-pill" id="battery-priority">-</span>
                </div>
                <div class="metric-grid">
                    <div>
                        <div class="metric-label">State of Charge</div>
                        <div class="hero-value">
                            <span id="battery-soc">-</span>
                            <span class="metric-unit">%</span>
                        </div>
                    </div>
                    <div>
                        <div class="metric-label">Flow</div>
                        <div class="hero-value">
                            <span id="battery-power">-</span>
                            <span class="metric-unit">W</span>
                        </div>
                        <div class="metric-subtext" id="battery-direction">-</div>
                    </div>
                    <div>
                        <div class="metric-label">Guard</div>
                        <div class="hero-value"><span id="battery-guard-display">--%</span></div>
                        <div class="metric-subtext">Minimum SOC</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="dashboard-grid">
            <div class="card controls-card">
                <div class="card-heading">
                    <h2>Controls</h2>
                    <div class="pill-toggle">
                        <button id="mode-manual-btn" class="active" onclick="handleModeButton('manual')">Manual</button>
                        <button id="mode-auto-btn" onclick="handleModeButton('auto')">Auto</button>
                    </div>
                </div>
                <div class="control-body">
                    <div class="manual-only" id="manual-controls">
                        <span class="manual-label">Manual current</span>
                        <select id="manual-current" onchange="setManualCurrent(this.value)">
                            <option value="6">6A</option>
                            <option value="8">8A</option>
                            <option value="10">10A</option>
                            <option value="13">13A</option>
                            <option value="16">16A</option>
                            <option value="20">20A</option>
                            <option value="24">24A</option>
                        </select>
                    </div>
                    <div class="action-row">
                        <button class="btn-success" onclick="startCharging()">Start Charging</button>
                        <button class="btn-danger" onclick="stopCharging()">Stop Charging</button>
                    </div>
                    <div class="flag-control threshold-control" style="width:100%;">
                        <div class="flag-text">
                            <div class="flag-title">Battery Minimum SOC</div>
                            <div class="flag-subtitle">Auto mode pauses EV charging until the house battery reaches this SOC. Current guard: <span id="battery-priority-note">--%</span></div>
                        </div>
                        <div class="threshold-inputs">
                            <input type="number" id="battery-priority-input" min="0" max="100" step="1" value="80" oninput="handleBatteryPriorityInput(this.value)">
                            <span class="threshold-unit">%</span>
                            <button class="btn-secondary" id="battery-priority-save" data-independent="true" onclick="handleBatteryPrioritySave()">Save</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card" id="energy-card">
                <h2>Solar & Inverter</h2>
                <div class="metric-grid three">
                    <div>
                        <div class="metric-label">Available Solar</div>
                        <div class="hero-value">
                            <span id="available-power">-</span>
                            <span class="metric-unit">W</span>
                        </div>
                    </div>
                    <div>
                        <div class="metric-label">Target Current</div>
                        <div class="hero-value">
                            <span id="target-current">-</span>
                            <span class="metric-unit">A</span>
                        </div>
                        <div class="metric-subtext">Commanded amps</div>
                    </div>
                    <div>
                        <div class="metric-label">Inverter Output</div>
                        <div class="hero-value">
                            <span id="inverter-power">-</span>
                            <span class="metric-unit">W</span>
                        </div>
                    </div>
                </div>
                <div class="alert-banner" id="inverter-limit-banner">⚠️ Inverter limit reached</div>
            </div>

            <div class="card limits-card">
                <h2>System Intent</h2>
                <div class="chip-list" id="limiting-factors">
                    <span class="chip">No limits active</span>
                </div>
                <div class="status-note" id="status-note"></div>
            </div>

            <div class="card">
                <h2>Lifetime Stats</h2>
                <div class="metric">
                    <span class="metric-label">Total Sessions</span>
                    <span class="metric-value" id="total-sessions">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total Energy</span>
                    <span class="metric-value">
                        <span id="total-energy">-</span>
                        <span class="metric-unit">kWh</span>
                    </span>
                </div>
                <div class="metric metric-explained">
                    <div>
                        <span class="metric-label">Avg Solar %</span>
                        <span class="metric-subtext">Share of total EV energy supplied by solar.</span>
                    </div>
                    <span class="metric-value">
                        <span id="avg-solar">-</span>
                        <span class="metric-unit">%</span>
                    </span>
                </div>
            </div>

            <div class="card">
                <h2>Recent Sessions</h2>
                <div class="session-list" id="session-list">
                    <div class="loading">Loading sessions...</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const LIMITING_LABELS = {
            battery_priority: 'Battery Priority',
            inverter_limit: 'Inverter Limit',
            grace_period: 'Grace Period',
            insufficient_power: 'Insufficient Solar',
            car_unplugged: 'EV Not Plugged In',
            vehicle_waiting: 'Vehicle Waiting',
            charger_refused: 'Charger Refused',
            vehicle_charged: 'Vehicle Charged'
        };
        let currentMode = null;
        let pendingMode = null;
        let pendingModeTimestamp = 0;
        let currentBatteryPrioritySoc = null;
        let pendingBatteryPrioritySoc = null;
        let pendingBatterySocTimestamp = 0;
        const PENDING_TIMEOUT_MS = 6000;

        function pendingExpired(timestamp) {
            return (Date.now() - timestamp) > PENDING_TIMEOUT_MS;
        }

        function applyModeVisualState(mode) {
            if (!mode) {
                return;
            }
            currentMode = mode;
            document.body.classList.toggle('mode-auto', mode === 'auto');
            document.body.classList.toggle('mode-manual', mode !== 'auto');
            const modeChip = document.getElementById('mode-chip');
            if (modeChip) {
                modeChip.textContent = mode === 'auto' ? 'Auto' : 'Manual';
                modeChip.classList.toggle('auto', mode === 'auto');
                modeChip.classList.toggle('manual', mode !== 'auto');
            }
            const manualButton = document.getElementById('mode-manual-btn');
            const autoButton = document.getElementById('mode-auto-btn');
            if (manualButton && autoButton) {
                manualButton.classList.toggle('active', mode !== 'auto');
                autoButton.classList.toggle('active', mode === 'auto');
            }
        }

        function setModeButtonsDisabled(disabled) {
            document.querySelectorAll('.pill-toggle button').forEach(btn => { btn.disabled = disabled; });
        }

        function applyBatteryPrioritySoc(value) {
            if (typeof value !== 'number' || Number.isNaN(value)) {
                return;
            }
            currentBatteryPrioritySoc = value;
            const input = document.getElementById('battery-priority-input');
            if (input && document.activeElement !== input) {
                input.value = value;
            }
            const note = document.getElementById('battery-priority-note');
            if (note) {
                note.textContent = `${value}%`;
            }
            const guard = document.getElementById('battery-guard-display');
            if (guard) {
                guard.textContent = `${value}%`;
            }
        }

        function setBatterySocControlsDisabled(disabled) {
            const input = document.getElementById('battery-priority-input');
            const saveButton = document.getElementById('battery-priority-save');
            if (input) {
                input.disabled = disabled;
            }
            if (saveButton) {
                saveButton.disabled = disabled;
            }
        }

        function formatDuration(seconds) {
            if (!seconds) return '-';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
        }

        function formatNumber(value, digits = 1) {
            return typeof value === 'number' ? value.toFixed(digits) : '-';
        }
        
        function updateUI(data) {
            // Learning status
            if (data.learning_status && data.learning_status.enabled) {
                const learningBanner = document.getElementById('learning-banner');
                const learningComplete = document.getElementById('learning-complete');
                
                if (data.learning_status.learning_complete) {
                    learningBanner.style.display = 'none';
                    learningComplete.style.display = 'block';
                    
                    // Show optimal settings
                    const optimalDiv = document.getElementById('optimal-settings');
                    const settings = data.learning_status.optimal_settings || {};
                    optimalDiv.innerHTML = Object.entries(settings)
                        .map(([key, value]) => `<div>${key}: <strong>${value}</strong></div>`)
                        .join('');
                } else {
                    learningBanner.style.display = 'block';
                    learningComplete.style.display = 'none';
                    
                    document.getElementById('learning-progress').textContent = data.learning_status.sessions_completed;
                    document.getElementById('learning-total').textContent = data.learning_status.total_sessions;
                    document.getElementById('learning-best-score').textContent = 
                        data.learning_status.current_best_score?.toFixed(2) || '-';
                    
                    // Show current parameters being tested
                    const params = [];
                    if (data.learning_status.optimal_settings) {
                        params.push(`Hysteresis: ${data.learning_status.optimal_settings.hysteresis_watts}W`);
                    }
                    document.getElementById('learning-current-params').textContent = 
                        params.join(', ') || 'Gathering baseline data...';
                }
            } else {
                document.getElementById('learning-banner').style.display = 'none';
                document.getElementById('learning-complete').style.display = 'none';
            }
            
            // Status badge
            const badge = document.getElementById('status-badge');
            badge.textContent = data.status;
            badge.className = 'status-badge status-' + data.status;
            
            // Current status
            document.getElementById('mode').textContent = data.mode || '-';
            const allowModeUpdate = !pendingMode || pendingExpired(pendingModeTimestamp) || data.mode === pendingMode;
            if (allowModeUpdate) {
                applyModeVisualState(data.mode);
                if (pendingMode && data.mode === pendingMode) {
                    pendingMode = null;
                }
            }
            const manualSelect = document.getElementById('manual-current');
            if (manualSelect && data.manual_current) {
                manualSelect.value = String(data.manual_current);
            }
            const autoChip = document.getElementById('auto-state-chip');
            if (autoChip) {
                if (data.mode === 'auto' && data.auto_state_label) {
                    autoChip.style.display = 'inline-flex';
                    autoChip.textContent = data.auto_state_label;
                    autoChip.className = `state-chip ${data.auto_state || ''}`;
                    autoChip.title = data.auto_state_help || '';
                } else {
                    autoChip.style.display = 'none';
                    autoChip.textContent = '';
                    autoChip.title = '';
                }
            }
            const allowBatterySocUpdate = pendingBatteryPrioritySoc === null
                || pendingExpired(pendingBatterySocTimestamp)
                || data.battery_priority_soc === pendingBatteryPrioritySoc;
            if (allowBatterySocUpdate && typeof data.battery_priority_soc === 'number') {
                applyBatteryPrioritySoc(data.battery_priority_soc);
                if (pendingBatteryPrioritySoc !== null && data.battery_priority_soc === pendingBatteryPrioritySoc) {
                    pendingBatteryPrioritySoc = null;
                }
            }
            document.getElementById('charger-status').textContent = data.charger_status || '-';
            document.getElementById('current-amps').textContent = data.current_amps?.toFixed(1) || '-';
            document.getElementById('charging-power').textContent = data.charging_power?.toFixed(0) || '-';
            const statusNote = document.getElementById('status-note');
            if (statusNote) {
                let noteText = '';
                if (data.auto_pause_reason === 'insufficient_power') {
                    noteText = 'Auto paused: not enough solar to reach minimum charger current.';
                } else if (data.auto_pause_reason === 'battery_priority') {
                    const battInfo = data.battery;
                    if (battInfo && battInfo.priority_threshold) {
                        noteText = `Battery SOC is ${battInfo.soc.toFixed(1)}% — waiting until it reaches ${battInfo.priority_threshold}% before EV charging starts.`;
                    } else {
                        noteText = 'Battery priority is holding charging until SOC recovers.';
                    }
                } else if (data.auto_pause_reason === 'inverter_limit') {
                    noteText = 'Auto paused because the inverter is at its limit, so the charger turned off immediately.';
                } else if (data.auto_pause_reason === 'car_unplugged') {
                    noteText = 'EV idle because the charger reports no car connected.';
                } else if (data.auto_pause_reason === 'vehicle_waiting') {
                    noteText = 'The charger is stuck in "waiting"—unplug and replug the vehicle to restart charging.';
                } else if (data.auto_pause_reason === 'charger_refused') {
                    noteText = 'Charger declined the start command twice; waiting so you can check the vehicle.';
                } else if (data.auto_pause_reason === 'vehicle_charged') {
                    noteText = 'Vehicle still reports fully charged, so the charger is staying idle.';
                } else if (data.charger_transition === 'stopping') {
                    noteText = 'Stopping charger… waiting for hardware to acknowledge.';
                } else if (data.charger_transition === 'starting') {
                    noteText = 'Starting charger… waiting for hardware to ramp up.';
                } else if (data.mode === 'auto' && data.auto_state_help && data.auto_state !== 'charging') {
                    noteText = data.auto_state_help;
                }
                statusNote.textContent = noteText;
                statusNote.style.display = noteText ? 'block' : 'none';
            }
            
            // Solar power
            document.getElementById('available-power').textContent = data.available_power?.toFixed(0) || '-';
            const targetCurrentValue = data.target_current?.toFixed(1) || '-';
            const targetPrimary = document.getElementById('target-current');
            if (targetPrimary) {
                targetPrimary.textContent = targetCurrentValue;
            }
            const targetHeroDisplay = document.getElementById('target-current-hero');
            if (targetHeroDisplay) {
                targetHeroDisplay.textContent = targetCurrentValue;
            }
            document.getElementById('inverter-power').textContent = data.inverter_power?.toFixed(0) || '-';
            const inverterBanner = document.getElementById('inverter-limit-banner');
            inverterBanner.style.display = data.inverter_limiting ? 'flex' : 'none';
            const batteryCard = document.getElementById('battery-card');
            const batteryData = data.battery;
            if (batteryData) {
                document.getElementById('battery-soc').textContent = formatNumber(batteryData.soc, 1);
                document.getElementById('battery-power').textContent = formatNumber(batteryData.power, 0);
                document.getElementById('battery-direction').textContent = (batteryData.direction || '-').replace(/(^|\s)\w/g, m => m.toUpperCase());
                document.getElementById('battery-priority').textContent = batteryData.priority_active ? 'Active' : 'Idle';
            } else {
                document.getElementById('battery-soc').textContent = '-';
                document.getElementById('battery-power').textContent = '-';
                document.getElementById('battery-direction').textContent = '-';
                document.getElementById('battery-priority').textContent = '-';
            }
            const limitingFactors = data.limiting_factors || [];
            const limitingContainer = document.getElementById('limiting-factors');
            if (limitingFactors.length === 0) {
                limitingContainer.innerHTML = '<span class="chip">No limits active</span>';
            } else {
                limitingContainer.innerHTML = limitingFactors.map(factor => {
                    const label = LIMITING_LABELS[factor] || factor;
                    const chipClass = factor === 'inverter_limit' ? 'chip chip-danger' : 'chip chip-warning';
                    return `<span class="${chipClass}">${label}</span>`;
                }).join('');
            }
            const highlightLimits = limitingFactors.includes('battery_priority') || limitingFactors.includes('grace_period') || limitingFactors.includes('insufficient_power');
            batteryCard.classList.toggle('card-warning', highlightLimits);
            
            // Grace period intention
            const intentionPanel = document.getElementById('intention-panel');
            if (data.grace_period && data.grace_period.active) {
                intentionPanel.style.display = 'block';
                const remaining = data.grace_period.remaining_seconds || 0;
                const total = data.grace_period.total_seconds || 1;
                const minutes = Math.floor(remaining / 60);
                const seconds = remaining % 60;
                document.getElementById('grace-countdown').textContent = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
                document.getElementById('grace-reason').textContent = data.grace_period.reason === 'insufficient_power' ? 'Insufficient solar power' : data.grace_period.reason;
                const progress = Math.min(100, Math.max(0, ((total - remaining) / total) * 100));
                document.getElementById('grace-progress').style.width = `${progress}%`;
            } else {
                intentionPanel.style.display = 'none';
            }
            
            // Session
            if (data.session_info) {
                document.getElementById('session-duration').textContent = formatDuration(data.session_info.current_duration_seconds);
                document.getElementById('session-energy').textContent = data.session_info.total_energy_kwh.toFixed(2);
                document.getElementById('session-solar').textContent = data.session_info.solar_percentage.toFixed(1);
            } else {
                document.getElementById('session-duration').textContent = '-';
                document.getElementById('session-energy').textContent = '-';
                document.getElementById('session-solar').textContent = '-';
            }
            
            // Stats
            if (data.stats) {
                document.getElementById('total-sessions').textContent = data.stats.total_sessions || 0;
                document.getElementById('total-energy').textContent = data.stats.total_energy_kwh?.toFixed(2) || 0;
                document.getElementById('avg-solar').textContent = data.stats.avg_solar_percentage?.toFixed(1) || 0;
            }
            
            // Sessions
            if (data.recent_sessions) {
                const sessionList = document.getElementById('session-list');
                if (data.recent_sessions.length === 0) {
                    sessionList.innerHTML = '<div class="loading">No sessions yet</div>';
                } else {
                    sessionList.innerHTML = data.recent_sessions.map(s => `
                        <div class="session-item">
                            <div class="session-id">${s.session_id}</div>
                            <div class="session-stats">
                                ${s.total_energy_kwh.toFixed(2)} kWh • 
                                ${s.solar_percentage.toFixed(1)}% solar • 
                                ${formatDuration(s.duration_seconds)}
                            </div>
                        </div>
                    `).join('');
                }
            }
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('error-message');
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            setTimeout(() => errorDiv.style.display = 'none', 5000);
        }
        
        function showSuccess(message) {
            const successDiv = document.getElementById('success-message');
            successDiv.textContent = message;
            successDiv.style.display = 'block';
            setTimeout(() => successDiv.style.display = 'none', 3000);
        }
        
        function setControlsDisabled(disabled) {
            document.querySelectorAll('button').forEach(btn => {
                if (!btn.dataset.independent) {
                    btn.disabled = disabled;
                }
            });
            document.querySelectorAll('select').forEach(sel => { sel.disabled = disabled; });
        }
        
        const ingressMatch = window.location.pathname.match(/^\/api\/hassio_ingress\/[A-Za-z0-9_-]+/);
        const basePath = ingressMatch ? ingressMatch[0] : '';
        const apiFetch = (path, options) => fetch(`${basePath}${path}`, options);
        
        async function fetchStatus() {
            try {
                const response = await apiFetch('/api/status');
                if (!response.ok) throw new Error('Failed to fetch status');
                const data = await response.json();
                updateUI(data);
            } catch (error) {
                console.error('Error fetching status:', error);
                showError('Failed to fetch status');
            }
        }
        
        async function setMode(mode) {
            if (currentMode && currentMode === mode) {
                return;
            }
            setModeButtonsDisabled(true);
            applyModeVisualState(mode);
            pendingMode = mode;
            pendingModeTimestamp = Date.now();
            try {
                const response = await apiFetch('/api/mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode })
                });
                if (!response.ok) throw new Error('Failed to set mode');
                showSuccess(`Switched to ${mode} mode`);
                await fetchStatus();
            } catch (error) {
                showError('Failed to set mode');
                pendingMode = null;
                await fetchStatus();
            } finally {
                setModeButtonsDisabled(false);
            }
        }

        function handleModeButton(mode) {
            if (currentMode && currentMode === mode) {
                return;
            }
            setMode(mode);
        }

        function handleBatteryPriorityInput(value) {
            const numeric = parseInt(value, 10);
            const note = document.getElementById('battery-priority-note');
            if (note) {
                note.textContent = Number.isNaN(numeric) ? '--%' : `${numeric}%`;
            }
            const guard = document.getElementById('battery-guard-display');
            if (guard) {
                guard.textContent = Number.isNaN(numeric) ? '--%' : `${numeric}%`;
            }
        }

        function handleBatteryPrioritySave() {
            const input = document.getElementById('battery-priority-input');
            if (!input) {
                return;
            }
            const value = parseInt(input.value, 10);
            if (Number.isNaN(value)) {
                showError('Enter a valid SOC between 0% and 100%.');
                return;
            }
            const clamped = Math.min(100, Math.max(0, value));
            if (clamped !== value) {
                input.value = clamped;
            }
            if (currentBatteryPrioritySoc === clamped && pendingBatteryPrioritySoc === null) {
                return;
            }
            setBatteryPrioritySoc(clamped);
        }

        async function setBatteryPrioritySoc(value) {
            setBatterySocControlsDisabled(true);
            pendingBatteryPrioritySoc = value;
            pendingBatterySocTimestamp = Date.now();
            try {
                const response = await apiFetch('/api/battery_priority_soc', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ soc: value })
                });
                if (!response.ok) throw new Error('Failed to update battery minimum SOC');
                showSuccess(`Battery minimum set to ${value}%`);
                await fetchStatus();
            } catch (error) {
                console.error('Error updating battery minimum SOC:', error);
                showError('Failed to update battery minimum SOC');
                pendingBatteryPrioritySoc = null;
                await fetchStatus();
            } finally {
                setBatterySocControlsDisabled(false);
            }
        }
        
        async function setManualCurrent(current) {
            setControlsDisabled(true);
            try {
                const response = await apiFetch('/api/manual_current', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current: parseInt(current, 10) })
                });
                if (!response.ok) throw new Error('Failed to set current');
                showSuccess(`Set current to ${current}A`);
                await fetchStatus();
            } catch (error) {
                showError('Failed to set current');
            } finally {
                setControlsDisabled(false);
            }
        }
        
        async function startCharging() {
            setControlsDisabled(true);
            try {
                const response = await apiFetch('/api/start', { method: 'POST' });
                if (!response.ok) throw new Error('Failed to start charging');
                showSuccess('Starting charging...');
                await fetchStatus();
            } catch (error) {
                showError('Failed to start charging');
            } finally {
                setControlsDisabled(false);
            }
        }
        
        async function stopCharging() {
            setControlsDisabled(true);
            try {
                const response = await apiFetch('/api/stop', { method: 'POST' });
                if (!response.ok) throw new Error('Failed to stop charging');
                showSuccess('Stopping charging...');
                await fetchStatus();
            } catch (error) {
                showError('Failed to stop charging');
            } finally {
                setControlsDisabled(false);
            }
        }
        
        // Initial fetch and auto-refresh
        fetchStatus();
        setInterval(fetchStatus, 2000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serve the main UI."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/status')
def api_status():
    """Get current status."""
    # This would be populated by the main manager
    # For now, return mock data
    data_file = Path('/data/ui_state.json')
    
    if data_file.exists():
        with open(data_file, 'r') as f:
            return jsonify(json.load(f))
    
    return jsonify({
        'status': 'idle',
        'mode': 'auto',
        'charger_status': 'unknown',
        'current_amps': 0,
        'charging_power': 0,
        'available_power': 0,
        'target_current': 0,
        'session_info': None,
        'stats': {},
        'recent_sessions': []
    })


@app.route('/api/mode', methods=['POST'])
def api_set_mode():
    """Set operation mode."""
    data = request.get_json()
    mode = data.get('mode')
    
    # Write command file for main process to pick up
    command_file = Path('/data/command.json')
    with open(command_file, 'w') as f:
        json.dump({'command': 'set_mode', 'mode': mode}, f)
    
    return jsonify({'success': True})


@app.route('/api/manual_current', methods=['POST'])
def api_set_manual_current():
    """Set manual current."""
    data = request.get_json()
    current = data.get('current')
    
    command_file = Path('/data/command.json')
    with open(command_file, 'w') as f:
        json.dump({'command': 'set_manual_current', 'current': current}, f)
    
    return jsonify({'success': True})


@app.route('/api/battery_priority_soc', methods=['POST'])
def api_set_battery_priority_soc():
    """Update the auto-mode battery minimum SOC threshold."""
    data = request.get_json()
    soc = data.get('soc')
    try:
        soc_value = max(0, min(100, int(soc)))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'invalid_soc'}), 400

    command_file = Path('/data/command.json')
    with open(command_file, 'w') as f:
        json.dump({'command': 'set_battery_priority_soc', 'soc': soc_value}, f)

    return jsonify({'success': True, 'soc': soc_value})


@app.route('/api/start', methods=['POST'])
def api_start():
    """Start charging."""
    command_file = Path('/data/command.json')
    with open(command_file, 'w') as f:
        json.dump({'command': 'start'}, f)
    
    return jsonify({'success': True})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop charging."""
    command_file = Path('/data/command.json')
    with open(command_file, 'w') as f:
        json.dump({'command': 'stop'}, f)
    
    return jsonify({'success': True})


def run_server(host='0.0.0.0', port=5000):
    """Run the Flask server."""
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    run_server()
