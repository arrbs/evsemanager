#!/usr/bin/env python3
"""
EVSE Manager - Intelligent EVSE power management with solar optimization.
"""
import json
import logging
import os
import sys
import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from charger_controller import ChargerController, ChargerStatus
from power_calculator import PowerManager
from session_manager import SessionManager, AdaptiveTuner
try:
    from ha_api import HomeAssistantAPI, EntityPublisher
except ImportError:
    # In simulation environment, these will be provided as mock objects
    HomeAssistantAPI = None
    EntityPublisher = None


class EVSEManager:
    """Main EVSE Manager class with intelligent solar-based charging."""

    def __init__(self, ha_api=None, config=None, data_dir=None):
        """Initialize the EVSE Manager."""
        self.config = config if config is not None else self._load_config()
        self._setup_logging()
        self.config = self._normalize_config(self.config)  # Convert simple format to internal format
        
        # Initialize components
        if ha_api is not None:
            # Simulation mode - use provided mock API
            self.ha_api = ha_api
        else:
            # Production mode - create real HA API
            if HomeAssistantAPI is None:
                raise RuntimeError("HomeAssistantAPI not available - missing requests module")
            self.ha_api = HomeAssistantAPI()
        
        self.charger = ChargerController(self.ha_api, self.config['charger'])
        self.power_manager = PowerManager(self.ha_api, self.config)
        
        # Use provided data_dir or default to /data
        session_data_dir = data_dir if data_dir is not None else "/data"
        self.session_manager = SessionManager(session_data_dir)
        
        # Entity publisher may be mock or real
        if hasattr(self.ha_api, '__class__') and 'Mock' in self.ha_api.__class__.__name__:
            # Mock API provides its own entity publisher
            self.entity_publisher = None
        else:
            self.entity_publisher = EntityPublisher(self.ha_api)
        
        # Initialize adaptive tuner if enabled
        adaptive_config = self.config.get('adaptive', {})
        self.adaptive_tuner = AdaptiveTuner(adaptive_config) if adaptive_config.get('enabled') else None
        
        # Control parameters
        control_settings = self.config.get('control', {})
        self.mode = control_settings.get('mode', 'auto')
        self.manual_current = control_settings.get('manual_current', 6)
        self.update_interval = control_settings.get('update_interval', 5)
        self.grace_period = control_settings.get('grace_period', 600)
        self.min_session_duration = control_settings.get('min_session_duration', 600)
        self.start_retry_attempts = control_settings.get('start_retry_attempts', 2)
        self.start_retry_delay = control_settings.get('start_retry_delay', 3)
        self.start_retry_cooldown = control_settings.get('start_retry_cooldown', 300)
        self.start_handshake_window = control_settings.get('start_handshake_window', 20)
        
        # Apply learned settings if available
        if self.adaptive_tuner and self.adaptive_tuner.should_apply_settings():
            self._apply_learned_settings()
        
        # State
        self.is_running = False
        self.last_status_publish = None
        self.insufficient_power_since = None
        self.session_active = False
        self.last_adjustment_time = None
        self.failed_start_reason = None
        self.last_failed_start_time = None
        self.startup_handshake_deadline = None
        self.switch_reapply_attempted = False
        self.inverter_limit_active_since = None
        
        self.logger.info("="*60)
        self.logger.info("EVSE Manager initialized successfully")
        self.logger.info(f"Mode: {self.mode}")
        self.logger.info(f"Power method: {self.config.get('power_method')}")
        self.logger.info(f"Update interval: {self.update_interval}s")
        if self.adaptive_tuner:
            status = self.adaptive_tuner.get_learning_status()
            self.logger.info(f"Adaptive Learning: Enabled ({status['sessions_completed']}/{status['total_sessions']} sessions)")
        self.logger.info("="*60)
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from options.json."""
        try:
            with open('/data/options.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error("Configuration file not found")
            sys.exit(1)
    
    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert simplified config format to internal format for backwards compatibility."""
        # Check if already in new format (has top-level simple keys)
        if 'charger_switch' in config:
            # New simplified format - convert to internal structure
            allowed_currents_str = config.get('charger_allowed_currents', '6,8,10,13,16,20,24')
            allowed_currents = [int(x.strip()) for x in allowed_currents_str.split(',')]
            
            normalized = {
                'charger': {
                    'name': 'EVSE',
                    'switch_entity': config.get('charger_switch'),
                    'current_entity': config.get('charger_current'),
                    'status_entity': config.get('charger_status'),
                    'allowed_currents': allowed_currents,
                    'max_current': max(allowed_currents),
                    'step_delay': config.get('charger_step_delay', 10),
                    'voltage_entity': config.get('voltage_sensor'),
                    'default_voltage': 230
                },
                'power_method': 'battery',
                'sensors': {
                    'battery_soc_entity': config.get('battery_soc'),
                    'battery_power_entity': config.get('battery_power'),
                    'battery_high_soc': 95,
                    'battery_priority_soc': config.get('battery_priority_soc', 80),
                    'battery_target_discharge_min': 0,
                    'battery_target_discharge_max': 1500,
                    'inverter_power_entity': config.get('inverter_power'),
                    'inverter_max_power': 8000
                },
                'control': {
                    'mode': config.get('mode', 'manual'),
                    'manual_current': 6,
                    'update_interval': config.get('update_interval', 5),
                    'grace_period': config.get('grace_period', 600),
                    'min_session_duration': 600,
                    'power_smoothing_window': config.get('power_smoothing_window', 60),
                    'power_smoothing_window_seconds': config.get('power_smoothing_window_seconds', 30),
                    'hysteresis_watts': config.get('hysteresis_watts', 500),
                    'start_retry_attempts': config.get('start_retry_attempts', 2),
                    'start_retry_delay': config.get('start_retry_delay', 3),
                    'start_retry_cooldown': config.get('start_retry_cooldown', 300),
                    'start_handshake_window': config.get('start_handshake_window', 20)
                },
                'adaptive': {
                    'enabled': False
                },
                'log_level': config.get('log_level', 'info')
            }
            self.logger.info("Converted simplified config to internal format")
            return normalized
        else:
            # Already in old detailed format
            return config
    
    def _setup_logging(self):
        """Set up logging based on configuration."""
        log_level = self.config.get('log_level', 'info').upper()
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stdout
        )
        self.logger = logging.getLogger(__name__)
    
    def check_battery_priority(self) -> bool:
        """
        Check if battery has priority over car charging.
        
        Returns:
            True if battery needs priority (don't charge car)
        """
        if self.mode == 'manual':
            return False
        if self.config.get('power_method') != 'battery':
            return False
        
        battery_soc_entity = self.config['sensors'].get('battery_soc_entity')
        battery_priority_soc = self.config['sensors'].get('battery_priority_soc', 80)
        
        if not battery_soc_entity:
            return False
        
        soc = self.ha_api.get_state(battery_soc_entity)
        
        if soc is None:
            return False
        
        soc = float(soc)
        
        if soc < battery_priority_soc:
            self.logger.info(f"Battery priority active: SOC {soc}% < {battery_priority_soc}%")
            return True
        
        return False
    
    def should_start_charging(self, ignore_cooldown: bool = False) -> bool:
        """
        Determine if we should start a charging session.
        
        Args:
            ignore_cooldown: Whether to ignore recent failed-start cooldowns (used for manual overrides)
        
        Returns:
            True if conditions are met to start charging
        """
        # Respect cooldown after a failed start to avoid flapping
        if (not ignore_cooldown and self.last_failed_start_time and self.start_retry_cooldown):
            elapsed = (datetime.now() - self.last_failed_start_time).total_seconds()
            if elapsed < self.start_retry_cooldown:
                remaining = int(self.start_retry_cooldown - elapsed)
                self.logger.info(
                    f"Skipping start attempt: cooldown {remaining}s remaining after {self.failed_start_reason}"
                )
                return False
            self.failed_start_reason = None
            self.last_failed_start_time = None

        # Check charger status
        status = self.charger.get_status()
        
        if status == ChargerStatus.AVAILABLE:
            self.logger.debug("Car not connected")
            return False
        
        if status == ChargerStatus.CHARGED:
            self.logger.debug("Car already charged")
            return False
        
        if status == ChargerStatus.FAULT:
            self.logger.error("Charger in fault state - cannot start")
            return False
        
        if status not in [ChargerStatus.WAITING, ChargerStatus.CHARGING]:
            self.logger.debug(f"Charger status not ready: {status}")
            return False
        
        # Battery priority only applies to active sessions (checked in update() loop)
        # Don't prevent starting - we check available power below which handles this
        
        # In auto mode, check if we have enough power
        if self.mode == 'auto':
            available_power = self.power_manager.get_available_power()
            min_power = self.charger.get_min_power()
            
            if available_power is None:
                self.logger.warning("Cannot determine available power")
                return False
            
            if available_power < min_power:
                self.logger.info(f"Insufficient power to start: {available_power}W < {min_power}W")
                return False
            
            # Check inverter limit
            if self.power_manager.check_inverter_limit():
                self.logger.warning("Inverter at limit - cannot start charging")
                return False
        
        return True
    
    def handle_auto_mode(self):
        """Handle automatic mode charging logic."""
        status = self.charger.get_status()
        current_amps = self.charger.get_current()

        if current_amps is None:
            self.logger.error("Cannot read current setting")
            return

        if self._handle_inverter_limit_response(current_amps):
            return
        
        # Check if we should stop due to insufficient power
        if self.power_manager.should_stop_charging(self.charger):
            if self.insufficient_power_since is None:
                self.insufficient_power_since = datetime.now()
                self.logger.info("Insufficient power detected - starting grace period")
            else:
                elapsed = (datetime.now() - self.insufficient_power_since).total_seconds()
                if elapsed > self.grace_period:
                    self.logger.warning(f"Grace period expired ({self.grace_period}s) - stopping charger")
                    self.stop_charging("insufficient_power")
                    self.insufficient_power_since = None
                    return
                else:
                    remaining = self.grace_period - elapsed
                    self.logger.debug(f"Grace period: {remaining:.0f}s remaining")
        else:
            # Reset grace period if power is sufficient
            if self.insufficient_power_since is not None:
                self.logger.info("Power sufficient again - grace period reset")
                self.insufficient_power_since = None
        
        # Calculate target current based on available power
        target_amps = self.power_manager.get_target_current(self.charger, current_amps)
        
        self.logger.info(f"Auto mode: current={current_amps}A, target={target_amps}A")
        
        if target_amps is not None and target_amps != current_amps:
            # Try to adjust current
            if self.charger.can_adjust_now():
                self.logger.info(f"Adjusting current: {current_amps}A → {target_amps}A")
                success = self.charger.set_current_step(target_amps)
                
                if success:
                    # Update power manager with commanded current for predictive compensation
                    self.power_manager.set_commanded_current(target_amps)
                    self.session_manager.record_adjustment()
                    self.last_adjustment_time = datetime.now()
                
                # Check for fault after adjustment
                time.sleep(2)  # Give charger time to respond
                if self.charger.get_status() == ChargerStatus.FAULT:
                    self.logger.error("Charger faulted after adjustment!")
                    self.session_manager.record_fault()
                    self.stop_charging("fault")
    
    def handle_manual_mode(self):
        """Handle manual mode charging logic."""
        current_amps = self.charger.get_current()
        
        if current_amps is None:
            return

        if self._handle_inverter_limit_response(current_amps):
            return
        
        # Adjust to manual target if different
        if abs(current_amps - self.manual_current) > 0.5:
            if self.charger.can_adjust_now():
                self.logger.info(f"Manual mode: adjusting to {self.manual_current}A")
                self.charger.set_current_step(self.manual_current)

    def _record_failed_start(self, reason: str):
        """Record a failed start attempt so we can back off auto retries."""
        self.failed_start_reason = reason
        self.last_failed_start_time = datetime.now()

    def _ensure_charger_powered(self) -> bool:
        """Make sure the charger switch stays on, retrying safely if needed."""
        if self.charger.is_on():
            return True
        max_attempts = max(1, self.start_retry_attempts)
        for attempt in range(1, max_attempts + 1):
            self.logger.info(f"Charger power-on attempt {attempt}/{max_attempts}")
            self.charger.turn_on()
            time.sleep(self.start_retry_delay)
            if self.charger.is_on():
                return True
            self.logger.warning("Charger switched itself off after ON command")
        return False

    def _session_duration_seconds(self) -> float:
        """Return current session duration in seconds if available."""
        if self.session_manager and self.session_manager.session_start_time:
            return (datetime.now() - self.session_manager.session_start_time).total_seconds()
        return 0.0

    def _get_active_failed_reason(self) -> Optional[str]:
        """Return recent failed-start reason if still relevant."""
        if not self.failed_start_reason or not self.last_failed_start_time:
            return None
        ttl = max(self.start_retry_cooldown, 300)
        elapsed = (datetime.now() - self.last_failed_start_time).total_seconds()
        if elapsed > ttl:
            self.failed_start_reason = None
            return None
        return self.failed_start_reason

    def _force_minimum_current(self) -> bool:
        """Force the charger down to its minimum current as quickly as possible."""
        target = self.charger.allowed_currents[0]
        max_steps = len(self.charger.allowed_currents)
        success = False
        status = self.charger.get_status()
        if status in (ChargerStatus.AVAILABLE, ChargerStatus.CHARGED):
            self.logger.debug("Charger idle - performing direct current reset")
            success = self.charger.set_current_direct(target)
            if success:
                self.session_manager.record_adjustment()
                self.last_adjustment_time = datetime.now()
            return success
        for _ in range(max_steps):
            current = self.charger.get_current()
            if current is None:
                break
            if int(round(current)) <= target:
                success = True
                break
            if not self.charger.set_current_step(target, force=True):
                break
            time.sleep(0.4)
        if success:
            self.power_manager.set_commanded_current(target)
            self.session_manager.record_adjustment()
            self.last_adjustment_time = datetime.now()
        return success

    def _handle_inverter_limit_response(self, current_amps: Optional[float]) -> bool:
        """React immediately when the inverter limit is reached."""
        if not self.power_manager.check_inverter_limit():
            self.inverter_limit_active_since = None
            return False

        min_current = self.charger.allowed_currents[0]
        if current_amps is None:
            current_amps = self.charger.get_current() or min_current

        if current_amps - min_current > 0.5:
            self.logger.warning("Inverter limit hit - forcing rapid current reduction")
            if not self._force_minimum_current():
                self.logger.error("Unable to reduce current while inverter limit active - stopping charger")
                self.stop_charging("inverter_limit")
            else:
                self.logger.info("Current forced to minimum to protect inverter")
            self.inverter_limit_active_since = datetime.now()
            return True

        self.logger.error("Inverter limit persists at minimum current - stopping immediately")
        self.inverter_limit_active_since = datetime.now()
        self.stop_charging("inverter_limit")
        return True
    
    def _apply_learned_settings(self):
        """Apply learned optimal settings."""
        if not self.adaptive_tuner or not self.adaptive_tuner.optimal_settings:
            return
        
        settings = self.adaptive_tuner.optimal_settings
        self.logger.info(f"Applying learned optimal settings: {settings}")
        
        # Update control parameters
        if 'hysteresis_watts' in settings:
            self.power_manager.hysteresis = settings['hysteresis_watts']
        
        if 'power_smoothing_window' in settings:
            self.power_manager.calculator.smoothing_window = settings['power_smoothing_window']
        
        if 'grace_period' in settings:
            self.grace_period = settings['grace_period']
    
    def _get_current_control_settings(self) -> dict:
        """Get current control settings for adaptive learning."""
        return {
            'hysteresis_watts': self.power_manager.hysteresis,
            'power_smoothing_window': self.power_manager.calculator.smoothing_window,
            'grace_period': self.grace_period
        }
    
    def start_charging(self, manual_request: bool = False) -> bool:
        """Start a charging session."""
        if self.session_active:
            return True
        
        qualifier = " (manual request)" if manual_request else ""
        self.logger.info(f"Starting charging session{qualifier}")
        self.failed_start_reason = None
        
        # If learning mode active, get next settings to try
        if self.adaptive_tuner and not self.adaptive_tuner.learning_complete:
            current_settings = self._get_current_control_settings()
            next_settings = self.adaptive_tuner.get_next_settings(current_settings)
            
            if next_settings:
                self.logger.info(f"Learning trial: testing settings {next_settings}")
                # Apply trial settings
                if 'hysteresis_watts' in next_settings:
                    self.power_manager.hysteresis = next_settings['hysteresis_watts']
                if 'power_smoothing_window' in next_settings:
                    self.power_manager.calculator.smoothing_window = next_settings['power_smoothing_window']
                if 'grace_period' in next_settings:
                    self.grace_period = next_settings['grace_period']
                
                # Start trial tracking
                self.adaptive_tuner.start_trial(next_settings)
        
        # Turn on charger if needed with safe retries
        if not self._ensure_charger_powered():
            self.logger.error("Charger refused to stay on - aborting start")
            self._record_failed_start('charger_refused')
            return False
        
        # Start session tracking
        self.session_manager.start_session(mode=self.mode)
        self.session_active = True
        self.insufficient_power_since = None
        self.last_failed_start_time = None
        self.switch_reapply_attempted = False
        self.startup_handshake_deadline = (
            datetime.now() + timedelta(seconds=self.start_handshake_window)
            if self.start_handshake_window
            else None
        )
        
        # Set initial current
        if self.mode == 'manual':
            target = self.manual_current
        else:
            # In auto mode, start at minimum
            target = self.charger.allowed_currents[0]
        
        self.charger.set_current_step(target, force=True)
        # Update power manager with commanded current
        self.power_manager.set_commanded_current(target)
        return True
    
    def stop_charging(self, reason: str = "normal"):
        """Stop charging session."""
        if not self.session_active:
            return
        
        self.logger.info(f"Stopping charging session: {reason}")
        
        # Turn off charger
        self.charger.turn_off()
        self.startup_handshake_deadline = None
        
        # Get session data before ending
        session_info = self.session_manager.get_current_session_info()
        
        # End session
        self.session_manager.end_session(reason=reason)
        self.session_active = False
        self.insufficient_power_since = None
        self.switch_reapply_attempted = False
        
        # Record trial outcome if learning
        if self.adaptive_tuner and session_info:
            self.adaptive_tuner.record_trial_outcome(session_info)
    
    def update_session_data(self):
        """Update session with current measurements."""
        if not self.session_active:
            return
        
        power = self.charger.get_power()
        current = self.charger.get_current()
        
        if power and current:
            # Determine if power is from solar (simplified)
            # In reality, this would need more sophisticated logic
            available_power = self.power_manager.get_available_power()
            is_solar = available_power is not None and available_power > 0
            
            self.session_manager.update_session(power, current, is_solar)
    
    def publish_status(self):
        """Publish current status to Home Assistant."""
        current_status = self.charger.get_status()
        current_amps = self.charger.get_current() or 0
        target_current = self.power_manager.commanded_current or current_amps
        charging_power = self.charger.get_power() if self.session_active else 0
        available_power = self.power_manager.get_available_power()
        min_power = self.charger.get_min_power()
        charger_on = self.charger.is_on()
        insufficient_power = False
        if self.mode == 'auto':
            if available_power is None or available_power < min_power:
                insufficient_power = True

        # Capture inverter telemetry for UI visibility
        inverter_power = None
        inverter_limiting = False
        if hasattr(self.power_manager, 'inverter_power_entity') and self.power_manager.inverter_power_entity:
            try:
                raw = self.ha_api.get_state(self.power_manager.inverter_power_entity)
                if raw is not None:
                    inverter_power = float(raw)
                inverter_limiting = self.power_manager.check_inverter_limit()
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(f"Unable to read inverter telemetry: {exc}")
                inverter_power = None
                inverter_limiting = False

        # Calculate grace-period countdown so UI can show intent
        grace_status = None
        if self.insufficient_power_since is not None:
            elapsed = (datetime.now() - self.insufficient_power_since).total_seconds()
            grace_status = {
                'active': True,
                'remaining_seconds': max(0, int(self.grace_period - elapsed)),
                'total_seconds': self.grace_period,
                'reason': 'insufficient_power'
            }

        sensors = self.config.get('sensors', {})
        soc_entity = sensors.get('battery_soc_entity')
        power_entity = sensors.get('battery_power_entity')
        battery_priority_active = self.check_battery_priority()
        battery_info = None
        battery_priority_soc_threshold = sensors.get('battery_priority_soc', 80)

        if soc_entity and power_entity:
            try:
                raw_soc = self.ha_api.get_state(soc_entity)
                raw_power = self.ha_api.get_state(power_entity)
                if raw_soc is not None and raw_power is not None:
                    soc = float(raw_soc)
                    power = float(raw_power)
                    charging_positive = sensors.get('battery_power_charging_positive', False)
                    if charging_positive:
                        charging = power > 50
                        discharging = power < -50
                    else:
                        charging = power < -50
                        discharging = power > 50
                    direction = 'charging' if charging else 'discharging' if discharging else 'idle'
                    battery_info = {
                        'soc': soc,
                        'power': power,
                        'direction': direction,
                        'priority_active': battery_priority_active,
                        'priority_threshold': battery_priority_soc_threshold
                    }
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(f"Unable to capture battery telemetry: {exc}")
                battery_info = None

        active_failed_reason = self._get_active_failed_reason()

        limiting_factors = []
        if battery_priority_active:
            limiting_factors.append('battery_priority')
        if inverter_limiting:
            limiting_factors.append('inverter_limit')
        if grace_status and grace_status.get('active'):
            limiting_factors.append('grace_period')
        if insufficient_power:
            limiting_factors.append('insufficient_power')
        car_unplugged = current_status == ChargerStatus.AVAILABLE and not self.session_active
        if car_unplugged:
            limiting_factors.append('car_unplugged')
        vehicle_waiting = current_status == ChargerStatus.WAITING and not self.session_active
        if vehicle_waiting:
            limiting_factors.append('vehicle_waiting')
        if active_failed_reason == 'charger_refused':
            limiting_factors.append('charger_refused')
        elif active_failed_reason == 'vehicle_charged':
            limiting_factors.append('vehicle_charged')

        auto_pause_reason = None
        if not self.session_active:
            if battery_priority_active:
                auto_pause_reason = 'battery_priority'
            elif insufficient_power:
                auto_pause_reason = 'insufficient_power'
            elif inverter_limiting:
                auto_pause_reason = 'inverter_limit'
            elif car_unplugged:
                auto_pause_reason = 'car_unplugged'
            elif vehicle_waiting:
                auto_pause_reason = 'vehicle_waiting'
        if not self.session_active and auto_pause_reason is None and active_failed_reason:
            auto_pause_reason = active_failed_reason

        charger_transition = None
        if self.session_active and not charger_on:
            charger_transition = 'starting'
        elif not self.session_active and charger_on:
            charger_transition = 'stopping'

        auto_state = None
        auto_state_label = None
        auto_state_help = None
        if self.mode == 'auto':
            if self.session_active:
                auto_state = 'charging'
                auto_state_label = 'Charging'
                auto_state_help = 'Actively charging using available solar power.'
            else:
                reason_map = {
                    'insufficient_power': (
                        'waiting_for_solar',
                        'Waiting for solar',
                        'Auto mode will resume once there is enough excess solar power.'
                    ),
                    'battery_priority': (
                        'waiting_for_battery',
                        'Holding for battery',
                        f'Battery SOC is {battery_info["soc"]:.1f}% (need {battery_priority_soc_threshold}%) — waiting for house battery to recover before starting EV charging.' if battery_info else 'Battery priority is delaying EV charging until the house battery recovers.'
                    ),
                    'inverter_limit': (
                        'inverter_limit',
                        'Inverter limit',
                        'The inverter is maxed out, so auto mode paused charging immediately.'
                    ),
                    'car_unplugged': (
                        'waiting_for_vehicle',
                        'Waiting for vehicle',
                        'Plug a vehicle in to let auto mode start charging.'
                    ),
                    'vehicle_waiting': (
                        'vehicle_waiting',
                        'Vehicle waiting',
                        'The charger reports "waiting"—unplug and replug the vehicle to restart charging.'
                    ),
                    'charger_refused': (
                        'blocked_charger',
                        'Charger refused',
                        'The charger rejected the ON command—toggle its hardware switch to clear the fault.'
                    ),
                    'vehicle_charged': (
                        'vehicle_full',
                        'Vehicle full',
                        'The vehicle reports a full battery; auto mode will stay idle.'
                    )
                }
                if auto_pause_reason in reason_map:
                    auto_state, auto_state_label, auto_state_help = reason_map[auto_pause_reason]
                else:
                    if current_status == ChargerStatus.WAITING:
                        auto_state = 'ready'
                        auto_state_label = 'Ready'
                        auto_state_help = 'Car connected and ready—auto mode will start when solar permits.'
                    elif current_status == ChargerStatus.AVAILABLE:
                        auto_state = 'waiting_for_vehicle'
                        auto_state_label = 'Waiting for vehicle'
                        auto_state_help = 'Plug a vehicle in to allow charging.'
                    elif current_status == ChargerStatus.CHARGED:
                        auto_state = 'vehicle_full'
                        auto_state_label = 'Vehicle full'
                        auto_state_help = 'The vehicle ended the session; auto mode is idle.'
                    else:
                        auto_state = 'idle'
                        auto_state_label = 'Idle'
                        auto_state_help = 'Auto mode is standing by.'

        # Prepare state dict
        state = {
            'mode': self.mode,
            'status': 'active' if self.session_active else 'idle',
            'charger_status': current_status.value,
            'current_amps': current_amps,
            'target_current': target_current,
            'available_power': available_power,
            'charging_power': charging_power,
            'manual_current': self.manual_current,
            'inverter_power': inverter_power,
            'inverter_limiting': inverter_limiting,
            'battery': battery_info,
            'battery_priority_soc': battery_priority_soc_threshold,
            'limiting_factors': limiting_factors,
            'auto_pause_reason': auto_pause_reason,
            'auto_state': auto_state,
            'auto_state_label': auto_state_label,
            'auto_state_help': auto_state_help,
            'charger_transition': charger_transition,
            'grace_period': grace_status,
            'session_info': self.session_manager.get_current_session_info(),
            'stats': self.session_manager.get_stats(),
            'recent_sessions': self.session_manager.get_recent_sessions(10),
            'learning_status': self.adaptive_tuner.get_learning_status() if self.adaptive_tuner else None
        }
        
        # Publish all entities
        self.entity_publisher.publish_all(state)
        
        # Save state for web UI
        try:
            ui_state_file = '/data/ui_state.json'
            with open(ui_state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            self.logger.error(f"Error saving UI state: {e}")
        
        self.last_status_publish = datetime.now()
    
    def check_commands(self):
        """Check for commands from web UI."""
        command_file = '/data/command.json'
        
        try:
            if os.path.exists(command_file):
                with open(command_file, 'r') as f:
                    command = json.load(f)
                
                # Process command
                cmd_type = command.get('command')
                
                if cmd_type == 'set_mode':
                    new_mode = command.get('mode')
                    if new_mode in ['auto', 'manual']:
                        self.logger.info(f"UI command: Set mode to {new_mode}")
                        self.mode = new_mode
                        if new_mode == 'manual':
                            min_current = min(self.charger.allowed_currents)
                            if self.manual_current != min_current:
                                self.logger.info(f"Manual mode defaulting current to {min_current}A")
                                self.manual_current = min_current
                            if self.charger.is_on():
                                self.logger.info("Manual mode engaged while charger on - forcing current to minimum")
                                self.charger.set_current_step(min_current, force=True)
                
                elif cmd_type == 'set_manual_current':
                    current = command.get('current')
                    if current is not None:
                        current_value = int(current)
                        self.logger.info(f"UI command: Set manual current to {current_value}A")
                        self.manual_current = current_value
                        if self.mode == 'manual':
                            applied = self.charger.set_current_step(self.manual_current, force=True)
                            if applied:
                                self.logger.info("Manual current applied immediately while charger idle")
                            else:
                                self.logger.debug("Manual current command queued; charger will adjust on next cycle")
                
                elif cmd_type == 'start':
                    self.logger.info("UI command: Start charging")
                    manual_force = self.mode == 'manual' and not self.session_active
                    if manual_force or self.should_start_charging(ignore_cooldown=True):
                        if manual_force:
                            self.logger.info("Manual mode start request bypassing solar checks")
                        if not self.start_charging(manual_request=True):
                            self.logger.warning("Manual start command failed - check vehicle state")
                    else:
                        self.logger.info("Start command ignored: conditions not met")
                
                elif cmd_type == 'stop':
                    self.logger.info("UI command: Stop charging")
                    if self.session_active:
                        self.stop_charging("user_request")
                elif cmd_type == 'set_battery_priority_soc':
                    soc_value = command.get('soc')
                    try:
                        soc_value = max(0, min(100, int(soc_value)))
                    except (TypeError, ValueError):
                        soc_value = None

                    if soc_value is not None:
                        self.logger.info("UI command: Set battery minimum SOC to %s%%", soc_value)
                        sensors = self.config.setdefault('sensors', {})
                        sensors['battery_priority_soc'] = soc_value
                        if hasattr(self.power_manager, 'set_battery_priority_soc'):
                            self.power_manager.set_battery_priority_soc(soc_value)
                
                # Remove command file after processing
                os.remove(command_file)
                
        except Exception as e:
            self.logger.error(f"Error processing command: {e}")
    
    def update(self):
        """Single update cycle - for simulation or single-step operation."""
        try:
            # Check for UI commands
            self.check_commands()
            
            status = self.charger.get_status()
            self.logger.debug(f"Charger status: {status.value}")
            
            # Check if we should start or stop
            if not self.session_active:
                if self.should_start_charging():
                    if not self.start_charging():
                        self.logger.debug("Start attempt aborted - waiting before retry")
                else:
                    if self.mode == 'auto' and self.charger.is_on():
                        available_power = self.power_manager.get_available_power()
                        min_power = self.charger.get_min_power()
                        if available_power is None or available_power < min_power:
                            self.logger.info("Auto mode: insufficient power detected while charger on - turning off")
                            self.charger.turn_off()
            else:
                # Session active - check if we should stop
                self.logger.debug(f"Session active, status={status.value}, mode={self.mode}")
                if not self.charger.is_on():
                    if not self.switch_reapply_attempted:
                        self.logger.warning("Charger switch dropped during session - reapplying ON command")
                        if self._ensure_charger_powered():
                            self.switch_reapply_attempted = True
                            return
                        self.logger.error("Charger refused to stay on after reapply attempt")
                    else:
                        self.logger.error("Charger switch dropped again after reapply")
                    self._record_failed_start('charger_refused')
                    self.stop_charging("charger_switch_off")
                    return

                if status == ChargerStatus.CHARGING and self.startup_handshake_deadline:
                    self.startup_handshake_deadline = None

                session_duration = self._session_duration_seconds()
                handshake_active = (
                    self.startup_handshake_deadline is not None
                    and datetime.now() < self.startup_handshake_deadline
                )

                if status in [ChargerStatus.AVAILABLE, ChargerStatus.CHARGED]:
                    if handshake_active:
                        self.logger.debug(
                            f"Vehicle still reporting {status.value} during handshake window; waiting"
                        )
                    else:
                        reason = "car_full" if status == ChargerStatus.CHARGED else "car_disconnected"
                        handshake_buffer = (self.start_handshake_window or 0) * 2
                        min_duration_before_full = max(120, handshake_buffer)
                        if status == ChargerStatus.CHARGED and session_duration < min_duration_before_full:
                            self._record_failed_start('vehicle_charged')
                        if status == ChargerStatus.AVAILABLE:
                            self.logger.info("Vehicle unplugged - forcing charger to minimum current")
                            if not self._force_minimum_current():
                                self.logger.warning("Failed to force minimum current after unplug event")
                        self.stop_charging(reason)
                    return

                if status == ChargerStatus.WAITING:
                    if handshake_active:
                        self.logger.debug("Vehicle waiting during handshake window; giving it more time")
                    else:
                        self.logger.warning("Charger stuck in waiting state - stopping session so user can replug")
                        self._record_failed_start('vehicle_waiting')
                        self.stop_charging("vehicle_waiting")
                    return

                if status == ChargerStatus.FAULT:
                    self.stop_charging("fault")
                    return

                if self.check_battery_priority():
                    self.stop_charging("battery_priority")
                    return

                # Continue charging - handle mode-specific logic
                if self.mode == 'auto':
                    self.handle_auto_mode()
                else:
                    self.handle_manual_mode()
                
                # Update session data
                self.update_session_data()
            
            # Publish status periodically (every 10 seconds)
            if self.entity_publisher and (self.last_status_publish is None or \
               (datetime.now() - self.last_status_publish).total_seconds() > 10):
                self.publish_status()
                
        except Exception as e:
            self.logger.error(f"Error in update cycle: {e}", exc_info=True)
    
    def control_loop(self):
        """Main control loop."""
        self.logger.info("Control loop started")
        
        while self.is_running:
            self.update()
            time.sleep(self.update_interval)
    
    def run(self):
        """Start the EVSE Manager."""
        self.is_running = True
        
        try:
            self.control_loop()
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown."""
        self.logger.info("Shutting down EVSE Manager")
        self.is_running = False
        
        # End any active session
        if self.session_active:
            self.stop_charging("shutdown")
        
        self.logger.info("Shutdown complete")


if __name__ == '__main__':
    manager = EVSEManager()
    manager.run()
