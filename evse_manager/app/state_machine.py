"""Deterministic EVSE state machine implementation."""
from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

EVSE_STEPS_AMPS = [0, 6, 8, 10, 13, 16, 20, 24]
AMP_TO_INDEX = {amp: idx for idx, amp in enumerate(EVSE_STEPS_AMPS)}


class ModeState(enum.Enum):
    """FSM macro states for the controller."""

    OFF = "OFF"
    MAIN_READY = "MAIN_READY"
    MAIN_COOLDOWN = "MAIN_COOLDOWN"
    PROBE_READY = "PROBE_READY"
    PROBE_COOLDOWN = "PROBE_COOLDOWN"


@dataclass(frozen=True)
class ControllerConfig:
    """Immutable constants that shape the FSM behaviour."""

    line_voltage_v: float = 230.0
    soc_main_max: float = 95.0
    soc_conservative_below: float = 94.0
    small_discharge_margin_w: float = 200.0
    conservative_charge_target_w: float = 100.0
    probe_max_discharge_w: float = 1000.0
    inverter_limit_w: float = 8000.0
    inverter_margin_w: float = 500.0
    cooldown_s: float = 5.0
    waiting_timeout_s: float = 60.0
    sensor_latency_s: float = 25.0

    @property
    def safe_inverter_max_w(self) -> float:
        return self.inverter_limit_w - self.inverter_margin_w


@dataclass(frozen=True)
class ControllerState:
    """Internal state tracked by the FSM."""

    mode_state: ModeState = ModeState.OFF
    evse_step_index: int = 0
    last_change_ts_s: float = 0.0
    waiting_since_ts_s: Optional[float] = None
    pending_effect_ts_s: Optional[float] = None


@dataclass(frozen=True)
class Inputs:
    """Snapshot of upstream entity values for a single tick."""

    batt_soc_percent: Optional[float]
    batt_power_w: Optional[float]
    inverter_power_w: Optional[float]
    pv_power_w: Optional[float]
    charger_status: str
    charger_switch_on: bool
    charger_current_a: Optional[float]
    auto_enabled: bool
    now_s: float


def _ev_plugged(status: str) -> bool:
    return status.lower() != "available"


@dataclass(frozen=True)
class DerivedValues:
    """Derived helpers computed from inputs and state."""

    region: str
    ev_plugged: bool
    excess_w: Optional[float]
    inverter_over_limit: bool
    cooldown_active: bool
    time_since_last_change: float
    waiting_timed_out: bool
    effect_ready: bool


@dataclass(frozen=True)
class Decision:
    """Represents a single FSM action outcome."""

    new_state: ControllerState
    switch_command: Optional[bool]
    current_command_amps: Optional[int]
    reason: str
    metadata: Dict[str, float]

    @property
    def requires_side_effects(self) -> bool:
        return self.switch_command is not None or self.current_command_amps is not None


class DeterministicStateMachine:
    """Single-owner deterministic FSM for EVSE control."""

    def __init__(self, config: ControllerConfig):
        self.config = config
        self.state = ControllerState()

    def sync_with_charger(self, inputs: Inputs) -> None:
        """Synchronize FSM state with actual charger state on startup.
        
        If the charger is already charging when the add-on starts, this method
        detects the current amperage and initializes the FSM to match, allowing
        it to take ownership of the existing session.
        """
        # Only sync if we're in the initial OFF state
        if self.state.evse_step_index != 0:
            return
        
        # Check if charger is actually charging
        status = inputs.charger_status.lower()
        if status not in {"charging", "connected"}:
            return
        
        # Try to match current amperage to a step
        if inputs.charger_current_a is None or inputs.charger_current_a < 1:
            return
        
        # Find the closest step index for the current amperage
        current_amps = inputs.charger_current_a
        best_index = 0
        min_diff = float('inf')
        
        for idx, step_amps in enumerate(EVSE_STEPS_AMPS):
            if idx == 0:  # Skip the OFF step
                continue
            diff = abs(step_amps - current_amps)
            if diff < min_diff:
                min_diff = diff
                best_index = idx
        
        # Only sync if we found a reasonable match (within 3A)
        if best_index > 0 and min_diff <= 3:
            region = self._region_for_soc(inputs.batt_soc_percent)
            mode_state = ModeState.MAIN_READY if region == "MAIN" else ModeState.PROBE_READY
            
            self.state = ControllerState(
                mode_state=mode_state,
                evse_step_index=best_index,
                last_change_ts_s=inputs.now_s,
                waiting_since_ts_s=None,
                pending_effect_ts_s=None,
            )

    def tick(self, inputs: Inputs) -> Tuple[Optional[Decision], DerivedValues]:
        derived = self._derive(inputs)
        self._detect_external_changes(inputs)
        self._sync_mode_state(derived.region, derived.cooldown_active)
        decision = self._evaluate_rules(inputs, derived)
        if decision:
            self.state = decision.new_state
        return decision, derived

    def _detect_external_changes(self, inputs: Inputs) -> None:
        """Detect if charger current was changed externally and resync state."""
        if inputs.charger_current_a is None or inputs.charger_current_a < 1:
            return
        
        # Check if actual current differs significantly from our expected step
        expected_amps = EVSE_STEPS_AMPS[self.state.evse_step_index]
        actual_amps = inputs.charger_current_a
        diff = abs(expected_amps - actual_amps)
        
        # If we're OFF but the charger is delivering current, or difference > 2A, resync
        if self.state.evse_step_index == 0 and actual_amps >= 1:
            diff = actual_amps  # force resync logic below
        if diff > 2:
            # Find the closest matching step
            best_index = 0
            min_diff = float('inf')
            
            for idx, step_amps in enumerate(EVSE_STEPS_AMPS):
                step_diff = abs(step_amps - actual_amps)
                if step_diff < min_diff:
                    min_diff = step_diff
                    best_index = idx
            
            # Update our state to match reality (within 3A tolerance)
            if min_diff <= 3:
                region = self._region_for_soc(inputs.batt_soc_percent)
                if best_index == 0:
                    mode_state = ModeState.OFF
                else:
                    mode_state = ModeState.MAIN_READY if region == "MAIN" else ModeState.PROBE_READY
                
                self.state = replace(
                    self.state,
                    evse_step_index=best_index,
                    mode_state=mode_state,
                    last_change_ts_s=inputs.now_s,
                    pending_effect_ts_s=None,
                )

    def _derive(self, inputs: Inputs) -> DerivedValues:
        target_region = self._region_for_soc(inputs.batt_soc_percent)
        time_since_last_change = max(0.0, inputs.now_s - self.state.last_change_ts_s)
        cooldown_active = time_since_last_change < self.config.cooldown_s
        inverter_over = False
        if inputs.inverter_power_w is not None:
            inverter_over = inputs.inverter_power_w > self.config.safe_inverter_max_w
        excess = None
        if target_region == "MAIN":
            if inputs.pv_power_w is not None and inputs.inverter_power_w is not None:
                excess = inputs.pv_power_w - inputs.inverter_power_w
            elif inputs.batt_power_w is not None:
                # Fallback: infer excess from battery flow when PV sensor unavailable.
                # Positive battery power means discharge (deficit), negative means charging (surplus).
                excess = -inputs.batt_power_w
        waiting_timed_out = False
        if self.state.waiting_since_ts_s is not None:
            waiting_timed_out = (inputs.now_s - self.state.waiting_since_ts_s) > self.config.waiting_timeout_s

        effect_ready = True
        pending_ts = self.state.pending_effect_ts_s
        if pending_ts is not None:
            effect_ready = (inputs.now_s - pending_ts) >= self.config.sensor_latency_s
            if effect_ready:
                self.state = replace(self.state, pending_effect_ts_s=None)
        return DerivedValues(
            region=target_region,
            ev_plugged=_ev_plugged(inputs.charger_status),
            excess_w=excess,
            inverter_over_limit=inverter_over,
            cooldown_active=cooldown_active,
            time_since_last_change=time_since_last_change,
            waiting_timed_out=waiting_timed_out,
            effect_ready=effect_ready,
        )

    def _sync_mode_state(self, region: str, cooldown_active: bool) -> None:
        desired = self._desired_mode_state(region, cooldown_active)
        if self.state.mode_state != desired:
            self.state = replace(self.state, mode_state=desired)

    def _desired_mode_state(self, region: str, cooldown_active: bool) -> ModeState:
        if self.state.evse_step_index == 0:
            return ModeState.OFF
        if region == "MAIN":
            return ModeState.MAIN_COOLDOWN if cooldown_active else ModeState.MAIN_READY
        return ModeState.PROBE_COOLDOWN if cooldown_active else ModeState.PROBE_READY

    def _region_for_soc(self, batt_soc: Optional[float]) -> str:
        if batt_soc is None:
            return "MAIN"
        if batt_soc >= self.config.soc_main_max:
            return "PROBE"
        return "MAIN"

    def _evaluate_rules(self, inputs: Inputs, derived: DerivedValues) -> Optional[Decision]:
        self._update_waiting_timer(inputs)
        decision = self._global_rules(inputs, derived)
        if decision:
            return decision
        if self.state.mode_state == ModeState.OFF:
            if derived.cooldown_active:
                return None
            if derived.region == "MAIN":
                return self._main_start_logic(inputs, derived)
            return self._probe_start_logic(inputs, derived)
        if self.state.mode_state in {ModeState.MAIN_COOLDOWN, ModeState.PROBE_COOLDOWN}:
            return None
        decision = self._inverter_emergency(inputs, derived)
        if decision:
            return decision
        if derived.region == "MAIN":
            return self._main_ready_logic(inputs, derived)
        return self._probe_ready_logic(inputs, derived)

    def _update_waiting_timer(self, inputs: Inputs) -> None:
        status = inputs.charger_status.lower()
        if status == "waiting":
            if self.state.waiting_since_ts_s is None:
                self.state = replace(self.state, waiting_since_ts_s=inputs.now_s)
        else:
            if self.state.waiting_since_ts_s is not None:
                self.state = replace(self.state, waiting_since_ts_s=None)

    def _global_rules(self, inputs: Inputs, derived: DerivedValues) -> Optional[Decision]:
        status = inputs.charger_status.lower()
        if status == "fault":
            return self._force_off(inputs, reason="fault_state", latch_wait=True)
        if derived.waiting_timed_out:
            return self._force_off(inputs, reason="waiting_timeout", latch_wait=True)
        if not derived.ev_plugged or not inputs.auto_enabled:
            reason = "ev_unplugged" if not derived.ev_plugged else "auto_disabled"
            return self._force_off(inputs, reason=reason, latch_wait=False)
        return None

    def _force_off(self, inputs: Inputs, reason: str, latch_wait: bool) -> Decision:
        waiting_ts = self.state.waiting_since_ts_s if latch_wait else None
        new_state = ControllerState(
            mode_state=ModeState.OFF,
            evse_step_index=0,
            last_change_ts_s=inputs.now_s,
            waiting_since_ts_s=waiting_ts,
            pending_effect_ts_s=None,
        )
        soc_value = inputs.batt_soc_percent if inputs.batt_soc_percent is not None else 0.0
        return Decision(
            new_state=new_state,
            switch_command=False,
            current_command_amps=None,
            reason=reason,
            metadata={"soc": soc_value},
        )

    def _main_start_logic(self, inputs: Inputs, derived: DerivedValues) -> Optional[Decision]:
        if derived.excess_w is None:
            return None
        threshold = EVSE_STEPS_AMPS[1] * self.config.line_voltage_v
        if derived.excess_w < threshold:
            return None
        if not self._inverter_safe(inputs, 0):
            return None
        return self._set_step(inputs, new_index=1, reason="main_start")

    def _probe_start_logic(self, inputs: Inputs, _derived: DerivedValues) -> Optional[Decision]:
        batt_power = inputs.batt_power_w
        if batt_power is None:
            return None
        if batt_power > 0:
            return None
        if not self._inverter_safe(inputs, 0):
            return None
        return self._set_step(inputs, new_index=1, reason="probe_start")

    def _inverter_emergency(self, inputs: Inputs, derived: DerivedValues) -> Optional[Decision]:
        if self.state.evse_step_index == 0:
            return None
        if not derived.inverter_over_limit:
            return None
        if self.state.evse_step_index == 1:
            return self._set_step(inputs, 0, "inverter_drop")
        return self._set_step(inputs, self.state.evse_step_index - 1, "inverter_step_down")

    def _main_ready_logic(self, inputs: Inputs, derived: DerivedValues) -> Optional[Decision]:
        # Determine if we're in conservative mode (SOC below guard threshold)
        conservative_mode = self._is_conservative_mode(inputs.batt_soc_percent)
        
        # If in conservative mode but can't determine excess, use battery power as fallback
        if conservative_mode and self.state.evse_step_index > 0:
            if derived.excess_w is None and inputs.batt_power_w is not None:
                # If battery is discharging in conservative mode, step down
                if inputs.batt_power_w > 50:  # Discharging more than 50W
                    next_index = max(0, self.state.evse_step_index - 1)
                    return self._set_step(inputs, next_index, "main_conservative_batt_discharge")
        
        # Step-up path
        if self.state.evse_step_index > 0 and derived.excess_w is not None:
            if self.state.evse_step_index < len(EVSE_STEPS_AMPS) - 1:
                required = self._step_up_power(self.state.evse_step_index)
                if (
                    derived.effect_ready
                    and derived.excess_w >= required
                    and self._inverter_safe(inputs, self.state.evse_step_index)
                ):
                    return self._set_step(inputs, self.state.evse_step_index + 1, "main_step_up")
            
            # Hold region - use different thresholds based on conservative mode
            if conservative_mode:
                # When SOC is below conservative threshold, prefer small charging over discharge
                # Step down if we're discharging (excess is negative)
                # Hold if we're charging at least the target amount
                if derived.excess_w >= self.config.conservative_charge_target_w:
                    return None
                # Step down if not meeting the conservative charge target
                if derived.excess_w < self.config.conservative_charge_target_w:
                    next_index = max(0, self.state.evse_step_index - 1)
                    return self._set_step(inputs, next_index, "main_conservative_step_down")
            else:
                # Normal mode: allow small discharge margin
                if derived.excess_w >= -self.config.small_discharge_margin_w:
                    return None
                # Step-down when exceeding discharge margin
                if derived.excess_w < -self.config.small_discharge_margin_w:
                    next_index = max(0, self.state.evse_step_index - 1)
                    return self._set_step(inputs, next_index, "main_step_down")
        return None

    def _is_conservative_mode(self, batt_soc: Optional[float]) -> bool:
        """Check if SOC is below the conservative threshold."""
        if batt_soc is None:
            return False
        return batt_soc < self.config.soc_conservative_below

    def _probe_ready_logic(self, inputs: Inputs, derived: DerivedValues) -> Optional[Decision]:
        batt_power = inputs.batt_power_w
        if batt_power is None:
            return None
        if self.state.evse_step_index == 0:
            return None
        if batt_power <= 0:
            if (
                self.state.evse_step_index < len(EVSE_STEPS_AMPS) - 1
                and derived.effect_ready
                and self._inverter_safe(inputs, self.state.evse_step_index)
            ):
                return self._set_step(inputs, self.state.evse_step_index + 1, "probe_step_up")
            return None
        if 0 < batt_power <= self.config.probe_max_discharge_w:
            return None
        next_index = max(0, self.state.evse_step_index - 1)
        return self._set_step(inputs, next_index, "probe_step_down")

    def _inverter_safe(self, inputs: Inputs, index: int) -> bool:
        if inputs.inverter_power_w is None:
            return True
        projected = inputs.inverter_power_w + self._step_up_power(index)
        return projected <= self.config.safe_inverter_max_w

    def _step_up_power(self, index: int) -> float:
        next_amp = EVSE_STEPS_AMPS[index + 1]
        curr_amp = EVSE_STEPS_AMPS[index]
        return (next_amp - curr_amp) * self.config.line_voltage_v

    def _set_step(self, inputs: Inputs, new_index: int, reason: str) -> Decision:
        new_index = max(0, min(new_index, len(EVSE_STEPS_AMPS) - 1))
        old_index = self.state.evse_step_index
        target_mode = ModeState.OFF
        if new_index == 0:
            target_mode = ModeState.OFF
        else:
            region = self._region_for_soc(inputs.batt_soc_percent)
            target_mode = ModeState.MAIN_COOLDOWN if region == "MAIN" else ModeState.PROBE_COOLDOWN

        pending_effect_ts_s = self.state.pending_effect_ts_s
        if new_index > old_index:
            pending_effect_ts_s = inputs.now_s
        elif new_index < old_index or new_index == 0:
            pending_effect_ts_s = None

        new_state = ControllerState(
            mode_state=target_mode,
            evse_step_index=new_index,
            last_change_ts_s=inputs.now_s,
            waiting_since_ts_s=self.state.waiting_since_ts_s,
            pending_effect_ts_s=pending_effect_ts_s,
        )
        target_current = EVSE_STEPS_AMPS[new_index] if new_index > 0 else None
        switch_command = None
        if new_index == 0:
            switch_command = False
        else:
            switch_command = True
        metadata = {"index": float(new_index)}
        if target_current is not None:
            metadata["target_amps"] = float(target_current)
        return Decision(
            new_state=new_state,
            switch_command=switch_command,
            current_command_amps=target_current,
            reason=reason,
            metadata=metadata,
        )
