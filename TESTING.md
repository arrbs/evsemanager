# Testing Guide for EVSE Manager

## Pre-Deployment Testing Strategy

Before installing in your production Home Assistant, follow this testing progression:

### Phase 1: Simulation Validation ✅ (Already Complete!)

You've already validated the control logic with comprehensive simulations showing:
- ✅ Probing behavior with zero-export PV curtailment
- ✅ Battery discharge detection
- ✅ Sunset step-down
- ✅ 100% solar charging
- ✅ Realistic variable loads

**Result**: 29.7 kWh charged, 100% solar, proper probing and step-down

---

### Phase 2: Dry-Run Mode (Recommended Next Step)

Run the add-on in "monitor-only" mode that logs what it **would** do without actually controlling the charger.

#### Setup

1. **Create dry-run configuration**:

```yaml
charger:
  name: "My EVSE"
  switch_entity: "switch.ev_charger"
  current_entity: "number.ev_charger_set_current"
  status_entity: "sensor.ev_charger_status"
  allowed_currents: [6, 8, 10, 13, 16, 20, 24]
  max_current: 24
  step_delay: 10
  voltage_entity: "sensor.ss_inverter_voltage"
  default_voltage: 230

power_method: "battery"

sensors:
  battery_soc_entity: "sensor.ss_battery_soc"
  battery_power_entity: "sensor.ss_battery_power"
  battery_high_soc: 95
  battery_priority_soc: 80
  battery_target_discharge_min: 0
  battery_target_discharge_max: 1500
  inverter_power_entity: "sensor.ss_inverter_power"
  inverter_max_power: 8000

control:
  mode: "manual"  # ⚠️ Keep in manual mode for dry-run
  manual_current: 6
  update_interval: 5
  grace_period: 600
  min_session_duration: 600
  power_smoothing_window: 60
  hysteresis_watts: 500

log_level: "debug"  # ⚠️ Enable debug logging
```

2. **Install add-on** (copy to `/addons/evse_manager/`)

3. **Start add-on** and watch logs

4. **Review logs** - Look for:
   - All sensor readings are correct
   - Battery power calculations look reasonable
   - Available power calculations make sense
   - No entity ID errors or API failures

5. **Let it run for a full day** while your car is **not** charging
   - Verify it reads all sensors correctly
   - Check web UI shows realistic data
   - Confirm no errors or crashes

#### What to Look For

```
✅ Good log entries:
- "Battery >95% charging 0W - probing upward"
- "Available power: 4500W (current EV load: 0W)"
- "PV: 5000W, Battery: 95% (0W), Load: 500W"

❌ Warning signs:
- "Entity not found: sensor.xyz"
- "Invalid state: None"
- "API connection failed"
- Repeated errors or exceptions
```

---

### Phase 3: Controlled Testing (First Real Charge)

Once dry-run validates all sensors work:

#### Pre-Test Checklist

- [ ] All sensor entities verified working in dry-run
- [ ] Logs show realistic power calculations
- [ ] Web UI accessible and showing data
- [ ] You can monitor charger status in real-time
- [ ] First test on a **sunny day** with **predictable solar**
- [ ] You will **actively monitor** the entire session

#### Conservative First Test Configuration

```yaml
control:
  mode: "auto"  # 🔴 NOW SWITCH TO AUTO
  update_interval: 10  # Slower updates initially
  grace_period: 300  # Shorter grace (5 min) for testing
  min_session_duration: 300
  power_smoothing_window: 90  # More smoothing
  hysteresis_watts: 800  # Wider hysteresis

charger:
  step_delay: 15  # ⚠️ LONGER delay for safety
  max_current: 16  # ⚠️ LIMIT max current initially

log_level: "debug"
```

#### During First Test

**Monitor actively**:
1. Keep HA dashboard open showing:
   - Charger status sensor
   - Current setting
   - Battery power
   - PV power

2. Keep add-on logs open

3. Watch for:
   - ✅ Smooth current adjustments (one step at a time)
   - ✅ Appropriate delays between changes
   - ✅ Battery discharge detection working
   - ❌ Rapid cycling (increase hysteresis)
   - ❌ Charger faults (increase step_delay)
   - ❌ Grid import (check battery priority settings)

#### If Charger Faults

**Immediately**:
1. Switch to `mode: "manual"` in configuration
2. Restart add-on
3. Set charger manually to safe current (6-8A)

**Then**:
- Increase `step_delay` to 20-30 seconds
- Verify `allowed_currents` match your charger exactly
- Check charger-specific requirements

---

### Phase 4: Optimization Testing

After successful first session:

#### Gradually Optimize

**Session 2-3**: Still monitor actively
- Keep conservative settings
- Verify consistency

**Session 4-5**: Increase confidence
- Reduce `step_delay` to 12 seconds if no faults
- Increase `max_current` to 20A
- Reduce `hysteresis_watts` to 600

**Session 6-10**: Fine-tune
- Try optimal `step_delay` (10s)
- Full `max_current` (24A)
- Tune `hysteresis_watts` based on behavior
- Adjust `grace_period` based on your solar patterns

**Session 10+**: Enable learning mode (optional)
```yaml
adaptive:
  enabled: true
  learning_sessions: 20
  optimization_goal: "balanced"
  auto_apply: false
```

---

### Phase 5: Continuous Monitoring

#### Create Monitoring Automation

```yaml
automation:
  - alias: "EVSE Manager - Alert on Fault"
    trigger:
      - platform: state
        entity_id: sensor.ev_charger_status
        to: "fault"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ EV Charger Fault"
          message: "Charger entered fault state. Check logs."
          
  - alias: "EVSE Manager - Alert on Grid Import While Charging"
    trigger:
      - platform: numeric_state
        entity_id: sensor.ss_grid_ct_power
        above: 100  # Importing >100W
    condition:
      - condition: state
        entity_id: sensor.evse_manager_status
        state: "active"
    action:
      - service: notify.mobile_app
        data:
          message: "EV charging but importing {{ states('sensor.ss_grid_ct_power') }}W from grid"
```

#### Dashboard Card

```yaml
type: entities
title: EVSE Manager Monitor
entities:
  - entity: sensor.evse_manager_status
  - entity: sensor.evse_manager_mode
  - entity: sensor.evse_manager_target_current
  - entity: sensor.evse_manager_available_power
  - entity: sensor.evse_manager_charging_power
  - entity: sensor.evse_manager_session_energy
  - entity: sensor.evse_manager_solar_percentage
  - entity: sensor.ev_charger_status
    name: Charger Status
  - entity: sensor.ss_battery_power
    name: Battery Power
  - entity: sensor.total_pv_power
    name: Solar Power
```

---

## Testing Checklist Summary

### ✅ Phase 1: Simulation (Complete)
- [x] Standard test scenario successful
- [x] Probing behavior validated
- [x] Battery discharge detection working
- [x] Sunset step-down confirmed

### ⏳ Phase 2: Dry-Run (Next)
- [ ] Install add-on in manual mode
- [ ] Verify all sensor entities work
- [ ] Run for full day without charging
- [ ] Review logs for any errors
- [ ] Confirm web UI accessible

### ⏳ Phase 3: First Real Charge
- [ ] Conservative configuration
- [ ] Sunny day with predictable solar
- [ ] Active monitoring entire session
- [ ] No charger faults
- [ ] Appropriate adjustments
- [ ] No grid import

### ⏳ Phase 4: Optimization (Sessions 2-10)
- [ ] Gradually reduce delays
- [ ] Increase max current
- [ ] Fine-tune hysteresis
- [ ] Consistent stable operation

### ⏳ Phase 5: Production Ready
- [ ] Multiple successful sessions
- [ ] Monitoring automations created
- [ ] Dashboard configured
- [ ] Learning mode enabled (optional)

---

## Troubleshooting Guide

### Issue: Entity Not Found
**Solution**: 
- Check exact entity IDs in HA Developer Tools → States
- Ensure entities exist and have values
- Entity IDs are case-sensitive

### Issue: Charger Faults Repeatedly
**Solution**:
- Increase `step_delay` to 20-30 seconds
- Verify `allowed_currents` match charger
- Check charger documentation for delay requirements
- Some chargers need 30+ seconds between changes

### Issue: Rapid On/Off Cycling
**Solution**:
- Increase `grace_period` to 900 (15 min)
- Increase `hysteresis_watts` to 1000
- Increase `power_smoothing_window` to 120

### Issue: Not Adjusting Current
**Solution**:
- Enable debug logging
- Check available power calculations in logs
- Verify `hysteresis_watts` not too high
- Confirm battery power sensor working

### Issue: Grid Import During Charging
**Solution**:
- Check `battery_priority_soc` setting
- Verify `inverter_max_power` is correct
- Review battery discharge logic in logs
- May need to tune `battery_target_discharge_max`

---

## Safety Reminders

⚠️ **Always monitor first sessions actively**
⚠️ **Have a way to manually control charger**
⚠️ **Start with conservative settings**
⚠️ **Gradually optimize based on behavior**
⚠️ **Create fault monitoring automations**

---

## Next Steps

1. **Complete Phase 2** (dry-run) for at least one full day
2. **Review this guide** before first active charge
3. **Plan first test** on sunny day when you can monitor
4. **Keep logs** and notes from each session
5. **Optimize gradually** over 10+ sessions

Good luck! 🌞⚡🚗
