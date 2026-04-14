"""
Core logic for the Terminal GUI monitoring framework.
"""
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
import subprocess
import requests
import re
import logging
import os
import copy
import threading
from datetime import datetime
from rich.console import Console
from cloudmesh.ai.common.io import load_yaml, dump_yaml

# Logging configuration
log_path = Path("~/.config/cloudmesh/ai/monitor.log").expanduser()
log_path.parent.mkdir(parents=True, exist_ok=True)

# Get log level from environment variable, default to INFO
log_level_str = os.environ.get("CLOUDMESH_LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# Explicitly configure the root logger to ensure the file is created
root_logger = logging.getLogger()
root_logger.setLevel(log_level)

# Remove existing handlers to avoid duplicate logs if re-initialized
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Create file handler
file_handler = logging.FileHandler(str(log_path))
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
root_logger.addHandler(file_handler)

logger = logging.getLogger("cloudmesh.ai.monitor")

console = Console()

class HostManager:
    """Manages remote AI hosts via YAML configuration files."""
    def __init__(self, config_path: str = "~/.config/cloudmesh/ai/hosts.yaml", status_path: str = "~/.config/cloudmesh/ai/hosts-status.yaml"):
        self.config_path = Path(config_path).expanduser()
        self.status_path = Path(status_path).expanduser()
        self.full_cfg = self._load_full_config()
        self.hosts_data = self.full_cfg.get("cloudmesh", {}).get("ai", {}).get("hosts", {})
        self._lock = threading.Lock()

    def _load_full_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {"cloudmesh": {"ai": {"hosts": {}, "host_order": []}}}
        cfg = load_yaml(self.config_path)
        if not cfg:
            return {"cloudmesh": {"ai": {"hosts": {}, "host_order": []}}}
        
        # Ensure structure exists
        cfg.setdefault("cloudmesh", {}).setdefault("ai", {}).setdefault("hosts", {})
        cfg["cloudmesh"]["ai"].setdefault("host_order", [])
        return cfg

    def save(self):
        """Persists the current configuration to disk."""
        with self._lock:
            dump_yaml(self.config_path, self.full_cfg)

    def _load_status(self) -> Dict[str, Any]:
        """Loads the status configuration file and returns the hosts dictionary."""
        if not self.status_path.exists():
            return {}
        cfg = load_yaml(self.status_path)
        if not cfg or not isinstance(cfg, dict):
            return {}
        return cfg.get("cloudmesh", {}).get("ai", {}).get("hosts", {})

    def _save_status(self, hosts_status: Dict[str, Any]):
        """Persists the status configuration to disk safely with full hierarchy."""
        full_status_cfg = {
            "cloudmesh": {
                "ai": {
                    "hosts": hosts_status
                }
            }
        }
        with self._lock:
            dump_yaml(self.status_path, full_status_cfg)

    def resolve_host(self, identifier: str) -> Optional[str]:
        """Resolves a label to the actual SSH hostname."""
        if identifier in self.hosts_data:
            return self.hosts_data[identifier].get("hostname")
        return identifier

    def get_host_info(self, label: str) -> Dict[str, Any]:
        """Returns metadata for a specific host, merging config and status."""
        info = self.hosts_data.get(label, {}).copy()
        status = self._load_status().get(label, {})
        info.update(status)
        return info

    def add_host(self, label: str, hostname: str, active: bool = True, refresh_interval: int = 10, probe_cmd: Optional[str] = None):
        """Adds or updates a host in the configuration using label as the unique key."""
        default_probe = "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        if label in self.hosts_data:
            # Update existing host
            self.hosts_data[label]["hostname"] = hostname
            self.hosts_data[label]["active"] = active
            self.hosts_data[label]["refresh_interval"] = refresh_interval
            self.hosts_data[label]["probe_cmd"] = probe_cmd or self.hosts_data[label].get("probe_cmd", default_probe)
            logger.info(f"Updated host: {label} ({hostname})")
        else:
            # Add new host - only store config here
            self.hosts_data[label] = {
                "hostname": hostname,
                "active": active,
                "refresh_interval": refresh_interval,
                "probe_cmd": probe_cmd or default_probe
            }
            # Add to order list
            if "cloudmesh" in self.full_cfg and "ai" in self.full_cfg["cloudmesh"]:
                order = self.full_cfg["cloudmesh"]["ai"].setdefault("host_order", [])
                if label not in order:
                    order.append(label)
            logger.info(f"Added new host: {label} ({hostname})")
        self.save()

    def update_metrics(self, label: str, gpu_usage: Any, gpu_temp: Any, mem_usage: Any, cpu_usage: Any = "N/A", cpu_temp: Any = "N/A", last_probe_success=None, last_probe_time: Any = "N/A"):
        """Updates the metrics for a host in the status file."""
        # We use the status file for metrics to avoid frequent writes to the main config
        hosts_status = self._load_status()
        
        host_status = hosts_status.setdefault(label, {})
        host_status["gpu_usage"] = gpu_usage
        host_status["gpu_temp"] = gpu_temp
        host_status["mem_usage"] = mem_usage
        host_status["cpu_usage"] = cpu_usage
        host_status["cpu_temp"] = cpu_temp
        
        # Group probe results into the 'probe' dictionary
        probe_info = host_status.setdefault("probe", {})
        probe_info["time"] = last_probe_time if last_probe_time != "N/A" else datetime.now().isoformat()
        probe_info["output"] = {
            "gpu_usage": copy.deepcopy(gpu_usage),
            "gpu_temp": copy.deepcopy(gpu_temp),
            "mem_usage": copy.deepcopy(mem_usage),
            "cpu_usage": copy.deepcopy(cpu_usage),
            "cpu_temp": copy.deepcopy(cpu_temp),
        }
        
        self._save_status(hosts_status)
        if last_probe_success is False:
            logger.warning(f"Probe failed for host: {label}")

    def remove_host(self, label: str):
        """Removes a host from the configuration."""
        if label in self.hosts_data:
            del self.hosts_data[label]
            # Remove from order list
            if "cloudmesh" in self.full_cfg and "ai" in self.full_cfg["cloudmesh"]:
                order = self.full_cfg["cloudmesh"]["ai"].get("host_order", [])
                if label in order:
                    order.remove(label)
            self.save()
            logger.info(f"Removed host: {label}")

    def rename_host(self, old_label: str, new_label: str, hostname: str, active: bool = True, refresh_interval: int = 10, probe_cmd: Optional[str] = None):
        """Renames a label while preserving its metrics."""
        if old_label in self.hosts_data:
            data = self.hosts_data.pop(old_label)
            data["hostname"] = hostname
            data["active"] = active
            data["refresh_interval"] = refresh_interval
            if probe_cmd:
                data["probe_cmd"] = probe_cmd
            self.hosts_data[new_label] = data
            self.save()
            logger.info(f"Renamed host: {old_label} -> {new_label}")
        else:
            # Fallback to add_host if old_label not found
            self.add_host(new_label, hostname, active, refresh_interval, probe_cmd)

    def set_active(self, label: str, status: bool):
        """Sets the active status of a host."""
        if label in self.hosts_data:
            self.hosts_data[label]["active"] = status
            self.save()
            logger.info(f"Set host {label} active status to {status}")

    def move_host(self, label: str, direction: str):
        """Moves a host up or down in the configuration order."""
        # Use host_order as the source of truth for ordering
        order = self.full_cfg.get("cloudmesh", {}).get("ai", {}).get("host_order", [])
        if not order:
            order = list(self.hosts_data.keys())
        
        if label not in order:
            return

        idx = order.index(label)

        if direction == "up" and idx > 0:
            order[idx], order[idx-1] = order[idx-1], order[idx]
        elif direction == "down" and idx < len(order) - 1:
            order[idx], order[idx+1] = order[idx+1], order[idx]
        else:
            return

        self.full_cfg["cloudmesh"]["ai"]["host_order"] = order
        self.save()

    def get_hosts_ordered(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Returns hosts in the order specified by host_order, merging status."""
        order = self.full_cfg.get("cloudmesh", {}).get("ai", {}).get("host_order", [])
        if not order:
            # If no order, use hosts_data keys
            labels = list(self.hosts_data.keys())
        else:
            labels = order
        
        ordered_hosts = []
        for label in labels:
            if label in self.hosts_data:
                ordered_hosts.append((label, self.get_host_info(label)))
        
        # Add any hosts that might be in hosts_data but not in order
        if order:
            for label, data in self.hosts_data.items():
                if label not in order:
                    ordered_hosts.append((label, self.get_host_info(label)))
                
        return ordered_hosts