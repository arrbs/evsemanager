# Sensor Delay & Overshoot Analysis

## Problem Statement

Home Assistant sensors have a **significant response delay** (30-60+ seconds) between when the EV charger changes current and when the power consumption sensors reflect that change. This causes the EVSE manager to overshoot available power because it makes decisions based on stale sensor data.

## Simulation Updates

### Changes Made

1. **ChargerSimulator** (`power_simulator.py`):
   - Added `sensor_delay` parameter (default 60s)
   - Split current into two values:
     - `actual_current`: Real physical current (immediate)
     - `reported_current`: What sensors report (delayed)
   - Sensors gradually catch up over the delay period
   - Power calculations use **reported** values (what HA sees)
   - Car charging uses **actual** values (physics reality)

2. **Scenario Configuration** (`scenarios.py`):
   - Added `sensor_delay_seconds` parameter (default 60s)
   - All scenarios can now simulate realistic sensor lag

3. **History Tracking** (`run_simulation.py`):
   - Now tracks both actual and reported values:
     - `ev_load` vs `ev_load_actual`
     - `charger_current` vs `charger_current_actual`
   - Added `sensor_delay_progress` to track lag state

4. **Visualization** (`plot_results.py`):
   - Panel 5 now shows overshoot clearly:
     - Gold line: Available power (calculated)
     - Dashed green: EV power (sensors see)
     - Solid red: EV power (actual consumption)
     - Dashed blue: Current (sensors see)
     - Solid blue: Current (actual)

## Test Results (Sunny Day Scenario, 60s delay)

### Overshoot Examples

During ramp-up from 0A → 16A, we observed:

| Time | Actual Current | Reported Current | Difference | Impact |
|------|----------------|------------------|------------|---------|
| 0.2 min | 2.5A | 0.2A | **+2.3A** | Controller thinks it's using 48W, actually 575W |
| 0.4 min | 10.0A | 1.9A | **+8.1A** | Controller thinks 441W, actually 2300W |
| 0.7 min | 16.0A | 4.8A | **+11.2A** | Controller thinks 1111W, actually 3680W |

**Key Finding:** With 60s sensor delay, the system overshoots by **up to 11.2A (2569W)** during ramp-up!

### Why This Matters

1. **Grid Import:** Controller thinks there's excess solar, keeps increasing power, actually importing from grid
2. **Battery Stress:** Controller thinks battery is charging, actually discharging to cover real load
3. **Oscillation:** By the time sensors catch up, controller overcorrects, causing instability
4. **Zero-Export Violations:** Actual consumption exceeds available power, forcing grid export

## Proposed Software Fixes

### Fix 1: Predictive Power Model ⭐ RECOMMENDED

Add a **predictive adjustment** that estimates actual power based on commanded current:

```python
# In power_calculator.py, add method:
def get_predicted_ev_load(self, target_current: float) -> float:
    """
    Predict actual EV load based on target current, accounting for sensor delay.
    
    Args:
        target_current: The current we just commanded to the charger
        
    Returns:
        Estimated actual power consumption (W)
    """
    # Assume sensors are reporting old value, predict new value
    voltage = 230  # V
    predicted_power = target_current * voltage
    
    # Apply safety margin (assume 10% higher than predicted)
    return predicted_power * 1.1

# Then in calculate_available_power():
predicted_ev_load = self.get_predicted_ev_load(current_target)
adjusted_available = pv_power - house_load - predicted_ev_load - battery_reserve
```

**Pros:**
- Simple to implement
- Immediate improvement
- No external dependencies

**Cons:**
- Relies on accurate voltage assumption
- Doesn't account for charger efficiency

### Fix 2: Exponential Moving Average (EMA) Smoothing

Smooth sensor readings to reduce noise and lag impact:

```python
# In ha_api.py or power_calculator.py:
class SensorSmoother:
    def __init__(self, alpha: float = 0.3):
        """Alpha: 0 = only history, 1 = only current reading."""
        self.alpha = alpha
        self.smoothed_values = {}
    
    def update(self, sensor_name: str, new_value: float) -> float:
        if sensor_name not in self.smoothed_values:
            self.smoothed_values[sensor_name] = new_value
        else:
            # EMA formula
            self.smoothed_values[sensor_name] = \
                self.alpha * new_value + (1 - self.alpha) * self.smoothed_values[sensor_name]
        
        return self.smoothed_values[sensor_name]
```

**Pros:**
- Reduces oscillation
- Handles noisy sensors

**Cons:**
- Adds more lag
- Doesn't solve overshoot problem

### Fix 3: Rate Limiting with Dwell Time ⭐ RECOMMENDED

Slow down adjustments to let sensors catch up:

```python
# In charger_controller.py:
class ChargerController:
    def __init__(self, ...):
        # ... existing code ...
        self.min_adjustment_interval = 120  # Wait 2 minutes between adjustments
        self.last_adjustment_time = 0
        
    def set_current(self, target_amps: float):
        current_time = time.time()
        
        # Check if enough time has passed since last adjustment
        time_since_last = current_time - self.last_adjustment_time
        if time_since_last < self.min_adjustment_interval:
            self.logger.debug(f"Skipping adjustment, only {time_since_last:.0f}s elapsed")
            return False
        
        # ... existing current setting logic ...
        
        self.last_adjustment_time = current_time
        return True
```

**Pros:**
- Allows sensors to catch up
- Reduces oscillation
- Simple configuration

**Cons:**
- Slower response to changing conditions
- May miss optimal charging windows

### Fix 4: Two-Phase Adjustment (Aggressive + Verify)

Ramp up aggressively, then verify and adjust:

```python
# In main.py control loop:
class EVSEManager:
    def __init__(self):
        self.pending_verification = None  # (target_current, time_set, verify_after)
        
    def control_loop(self):
        # ... calculate available_power ...
        
        if self.pending_verification:
            # We're in verification phase
            target, time_set, verify_after = self.pending_verification
            if time.time() - time_set >= verify_after:
                # Time to verify
                actual_consumption = self.get_sensor('ev_power')
                if actual_consumption > available_power:
                    # Overshoot! Back off
                    new_target = self.calculate_safe_current(actual_consumption, available_power)
                    self.charger.set_current(new_target)
                    self.logger.warning(f"Overshoot detected: {actual_consumption}W > {available_power}W, reducing to {new_target}A")
                
                self.pending_verification = None
        else:
            # Normal operation
            target_current = self.calculate_target_current(available_power)
            self.charger.set_current(target_current)
            
            # Set verification for 90 seconds from now (1.5x sensor delay)
            self.pending_verification = (target_current, time.time(), 90)
```

**Pros:**
- Fast initial response
- Self-correcting
- Learns from mistakes

**Cons:**
- More complex
- May still briefly overshoot

## Recommended Implementation Plan

### Phase 1: Immediate Fixes (Week 1)
1. ✅ Implement **Fix 1: Predictive Power Model**
   - Add to `power_calculator.py`
   - Use commanded current to predict load
   - Apply 10-15% safety margin

2. ✅ Implement **Fix 3: Rate Limiting**
   - Set `min_adjustment_interval = 120s` (2x sensor delay)
   - Add configuration option
   - Log skipped adjustments for tuning

### Phase 2: Validation (Week 2)
1. Test with real hardware
2. Monitor for:
   - Grid import during charging
   - Battery discharge spikes
   - Oscillation behavior
3. Tune parameters:
   - Safety margin (10-20%)
   - Adjustment interval (90-180s)

### Phase 3: Advanced Features (Week 3+)
1. Implement **Fix 4: Two-Phase Adjustment** if needed
2. Add sensor quality monitoring
3. Adaptive delay estimation (learn actual sensor lag)

## Configuration Changes Needed

Add to `config.yaml`:

```yaml
power_calculation:
  # Existing settings...
  
  # Sensor delay compensation
  sensor_delay_seconds: 60  # How long sensors take to reflect changes
  predictive_model_enabled: true
  predictive_safety_margin: 0.15  # Add 15% to predicted consumption
  
charger:
  # Existing settings...
  
  # Rate limiting
  min_adjustment_interval: 120  # Seconds between current changes
  verification_delay: 90  # Seconds to wait before verifying adjustment
```

## Testing Strategy

### 1. Simulation Tests (Ready to run)
```bash
# Test with different sensor delays
python3 run_simulation.py "Sunny Day" --output delay_60s.json
python3 run_simulation.py "Morning Ramp" --output ramp_60s.json

# Visualize overshoot
python3 plot_results.py delay_60s.json delay_60s.png
```

### 2. Real Hardware Tests
1. **Baseline:** Record current behavior, note overshoot incidents
2. **With Fixes:** Deploy fixes, compare behavior
3. **Metrics to track:**
   - Max overshoot power (W)
   - Grid import events during charging
   - Battery SoC drops during charging
   - Number of current adjustments per session
   - Total session efficiency

### 3. Success Criteria
- ✅ Overshoot reduced to <500W (2A @ 230V)
- ✅ No grid import during good solar conditions
- ✅ Battery SoC increases or stays flat during charging
- ✅ Fewer than 10 adjustments per hour
- ✅ Session efficiency >90% solar powered

## Next Steps

1. **Update simulation:** Add predictive model to simulated controller
2. **Run comparison:** Test with/without fixes
3. **Update real code:** Apply fixes to `app/` directory
4. **Deploy & monitor:** Test on real hardware with logging
5. **Iterate:** Tune parameters based on real-world data
