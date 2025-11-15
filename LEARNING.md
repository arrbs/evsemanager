# Adaptive Learning Mode Guide

## Overview

The EVSE Manager includes an **Adaptive Learning Mode** that automatically discovers optimal control parameters for your specific setup. Instead of manually tuning settings, the system learns from actual charging sessions to find the best configuration for:

- Solar percentage maximization
- System stability
- Fault prevention
- Responsive power tracking

## How It Works

### Learning Process

1. **Exploration Phase** (Sessions 1-8)
   - Systematically tries different parameter combinations
   - Tests hysteresis values (300W to 1500W)
   - Varies smoothing windows (30s to 180s)
   - Adjusts grace periods (5min to 30min)

2. **Exploitation Phase** (Sessions 9+)
   - Focuses on best-performing regions
   - Refines promising parameter combinations
   - Converges on optimal settings

3. **Completion**
   - Analyzes all trials
   - Selects top-performing configurations
   - Recommends (or applies) optimal settings

### Scoring Algorithm

Each trial is scored based on:
- **Solar Percentage**: Higher is better
- **Energy Delivered**: More kWh preferred
- **Stability**: Fewer adjustments better
- **Fault Avoidance**: Faults heavily penalized
- **Completion**: Successful sessions weighted higher

The scoring adapts based on your optimization goal.

## Configuration

### Enable Learning Mode

```yaml
adaptive:
  enabled: true                    # Turn on learning
  learning_sessions: 20            # Number of sessions to learn over
  optimization_goal: "balanced"    # What to optimize for
  auto_apply: false               # Automatically apply learned settings
  tune_hysteresis: true           # Allow tuning hysteresis
  tune_smoothing: true            # Allow tuning smoothing window
  tune_grace_period: true         # Allow tuning grace period
  min_step_delay: 5               # Safety: minimum step delay
  max_step_delay: 30              # Maximum step delay to try
```

### Optimization Goals

**solar** - Maximize solar percentage
- Best for: Pure solar charging, minimal grid use
- Prioritizes: High solar %, energy delivered
- May sacrifice: Some stability

**stability** - Minimize adjustments and faults
- Best for: Sensitive chargers, reliability
- Prioritizes: Smooth operation, fault avoidance
- May sacrifice: Some solar optimization

**balanced** (recommended)
- Best for: Most users
- Balances: Solar %, stability, energy, faults
- Good all-around performance

### Auto-Apply Settings

**Manual Review** (recommended)
```yaml
auto_apply: false
```
- System suggests optimal settings
- You review and manually apply
- Safer for initial learning

**Automatic** (advanced)
```yaml
auto_apply: true
```
- System applies settings immediately after learning
- Best for continuous optimization
- Requires confidence in system

## Using Learning Mode

### Step 1: Enable and Configure

Edit your `config.yaml`:

```yaml
adaptive:
  enabled: true
  learning_sessions: 20
  optimization_goal: "balanced"
  auto_apply: false
```

### Step 2: Start Learning

1. Restart the add-on
2. Check logs: "Adaptive Learning: Enabled"
3. Web UI will show learning banner

### Step 3: Monitor Progress

**Web Interface** shows:
- Current session count (e.g., "5/20")
- Best score achieved so far
- Settings being tested

**Logs** show:
```
INFO - Learning trial: testing settings {...}
INFO - Trial completed. Score: 8.52, Solar: 94.2%
```

### Step 4: Review Results

After 20 sessions:
```
INFO - LEARNING COMPLETE!
INFO - Best score: 9.87
INFO - Best solar %: 96.3%
INFO - Optimal settings: {'hysteresis_watts': 600, ...}
```

**Web UI** displays:
- ✅ Learning Complete banner
- Optimal settings found
- Button to apply settings

### Step 5: Apply Settings

**Option A: Manual Application**
1. Copy optimal settings from logs/UI
2. Update your `config.yaml`
3. Restart add-on

**Option B: Automatic** (if `auto_apply: true`)
- Settings applied immediately
- Effective on next session

## What Gets Tuned

### Hysteresis (hysteresis_watts)
- **What**: Minimum power change to trigger adjustment
- **Range**: 300W to 1500W
- **Lower values**: More responsive, more adjustments
- **Higher values**: More stable, fewer adjustments
- **Typical optimal**: 400-800W

### Smoothing Window (power_smoothing_window)
- **What**: Time period for averaging power readings
- **Range**: 30s to 180s
- **Lower values**: Faster response to changes
- **Higher values**: Smoother, ignores brief fluctuations
- **Typical optimal**: 60-90s

### Grace Period (grace_period)
- **What**: Wait time before stopping due to low power
- **Range**: 300s (5min) to 1800s (30min)
- **Lower values**: Quicker response to lack of solar
- **Higher values**: More tolerant of clouds
- **Typical optimal**: 600-900s (10-15min)

## Advanced Features

### Reset Learning

To start learning over:

```python
# Via Home Assistant service call (future feature)
# Or delete: /data/adaptive_tuning.json
```

### Learning Duration

**Short Learning** (10 sessions)
- Faster results
- Less thorough
- Good for quick optimization

**Medium Learning** (20 sessions) - Recommended
- Balanced thoroughness
- Covers parameter space well
- Usually finds good settings

**Long Learning** (50+ sessions)
- Very thorough
- Better for complex systems
- Marginal improvement vs time

### Continuous Learning

Set a high session count (e.g., 100) to continuously adapt:
```yaml
learning_sessions: 100
auto_apply: true
```

System keeps learning and applying improvements over time.

## Interpreting Results

### Good Learning Outcome

```
Best score: 9.5+
Best solar %: 95%+
Faults: 0
Adjustments: Moderate (10-30 per session)
```

Settings should be reliable and well-optimized.

### Poor Learning Outcome

```
Best score: < 5.0
Best solar %: < 70%
Faults: Multiple
```

**Possible causes:**
- Insufficient solar during learning period
- Charger incompatibility
- Sensor issues
- Weather too variable

**Solutions:**
- Learn during better weather
- Check sensor accuracy
- Manually set conservative baseline
- Increase learning sessions

## Safety Considerations

### Built-in Safety Limits

The system enforces:
- **Minimum step delay**: Won't go below configured minimum
- **Known working ranges**: Only tests reasonable values
- **Fault detection**: Stops if charger faults
- **Session validation**: Ignores incomplete/faulty sessions

### Recommendations

1. **Start conservative**: Use manual review mode first
2. **Monitor early sessions**: Watch logs during initial trials
3. **Good weather**: Learn during stable solar conditions
4. **Sufficient sessions**: 20+ for reliable results
5. **Verify sensors**: Ensure all readings accurate

## Troubleshooting

### Learning Not Starting

**Check:**
- `adaptive.enabled: true` in config
- Add-on restarted after config change
- Logs show "Adaptive Learning: Enabled"

### No Progress

**Check:**
- Car must be connected for sessions to run
- Sufficient solar power available
- Sessions completing successfully (not all faults)

### Poor Results

**Try:**
- Increase `learning_sessions` to 30-50
- Change `optimization_goal`
- Learn during better weather
- Verify sensor accuracy

### Settings Not Applied

**If `auto_apply: false`:**
- This is normal - manual application required
- Copy settings from logs to config

**If `auto_apply: true`:**
- Check logs for errors
- Verify learning completed
- Settings apply on next session start

## Example Workflow

### First-Time Setup

```yaml
# Start with learning
adaptive:
  enabled: true
  learning_sessions: 25
  optimization_goal: "balanced"
  auto_apply: false
  tune_hysteresis: true
  tune_smoothing: true
  tune_grace_period: true
```

**After learning completes:**

1. Review optimal settings in logs
2. Looks good? Update config manually:

```yaml
control:
  hysteresis_watts: 650        # From learning
  power_smoothing_window: 75   # From learning
  grace_period: 750            # From learning

adaptive:
  enabled: false  # Disable learning, use learned values
```

### Continuous Optimization

```yaml
# Always learning
adaptive:
  enabled: true
  learning_sessions: 100
  optimization_goal: "balanced"
  auto_apply: true  # Careful: automatic updates
```

System continuously refines settings as conditions change.

## Data Storage

Learning data stored in:
```
/data/adaptive_tuning.json
```

Contains:
- All trial results
- Scores and metrics
- Optimal settings
- Learning progress

Can be backed up, analyzed, or reset by deleting file.

## Performance Expectations

### Typical Improvements

- **Solar %**: +5-15% increase
- **Faults**: 50-100% reduction
- **Adjustments**: Optimized for your system
- **Stability**: Smoother operation

### Results Vary By

- Solar variability (weather)
- House load patterns
- Battery size and behavior
- Charger characteristics
- Sensor accuracy

## FAQ

**Q: How long does learning take?**
A: 20 sessions = typically 1-3 weeks depending on usage

**Q: Can I drive during learning?**
A: Yes, each time you plug in counts as a session

**Q: Will it fault my charger?**
A: Safety limits prevent dangerous settings. Faults possible but detected and avoided in future trials.

**Q: Can I change goal mid-learning?**
A: Not recommended. Restart learning with new goal.

**Q: Do I need to relearn after changes?**
A: Not for minor changes. Relearn if you change power method, sensors, or charger.

**Q: Can I see trial details?**
A: Yes, check `/data/adaptive_tuning.json` for full trial data

## Future Enhancements

Planned features:
- Weather-aware learning
- Time-of-day parameter adaptation
- Multi-season optimization
- Advanced ML algorithms
- Real-time parameter updates

---

**Start learning today and let your system optimize itself! 🎓**
