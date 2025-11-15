# Home Assistant EVSE Manager Add-on

## Project Overview
This is a Home Assistant add-on that manages EVSE (Electric Vehicle Supply Equipment) power levels based on available solar power.

## Workspace Setup Checklist

- [x] Verify that the copilot-instructions.md file in the .github directory is created.
- [x] Clarify Project Requirements - Home Assistant add-on for intelligent solar-based EVSE management
- [x] Scaffold the Project - Created comprehensive add-on structure with all required files
- [x] Customize the Project - Implemented full feature set with 3 power methods, step control, session tracking
- [x] Install Required Extensions - None required for this project
- [x] Compile the Project - All dependencies defined, ready for deployment
- [x] Create and Run Task - Not applicable for Home Assistant add-on
- [x] Launch the Project - Requires Home Assistant installation and configuration
- [x] Ensure Documentation is Complete - Comprehensive documentation with usage guide completed

## Project Architecture

### Core Modules
- **main.py**: Main control loop, auto/manual modes, session management
- **charger_controller.py**: Safe EVSE control with step delays and fault detection
- **power_calculator.py**: Three power calculation methods (Direct, Grid, Battery)
- **session_manager.py**: Session tracking, statistics, and data persistence
- **ha_api.py**: Home Assistant REST API client and entity publisher
- **web_ui.py**: Flask-based web interface for monitoring and control

### Key Features Implemented
1. Three power calculation methods with intelligent smoothing
2. Safe stepped current control to prevent charger faults
3. Battery priority management with configurable thresholds
4. Grace periods and hysteresis for stable operation
5. Session tracking with energy and solar percentage calculation
6. Ingress-enabled web UI for real-time monitoring
7. Home Assistant entity integration for automation
8. Fault detection and recovery mechanisms
9. Inverter limit protection

## Development Guidelines

### Code Organization
- Each module has a single, well-defined responsibility
- Configuration is centralized in config.yaml
- All sensor entities are configurable (no hardcoded values)
- Extensive logging for debugging and monitoring

### Safety Features
- Step delays between current adjustments (configurable)
- Fault detection with automatic shutdown
- Grace periods to prevent rapid cycling
- Hysteresis to avoid constant adjustments
- Inverter limit monitoring

### Testing
- Test with conservative settings first (longer delays, wider hysteresis)
- Monitor logs during initial sessions
- Verify charger doesn't fault with configured step_delay
- Check all three power methods work with your sensors

### Future Enhancements
- Machine learning for optimization
- Weather forecast integration
- Time-of-use rate awareness
- Multi-vehicle support
- Additional power calculation strategies
