"""
Solar/Battery/Grid simulation engine.
Generates realistic power profiles for testing the EVSE manager.
"""

import math
from typing import Dict, Any
from datetime import datetime, time


class PowerSimulator:
    """Simulates solar, battery, and grid power flows."""
    
    def __init__(self, scenario: str = "sunny_day"):
        """
        Initialize the power simulator.
        
        Args:
            scenario: Type of scenario to simulate
                - sunny_day: Clear sky, strong solar production
                - cloudy_day: Variable solar with frequent clouds
                - morning_ramp: Early morning solar ramp-up
                - afternoon_fade: Late afternoon solar decline
                - partly_cloudy: Mix of sun and clouds
        """
        self.scenario = scenario
        self.time_offset = 0  # Simulated seconds since midnight
        
        # System parameters
        self.inverter_max_power = 8000  # W
        self.battery_capacity = 10000  # Wh (10 kWh)
        self.battery_soc = 50  # %
        self.house_base_load = 500  # W baseline load
        
        # Weather parameters (adjusted by scenario)
        self.cloud_factor = 1.0  # Multiplier for solar (1.0 = clear)
        self.cloud_frequency = 0.0  # How often clouds pass
        
        # Load spike events (time_in_seconds, additional_watts, duration_seconds)
        self.load_events = []
        self.active_load_spikes = []  # Currently active load increases
        
        self._setup_scenario()
        
    def _setup_scenario(self):
        """Configure scenario-specific parameters."""
        if self.scenario == "sunny_day":
            self.cloud_factor = 1.0
            self.cloud_frequency = 0.0
            self.battery_soc = 85
            self.time_offset = 9 * 3600  # Start at 9 AM (good solar)
        elif self.scenario == "cloudy_day":
            self.cloud_factor = 0.4
            self.cloud_frequency = 0.3
            self.battery_soc = 60
            self.time_offset = 9 * 3600  # Start at 9 AM
        elif self.scenario == "morning_ramp":
            self.time_offset = 6 * 3600  # Start at 6 AM
            self.cloud_factor = 0.9
            self.battery_soc = 40
        elif self.scenario == "afternoon_fade":
            self.time_offset = 15 * 3600  # Start at 3 PM
            self.cloud_factor = 0.8
            self.battery_soc = 95
        elif self.scenario == "partly_cloudy":
            self.cloud_factor = 0.7
            self.cloud_frequency = 0.15
            self.battery_soc = 70
            self.time_offset = 10 * 3600  # Start at 10 AM
            
    def get_time_of_day(self) -> float:
        """Get current hour of day (0-24)."""
        return (self.time_offset % 86400) / 3600
        
    def calculate_solar_irradiance(self) -> float:
        """
        Calculate solar irradiance based on time of day.
        Returns value 0-1 representing sun strength.
        """
        hour = self.get_time_of_day()
        
        # Solar elevation model (simplified)
        # Peak at solar noon (12:00), zero before 6 AM and after 6 PM
        if hour < 6 or hour > 18:
            return 0.0
            
        # Sine curve for solar elevation
        # Peak at noon (hour 12)
        normalized_hour = (hour - 6) / 12  # 0 at 6 AM, 1 at 6 PM
        irradiance = math.sin(normalized_hour * math.pi)
        
        return max(0, irradiance)
        
    def calculate_cloud_effect(self) -> float:
        """Calculate cloud coverage effect on solar."""
        if self.cloud_frequency == 0:
            return 1.0
            
        # Use sine waves to create passing clouds
        cloud_cycle = math.sin(self.time_offset / 300) * 0.5 + 0.5  # 5 min cycles
        
        # Random-looking clouds by combining multiple frequencies
        cloud_pattern = (
            math.sin(self.time_offset / 300) * 0.3 +
            math.sin(self.time_offset / 197) * 0.3 +
            math.sin(self.time_offset / 411) * 0.4
        )
        
        # Convert to 0-1 range
        cloud_pattern = (cloud_pattern + 1) / 2
        
        # Apply frequency (how often clouds occur)
        if cloud_pattern > (1 - self.cloud_frequency):
            # Cloud passing - reduce solar by 50-90%
            reduction = 0.1 + (cloud_pattern - (1 - self.cloud_frequency)) / self.cloud_frequency * 0.4
            return reduction
        else:
            return 1.0
            
    def calculate_pv_power(self) -> float:
        """Calculate total PV production."""
        irradiance = self.calculate_solar_irradiance()
        cloud_effect = self.calculate_cloud_effect()
        
        # Max PV production (matching inverter capacity)
        max_pv = 8000  # W
        
        pv_power = max_pv * irradiance * cloud_effect * self.cloud_factor
        
        return max(0, pv_power)
        
    def add_load_event(self, start_time: int, power: float, duration: int, description: str = ""):
        """
        Add a sudden load increase event.
        
        Args:
            start_time: When to start (seconds from simulation start)
            power: Additional power draw in watts
            duration: How long the load lasts (seconds)
            description: Description of the load (e.g., "AC unit starts")
        """
        self.load_events.append({
            'start': start_time,
            'power': power,
            'duration': duration,
            'description': description
        })
        
    def _update_active_load_spikes(self):
        """Update currently active load spike events."""
        # Add new events that should start
        for event in self.load_events:
            if event['start'] <= self.time_offset < event['start'] + event['duration']:
                # Check if already active
                if not any(e['start'] == event['start'] for e in self.active_load_spikes):
                    self.active_load_spikes.append(event)
                    
        # Remove expired events
        self.active_load_spikes = [
            e for e in self.active_load_spikes 
            if self.time_offset < e['start'] + e['duration']
        ]
        
    def get_active_load_spikes_power(self) -> float:
        """Get total additional power from active load spikes."""
        return sum(e['power'] for e in self.active_load_spikes)
    
    def calculate_house_load(self) -> float:
        """Calculate house load with time-of-day variations and sudden load events."""
        hour = self.get_time_of_day()
        
        # Base load
        load = self.house_base_load
        
        # Morning peak (7-9 AM): +800W
        if 7 <= hour <= 9:
            load += 800 * math.sin((hour - 7) / 2 * math.pi)
            
        # Evening peak (18-21): +1200W
        if 18 <= hour <= 21:
            load += 1200 * math.sin((hour - 18) / 3 * math.pi)
            
        # Midday: +300W
        if 11 <= hour <= 14:
            load += 300
            
        # Add some randomness (±10%)
        variation = math.sin(self.time_offset / 137) * 0.1
        load *= (1 + variation)
        
        # Add sudden load spikes (appliances starting, etc.)
        self._update_active_load_spikes()
        load += self.get_active_load_spikes_power()
        
        return max(200, load)
        
    def update_battery_soc(self, battery_power: float, dt: float):
        """
        Update battery state of charge.
        
        Args:
            battery_power: Battery power (positive = charging, negative = discharging)
            dt: Time step in seconds
        """
        # Energy change in Wh
        energy_change = (battery_power * dt) / 3600
        
        # Update SoC
        soc_change = (energy_change / self.battery_capacity) * 100
        self.battery_soc = max(0, min(100, self.battery_soc + soc_change))
        
    def get_state(self, ev_load: float = 0, dt: float = 5) -> Dict[str, Any]:
        """
        Get current system state.
        
        Args:
            ev_load: Current EV charger load (W)
            dt: Time step for battery SoC calculation
            
        Returns:
            Dictionary with all sensor values
        """
        pv_power = self.calculate_pv_power()
        house_load = self.calculate_house_load()
        
        # Total load including EV if charging
        total_load = house_load + ev_load
        
        # Calculate battery behavior
        # If PV > Load: Battery charges (or charges slower if already high SoC)
        # If PV < Load: Battery discharges (or grid imports if SoC too low)
        
        net_power = pv_power - total_load
        
        # Battery charging logic
        if self.battery_soc < 20:
            # Low SoC: import from grid to charge battery + loads
            battery_power = min(3000, -net_power + 2000)  # Try to charge at 2kW
            grid_power = total_load - pv_power + battery_power
        elif self.battery_soc > 95:
            # High SoC: excess goes to grid (or EV could take more)
            if net_power > 0:
                battery_power = min(1000, net_power)  # Slow charge when nearly full
            else:
                battery_power = max(-3000, net_power)  # Discharge to cover deficit
            grid_power = -(pv_power - total_load - battery_power)
        else:
            # Normal operation: battery balances the system
            if net_power > 0:
                # Excess solar: charge battery
                battery_power = min(5000, net_power)  # Max 5kW charge
                grid_power = -(net_power - battery_power)  # Export remainder
            else:
                # Deficit: discharge battery
                battery_power = max(-5000, net_power)  # Max 5kW discharge
                if abs(net_power) > 5000:
                    # Battery can't cover it all: import from grid
                    grid_power = abs(net_power) - 5000
                else:
                    grid_power = 0
                    
        # Update battery SoC
        self.update_battery_soc(battery_power, dt)
        
        # Inverter power calculation:
        # - When battery discharging: inverter_power = PV + battery discharge
        # - When battery charging: inverter_power = PV only (battery charging doesn't flow through inverter to AC side)
        if battery_power < 0:  # Discharging (negative = discharge)
            inverter_power = pv_power + abs(battery_power)
        else:  # Charging or idle
            inverter_power = pv_power
            
        # Check if we're hitting inverter limits
        inverter_limited = inverter_power >= self.inverter_max_power
        
        return {
            'pv_power': round(pv_power, 1),
            'house_load': round(house_load, 1),
            'total_load': round(total_load, 1),
            'battery_power': round(battery_power, 1),
            'battery_soc': round(self.battery_soc, 1),
            'grid_power': round(grid_power, 1),
            'inverter_power': round(inverter_power, 1),
            'ev_load': round(ev_load, 1),
            'time_of_day': round(self.get_time_of_day(), 2),
            'irradiance': round(self.calculate_solar_irradiance(), 3),
            'inverter_limited': inverter_limited,
            'load_spikes': self.get_active_load_spikes_power(),
            'active_events': [e['description'] for e in self.active_load_spikes],
        }
        
    def advance_time(self, seconds: int):
        """Advance simulation time."""
        self.time_offset += seconds


class ChargerSimulator:
    """Simulates EV charger behavior."""
    
    def __init__(self, voltage: float = 230):
        """Initialize charger simulator."""
        self.voltage = voltage
        self.current = 0  # Current setting in amps
        self.is_on = False
        self.status = "available"  # available, waiting, charging, charged, fault
        self.actual_current = 0  # What charger is actually drawing
        self.ramp_rate = 0.5  # Amps per second ramp rate
        self.car_connected = False
        self.car_soc = 30  # %
        self.car_battery_capacity = 60000  # Wh (60 kWh)
        
    def connect_car(self, initial_soc: float = 30):
        """Connect a car to the charger."""
        self.car_connected = True
        self.car_soc = initial_soc
        self.status = "waiting"
        
    def disconnect_car(self):
        """Disconnect car."""
        self.car_connected = False
        self.is_on = False
        self.current = 0
        self.actual_current = 0
        self.status = "available"
        
    def set_current(self, amps: float):
        """Set target current."""
        self.current = amps
        
    def turn_on(self):
        """Turn charger on."""
        if self.car_connected:
            self.is_on = True
            if self.status == "waiting":
                self.status = "charging"
                
    def turn_off(self):
        """Turn charger off."""
        self.is_on = False
        if self.car_connected:
            self.status = "waiting"
        else:
            self.status = "available"
            
    def update(self, dt: float) -> float:
        """
        Update charger state and return actual power draw.
        
        Args:
            dt: Time step in seconds
            
        Returns:
            Actual power draw in watts
        """
        if not self.is_on or not self.car_connected:
            # Ramp down
            self.actual_current = max(0, self.actual_current - self.ramp_rate * dt)
            return 0
            
        # Ramp to target current
        if self.actual_current < self.current:
            self.actual_current = min(self.current, self.actual_current + self.ramp_rate * dt)
        elif self.actual_current > self.current:
            self.actual_current = max(self.current, self.actual_current - self.ramp_rate * dt)
            
        # Calculate power
        power = self.actual_current * self.voltage
        
        # Update car SoC
        energy = (power * dt) / 3600  # Wh
        soc_increase = (energy / self.car_battery_capacity) * 100
        self.car_soc = min(100, self.car_soc + soc_increase)
        
        # Check if charged
        if self.car_soc >= 99:
            self.status = "charged"
            
        return power
        
    def get_status(self) -> str:
        """Get charger status."""
        return self.status
