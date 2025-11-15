#!/bin/bash
# Test EVSE Manager in Docker container locally

echo "🐳 Building Docker container..."
docker build -t evse-manager:test .

echo ""
echo "📋 Creating test configuration..."
mkdir -p test_data

cat > test_data/options.json << 'EOF'
{
  "charger": {
    "name": "Test EVSE",
    "switch_entity": "switch.ev_charger",
    "current_entity": "number.ev_charger_set_current",
    "status_entity": "sensor.ev_charger_status",
    "allowed_currents": [6, 8, 10, 13, 16, 20, 24],
    "max_current": 24,
    "step_delay": 10,
    "voltage_entity": "sensor.ss_inverter_voltage",
    "default_voltage": 230
  },
  "power_method": "battery",
  "sensors": {
    "battery_soc_entity": "sensor.ss_battery_soc",
    "battery_power_entity": "sensor.ss_battery_power",
    "battery_high_soc": 95,
    "battery_priority_soc": 80,
    "battery_target_discharge_min": 0,
    "battery_target_discharge_max": 1500,
    "inverter_power_entity": "sensor.ss_inverter_power",
    "inverter_max_power": 8000
  },
  "control": {
    "mode": "auto",
    "manual_current": 6,
    "update_interval": 5,
    "grace_period": 600,
    "min_session_duration": 600,
    "power_smoothing_window": 60,
    "hysteresis_watts": 500
  },
  "log_level": "debug"
}
EOF

echo ""
echo "⚠️  NOTE: This will try to connect to Home Assistant"
echo "   Set HA_URL and HA_TOKEN environment variables"
echo ""
read -p "Enter Home Assistant URL (e.g., http://homeassistant.local:8123): " HA_URL
read -p "Enter Long-Lived Access Token: " HA_TOKEN

echo ""
echo "🚀 Running container..."
echo "   Press Ctrl+C to stop"
echo ""

docker run --rm \
  -v $(pwd)/test_data:/data \
  -e SUPERVISOR_TOKEN="${HA_TOKEN}" \
  -e HA_URL="${HA_URL}" \
  -p 5000:5000 \
  evse-manager:test

echo ""
echo "✅ Container stopped"
