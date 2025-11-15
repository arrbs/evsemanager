"""
Charger Controller Module
Handles safe current adjustments with step delays and fault detection.
"""
import logging
import time
from enum import Enum
from typing import List, Optional
from datetime import datetime, timedelta


class ChargerStatus(Enum):
    """Charger status states."""
    CHARGING = "charging"
    WAITING = "waiting"
    AVAILABLE = "available"
    CHARGED = "charged"
    FAULT = "fault"
    UNKNOWN = "unknown"


class ChargerController:
    """Controls EVSE charger with safe step transitions."""
    
    def __init__(self, ha_api, config: dict):
        """
        Initialize charger controller.
        
        Args:
            ha_api: Home Assistant API client
            config: Charger configuration dict
        """
        self.logger = logging.getLogger(__name__)
        self.ha_api = ha_api
        
        # Configuration
        self.name = config.get('name', 'EVSE')
        self.switch_entity = config['switch_entity']
        self.current_entity = config['current_entity']
        self.status_entity = config['status_entity']
        self.allowed_currents = sorted(config['allowed_currents'])
        self.step_delay = config.get('step_delay', 10)
        self.voltage_entity = config.get('voltage_entity')
        self.default_voltage = config.get('default_voltage', 230)
        
        # State
        self.current_current = None
        self.target_current = None
        self.last_adjustment_time = None
        self.is_adjusting = False
        self.voltage = self.default_voltage
        
        self.logger.info(f"ChargerController initialized: {self.name}")
        self.logger.info(f"Allowed currents: {self.allowed_currents}A")
        self.logger.info(f"Step delay: {self.step_delay}s")
    
    def get_voltage(self) -> float:
        """Get current voltage from sensor or use default."""
        if self.voltage_entity:
            voltage = self.ha_api.get_state(self.voltage_entity)
            if voltage is not None:
                self.voltage = float(voltage)
                return self.voltage
        return self.default_voltage
    
    def amps_to_watts(self, amps: float) -> float:
        """Convert amps to watts using current voltage."""
        voltage = self.get_voltage()
        return amps * voltage
    
    def watts_to_amps(self, watts: float) -> float:
        """Convert watts to amps using current voltage."""
        voltage = self.get_voltage()
        return watts / voltage
    
    def get_status(self) -> ChargerStatus:
        """Get current charger status."""
        status_str = self.ha_api.get_state(self.status_entity)
        if status_str is None:
            return ChargerStatus.UNKNOWN
        
        status_lower = str(status_str).lower()
        
        if status_lower == "charging":
            return ChargerStatus.CHARGING
        elif status_lower == "waiting":
            return ChargerStatus.WAITING
        elif status_lower == "available":
            return ChargerStatus.AVAILABLE
        elif status_lower == "charged":
            return ChargerStatus.CHARGED
        elif status_lower == "fault":
            return ChargerStatus.FAULT
        else:
            self.logger.warning(f"Unknown charger status: {status_str}")
            return ChargerStatus.UNKNOWN
    
    def get_current(self) -> Optional[float]:
        """Get current charging current setting."""
        current = self.ha_api.get_state(self.current_entity)
        if current is not None:
            self.current_current = float(current)
            return self.current_current
        return None
    
    def is_on(self) -> bool:
        """Check if charger switch is on."""
        state = self.ha_api.get_state(self.switch_entity)
        return state == "on" if state is not None else False
    
    def turn_on(self) -> bool:
        """Turn charger on."""
        self.logger.info("Turning charger ON")
        return self.ha_api.call_service(
            "switch", "turn_on",
            entity_id=self.switch_entity
        )
    
    def turn_off(self) -> bool:
        """Turn charger off."""
        self.logger.info("Turning charger OFF")
        return self.ha_api.call_service(
            "switch", "turn_off",
            entity_id=self.switch_entity
        )
    
    def _find_nearest_allowed_current(self, target: float) -> int:
        """Find nearest allowed current to target."""
        if target < self.allowed_currents[0]:
            return self.allowed_currents[0]
        if target > self.allowed_currents[-1]:
            return self.allowed_currents[-1]
        
        # Find closest
        return min(self.allowed_currents, key=lambda x: abs(x - target))
    
    def _get_next_step(self, current: int, target: int) -> Optional[int]:
        """Get next step towards target current."""
        if current == target:
            return None
        
        if current < target:
            # Find next higher current
            next_currents = [c for c in self.allowed_currents if c > current]
            if next_currents:
                next_current = next_currents[0]
                # Don't overshoot target
                if next_current > target:
                    return target if target in self.allowed_currents else None
                return next_current
        else:
            # Find next lower current
            next_currents = [c for c in self.allowed_currents if c < current]
            if next_currents:
                next_current = next_currents[-1]
                # Don't undershoot target
                if next_current < target:
                    return target if target in self.allowed_currents else None
                return next_current
        
        return None
    
    def can_adjust_now(self) -> bool:
        """Check if enough time has passed since last adjustment."""
        if self.last_adjustment_time is None:
            return True
        
        elapsed = time.time() - self.last_adjustment_time
        return elapsed >= self.step_delay
    
    def set_current_step(self, target_amps: float, force: bool = False) -> bool:
        """
        Perform a single step towards target current.
        
        Args:
            target_amps: Target current in amps
            force: Force adjustment even if delay hasn't elapsed
            
        Returns:
            True if step was performed, False if waiting or done
        """
        # Get nearest allowed current
        target = self._find_nearest_allowed_current(target_amps)
        
        # Get current setting
        current = self.get_current()
        if current is None:
            self.logger.error("Could not read current setting")
            return False
        
        current_int = int(round(current))
        
        # Check if we're already at target
        if current_int == target:
            self.logger.debug(f"Already at target current: {target}A")
            return False
        
        # Check if we can adjust now
        if not force and not self.can_adjust_now():
            wait_time = self.step_delay - (time.time() - self.last_adjustment_time)
            self.logger.debug(f"Waiting {wait_time:.1f}s before next adjustment")
            return False
        
        # Check charger status
        status = self.get_status()
        if status == ChargerStatus.FAULT:
            self.logger.error("Charger in FAULT state - cannot adjust current")
            return False
        
        # Get next step
        next_step = self._get_next_step(current_int, target)
        if next_step is None:
            self.logger.debug("No valid next step available")
            return False
        
        # Set the current
        self.logger.info(f"Adjusting current: {current_int}A → {next_step}A (target: {target}A)")
        success = self.ha_api.call_service(
            "number", "set_value",
            entity_id=self.current_entity,
            value=next_step
        )
        
        if success:
            self.last_adjustment_time = time.time()
            self.current_current = next_step
        
        return success
    
    def set_current_smooth(self, target_amps: float, timeout: float = 300) -> bool:
        """
        Smoothly adjust current to target through all steps.
        
        Args:
            target_amps: Target current in amps
            timeout: Maximum time to wait for adjustments
            
        Returns:
            True if target reached, False on timeout or error
        """
        target = self._find_nearest_allowed_current(target_amps)
        self.logger.info(f"Smooth adjustment to {target}A started")
        
        start_time = time.time()
        
        while True:
            current = self.get_current()
            if current is None:
                self.logger.error("Lost communication with charger")
                return False
            
            current_int = int(round(current))
            
            # Check if we've reached target
            if current_int == target:
                self.logger.info(f"Target current {target}A reached")
                return True
            
            # Check timeout
            if time.time() - start_time > timeout:
                self.logger.warning(f"Timeout adjusting current to {target}A")
                return False
            
            # Check for fault
            status = self.get_status()
            if status == ChargerStatus.FAULT:
                self.logger.error("Charger faulted during adjustment")
                return False
            
            # Try to take a step
            if self.can_adjust_now():
                self.set_current_step(target, force=False)
            
            # Small sleep to avoid busy-waiting
            time.sleep(1)
    
    def get_power(self) -> float:
        """Get current charging power in watts."""
        current = self.get_current()
        if current is not None:
            return self.amps_to_watts(current)
        return 0.0
    
    def get_min_power(self) -> float:
        """Get minimum charging power in watts."""
        return self.amps_to_watts(self.allowed_currents[0])
    
    def get_max_power(self) -> float:
        """Get maximum charging power in watts."""
        return self.amps_to_watts(self.allowed_currents[-1])
