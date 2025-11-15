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
from ha_api import HomeAssistantAPI, EntityPublisher


class EVSEManager:
    """Main EVSE Manager class with intelligent solar-based charging."""

    def __init__(self):
        """Initialize the EVSE Manager."""
        self.config = self._load_config()
        self._setup_logging()
        
        # Initialize components
        self.ha_api = HomeAssistantAPI()
        self.charger = ChargerController(self.ha_api, self.config['charger'])
        self.power_manager = PowerManager(self.ha_api, self.config)
        self.session_manager = SessionManager()
        self.entity_publisher = EntityPublisher(self.ha_api)
        
        # Initialize adaptive tuner if enabled
        adaptive_config = self.config.get('adaptive', {})
        self.adaptive_tuner = AdaptiveTuner(adaptive_config) if adaptive_config.get('enabled') else None
        
        # Control parameters
        self.mode = self.config['control'].get('mode', 'auto')
        self.manual_current = self.config['control'].get('manual_current', 6)
        self.update_interval = self.config['control'].get('update_interval', 5)
        self.grace_period = self.config['control'].get('grace_period', 600)
        self.min_session_duration = self.config['control'].get('min_session_duration', 600)
        
        # Apply learned settings if available
        if self.adaptive_tuner and self.adaptive_tuner.should_apply_settings():
            self._apply_learned_settings()
        
        # State
        self.is_running = False
        self.last_status_publish = None
        self.insufficient_power_since = None
        self.session_active = False
        self.last_adjustment_time = None
        
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
    
    def should_start_charging(self) -> bool:
        """
        Determine if we should start a charging session.
        
        Returns:
            True if conditions are met to start charging
        """
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
        
        # Check battery priority
        if self.check_battery_priority():
            return False
        
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
        
        # Get current charging current
        current_amps = self.charger.get_current()
        if current_amps is None:
            self.logger.error("Cannot read current setting")
            return
        
        # Calculate target current based on available power
        target_amps = self.power_manager.get_target_current(self.charger, current_amps)
        
        if target_amps is not None and target_amps != current_amps:
            # Try to adjust current
            if self.charger.can_adjust_now():
                self.logger.info(f"Adjusting current: {current_amps}A → {target_amps}A")
                success = self.charger.set_current_step(target_amps)
                
                if success:
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
        
        # Adjust to manual target if different
        if abs(current_amps - self.manual_current) > 0.5:
            if self.charger.can_adjust_now():
                self.logger.info(f"Manual mode: adjusting to {self.manual_current}A")
                self.charger.set_current_step(self.manual_current)
    
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
    
    def start_charging(self):
        """Start a charging session."""
        if self.session_active:
            return
        
        self.logger.info("Starting charging session")
        
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
        
        # Turn on charger if needed
        if not self.charger.is_on():
            self.charger.turn_on()
            time.sleep(2)  # Give charger time to turn on
        
        # Start session tracking
        self.session_manager.start_session(mode=self.mode)
        self.session_active = True
        self.insufficient_power_since = None
        
        # Set initial current
        if self.mode == 'manual':
            target = self.manual_current
        else:
            # In auto mode, start at minimum
            target = self.charger.allowed_currents[0]
        
        self.charger.set_current_step(target, force=True)
    
    def stop_charging(self, reason: str = "normal"):
        """Stop charging session."""
        if not self.session_active:
            return
        
        self.logger.info(f"Stopping charging session: {reason}")
        
        # Turn off charger
        self.charger.turn_off()
        
        # Get session data before ending
        session_info = self.session_manager.get_current_session_info()
        
        # End session
        self.session_manager.end_session(reason=reason)
        self.session_active = False
        self.insufficient_power_since = None
        
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
        # Prepare state dict
        state = {
            'mode': self.mode,
            'status': 'active' if self.session_active else 'idle',
            'charger_status': self.charger.get_status().value,
            'current_amps': self.charger.get_current() or 0,
            'target_current': self.charger.get_current(),
            'available_power': self.power_manager.get_available_power(),
            'charging_power': self.charger.get_power() if self.session_active else 0,
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
                
                elif cmd_type == 'set_manual_current':
                    current = command.get('current')
                    if current:
                        self.logger.info(f"UI command: Set manual current to {current}A")
                        self.manual_current = current
                
                elif cmd_type == 'start':
                    self.logger.info("UI command: Start charging")
                    if self.should_start_charging():
                        self.start_charging()
                
                elif cmd_type == 'stop':
                    self.logger.info("UI command: Stop charging")
                    if self.session_active:
                        self.stop_charging("user_request")
                
                # Remove command file after processing
                os.remove(command_file)
                
        except Exception as e:
            self.logger.error(f"Error processing command: {e}")
    
    def control_loop(self):
        """Main control loop."""
        self.logger.info("Control loop started")
        
        while self.is_running:
            try:
                # Check for UI commands
                self.check_commands()
                
                status = self.charger.get_status()
                self.logger.debug(f"Charger status: {status.value}")
                
                # Check if we should start or stop
                if not self.session_active:
                    if self.should_start_charging():
                        self.start_charging()
                else:
                    # Session active - check if we should stop
                    if status in [ChargerStatus.AVAILABLE, ChargerStatus.CHARGED]:
                        self.stop_charging("car_disconnected")
                    elif status == ChargerStatus.FAULT:
                        self.stop_charging("fault")
                    elif self.check_battery_priority():
                        self.stop_charging("battery_priority")
                    else:
                        # Continue charging - handle mode-specific logic
                        if self.mode == 'auto':
                            self.handle_auto_mode()
                        else:
                            self.handle_manual_mode()
                        
                        # Update session data
                        self.update_session_data()
                
                # Publish status periodically (every 10 seconds)
                if self.last_status_publish is None or \
                   (datetime.now() - self.last_status_publish).total_seconds() > 10:
                    self.publish_status()
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in control loop: {e}", exc_info=True)
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
