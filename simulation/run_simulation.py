"""
Main simulation runner.
Runs the EVSE manager with simulated power data and analyzes results.
"""

import sys
import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from simulation.mock_ha_api import MockHomeAssistantAPI, MockEntityPublisher
from simulation.power_simulator import PowerSimulator, ChargerSimulator
from simulation.scenarios import get_scenario, list_scenarios, ALL_SCENARIOS

# Import the actual EVSE manager components
from app.charger_controller import ChargerController
from app.power_calculator import PowerManager
from app.session_manager import SessionManager


class SimulationRunner:
    """Runs EVSE manager simulations."""
    
    def __init__(self, scenario_name: str, config: Dict[str, Any]):
        """
        Initialize simulation.
        
        Args:
            scenario_name: Name of scenario to run
            config: Configuration dict (like config.yaml)
        """
        self.scenario = get_scenario(scenario_name)
        self.config = config
        self.scenario_config = self.scenario.get_config()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Create mock HA API
        self.ha_api = MockHomeAssistantAPI()
        self.entity_publisher = MockEntityPublisher(self.ha_api, "evse_manager")
        
        # Create simulators
        self.power_sim = PowerSimulator(self.scenario_config['power_scenario'])
        
        # Override battery SoC if specified
        if 'battery_initial_soc' in self.scenario_config:
            self.power_sim.battery_soc = self.scenario_config['battery_initial_soc']
            
        # Override cloud factor if specified
        if 'cloud_factor' in self.scenario_config:
            self.power_sim.cloud_factor = self.scenario_config['cloud_factor']
            
        # Add load events if specified
        if 'load_events' in self.scenario_config:
            for event in self.scenario_config['load_events']:
                start_time, power, duration, description = event
                self.power_sim.add_load_event(start_time, power, duration, description)
                self.logger.info(f"Scheduled load event: {description} at {start_time}s (+{power}W for {duration}s)")
            
        self.charger_sim = ChargerSimulator(voltage=config['charger']['default_voltage'])
        
        # Connect car if specified
        car_connect_at = self.scenario_config.get('car_connect_at', 0)
        if car_connect_at == 0:
            self.charger_sim.connect_car(self.scenario_config['car_initial_soc'])
            
        # Create EVSE manager components
        self.charger_controller = ChargerController(
            ha_api=self.ha_api,
            config=config['charger']
        )
        
        self.power_manager = PowerManager(
            ha_api=self.ha_api,
            config=config
        )
        
        # Create temp directory for session data
        os.makedirs('/tmp/evse_sim', exist_ok=True)
        self.session_manager = SessionManager(data_dir='/tmp/evse_sim')
        
        # Simulation state
        self.time = 0  # Simulation time in seconds
        self.dt = 5  # Time step in seconds
        self.history: List[Dict] = []
        self.is_charging = False
        self.current_session_id = None
        
    def update_sensors(self, state: Dict[str, Any]):
        """Update mock sensor values."""
        # Map simulator state to HA entities
        sensors_config = self.config['sensors']
        
        self.ha_api.set_state(sensors_config['battery_soc_entity'], state['battery_soc'])
        self.ha_api.set_state(sensors_config['battery_power_entity'], state['battery_power'])
        self.ha_api.set_state(sensors_config['inverter_power_entity'], state['inverter_power'])
        self.ha_api.set_state(sensors_config['grid_power_entity'], state['grid_power'])
        
        if 'total_pv_entity' in sensors_config:
            self.ha_api.set_state(sensors_config['total_pv_entity'], state['pv_power'])
        if 'total_load_entity' in sensors_config:
            self.ha_api.set_state(sensors_config['total_load_entity'], state['total_load'])
            
        # Charger status
        self.ha_api.set_state(
            self.config['charger']['status_entity'],
            self.charger_sim.get_status()
        )
        self.ha_api.set_state(
            self.config['charger']['switch_entity'],
            'on' if self.charger_sim.is_on else 'off'
        )
        self.ha_api.set_state(
            self.config['charger']['current_entity'],
            self.charger_sim.current
        )
        
    def step(self) -> Dict[str, Any]:
        """
        Run one simulation step.
        
        Returns:
            State dictionary for this timestep
        """
        # Check if car should connect
        car_connect_at = self.scenario_config.get('car_connect_at', 0)
        if self.time >= car_connect_at and not self.charger_sim.car_connected:
            self.charger_sim.connect_car(self.scenario_config['car_initial_soc'])
            self.logger.info(f"[{self.time}s] Car connected at {self.scenario_config['car_initial_soc']}% SoC")
            
        # Get current EV load
        ev_load = self.charger_sim.actual_current * self.charger_sim.voltage
        
        # Get power system state
        power_state = self.power_sim.get_state(ev_load=ev_load, dt=self.dt)
        
        # Update mock sensors
        self.update_sensors(power_state)
        
        # Update charger simulator
        actual_ev_load = self.charger_sim.update(self.dt)
        
            # Run EVSE manager logic (if car connected)
        if self.charger_sim.car_connected:
            # Calculate available power
            available_power = self.power_manager.get_available_power()
            
            # Calculate minimum charge power
            min_current = min(self.config['charger']['allowed_currents'])
            min_charge_power = min_current * self.config['charger']['default_voltage']
            
            # Determine if should be charging
            if not self.is_charging:
                # Check if should start
                if available_power >= min_charge_power:
                    target_current = self.charger_controller.watts_to_amps(available_power)
                    if target_current >= min(self.config['charger']['allowed_currents']):
                        self.logger.info(
                            f"[{self.time}s] Starting charge: {available_power:.0f}W available "
                            f"-> {target_current:.1f}A"
                        )
                        self.charger_sim.turn_on()
                        self.charger_sim.set_current(target_current)
                        self.is_charging = True
                        self.current_session_id = self.session_manager.start_session()
            else:
                # Already charging - adjust power
                target_current = self.charger_controller.watts_to_amps(available_power)
                
                # Check if should stop
                if target_current < min(self.config['charger']['allowed_currents']):
                    # Would implement grace period here in full version
                    self.logger.info(
                        f"[{self.time}s] Stopping charge: insufficient power "
                        f"({available_power:.0f}W)"
                    )
                    self.charger_sim.turn_off()
                    self.is_charging = False
                    if self.current_session_id:
                        self.session_manager.end_session(self.current_session_id)
                        self.current_session_id = None
                else:
                    # Adjust current - find nearest allowed current
                    nearest_current = min(self.config['charger']['allowed_currents'], 
                                        key=lambda x: abs(x - target_current))
                    self.charger_sim.set_current(nearest_current)
                    
        # Advance time
        self.power_sim.advance_time(self.dt)
        self.time += self.dt
        
        # Record history
        history_entry = {
            'time': self.time,
            'time_of_day': power_state['time_of_day'],
            'pv_power': power_state['pv_power'],
            'house_load': power_state['house_load'],
            'battery_power': power_state['battery_power'],
            'battery_soc': power_state['battery_soc'],
            'grid_power': power_state['grid_power'],
            'ev_load': actual_ev_load,
            'charger_current': self.charger_sim.actual_current,
            'charger_target': self.charger_sim.current,
            'charger_on': self.charger_sim.is_on,
            'car_soc': self.charger_sim.car_soc,
            'available_power': self.power_manager.get_available_power() if self.charger_sim.car_connected else 0,
            'load_spikes': power_state.get('load_spikes', 0),
            'inverter_limited': power_state.get('inverter_limited', False),
            'active_events': power_state.get('active_events', []),
        }
        self.history.append(history_entry)
        
        return history_entry
        
    def run(self) -> Dict[str, Any]:
        """
        Run the full simulation.
        
        Returns:
            Results dictionary with metrics and history
        """
        self.logger.info(f"Starting simulation: {self.scenario.name}")
        self.logger.info(f"Description: {self.scenario.description}")
        self.logger.info(f"Duration: {self.scenario.duration_hours} hours")
        
        total_steps = int(self.scenario.duration_seconds / self.dt)
        
        for step_num in range(total_steps):
            self.step()
            
            # Log progress every simulated hour
            if self.time % 3600 == 0:
                hour = self.time / 3600
                state = self.history[-1]
                extra_info = ""
                if state.get('load_spikes', 0) > 0:
                    extra_info = f" [+{state['load_spikes']:.0f}W load spike]"
                if state.get('inverter_limited', False):
                    extra_info += " [INVERTER LIMIT]"
                    
                self.logger.info(
                    f"[Hour {hour:.0f}] "
                    f"PV: {state['pv_power']:.0f}W, "
                    f"Battery: {state['battery_soc']:.0f}% ({state['battery_power']:.0f}W), "
                    f"EV: {state['ev_load']:.0f}W ({state['charger_current']:.1f}A), "
                    f"Grid: {state['grid_power']:.0f}W"
                    f"{extra_info}"
                )
                
            # Log load events as they happen
            state = self.history[-1]
            if state.get('active_events'):
                for event in state['active_events']:
                    if not any(event in h.get('active_events', []) for h in self.history[:-1]):
                        self.logger.warning(f"[{self.time}s] LOAD EVENT: {event} (+{state['load_spikes']:.0f}W)")
                
        # Calculate metrics
        results = self.analyze_results()
        
        self.logger.info(f"\nSimulation complete!")
        self.logger.info(f"Results: {json.dumps(results['summary'], indent=2)}")
        
        return results
        
    def analyze_results(self) -> Dict[str, Any]:
        """Analyze simulation results."""
        # Calculate metrics
        total_ev_energy = sum(h['ev_load'] * self.dt / 3600 for h in self.history)  # kWh
        total_grid_import = sum(max(0, h['grid_power']) * self.dt / 3600 for h in self.history)
        total_grid_export = sum(max(0, -h['grid_power']) * self.dt / 3600 for h in self.history)
        
        # Solar percentage for EV charging
        ev_from_solar = total_ev_energy - (total_grid_import if total_ev_energy > 0 else 0)
        solar_percent = (ev_from_solar / total_ev_energy * 100) if total_ev_energy > 0 else 0
        
        # Count adjustments
        adjustments = sum(
            1 for i in range(1, len(self.history))
            if self.history[i]['charger_target'] != self.history[i-1]['charger_target']
        )
        
        # Charging time
        charging_time = sum(h['charger_on'] for h in self.history) * self.dt / 3600  # hours
        
        # Car SoC change
        initial_soc = self.scenario_config['car_initial_soc']
        final_soc = self.history[-1]['car_soc'] if self.history else initial_soc
        
        # Load spike stats
        max_load_spike = max((h.get('load_spikes', 0) for h in self.history), default=0)
        total_load_events = len([e for h in self.history for e in h.get('active_events', [])])
        inverter_limited_time = sum(h.get('inverter_limited', False) for h in self.history) * self.dt / 60  # minutes
        
        summary = {
            'scenario': self.scenario.name,
            'duration_hours': self.scenario.duration_hours,
            'ev_energy_kwh': round(total_ev_energy, 2),
            'grid_import_kwh': round(total_grid_import, 2),
            'grid_export_kwh': round(total_grid_export, 2),
            'solar_percent': round(solar_percent, 1),
            'charging_hours': round(charging_time, 2),
            'adjustments': adjustments,
            'car_soc_start': initial_soc,
            'car_soc_end': round(final_soc, 1),
            'soc_gain': round(final_soc - initial_soc, 1),
            'max_load_spike_w': round(max_load_spike, 0),
            'inverter_limited_minutes': round(inverter_limited_time, 1),
            'load_events_count': total_load_events,
        }
        
        return {
            'summary': summary,
            'history': self.history,
            'scenario_config': self.scenario_config,
        }
        
    def save_results(self, filename: str):
        """Save results to file."""
        results = self.analyze_results()
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Results saved to {filename}")


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    # Default config for simulation (don't need to parse actual config.yaml for simulation)
    return {
        'charger': {
            'name': 'Simulated EVSE',
            'switch_entity': 'switch.ev_charger',
            'current_entity': 'number.ev_charger_set_current',
            'status_entity': 'sensor.ev_charger_status',
            'allowed_currents': [6, 8, 10, 13, 16, 20, 24],
            'step_delay': 10,
            'voltage_entity': 'sensor.ss_inverter_voltage',
            'default_voltage': 230,
        },
        'power_method': 'battery',
        'sensors': {
            'battery_soc_entity': 'sensor.ss_battery_soc',
            'battery_power_entity': 'sensor.ss_battery_power',
            'battery_high_soc': 95,
            'battery_priority_soc': 80,
            'battery_target_discharge_min': 0,
            'battery_target_discharge_max': 1500,
            'inverter_power_entity': 'sensor.ss_inverter_power',
            'inverter_max_power': 8000,
            'grid_power_entity': 'sensor.ss_grid_ct_power',
            'total_pv_entity': 'sensor.total_pv_power',
            'total_load_entity': 'sensor.total_load_power',
        },
        'control': {
            'mode': 'auto',
            'manual_current': 6,
            'update_interval': 5,
            'grace_period': 600,
            'min_session_duration': 600,
            'power_smoothing_window': 60,
            'hysteresis_watts': 500,
        },
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run EVSE Manager simulations')
    parser.add_argument(
        'scenario',
        nargs='?',
        help='Scenario to run (or "all" for all scenarios)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available scenarios'
    )
    parser.add_argument(
        '--output',
        '-o',
        help='Output file for results (JSON)'
    )
    
    args = parser.parse_args()
    
    if args.list:
        print("\nAvailable scenarios:")
        for scenario in ALL_SCENARIOS:
            print(f"  {scenario.name:20s} - {scenario.description}")
        return
        
    if not args.scenario:
        parser.print_help()
        print("\nUse --list to see available scenarios")
        return
        
    config = load_config()
    
    if args.scenario.lower() == 'all':
        # Run all scenarios
        all_results = []
        for scenario in ALL_SCENARIOS:
            print(f"\n{'='*60}")
            print(f"Running: {scenario.name}")
            print(f"{'='*60}\n")
            
            sim = SimulationRunner(scenario.name, config)
            results = sim.run()
            all_results.append(results)
            
        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY OF ALL SCENARIOS")
        print(f"{'='*60}\n")
        print(f"{'Scenario':<20} {'EV kWh':<10} {'Solar %':<10} {'Adj':<8} {'SoC Gain':<10}")
        print("-" * 60)
        for r in all_results:
            s = r['summary']
            print(
                f"{s['scenario']:<20} "
                f"{s['ev_energy_kwh']:<10.2f} "
                f"{s['solar_percent']:<10.1f} "
                f"{s['adjustments']:<8} "
                f"{s['soc_gain']:<10.1f}"
            )
    else:
        # Run single scenario
        sim = SimulationRunner(args.scenario, config)
        results = sim.run()
        
        if args.output:
            sim.save_results(args.output)


if __name__ == '__main__':
    main()
