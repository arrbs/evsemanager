"""
Power Calculator Module
Calculates available excess power using different methods.
"""
import logging
from collections import deque
from typing import Optional, Dict
import time


class PowerCalculator:
    """Base class for power calculation."""
    
    def __init__(self, ha_api, config: dict):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ha_api = ha_api
        self.config = config
        
        # Smoothing
        self.smoothing_window = config.get('power_smoothing_window', 60)
        self.power_history = deque(maxlen=self.smoothing_window)
        self.last_update = None
    
    def calculate_available_power(self) -> Optional[float]:
        """Calculate available excess power. Override in subclasses."""
        raise NotImplementedError
    
    def get_smoothed_power(self) -> Optional[float]:
        """Get time-weighted smoothed power value."""
        if not self.power_history:
            return None
        
        # Simple moving average for now
        # Could be enhanced with weighted average based on timestamps
        return sum(self.power_history) / len(self.power_history)
    
    def update(self) -> Optional[float]:
        """Update and return available power."""
        power = self.calculate_available_power()
        
        if power is not None:
            self.power_history.append(power)
            self.last_update = time.time()
            
            smoothed = self.get_smoothed_power()
            self.logger.debug(f"Power: {power}W (smoothed: {smoothed}W)")
            return smoothed
        
        return None


class DirectPowerCalculator(PowerCalculator):
    """Method A: Direct excess power sensor."""
    
    def __init__(self, ha_api, config: dict):
        super().__init__(ha_api, config)
        self.excess_power_entity = config['sensors']['excess_power_entity']
        self.logger.info(f"Using direct power method: {self.excess_power_entity}")
    
    def calculate_available_power(self) -> Optional[float]:
        """Get power directly from excess power sensor."""
        power = self.ha_api.get_state(self.excess_power_entity)
        
        if power is None:
            self.logger.warning("Could not read excess power sensor")
            return None
        
        return float(power)


class GridExportCalculator(PowerCalculator):
    """Method B: Calculate from grid export."""
    
    def __init__(self, ha_api, config: dict):
        super().__init__(ha_api, config)
        self.grid_power_entity = config['sensors']['grid_power_entity']
        self.logger.info(f"Using grid export method: {self.grid_power_entity}")
    
    def calculate_available_power(self) -> Optional[float]:
        """Calculate available power from grid export (negative = exporting)."""
        grid_power = self.ha_api.get_state(self.grid_power_entity)
        
        if grid_power is None:
            self.logger.warning("Could not read grid power sensor")
            return None
        
        grid_power = float(grid_power)
        
        # Negative values mean we're exporting (excess available)
        # Positive values mean we're importing (no excess)
        available = -grid_power if grid_power < 0 else 0
        
        self.logger.debug(f"Grid power: {grid_power}W, Available: {available}W")
        return available


class BatteryCalculator(PowerCalculator):
    """Method C: Calculate from battery charging rate and state."""
    
    def __init__(self, ha_api, config: dict):
        super().__init__(ha_api, config)
        self.battery_soc_entity = config['sensors']['battery_soc_entity']
        self.battery_power_entity = config['sensors']['battery_power_entity']
        self.high_soc = config['sensors'].get('battery_high_soc', 95)
        self.priority_soc = config['sensors'].get('battery_priority_soc', 80)
        self.target_discharge_min = config['sensors'].get('battery_target_discharge_min', 0)
        self.target_discharge_max = config['sensors'].get('battery_target_discharge_max', 1500)
        
        # Optional: use grid export sensor as fallback when battery is full
        self.grid_power_entity = config['sensors'].get('grid_power_entity')
        
        self.logger.info(f"Using battery method: SOC={self.battery_soc_entity}, Power={self.battery_power_entity}")
        self.logger.info(f"High SOC threshold: {self.high_soc}%, Priority: {self.priority_soc}%")
        if self.grid_power_entity:
            self.logger.info(f"Grid sensor available for enhanced detection: {self.grid_power_entity}")
    
    def calculate_available_power(self) -> Optional[float]:
        """
        Calculate available power based on battery state.
        
        Logic:
        - SOC < priority_soc: No excess (battery priority)
        - SOC < high_soc: Use battery charging rate as available power
        - SOC >= high_soc: Try to maintain mild discharge (target_discharge range)
        """
        soc = self.ha_api.get_state(self.battery_soc_entity)
        battery_power = self.ha_api.get_state(self.battery_power_entity)
        
        if soc is None or battery_power is None:
            self.logger.warning("Could not read battery sensors")
            return None
        
        soc = float(soc)
        battery_power = float(battery_power)
        
        # Negative battery power = charging (excess available)
        # Positive battery power = discharging (consuming stored energy)
        
        if soc < self.priority_soc:
            # Battery has priority - no excess for car
            self.logger.debug(f"Battery priority active (SOC {soc}% < {self.priority_soc}%)")
            return 0.0
        
        elif soc < self.high_soc:
            # Battery still charging - available power is what's going into battery
            if battery_power < 0:
                available = -battery_power
                self.logger.debug(f"Battery charging at {-battery_power}W (SOC {soc}%)")
                return available
            else:
                # Battery discharging but below high threshold - reduce consumption
                self.logger.debug(f"Battery discharging {battery_power}W (SOC {soc}%)")
                return 0.0
        
        else:
            # SOC >= high_soc: Simple probing logic
            # 1. Battery >95%: step up until it starts discharging
            # 2. Normal: keep battery roughly stable (small discharge ok)
            
            if soc > 95:
                # Battery full - probe upward until it discharges
                # When battery at 0W, PV may be curtailed - keep probing to find actual solar limit
                if battery_power <= 0:
                    # Not discharging - either charging or at 0W (curtailed PV)
                    # Keep stepping up to discover actual solar capacity
                    available = 5000  # Signal: keep stepping up
                    if battery_power < -100:
                        self.logger.info(
                            f"Battery >95% charging {-battery_power}W - probing upward"
                        )
                else:
                    # Battery discharging - we've exceeded actual solar, reduce EVSE
                    available = self.target_discharge_max - battery_power
                    self.logger.info(
                        f"Battery discharging {battery_power}W - exceeded solar limit, reducing"
                    )
                return available
            
            else:
                # Normal mode - keep battery roughly stable
                # Target: small discharge (0-1500W)
                if battery_power < -500:
                    # Charging too much - can increase EVSE
                    available = -battery_power + self.target_discharge_max
                    self.logger.info(
                        f"Battery charging {-battery_power}W - can increase EVSE"
                    )
                elif battery_power <= self.target_discharge_max:
                    # In target range - small adjustments
                    available = self.target_discharge_max - battery_power
                    self.logger.info(
                        f"Battery at {battery_power}W - in target range"
                    )
                else:
                    # Discharging too much - need to decrease EVSE
                    available = self.target_discharge_max - battery_power  # Will be negative
                    self.logger.info(
                        f"Battery discharging {battery_power}W - need to decrease EVSE"
                    )
                return available


class PowerManager:
    """
    Manages power calculation with rapid response to changes.
    Implements PID-like control for smooth adjustments.
    """
    
    def __init__(self, ha_api, config: dict):
        self.logger = logging.getLogger(__name__)
        self.ha_api = ha_api
        self.config = config
        
        # Select calculator based on method
        method = config.get('power_method', 'battery')
        
        if method == 'direct':
            self.calculator = DirectPowerCalculator(ha_api, config)
        elif method == 'grid':
            self.calculator = GridExportCalculator(ha_api, config)
        elif method == 'battery':
            self.calculator = BatteryCalculator(ha_api, config)
        else:
            raise ValueError(f"Unknown power method: {method}")
        
        self.method = method
        self.logger.info(f"Power method: {method}")
        
        # Control parameters
        self.hysteresis = config['control'].get('hysteresis_watts', 500)
        
        # Additional sensors for monitoring
        self.inverter_power_entity = config['sensors'].get('inverter_power_entity')
        self.inverter_max_power = config['sensors'].get('inverter_max_power', 8000)
        
        # State
        self.last_available_power = None
        self.last_change_time = None
        
        # Sensor delay compensation
        self.sensor_delay_seconds = config['control'].get('sensor_delay_seconds', 60)
        self.predictive_enabled = config['control'].get('predictive_model_enabled', True)
        self.predictive_margin = config['control'].get('predictive_safety_margin', 0.15)
        self.commanded_current = 0  # Last current we commanded to charger
        self.command_time = None
        
        if self.predictive_enabled:
            self.logger.info(f"Predictive compensation enabled: {self.sensor_delay_seconds}s delay, {self.predictive_margin*100:.0f}% safety margin")
        
        self.logger.info(f"Hysteresis: {self.hysteresis}W")
    
    def set_commanded_current(self, amps: float):
        """
        Update the commanded current for predictive compensation.
        Call this whenever you change the charger current setting.
        
        Args:
            amps: Current commanded to charger
        """
        self.commanded_current = amps
        self.command_time = time.time()
        self.logger.debug(f"Commanded current updated: {amps}A")
    
    def get_predicted_ev_load(self, voltage: float = 230) -> float:
        """
        Estimate actual EV load based on commanded current.
        Accounts for sensor delay where sensors haven't caught up yet.
        
        Args:
            voltage: Line voltage (default 230V)
            
        Returns:
            Predicted actual EV power consumption (W)
        """
        if not self.predictive_enabled or self.command_time is None:
            return 0
        
        # Check if we're still within the sensor delay window
        time_since_command = time.time() - self.command_time
        if time_since_command > self.sensor_delay_seconds:
            # Sensors should have caught up by now
            return 0
        
        # Predict actual power consumption
        predicted_power = self.commanded_current * voltage
        
        # Apply safety margin (assume slightly higher consumption)
        predicted_power *= (1.0 + self.predictive_margin)
        
        self.logger.debug(f"Predicted EV load: {predicted_power:.0f}W (commanded {self.commanded_current}A, {time_since_command:.0f}s ago)")
        return predicted_power
    
    def get_available_power(self, voltage: float = 230, reported_ev_load: float = 0) -> Optional[float]:
        """
        Get current available power with smoothing and predictive compensation.
        
        Args:
            voltage: Line voltage for EV load prediction
            reported_ev_load: Current EV load from sensors (W)
            
        Returns:
            Available power in watts, compensated for sensor delay
        """
        raw_power = self.calculator.update()
        
        if raw_power is not None:
            # Check for rapid changes in RAW power before compensation
            # This detects actual load changes (like kettle turning on)
            if self.last_available_power is not None:
                delta = raw_power - self.last_available_power
                
                # Large drop in available power (e.g., kettle turned on)
                if delta < -1000:
                    self.logger.warning(f"Rapid power drop detected: {delta}W")
                    # Skip compensation and return raw power for immediate response
                    self.last_available_power = raw_power
                    return raw_power
            
            # Apply predictive compensation
            power = raw_power
            predicted_ev = self.get_predicted_ev_load(voltage)
            if predicted_ev > 0:
                # Calculate the underreported amount (difference between actual and reported)
                underreported = predicted_ev - reported_ev_load
                # Subtract only the underreported amount from available power
                power = raw_power - underreported
                self.logger.debug(f"Power compensation: {raw_power:.0f}W - ({predicted_ev:.0f}W predicted - {reported_ev_load:.0f}W reported) = {power:.0f}W")
            
            self.last_available_power = raw_power  # Track raw power for delta detection
        
        return power
    
    def get_target_current(self, charger_controller, current_amps: float) -> Optional[float]:
        """
        Calculate target current based on available power with hysteresis.
        
        Args:
            charger_controller: ChargerController instance
            current_amps: Current charging current
            
        Returns:
            Target current in amps, or None if no change needed
        """
        available_power = self.get_available_power()
        
        if available_power is None:
            return None
        
        # Convert current amps to watts
        current_watts = charger_controller.amps_to_watts(current_amps)
        
        # Calculate power difference
        power_diff = available_power - current_watts
        
        # Apply hysteresis - only adjust if change is significant
        if abs(power_diff) < self.hysteresis:
            self.logger.info(f"Power diff {power_diff:.1f}W within hysteresis {self.hysteresis}W (available={available_power:.1f}W, current={current_watts:.1f}W)")
            return None
        
        # Calculate target power
        target_watts = current_watts + power_diff
        
        # Clamp to charger limits
        min_watts = charger_controller.get_min_power()
        max_watts = charger_controller.get_max_power()
        
        target_watts = max(min_watts, min(max_watts, target_watts))
        
        # Convert to amps
        target_amps = charger_controller.watts_to_amps(target_watts)
        
        self.logger.debug(f"Available: {available_power}W, Current: {current_watts}W, Target: {target_watts}W ({target_amps}A)")
        
        return target_amps
    
    def check_inverter_limit(self) -> bool:
        """
        Check if inverter is approaching or exceeding its limit.
        
        Returns:
            True if inverter is maxed out and we're likely importing from grid
        """
        if not self.inverter_power_entity:
            return False
        
        inverter_power = self.ha_api.get_state(self.inverter_power_entity)
        
        if inverter_power is None:
            return False
        
        inverter_power = float(inverter_power)
        
        # Check if we're near or over the limit (within 5%)
        limit_threshold = self.inverter_max_power * 0.95
        
        if inverter_power >= limit_threshold:
            self.logger.warning(f"Inverter at/near limit: {inverter_power}W / {self.inverter_max_power}W")
            return True
        
        return False
    
    def should_stop_charging(self, charger_controller) -> bool:
        """
        Determine if charging should be stopped entirely.
        
        Reasons to stop:
        - Available power below minimum charger power
        - Inverter maxed out and importing from grid
        
        Returns:
            True if charging should be stopped
        """
        available = self.get_available_power()
        
        if available is None:
            return False
        
        min_power = charger_controller.get_min_power()
        
        # Not enough power to charge at minimum
        if available < min_power:
            self.logger.info(f"Available power {available}W below minimum {min_power}W")
            return True
        
        # Inverter maxed out
        if self.check_inverter_limit():
            # Check if we're actually importing
            if self.method == 'grid':
                grid_power = self.ha_api.get_state(self.config['sensors']['grid_power_entity'])
                if grid_power is not None and float(grid_power) > 100:
                    self.logger.warning("Inverter maxed and importing from grid")
                    return True
        
        return False
