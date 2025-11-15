# EVSE Manager Simulation

Simulation framework for testing the EVSE manager with realistic solar/battery/grid scenarios.

## Overview

The simulation system allows you to test the EVSE manager's behavior without a real charger or Home Assistant installation. It simulates:

- **Solar production** with realistic daily curves and cloud effects
- **Battery charging/discharging** with SoC tracking
- **House loads** with time-of-day variations
- **Grid import/export** based on power balance
- **EV charger** with realistic ramp rates and current steps

## Quick Start

### Run a Single Scenario

```bash
cd simulation
python run_simulation.py "Sunny Day"
```

### Run All Scenarios

```bash
python run_simulation.py all
```

### List Available Scenarios

```bash
python run_simulation.py --list
```

## Available Scenarios

### Basic Scenarios
1. **Sunny Day** - Perfect conditions with clear sky and strong solar
2. **Cloudy Day** - Variable solar with frequent clouds passing
3. **Morning Ramp** - Solar ramping up from dawn
4. **Afternoon Fade** - Solar declining in late afternoon
5. **Battery Full** - Battery >95% SoC, tests discharge targeting
6. **Insufficient Power** - Very cloudy, not enough power to charge
7. **Step Control Test** - Rapid changes to test step control safety
8. **Late Arrival** - Car connects mid-day with good solar

### Load Spike Scenarios (NEW!)
9. **Sudden Load Spikes** - AC, water heater, and appliances start during charging
10. **Inverter Limit** - Heavy loads approach/exceed inverter capacity, causing grid import
11. **Heavy Load Interruption** - Large sudden load consumes all power, EV stops temporarily
12. **Random Appliances** - Realistic pattern of appliances starting/stopping randomly
13. **Grid Import Stress** - Continuous heavy loads requiring grid import while charging

These scenarios test how the EVSE manager responds to:
- **Sudden appliance starts** (AC units, water heaters, ovens, dryers, pool pumps)
- **Inverter power limits** being approached or exceeded
- **Grid import** when total load exceeds available solar + battery
- **Dynamic power adjustments** to maintain system balance
- **Temporary charging interruptions** during heavy load periods

## Visualization

### Install Dependencies

```bash
pip install matplotlib
```

### Visualize Results

After running a simulation, visualize the results:

```bash
python run_simulation.py "Sunny Day" --output results.json
python visualize.py results.json --output sunny_day.png
```

This creates a comprehensive plot showing:
- Power flows (PV, house, EV)
- Battery state (SoC and power)
- Grid import/export
- Charger current control
- Vehicle SoC progression

### Compare Multiple Scenarios

Run all scenarios and compare:

```bash
# Run and save each scenario
for scenario in "Sunny Day" "Cloudy Day" "Morning Ramp"; do
    python run_simulation.py "$scenario" --output "${scenario// /_}.json"
done

# Create comparison plot (manual aggregation needed)
```

## How It Works

### Architecture

```
run_simulation.py          # Main simulation runner
├── mock_ha_api.py        # Mock Home Assistant API
├── power_simulator.py    # Solar/battery/grid physics
├── scenarios.py          # Test scenarios
└── visualize.py          # Plotting and visualization
```

### Simulation Loop

1. **Update Power State**: Calculate solar, battery, grid based on time of day
2. **Update Sensors**: Push values to mock HA API
3. **Run EVSE Logic**: Actual charger_controller and power_calculator run
4. **Update Charger**: Simulate charger ramping to target current
5. **Record Data**: Save timestep data for analysis
6. **Advance Time**: Move forward 5 seconds (configurable)

### Power Simulator

The power simulator uses realistic physics:

**Solar Production:**
- Sine curve from 6 AM to 6 PM
- Peak at solar noon (12:00)
- Cloud effects with multiple frequency patterns
- Scenario-specific weather (clear/cloudy/partly cloudy)

**Battery Behavior:**
- Charges when PV > Load
- Discharges when PV < Load
- Rate limits (5kW charge/discharge max)
- SoC tracking based on 10 kWh capacity
- Realistic charge slowing at high SoC

**House Load:**
- Base load: 500W
- Morning peak (7-9 AM): +800W
- Evening peak (18-21): +1200W
- Midday increase: +300W
- Random variations (±10%)

**Grid Import/Export:**
- Imports when: PV + Battery < Total Load
- Exports when: PV > Load + Battery Charging

### Charger Simulator

Simulates real EV charger behavior:
- Ramp rate: 0.5 A/second (realistic)
- Tracks actual vs target current
- Car SoC calculation (60 kWh battery)
- Status states: available, waiting, charging, charged, fault

## Example Output

### Sunny Day (Ideal Conditions)
```
Starting simulation: Sunny Day
Description: Perfect conditions: clear sky, strong solar, battery healthy
Duration: 6.0 hours

[Hour 0] PV: 6234W, Battery: 85% (1245W), EV: 0W (0.0A), Grid: -987W
[0s] Car connected at 30.0% SoC
[0s] Starting charge: 4500W available -> 19.6A
[Hour 1] PV: 7456W, Battery: 88% (789W), EV: 3680W (16.0A), Grid: -1234W
[Hour 2] PV: 7891W, Battery: 92% (567W), EV: 4140W (18.0A), Grid: -1567W
[Hour 3] PV: 7923W, Battery: 95% (234W), EV: 4600W (20.0A), Grid: -1890W

Simulation complete!
Results: {
  "scenario": "Sunny Day",
  "ev_energy_kwh": 27.84,
  "grid_import_kwh": 0.12,
  "solar_percent": 99.6,
  "adjustments": 8,
  "soc_gain": 46.4
}
```

### Sudden Load Spikes (Realistic Usage)
```
Starting simulation: Sudden Load Spikes
Description: AC, water heater, and appliances start during charging
Duration: 3.0 hours

Scheduled load event: AC unit starts at 900s (+2800W for 1200s)
Scheduled load event: Water heater at 2100s (+1500W for 900s)
Scheduled load event: Pool pump + dryer at 3600s (+3500W for 1800s)

[Hour 0] PV: 7200W, Battery: 70% (1200W), EV: 4140W (18.0A), Grid: -450W
[900s] LOAD EVENT: AC unit starts (+2800W)
[903s] Reducing charge: 2100W available -> 9.1A
[Hour 1] PV: 7850W, Battery: 75% (890W), EV: 2300W (10.0A), Grid: 250W [+2800W load spike]
[2100s] LOAD EVENT: Water heater (+1500W)
[Hour 2] PV: 7650W, Battery: 72% (-340W), EV: 2300W (10.0A), Grid: 890W [+4300W load spike]
[3600s] LOAD EVENT: Pool pump + dryer (+3500W)
[3605s] Stopping charge: insufficient power (1200W)

Simulation complete!
Results: {
  "scenario": "Sudden Load Spikes",
  "ev_energy_kwh": 6.82,
  "grid_import_kwh": 1.45,
  "solar_percent": 78.7,
  "adjustments": 12,
  "max_load_spike_w": 4300,
  "load_events_count": 4
}
```

### Inverter Limit (Stress Test)
```
Starting simulation: Inverter Limit
Description: Heavy loads approach/exceed inverter capacity
Duration: 2.0 hours

[600s] LOAD EVENT: AC unit 1 (+2500W)
[900s] LOAD EVENT: AC unit 2 (+2500W)
[1200s] LOAD EVENT: Water heater (+2000W)
[Hour 1] PV: 8000W, Battery: 60% (-2100W), EV: 2300W (10.0A), Grid: 1850W [+7000W load spike] [INVERTER LIMIT]

Simulation complete!
Results: {
  "scenario": "Inverter Limit",
  "ev_energy_kwh": 3.21,
  "grid_import_kwh": 2.87,
  "solar_percent": 52.3,
  "inverter_limited_minutes": 45.2,
  "max_load_spike_w": 7000
}
```

## Metrics Explained

- **ev_energy_kwh**: Total energy delivered to EV
- **grid_import_kwh**: Energy imported from grid
- **grid_export_kwh**: Energy exported to grid
- **solar_percent**: Percentage of EV energy from solar
- **charging_hours**: Total time actively charging
- **adjustments**: Number of current changes
- **soc_gain**: Vehicle SoC increase

## Customizing Scenarios

Edit `scenarios.py` to create custom scenarios:

```python
class MyScenario(Scenario):
    def __init__(self):
        super().__init__(
            name="My Test",
            description="Custom test scenario",
            duration_hours=4
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 20,
            'car_connect_at': 3600,  # Connect after 1 hour
            'battery_initial_soc': 50,
            'cloud_factor': 0.8,  # 80% of max solar
            'expected_results': {
                'should_charge': True,
                'min_solar_percent': 80,
            }
        }
```

## Advanced Usage

### Custom Configuration

Modify the config in `run_simulation.py` to test different settings:

```python
config = {
    'control': {
        'hysteresis_watts': 800,  # Test with higher hysteresis
        'power_smoothing_window': 120,  # Longer smoothing
        'grace_period': 900,  # 15 minute grace period
    }
}
```

### Extract Specific Metrics

Load results JSON and analyze:

```python
import json

with open('results.json', 'r') as f:
    results = json.load(f)
    
history = results['history']

# Find maximum power
max_ev_power = max(h['ev_load'] for h in history)

# Calculate efficiency
total_adjustments = results['summary']['adjustments']
efficiency = results['summary']['ev_energy_kwh'] / total_adjustments

# Analyze battery behavior
battery_cycles = sum(
    1 for i in range(1, len(history))
    if history[i]['battery_power'] * history[i-1]['battery_power'] < 0
)
```

## Validating Control Logic

The simulation helps validate:

1. **Step Control Safety**: Verify only one-step changes occur
2. **Grace Periods**: Check charging doesn't stop immediately on power dips
3. **Battery Priority**: Confirm battery charges before EV at low SoC
4. **Discharge Targeting**: Validate EV increases load when battery >95%
5. **Solar Maximization**: Measure solar percentage across scenarios
6. **Fault Prevention**: Ensure no rapid current changes

## Interpreting Results

### Good Performance

- Solar % > 90% in sunny conditions
- Solar % > 70% in cloudy conditions
- Adjustments < 2 per hour
- Smooth current transitions
- No grid import (or minimal)

### Areas for Tuning

- **Too many adjustments**: Increase hysteresis or smoothing
- **Low solar %**: Decrease grace period, adjust faster
- **Grid import during sun**: Power calculation may be conservative
- **Frequent stops**: Increase grace period

## Limitations

The simulation:
- Uses simplified physics (real systems more complex)
- Doesn't model all inverter behaviors
- Assumes perfect sensors (no noise/delays)
- Single-phase only (no 3-phase modeling)
- Fixed house load patterns

Still excellent for validating control logic and parameter tuning!

## Future Enhancements

Planned features:
- Real-time visualization during simulation
- Integration with adaptive learning system
- Multi-day simulations
- Weather data import (actual historical data)
- Multiple vehicle scenarios
- Network latency simulation
- Sensor noise injection

---

**Run simulations to validate your EVSE manager before deploying! 🧪**
