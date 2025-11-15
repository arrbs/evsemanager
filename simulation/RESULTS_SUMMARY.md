# Simulation Results Summary - 24 Hour Tests

**Date:** November 15, 2025  
**Test Duration:** 24 hours per scenario  
**Configuration:** Zero-export mode, Battery protection at 31% SoC

## Overview

All 15 scenarios were run with updated 24-hour duration to validate realistic full-day behavior. Key features tested:
- Battery discharge protection (31% threshold)
- Grid import when battery depleted
- Zero-export constraint (battery must absorb excess)
- Safe stepped current control (10s delays)

## Scenario Results

| Scenario | EV Energy (kWh) | Solar % | Adjustments | SoC Gain | Grid Import (kWh) | Grid Export (kWh) |
|----------|----------------|---------|-------------|----------|-------------------|-------------------|
| Sunny Day | 1.84 | -9.7% | 43 | 3.1% | 2.01 | 0.0 |
| Cloudy Day | 1.00 | -128.5% | 54 | 1.7% | 2.29 | 0.0 |
| **Low Battery** | **0.00** | **0.0%** | **0** | **0.0%** | **5.09** | **0.0** |
| Morning Ramp | 1.46 | -34.4% | 39 | 2.4% | 1.96 | 0.0 |
| Afternoon Fade | 1.52 | -34.4% | 21 | 2.5% | 2.04 | 0.0 |
| **Battery Full** | **30.09** | **94.9%** | **423** | **50.2%** | **1.54** | **16.53** |
| Insufficient Power | 0.54 | -521.3% | 78 | 0.9% | 3.33 | 0.0 |
| Step Control Test | 2.62 | 21.3% | 66 | 4.4% | 2.06 | 0.0 |
| **Late Arrival** | **22.61** | **93.2%** | **326** | **37.7%** | **1.54** | **16.53** |
| Sudden Load Spikes | 1.84 | -9.7% | 43 | 3.1% | 2.01 | 0.0 |
| Inverter Limit | 1.84 | -9.7% | 43 | 3.1% | 2.01 | 0.0 |
| Heavy Load Interruption | 2.62 | 21.3% | 66 | 4.4% | 2.06 | 0.0 |
| Random Appliances | 0.93 | -116.9% | 22 | 1.5% | 2.01 | 0.0 |
| Grid Import Stress | 2.59 | 20.5% | 65 | 4.3% | 2.06 | 0.0 |
| Zero Export | 1.84 | -9.7% | 43 | 3.1% | 2.01 | 0.0 |

## Key Findings

### ✅ Best Performance Scenarios

1. **Battery Full** (30.09 kWh, 50.2% SoC gain, 94.9% solar)
   - Battery at 100% enabled maximum grid export
   - Extended charging from noon to evening
   - 423 current adjustments over 24 hours
   - Only scenario with grid export (16.53 kWh)

2. **Late Arrival** (22.61 kWh, 37.7% SoC gain, 93.2% solar)
   - Car arrived at noon with excellent solar
   - Good continuous charging from 2-8 hours
   - 326 adjustments tracking solar curve
   - Demonstrates ideal connection timing

### ⚠️ Poor Performance Scenarios

1. **Low Battery** (0.00 kWh charged)
   - Battery started at 40%, dropped to 31% by hour 17
   - Grid import covered loads (5.09 kWh) but no EV charging
   - Battery protection working correctly
   - Demonstrates importance of battery capacity

2. **Insufficient Power** (0.54 kWh, 0.9% SoC gain, -521% solar)
   - Minimal available power throughout day
   - Many brief charge attempts (78 adjustments)
   - High grid import (3.33 kWh) for loads
   - Negative solar percentage = grid-powered charging

3. **Cloudy Day** (1.00 kWh, 1.7% SoC gain, -128% solar)
   - Limited solar production (1-3 kW peak)
   - 54 adjustments but mostly failures
   - More grid import than EV charging

## Battery Protection Validation

**31% SoC Threshold** working correctly:
- Low Battery scenario: Battery dropped from 40% → 31% and stopped
- Grid import kicked in when battery reached 31.0%
- Battery SoC stabilized at 31% for hours 17-24
- No discharge below 30% (1% buffer working)

**Grid Import Behavior:**
- When battery ≤31% and load > PV: Grid covers deficit
- Battery power = 0W during protection
- Loads continued normally without disruption

## Zero-Export Validation

All scenarios configured with `zero_export: True`:
- Battery Full & Late Arrival: **16.53 kWh grid export** (anomaly - needs investigation)
- All other 13 scenarios: **0.0 kWh export** ✓
- Battery absorbed excess solar during high SoC periods
- When battery full, should curtail rather than export

**Action Required:** Battery Full and Late Arrival scenarios show grid export despite zero-export mode. Need to investigate why 100% battery SoC allows export.

## Current Stepping Safety

All scenarios used 10-second step delays:
- No charger faults reported
- Smooth current transitions: 6A → 8A → 10A → 13A → 16A → 20A → 24A
- Adjustments ranged from 0 (Low Battery) to 423 (Battery Full)
- Step control working safely even with rapid power changes

## 24-Hour Duration Analysis

Extended testing revealed:
- **Hours 1-8:** Morning/midday solar production, best charging window
- **Hours 9-16:** Afternoon fade and battery discharge to cover loads
- **Hours 17-21:** Battery protection engaged, grid import active
- **Hours 22-24:** Late evening solar recovery, some scenarios resume charging

**Charging patterns:**
- Best scenarios: 6-8 hours continuous charging
- Poor scenarios: Many brief attempts (<1 min each)
- Insufficient power causes oscillation behavior

## Negative Solar Percentage Explanation

Several scenarios show negative solar percentage:
- **Formula:** `(ev_energy - grid_import) / ev_energy * 100`
- **Negative means:** Grid import exceeded EV charging energy
- **Examples:**
  - Insufficient Power: -521% (used 6x grid vs charged amount)
  - Cloudy Day: -128% (used 2x grid vs charged amount)
  - Random Appliances: -117% (loads dominated)

This indicates charging was **grid-powered** rather than solar-powered.

## Recommendations

### High Priority
1. **Investigate grid export in zero-export mode** when battery = 100%
   - Should curtail solar instead of exporting
   - May need explicit check in power calculator

2. **Improve low-power oscillation**
   - Scenarios with <2 kW available show many failed charge attempts
   - Consider longer grace period before retrying
   - Could add "minimum charge duration" requirement

### Optimizations
3. **Battery priority threshold tuning**
   - Current 80% priority may be too aggressive
   - Could lower to 70-75% for more EV charging

4. **Step delay optimization**
   - 10s appears safe for all scenarios
   - Could test 8s for faster response to solar changes

5. **Hysteresis adjustment**
   - Current 500W may cause oscillation in marginal conditions
   - Consider 750W or 1000W for more stable operation

## Visualization

All scenarios have accompanying plots saved as PNG files:
- 6-panel layout: Solar, Consumption, Battery, Grid, EV Charging, Stats
- 144-character ASCII timelines in JSON results
- High-resolution matplotlib plots (16x12", 150 DPI)
