# Home Assistant EVSE Manager Add-on

An intelligent Home Assistant add-on that dynamically manages your Electric Vehicle Supply Equipment (EVSE) power levels based on available solar power production with advanced control algorithms and real-time monitoring.

## Overview

This add-on provides sophisticated solar-aware EV charging with multiple power calculation methods, intelligent step control to prevent faults, session tracking, and a built-in web interface. It automatically adjusts your EV charger's power output to maximize the use of excess solar energy while respecting your charger's limitations and preventing grid import.

## Features

### Core Functionality
- 🌞 **Three Power Calculation Methods**:
  - **Direct**: Use a pre-calculated excess power sensor
  - **Grid Export**: Calculate from grid import/export
  - **Battery**: Intelligent battery state monitoring with priority control
  
- ⚡ **Smart Charger Control**:
  - Configurable stepped current control (prevents faults)
  - Automatic delay between adjustments
  - Fault detection and recovery
  - Support for chargers with discrete amp steps
  
- 🎯 **Dual Operating Modes**:
  - **Auto Mode**: Automatically adjusts power based on solar availability
  - **Manual Mode**: Fixed current setting with safe step transitions
  
- 🔋 **Battery Priority Management**:
  - Configurable battery SoC threshold
  - Prioritizes home battery over EV charging
  - Maintains target discharge range when battery is full
  
- 📊 **Session Tracking & Analytics**:
  - Tracks energy consumed per session
  - Calculates solar vs. grid percentage
  - Historical session data storage
  - Learning and optimization over time
  
- 🌐 **Built-in Web Interface**:
  - Real-time monitoring dashboard
  - Control mode and current settings
  - View current session and statistics
  - Session history
  
- 🏠 **Home Assistant Integration**:
  - Publishes entities for all key metrics
  - Seamless integration with automations
  - Dashboard widgets and controls

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
  hysteresis_watts: 500

log_level: "info"
```

## Prerequisites

Before using this add-on, ensure you have:

1. **Solar Power Sensor**: A sensor entity that reports current solar power production in Watts
   - Example: Integration with your solar inverter (SolarEdge, Fronius, Enphase, etc.)

2. **EVSE Integration**: Your EV charger must be integrated with Home Assistant
   - Popular integrations: Wallbox, Easee, OpenEVSE, etc.
   - The charger entity should support power level control

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

You can modify the power calculation logic in `app/power_calculator.py`:
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

### Project Structure

```
homeassistant-evse-manager/
├── app/
│   ├── main.py                 # Main control loop and manager
│   ├── charger_controller.py   # EVSE control with safe step logic
│   ├── power_calculator.py     # Power calculation methods A/B/C
│   ├── session_manager.py      # Session tracking and statistics
│   ├── ha_api.py               # Home Assistant API client
│   └── web_ui.py              # Flask web interface
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

# Set Home Assistant connection (for testing)
export HA_URL="http://homeassistant.local:8123"
export HA_TOKEN="your-long-lived-access-token"

# Run the application
cd app
python3 main.py

# Or run web UI separately
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
