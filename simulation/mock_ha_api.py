"""
Mock Home Assistant API for simulation purposes.
Mimics the real HA API but uses simulated sensor values.
"""

import logging
from typing import Dict, Any, Optional


class MockHomeAssistantAPI:
    """Mock HA API that returns simulated sensor values."""
    
    def __init__(self):
        """Initialize the mock API."""
        self.logger = logging.getLogger(__name__)
        self.states: Dict[str, Dict[str, Any]] = {}
        self.service_calls: list = []  # Track service calls for analysis
        
    def set_state(self, entity_id: str, state: Any, attributes: Optional[Dict] = None):
        """Set a sensor state (used by simulator)."""
        self.states[entity_id] = {
            'entity_id': entity_id,
            'state': str(state),
            'attributes': attributes or {}
        }
        
    def get_state(self, entity_id: str) -> Optional[str]:
        """Get the current state of an entity."""
        if entity_id in self.states:
            return self.states[entity_id]['state']
        return None
        
    def call_service(self, domain: str, service: str, entity_id: str, **kwargs) -> bool:
        """Record a service call."""
        call_data = {
            'domain': domain,
            'service': service,
            'entity_id': entity_id,
            'data': kwargs
        }
        self.service_calls.append(call_data)
        
        # Actually update the mock state for switches and numbers
        if domain == 'switch':
            if service == 'turn_on':
                self.set_state(entity_id, 'on')
            elif service == 'turn_off':
                self.set_state(entity_id, 'off')
        elif domain == 'number':
            if 'value' in kwargs:
                self.set_state(entity_id, kwargs['value'])
                
        self.logger.debug(f"Service call: {domain}.{service} on {entity_id} with {kwargs}")
        return True
        
    def get_service_calls(self, clear: bool = False) -> list:
        """Get recorded service calls."""
        calls = self.service_calls.copy()
        if clear:
            self.service_calls.clear()
        return calls


class MockEntityPublisher:
    """Mock entity publisher for simulation."""
    
    def __init__(self, ha_api: MockHomeAssistantAPI, addon_name: str):
        """Initialize mock publisher."""
        self.ha_api = ha_api
        self.addon_name = addon_name
        self.logger = logging.getLogger(__name__)
        
    def create_entities(self):
        """Mock entity creation."""
        self.logger.info(f"Mock: Would create entities for {self.addon_name}")
        
    def update_entity(self, entity_id: str, state: Any, attributes: Optional[Dict] = None):
        """Update an entity state."""
        self.ha_api.set_state(f"sensor.{self.addon_name}_{entity_id}", state, attributes)
