"""Tick-level tests for DeterministicStateMachine."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "evse_manager" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from state_machine import (  # noqa: E402  # pylint: disable=wrong-import-position
    ControllerConfig,
    DeterministicStateMachine,
    Inputs,
)


def make_inputs(
    *,
    now_s: float,
    pv_power_w: float,
    inverter_power_w: float,
    batt_power_w: float = -500.0,
    batt_soc_percent: float = 60.0,
    charger_status: str = "charging",
    auto_enabled: bool = True,
) -> Inputs:
    """Helper to create an Inputs snapshot with sane defaults."""

    return Inputs(
        batt_soc_percent=batt_soc_percent,
        batt_power_w=batt_power_w,
        inverter_power_w=inverter_power_w,
        pv_power_w=pv_power_w,
        charger_status=charger_status,
        charger_switch_on=True,
        charger_current_a=None,
        auto_enabled=auto_enabled,
        now_s=now_s,
    )


class DeterministicStateMachineTests(unittest.TestCase):
    """Exercise key FSM behaviours without touching Home Assistant."""

    def setUp(self) -> None:
        self.config = ControllerConfig()
        self.machine = DeterministicStateMachine(self.config)

    def test_cooldown_enforced_between_step_changes(self) -> None:
        """Controller must wait at least cooldown_s before the next ramp."""

        decision, _ = self.machine.tick(
            make_inputs(now_s=100.0, pv_power_w=6000.0, inverter_power_w=2000.0)
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.current_command_amps, 6)
        self.assertEqual(self.machine.state.evse_step_index, 1)

        # Next tick occurs before cooldown expires – no adjustments allowed
        decision, _ = self.machine.tick(
            make_inputs(now_s=102.0, pv_power_w=6000.0, inverter_power_w=2000.0)
        )
        self.assertIsNone(decision)
        self.assertEqual(self.machine.state.evse_step_index, 1)

        # Cooldown expired but sensor latency window still active – hold position
        decision, _ = self.machine.tick(
            make_inputs(now_s=110.0, pv_power_w=8000.0, inverter_power_w=2500.0)
        )
        self.assertIsNone(decision)
        self.assertEqual(self.machine.state.evse_step_index, 1)

        # Once both cooldown and latency windows are satisfied, the controller can step up
        decision, _ = self.machine.tick(
            make_inputs(now_s=130.0, pv_power_w=8000.0, inverter_power_w=2500.0)
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.current_command_amps, 8)
        self.assertEqual(self.machine.state.evse_step_index, 2)

    def test_inverter_safety_blocks_start_when_margin_exceeded(self) -> None:
        """Starting from OFF should honour inverter safety checks."""

        decision, _ = self.machine.tick(
            make_inputs(now_s=200.0, pv_power_w=7000.0, inverter_power_w=7000.0)
        )
        self.assertIsNone(decision)
        self.assertEqual(self.machine.state.evse_step_index, 0)

        # Once inverter load drops, the controller may start safely
        decision, _ = self.machine.tick(
            make_inputs(now_s=210.0, pv_power_w=7000.0, inverter_power_w=5000.0)
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.current_command_amps, 6)
        self.assertEqual(self.machine.state.evse_step_index, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
