"""
Test scenarios for EVSE manager simulation.
Each scenario tests different aspects of the control system.
"""

from typing import Dict, Any, List


class Scenario:
    """Base class for simulation scenarios."""
    
    def __init__(self, name: str, description: str, duration_hours: float):
        """Initialize scenario."""
        self.name = name
        self.description = description
        self.duration_hours = duration_hours
        self.duration_seconds = int(duration_hours * 3600)
        
    def get_config(self) -> Dict[str, Any]:
        """Get configuration for this scenario."""
        raise NotImplementedError


class SunnyDayScenario(Scenario):
    """Perfect sunny day with strong solar production."""
    
    def __init__(self):
        super().__init__(
            name="Sunny Day",
            description="Perfect conditions: clear sky, strong solar, battery healthy",
            duration_hours=6
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 30,
            'car_connect_at': 0,  # Connect immediately
            'expected_results': {
                'should_charge': True,
                'min_solar_percent': 90,
                'should_complete': False,  # 6 hours not enough for full charge
                'max_grid_import': 500,  # Some brief imports OK
            }
        }


class CloudyDayScenario(Scenario):
    """Cloudy day with variable solar."""
    
    def __init__(self):
        super().__init__(
            name="Cloudy Day",
            description="Variable solar with frequent clouds passing",
            duration_hours=6
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'cloudy_day',
            'car_initial_soc': 40,
            'car_connect_at': 0,
            'expected_results': {
                'should_charge': True,
                'min_solar_percent': 60,  # Lower expectation due to clouds
                'expect_adjustments': True,  # Should adjust frequently
                'max_grid_import': 2000,  # More imports expected
            }
        }


class MorningRampScenario(Scenario):
    """Morning solar ramp-up from 6 AM."""
    
    def __init__(self):
        super().__init__(
            name="Morning Ramp",
            description="Solar ramping up from dawn, test start/stop behavior",
            duration_hours=4
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'morning_ramp',
            'car_initial_soc': 35,
            'car_connect_at': 0,
            'expected_results': {
                'should_charge': True,
                'delayed_start': True,  # Should wait for sufficient solar
                'min_solar_percent': 75,
                'verify_grace_period': True,  # Test grace period behavior
            }
        }


class AfternoonFadeScenario(Scenario):
    """Afternoon solar declining from 3 PM."""
    
    def __init__(self):
        super().__init__(
            name="Afternoon Fade",
            description="Solar declining in afternoon, test graceful stop",
            duration_hours=3
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'afternoon_fade',
            'car_initial_soc': 60,
            'car_connect_at': 0,
            'expected_results': {
                'should_charge': True,
                'expect_stop': True,  # Should stop as solar fades
                'verify_grace_period': True,
                'min_solar_percent': 70,
            }
        }


class BatteryFullScenario(Scenario):
    """Battery at high SoC, test target discharge behavior."""
    
    def __init__(self):
        super().__init__(
            name="Battery Full",
            description="Battery >95% SoC, should increase EV load to discharge battery",
            duration_hours=3
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 25,
            'car_connect_at': 0,
            'battery_initial_soc': 96,  # Force high battery
            'expected_results': {
                'should_charge': True,
                'expect_higher_power': True,  # Should ramp to discharge battery
                'battery_discharge_target': True,
                'min_solar_percent': 85,
            }
        }


class InsufficientPowerScenario(Scenario):
    """Very cloudy day with insufficient power for minimum charge."""
    
    def __init__(self):
        super().__init__(
            name="Insufficient Power",
            description="Not enough power to start/maintain charging",
            duration_hours=2
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'cloudy_day',
            'car_initial_soc': 50,
            'car_connect_at': 0,
            'cloud_factor': 0.2,  # Very cloudy
            'expected_results': {
                'should_charge': False,  # Should not charge or stop quickly
                'expect_stop': True,
                'grace_period_triggered': True,
            }
        }


class StepControlScenario(Scenario):
    """Test stepped current control and delays."""
    
    def __init__(self):
        super().__init__(
            name="Step Control Test",
            description="Rapid power changes to test step control safety",
            duration_hours=1
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'partly_cloudy',
            'car_initial_soc': 30,
            'car_connect_at': 0,
            'expected_results': {
                'should_charge': True,
                'verify_step_delays': True,  # Check delays between adjustments
                'max_step_size': 1,  # Should only move one step at a time
                'no_faults': True,
            }
        }


class LateArrivalScenario(Scenario):
    """Car connects mid-day with good solar."""
    
    def __init__(self):
        super().__init__(
            name="Late Arrival",
            description="Car arrives at noon with good solar available",
            duration_hours=4
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 40,
            'car_connect_at': 2 * 3600,  # Connect after 2 hours (noon)
            'expected_results': {
                'should_charge': True,
                'fast_start': True,  # Should start quickly once connected
                'min_solar_percent': 90,
            }
        }


class SuddenLoadSpikesScenario(Scenario):
    """Multiple sudden load increases during charging."""
    
    def __init__(self):
        super().__init__(
            name="Sudden Load Spikes",
            description="AC, water heater, and appliances start during charging",
            duration_hours=3
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 35,
            'car_connect_at': 0,
            'load_events': [
                # (start_time, power, duration, description)
                (900, 2800, 1200, "AC unit starts"),  # 15 min in, 2.8kW for 20 min
                (2100, 1500, 900, "Water heater"),     # 35 min in, 1.5kW for 15 min
                (3600, 3500, 1800, "Pool pump + dryer"),  # 1 hour in, 3.5kW for 30 min
                (5400, 2200, 600, "Oven preheating"),  # 1.5 hours in, 2.2kW for 10 min
            ],
            'expected_results': {
                'should_charge': True,
                'expect_adjustments': True,
                'should_reduce_power': True,  # Should reduce EV power during spikes
                'min_solar_percent': 70,
            }
        }


class InverterLimitScenario(Scenario):
    """Load increases push system to inverter limits."""
    
    def __init__(self):
        super().__init__(
            name="Inverter Limit",
            description="Heavy loads approach/exceed inverter capacity, causing grid import",
            duration_hours=2
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 30,
            'car_connect_at': 0,
            'load_events': [
                # Stacking loads that exceed inverter capacity
                (600, 2500, 3600, "AC unit 1"),
                (900, 2500, 3600, "AC unit 2"),  # Now 5kW of AC
                (1200, 2000, 2400, "Water heater"),  # +2kW = 7kW base + EV
                (2400, 1800, 1800, "Oven"),  # Brief additional spike
            ],
            'expected_results': {
                'should_charge': True,
                'expect_grid_import': True,  # Will need grid due to inverter limit
                'should_reduce_ev_power': True,
                'inverter_limited': True,
            }
        }


class HeavyLoadInterruptionScenario(Scenario):
    """Major appliance causes charging to stop temporarily."""
    
    def __init__(self):
        super().__init__(
            name="Heavy Load Interruption",
            description="Large sudden load consumes all available power, EV stops temporarily",
            duration_hours=2
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'partly_cloudy',
            'car_initial_soc': 40,
            'car_connect_at': 0,
            'load_events': [
                # Massive load spike that consumes everything
                (1800, 6000, 1200, "All appliances (AC+dryer+oven+pool)"),
            ],
            'expected_results': {
                'should_charge': True,
                'expect_stop': True,  # Should stop during heavy load
                'expect_restart': True,  # Should restart after load ends
                'verify_grace_period': True,
            }
        }


class RandomAppliancesScenario(Scenario):
    """Realistic random appliance usage throughout day."""
    
    def __init__(self):
        super().__init__(
            name="Random Appliances",
            description="Realistic pattern of appliances starting/stopping randomly",
            duration_hours=4
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 30,
            'car_connect_at': 600,  # Connect after 10 min
            'load_events': [
                # Overlapping, realistic appliance usage
                (300, 800, 600, "Microwave"),
                (1200, 2400, 2700, "AC unit"),
                (1500, 1200, 1800, "Dishwasher"),
                (2400, 3200, 3600, "Dryer"),
                (3000, 1500, 1200, "Water heater"),
                (4200, 2200, 1800, "Oven"),
                (6000, 2400, 5400, "AC unit 2nd cycle"),
                (7200, 800, 900, "Kettle"),
                (9000, 1800, 2400, "Pool pump"),
            ],
            'expected_results': {
                'should_charge': True,
                'expect_adjustments': True,
                'dynamic_behavior': True,
                'min_solar_percent': 75,
            }
        }


class GridImportStressScenario(Scenario):
    """Extreme scenario with consistent grid import needed."""
    
    def __init__(self):
        super().__init__(
            name="Grid Import Stress",
            description="Continuous heavy loads requiring grid import while charging",
            duration_hours=2
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'partly_cloudy',
            'car_initial_soc': 25,
            'car_connect_at': 0,
            'battery_initial_soc': 55,  # Mid-range battery
            'load_events': [
                # Sustained heavy load throughout
                (0, 3500, 7200, "Continuous AC + base load"),
                (1800, 1500, 3600, "Water heater overlap"),
                (3600, 2000, 2400, "Additional appliance"),
            ],
            'expected_results': {
                'should_charge': True,
                'expect_grid_import': True,
                'solar_percent_low': True,  # Will be lower due to grid import
                'battery_discharge': True,
            }
        }


class ZeroExportScenario(Scenario):
    """Scenario with zero export constraint (common for many solar systems)."""
    
    def __init__(self):
        super().__init__(
            name="Zero Export",
            description="System cannot export to grid, battery must absorb all excess",
            duration_hours=6
        )
        
    def get_config(self) -> Dict[str, Any]:
        return {
            'power_scenario': 'sunny_day',
            'car_initial_soc': 30,
            'car_connect_at': 0,
            'zero_export': True,  # Enable zero export mode
            'expected_results': {
                'should_charge': True,
                'no_grid_export': True,
                'max_grid_export': 0,
                'min_solar_percent': 95,
            }
        }


# List of all available scenarios
ALL_SCENARIOS = [
    SunnyDayScenario(),
    CloudyDayScenario(),
    MorningRampScenario(),
    AfternoonFadeScenario(),
    BatteryFullScenario(),
    InsufficientPowerScenario(),
    StepControlScenario(),
    LateArrivalScenario(),
    SuddenLoadSpikesScenario(),
    InverterLimitScenario(),
    HeavyLoadInterruptionScenario(),
    RandomAppliancesScenario(),
    GridImportStressScenario(),
    ZeroExportScenario(),
]


def get_scenario(name: str) -> Scenario:
    """Get a scenario by name."""
    for scenario in ALL_SCENARIOS:
        if scenario.name.lower() == name.lower():
            return scenario
    raise ValueError(f"Unknown scenario: {name}")


def list_scenarios() -> List[str]:
    """List all available scenario names."""
    return [s.name for s in ALL_SCENARIOS]
