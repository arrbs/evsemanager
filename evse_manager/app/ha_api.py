"""
Home Assistant API Client
Handles communication with Home Assistant.
"""
import logging
import os
from typing import Optional, Any, Dict
import requests


class HomeAssistantAPI:
    """Client for Home Assistant REST API."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Get supervisor token and URL
        # Note: SUPERVISOR_TOKEN only works for supervisor API, not core API
        # We need to access HA directly via local network
        self.token = os.getenv('SUPERVISOR_TOKEN')
        
        if self.token:
            # Access Home Assistant directly on local network
            # The add-on runs inside the HA network, so we can use homeassistant hostname
            self.base_url = "http://homeassistant:8123"
            self.headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            }
            self.logger.info(f"Running in Home Assistant add-on mode (via homeassistant:8123)")
        else:
            # Fallback for development
            self.base_url = os.getenv('HA_URL', 'http://homeassistant.local:8123')
            self.token = os.getenv('HA_TOKEN')
            if self.token:
                self.headers = {
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': 'application/json'
                }
                self.logger.info("Running in development mode with token")
            else:
                self.headers = {'Content-Type': 'application/json'}
                self.logger.error("No authentication token found!")
        
        self.timeout = 10
    
    def get_state(self, entity_id: str) -> Optional[Any]:
        """
        Get state of an entity.
        
        Args:
            entity_id: Entity ID (e.g., 'sensor.solar_power')
            
        Returns:
            State value or None on error
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/states/{entity_id}",
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data.get('state')
        except requests.RequestException as e:
            self.logger.error(f"Error getting state for {entity_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting state for {entity_id}: {e}")
            return None
    
    def call_service(self, domain: str, service: str, **kwargs) -> bool:
        """
        Call a Home Assistant service.
        
        Args:
            domain: Service domain (e.g., 'switch', 'number')
            service: Service name (e.g., 'turn_on', 'set_value')
            **kwargs: Service data (e.g., entity_id='switch.charger', value=10)
            
        Returns:
            True on success, False on error
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self.headers,
                json=kwargs,
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            self.logger.error(f"Error calling service {domain}.{service}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error calling service {domain}.{service}: {e}")
            return False
    
    def set_state(self, entity_id: str, state: Any, attributes: Optional[Dict] = None) -> bool:
        """
        Set state of an entity (for creating virtual sensors).
        
        Args:
            entity_id: Entity ID
            state: State value
            attributes: Optional attributes dict
            
        Returns:
            True on success, False on error
        """
        try:
            data = {
                'state': state,
                'attributes': attributes or {}
            }
            
            response = requests.post(
                f"{self.base_url}/api/states/{entity_id}",
                headers=self.headers,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            self.logger.error(f"Error setting state for {entity_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error setting state for {entity_id}: {e}")
            return False
    
    def fire_event(self, event_type: str, event_data: Optional[Dict] = None) -> bool:
        """
        Fire a Home Assistant event.
        
        Args:
            event_type: Event type name
            event_data: Optional event data
            
        Returns:
            True on success, False on error
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/events/{event_type}",
                headers=self.headers,
                json=event_data or {},
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            self.logger.error(f"Error firing event {event_type}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error firing event {event_type}: {e}")
            return False


class EntityPublisher:
    """Publishes EVSE Manager entities to Home Assistant."""
    
    def __init__(self, ha_api: HomeAssistantAPI):
        self.logger = logging.getLogger(__name__)
        self.ha_api = ha_api
        self.entity_prefix = "evse_manager"
    
    def publish_mode(self, mode: str):
        """Publish current mode (auto/manual)."""
        entity_id = f"sensor.{self.entity_prefix}_mode"
        self.ha_api.set_state(
            entity_id,
            mode,
            {
                'friendly_name': 'EVSE Manager Mode',
                'icon': 'mdi:auto-mode' if mode == 'auto' else 'mdi:hand-back-right'
            }
        )
    
    def publish_status(self, status: str):
        """Publish manager status."""
        entity_id = f"sensor.{self.entity_prefix}_status"
        self.ha_api.set_state(
            entity_id,
            status,
            {
                'friendly_name': 'EVSE Manager Status',
                'icon': 'mdi:information'
            }
        )
    
    def publish_target_current(self, current: float):
        """Publish target charging current."""
        entity_id = f"sensor.{self.entity_prefix}_target_current"
        self.ha_api.set_state(
            entity_id,
            round(current, 1),
            {
                'friendly_name': 'EVSE Target Current',
                'unit_of_measurement': 'A',
                'icon': 'mdi:current-ac'
            }
        )
    
    def publish_available_power(self, power: float):
        """Publish available power for charging."""
        entity_id = f"sensor.{self.entity_prefix}_available_power"
        self.ha_api.set_state(
            entity_id,
            round(power, 0),
            {
                'friendly_name': 'Available Solar Power',
                'unit_of_measurement': 'W',
                'icon': 'mdi:solar-power',
                'device_class': 'power'
            }
        )
    
    def publish_charging_power(self, power: float):
        """Publish actual charging power."""
        entity_id = f"sensor.{self.entity_prefix}_charging_power"
        self.ha_api.set_state(
            entity_id,
            round(power, 0),
            {
                'friendly_name': 'EVSE Charging Power',
                'unit_of_measurement': 'W',
                'icon': 'mdi:ev-station',
                'device_class': 'power'
            }
        )
    
    def publish_session_info(self, session_info: Optional[Dict]):
        """Publish current session information."""
        if session_info is None:
            entity_id = f"sensor.{self.entity_prefix}_session"
            self.ha_api.set_state(
                entity_id,
                'idle',
                {
                    'friendly_name': 'Charging Session',
                    'icon': 'mdi:ev-station'
                }
            )
            return
        
        # Session status
        entity_id = f"sensor.{self.entity_prefix}_session"
        self.ha_api.set_state(
            entity_id,
            'active',
            {
                'friendly_name': 'Charging Session',
                'icon': 'mdi:ev-station',
                'session_id': session_info.get('session_id'),
                'duration': session_info.get('current_duration_seconds', 0),
                'energy_kwh': round(session_info.get('total_energy_kwh', 0), 2),
                'solar_percentage': round(session_info.get('solar_percentage', 0), 1)
            }
        )
        
        # Session energy
        entity_id = f"sensor.{self.entity_prefix}_session_energy"
        self.ha_api.set_state(
            entity_id,
            round(session_info.get('total_energy_kwh', 0), 2),
            {
                'friendly_name': 'Session Energy',
                'unit_of_measurement': 'kWh',
                'icon': 'mdi:lightning-bolt',
                'device_class': 'energy'
            }
        )
        
        # Solar percentage
        entity_id = f"sensor.{self.entity_prefix}_solar_percentage"
        self.ha_api.set_state(
            entity_id,
            round(session_info.get('solar_percentage', 0), 1),
            {
                'friendly_name': 'Solar Charging %',
                'unit_of_measurement': '%',
                'icon': 'mdi:solar-power'
            }
        )
    
    def publish_stats(self, stats: Dict):
        """Publish overall statistics."""
        entity_id = f"sensor.{self.entity_prefix}_total_energy"
        self.ha_api.set_state(
            entity_id,
            round(stats.get('total_energy_kwh', 0), 2),
            {
                'friendly_name': 'Total Energy Charged',
                'unit_of_measurement': 'kWh',
                'icon': 'mdi:lightning-bolt',
                'device_class': 'energy',
                'total_sessions': stats.get('total_sessions', 0),
                'avg_solar_percentage': round(stats.get('avg_solar_percentage', 0), 1)
            }
        )
    
    def publish_all(self, manager_state: Dict):
        """
        Publish all entities from manager state.
        
        Args:
            manager_state: Dict with keys: mode, status, target_current, available_power,
                          charging_power, session_info, stats
        """
        self.publish_mode(manager_state.get('mode', 'unknown'))
        self.publish_status(manager_state.get('status', 'unknown'))
        
        if manager_state.get('target_current') is not None:
            self.publish_target_current(manager_state['target_current'])
        
        if manager_state.get('available_power') is not None:
            self.publish_available_power(manager_state['available_power'])
        
        if manager_state.get('charging_power') is not None:
            self.publish_charging_power(manager_state['charging_power'])
        
        self.publish_session_info(manager_state.get('session_info'))
        
        if manager_state.get('stats'):
            self.publish_stats(manager_state['stats'])
