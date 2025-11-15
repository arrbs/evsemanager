"""
Session Manager Module
Tracks charging sessions, statistics, and learning.
"""
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ChargingSession:
    """Represents a single charging session."""
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    start_soc: Optional[float] = None
    end_soc: Optional[float] = None
    total_energy_kwh: float = 0.0
    solar_energy_kwh: float = 0.0
    grid_energy_kwh: float = 0.0
    avg_power_w: float = 0.0
    peak_power_w: float = 0.0
    duration_seconds: int = 0
    avg_current_a: float = 0.0
    solar_percentage: float = 0.0
    mode: str = "auto"
    adjustments_count: int = 0
    faults_count: int = 0
    stopped_reason: Optional[str] = None


class SessionManager:
    """Manages charging session tracking and statistics."""
    
    def __init__(self, data_dir: str = "/data"):
        self.logger = logging.getLogger(__name__)
        self.data_dir = Path(data_dir)
        self.sessions_file = self.data_dir / "sessions.json"
        self.stats_file = self.data_dir / "stats.json"
        
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Current session
        self.current_session: Optional[ChargingSession] = None
        self.session_start_time = None
        self.session_energy_samples = []
        self.session_power_samples = []
        self.session_current_samples = []
        
        # Load historical data
        self.sessions = self._load_sessions()
        self.stats = self._load_stats()
        
        self.logger.info(f"SessionManager initialized. {len(self.sessions)} historical sessions loaded.")
    
    def _load_sessions(self) -> List[Dict]:
        """Load historical sessions from file."""
        if not self.sessions_file.exists():
            return []
        
        try:
            with open(self.sessions_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading sessions: {e}")
            return []
    
    def _save_sessions(self):
        """Save sessions to file."""
        try:
            # Keep only last 100 sessions
            sessions_to_save = self.sessions[-100:]
            
            with open(self.sessions_file, 'w') as f:
                json.dump(sessions_to_save, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving sessions: {e}")
    
    def _load_stats(self) -> Dict:
        """Load statistics from file."""
        if not self.stats_file.exists():
            return {
                'total_sessions': 0,
                'total_energy_kwh': 0.0,
                'total_solar_kwh': 0.0,
                'avg_solar_percentage': 0.0,
                'total_duration_hours': 0.0,
                'last_updated': None
            }
        
        try:
            with open(self.stats_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading stats: {e}")
            return {}
    
    def _save_stats(self):
        """Save statistics to file."""
        try:
            self.stats['last_updated'] = datetime.now().isoformat()
            
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving stats: {e}")
    
    def start_session(self, mode: str = "auto") -> str:
        """
        Start a new charging session.
        
        Args:
            mode: Charging mode (auto or manual)
            
        Returns:
            Session ID
        """
        if self.current_session is not None:
            self.logger.warning("Session already active, ending previous session")
            self.end_session("new_session_started")
        
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.current_session = ChargingSession(
            session_id=session_id,
            start_time=datetime.now().isoformat(),
            mode=mode
        )
        
        self.session_start_time = datetime.now()
        self.session_energy_samples = []
        self.session_power_samples = []
        self.session_current_samples = []
        
        self.logger.info(f"Charging session started: {session_id} (mode: {mode})")
        
        return session_id
    
    def update_session(self, power_w: float, current_a: float, is_solar: bool = True):
        """
        Update current session with new measurements.
        
        Args:
            power_w: Current power in watts
            current_a: Current in amps
            is_solar: Whether power is from solar (vs grid)
        """
        if self.current_session is None:
            return
        
        now = datetime.now()
        
        # Store samples
        self.session_power_samples.append(power_w)
        self.session_current_samples.append(current_a)
        
        # Calculate energy (very rough estimate - power * time)
        if self.session_start_time:
            duration = (now - self.session_start_time).total_seconds()
            
            # Energy in kWh = (Power in W * time in hours) / 1000
            energy_kwh = (power_w * (duration / 3600)) / 1000
            
            if is_solar:
                solar_energy = energy_kwh
                grid_energy = 0
            else:
                solar_energy = 0
                grid_energy = energy_kwh
            
            # Incremental update
            energy_delta = energy_kwh - self.current_session.total_energy_kwh
            self.current_session.total_energy_kwh = energy_kwh
            
            if is_solar:
                self.current_session.solar_energy_kwh += energy_delta
            else:
                self.current_session.grid_energy_kwh += energy_delta
        
        # Update peak power
        if power_w > self.current_session.peak_power_w:
            self.current_session.peak_power_w = power_w
    
    def record_adjustment(self):
        """Record a current adjustment."""
        if self.current_session:
            self.current_session.adjustments_count += 1
    
    def record_fault(self):
        """Record a fault occurrence."""
        if self.current_session:
            self.current_session.faults_count += 1
    
    def end_session(self, reason: str = "normal"):
        """
        End current charging session.
        
        Args:
            reason: Reason for ending session
        """
        if self.current_session is None:
            self.logger.warning("No active session to end")
            return
        
        now = datetime.now()
        self.current_session.end_time = now.isoformat()
        self.current_session.stopped_reason = reason
        
        # Calculate duration
        if self.session_start_time:
            duration = (now - self.session_start_time).total_seconds()
            self.current_session.duration_seconds = int(duration)
        
        # Calculate averages
        if self.session_power_samples:
            self.current_session.avg_power_w = sum(self.session_power_samples) / len(self.session_power_samples)
        
        if self.session_current_samples:
            self.current_session.avg_current_a = sum(self.session_current_samples) / len(self.session_current_samples)
        
        # Calculate solar percentage
        if self.current_session.total_energy_kwh > 0:
            self.current_session.solar_percentage = (
                self.current_session.solar_energy_kwh / self.current_session.total_energy_kwh * 100
            )
        
        # Save session
        session_dict = asdict(self.current_session)
        self.sessions.append(session_dict)
        self._save_sessions()
        
        # Update stats
        self.stats['total_sessions'] = self.stats.get('total_sessions', 0) + 1
        self.stats['total_energy_kwh'] = self.stats.get('total_energy_kwh', 0) + self.current_session.total_energy_kwh
        self.stats['total_solar_kwh'] = self.stats.get('total_solar_kwh', 0) + self.current_session.solar_energy_kwh
        self.stats['total_duration_hours'] = self.stats.get('total_duration_hours', 0) + (self.current_session.duration_seconds / 3600)
        
        if self.stats['total_energy_kwh'] > 0:
            self.stats['avg_solar_percentage'] = (self.stats['total_solar_kwh'] / self.stats['total_energy_kwh']) * 100
        
        self._save_stats()
        
        self.logger.info(f"Session ended: {self.current_session.session_id}")
        self.logger.info(f"  Duration: {self.current_session.duration_seconds}s")
        self.logger.info(f"  Energy: {self.current_session.total_energy_kwh:.2f} kWh ({self.current_session.solar_percentage:.1f}% solar)")
        self.logger.info(f"  Avg Power: {self.current_session.avg_power_w:.0f}W")
        self.logger.info(f"  Adjustments: {self.current_session.adjustments_count}, Faults: {self.current_session.faults_count}")
        
        self.current_session = None
        self.session_start_time = None
    
    def get_current_session_info(self) -> Optional[Dict]:
        """Get current session information."""
        if self.current_session is None:
            return None
        
        session_dict = asdict(self.current_session)
        
        # Add real-time duration
        if self.session_start_time:
            duration = (datetime.now() - self.session_start_time).total_seconds()
            session_dict['current_duration_seconds'] = int(duration)
        
        return session_dict
    
    def get_stats(self) -> Dict:
        """Get overall statistics."""
        return self.stats.copy()
    
    def get_recent_sessions(self, count: int = 10) -> List[Dict]:
        """Get recent sessions."""
        return self.sessions[-count:] if self.sessions else []
    
    def get_optimal_charging_hours(self) -> Dict[str, float]:
        """
        Analyze historical data to find optimal charging hours.
        Returns dict of hour -> avg_solar_percentage
        """
        hourly_data = {}
        
        for session in self.sessions:
            try:
                start_time = datetime.fromisoformat(session['start_time'])
                hour = start_time.hour
                
                if hour not in hourly_data:
                    hourly_data[hour] = []
                
                hourly_data[hour].append(session.get('solar_percentage', 0))
            except:
                continue
        
        # Calculate averages
        hourly_averages = {}
        for hour, percentages in hourly_data.items():
            if percentages:
                hourly_averages[hour] = sum(percentages) / len(percentages)
        
        return hourly_averages


class AdaptiveTuner:
    """
    Adaptive learning system for optimizing control parameters.
    Uses statistical analysis of session outcomes to find optimal settings.
    """
    
    def __init__(self, config: Dict, data_dir: str = "/data"):
        self.logger = logging.getLogger(__name__)
        self.data_dir = Path(data_dir)
        self.tuning_file = self.data_dir / "adaptive_tuning.json"
        
        # Configuration
        self.enabled = config.get('enabled', False)
        self.learning_sessions = config.get('learning_sessions', 20)
        self.optimization_goal = config.get('optimization_goal', 'balanced')
        self.auto_apply = config.get('auto_apply', False)
        
        # What to tune
        self.tune_hysteresis = config.get('tune_hysteresis', True)
        self.tune_smoothing = config.get('tune_smoothing', True)
        self.tune_grace_period = config.get('tune_grace_period', True)
        
        # Safety limits
        self.min_step_delay = config.get('min_step_delay', 5)
        self.max_step_delay = config.get('max_step_delay', 30)
        
        # Learning state
        self.trials = []
        self.current_trial_id = None
        self.sessions_completed = 0
        self.learning_complete = False
        self.optimal_settings = None
        
        # Parameter ranges to explore
        self.param_ranges = {
            'hysteresis_watts': [300, 400, 500, 600, 800, 1000, 1200, 1500],
            'power_smoothing_window': [30, 45, 60, 90, 120, 150, 180],
            'grace_period': [300, 450, 600, 900, 1200, 1500, 1800],
            'step_delay': list(range(self.min_step_delay, self.max_step_delay + 1, 2))
        }
        
        # Load existing tuning data
        self._load_tuning_data()
        
        if self.enabled:
            self.logger.info(f"Adaptive tuning enabled: {self.learning_sessions} sessions, goal: {self.optimization_goal}")
    
    def _load_tuning_data(self):
        """Load existing tuning data."""
        if not self.tuning_file.exists():
            return
        
        try:
            with open(self.tuning_file, 'r') as f:
                data = json.load(f)
                self.trials = data.get('trials', [])
                self.sessions_completed = data.get('sessions_completed', 0)
                self.learning_complete = data.get('learning_complete', False)
                self.optimal_settings = data.get('optimal_settings')
                
            self.logger.info(f"Loaded {len(self.trials)} tuning trials, {self.sessions_completed} sessions")
        except Exception as e:
            self.logger.error(f"Error loading tuning data: {e}")
    
    def _save_tuning_data(self):
        """Save tuning data."""
        try:
            data = {
                'trials': self.trials,
                'sessions_completed': self.sessions_completed,
                'learning_complete': self.learning_complete,
                'optimal_settings': self.optimal_settings,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.tuning_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving tuning data: {e}")
    
    def start_trial(self, settings: Dict) -> str:
        """
        Start a new trial with specific settings.
        
        Args:
            settings: Dict of control parameters being tested
            
        Returns:
            Trial ID
        """
        if not self.enabled or self.learning_complete:
            return None
        
        trial_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        trial = {
            'trial_id': trial_id,
            'settings': settings.copy(),
            'start_time': datetime.now().isoformat(),
            'metrics': {}
        }
        
        self.trials.append(trial)
        self.current_trial_id = trial_id
        
        self.logger.info(f"Started trial {trial_id} with settings: {settings}")
        
        return trial_id
    
    def record_trial_outcome(self, session_data: Dict):
        """
        Record the outcome of the current trial.
        
        Args:
            session_data: Session metrics from SessionManager
        """
        if not self.enabled or not self.current_trial_id:
            return
        
        # Find current trial
        trial = next((t for t in self.trials if t['trial_id'] == self.current_trial_id), None)
        if not trial:
            return
        
        # Extract key metrics
        metrics = {
            'solar_percentage': session_data.get('solar_percentage', 0),
            'total_energy_kwh': session_data.get('total_energy_kwh', 0),
            'duration_seconds': session_data.get('duration_seconds', 0),
            'adjustments_count': session_data.get('adjustments_count', 0),
            'faults_count': session_data.get('faults_count', 0),
            'avg_power_w': session_data.get('avg_power_w', 0),
            'completed': session_data.get('stopped_reason') not in ['fault', 'battery_priority']
        }
        
        trial['metrics'] = metrics
        trial['end_time'] = datetime.now().isoformat()
        trial['score'] = self._calculate_score(metrics)
        
        self.sessions_completed += 1
        self.current_trial_id = None
        
        self.logger.info(f"Trial completed. Score: {trial['score']:.2f}, Solar: {metrics['solar_percentage']:.1f}%")
        
        # Check if learning is complete
        if self.sessions_completed >= self.learning_sessions:
            self._finalize_learning()
        
        self._save_tuning_data()
    
    def _calculate_score(self, metrics: Dict) -> float:
        """
        Calculate a score for trial metrics based on optimization goal.
        
        Args:
            metrics: Trial metrics
            
        Returns:
            Score (higher is better)
        """
        # Base components
        solar_score = metrics['solar_percentage'] / 100.0  # 0-1
        energy_score = min(metrics['total_energy_kwh'] / 50.0, 1.0)  # Normalize to ~50kWh
        completion_bonus = 1.0 if metrics['completed'] else 0.5
        
        # Penalties
        fault_penalty = metrics['faults_count'] * 10.0
        adjustment_penalty = (metrics['adjustments_count'] / 100.0) * 0.5  # Small penalty for many adjustments
        
        # Calculate based on goal
        if self.optimization_goal == 'solar':
            # Maximize solar percentage
            score = (solar_score * 3.0 + energy_score) * completion_bonus - fault_penalty - adjustment_penalty
            
        elif self.optimization_goal == 'stability':
            # Minimize adjustments and faults
            stability_score = 1.0 - (adjustment_penalty + (fault_penalty / 10.0))
            score = (stability_score * 2.0 + solar_score) * completion_bonus
            
        else:  # balanced
            # Balance everything
            score = (solar_score * 2.0 + energy_score + (1.0 - adjustment_penalty)) * completion_bonus - fault_penalty
        
        return max(score, 0.0)  # Ensure non-negative
    
    def get_next_settings(self, current_settings: Dict) -> Optional[Dict]:
        """
        Generate next settings to try using exploration strategy.
        
        Args:
            current_settings: Current control settings
            
        Returns:
            New settings to try, or None if learning complete
        """
        if not self.enabled or self.learning_complete:
            return None
        
        # Early exploration: Try each parameter systematically
        if self.sessions_completed < 8:
            return self._explore_parameters(current_settings)
        
        # Later: Focus on promising regions
        return self._exploit_best_regions(current_settings)
    
    def _explore_parameters(self, current_settings: Dict) -> Dict:
        """Systematic exploration of parameter space."""
        new_settings = current_settings.copy()
        
        # Cycle through parameters
        param_index = self.sessions_completed % 3
        params = ['hysteresis_watts', 'power_smoothing_window', 'grace_period']
        param = params[param_index]
        
        if param == 'hysteresis_watts' and self.tune_hysteresis:
            # Try different hysteresis values
            values = self.param_ranges['hysteresis_watts']
            new_settings[param] = values[self.sessions_completed % len(values)]
            
        elif param == 'power_smoothing_window' and self.tune_smoothing:
            values = self.param_ranges['power_smoothing_window']
            new_settings[param] = values[self.sessions_completed % len(values)]
            
        elif param == 'grace_period' and self.tune_grace_period:
            values = self.param_ranges['grace_period']
            new_settings[param] = values[self.sessions_completed % len(values)]
        
        self.logger.debug(f"Exploring: {param} = {new_settings.get(param)}")
        return new_settings
    
    def _exploit_best_regions(self, current_settings: Dict) -> Dict:
        """Focus on best-performing parameter combinations."""
        # Find top 30% of trials
        sorted_trials = sorted([t for t in self.trials if 'score' in t], 
                              key=lambda x: x['score'], reverse=True)
        
        top_trials = sorted_trials[:max(1, len(sorted_trials) // 3)]
        
        if not top_trials:
            return self._explore_parameters(current_settings)
        
        # Average the best settings
        new_settings = current_settings.copy()
        
        for param in ['hysteresis_watts', 'power_smoothing_window', 'grace_period']:
            if param in current_settings:
                values = [t['settings'][param] for t in top_trials if param in t['settings']]
                if values:
                    avg_value = sum(values) / len(values)
                    # Round to nearest value in range
                    new_settings[param] = min(self.param_ranges[param], 
                                             key=lambda x: abs(x - avg_value))
        
        self.logger.debug(f"Exploiting best region: {new_settings}")
        return new_settings
    
    def _finalize_learning(self):
        """Finalize learning and determine optimal settings."""
        self.learning_complete = True
        
        # Find best trial
        sorted_trials = sorted([t for t in self.trials if 'score' in t],
                              key=lambda x: x['score'], reverse=True)
        
        if not sorted_trials:
            self.logger.warning("No successful trials to learn from")
            return
        
        # Take top 3 trials and average their settings
        top_trials = sorted_trials[:min(3, len(sorted_trials))]
        
        self.optimal_settings = {}
        for param in ['hysteresis_watts', 'power_smoothing_window', 'grace_period']:
            values = [t['settings'].get(param) for t in top_trials if param in t['settings']]
            if values:
                self.optimal_settings[param] = int(sum(values) / len(values))
        
        best_score = top_trials[0]['score']
        best_metrics = top_trials[0]['metrics']
        
        self.logger.info("="*60)
        self.logger.info("LEARNING COMPLETE!")
        self.logger.info(f"Best score: {best_score:.2f}")
        self.logger.info(f"Best solar %: {best_metrics.get('solar_percentage', 0):.1f}%")
        self.logger.info(f"Optimal settings: {self.optimal_settings}")
        self.logger.info("="*60)
        
        self._save_tuning_data()
    
    def get_learning_status(self) -> Dict:
        """Get current learning status for UI."""
        return {
            'enabled': self.enabled,
            'learning_complete': self.learning_complete,
            'sessions_completed': self.sessions_completed,
            'total_sessions': self.learning_sessions,
            'progress_percentage': (self.sessions_completed / self.learning_sessions * 100) if self.learning_sessions > 0 else 0,
            'optimal_settings': self.optimal_settings,
            'current_best_score': max([t.get('score', 0) for t in self.trials]) if self.trials else 0,
            'total_trials': len(self.trials)
        }
    
    def should_apply_settings(self) -> bool:
        """Check if optimal settings should be applied."""
        return self.enabled and self.learning_complete and self.auto_apply and self.optimal_settings is not None
    
    def reset_learning(self):
        """Reset learning state to start over."""
        self.trials = []
        self.current_trial_id = None
        self.sessions_completed = 0
        self.learning_complete = False
        self.optimal_settings = None
        self._save_tuning_data()
        self.logger.info("Learning state reset")
