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
        control_config = config.get('control', {})

        # Smoothing (support time or sample-based windows)
        update_interval = max(1, control_config.get('update_interval', 5))
        configured_seconds = control_config.get('power_smoothing_window_seconds')
        configured_samples = control_config.get('power_smoothing_window')

        if configured_seconds is not None:
            self.smoothing_window_seconds = max(5, configured_seconds)
        elif configured_samples is not None:
            self.smoothing_window_seconds = max(5, configured_samples * update_interval)
        else:
            # Default to ~30 seconds of history for responsive behavior
            self.smoothing_window_seconds = 30

        # Keep sample fallback for environments that prefer sample counts
        if configured_samples is not None:
            self.smoothing_window_samples = max(1, configured_samples)
        else:
            derived_samples = max(1, int(round(self.smoothing_window_seconds / update_interval)))
            self.smoothing_window_samples = derived_samples
        self.power_history = deque()
        self.last_update = None

    def _trim_history(self, now: float):
        """Trim stored samples to respect smoothing configuration."""
        if self.smoothing_window_seconds:
            while self.power_history and (now - self.power_history[0][0]) > self.smoothing_window_seconds:
                self.power_history.popleft()
        else:
            while len(self.power_history) > self.smoothing_window_samples:
                self.power_history.popleft()
    
    def calculate_available_power(self) -> Optional[float]:
        """Calculate available excess power. Override in subclasses."""
        raise NotImplementedError
    
    def get_smoothed_power(self) -> Optional[float]:
        """Get time-weighted smoothed power value."""
        if not self.power_history:
            return None
        
        # Simple moving average using stored samples
        total = sum(sample[1] for sample in self.power_history)
        return total / len(self.power_history)
    
    def update(self, current_ev_watts: float = 0, for_display: bool = False) -> Optional[float]:
        """Update and return available power.
        
        Args:
            current_ev_watts: Current EV power consumption
            for_display: If True, calculate for display (excluding EV from load)
        """
        power = self.calculate_available_power(current_ev_watts, for_display)
        
        if power is not None:
            now = time.time()
            self.power_history.append((now, power))
            self._trim_history(now)
            self.last_update = now
            
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
        self.battery_power_charging_positive = config['sensors'].get('battery_power_charging_positive', False)
        self.high_soc = config['sensors'].get('battery_high_soc', 95)
        self.priority_soc = config['sensors'].get('battery_priority_soc', 80)
        self.target_discharge_min = config['sensors'].get('battery_target_discharge_min', 0)
        self.target_discharge_max = config['sensors'].get('battery_target_discharge_max', 1500)
        
        # Optional: use grid export sensor as fallback when battery is full
        self.grid_power_entity = config['sensors'].get('grid_power_entity')
        
        self.logger.info(
            f"Using battery method: SOC={self.battery_soc_entity}, Power={self.battery_power_entity}"
        )
        direction = "positive" if self.battery_power_charging_positive else "negative"
        self.logger.info(f"Battery charging reported as {direction} power")
        self.logger.info(f"High SOC threshold: {self.high_soc}%, Priority: {self.priority_soc}%")
        if self.grid_power_entity:
            self.logger.info(f"Grid sensor available for enhanced detection: {self.grid_power_entity}")
    
    def _normalize_battery_power(self, battery_power: float) -> float:
        """Convert raw sensor value so positive means discharging."""
        return -battery_power if self.battery_power_charging_positive else battery_power

    def calculate_available_power(self, current_ev_watts: float = 0, for_display: bool = False) -> Optional[float]:
        """
        Calculate excess solar power available for EV charging.
        
        Formula: PV - House Load (excluding EV) = Excess available for EV
        
        Note: The house load sensor includes the car's consumption. So for display:
          Excess = PV - (House Load - Car Load)
        
        For control decisions, we use PV - Total Load to see the current margin.
        
        Args:
            current_ev_watts: Current EV power consumption (to subtract from house load)
            for_display: If True, exclude EV from load for visualization
        
        Logic:
        - SOC < priority_soc: No excess (battery has priority)
        - SOC ≥ priority_soc: Use PV - Load formula
        - SOC ≥ 95%: Allow moderate battery discharge as bonus
        """
        soc = self.ha_api.get_state(self.battery_soc_entity)
        battery_power = self.ha_api.get_state(self.battery_power_entity)
        
        if soc is None or battery_power is None:
            self.logger.warning("Could not read battery sensors")
            return None
        
        soc = float(soc)
        battery_power = float(battery_power)
        normalized_power = self._normalize_battery_power(battery_power)
        
        # normalized_power: positive = discharging, negative = charging
        
        if soc < self.priority_soc:
            # Battery has priority - no excess for car
            self.logger.debug(f"Battery priority active (SOC {soc}% < {self.priority_soc}%)")
            return 0.0
        
        # Calculate excess from PV and Load sensors
        total_pv_entity = self.config['sensors'].get('total_pv_entity')
        total_load_entity = self.config['sensors'].get('total_load_entity')
        
        if total_pv_entity and total_load_entity:
            pv_power = self.ha_api.get_state(total_pv_entity)
            load_power = self.ha_api.get_state(total_load_entity)
            
            if pv_power is not None and load_power is not None:
                pv_power = float(pv_power)
                load_power = float(load_power)
                
                # House load includes the car's consumption
                # For display: show excess available = PV - (Load - Car)
                # For control: show current margin = PV - Load (including car)
                if for_display and current_ev_watts > 0:
                    # Subtract car from load to show true available excess
                    house_only_load = load_power - current_ev_watts
                    excess = pv_power - house_only_load
                    self.logger.debug(
                        f"Display: PV {pv_power:.0f}W - (Load {load_power:.0f}W - EV {current_ev_watts:.0f}W) = {excess:.0f}W"
                    )
                else:
                    # Control decision: use total load including car
                    excess = pv_power - load_power
                    self.logger.debug(
                        f"Control: PV {pv_power:.0f}W - Load {load_power:.0f}W = {excess:.0f}W margin"
                    )
                
                # When battery is full (≥95%), allow moderate discharge
                if soc >= 95 and normalized_power > 0 and normalized_power <= self.target_discharge_max:
                    excess += normalized_power
                    self.logger.debug(f"Adding battery discharge {normalized_power:.0f}W")
                
                return max(0, excess)
        
        # Fallback: if PV/Load sensors not available, use battery power as proxy
        self.logger.warning("PV/Load sensors not configured - using battery power fallback")
        if normalized_power < 0:
            # Battery charging - available power is what's going in
            return -normalized_power
        else:
            # Battery discharging - no excess available
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
    
    def get_available_power(self, voltage: float = 230, current_ev_load: float = 0, 
                           for_display: bool = False) -> Optional[float]:
        """
        Get current available power for EV charging.
        
        The key insight: if the EV is already drawing power, we need to add that back
        to determine the TOTAL power budget available for the EV. For example:
        - Battery charging at 1.7 kW (raw available)
        - EV currently drawing 1.3 kW
        - Total available for EV = 1.7 + 1.3 = 3.0 kW
        
        This prevents the system from thinking there's "insufficient power" when
        the EV is already successfully charging.
        
        Args:
            voltage: Line voltage for EV load prediction (unused now)
            current_ev_load: Current EV power draw in watts
            
        Returns:
            Total available power budget for EV charging
        """
        # Get power from calculator
        raw_power = self.calculator.update(current_ev_watts=current_ev_load, for_display=for_display)
        
        if raw_power is not None:
            # Check for rapid changes indicating external load changes
            if self.last_available_power is not None:
                delta = raw_power - self.last_available_power
                
                # Large drop in available power (e.g., kettle turned on)
                if delta < -1000:
                    self.logger.warning(f"Rapid power drop detected: {delta}W")
            
            self.last_available_power = raw_power
            
            # For display: return raw (already excludes EV from load)
            if for_display:
                return raw_power
            
            # For control: add current EV load to margin to get total budget
            total_budget = raw_power + current_ev_load
            
            if current_ev_load > 100:
                self.logger.debug(
                    f"Budget: {raw_power:.0f}W margin + {current_ev_load:.0f}W current = {total_budget:.0f}W total"
                )
            
            return total_budget
        else:
            return 0.0 if for_display else (current_ev_load if current_ev_load > 0 else 0.0)
    
    def get_target_current(self, charger_controller, current_amps: float) -> Optional[float]:
        """
        Calculate target current based on available power with hysteresis.
        
        Args:
            charger_controller: ChargerController instance
            current_amps: Current charging current
            
        Returns:
            Target current in amps, or None if no change needed
        """
        # Convert current amps to watts
        current_watts = charger_controller.amps_to_watts(current_amps)
        
        # Get available power considering current EV load
        available_power = self.get_available_power(current_ev_load=current_watts)
        
        if available_power is None:
            return None
        
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

    def get_power_history(self, samples: int = 60) -> list[float]:
        """Return recent raw available-power samples for visualization."""
        try:
            history = list(self.calculator.power_history)
        except AttributeError:
            return []
        if samples > 0:
            history = history[-samples:]
        return [value for _, value in history]

    def set_battery_priority_soc(self, value: int):
        """Update the battery priority SOC threshold when battery method is active."""
        if self.method == 'battery' and hasattr(self.calculator, 'priority_soc'):
            self.calculator.priority_soc = value
            self.logger.info(f"Battery priority SOC updated to {value}%")
    
    def should_stop_charging(self, charger_controller) -> bool:
        """
        Determine if charging should be stopped entirely.
        
        Reasons to stop:
        - Available power below minimum charger power
        - Inverter maxed out and importing from grid
        
        Returns:
            True if charging should be stopped
        """
        # Get current EV load to calculate total available
        current_amps = charger_controller.get_current() or 0
        current_watts = charger_controller.amps_to_watts(current_amps)
        available = self.get_available_power(current_ev_load=current_watts)
        
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
