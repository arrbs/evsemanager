#!/usr/bin/env python3
"""
EVSE Manager Performance Visualization.
Shows how well the EVSE tracks available solar power with stepped current control.
"""

import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt


def load_results(filepath: str) -> dict:
    """Load simulation results from JSON file."""
    with open(filepath) as f:
        return json.load(f)


def plot_evse_performance(results: dict, output_file: str = None):
    """Create focused visualization of EVSE manager performance."""
    history = results['history']
    summary = results['summary']
    
    # Extract time series data
    times_hours = [h['time']/3600 for h in history]
    
    # Key metrics for EVSE performance
    available_power = [h.get('available_power', 0) for h in history]
    ev_load_actual = [h.get('ev_load_actual', h.get('ev_load', 0)) for h in history]
    charger_current_actual = [h.get('charger_current_actual', h.get('charger_current', 0)) for h in history]
    pv_power = [h['pv_power'] for h in history]
    battery_soc = [h['battery_soc'] for h in history]
    charger_on = [h.get('charger_on', False) for h in history]
    
    # Create figure with 3 focused subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(18, 10), sharex=True)
    fig.suptitle(f"EVSE Manager Performance - {summary['scenario']}", 
                 fontsize=16, fontweight='bold')
    
    # ========== Subplot 1: Power Tracking ==========
    ax1.plot(times_hours, pv_power, 'gold', linewidth=2.5, label='Solar PV', alpha=0.9, zorder=5)
    ax1.plot(times_hours, available_power, 'orange', linewidth=2, label='Available for EV', 
             linestyle='--', alpha=0.8, zorder=4)
    ax1.plot(times_hours, ev_load_actual, 'green', linewidth=2.5, label='EV Actual Load', 
             alpha=0.9, zorder=6)
    
    # Shade charging periods
    ax1.fill_between(times_hours, 0, max(pv_power)*1.1, where=charger_on,
                     alpha=0.1, color='green', label='Charging Active', zorder=1)
    
    ax1.set_ylabel('Power (W)', fontsize=12, fontweight='bold')
    ax1.set_title('Power Tracking: How well does EVSE use available power?', fontsize=13)
    ax1.legend(loc='upper right', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(bottom=0)
    
    # ========== Subplot 2: Current Stepping ==========
    ax2.step(times_hours, charger_current_actual, 'blue', linewidth=2.5, 
             where='post', label='Charger Current (A)', zorder=5)
    
    # Mark allowed current steps
    allowed_currents = [6, 8, 10, 13, 16, 20, 24]
    for current in allowed_currents:
        ax2.axhline(y=current, color='gray', linestyle=':', alpha=0.3, linewidth=0.8)
    
    # Shade charging periods
    ax2.fill_between(times_hours, 0, max(allowed_currents)*1.1, where=charger_on,
                     alpha=0.1, color='green', zorder=1)
    
    ax2.set_ylabel('Current (A)', fontsize=12, fontweight='bold')
    ax2.set_title('Current Stepping: Discrete steps [6, 8, 10, 13, 16, 20, 24]A', fontsize=13)
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim([0, max(allowed_currents) * 1.1])
    
    # ========== Subplot 3: Battery State Context ==========
    ax3.plot(times_hours, battery_soc, 'orange', linewidth=2, label='Battery SoC (%)', zorder=4)
    ax3.axhline(y=95, color='red', linestyle='--', alpha=0.5, linewidth=1.5, 
                label='Full Battery Threshold (95%)')
    
    # Shade charging periods
    ax3.fill_between(times_hours, 0, 105, where=charger_on,
                     alpha=0.1, color='green', label='EV Charging', zorder=1)
    
    ax3.set_xlabel('Time (hours)', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Battery SoC (%)', fontsize=12, fontweight='bold')
    ax3.set_title('Battery Context: When battery >95%, available power comes from curtailed solar', fontsize=13)
    ax3.legend(loc='upper right', fontsize=10)
    ax3.grid(True, alpha=0.3)
    ax3.set_ylim([0, 105])
    
    plt.tight_layout()
    
    # Add performance summary
    total_available = sum(available_power) / 12  # Convert to Wh (5s intervals)
    total_used = sum(ev_load_actual) / 12
    utilization = (total_used / total_available * 100) if total_available > 0 else 0
    
    stats_text = (
        f"PERFORMANCE SUMMARY\n"
        f"Duration: {summary['duration_hours']}h\n"
        f"EV Energy: {summary['ev_energy_kwh']:.1f} kWh\n"
        f"Charging Time: {summary['charging_hours']:.1f}h ({summary['charging_hours']/summary['duration_hours']*100:.0f}%)\n"
        f"Solar Utilization: {utilization:.1f}%\n"
        f"Car SoC: {summary['car_soc_start']}% → {summary['car_soc_end']}% (+{summary['soc_gain']:.1f}%)\n"
        f"Grid Import: {summary['grid_import_kwh']:.2f} kWh (should be ~0)"
    )
    
    fig.text(0.02, 0.02, stats_text, fontsize=10, family='monospace',
             bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8),
             verticalalignment='bottom')
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Saved EVSE performance visualization to {output_file}")
    else:
        plt.show()
    
    plt.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 evse_performance_viz.py <results.json> [output.png]")
        sys.exit(1)
    
    results_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else results_file.replace('.json', '_performance.png')
    
    if not Path(results_file).exists():
        print(f"Error: File not found: {results_file}")
        sys.exit(1)
    
    results = load_results(results_file)
    plot_evse_performance(results, output_file)
    
    print(f"\nScenario: {results['summary']['scenario']}")
    print(f"EV Energy: {results['summary']['ev_energy_kwh']:.1f} kWh")
    print(f"Solar %: {results['summary']['solar_percent']:.1f}%")
    print(f"Charging Hours: {results['summary']['charging_hours']:.1f}h / {results['summary']['duration_hours']}h")


if __name__ == '__main__':
    main()
