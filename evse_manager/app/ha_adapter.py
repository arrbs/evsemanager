"""Home Assistant adapter for deterministic controller."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from controller_config import EntityConfig
from state_machine import Decision, Inputs


@dataclass
class SensorSnapshot:
    """Raw values read from Home Assistant for a single tick."""

    batt_soc: Optional[float]
    batt_power: Optional[float]
    inverter_power: Optional[float]
    pv_power: Optional[float]
    charger_status: str
    charger_switch_on: bool
    charger_current_a: Optional[float]
    auto_enabled: bool


class HomeAssistantAdapter:
    """Thin layer that isolates HA REST calls from the FSM."""

    def __init__(self, api, entity_config: EntityConfig, logger: Optional[logging.Logger] = None):
        self.api = api
        self.entities = entity_config
        self.logger = logger or logging.getLogger(__name__)

    def read_inputs(self, now_s: float) -> Inputs:
        snapshot = self._poll_entities()
        return Inputs(
            batt_soc_percent=snapshot.batt_soc,
            batt_power_w=snapshot.batt_power,
            inverter_power_w=snapshot.inverter_power,
            pv_power_w=snapshot.pv_power,
            charger_status=snapshot.charger_status,
            charger_switch_on=snapshot.charger_switch_on,
            charger_current_a=snapshot.charger_current_a,
            auto_enabled=snapshot.auto_enabled,
            now_s=now_s,
        )

    def _poll_entities(self) -> SensorSnapshot:
        batt_soc = self._read_float(self.entities.battery_soc)
        batt_power = self._read_float(self.entities.battery_power)
        inverter_power = self._read_float(self.entities.inverter_power)
        pv_power = self._read_float(self.entities.pv_power)
        charger_status = self._read_text(self.entities.charger_status, default="unknown")
        charger_switch_on = self._read_text(self.entities.charger_switch, default="off") == "on"
        charger_current = self._read_float(self.entities.charger_current)
        auto_enabled = self._read_auto_enabled()
        return SensorSnapshot(
            batt_soc=batt_soc,
            batt_power=batt_power,
            inverter_power=inverter_power,
            pv_power=pv_power,
            charger_status=charger_status,
            charger_switch_on=charger_switch_on,
            charger_current_a=charger_current,
            auto_enabled=auto_enabled,
        )

    def apply_decision(self, decision: Decision) -> None:
        """Apply switch/current commands to Home Assistant."""
        if decision.switch_command is not None:
            desired = decision.switch_command
            entity_id = self.entities.charger_switch
            service = "turn_on" if desired else "turn_off"
            self.logger.info("%s -> %s (%s)", entity_id, service, decision.reason)
            self.api.call_service("switch", service, entity_id=entity_id)
        if decision.current_command_amps is not None:
            entity_id = self.entities.charger_current
            value = decision.current_command_amps
            self.logger.info("%s -> %s A (%s)", entity_id, value, decision.reason)
            self.api.call_service("number", "set_value", entity_id=entity_id, value=value)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _read_text(self, entity_id: Optional[str], default: str = "") -> str:
        if not entity_id:
            return default
        state = self.api.get_state(entity_id)
        if state is None:
            return default
        return str(state).lower()

    def _read_float(self, entity_id: Optional[str]) -> Optional[float]:
        if not entity_id:
            return None
        state = self.api.get_state(entity_id)
        if state is None:
            return None
        try:
            return float(state)
        except (ValueError, TypeError):
            self.logger.debug("Unable to parse float from %s=%s", entity_id, state)
            return None

    def _read_auto_enabled(self) -> bool:
        entity = self.entities.auto_enabled
        if not entity:
            return self.entities.auto_enabled_default
        state = self.api.get_state(entity)
        if state is None:
            return self.entities.auto_enabled_default
        normalized = str(state).strip().lower()
        if normalized in {"on", "true", "1", "enabled"}:
            return True
        if normalized in {"off", "false", "0", "disabled"}:
            return False
        return self.entities.auto_enabled_default
