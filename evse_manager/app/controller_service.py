#!/usr/bin/env python3
"""Deterministic EVSE control service entrypoint."""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from controller_config import load_runtime_config
from ha_adapter import HomeAssistantAdapter
from ha_api import HomeAssistantAPI
from state_machine import Decision, DeterministicStateMachine, EVSE_STEPS_AMPS, Inputs

UI_STATE_PATH = Path("/data/ui_state.json")
HISTORY_LIMIT = 180


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout,
    )


class ControlService:
    """Owns the deterministic control loop and UI persistence."""

    def __init__(self):
        self.runtime_config = load_runtime_config()
        configure_logging(self.runtime_config.log_level)
        self.logger = logging.getLogger("evse.controller")
        self.api = HomeAssistantAPI()
        self.adapter = HomeAssistantAdapter(self.api, self.runtime_config.entities, self.logger)
        self.machine = DeterministicStateMachine(self.runtime_config.controller)
        self.tick_seconds = self.runtime_config.tick_seconds
        self.energy_history: List[Dict[str, Optional[float]]] = []
        self.logger.info(
            "Deterministic FSM online (tick=%ss, inverter limit=%sW)",
            self.tick_seconds,
            self.runtime_config.controller.inverter_limit_w,
        )
        
        # Synchronize with any existing charging session
        try:
            startup_inputs = self.adapter.read_inputs(time.monotonic())
            self.machine.sync_with_charger(startup_inputs)
            if self.machine.state.evse_step_index > 0:
                self.logger.info(
                    "Detected existing charging session: %sA (step %s), taking ownership",
                    EVSE_STEPS_AMPS[self.machine.state.evse_step_index],
                    self.machine.state.evse_step_index,
                )
        except Exception:
            self.logger.exception("Failed to sync with charger state on startup")

    def run_forever(self) -> None:
        while True:
            tick_start = time.monotonic()
            try:
                self._run_tick(tick_start)
            except Exception:  # noqa: BLE001
                self.logger.exception("Controller tick failed")
            elapsed = time.monotonic() - tick_start
            time.sleep(max(0.0, self.tick_seconds - elapsed))

    def _run_tick(self, now_s: float) -> None:
        prev_state = self.machine.state
        inputs = self.adapter.read_inputs(now_s)
        
        # Detect external changes before processing
        if prev_state.evse_step_index != 0 and inputs.charger_current_a is not None:
            expected_amps = EVSE_STEPS_AMPS[prev_state.evse_step_index]
            if abs(expected_amps - inputs.charger_current_a) > 2:
                self.logger.info(
                    "Detected external current change: expected=%sA, actual=%sA",
                    expected_amps,
                    inputs.charger_current_a,
                )
        
        decision, derived = self.machine.tick(inputs)
        
        # Log if state changed due to external sync (no decision but state changed)
        if not decision and prev_state.evse_step_index != self.machine.state.evse_step_index:
            self.logger.info(
                "Synchronized with external change: %sA→%sA (step %s→%s)",
                EVSE_STEPS_AMPS[prev_state.evse_step_index],
                EVSE_STEPS_AMPS[self.machine.state.evse_step_index],
                prev_state.evse_step_index,
                self.machine.state.evse_step_index,
            )
        
        if decision:
            self._log_transition(prev_state, decision, inputs)
            self.adapter.apply_decision(decision)
        else:
            # Log when in conservative mode but not taking action
            if (
                self.machine.state.evse_step_index > 0
                and inputs.batt_soc_percent is not None
                and inputs.batt_soc_percent < self.runtime_config.controller.soc_conservative_below
                and inputs.batt_power_w is not None
                and inputs.batt_power_w > 50
            ):
                self.logger.debug(
                    "Conservative mode: SOC=%.1f%%, batt_discharge=%.0fW, excess=%s, no decision",
                    inputs.batt_soc_percent,
                    inputs.batt_power_w,
                    derived.excess_w,
                )
        self._persist_ui_state(inputs, derived, decision)

    # ------------------------------------------------------------------
    # Logging & persistence helpers
    # ------------------------------------------------------------------
    def _log_transition(self, prev_state, decision: Decision, inputs: Inputs) -> None:
        old_amps = EVSE_STEPS_AMPS[prev_state.evse_step_index]
        new_amps = EVSE_STEPS_AMPS[decision.new_state.evse_step_index]
        self.logger.info(
            "FSM %s→%s | %sA→%sA | reason=%s | soc=%.2f%% | inv=%sW",
            prev_state.mode_state.value,
            decision.new_state.mode_state.value,
            old_amps,
            new_amps,
            decision.reason,
            inputs.batt_soc_percent or 0.0,
            inputs.inverter_power_w,
        )

    def _persist_ui_state(self, inputs: Inputs, derived, decision: Optional[Decision]) -> None:
        current_index = self.machine.state.evse_step_index
        current_amps = EVSE_STEPS_AMPS[current_index]
        target_amps = (
            decision.current_command_amps
            if decision and decision.current_command_amps is not None
            else current_amps
        )
        voltage = self.runtime_config.controller.line_voltage_v
        current_watts = current_amps * voltage
        target_watts = target_amps * voltage if target_amps else 0.0
        available_power = self._available_power(inputs, derived)
        
        # UI-specific display values for available power and PV
        ui_available_for_ev = self._ui_available_for_ev(inputs, current_watts, derived.region)
        ui_pv_display = inputs.pv_power_w
        
        timestamp = datetime.now(timezone.utc).isoformat()
        # Use UI values for history display on graph
        self._append_history(
            timestamp,
            ui_available_for_ev,
            ui_pv_display,
            inputs.inverter_power_w,
            current_watts,
            target_watts,
        )
        payload = {
            "mode": "auto",
            "status": "active" if current_index > 0 else "idle",
            "mode_state": self.machine.state.mode_state.value,
            "region": derived.region,
            "charger_status": inputs.charger_status,
            "current_amps": current_amps,
            "target_current": target_amps,
            "available_power": available_power,
            "ui_available_for_ev": ui_available_for_ev,
            "ui_pv_display": ui_pv_display,
            "charging_power": current_watts,
            "inverter_power": inputs.inverter_power_w,
            "pv_power_w": inputs.pv_power_w,
            "battery": self._battery_payload(inputs),
            "battery_priority_soc": self.runtime_config.controller.soc_main_max,
            "limiting_factors": self._limiting_factors(inputs, derived),
            "auto_state": self._auto_state(current_index, inputs, derived),
            "auto_state_label": self._auto_state_label(current_index, inputs, derived),
            "auto_state_help": self._auto_state_help(current_index, inputs, derived),
            "energy_map": self._energy_map(current_watts, target_watts, available_power),
        }
        try:
            UI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with UI_STATE_PATH.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"))
        except Exception:  # noqa: BLE001
            self.logger.exception("Unable to write UI state")

    def _battery_payload(self, inputs: Inputs) -> Optional[Dict[str, float]]:
        if inputs.batt_soc_percent is None and inputs.batt_power_w is None:
            return None
        direction = "idle"
        if inputs.batt_power_w is not None:
            if inputs.batt_power_w > 50:
                direction = "discharging"
            elif inputs.batt_power_w < -50:
                direction = "charging"
        return {
            "soc": inputs.batt_soc_percent,
            "power": inputs.batt_power_w,
            "direction": direction,
        }

    def _available_power(self, inputs: Inputs, derived) -> Optional[float]:
        if derived.region == "MAIN":
            return derived.excess_w
        if inputs.batt_power_w is None:
            return None
        if inputs.batt_power_w <= 0:
            return abs(inputs.batt_power_w)
        if inputs.batt_power_w <= self.runtime_config.controller.probe_max_discharge_w:
            return 0.0
        return None

    def _ui_available_for_ev(self, inputs: Inputs, current_evse_watts: float, region: str) -> Optional[float]:
        """Calculate UI display value for 'Available for EV'."""
        # When SOC >= 95% (PROBE region), return None to display "Probing"
        if region == "PROBE":
            return None
        
        # When SOC < 95% (MAIN region): Total PV - (Inverter - Current EVSE)
        if inputs.pv_power_w is None or inputs.inverter_power_w is None:
            self.logger.debug(
                "Cannot calculate UI available power: pv=%s, inverter=%s",
                inputs.pv_power_w,
                inputs.inverter_power_w,
            )
            return None
        
        # Available = PV - (Inverter - EVSE) = PV - Inverter + EVSE
        available = inputs.pv_power_w - (inputs.inverter_power_w - current_evse_watts)
        return available

    def _append_history(
        self,
        timestamp: str,
        available: Optional[float],
        pv: Optional[float],
        load: Optional[float],
        current: float,
        target: float,
    ) -> None:
        sample = {
            "ts": timestamp,
            "available": available,
            "pv": pv,
            "load": load,
            "current": current,
            "target": target,
        }
        self.energy_history.append(sample)
        if len(self.energy_history) > HISTORY_LIMIT:
            self.energy_history = self.energy_history[-HISTORY_LIMIT:]

    def _energy_map(
        self, current_watts: float, target_watts: float, available_power: Optional[float]
    ) -> Dict[str, object]:
        steps = [
            {"amps": amps, "watts": amps * self.runtime_config.controller.line_voltage_v}
            for amps in EVSE_STEPS_AMPS
        ]
        return {
            "history": list(self.energy_history[-HISTORY_LIMIT:]),
            "evse_steps": steps,
            "current_watts": current_watts,
            "target_watts": target_watts,
            "available_power": available_power,
            "inverter_limit": self.runtime_config.controller.inverter_limit_w,
            "battery_guard_soc": self.runtime_config.controller.soc_main_max,
        }

    def _limiting_factors(self, inputs: Inputs, derived) -> List[str]:
        factors: List[str] = []
        if not derived.ev_plugged:
            factors.append("car_unplugged")
        if not inputs.auto_enabled:
            factors.append("auto_disabled")
        if derived.inverter_over_limit:
            factors.append("inverter_limit")
        if derived.waiting_timed_out:
            factors.append("vehicle_waiting")
        return factors

    def _auto_state(self, step_index: int, inputs: Inputs, derived) -> str:
        if step_index > 0:
            return "charging"
        if not derived.ev_plugged:
            return "waiting_for_vehicle"
        if not inputs.auto_enabled:
            return "auto_disabled"
        return "idle"

    def _auto_state_label(self, step_index: int, inputs: Inputs, derived) -> str:
        mapping = {
            "charging": "Charging",
            "waiting_for_vehicle": "Waiting for vehicle",
            "auto_disabled": "Auto disabled",
            "idle": "Idle",
        }
        return mapping.get(self._auto_state(step_index, inputs, derived), "Idle")

    def _auto_state_help(self, step_index: int, inputs: Inputs, derived) -> str:
        state = self._auto_state(step_index, inputs, derived)
        if state == "charging":
            return "EVSE drawing solar-limited current."
        if state == "waiting_for_vehicle":
            return "Plug a vehicle into the charger to resume control."
        if state == "auto_disabled":
            return "Auto-enable boolean is off; controller is holding the EVSE."
        return "Controller is monitoring sensors for solar headroom."


def main() -> None:
    service = ControlService()
    service.run_forever()


if __name__ == "__main__":
    main()
