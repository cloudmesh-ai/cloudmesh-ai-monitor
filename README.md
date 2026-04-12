# cloudmesh-ai-monitor

Observability extension for cloudmesh-ai services.

## Purpose
Deep integration with Prometheus, Grafana, and remote system monitoring to provide real-time health and performance data for AI infrastructure (DGX nodes, GPU exporters).

## Features
- **Real-time TUI Dashboard**: A professional Textual-based terminal interface for fleet-wide monitoring.
- **Remote Host Management**: Manage a fleet of AI nodes via a YAML configuration file or interactive TUI setup.
- **Automatic Hardware Discovery**: Probe remote hosts to automatically detect GPU and CPU types.
- **Interactive Monitoring**: Launch `top`, `nvtop`, or `nvitop` on remote hosts via SSH.
- **Fleet Stats**: Quickly check GPU load, temperatures, and CPU stats across multiple hosts.
- **GPU Exporter Health Check**: Verify that the Prometheus GPU exporter is running and providing metrics.
- **OOM Detection**: Scan system logs and metrics for "Out of Memory" (OOM) events.
- **Grafana Integration**: Commands to trigger snapshots or link to specific AI performance dashboards.

## Configuration

### Host Configuration
Create a configuration file at `~/.config/cloudmesh/ai/hosts.yaml`:
```yaml
cloudmesh:
  ai:
    hosts:
      dgx-01:
        label: "DGX-Primary"
        gpu: "nvidia"
        cpu: "intel"
      dgx-02:
        label: "DGX-Secondary"
        gpu: "nvidia"
        cpu: "intel"
```

### GUI Framework Selection
The monitor supports multiple GUI frameworks. Use the `CMC_GUI` environment variable to switch:
- `terminalgui` (Default): Launches the Textual-based TUI.
- `grafana`: Integrates with Grafana dashboards.

```bash
export CMC_GUI=terminalgui
```

## Installation
```bash
pip install .
```

## Usage

### Real-time Dashboard
Launch the interactive fleet dashboard:
```bash
cloudmesh-ai-monitor dashboard
```

### Host Setup
Manage your monitoring fleet via CLI:
```bash
# Add a new host
cloudmesh-ai-monitor setup add dgx-03 --label "DGX-New"

# Activate/Deactivate a host
cloudmesh-ai-monitor setup activate dgx-01
cloudmesh-ai-monitor setup deactivate dgx-02

# Remove a host
cloudmesh-ai-monitor setup remove dgx-03
```

### Hardware Discovery
```bash
# Automatically detect GPU/CPU and update the default config
cloudmesh-ai-monitor probe dgx-01 dgx-02

# Probe and save to a specific config file
cloudmesh-ai-monitor probe dgx-03 --config my_cluster.yaml
```

### Remote Interactive Tools
```bash
# Run nvtop on a specific host or label
cloudmesh-ai-monitor run dgx-01 nvtop
cloudmesh-ai-monitor run "DGX-Primary" top
```

### Fleet Statistics
```bash
# Check GPU stats for multiple hosts
cloudmesh-ai-monitor stats gpu dgx-01 dgx-02

# Check CPU stats for multiple hosts
cloudmesh-ai-monitor stats cpu dgx-01
```

### Infrastructure Health
```bash
cloudmesh-ai-monitor check-exporter --url http://dgx-node:9100/metrics
cloudmesh-ai-monitor oom-check
```

## Key Achievements

- **Textual TUI**: Implemented a professional Terminal User Interface using the `textual` framework, providing a real-time fleet dashboard and an interactive host management setup screen.
- **Modular Architecture**: Organized the code into `terminalgui` (for TUI), `command` (for CLI), and `grafana` (for future web-based monitoring) frameworks.
- **Comprehensive CLI**: Added a wide array of commands via `click` and `rich`, including:
  - `cmc monitor setup [add|remove|activate|deactivate]`: Manage monitored hosts.
  - `cmc monitor dashboard`: Launch the Textual TUI (default) or Grafana.
  - `cmc monitor run [host] [tool]`: Execute interactive tools like `nvtop` on remote hosts.
  - `cmc monitor stats [gpu|cpu] [hosts]`: Aggregate hardware stats across the fleet.
  - `cmc monitor probe [hosts]`: Auto-detect hardware and update configuration.
  - `cmc monitor oom-check`: Scan for Out-of-Memory events.
  - `cmc monitor check-exporter`: Verify Prometheus GPU exporter health.
- **Dynamic GUI Selection**: The system now respects the `CMC_GUI` environment variable to switch between monitoring interfaces, defaulting to `terminalgui`.
- **Core Logic**: Centralized host management and remote execution logic to ensure consistency across different interfaces.