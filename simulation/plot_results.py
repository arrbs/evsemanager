#!/usr/bin/env python3
"""
High-quality matplotlib visualization of simulation results.
"""

import json
import sys
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np


def plot_scenario(results_file: str, save_file: str = None):
    """Create comprehensive visualization of simulation results."""
    
    # Load results
    with open(results_file, 'r') as f:
        data = json.load(f)
    
    summary = data['summary']
    history = data['history']
    
    if not history:
        print("No history data to plot")
        return
    
    # Extract time series
    times = [datetime(2024, 1, 1) + timedelta(seconds=s['time']) for s in history]
    pv_power = [s['pv_power'] for s in history]
    house_load = [s['house_load'] for s in history]
    ev_load = [s['ev_load'] for s in history]
    ev_load_actual = [s.get('ev_load_actual', s['ev_load']) for s in history]
    battery_power = [s['battery_power'] for s in history]
    battery_soc = [s['battery_soc'] for s in history]
    grid_power = [s['grid_power'] for s in history]
    car_soc = [s['car_soc'] for s in history]
    charger_current = [s['charger_current'] for s in history]
    charger_current_actual = [s.get('charger_current_actual', s['charger_current']) for s in history]
    available_power = [s['available_power'] for s in history]
    
    # Create figure with subplots
    fig, axes = plt.subplots(6, 1, figsize=(16, 12), sharex=True)
    fig.suptitle(f"{summary['scenario']} - {summary['duration_hours']:.0f} Hour Simulation", 
                 fontsize=16, fontweight='bold')
    
    # 1. Solar Production
    ax = axes[0]
    ax.fill_between(times, pv_power, alpha=0.3, color='gold', label='PV Power')
    ax.plot(times, pv_power, color='orange', linewidth=1.5)
    ax.set_ylabel('Power (W)', fontweight='bold')
    ax.set_title('Solar Production', fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right')
    
    # 2. Power Consumption
    ax = axes[1]
    total_load = [h + e for h, e in zip(house_load, ev_load)]
    ax.fill_between(times, house_load, alpha=0.3, color='steelblue', label='House Load')
    ax.fill_between(times, house_load, total_load, alpha=0.3, color='green', label='EV Load')
    ax.plot(times, total_load, color='darkblue', linewidth=1.5, label='Total Load')
    ax.set_ylabel('Power (W)', fontweight='bold')
    ax.set_title('Power Consumption', fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right')
    
    # 3. Battery Status
    ax = axes[2]
    ax2 = ax.twinx()
    
    # Battery SoC on left axis
    line1 = ax.plot(times, battery_soc, color='purple', linewidth=2, label='Battery SoC')
    ax.set_ylabel('State of Charge (%)', fontweight='bold', color='purple')
    ax.tick_params(axis='y', labelcolor='purple')
    ax.set_ylim(0, 100)
    
    # Battery Power on right axis (positive = discharge, negative = charge)
    line2 = ax2.plot(times, battery_power, color='darkorange', linewidth=1.5, alpha=0.7, label='Battery Power')
    ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax2.fill_between(times, 0, battery_power, where=[p > 0 for p in battery_power], 
                     alpha=0.3, color='red', label='Discharge')
    ax2.fill_between(times, 0, battery_power, where=[p < 0 for p in battery_power], 
                     alpha=0.3, color='green', label='Charge')
    ax2.set_ylabel('Battery Power (W)', fontweight='bold', color='darkorange')
    ax2.tick_params(axis='y', labelcolor='darkorange')
    
    ax.set_title('Battery Status', fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # Combine legends
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    
    # 4. Grid Power
    ax = axes[3]
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax.fill_between(times, 0, grid_power, where=[p > 0 for p in grid_power], 
                    alpha=0.3, color='red', label='Grid Import')
    ax.fill_between(times, 0, grid_power, where=[p < 0 for p in grid_power], 
                    alpha=0.3, color='green', label='Grid Export')
    ax.plot(times, grid_power, color='darkred', linewidth=1.5, alpha=0.7)
    ax.set_ylabel('Power (W)', fontweight='bold')
    ax.set_title('Grid Power Flow', fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right')
    
    # 5. Available Power vs EV Charging (showing overshoot from sensor delay)
    ax = axes[4]
    ax2 = ax.twinx()
    
    # Available power and EV load on left axis (Watts)
    line1 = ax.plot(times, available_power, color='gold', linewidth=2, alpha=0.7, label='Available Power (Calculated)')
    ax.fill_between(times, available_power, alpha=0.2, color='gold')
    line2 = ax.plot(times, ev_load, color='darkgreen', linewidth=2, label='EV Power (Sensors)', linestyle='--', alpha=0.7)
    line3 = ax.plot(times, ev_load_actual, color='red', linewidth=2, label='EV Power (Actual)', alpha=0.8)
    ax.fill_between(times, ev_load_actual, alpha=0.2, color='red')
    ax.set_ylabel('Power (W)', fontweight='bold')
    ax.set_ylim(bottom=0)
    
    # Charger current on right axis (Amps) - show both reported and actual
    line4 = ax2.plot(times, charger_current, color='blue', linewidth=1.5, alpha=0.5, 
                     linestyle='--', label='Current (Sensors)')
    line5 = ax2.plot(times, charger_current_actual, color='darkblue', linewidth=1.5, alpha=0.7,
                     label='Current (Actual)')
    ax2.set_ylabel('Current (A)', fontweight='bold', color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')
    ax2.set_ylim(bottom=0)
    
    ax.set_title('Available Solar vs EV Charging (Sensor Delay & Overshoot)', fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # Combine legends
    lines = line1 + line2 + line3 + line4 + line5
    labels = [l.get_label() for l in lines]
    ax.legend(lines, labels, loc='upper right', fontsize=8)
    
    # 6. Summary Stats and Car SoC
    ax = axes[5]
    ax2 = ax.twinx()
    
    # Car SoC timeline on the bottom panel
    line1 = ax.plot(times, car_soc, color='darkgreen', linewidth=2.5, label='Car SoC')
    ax.fill_between(times, car_soc, alpha=0.3, color='green')
    ax.set_ylabel('Car SoC (%)', fontweight='bold', color='darkgreen')
    ax.tick_params(axis='y', labelcolor='darkgreen')
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left')
    ax.set_title('Car State of Charge', fontweight='bold')
    
    # Summary text on right side
    ax2.axis('off')
    
    summary_text = f"""SUMMARY METRICS:
    
EV Energy:     {summary['ev_energy_kwh']:.2f} kWh
Solar %:       {summary['solar_percent']:.1f}%
Grid Import:   {summary['grid_import_kwh']:.2f} kWh
Grid Export:   {summary['grid_export_kwh']:.2f} kWh

Duration:      {summary['charging_hours']:.2f} hrs
Adjustments:   {summary['adjustments']}

Car SoC:       {summary['car_soc_start']}% → {summary['car_soc_end']}%
Gain:          {summary['soc_gain']:+.1f}%"""
    
    ax2.text(0.65, 0.5, summary_text, fontsize=10, family='monospace',
            verticalalignment='center', transform=ax.transAxes,
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    # Format x-axis (time)
    axes[-2].set_xlabel('Time (hours)', fontweight='bold')
    
    # Set x-axis to show hours
    hour_formatter = mdates.DateFormatter('%H:00')
    axes[-2].xaxis.set_major_formatter(hour_formatter)
    axes[-2].xaxis.set_major_locator(mdates.HourLocator(interval=2))
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    if save_file:
        plt.savefig(save_file, dpi=150)
        print(f"Saved plot to {save_file}")
    else:
        plt.show()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 plot_results.py <results.json> [output.png]")
        print("\nExample:")
        print("  python3 run_simulation.py 'Sunny Day' --output results.json")
        print("  python3 plot_results.py results.json sunny_day.png")
        sys.exit(1)
    
    results_file = sys.argv[1]
    save_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    plot_scenario(results_file, save_file)


if __name__ == '__main__':
    main()
