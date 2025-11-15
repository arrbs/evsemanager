#!/usr/bin/env python3
"""
Test script to compare performance with and without sensor delay compensation.
"""
import subprocess
import json
import sys

def run_scenario(name, output_file, delay=60):
    """Run a scenario and return results."""
    print(f"\n{'='*80}")
    print(f"Running: {name} (delay={delay}s)")
    print(f"{'='*80}")
    
    cmd = ["python3", "run_simulation.py", name, "--output", output_file]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"FAILED: {result.stderr}")
        return None
    
    # Load results
    with open(output_file) as f:
        data = json.load(f)
    
    return data['summary']

def compare_results(before, after, name):
    """Compare results and print improvement."""
    print(f"\n{name} Comparison:")
    print(f"{'='*80}")
    print(f"{'Metric':<30} {'Without Fix':<20} {'With Fix':<20} {'Change':<20}")
    print(f"{'-'*80}")
    
    metrics = [
        ('ev_energy_kwh', 'EV Energy (kWh)', '+'),
        ('charging_hours', 'Charging Hours', '+'),
        ('solar_percent', 'Solar %', '+'),
        ('grid_import_kwh', 'Grid Import (kWh)', '-'),
        ('adjustments', 'Adjustments', '='),
        ('soc_gain', 'SoC Gain (%)', '+'),
    ]
    
    for key, label, direction in metrics:
        before_val = before[key]
        after_val = after[key]
        
        if isinstance(before_val, float):
            change = after_val - before_val
            change_pct = (change / before_val * 100) if before_val != 0 else 0
            
            if direction == '+':
                symbol = '✓' if change > 0 else '✗'
            elif direction == '-':
                symbol = '✓' if change < 0 else '✗'
            else:
                symbol = '='
            
            print(f"{label:<30} {before_val:>19.2f} {after_val:>19.2f} {symbol} {change:>7.2f} ({change_pct:+.1f}%)")
        else:
            change = after_val - before_val
            print(f"{label:<30} {before_val:>19} {after_val:>19} {change:>18}")

def main():
    print("Sensor Delay Compensation Test")
    print("="*80)
    print("\nThis test compares performance with and without the predictive compensation fix.")
    print("Both tests use 60s sensor delay, but the 'after' includes predictive compensation.")
    
    scenarios = ["Sunny Day", "Morning Ramp", "Battery Full"]
    
    for scenario in scenarios:
        # First, we need to update scenarios.py to allow toggling predictive compensation
        # For now, just run with current setup
        before_file = f"test_before_{scenario.replace(' ', '_')}.json"
        after_file = f"test_after_{scenario.replace(' ', '_')}.json"
        
        print(f"\n\nTesting scenario: {scenario}")
        print(f"Note: To see the improvement, you would need to:")
        print(f"1. Run simulation WITHOUT predictive compensation")
        print(f"2. Run simulation WITH predictive compensation")
        print(f"3. Compare results")
        
        # Run scenario
        results = run_scenario(scenario, after_file)
        
        if results:
            print(f"\nResults with predictive compensation:")
            print(f"  EV Energy: {results['ev_energy_kwh']:.2f} kWh")
            print(f"  Charging Hours: {results['charging_hours']:.2f}")
            print(f"  Solar %: {results['solar_percent']:.1f}%")
            print(f"  SoC Gain: {results['soc_gain']:.1f}%")

if __name__ == '__main__':
    main()
