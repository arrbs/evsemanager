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
        
        self.logger.info(f"Using battery method: SOC={self.battery_soc_entity}, Power={self.battery_power_entity}")
        self.logger.info(f"High SOC threshold: {self.high_soc}%, Priority: {self.priority_soc}%")
    
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
            # SOC >= high_soc: Try to maintain target discharge
            # We want battery to discharge between target_discharge_min and target_discharge_max
            # This tells us how much excess solar is really available
            
            if battery_power < 0:
                # Still charging - we have lots of excess
                # All charging power is excess, plus we want to shift to mild discharge
                available = -battery_power + self.target_discharge_max
                self.logger.debug(f"Battery charging at {-battery_power}W (SOC {soc}% high) - targeting discharge")
                return available
            
            elif battery_power < self.target_discharge_min:
                # Not discharging enough - we have excess available
                # We want to increase car load to push battery into target discharge range
                available = self.target_discharge_max - battery_power
                self.logger.debug(f"Battery discharge {battery_power}W too low - available: {available}W")
                return available
            
            elif battery_power > self.target_discharge_max:
                # Discharging too much - reduce car load
                # This is actually negative "available" power
                deficit = battery_power - self.target_discharge_max
                self.logger.debug(f"Battery discharge {battery_power}W too high - need to reduce: {deficit}W")
                return -deficit
            
            else:
                # In target range - maintain current level
                self.logger.debug(f"Battery discharge {battery_power}W in target range")
                return 0.0


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
        
        self.logger.info(f"Hysteresis: {self.hysteresis}W")
    
    def get_available_power(self) -> Optional[float]:
        """Get current available power with smoothing."""
        power = self.calculator.update()
        
        if power is not None:
            # Check for rapid changes that need immediate response
            if self.last_available_power is not None:
                delta = power - self.last_available_power
                
                # Large drop in available power (e.g., kettle turned on)
                if delta < -1000:
                    self.logger.warning(f"Rapid power drop detected: {delta}W")
                    # Return raw power for immediate response
                    self.last_available_power = power
                    return power
            
            self.last_available_power = power
        
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
            self.logger.debug(f"Power diff {power_diff}W within hysteresis {self.hysteresis}W")
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
