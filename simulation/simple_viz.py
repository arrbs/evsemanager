#!/usr/bin/env python3
"""
Simple text-based visualization of simulation results.
No matplotlib required - uses ASCII charts.
"""

import json
import sys
from typing import Dict, List, Any


def draw_bar(value: float, max_value: float, width: int = 50, char: str = '█') -> str:
    """Draw a simple ASCII bar."""
    if max_value == 0:
        return ''
    bar_length = int((value / max_value) * width)
    return char * bar_length


def draw_timeline_graph(data: List[float], height: int = 10, width: int = 80, label: str = "", 
                       center_zero: bool = False) -> List[str]:
    """
    Draw an ASCII timeline graph.
    
    Args:
        data: List of values to plot
        height: Height of the graph in characters
        width: Width of the graph in characters
        label: Label for the Y-axis
        center_zero: If True, put zero line in the middle for +/- values
        
    Returns:
        List of strings representing each line of the graph
    """
    if not data or len(data) == 0:
        return [f"{label}: No data"]
    
    # Normalize data to fit in width
    step = max(1, len(data) // width)
    sampled = [data[i] for i in range(0, len(data), step)]
    if len(sampled) > width:
        sampled = sampled[:width]
    
    # Get min/max for scaling
    min_val = min(sampled)
    max_val = max(sampled)
    
    if max_val == min_val:
        max_val = min_val + 1
    
    # Decide if we need centered zero line
    if center_zero or (min_val < 0 and max_val > 0):
        # Values cross zero - center it
        abs_max = max(abs(min_val), abs(max_val))
        max_val = abs_max
        min_val = -abs_max
    
    # Create graph lines
    lines = []
    
    # Top line with max value
    lines.append(f"{label:>12} {max_val:>6.0f} ┤" + "─" * len(sampled))
    
    # Graph lines
    zero_row = None
    for row in range(height - 2):
        threshold = max_val - (row + 1) * (max_val - min_val) / (height - 1)
        
        # Mark where zero line is
        if min_val < 0 and threshold <= 0 and zero_row is None:
            zero_row = row
        
        line = f"{' ':>12} {threshold:>6.0f} │"
        
        for val in sampled:
            if threshold >= 0:
                # Above zero - fill if value is above threshold
                if val >= threshold:
                    line += "█"
                else:
                    line += "·" if val >= 0 else " "
            else:
                # Below zero - fill if value is below threshold (more negative)
                if val <= threshold:
                    line += "▓"
                else:
                    line += "·" if val < 0 else " "
        
        lines.append(line)
    
    # Bottom line with min value
    bottom = f"{' ':>12} {min_val:>6.0f} └" + "─" * len(sampled)
    lines.append(bottom)
    
    return lines


def draw_discrete_timeline(data: List[float], height: int = 8, width: int = 80, label: str = "", 
                          levels: List[float] = None) -> List[str]:
    """
    Draw a discrete/stepped timeline (for charger current selection).
    
    Args:
        data: List of values to plot
        height: Height of the graph
        width: Width of the graph
        label: Label for the axis
        levels: Discrete levels to show (e.g., allowed currents)
        
    Returns:
        List of strings representing the graph
    """
    if not data or len(data) == 0:
        return [f"{label}: No data"]
    
    # Sample data to fit width
    step = max(1, len(data) // width)
    sampled = [data[i] for i in range(0, len(data), step)]
    if len(sampled) > width:
        sampled = sampled[:width]
    
    max_val = max(sampled) if sampled else 0
    
    lines = []
    lines.append(f"{label:>12} {max_val:>6.1f} ┤" + "─" * len(sampled))
    
    for row in range(height - 2):
        threshold = max_val * (1 - (row + 1) / (height - 1))
        line = f"{' ':>12} {threshold:>6.1f} │"
        
        for val in sampled:
            if val > 0 and val >= threshold:
                line += "▓"
            elif val > 0:
                line += "░"
            else:
                line += " "
        
        lines.append(line)
    
    bottom = f"{' ':>12} {0:>6.1f} └" + "─" * len(sampled)
    lines.append(bottom)
    
    return lines


def visualize_scenario(results_file: str):
    """Visualize simulation results from JSON file."""
    
    with open(results_file, 'r') as f:
        data = json.load(f)
    
    # Handle both flat and nested structure
    if 'summary' in data:
        summary = data['summary']
        history = data.get('history', [])
    else:
        summary = data
        history = data.get('history', [])
    
    print(f"\n{'='*80}")
    print(f"  Scenario: {summary['scenario']}")
    print(f"  Duration: {summary['duration_hours']} hours")
    print(f"{'='*80}\n")
    
    # Summary metrics
    print("SUMMARY METRICS:")
    print(f"  EV Energy Charged:  {summary['ev_energy_kwh']:.2f} kWh")
    print(f"  Solar Percentage:   {summary['solar_percent']:.1f}%")
    print(f"  Grid Import:        {summary['grid_import_kwh']:.2f} kWh")
    print(f"  Grid Export:        {summary['grid_export_kwh']:.2f} kWh")
    print(f"  Charging Hours:     {summary['charging_hours']:.2f} hrs")
    print(f"  Current Adjustments: {summary['adjustments']}")
    print(f"  Car SoC:            {summary['car_soc_start']}% → {summary['car_soc_end']}% (+{summary['soc_gain']}%)")
    print()
    
    # Hourly breakdown
    if history:
        print("HOURLY POWER FLOWS:")
        print(f"  {'Hour':<6} {'PV':>8} {'House':>8} {'Battery':>8} {'EV':>8} {'Grid':>8}")
        print(f"  {'-'*50}")
        
        hours = int(summary['duration_hours'])
        samples_per_hour = len(history) // hours
        
        for hour in range(hours):
            # Get samples for this hour
            start_idx = hour * samples_per_hour
            end_idx = (hour + 1) * samples_per_hour
            hour_samples = history[start_idx:end_idx]
            
            # Calculate averages
            avg_pv = sum(s['pv_power'] for s in hour_samples) / len(hour_samples)
            avg_house = sum(s['house_load'] for s in hour_samples) / len(hour_samples)
            avg_battery = sum(s['battery_power'] for s in hour_samples) / len(hour_samples)
            avg_ev = sum(s['ev_load'] for s in hour_samples) / len(hour_samples)
            avg_grid = sum(s['grid_power'] for s in hour_samples) / len(hour_samples)
            
            print(f"  {hour+1:<6} {avg_pv:>7.0f}W {avg_house:>7.0f}W {avg_battery:>7.0f}W {avg_ev:>7.0f}W {avg_grid:>7.0f}W")
    
    print()
    
    # Power flow visualization
    print("POWER FLOW CHART (Average):")
    if history:
        avg_pv = sum(s['pv_power'] for s in history) / len(history)
        avg_house = sum(s['house_load'] for s in history) / len(history)
        avg_ev = sum(s['ev_load'] for s in history) / len(history)
        avg_battery = sum(s['battery_power'] for s in history) / len(history)
        avg_grid = sum(s['grid_power'] for s in history) / len(history)
        
        max_power = max(avg_pv, avg_house + avg_ev, abs(avg_battery), abs(avg_grid))
        
        print(f"  PV Production:  {avg_pv:>6.0f}W {draw_bar(avg_pv, max_power, 40, '☀')}")
        print(f"  House Load:     {avg_house:>6.0f}W {draw_bar(avg_house, max_power, 40, '🏠')}")
        print(f"  EV Load:        {avg_ev:>6.0f}W {draw_bar(avg_ev, max_power, 40, '🚗')}")
        
        if avg_battery > 0:
            print(f"  Battery Out:    {avg_battery:>6.0f}W {draw_bar(avg_battery, max_power, 40, '🔋')}")
        else:
            print(f"  Battery In:     {-avg_battery:>6.0f}W {draw_bar(-avg_battery, max_power, 40, '⚡')}")
        
        if avg_grid > 0:
            print(f"  Grid Import:    {avg_grid:>6.0f}W {draw_bar(avg_grid, max_power, 40, '⬆')}")
        else:
            print(f"  Grid Export:    {-avg_grid:>6.0f}W {draw_bar(-avg_grid, max_power, 40, '⬇')}")
    
    print()
    
    # Timeline graphs
    if history:
        print("=" * 100)
        print("TIMELINE VISUALIZATION")
        print("=" * 100)
        print()
        
        # Extract data series
        pv_power = [s['pv_power'] for s in history]
        house_load = [s['house_load'] for s in history]
        ev_load = [s['ev_load'] for s in history]
        battery_power = [s['battery_power'] for s in history]
        battery_soc = [s['battery_soc'] for s in history]
        car_soc = [s['car_soc'] for s in history]
        charger_current = [s['charger_current'] for s in history]
        grid_power = [s['grid_power'] for s in history]
        
        # Calculate total load
        total_load = [h + e for h, e in zip(house_load, ev_load)]
        
        # Time axis
        duration_hours = summary['duration_hours']
        width = 80
        time_labels = "            " + " " * 7 + "└"
        step = max(1, int(duration_hours / 8))  # Show ~8 time markers
        for i in range(0, int(duration_hours) + 1, step):
            pos = int((i / duration_hours) * width)
            time_labels += " " * (pos - len(time_labels) + 20) + f"{i}h"
        
        # 1. Solar Production
        print("SOLAR PRODUCTION (W)")
        for line in draw_timeline_graph(pv_power, height=8, width=width, label="PV Power"):
            print(line)
        print(time_labels)
        print()
        
        # 2. Loads (House + EV)
        print("POWER CONSUMPTION (W)")
        for line in draw_timeline_graph(total_load, height=8, width=width, label="Total Load"):
            print(line)
        print()
        for line in draw_timeline_graph(house_load, height=6, width=width, label="House Load"):
            print(line)
        print()
        for line in draw_timeline_graph(ev_load, height=6, width=width, label="EV Load"):
            print(line)
        print(time_labels)
        print()
        
        # 3. Battery
        print("BATTERY STATUS")
        for line in draw_timeline_graph(battery_soc, height=8, width=width, label="Batt SoC (%)"):
            print(line)
        print()
        
        # Show battery power flow (positive = discharging, negative = charging)
        print("BATTERY POWER FLOW (W, positive=discharge, negative=charge)")
        for line in draw_timeline_graph(battery_power, height=8, width=width, label="Batt Power", center_zero=True):
            print(line)
        print(time_labels)
        print()
        
        # 4. EV Charging
        print("EV CHARGING STATUS")
        for line in draw_timeline_graph(car_soc, height=8, width=width, label="Car SoC (%)"):
            print(line)
        print()
        for line in draw_discrete_timeline(charger_current, height=8, width=width, label="Charge (A)"):
            print(line)
        print(time_labels)
        print()
        
        # 5. Grid Power
        print("GRID POWER (W, negative=export, positive=import)")
        for line in draw_timeline_graph(grid_power, height=8, width=width, label="Grid", center_zero=True):
            print(line)
        print(time_labels)
        print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 simple_viz.py <results.json>")
        print("\nExample:")
        print("  python3 run_simulation.py 'Sunny Day' --save results.json")
        print("  python3 simple_viz.py results.json")
        sys.exit(1)
    
    visualize_scenario(sys.argv[1])


if __name__ == '__main__':
    main()
