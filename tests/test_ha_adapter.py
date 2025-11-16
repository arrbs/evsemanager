"""Tests for HomeAssistantAdapter switch jiggle behaviour."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "evse_manager" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from controller_config import EntityConfig  # noqa: E402
from ha_adapter import HomeAssistantAdapter  # noqa: E402
from state_machine import ControllerState, Decision  # noqa: E402


class FakeAPI:
    """Simple HA API stub that simulates an EVSE needing multiple ON pulses."""

    def __init__(self):
        self.turn_on_calls = 0
        self.turn_off_calls = 0
        self.state = "off"
        self.calls = []

    def call_service(self, domain, service, **kwargs):
        self.calls.append((domain, service, kwargs))
        if domain == "switch" and service == "turn_on":
            self.turn_on_calls += 1
            # Only latch after the second ON pulse
            self.state = "on" if self.turn_on_calls >= 2 else "off"
        elif domain == "switch" and service == "turn_off":
            self.turn_off_calls += 1
            self.state = "off"
        return True

    def get_state(self, entity_id):  # pylint: disable=unused-argument
        return self.state


def make_entity_config(**overrides):
    defaults = dict(
        charger_switch="switch.test_evse",
        charger_current="number.test_current",
        charger_status="sensor.test_status",
        battery_soc=None,
        battery_power=None,
        inverter_power=None,
        pv_power=None,
        auto_enabled=None,
        auto_enabled_default=True,
        switch_jiggle_attempts=2,
        switch_jiggle_delay_s=0.0,
    )
    defaults.update(overrides)
    return EntityConfig(**defaults)


class HomeAssistantAdapterJiggleTests(unittest.TestCase):
    """Ensure the adapter handles the EVSE switch jiggle outside the FSM."""

    def setUp(self):
        self.api = FakeAPI()
        self.entity_cfg = make_entity_config()
        self.adapter = HomeAssistantAdapter(self.api, self.entity_cfg, sleep_fn=lambda _delay: None)

    def _decision(self, *, switch_on: bool) -> Decision:
        return Decision(
            new_state=ControllerState(),
            switch_command=switch_on,
            current_command_amps=None,
            reason="test",
            metadata={},
        )

    def test_jiggle_attempts_until_switch_latches(self):
        """Adapter should pulse ON multiple times until the switch reports on."""

        self.adapter.apply_decision(self._decision(switch_on=True))
        self.assertGreaterEqual(self.api.turn_on_calls, 2)
        self.assertEqual(self.api.state, "on")

    def test_turn_off_bypasses_jiggle(self):
        """Turning off should call the switch service only once and not jiggle."""

        self.adapter.apply_decision(self._decision(switch_on=False))
        self.assertEqual(self.api.turn_off_calls, 1)
        self.assertEqual(self.api.turn_on_calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
