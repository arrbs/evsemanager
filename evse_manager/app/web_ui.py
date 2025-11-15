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
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 { color: #333; margin-bottom: 10px; }
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
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card h2 { color: #333; font-size: 18px; margin-bottom: 15px; }
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #666; font-size: 14px; }
        .metric-value { color: #333; font-size: 20px; font-weight: 600; }
        .metric-unit { color: #999; font-size: 14px; margin-left: 4px; }
        
        .controls {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary { background: #2196f3; color: white; }
        .btn-primary:hover { background: #1976d2; }
        .btn-success { background: #4caf50; color: white; }
        .btn-success:hover { background: #388e3c; }
        .btn-danger { background: #f44336; color: white; }
        .btn-danger:hover { background: #d32f2f; }
        .btn-secondary { background: #999; color: white; }
        .btn-secondary:hover { background: #777; }
        
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
        .error { background: #ffebee; color: #c62828; padding: 15px; border-radius: 6px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ EVSE Manager</h1>
            <span class="status-badge" id="status-badge">Loading...</span>
        </div>
        
        <div id="error-message" class="error" style="display: none;"></div>
        
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
        
        <div class="grid">
            <div class="card">
                <h2>Current Status</h2>
                <div class="metric">
                    <span class="metric-label">Mode</span>
                    <span class="metric-value" id="mode">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Charger Status</span>
                    <span class="metric-value" id="charger-status">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Current</span>
                    <span class="metric-value">
                        <span id="current-amps">-</span>
                        <span class="metric-unit">A</span>
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Charging Power</span>
                    <span class="metric-value">
                        <span id="charging-power">-</span>
                        <span class="metric-unit">W</span>
                    </span>
                </div>
            </div>
            
            <div class="card">
                <h2>Solar Power</h2>
                <div class="metric">
                    <span class="metric-label">Available</span>
                    <span class="metric-value">
                        <span id="available-power">-</span>
                        <span class="metric-unit">W</span>
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Target Current</span>
                    <span class="metric-value">
                        <span id="target-current">-</span>
                        <span class="metric-unit">A</span>
                    </span>
                </div>
            </div>
            
            <div class="card">
                <h2>Current Session</h2>
                <div class="metric">
                    <span class="metric-label">Duration</span>
                    <span class="metric-value" id="session-duration">-</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Energy</span>
                    <span class="metric-value">
                        <span id="session-energy">-</span>
                        <span class="metric-unit">kWh</span>
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Solar %</span>
                    <span class="metric-value">
                        <span id="session-solar">-</span>
                        <span class="metric-unit">%</span>
                    </span>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>Controls</h2>
            <div class="controls">
                <button class="btn-primary" onclick="setMode('auto')">Auto Mode</button>
                <button class="btn-secondary" onclick="setMode('manual')">Manual Mode</button>
                <select id="manual-current" onchange="setManualCurrent(this.value)">
                    <option value="6">6A</option>
                    <option value="8">8A</option>
                    <option value="10">10A</option>
                    <option value="13">13A</option>
                    <option value="16">16A</option>
                    <option value="20">20A</option>
                    <option value="24">24A</option>
                </select>
                <button class="btn-success" onclick="startCharging()">Start Charging</button>
                <button class="btn-danger" onclick="stopCharging()">Stop Charging</button>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>Statistics</h2>
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
                <div class="metric">
                    <span class="metric-label">Avg Solar %</span>
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
        function formatDuration(seconds) {
            if (!seconds) return '-';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
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
            document.getElementById('charger-status').textContent = data.charger_status || '-';
            document.getElementById('current-amps').textContent = data.current_amps?.toFixed(1) || '-';
            document.getElementById('charging-power').textContent = data.charging_power?.toFixed(0) || '-';
            
            // Solar power
            document.getElementById('available-power').textContent = data.available_power?.toFixed(0) || '-';
            document.getElementById('target-current').textContent = data.target_current?.toFixed(1) || '-';
            
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
            try {
                const response = await apiFetch('/api/mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode })
                });
                if (!response.ok) throw new Error('Failed to set mode');
                fetchStatus();
            } catch (error) {
                showError('Failed to set mode');
            }
        }
        
        async function setManualCurrent(current) {
            try {
                const response = await apiFetch('/api/manual_current', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current: parseInt(current) })
                });
                if (!response.ok) throw new Error('Failed to set current');
                fetchStatus();
            } catch (error) {
                showError('Failed to set current');
            }
        }
        
        async function startCharging() {
            try {
                const response = await apiFetch('/api/start', { method: 'POST' });
                if (!response.ok) throw new Error('Failed to start charging');
                fetchStatus();
            } catch (error) {
                showError('Failed to start charging');
            }
        }
        
        async function stopCharging() {
            try {
                const response = await apiFetch('/api/stop', { method: 'POST' });
                if (!response.ok) throw new Error('Failed to stop charging');
                fetchStatus();
            } catch (error) {
                showError('Failed to stop charging');
            }
        }
        
        // Initial fetch and auto-refresh
        fetchStatus();
        setInterval(fetchStatus, 5000);
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
