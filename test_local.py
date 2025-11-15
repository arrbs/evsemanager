#!/usr/bin/env python3
"""
Local testing script for EVSE Manager without Home Assistant.
Creates mock sensors and runs the control logic.
"""

import sys
import time
import json
from datetime import datetime

# Mock Home Assistant API for testing
class MockHAAPI:
    """Simulates Home Assistant API with fake sensor values."""
    
    def __init__(self):
        self.entities = {
            "switch.ev_charger": {"state": "on"},
            "number.ev_charger_set_current": {"state": "6"},
            "sensor.ev_charger_status": {"state": "charging"},
            "sensor.ss_battery_soc": {"state": "98"},  # >95% to trigger probing
            "sensor.ss_battery_power": {"state": "0"},  # Will vary during test
            "sensor.ss_inverter_voltage": {"state": "230"},
            "sensor.ss_inverter_power": {"state": "5000"},
            "sensor.total_pv_power": {"state": "5500"},
            "sensor.total_load_power": {"state": "500"},
        }
        self.current = 6  # Track current setting
        
    def get_state(self, entity_id):
        """Get mock sensor state."""
        if entity_id not in self.entities:
            return None
        # Return state value directly (not wrapped in dict)
        return self.entities[entity_id]["state"]
    
    def set_state(self, entity_id, state):
        """Set mock sensor state."""
        if entity_id not in self.entities:
            self.entities[entity_id] = {}
        self.entities[entity_id]["state"] = str(state)
    
    def call_service(self, domain, service, entity_id, **kwargs):
        """Simulate service call."""
        print(f"  📡 Service: {domain}.{service} on {entity_id} {kwargs}")
        
        if entity_id == "number.ev_charger_set_current" and "value" in kwargs:
            self.current = kwargs["value"]
            self.set_state(entity_id, kwargs["value"])
            print(f"  ⚡ Charger current set to {self.current}A")
        
        return True

def test_scenario(scenario_name, api, config, duration_minutes=5):
    """Run a test scenario."""
    print(f"\n{'='*60}")
    print(f"🧪 Test: {scenario_name}")
    print(f"{'='*60}")
    
    # Import app modules
    sys.path.insert(0, 'app')
    from power_calculator import PowerManager
    from charger_controller import ChargerController
    
    # Create managers
    power_mgr = PowerManager(api, config)
    charger_ctrl = ChargerController(api, config["charger"])
    
    # Run for specified duration
    update_interval = config["control"]["update_interval"]
    iterations = (duration_minutes * 60) // update_interval
    
    print(f"Running for {duration_minutes} minutes ({iterations} iterations)")
    
    for i in range(iterations):
        elapsed = i * update_interval
        
        # Get power calculation
        available_power = power_mgr.get_available_power()
        
        # Debug first iteration
        if i == 0:
            battery_soc = api.get_state("sensor.ss_battery_soc")
            battery_pwr = api.get_state("sensor.ss_battery_power")
            print(f"  🔍 Debug: Battery SOC={battery_soc}%, Power={battery_pwr}W")
        
        # Simulate battery discharge when EV load exceeds solar
        ev_load = api.current * 230  # Current * voltage
        total_load = float(api.get_state("sensor.total_load_power"))
        pv_power = float(api.get_state("sensor.total_pv_power"))
        house_load = total_load - ev_load
        
        net_power = pv_power - house_load - ev_load
        
        # Update battery power based on net
        if net_power < 0:
            # Battery discharging
            api.set_state("sensor.ss_battery_power", str(abs(net_power)))
        else:
            # Battery at 0W (full) or slightly charging
            api.set_state("sensor.ss_battery_power", "0")
        
        # Get charger status
        status = api.get_state("sensor.ev_charger_status")
        
        # Print status every 30 seconds
        if elapsed % 30 == 0:
            battery_power = api.get_state("sensor.ss_battery_power")
            print(f"\n⏱️  {elapsed}s | Status: {status}")
            print(f"  PV: {pv_power}W | House: {house_load:.0f}W | EV: {ev_load:.0f}W ({api.current}A)")
            print(f"  Battery: {battery_power}W | Available: {available_power:.0f}W")
        
        # Simulate control decision (match real logic)
        # When battery >95% and power ≤ 0, calculator returns large available power to probe up
        # When battery discharges, calculator reduces available power
        
        target_power = available_power
        current_power = ev_load
        power_diff = target_power - current_power
        
        # Hysteresis check
        hysteresis = config["control"]["hysteresis_watts"]
        
        if power_diff > hysteresis:
            # Can increase
            allowed = config["charger"]["allowed_currents"]
            idx = allowed.index(api.current) if api.current in allowed else 0
            if idx < len(allowed) - 1:
                new_current = allowed[idx + 1]
                print(f"  ⬆️  Increasing to {new_current}A (available: {available_power:.0f}W, using: {current_power:.0f}W, diff: +{power_diff:.0f}W)")
                charger_ctrl.set_current_step(new_current)
        
        elif power_diff < -hysteresis:
            # Need to decrease
            allowed = config["charger"]["allowed_currents"]
            idx = allowed.index(api.current) if api.current in allowed else 0
            if idx > 0:
                new_current = allowed[idx - 1]
                print(f"  ⬇️  Decreasing to {new_current}A (available: {available_power:.0f}W, using: {current_power:.0f}W, diff: {power_diff:.0f}W)")
                charger_ctrl.set_current_step(new_current)
        
        time.sleep(0.5)  # Speed up testing
    
    print(f"\n✅ Test complete!")
    print(f"Final current: {api.current}A")
    print(f"Final battery power: {api.get_state('sensor.ss_battery_power')}W")

def main():
    """Run local tests."""
    print("\n🔧 EVSE Manager - Local Testing")
    print("Testing control logic without Home Assistant\n")
    
    # Load configuration
    config = {
        "charger": {
            "name": "Test EVSE",
            "switch_entity": "switch.ev_charger",
            "current_entity": "number.ev_charger_set_current",
            "status_entity": "sensor.ev_charger_status",
            "allowed_currents": [6, 8, 10, 13, 16, 20, 24],
            "max_current": 24,
            "step_delay": 2,  # Faster for testing
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
            "inverter_max_power": 8000,
            "total_pv_entity": "sensor.total_pv_power",
            "total_load_entity": "sensor.total_load_power"
        },
        "control": {
            "mode": "auto",
            "update_interval": 5,
            "grace_period": 60,
            "power_smoothing_window": 30,
            "hysteresis_watts": 500
        },
        "log_level": "info"
    }
    
    # Create mock API
    api = MockHAAPI()
    
    # Test scenarios
    scenarios = [
        ("High Solar - Probing Upward", 2),
        # Add more scenarios here
    ]
    
    for name, duration in scenarios:
        test_scenario(name, api, config, duration)
        
        # Reset for next test
        api.current = 6
        api.set_state("number.ev_charger_set_current", "6")
        time.sleep(1)
    
    print("\n✅ All tests complete!")

if __name__ == "__main__":
    main()
