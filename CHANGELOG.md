# Changelog

All notable changes to `cloudmesh-ai-monitor` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [7.0.2.dev1] - 2026-04-19

### Added
- **AI Infrastructure Monitoring**: Introduced a comprehensive observability suite for monitoring LLM health and system performance.
- **Probing System**: 
    - Implemented `probe.py` for active health checking of AI services.
    - Added `llm_checker.py` for validating LLM response quality and availability.
- **Multi-Interface Visualization**:
    - **Web GUI**: Added a web-based dashboard for real-time monitoring of AI infrastructure.
    - **Terminal GUI (TUI)**: Implemented a rich terminal-based interface for low-latency monitoring.
- **Rendering Engine**: Added a specialized `renderer.py` to standardize the display of monitoring data across different interfaces.
- **CMC Integration**: Integrated the monitor as a first-class command within the `cloudmesh-ai-cmc` ecosystem.
- **Cross-Platform Support**: Added integration tests for diverse host environments, including DGX, Mac, and Spark hosts.
- **Test Suite**: Implemented unit and integration tests to ensure the reliability of the monitoring probes and renderers.

### Changed
- Initial project structure established to provide deep observability into AI model deployment and performance.