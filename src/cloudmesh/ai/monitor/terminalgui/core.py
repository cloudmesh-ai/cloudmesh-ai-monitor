"""
Core logic for the Terminal GUI monitoring framework.
"""
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
import subprocess
import requests
from rich.console import Console
from cloudmesh.ai.common.io import load_yaml, dump_yaml

console = Console()

class HostManager:
    """Manages remote AI hosts via a YAML configuration file."""
    def __init__(self, config_path: str = "~/.config/cloudmesh/ai/hosts.yaml"):
        self.config_path = Path(config_path).expanduser()
        self.full_cfg = self._load_full_config()
        self.hosts_data = self.full_cfg.get("cloudmesh", {}).get("ai", {}).get("hosts", {})

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
        dump_yaml(self.config_path, self.full_cfg)

    def resolve_host(self, identifier: str) -> Optional[str]:
        """Resolves a label to the actual SSH hostname."""
        if identifier in self.hosts_data:
            return self.hosts_data[identifier].get("hostname")
        return identifier

    def get_host_info(self, label: str) -> Dict[str, Any]:
        """Returns metadata for a specific host identified by label."""
        return self.hosts_data.get(label, {})

    def add_host(self, label: str, hostname: str, active: bool = True, refresh_interval: int = 10, devices: Optional[str] = None):
        """Adds or updates a host in the configuration using label as the unique key."""
        if label in self.hosts_data:
            # Update existing host, preserving current metrics
            self.hosts_data[label]["hostname"] = hostname
            self.hosts_data[label]["active"] = active
            self.hosts_data[label]["refresh_interval"] = refresh_interval
            self.hosts_data[label]["devices"] = devices or ""
        else:
            # Add new host
            self.hosts_data[label] = {
                "hostname": hostname,
                "active": active,
                "gpu_usage": "N/A",
                "gpu_temp": "N/A",
                "mem_usage": "N/A",
                "refresh_interval": refresh_interval,
                "devices": devices or ""
            }
            # Add to order list
            if "cloudmesh" in self.full_cfg and "ai" in self.full_cfg["cloudmesh"]:
                order = self.full_cfg["cloudmesh"]["ai"].setdefault("host_order", [])
                if label not in order:
                    order.append(label)
        self.save()

    def update_metrics(self, label: str, gpu_usage: str, gpu_temp: str, mem_usage: str):
        """Updates the metrics for a host in the configuration file."""
        if label in self.hosts_data:
            self.hosts_data[label]["gpu_usage"] = gpu_usage
            self.hosts_data[label]["gpu_temp"] = gpu_temp
            self.hosts_data[label]["mem_usage"] = mem_usage
            self.save()

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

    def rename_host(self, old_label: str, new_label: str, hostname: str, active: bool = True, refresh_interval: int = 10, devices: Optional[str] = None):
        """Renames a label while preserving its metrics."""
        if old_label in self.hosts_data:
            data = self.hosts_data.pop(old_label)
            data["hostname"] = hostname
            data["active"] = active
            data["refresh_interval"] = refresh_interval
            data["devices"] = devices or ""
            self.hosts_data[new_label] = data
            self.save()
        else:
            # Fallback to add_host if old_label not found
            self.add_host(new_label, hostname, active, refresh_interval, devices)

    def set_active(self, label: str, status: bool):
        """Sets the active status of a host."""
        if label in self.hosts_data:
            self.hosts_data[label]["active"] = status
            self.save()

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
        """Returns hosts in the order specified by host_order."""
        order = self.full_cfg.get("cloudmesh", {}).get("ai", {}).get("host_order", [])
        if not order:
            return list(self.hosts_data.items())
        
        ordered_hosts = []
        for label in order:
            if label in self.hosts_data:
                ordered_hosts.append((label, self.hosts_data[label]))
        
        # Add any hosts that might be in hosts_data but not in host_order
        for label, data in self.hosts_data.items():
            if label not in order:
                ordered_hosts.append((label, data))
                
        return ordered_hosts

class RemoteExecutor:
    """Handles execution of commands on remote hosts via SSH."""
    @staticmethod
    def run_interactive(hostname: str, tool: str):
        """Runs an interactive tool (top, nvtop, etc.) on a remote host."""
        cmd = ["ssh", "-t", hostname, tool]
        try:
            subprocess.run(cmd)
        except Exception as e:
            console.print(f"[bold red]Error launching {tool} on {hostname}:[/bold red] {e}")

    @staticmethod
    def run_command(hostname: str, command: str) -> Optional[str]:
        """Runs a non-interactive command and returns the output."""
        cmd = ["ssh", hostname, command]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    @staticmethod
    def probe_hardware(hostname: str) -> Dict[str, str]:
        """Probes the remote host for GPU and CPU hardware types."""
        results = {"gpu": "unknown", "cpu": "unknown"}
        if RemoteExecutor.run_command(hostname, "nvidia-smi -L"):
            results["gpu"] = "nvidia"
        elif RemoteExecutor.run_command(hostname, "lspci | grep -i vga | grep -i amd") or \
             RemoteExecutor.run_command(hostname, "rocm-smi"):
            results["gpu"] = "amd"
        else:
            results["gpu"] = "none"
            
        cpu_info = RemoteExecutor.run_command(hostname, "lscpu")
        if cpu_info:
            cpu_info_lower = cpu_info.lower()
            if "genuineintel" in cpu_info_lower:
                results["cpu"] = "intel"
            elif "authenticamd" in cpu_info_lower:
                results["cpu"] = "amd"
            elif "aarch64" in cpu_info_lower or "arm" in cpu_info_lower:
                results["cpu"] = "arm"
        return results