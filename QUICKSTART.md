# EVSE Manager - Quick Start Guide

## What You Have

A fully-featured Home Assistant add-on for intelligent solar-based EV charging with:

✅ **3 Power Calculation Methods**
- Direct excess power sensor
- Grid export monitoring  
- Battery state analysis (your choice)

✅ **Smart Charger Control**
- Safe stepped current adjustments
- Configurable delays between steps
- Automatic fault detection

✅ **Dual Modes**
- Auto: Solar-optimized charging
- Manual: Fixed current with safe transitions

✅ **Web Interface**
- Real-time monitoring dashboard
- Control panel for mode and current
- Session history and statistics

✅ **Session Tracking**
- Energy consumption per session
- Solar vs grid percentage
- Historical data storage

## Enable Learning Mode (Optional)

**Let the system find optimal settings automatically!**

Add to your configuration:
```yaml
adaptive:
  enabled: true
  learning_sessions: 20
  optimization_goal: "balanced"
  auto_apply: false  # Review before applying
```

**What happens:**
- System tests different settings over 20 charging sessions
- Web UI shows learning progress
- After 20 sessions, recommends optimal configuration
- You review and manually apply (if `auto_apply: false`)

**See:** [LEARNING.md](LEARNING.md) for complete guide

---

## Your Configuration

Based on your requirements, here's your configuration:

  switch_entity: "switch.ev_charger"
  current_entity: "number.ev_charger_set_current"
  voltage_entity: "sensor.ss_inverter_voltage"
  default_voltage: 230
This quickstart now only covers the included Web UI; the control logic has been removed.

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
  grid_power_entity: "sensor.ss_grid_ct_power"
  total_pv_entity: "sensor.total_pv_power"
  total_load_entity: "sensor.total_load_power"

  grace_period: 600
  min_session_duration: 600
  power_smoothing_window: 60

log_level: "info"

# Run the Web UI
cd app
python3 web_ui.py
## Next Steps

1. **Install in Home Assistant**
   - Copy the entire folder to your Home Assistant add-ons directory
   - Or set up as a repository add-on

2. **Configure**
   - Update config.yaml with your specific entity IDs
   - Verify all entity IDs exist in your Home Assistant

3. **Test Carefully**
│   └── web_ui.py              # Web interface (UI-only)
   - Monitor logs during first few sessions
   - Watch for any fault conditions
   - Adjust `step_delay` if needed

4. **Access Web UI**
   - After starting, click "EVSE Manager" in HA sidebar
   - Monitor real-time charging status

5. **Create Automations**
   - Use the exposed entities in your automations

```
homeassistant-evse-manager/
│   ├── session_manager.py      # Sessions (279 lines)
│   ├── ha_api.py               # HA integration (288 lines)
├── run.sh                      # Startup script
├── build.yaml                  # Multi-arch builds
```

**Total**: ~1,895 lines of Python code + configuration

### Battery Method (Your Choice)
- **Below 80% SoC**: Battery charges first, no EV charging

### Step Control Safety
- Monitors for faults after each change
- Automatically stops if charger faults
- Doesn't stop immediately when solar drops
- Waits 10 minutes (configurable) before stopping
- Handles clouds and transient loads gracefully

### Hysteresis
- Won't adjust for changes <500W (configurable)
- Smooths readings over 60 seconds
- Responds rapidly to large drops (>1000W)

## Troubleshooting Tips

**If charger faults:**
- Increase `step_delay` to 15-20 seconds
- Check `allowed_currents` match your charger exactly

**If not adjusting:**
- Check all sensor entity IDs are correct
- Verify sensors are reporting values
- Set `log_level: debug` to see calculations

**If stops too often:**
- Increase `grace_period` to 900 (15 min)
- Increase `hysteresis_watts` to 1000

**If adjusts too much:**
- Increase `hysteresis_watts`
- Increase `power_smoothing_window`

## Support

All code is well-commented and modular. Each module can be understood independently. Check the README.md for comprehensive documentation.

Good luck with your solar-powered EV charging! 🌞⚡🚗
