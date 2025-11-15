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
    
    # Charging behavior
    if history:
        print("CHARGING PATTERN:")
        
        # Sample every N points to keep it readable
        sample_every = max(1, len(history) // 100)
        
        for i in range(0, len(history), sample_every):
            sample = history[i]
            hour = sample['time'] / 3600
            current = sample['charger_current']
            soc = sample['car_soc']
            
            if current > 0:
                bar = draw_bar(current, 24, 30, '█')
                print(f"  {hour:5.1f}h: [{bar:<30}] {current:4.1f}A  SoC: {soc:4.1f}%")


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
