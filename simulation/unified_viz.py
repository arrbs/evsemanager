#!/usr/bin/env python3
"""
Unified visualization for EVSE simulation results.
Shows all key metrics in ONE comprehensive graph for easy analysis.
"""

import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


def load_results(filepath: str) -> dict:
    """Load simulation results from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def plot_unified(results: dict, output_file: str = None):
    """Create unified visualization with ALL metrics on ONE graph."""
    history = results['history']
    summary = results['summary']
    
    # Extract time series data
    times_sec = [h['time'] for h in history]
    times_hours = [t/3600 for t in times_sec]
    
    pv_power = [h['pv_power'] for h in history]
    house_load = [h['house_load'] for h in history]
    battery_power = [h['battery_power'] for h in history]
    battery_soc = [h['battery_soc'] for h in history]
    grid_power = [h['grid_power'] for h in history]
    ev_load = [h.get('ev_load', 0) for h in history]
    ev_load_actual = [h.get('ev_load_actual', h.get('ev_load', 0)) for h in history]
    charger_current = [h.get('charger_current', 0) for h in history]
    car_soc = [h.get('car_soc', 0) for h in history]
    charger_on = [h.get('charger_on', False) for h in history]
    
    # Calculate total load (house + EV actual consumption)
    total_load = [h + e for h, e in zip(house_load, ev_load_actual)]
    
    # Create single large figure
    fig, ax = plt.subplots(1, 1, figsize=(20, 10))
    fig.suptitle(f"EVSE Manager - {summary['scenario']} ({summary['duration_hours']}h)", 
                 fontsize=18, fontweight='bold')
    
    # Main power flows on primary axis
    ax.plot(times_hours, pv_power, 'gold', linewidth=3, label='Solar PV', zorder=10)
    ax.plot(times_hours, total_load, 'red', linewidth=2.5, label='Total Load (House+EV)', 
            linestyle='--', alpha=0.9, zorder=9)
    ax.plot(times_hours, house_load, 'blue', linewidth=1.5, label='House Load', 
            alpha=0.7, zorder=8)
    ax.plot(times_hours, ev_load_actual, 'green', linewidth=2, label='EV Load', 
            alpha=0.8, zorder=7)
    ax.plot(times_hours, battery_power, 'purple', linewidth=1.5, 
            label='Battery Power (+discharge/-charge)', alpha=0.7, zorder=6)
    ax.plot(times_hours, grid_power, 'darkred', linewidth=1.5, 
            label='Grid Power (+import/-export)', alpha=0.7, zorder=5)
    
    # Shade charging periods
    for i in range(len(times_hours)-1):
        if charger_on[i]:
            ax.axvspan(times_hours[i], times_hours[i+1], alpha=0.05, color='green', zorder=1)
    
    # Add zero line
    ax.axhline(0, color='black', linewidth=0.5, linestyle='--', alpha=0.4, zorder=2)
    
    # Create twin axis for SoC percentages
    ax_soc = ax.twinx()
    ax_soc.plot(times_hours, battery_soc, 'orange', linewidth=2.5, linestyle=':', 
                label='Battery SoC', alpha=0.6, zorder=4)
    ax_soc.plot(times_hours, car_soc, 'cyan', linewidth=2.5, linestyle=':', 
                label='Car SoC', alpha=0.6, zorder=3)
    ax_soc.set_ylim([0, 105])
    
    # Labels and formatting
    ax.set_xlabel('Time (hours)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Power (W)', fontsize=14, fontweight='bold')
    ax_soc.set_ylabel('State of Charge (%)', fontsize=14, fontweight='bold', color='orange')
    ax_soc.tick_params(axis='y', labelcolor='orange', labelsize=11)
    ax.tick_params(axis='both', labelsize=11)
    
    # Title explaining expected behavior
    title_text = ('Complete System Overview\n'
                  'NOTE: When battery >95% SoC and EV not charging, PV should curtail to match Total Load (zero-export mode)')
    ax.text(0.5, 0.97, title_text, transform=fig.transFigure, 
            fontsize=11, ha='center', va='top', style='italic',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))
    
    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_soc.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, 
             loc='upper left', fontsize=11, ncol=2, framealpha=0.9)
    
    ax.grid(True, alpha=0.3, linewidth=0.5)
    
    # Add summary statistics box
    stats_text = (
        f"Duration: {summary['duration_hours']}h\n"
        f"EV Energy: {summary['ev_energy_kwh']:.1f} kWh\n"
        f"Charging Time: {summary['charging_hours']:.1f}h "
        f"({summary['charging_hours']/summary['duration_hours']*100:.0f}%)\n"
        f"Solar %: {summary['solar_percent']:.1f}%\n"
        f"Car SoC: {summary['car_soc_start']}% → {summary['car_soc_end']}% "
        f"(+{summary['soc_gain']:.1f}%)\n"
        f"Grid Import: {summary['grid_import_kwh']:.2f} kWh\n"
        f"Grid Export: {summary['grid_export_kwh']:.2f} kWh"
    )
    
    ax.text(0.02, 0.02, stats_text, transform=fig.transFigure,
            fontsize=11, family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
            verticalalignment='bottom')
    
    plt.tight_layout(rect=[0, 0.08, 1, 0.93])
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved visualization to {output_file}")
    else:
        plt.show()
    
    plt.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 unified_viz.py <results.json> [output.png]")
        sys.exit(1)
    
    results_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else results_file.replace('.json', '.png')
    
    if not Path(results_file).exists():
        print(f"Error: File not found: {results_file}")
        sys.exit(1)
    
    results = load_results(results_file)
    plot_unified(results, output_file)
    
    print(f"\nScenario: {results['summary']['scenario']}")
    print(f"Duration: {results['summary']['duration_hours']}h")
    print(f"EV Energy: {results['summary']['ev_energy_kwh']:.1f} kWh")
    print(f"Solar %: {results['summary']['solar_percent']:.1f}%")
    print(f"SOC Gain: {results['summary']['soc_gain']:.1f}%")


if __name__ == '__main__':
    main()
