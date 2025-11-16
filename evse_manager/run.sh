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
ACCESS_LOG_ARGS="--access-logfile /dev/null"
if bashio::config.true 'ui_access_logs'; then
	ACCESS_LOG_ARGS="--access-logfile -"
fi
cd /app
python3 -m gunicorn -w 1 -b 0.0.0.0:5000 web_ui:app ${ACCESS_LOG_ARGS} --error-logfile - &

# Small delay to let web server start
sleep 2

bashio::log.info "Starting deterministic controller loop..."
python3 controller_service.py
