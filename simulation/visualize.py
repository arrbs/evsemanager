"""
Visualization tools for simulation results.
Creates plots showing power flows, charging behavior, and system state.
"""

import json
from typing import Dict, Any, List
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta


def plot_simulation_results(results: Dict[str, Any], output_file: str = None):
    """
    Create comprehensive visualization of simulation results.
    
    Args:
        results: Results dictionary from simulation
        output_file: Optional file to save plot to
    """
    history = results['history']
    summary = results['summary']
    
    # Convert time to hours for x-axis
    times = [h['time'] / 3600 for h in history]
    
    # Create figure with subplots
    fig, axes = plt.subplots(5, 1, figsize=(14, 12))
    fig.suptitle(f"EVSE Manager Simulation: {summary['scenario']}", fontsize=16, fontweight='bold')
    
    # Plot 1: Power flows
    ax1 = axes[0]
    ax1.plot(times, [h['pv_power'] for h in history], label='Solar PV', color='orange', linewidth=2)
    ax1.plot(times, [h['house_load'] for h in history], label='House Load', color='gray', linewidth=1.5)
    ax1.plot(times, [h['ev_load'] for h in history], label='EV Load', color='green', linewidth=2)
    
    # Highlight load spikes if present
    load_spikes = [h.get('load_spikes', 0) for h in history]
    if max(load_spikes) > 0:
        ax1.fill_between(times, [h['house_load'] - h.get('load_spikes', 0) for h in history],
                         [h['house_load'] for h in history], alpha=0.4, color='red', label='Load Spikes')
    
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    # Show inverter limit
    if 'inverter_max_power' in results.get('scenario_config', {}):
        inverter_max = 8000  # Default
        ax1.axhline(y=inverter_max, color='red', linestyle='--', linewidth=1, alpha=0.5, label='Inverter Limit')
    
    ax1.fill_between(times, 0, [h['pv_power'] for h in history], alpha=0.2, color='orange')
    ax1.set_ylabel('Power (W)', fontsize=11)
    ax1.set_title('Power Flows', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=8)
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Battery state
    ax2 = axes[1]
    ax2_power = ax2.twinx()
    
    # Battery SoC on left axis
    line1 = ax2.plot(times, [h['battery_soc'] for h in history], label='Battery SoC', 
                     color='blue', linewidth=2)
    ax2.axhline(y=80, color='blue', linestyle='--', linewidth=1, alpha=0.5, label='Priority Threshold')
    ax2.axhline(y=95, color='red', linestyle='--', linewidth=1, alpha=0.5, label='High SoC')
    ax2.set_ylabel('Battery SoC (%)', fontsize=11, color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')
    ax2.set_ylim([0, 100])
    
    # Battery power on right axis
    battery_powers = [h['battery_power'] for h in history]
    line2 = ax2_power.plot(times, battery_powers, label='Battery Power', 
                          color='cyan', linewidth=1.5, alpha=0.7)
    ax2_power.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2_power.set_ylabel('Battery Power (W)', fontsize=11, color='cyan')
    ax2_power.tick_params(axis='y', labelcolor='cyan')
    
    ax2.set_title('Battery State', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    # Combined legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax2.legend(lines, labels, loc='upper left')
    
    # Plot 3: Grid interaction
    ax3 = axes[2]
    grid_powers = [h['grid_power'] for h in history]
    colors = ['red' if p > 0 else 'green' for p in grid_powers]
    
    # Split into import and export for clear visualization
    imports = [max(0, p) for p in grid_powers]
    exports = [min(0, p) for p in grid_powers]
    
    ax3.fill_between(times, 0, imports, alpha=0.5, color='red', label='Grid Import')
    ax3.fill_between(times, exports, 0, alpha=0.5, color='green', label='Grid Export')
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax3.set_ylabel('Grid Power (W)', fontsize=11)
    ax3.set_title('Grid Import/Export', fontsize=12, fontweight='bold')
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Charger current
    ax4 = axes[3]
    ax4.plot(times, [h['charger_target'] for h in history], label='Target Current', 
            color='orange', linewidth=1, linestyle='--')
    ax4.plot(times, [h['charger_current'] for h in history], label='Actual Current', 
            color='blue', linewidth=2)
    
    # Shade charging periods
    charging = [h['charger_on'] for h in history]
    ax4.fill_between(times, 0, max([h['charger_target'] for h in history] + [24]), 
                     where=charging, alpha=0.1, color='green', label='Charging Active')
    
    ax4.set_ylabel('Current (A)', fontsize=11)
    ax4.set_title('Charger Current Control', fontsize=12, fontweight='bold')
    ax4.legend(loc='upper left')
    ax4.grid(True, alpha=0.3)
    ax4.set_ylim([0, 26])
    
    # Plot 5: Car SoC
    ax5 = axes[4]
    ax5.plot(times, [h['car_soc'] for h in history], label='Car SoC', 
            color='purple', linewidth=2)
    ax5.fill_between(times, 0, [h['car_soc'] for h in history], alpha=0.2, color='purple')
    ax5.axhline(y=80, color='green', linestyle='--', linewidth=1, alpha=0.5, label='Target SoC')
    ax5.set_ylabel('Car SoC (%)', fontsize=11)
    ax5.set_xlabel('Time (hours)', fontsize=11)
    ax5.set_title('Vehicle State of Charge', fontsize=12, fontweight='bold')
    ax5.legend(loc='upper left')
    ax5.grid(True, alpha=0.3)
    ax5.set_ylim([0, 100])
    
    # Add summary text
    summary_text = (
        f"Duration: {summary['duration_hours']:.1f} hours  |  "
        f"EV Energy: {summary['ev_energy_kwh']:.2f} kWh  |  "
        f"Solar %: {summary['solar_percent']:.1f}%  |  "
        f"Grid Import: {summary['grid_import_kwh']:.2f} kWh  |  "
        f"Adjustments: {summary['adjustments']}  |  "
        f"SoC: {summary['car_soc_start']:.0f}% → {summary['car_soc_end']:.1f}% (+{summary['soc_gain']:.1f}%)"
    )
    if summary.get('max_load_spike_w', 0) > 0:
        summary_text += f"\nMax Load Spike: {summary['max_load_spike_w']:.0f}W  |  "
        summary_text += f"Inverter Limited: {summary.get('inverter_limited_minutes', 0):.1f} min"
    fig.text(0.5, 0.02, summary_text, ha='center', fontsize=10, 
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    plt.tight_layout(rect=[0, 0.04, 1, 0.98])
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {output_file}")
    else:
        plt.show()


def plot_comparison(results_list: List[Dict[str, Any]], output_file: str = None):
    """
    Create comparison plot for multiple scenarios.
    
    Args:
        results_list: List of results dictionaries
        output_file: Optional file to save plot to
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("EVSE Manager Scenario Comparison", fontsize=16, fontweight='bold')
    
    scenarios = [r['summary']['scenario'] for r in results_list]
    
    # Plot 1: Energy metrics
    ax1 = axes[0, 0]
    ev_energy = [r['summary']['ev_energy_kwh'] for r in results_list]
    solar_percent = [r['summary']['solar_percent'] for r in results_list]
    
    x = range(len(scenarios))
    ax1.bar(x, ev_energy, alpha=0.7, color='green', label='EV Energy (kWh)')
    ax1.set_ylabel('Energy (kWh)', fontsize=11)
    ax1.set_title('Energy Delivered', fontsize=12, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, rotation=45, ha='right')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # Plot 2: Solar percentage
    ax2 = axes[0, 1]
    colors = ['green' if p >= 85 else 'orange' if p >= 70 else 'red' for p in solar_percent]
    ax2.bar(x, solar_percent, alpha=0.7, color=colors)
    ax2.axhline(y=85, color='green', linestyle='--', linewidth=1, alpha=0.5, label='Excellent (85%+)')
    ax2.axhline(y=70, color='orange', linestyle='--', linewidth=1, alpha=0.5, label='Good (70%+)')
    ax2.set_ylabel('Solar %', fontsize=11)
    ax2.set_title('Solar Percentage', fontsize=12, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios, rotation=45, ha='right')
    ax2.set_ylim([0, 100])
    ax2.legend(loc='lower left', fontsize=8)
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Plot 3: Adjustments
    ax3 = axes[1, 0]
    adjustments = [r['summary']['adjustments'] for r in results_list]
    ax3.bar(x, adjustments, alpha=0.7, color='blue')
    ax3.set_ylabel('Count', fontsize=11)
    ax3.set_title('Current Adjustments', fontsize=12, fontweight='bold')
    ax3.set_xticks(x)
    ax3.set_xticklabels(scenarios, rotation=45, ha='right')
    ax3.grid(True, alpha=0.3, axis='y')
    
    # Plot 4: SoC gain
    ax4 = axes[1, 1]
    soc_gain = [r['summary']['soc_gain'] for r in results_list]
    ax4.bar(x, soc_gain, alpha=0.7, color='purple')
    ax4.set_ylabel('SoC Gain (%)', fontsize=11)
    ax4.set_title('Vehicle SoC Increase', fontsize=12, fontweight='bold')
    ax4.set_xticks(x)
    ax4.set_xticklabels(scenarios, rotation=45, ha='right')
    ax4.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"Comparison plot saved to {output_file}")
    else:
        plt.show()


def main():
    """Main entry point for visualization."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Visualize EVSE simulation results')
    parser.add_argument('input', help='Input JSON file with results')
    parser.add_argument('--output', '-o', help='Output image file')
    parser.add_argument('--compare', action='store_true', 
                       help='Compare multiple scenarios (input should be list)')
    
    args = parser.parse_args()
    
    with open(args.input, 'r') as f:
        data = json.load(f)
        
    if args.compare and isinstance(data, list):
        plot_comparison(data, args.output)
    else:
        plot_simulation_results(data, args.output)


if __name__ == '__main__':
    main()
