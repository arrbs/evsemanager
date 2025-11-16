"""Configuration loading helpers for the deterministic controller."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from state_machine import ControllerConfig


@dataclass(frozen=True)
class EntityConfig:
    charger_switch: str
    charger_current: str
    charger_status: str
    battery_soc: Optional[str]
    battery_power: Optional[str]
    inverter_power: Optional[str]
    pv_power: Optional[str]
    auto_enabled: Optional[str]
    auto_enabled_default: bool


@dataclass(frozen=True)
class RuntimeConfig:
    tick_seconds: float
    controller: ControllerConfig
    entities: EntityConfig
    log_level: str


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_runtime_config(path: Path = Path("/data/options.json")) -> RuntimeConfig:
    data = _read_json(path)

    def _extract(key: str, default=None):
        if key in data:
            return data[key]
        return default

    def _from_nested(parent: str, key: str, default=None):
        if parent in data and isinstance(data[parent], dict):
            return data[parent].get(key, default)
        return default

    entities = data.get("entities", {})

    charger_switch = (
        entities.get("charger_switch")
        or _extract("charger_switch")
        or _from_nested("charger", "switch_entity")
        or "switch.ev_charger"
    )
    charger_current = (
        entities.get("charger_current")
        or _extract("charger_current")
        or _from_nested("charger", "current_entity")
        or "number.ev_charger_set_current"
    )
    charger_status = (
        entities.get("charger_status")
        or _extract("charger_status")
        or _from_nested("charger", "status_entity")
        or "sensor.ev_charger_status"
    )

    battery_soc = (
        entities.get("battery_soc")
        or _extract("battery_soc")
        or _from_nested("sensors", "battery_soc_entity")
    )
    battery_power = (
        entities.get("battery_power")
        or _extract("battery_power")
        or _from_nested("sensors", "battery_power_entity")
    )
    inverter_power = (
        entities.get("inverter_power")
        or _extract("inverter_power")
        or _from_nested("sensors", "inverter_power_entity")
    )
    pv_power = (
        entities.get("pv_power")
        or _extract("total_pv_power")
        or _from_nested("sensors", "total_pv_entity")
    )
    auto_enabled_entity = entities.get("auto_enabled") or _extract("auto_enabled_entity")
    auto_enabled_default = bool(_extract("auto_enabled_default", True))

    controller_cfg = ControllerConfig(
        line_voltage_v=float(_extract("line_voltage_v", 230)),
        soc_main_max=float(_extract("soc_main_max", 95.0)),
        small_discharge_margin_w=float(_extract("small_discharge_margin_w", 200)),
        probe_max_discharge_w=float(_extract("probe_max_discharge_w", 1000)),
        inverter_limit_w=float(
            _extract(
                "inverter_limit_w",
                _from_nested("sensors", "inverter_max_power", 8000),
            )
        ),
        inverter_margin_w=float(_extract("inverter_margin_w", 500)),
        cooldown_s=float(_extract("cooldown_s", 5)),
        waiting_timeout_s=float(_extract("waiting_timeout_s", 60)),
    )

    tick_seconds = float(
        _extract("tick_seconds", _from_nested("control", "update_interval", 2))
    )
    tick_seconds = max(1.0, min(2.0, tick_seconds))

    entities_cfg = EntityConfig(
        charger_switch=charger_switch,
        charger_current=charger_current,
        charger_status=charger_status,
        battery_soc=battery_soc,
        battery_power=battery_power,
        inverter_power=inverter_power,
        pv_power=pv_power,
        auto_enabled=auto_enabled_entity,
        auto_enabled_default=auto_enabled_default,
    )

    log_level = str(_extract("log_level", "INFO")).upper()

    return RuntimeConfig(
        tick_seconds=tick_seconds,
        controller=controller_cfg,
        entities=entities_cfg,
        log_level=log_level,
    )
