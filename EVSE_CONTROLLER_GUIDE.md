# EVSE Controller – Deterministic State Machine Implementation Guide

This document describes the authoritative control model for an EVSE controller that cooperates with Home Assistant. It assumes that the Web UI in this repository remains read-only; the logic outlined here is provided so that integrators can rebuild a deterministic controller that obeys strict safety and predictability rules.

---

## 0. Design Philosophy

- **Single explicit FSM**: Exactly one finite state machine owns every EVSE decision. No hidden sub-modes, no parallel automations.
- **Deterministic**: Identical inputs and state at tick `t` must always yield identical outputs.
- **Side-effect isolation**: Compute the full decision first, then emit Home Assistant service calls.
- **No racing**: The add-on’s control loop is the sole authority over the EVSE entities listed below.

---

## 1. Runtime Model

### 1.1 Periodic Tick Loop

- Tick period configurable between 1–2 seconds (default 2 s).
- Each tick performs the following stages:
  1. **Read** every required Home Assistant entity exactly once via a thin adapter.
  2. **Derive** helper values (excess wattage, cooldown timers, etc.).
  3. **Decide** by running the pure FSM evaluation.
  4. **Act** by issuing service calls based on the FSM’s chosen action set.
- No other automation/script may touch:
  - `switch.ev_charger`
  - `number.ev_charger_set_current`
  - `input_select.evse_mode_state` (if exposed)
  - `input_number.evse_step_index` (if exposed)

### 1.2 Monotonic Time Handling

- Use a monotonic clock for all timing logic (`now_s`).
- Track `last_change_ts_s` (timestamp of the most recent EVSE step or power command).
- Derived cooldown timer: `time_since_last_change = now_s - last_change_ts_s`.
- Cooldown rule: do not change EVSE state until `time_since_last_change ≥ 5` seconds.

---

## 2. Home Assistant Entities & Semantics

### 2.1 EVSE Entities

| Entity | Meaning |
| --- | --- |
| `switch.ev_charger` | `on` = EVSE energized, `off` = EVSE disabled. |
| `sensor.ev_charger_status` | `available`, `charging`, `charged`, `waiting`, `fault`. |
| `number.ev_charger_set_current` | Integer amps; must match supported steps. |

Behavioral notes:
- `fault`: force OFF and remain there until cleared.
- `waiting`: treat as transient; if it persists >60 s, force OFF similar to fault.
- `charged`: EV plugged in but idle; controller may still adjust current/switch.
- `available`: EV unplugged, so controller must shut everything down.

### 2.2 Power / Battery / Inverter Entities

| Entity | Derived Symbol | Notes |
| --- | --- | --- |
| `sensor.ss_battery_soc` | `BattSOC_percent` | Float 0–100. |
| `sensor.ss_battery_power` | `BattP_W` | Positive = discharging, negative = charging. |
| `sensor.ss_inverter_power` | `Inv_W` | AC load seen by inverter, includes EVSE draw. |
| `sensor.total_pv_power` | `PV_W` | Trust only while `BattSOC_percent < 95`. |

### 2.3 Auto-enable Flag

Expose `AUTO_ENABLED` (e.g., `input_boolean.evse_auto_enabled`). When false, the FSM must force OFF.

### 2.4 Plug Detection

`EV_PLUGGED = (sensor.ev_charger_status != "available")`.

---

## 3. Internal Representation

### 3.1 EVSE Steps

- `EVSE_STEPS_AMPS = [0, 6, 8, 10, 13, 16, 20, 24]` (index 0 = logical OFF).
- Helper lookups:
  - `amps(i)` → `EVSE_STEPS_AMPS[i]`.
  - `index_of_amps(a)` (precomputed dict).
  - `step_up_power_W(i) = (EVSE_STEPS_AMPS[i+1] - EVSE_STEPS_AMPS[i]) * LINE_VOLTAGE_V`.

### 3.2 FSM State Variables

- `mode_state ∈ {OFF, MAIN_READY, MAIN_COOLDOWN, PROBE_READY, PROBE_COOLDOWN}`.
- `evse_step_index ∈ [0..7]`.
- `last_change_ts_s` (monotonic seconds).

### 3.3 Constants (configurable but immutable at runtime)

| Constant | Default | Purpose |
| --- | --- | --- |
| `LINE_VOLTAGE_V` | 230 | Used for power-step calculations. |
| `SOC_MAIN_MAX` | 95.0 | MAIN vs PROBE split threshold. |
| `SMALL_DISCHARGE_MARGIN_W` | 200 | Allowed discharge before stepping down. |
| `MIN_ACTIVE_AMPS` | 6 | Lowest EVSE step to hold before powering off. |
| `PROBE_MAX_DISCHARGE_W` | 1000 | Max discharge in PROBE mode before stepping down. |
| `INVERTER_LIMIT_W` | 8000 | Inverter hard limit. |
| `INVERTER_MARGIN_W` | 500 | Safety margin. |
| `COOLDOWN_S` | 5 | Mandatory delay between adjustments. |

Derived: `SAFE_INVERTER_MAX_W = INVERTER_LIMIT_W - INVERTER_MARGIN_W`.

For MAIN mode only: `Excess_W = PV_W - Inv_W` (valid when `BattSOC_percent < SOC_MAIN_MAX`).

---

## 4. State Definitions & Invariants

All invariants are mandatory; violation indicates a bug.

| State | Requirements |
| --- | --- |
| **OFF** | `evse_step_index = 0`, `switch.ev_charger = off`. |
| **MAIN_READY** | `BattSOC_percent < SOC_MAIN_MAX`, PV trustworthy, cooldown satisfied. |
| **MAIN_COOLDOWN** | Same SOC region as MAIN_READY but still inside cooldown. |
| **PROBE_READY** | `BattSOC_percent ≥ SOC_MAIN_MAX`, PV curtailed, cooldown satisfied. |
| **PROBE_COOLDOWN** | Same as PROBE_READY but within cooldown window. |

---

## 5. Rule Priority & Evaluation Order

At every tick, evaluate rules in strict priority order. Apply the first matching rule, perform its actions, update internal state, then stop for this tick.

### 5.1 Global / Safety Rules

1. **Fault handling**
   - If `sensor.ev_charger_status == "fault"`, force OFF, move to `OFF`, freeze adjustments until the status clears.
2. **Waiting timeout**
   - Track duration spent in `"waiting"`; if >60 s, treat as fault.
3. **Unplugged or auto-disabled**
   - If `EV_PLUGGED == false` or `AUTO_ENABLED == false`, force OFF, update `last_change_ts_s`, move to `OFF`.

### 5.2 Inverter Protection Rules

Evaluated inside MAIN_READY or PROBE_READY before any step-up logic:

- **Emergency downstep**: if `evse_step_index > 0` and `Inv_W > SAFE_INVERTER_MAX_W`, reduce current (or switch off if already at 6 A) and enter the corresponding cooldown state.
- **Step-up safety constraint**: stepping up is only legal when `Inv_W + step_up_power_W(evse_step_index) ≤ SAFE_INVERTER_MAX_W`.

---

## 6. Mode Selection

Mode changes never adjust EVSE steps directly; they only move between MAIN and PROBE readiness states.

- If `BattSOC_percent ≥ SOC_MAIN_MAX`, collapse MAIN states into PROBE equivalents (respect cooldown).
- If `BattSOC_percent < SOC_MAIN_MAX`, collapse PROBE states into MAIN equivalents (respect cooldown).

---

## 7. MAIN Mode Logic (BattSOC < 95%)

Only MAIN_READY may change EVSE steps.

### 7.1 Starting from OFF

Conditions:
- `evse_step_index == 0`.
- `Excess_W ≥ 6 * LINE_VOLTAGE_V` (~1380 W).
- Cooldown satisfied.

Action: step to 6 A, turn switch on, set number entity, update timestamps, transition to MAIN_COOLDOWN.

### 7.2 Step-up (>0 and <24 A)

Conditions:
- `0 < evse_step_index < max_index`.
- `Excess_W ≥ step_up_power_W(evse_step_index)`.
- `Inv_W + step_up_power_W(evse_step_index) ≤ SAFE_INVERTER_MAX_W`.
- Cooldown satisfied.

Action: increase index by one, set current, maintain switch on, update timestamps, transition to MAIN_COOLDOWN.

### 7.3 Hold Region

Conditions:
- `evse_step_index > 0`.
- `-SMALL_DISCHARGE_MARGIN_W ≤ Excess_W < step_up_power_W(evse_step_index)`.

Action: no change; remain in MAIN_READY.

### 7.4 Step-down

Trigger: `Excess_W < -SMALL_DISCHARGE_MARGIN_W`.

- If `evse_step_index` is above the `MIN_ACTIVE_AMPS` step, decrement index by one, keep the switch on, set current, update timestamps.
- If already at or below `MIN_ACTIVE_AMPS`, shut off (index 0, switch off) as a last resort.
- Always enter MAIN_COOLDOWN after a downstep.

### 7.5 Max Step Behavior

At 24 A, follow the same rules: hold if safe, otherwise downstep when discharge margin exceeded or inverter unsafe.

---

## 8. PROBE Mode Logic (BattSOC ≥ 95%)

PV wattage is curtailed, so decisions use `BattP_W` instead of `Excess_W`. Only PROBE_READY may change steps.

### 8.1 Starting from OFF

Conditions:
- `evse_step_index == 0`.
- `BattP_W ≤ 0` (battery charging or flat).
- Cooldown satisfied.

Action: ramp to 6 A, switch on, set number, update timestamps, enter PROBE_COOLDOWN.

### 8.2 Step-up

Conditions:
- `0 < evse_step_index < max_index`.
- `BattP_W ≤ 0`.
- `Inv_W + step_up_power_W(evse_step_index) ≤ SAFE_INVERTER_MAX_W`.
- Cooldown satisfied.

Action: increment step, set number, enter PROBE_COOLDOWN.

### 8.3 Hold Band

Conditions:
- `evse_step_index > 0`.
- `0 < BattP_W ≤ PROBE_MAX_DISCHARGE_W`.

Action: hold PROBE_READY.

### 8.4 Step-down (Over-discharging)

Trigger: `BattP_W > PROBE_MAX_DISCHARGE_W`.

- If above the `MIN_ACTIVE_AMPS` step, decrement index, keep the switch on, set number, enter PROBE_COOLDOWN.
- If already at or below `MIN_ACTIVE_AMPS`, shut off (index 0) as a last resort to stop battery discharge.

---

## 9. Handling `charged` / `available`

- `charged`: optional nicety—slowly drift back to 6 A when idle so the next session starts at a safe minimum, but no special rule is required beyond the core FSM.
- `available`: treat as unplugged (global OFF rule applies). Pre-setting `number.ev_charger_set_current` to 6 A is acceptable but optional.

---

## 10. Implementation Constraints & Helpers

### 10.1 No Magic Constants

Expose every threshold as a named constant or configuration input; never inline raw numbers.

### 10.2 Helper Functions

Create small pure helpers to avoid duplicated logic:

- `bool step_up_possible_main(inputs, state)`
- `bool step_up_possible_probe(inputs, state)`
- `State step_down(inputs, state)`
- `State enforce_inverter_limit(inputs, state)`

### 10.3 Pure Decision Graph

- Conditions must have no side effects.
- The FSM decision returns a struct containing the next state, next step index, desired switch state, desired current, and reason for logging.
- Only after the decision is finalized should you compare desired vs. actual outputs and call Home Assistant services.

### 10.4 Adapter Layout

```python
@dataclass
class Inputs:
    batt_soc: float
    batt_power_w: float
    inverter_power_w: float
    pv_power_w: float
    charger_status: str
    charger_switch_on: bool
    charger_current_a: int
    auto_enabled: bool
    now_s: float

@dataclass
class Decision:
    next_mode_state: ModeState
    next_step_index: int
    switch_on: bool
    set_current_a: Optional[int]
    reason: str
```

- `poll_inputs()` reads HA entities once per tick.
- `apply_decision(decision)` issues minimal service calls (toggle switch if needed, set current if changed). Update `last_change_ts_s` immediately before returning to the idle loop.

### 10.5 Logging

Log on every state transition and whenever the EVSE current changes. Include: old/new state, old/new step, SOC, BattP_W, Inv_W, Excess_W (if valid), and rule reason.

---

## 11. Testing Strategy

Before deploying, run offline simulations using captured or synthetic traces that cover:

1. Rising PV followed by falling PV.
2. Battery SOC moving around the 95% boundary (crossing both directions).
3. Inverter output nearing and exceeding the safety limit.
4. EV plug/unplug sequences and status changes (`charging`, `charged`, `waiting`, `fault`).

Validation goals:
- No two EVSE step changes occur within `COOLDOWN_S`.
- `Inv_W` never exceeds `INVERTER_LIMIT_W` for more than a single tick because of controller actions.
- MAIN vs PROBE behavior matches the rule tables above.
- Global rules (fault/unplugged/auto-disabled) always override mode logic.

Consider building a lightweight simulator that replays CSV traces through the FSM, capturing emitted actions for regression testing.

---

### Reference Tick Pseudocode

```python
def control_tick():
    inputs = poll_inputs()  # Single HA read
    derived = compute_derived(inputs, state)
    decision = evaluate_fsm(inputs, derived, state)
    if decision is None:
        return  # No change this tick
    apply_decision(decision)
    state.update(decision)
```

This pseudocode highlights the separation between reading inputs, deciding, and applying side effects.
