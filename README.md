# EVSE Manager — Deterministic Controller + Web UI

This add-on now ships a lean, deterministic EVSE controller plus the existing monitoring UI:

- `evse_manager/app/controller_service.py` owns the main loop, invoking the FSM every second.
- `state_machine.py`, `controller_config.py`, and `ha_adapter.py` implement the rule set from `EVSE_CONTROLLER_GUIDE.md`.
- `web_ui.py` continues to render the live dashboard, reading `ui_state.json` that the controller persists each tick.

The focus is on a single-owner, deterministic controller that modulates current purely from Home Assistant sensor data—no adaptive learning or historical heuristics. If you need the legacy auto/manual manager, refer to repository history.

## Deterministic FSM Controller Guide

- `EVSE_CONTROLLER_GUIDE.md` remains the authoritative specification for the control rules and invariants.
- The new controller implementation follows this guide: monotonic cooldown handling, inverter protection, probe/main regions, and explicit rule ordering.
- When extending the controller, update the guide first to keep design and implementation in lockstep.

> **Note**: Sections below the next heading are preserved from the original project. Many advanced features (learning mode, sessions, etc.) are not part of the deterministic controller and should be treated as historical documentation.

## Current Components

- Deterministic FSM controller (see `controller_service.py`).
- Flask/Gunicorn Web UI for ingress.
- Configuration loader that maps `options.json` into controller + entity wiring.
- Home Assistant REST adapter for switch/current commands.

Any additional logic—power calculators, simulators, adaptive learning—has been removed intentionally.

## Deterministic Controller Quickstart

Set the required entity IDs and controller constants inside your add-on configuration (`/data/options.json`). All keys live at the top level unless noted:

```yaml
entities:
  charger_switch: switch.ev_charger
  charger_current: number.ev_charger_set_current
  charger_status: sensor.ev_charger_status
  battery_soc: sensor.battery_soc
  battery_power: sensor.battery_power        # Negative = charging
  inverter_power: sensor.inverter_power
  pv_power: sensor.total_pv_power
  auto_enabled: input_boolean.evse_auto      # Optional; omit to always allow auto

tick_seconds: 1.5          # Clamped between 1–2s
line_voltage_v: 230        # Used to convert amps → watts for UI
soc_main_max: 95           # Above this, controller switches to PROBE region
inverter_limit_w: 8000     # Hard cap reported by inverter
inverter_margin_w: 500     # Safety cushion below inverter limit
probe_max_discharge_w: 1000
small_discharge_margin_w: 200

log_level: INFO            # DEBUG for verbose FSM traces
auto_enabled_default: true # Fallback when auto entity missing/unavailable
```

When the add-on starts, `controller_service.py` loads this configuration, polls the listed entities once per tick, runs the FSM, and writes the latest UI payload to `/data/ui_state.json`. The web UI renders the same data via Gunicorn on port 5000/ingress. Adjusting entity IDs in the config requires an add-on restart.

### Manual Verification Checklist

1. **Sensor sanity** – In Home Assistant Developer Tools, confirm every entity listed above reports valid values (particularly units/sign conventions for power sensors).
2. **Dry run** – Start the add-on while the EVSE is idle. Watch the add-on logs for `Deterministic FSM online` and ensure the UI shows `idle`.
3. **Plug in vehicle** – With auto-enabled, plug in the EV. The FSM should transition from `idle` to `charging` once PV excess or battery discharge rules allow the first 6 A step.
4. **Step changes** – Observe log lines like `FSM MAIN_READY→MAIN_COOLDOWN | 6A→8A` as solar power increases/decreases; verify the HA number entity mirrors the commanded amps.
5. **Inverter guard** – Temporarily limit inverter capacity (or simulate via Developer Tools) so total load exceeds `inverter_limit_w`. The FSM should step down and, if necessary, disable the switch entirely.
6. **Probe region** – Raise battery SoC above `soc_main_max` and verify the controller switches to probe mode (look for `PROBE_READY` in logs) and uses battery discharge thresholds instead of PV excess.

## Installation

### Method 1: Add Repository URL

1. In Home Assistant, navigate to **Settings** → **Add-ons** → **Add-on Store**
2. Click the three dots menu (⋮) in the top right
3. Select **Repositories**
4. Add this repository URL: `https://github.com/yourusername/homeassistant-evse-manager`
5. Find "EVSE Manager" in the add-on store and click **Install**

### Method 2: Manual Installation

1. Copy this entire folder to `/addons/evse_manager/` on your Home Assistant instance
2. Restart Home Assistant
3. Navigate to **Settings** → **Add-ons** → **Add-on Store**
4. Find "EVSE Manager" in the local add-ons section and click **Install**

## Configuration

### Charger Configuration

Define your EVSE charger's characteristics:

```yaml
charger:
  name: "My EVSE"
  switch_entity: "switch.ev_charger"           # On/off control
  current_entity: "number.ev_charger_set_current"  # Current setting
  status_entity: "sensor.ev_charger_status"    # Status sensor
  allowed_currents: [6, 8, 10, 13, 16, 20, 24] # Allowed current steps (Amps)
  step_delay: 10                                # Seconds between adjustments
  voltage_entity: "sensor.ss_inverter_voltage" # Optional: voltage sensor
  default_voltage: 230                          # Default voltage if sensor unavailable
```

**Status Values**: The `status_entity` should report:
- `charging` - Currently charging
- `waiting` - Car connected, not charging
- `available` - No car connected
- `charged` - Charging complete
- `fault` - Charger fault state

### Power Calculation Method

Choose how to calculate available solar power:

```yaml
power_method: "battery"  # Options: "direct", "grid", "battery"
```

#### Method A: Direct Excess Power (Recommended if available)
```yaml
power_method: "direct"
sensors:
  excess_power_entity: "sensor.pv_excess_power"
```

#### Method B: Grid Export
```yaml
power_method: "grid"
sensors:
  grid_power_entity: "sensor.grid_ct_power"  # Negative = exporting
```

#### Method C: Battery State (Most sophisticated)
```yaml
power_method: "battery"
sensors:
  battery_soc_entity: "sensor.battery_soc"
  battery_power_entity: "sensor.battery_power"  # Negative = charging
  battery_power_charging_positive: false          # Set true if your sensor reports positive while charging
  battery_high_soc: 95          # Above this, try to discharge battery
  battery_priority_soc: 80      # Below this, battery has priority
  battery_target_discharge_min: 0    # Target discharge range when full
  battery_target_discharge_max: 1500  # (helps measure true excess)
  inverter_power_entity: "sensor.inverter_power"
  inverter_max_power: 8000      # Inverter capacity limit
```

### Control Parameters

```yaml
control:
  mode: "auto"                  # "auto" or "manual"
  manual_current: 6             # Current for manual mode (Amps)
  update_interval: 5            # Control loop interval (seconds)
  grace_period: 600             # Seconds to wait before stopping due to low power
  min_session_duration: 600     # Minimum session time (seconds)
  power_smoothing_window: 60    # Smoothing window for power readings (seconds)
  hysteresis_watts: 500         # Minimum power change to trigger adjustment
```

### Complete Example Configuration

```yaml
charger:
  name: "Tesla Wall Connector"
  switch_entity: "switch.ev_charger"
  current_entity: "number.ev_charger_set_current"
  status_entity: "sensor.ev_charger_status"
  allowed_currents: [6, 8, 10, 13, 16, 20, 24]
  step_delay: 10
  voltage_entity: "sensor.ss_inverter_voltage"
  default_voltage: 230

power_method: "battery"

sensors:
  battery_soc_entity: "sensor.ss_battery_soc"
  battery_power_entity: "sensor.ss_battery_power"
  battery_power_charging_positive: false
  battery_high_soc: 95
  battery_priority_soc: 80
  battery_target_discharge_min: 0
  battery_target_discharge_max: 1500
  inverter_power_entity: "sensor.ss_inverter_power"
  inverter_max_power: 8000
  total_pv_entity: "sensor.total_pv_power"
  total_load_entity: "sensor.total_load_power"

control:
  mode: "auto"
  manual_current: 6
  update_interval: 5
  grace_period: 600
  min_session_duration: 600
  power_smoothing_window: 60
  power_smoothing_window_seconds: 30
  hysteresis_watts: 500

log_level: "info"
```

## How to run the Web UI

Run the local Flask server to serve the UI for monitoring. This serves a self-contained dashboard and reads `ui_state.json` if present.

Install Flask:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
```

Run the UI:

```bash
python3 evse_manager/app/web_ui.py
```

Open http://localhost:5000 in your browser to view the dashboard.

## How It Works

### Control Flow

1. **Power Monitoring**: Continuously monitors solar production using your selected method
2. **State Detection**: Checks charger status (car connected, charging, etc.)
3. **Decision Making**: 
   - Checks battery priority threshold
   - Calculates available excess power
   - Determines if sufficient power available to charge
4. **Safe Adjustment**: 
   - Steps through allowed currents with configured delays
   - Monitors for fault conditions
   - Applies hysteresis to prevent rapid cycling
5. **Session Tracking**: Records energy usage and solar percentage
6. **Status Publishing**: Updates Home Assistant entities and web UI

### Intelligent Features

#### Step Control
- Prevents faults by respecting charger step delays
- Only moves one step at a time (e.g., 6A→8A→10A)
- Waits configured delay between changes
- Monitors charger status after each adjustment

#### Grace Period
- Doesn't immediately stop charging when clouds pass
- Waitable period before stopping due to insufficient power
- Balances solar optimization with charging continuity

#### Battery Priority (Method C)
- Below priority SoC: Battery charges first, no EV charging
- Between priority and high SoC: Use battery charging rate as available power
- Above high SoC: Increase EV load until battery mildly discharges
- This reveals true available solar power even when battery is full

#### Hysteresis
- Prevents constant adjustments for small power fluctuations
- Only adjusts when power change exceeds threshold
- Smooths power readings over configured window
- Responds rapidly to large changes (e.g., sudden loads)

#### Inverter Limit Protection
- Monitors inverter output power
- Stops charging if inverter maxed and importing from grid
- Prevents grid import during solar charging

## Adaptive Learning Mode ⭐

**NEW!** Let the system automatically discover optimal settings for your setup.

### Quick Start

Enable learning in your configuration:

```yaml
adaptive:
  enabled: true
  learning_sessions: 20
  optimization_goal: "balanced"  # Options: solar, stability, balanced
  auto_apply: false  # Review before applying
```

The system will:
1. **Test different parameter combinations** over 20 charging sessions
2. **Score each trial** based on solar %, stability, and energy delivered
3. **Find optimal settings** for hysteresis, smoothing, and grace period
4. **Suggest (or apply)** the best configuration for your system

### See It In Action

Web UI shows real-time learning progress:
- Session count (e.g., "Learning: 12/20 sessions")
- Current best score
- Settings being tested
- Optimal configuration when complete

### Detailed Guide

See **[LEARNING.md](LEARNING.md)** for:
- How the learning algorithm works
- Configuration options explained
- Optimization goals (solar/stability/balanced)
- Safety features and limits
- Troubleshooting guide
- Example workflows

### Benefits

- **No manual tuning needed** - System finds optimal settings
- **Adapts to your specific setup** - Solar profile, battery, charger
- **Improves over time** - Learns from real sessions
- **Safe exploration** - Built-in safety limits and fault detection

---

## Using the Web Interface

The add-on includes a web UI for monitoring and manual control.

### Accessing the UI

## Home Assistant Entities

The add-on creates the following entities:

### Sensors
- `sensor.evse_manager_mode` - Current mode (auto/manual)
- `sensor.evse_manager_status` - Manager status (active/idle)
- `sensor.evse_manager_target_current` - Target charging current (A)
- `sensor.evse_manager_available_power` - Available solar power (W)
- `sensor.evse_manager_charging_power` - Actual charging power (W)
- `sensor.evse_manager_session` - Current session status
- `sensor.evse_manager_session_energy` - Session energy (kWh)
- `sensor.evse_manager_solar_percentage` - Session solar % 
- `sensor.evse_manager_total_energy` - Total energy all-time (kWh)

### Using in Automations

```yaml
automation:
  - alias: "Notify when EV charging starts"
    trigger:
      - platform: state
        entity_id: sensor.evse_manager_status
        to: "active"
    action:
      - service: notify.mobile_app
        data:
          message: "EV charging started with {{ states('sensor.evse_manager_available_power') }}W solar"
```

## Troubleshooting

### Check Logs

View add-on logs in Home Assistant:
1. Navigate to **Settings** → **Add-ons** → **EVSE Manager**
2. Click the **Log** tab

Set `log_level: debug` in configuration for detailed logging.

### Common Issues

#### Add-on won't start
- Verify all entity IDs in configuration are correct and exist
- Check entity IDs match exactly (case-sensitive)
- Ensure Home Assistant API is accessible
- Review add-on log for specific error messages

#### Charger goes into fault
- **Increase `step_delay`**: Your charger may need more time between adjustments
- **Check allowed_currents**: Ensure these match your charger's supported values
- **Verify voltage**: Make sure voltage sensor is correct or set appropriate default
- The add-on will automatically stop charging if fault is detected

#### Power not adjusting
- **Check power_method sensors**: Ensure all sensors for your method are configured and reporting values
- **Verify hysteresis_watts**: If set too high, small changes won't trigger adjustments
- **Check grace_period**: Might be waiting to confirm power change is sustained
- **Review logs**: Debug mode shows power calculations and adjustment decisions

#### Charging stops unexpectedly
- **Grace period expired**: Insufficient power for longer than `grace_period`
- **Battery priority active**: Battery SoC below `battery_priority_soc`
- **Inverter limit reached**: Check `inverter_max_power` setting
- **Car disconnected**: Check charger status sensor

#### Web UI not loading
- Verify ingress is enabled in configuration
- Check port 5000 is not blocked
- Review add-on logs for web server errors
- Try restarting the add-on

### Charger-Specific Notes

#### Chargers with Fixed Steps
Some chargers only support specific current values. Configure `allowed_currents` to match:
```yaml
allowed_currents: [6, 8, 10, 13, 16, 20, 24]  # Example for certain chargers
```

#### Slow-Responding Chargers
If your charger takes time to respond to changes:
```yaml
step_delay: 15  # Increase delay between steps
```

#### Integration Support
This add-on works with any EVSE integration that provides:
- A switch entity for on/off control
- A number entity for current setting
- A sensor entity for status

Compatible integrations include: Wallbox, Easee, OpenEVSE, and others with similar entity structure.

## Advanced Configuration

### Adaptive Learning Parameters

```yaml
adaptive:
  enabled: false                   # Enable learning mode
  learning_sessions: 20            # Number of sessions to learn over
  optimization_goal: "balanced"    # What to optimize: solar, stability, balanced
  auto_apply: false               # Auto-apply learned settings (careful!)
  tune_hysteresis: true           # Allow learning to adjust hysteresis
  tune_smoothing: true            # Allow learning to adjust smoothing
  tune_grace_period: true         # Allow learning to adjust grace period
  min_step_delay: 5               # Safety: minimum step delay (seconds)
  max_step_delay: 30              # Maximum step delay to try
```

**Optimization Goals:**
- `solar` - Maximize solar percentage, may be less stable
- `stability` - Minimize adjustments/faults, may use less solar
- `balanced` - Best of both (recommended)

**Recommendations:**
- Start with `auto_apply: false` to review learned settings
- Use 20+ sessions for reliable results
- Learn during stable, sunny weather
- See [LEARNING.md](LEARNING.md) for detailed guide

### Custom Power Algorithms

The power calculation control code has been removed. Instead, you can view the Web UI in `evse_manager/app/web_ui.py`.
- Adjust smoothing algorithms
- Change hysteresis behavior
- Add custom conditions

### Session Data

Session data is stored in `/data/sessions.json` and `/data/stats.json`. You can:
- Export for analysis
- Build custom visualizations
- Track long-term trends

### Integration with Automations

Use the published entities in complex automations:

```yaml
# Stop charging if forecast shows clouds
automation:
  - alias: "Stop charging on bad forecast"
    trigger:
      - platform: state
        entity_id: weather.home
        to: "cloudy"
    condition:
      - condition: state
        entity_id: sensor.evse_manager_status
        state: "active"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.ev_charger
```

## Development

### Project Structure (UI-only)

```
homeassistant-evse-manager/
├── app/
│   └── web_ui.py              # Flask web interface (UI-only)
├── .github/
│   └── copilot-instructions.md
├── build.yaml                  # Multi-arch build configuration
├── config.yaml                 # Add-on configuration schema
├── Dockerfile                  # Container build instructions
├── run.sh                      # Startup script
├── .gitignore
└── README.md
```

### Local Testing

```bash
# Install dependencies
pip3 install requests flask gunicorn

# Create test configuration
mkdir -p data
cat > data/options.json << EOF
{
  "charger": {
    "name": "Test EVSE",
    "switch_entity": "switch.ev_charger",
    "current_entity": "number.ev_charger_set_current",
    "status_entity": "sensor.ev_charger_status",
    "allowed_currents": [6, 8, 10, 13, 16, 20, 24],
    "step_delay": 10,
    "default_voltage": 230
  },
  "power_method": "battery",
  "sensors": {
    "battery_soc_entity": "sensor.battery_soc",
    "battery_power_entity": "sensor.battery_power",
    "battery_high_soc": 95,
    "battery_priority_soc": 80,
    "battery_target_discharge_min": 0,
    "battery_target_discharge_max": 1500,
    "inverter_power_entity": "sensor.inverter_power",
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

# Run the UI locally
cd app
python3 web_ui.py
```

### Building the Add-on

```bash
# Build for local architecture
docker build -t evse-manager .

# Test the container
docker run --rm \
  -v $(pwd)/data:/data \
  -e SUPERVISOR_TOKEN=your-token \
  evse-manager
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

This project is provided as-is for personal and educational use.

## Architecture

### Components

1. **ChargerController**: Manages safe current adjustments with step delays and fault detection
2. **PowerManager**: Calculates available power using selected method (A/B/C) with smoothing
3. **SessionManager**: Tracks sessions, energy usage, and statistics
4. **HomeAssistantAPI**: Communicates with Home Assistant REST API
5. **EntityPublisher**: Creates and updates Home Assistant entities
6. **WebUI**: Flask-based web interface with real-time monitoring

### Data Flow

```
┌─────────────────┐
│ Home Assistant  │
│   Sensors       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  PowerManager   │────▶│ ChargerController│
│  (Calculate)    │     │  (Safe Adjust)   │
└─────────────────┘     └────────┬─────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│ SessionManager  │     │   EVSE Hardware  │
│  (Track)        │     │   (Charger)      │
└─────────────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐
│  Web UI +       │
│  HA Entities    │
└─────────────────┘
```

## Safety Considerations

### Electrical Safety
- **Always monitor** your first few charging sessions
- **Verify voltage** settings match your installation
- **Ensure proper grounding** of all equipment
- **Check amp ratings** of your electrical circuit and wiring
- **Consult an electrician** if unsure about your setup

### Charger Protection
- The add-on implements multiple safety features:
  - Step delays prevent rapid changes that could fault the charger
  - Fault detection automatically stops charging
  - Grace periods prevent rapid on/off cycling
  - Inverter limit protection prevents overload

### Recommendations
- Start with conservative settings (longer delays, wider hysteresis)
- Monitor logs during initial sessions
- Gradually optimize settings based on your system's behavior
- Keep `step_delay` at 10 seconds or higher unless you've verified your charger can handle faster changes

## Contributing

Contributions are welcome! Areas for enhancement:
- Additional power calculation methods
- Machine learning for optimization
- Weather forecast integration
- Time-of-use rate awareness
- Multi-vehicle support

Please open an issue or pull request on GitHub.

## Changelog

### v0.1.0 (Initial Release)
- Three power calculation methods (Direct, Grid Export, Battery)
- Intelligent step control with fault prevention
- Auto and manual modes
- Session tracking and statistics
- Web UI with real-time monitoring
- Home Assistant entity integration
- Battery priority management
- Hysteresis and smoothing

## License

This project is provided as-is for personal and educational use.

## Disclaimer

This add-on is provided without warranty of any kind. The authors are not responsible for:
- Damage to your EVSE, vehicle, or electrical system
- Electrical safety issues
- Grid connection violations
- Any other issues arising from use of this software

**Important**:
- Always monitor your EV charging, especially during initial setup
- Ensure your electrical installation is appropriate for the power levels configured
- Verify compliance with local electrical codes and regulations
- Consult with a qualified electrician if you have any doubts about your setup
- Test thoroughly with conservative settings before optimizing

## Support

For issues, questions, or feature requests:
- Check the Troubleshooting section above
- Review add-on logs with debug level enabled
- Open an issue on GitHub with detailed information

## Acknowledgments

Built with Home Assistant add-on architecture and designed for solar-optimized EV charging.
