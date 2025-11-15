#!/usr/bin/with-contenv bashio

set -e

CONFIG_PATH=/data/options.json

bashio::log.info "Starting EVSE Manager..."

# Get configuration
CHARGER_NAME=$(bashio::config 'charger.name' 'EVSE')
POWER_METHOD=$(bashio::config 'power_method' 'battery')
MODE=$(bashio::config 'control.mode' 'auto')

bashio::log.info "Charger: ${CHARGER_NAME}"
bashio::log.info "Power Method: ${POWER_METHOD}"
bashio::log.info "Mode: ${MODE}"

# Start web UI in background
bashio::log.info "Starting Web UI on port 5000..."
cd /app
python3 -m gunicorn -w 1 -b 0.0.0.0:5000 web_ui:app --access-logfile - --error-logfile - &

# Small delay to let web server start
sleep 2

# Run the main application
bashio::log.info "Starting EVSE Manager daemon..."
cd /app && python3 main.py
