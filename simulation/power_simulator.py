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
        self.zero_export = False  # If True, no grid export allowed
        
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
        elif self.scenario == "full_day_with_sunset":
            self.time_offset = 6 * 3600  # Start at 6 AM
            self.cloud_factor = 0.95
            self.cloud_frequency = 0.02  # Mostly clear
            self.battery_soc = 50
        elif self.scenario == "afternoon_fade":
            self.time_offset = 15 * 3600  # Start at 3 PM
            self.cloud_factor = 0.8
            self.battery_soc = 95
        elif self.scenario == "partly_cloudy":
            self.cloud_factor = 1.0  # Full sun periods for good charging
            self.cloud_frequency = 0.05  # Minimal clouds
            self.battery_soc = 96  # Battery full to avoid priority issues
            self.time_offset = 9 * 3600  # Start at 9 AM for more daylight
            
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
        
        # Base load: 300-500W depending on time of day
        load = 300 + 200 * abs(math.sin(hour / 24 * math.pi))
        
        # Morning peak (6-9 AM): +1500W average (kettle, toaster, etc.)
        if 6 <= hour <= 9:
            load += 1500 * math.sin((hour - 6) / 3 * math.pi)
            
        # Midday activity (11-14): +800W
        if 11 <= hour <= 14:
            load += 800 * math.sin((hour - 11) / 3 * math.pi)
            
        # Evening peak (17-22): +2000W (cooking, appliances)
        if 17 <= hour <= 22:
            load += 2000 * math.sin((hour - 17) / 5 * math.pi)
            
        # Add realistic variability - random bursts (washing machine, oven, etc.)
        # Create pseudo-random but repeatable spikes
        spike_pattern = (
            abs(math.sin(self.time_offset / 427)) * 
            abs(math.cos(self.time_offset / 731))
        )
        if spike_pattern > 0.85:  # 15% of the time, spike
            load += spike_pattern * 3000  # Up to 3000W spike
        
        # Add configured load events (from scenario)
        self._update_active_load_spikes()
        load += self.get_active_load_spikes_power()
        
        return max(300, load)
        
    def _update_battery_soc(self, battery_power: float, dt: float):
        """
        Update battery SoC based on power flow.
        
        Args:
            battery_power: Battery power internally (positive = charging, negative = discharging)
                          Note: Output is inverted to match HA convention
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
        pv_power_available = self.calculate_pv_power()  # Actual solar capacity
        house_load = self.calculate_house_load()
        
        # Total load including EV if charging
        total_load = house_load + ev_load
        
        # Calculate net power (can PV cover the load?)
        net_power = pv_power_available - total_load
        
        # For zero-export: PV sensor reading matches load when battery is full
        # (Inverter curtails excess, so app can't see it)
        # App must probe by increasing load to discover actual capacity
        if self.zero_export and self.battery_soc >= 100 and net_power > 0:
            # Battery full, excess solar: PV reading equals load (curtailed)
            pv_power = total_load
        else:
            # Normal operation: PV reading shows actual production
            pv_power = pv_power_available
        
        # Battery charging logic
        if self.battery_soc <= 31:
            # Low SoC: protect battery from deep discharge (use 31% to prevent going below 30%)
            if net_power > 0:
                # Have excess solar: charge battery with all of it
                battery_power = min(5000, net_power)  # Max 5kW charge
                grid_power = 0
            else:
                # Deficit: import from grid to cover loads, don't discharge battery
                battery_power = 0  # Don't discharge when low
                grid_power = total_load - pv_power  # Import what we need
        elif self.battery_soc > 95:
            # High SoC: battery nearly full
            # PV curtailment already handled above for zero-export systems
            if net_power > 0:
                # Excess solar: charge battery (if not already full)
                if self.battery_soc >= 100:
                    battery_power = 0  # Full battery can't charge
                    grid_power = 0 if self.zero_export else -net_power
                else:
                    battery_power = min(500, net_power)  # Slow charge when nearly full
                    grid_power = 0 if self.zero_export else -(net_power - battery_power)
            else:
                # Deficit: discharge battery to cover
                if self.zero_export:
                    # Discharge battery to cover deficit (no grid export/import)
                    battery_power = max(-5000, net_power)  # Max 5kW discharge
                    grid_power = 0
                else:
                    battery_power = max(-3000, net_power)  # Discharge to cover deficit
                    grid_power = -(pv_power - total_load - battery_power)
        else:
            # Normal operation: battery balances the system
            if net_power > 0:
                # Excess solar: charge battery
                battery_power = min(5000, net_power)  # Max 5kW charge
                
                if self.zero_export:
                    # Zero export mode: use battery to absorb all excess
                    battery_power = net_power  # Charge battery with all excess
                    grid_power = 0
                else:
                    # Normal mode: can export to grid
                    grid_power = -(net_power - battery_power)  # Export remainder
            else:
                # Deficit: discharge battery
                battery_power = max(-5000, net_power)  # Max 5kW discharge
                
                if self.zero_export:
                    # Zero export mode: battery must cover everything
                    if abs(battery_power) < abs(net_power):
                        # Battery can't cover deficit: need grid import
                        grid_power = abs(net_power) - abs(battery_power)
                    else:
                        grid_power = 0
                else:
                    # Normal mode: grid can help if needed
                    if abs(net_power) > 5000:
                        # Battery can't cover it all: import from grid
                        grid_power = abs(net_power) - 5000
                    else:
                        grid_power = 0
                    
        # Update battery SoC
        self._update_battery_soc(battery_power, dt)
        
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
            'battery_power': round(-battery_power, 1),  # Flip sign: negative = charging, positive = discharging
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
    
    def __init__(self, voltage: float = 230, sensor_delay: float = 60):
        """
        Initialize charger simulator.
        
        Args:
            voltage: Line voltage (230V for single-phase)
            sensor_delay: Delay in seconds before sensors reflect power changes (default 60s)
        """
        self.voltage = voltage
        self.current = 0  # Current setting in amps
        self.is_on = False
        self.status = "available"  # available, waiting, charging, charged, fault
        self.actual_current = 0  # What charger is actually drawing (real physical current)
        self.reported_current = 0  # What sensors report (delayed)
        self.ramp_rate = 0.5  # Amps per second ramp rate
        self.car_connected = False
        self.car_soc = 30  # %
        self.car_battery_capacity = 60000  # Wh (60 kWh)
        
        # Sensor delay simulation
        self.sensor_delay = sensor_delay  # Seconds of delay
        self.pending_change = None  # (target_current, time_remaining)
        self.change_start_current = 0  # Current when change started
        
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
        """
        Set target current. Creates a pending change that will be reflected
        in sensors after sensor_delay seconds.
        """
        self.current = amps
        
        # If there's a significant change, start the delay timer
        if abs(self.current - self.reported_current) > 0.5:  # More than 0.5A change
            self.pending_change = self.current
            self.change_start_current = self.reported_current
            self.pending_change_time = 0  # Time elapsed since change started
        
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
            Actual power draw in watts (what sensors report, which is delayed)
        """
        if not self.is_on or not self.car_connected:
            # Ramp down
            self.actual_current = max(0, self.actual_current - self.ramp_rate * dt)
            self.reported_current = self.actual_current
            return 0
            
        # Ramp to target current (this happens immediately in hardware)
        if self.actual_current < self.current:
            self.actual_current = min(self.current, self.actual_current + self.ramp_rate * dt)
        elif self.actual_current > self.current:
            self.actual_current = max(self.current, self.actual_current - self.ramp_rate * dt)
            
        # Update sensor delay simulation
        # The sensors take time to reflect the actual current
        if self.pending_change is not None:
            self.pending_change_time += dt
            
            # Gradually ramp the reported value over the delay period
            if self.pending_change_time >= self.sensor_delay:
                # Delay complete, sensors now show actual value
                self.reported_current = self.actual_current
                self.pending_change = None
            else:
                # Sensors are still catching up - linear interpolation
                progress = self.pending_change_time / self.sensor_delay
                self.reported_current = self.change_start_current + \
                    (self.actual_current - self.change_start_current) * progress
        else:
            # No pending change, sensors track actual (with small lag)
            self.reported_current = self.actual_current
            
        # Calculate power based on what sensors REPORT (delayed)
        # This is what Home Assistant sees
        reported_power = self.reported_current * self.voltage
        
        # But the ACTUAL power consumption affects the car battery
        actual_power = self.actual_current * self.voltage
        
        # Update car SoC based on ACTUAL power
        energy = (actual_power * dt) / 3600  # Wh
        soc_increase = (energy / self.car_battery_capacity) * 100
        self.car_soc = min(100, self.car_soc + soc_increase)
        
        # Check if charged
        if self.car_soc >= 99:
            self.status = "charged"
            
        # Return what sensors REPORT (this is what HA sees and affects power calculations)
        return reported_power
    
    def get_actual_power(self) -> float:
        """Get actual power consumption (not what sensors report)."""
        return self.actual_current * self.voltage
    
    def get_delay_info(self) -> Dict[str, Any]:
        """Get information about sensor delay state."""
        return {
            'actual_current': self.actual_current,
            'reported_current': self.reported_current,
            'pending_change': self.pending_change,
            'delay_progress': self.pending_change_time / self.sensor_delay if self.pending_change is not None else 1.0
        }
        
    def get_status(self) -> str:
        """Get charger status."""
        return self.status
