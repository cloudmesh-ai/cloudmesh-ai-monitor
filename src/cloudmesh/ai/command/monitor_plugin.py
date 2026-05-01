import subprocess
import os
import getpass
import threading
from cloudmesh.ai.command.plugin import PanelPlugin
from cloudmesh.ai.monitor.core import HostManager
from typing import Any


class MonitorPlugin(PanelPlugin):
    # Set to track hosts currently being probed
    PROBING_HOSTS = set()
    _probing_lock = threading.Lock()

    # Registry for custom Python probe functions
    # Format: { "function_name": callable(host_info) -> dict }
    PROBE_FUNCTIONS = {
        "default_gpu": lambda info: {
            "gpu_usage": "0%",
            "gpu_temp": "0 C",
            "mem_usage": "0%",
            "cpu_usage": "0%",
            "cpu_temp": "0 C",
            "success": True,
        },
    }

    @property
    def plugin_id(self) -> str:
        return "monitor"

    @property
    def plugin_name(self) -> str:
        return "Host Monitor"

    @property
    def plugin_icon(self) -> str:
        return "fa-solid fa-desktop"

    @property
    def plugin_description(self) -> str:
        return "Real-time monitoring of GPU, CPU, and Memory usage across AI compute hosts."

    def get_data(self) -> Any:
        hm = HostManager.get_instance()
        hosts_data = []
        with self._probing_lock:
            current_probing = set(self.PROBING_HOSTS)
            
        for label, info in hm.get_hosts_ordered():
            hosts_data.append(
                {
                    "label": label,
                    "hostname": info.get("hostname", "N/A"),
                    "active": info.get("active", True),
                    "refresh_interval": info.get("refresh_interval", 10),
                    "gpu_usage": info.get("gpu_usage", "N/A"),
                    "gpu_temp": info.get("gpu_temp", "N/A"),
                    "mem_usage": info.get("mem_usage", "N/A"),
                    "cpu_usage": info.get("cpu_usage", "N/A"),
                    "cpu_temp": info.get("cpu_temp", "N/A"),
                    "who": info.get("who", "N/A"),
                    "last_probe_success": info.get("last_probe_success"),
                    "probing": label in current_probing,
                    "last_updated": (
                        info.get("probe", {}).get("time", "N/A")
                        if isinstance(info.get("probe"), dict)
                        else "N/A"
                    ),
                }
            )
        return hosts_data

    def get_assets(self):
        return {
            "monitor_table_config.js": "cloudmesh-ai-monitor/src/cloudmesh/ai/command/monitor_table_config.js",
            "monitor_table_styles.css": "cloudmesh-ai-monitor/src/cloudmesh/ai/command/monitor_table_styles.css",
        }

    def update_interval(self, interval: int):
        """Updates the refresh interval for all active hosts."""
        hm = HostManager.get_instance()
        count = 0
        for label, info in hm.get_hosts_ordered():
            if info.get("active", True):
                hm.add_host(
                    label,
                    info.get("hostname"),
                    info.get("active", True),
                    interval,
                    info.get("probe_cmd"),
                )
                count += 1
        return {"success": True, "updated": count, "interval": interval}

    def _get_host_info(self, hm, label):
        """Helper to find host info by label from HostManager."""
        for l, info in hm.get_hosts_ordered():
            if l == label:
                return info
        return None

    def update_host_interval(self, label: str, interval: int):
        """Updates the refresh interval for a specific host."""
        hm = HostManager.get_instance()
        info = self._get_host_info(hm, label)
        if info:
            hm.add_host(
                label,
                info.get("hostname"),
                info.get("active", True),
                interval,
                info.get("probe_cmd"),
            )
            return {"success": True, "label": label, "interval": interval}
        return {"success": False, "error": "Host not found"}

    def update_host_active(self, label: str, active: int):
        """Updates the active status of a host."""
        try:
            # Convert 1/0 to boolean
            active_bool = bool(active)
                
            hm = HostManager.get_instance()
            hm.set_active(label, active_bool)
            return {"success": True, "label": label, "active": active_bool}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _clean_ssh_output(self, output: str) -> str:
        """Removes specific SSH post-quantum warnings from the output."""
        if not output:
            return ""
        
        # Specifically target the post-quantum key exchange warnings
        pq_patterns = [
            "connection is not using a post-quantum key exchange algorithm",
            "vulnerable to \"store now, decrypt later\"",
            "openssh.com/pq.html"
        ]
        
        lines = output.splitlines()
        cleaned_lines = []
        for line in lines:
            # Only skip the line if it contains one of the specific PQ warning patterns
            if any(p.lower() in line.lower() for p in pq_patterns):
                continue
            cleaned_lines.append(line)
            
        return "\n".join(cleaned_lines)

    def _get_remote_users(self, hostname: str) -> str:
        """Fetches unique logged-in users from the remote host."""
        try:
            # 'users' command returns a space-separated list of usernames
            cmd = f"ssh {hostname} \"users\""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                output = self._clean_ssh_output(result.stdout).strip()
                if not output:
                    return "None"
                # Split by whitespace and get unique users
                users = sorted(list(set(output.split())))
                return ", ".join(users)
        except Exception as e:
            # Use print as logger is not defined in this module
            print(f"[ERROR] Failed to fetch remote users for {hostname}: {e}")
        return "N/A"

    def refresh_host(self, label: str, automatic: bool = False):
        """Triggers a probe for a specific host. If automatic is True, respects the active status."""
        with self._probing_lock:
            self.PROBING_HOSTS.add(label)
            
        try:
            hm = HostManager.get_instance()
            info = self._get_host_info(hm, label)
            if not info:
                return {"success": False, "error": "Host not found"}

            if automatic and not info.get("active", True):
                return {"success": True, "message": "Host is inactive, skipping automatic probe"}

            hostname = info.get("hostname")
            remote_users = self._get_remote_users(hostname)

            probe_cmd = info.get(
                "probe_cmd",
                "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits",
            )

            # Support for Python functions defined in hosts.yaml
            # 1. Check for fully qualified paths (e.g., cloudmesh.ai.common.monitor.probe.cm-dgx-smi)
            if "cloudmesh.ai" in probe_cmd:
                try:
                    import importlib

                    parts = probe_cmd.split()
                    full_path = parts[0]
                    args = parts[1:]

                    module_path, func_name_raw = full_path.rsplit(".", 1)
                    # Map hyphenated names to underscored function names (cm-dgx-smi -> cm_dgx_smi)
                    func_name = func_name_raw.replace("-", "_")

                    module = importlib.import_module(module_path)
                    probe_func = getattr(module, func_name)

                    # The functions in probe.py expect (hostname, *args)
                    hostname = info.get("hostname")
                    
                    # Avoid passing the hostname twice if it's already the first argument in probe_cmd
                    actual_args = args
                    if args and args[0] == hostname:
                        actual_args = args[1:]
                    
                    res = probe_func(hostname, *actual_args)

                    if isinstance(res, dict) and "gpu_usage" in res:
                        hm.update_metrics(
                            label,
                            gpu_usage=res.get("gpu_usage", "N/A"),
                            gpu_temp=res.get("gpu_temp", "N/A"),
                            mem_usage=res.get("mem_usage", "N/A"),
                            cpu_usage=res.get("cpu_usage", "N/A"),
                            cpu_temp=res.get("cpu_temp", "N/A"),
                            last_probe_success=True,
                            who=remote_users,
                        )
                        return {
                            "success": True,
                            "label": label,
                            "message": f"Python probe {func_name} executed successfully",
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Probe returned unexpected format or error: {res}",
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Dynamic Python probe failed: {str(e)}",
                    }

            # 2. Check for explicit 'python:' prefix or registry lookup
            func_name = None
            if probe_cmd.startswith("python:"):
                func_name = probe_cmd.replace("python:", "").strip()
            else:
                first_word = probe_cmd.split()[0] if probe_cmd.split() else ""
                if probe_cmd in self.PROBE_FUNCTIONS:
                    func_name = probe_cmd
                elif first_word in self.PROBE_FUNCTIONS:
                    func_name = first_word

            if func_name:
                probe_func = self.PROBE_FUNCTIONS.get(func_name)
                try:
                    res = probe_func(info)
                    if isinstance(res, dict) and res.get("success"):
                        hm.update_metrics(
                            label,
                            gpu_usage=res.get("gpu_usage", "N/A"),
                            gpu_temp=res.get("gpu_temp", "N/A"),
                            mem_usage=res.get("mem_usage", "N/A"),
                            cpu_usage=res.get("cpu_usage", "N/A"),
                            cpu_temp=res.get("cpu_temp", "N/A"),
                            last_probe_success=True,
                            who=remote_users,
                        )
                        return {
                            "success": True,
                            "label": label,
                            "message": f"Python probe {func_name} executed successfully",
                        }
                    else:
                        return {
                            "success": False,
                            "error": res.get("error", "Python probe failed"),
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Python probe execution failed: {str(e)}",
                    }

            # Fallback to SSH shell command execution
            hostname = info.get("hostname")
            try:
                # Execute the probe command via SSH using a login shell to ensure PATH is loaded
                full_cmd = f"ssh {hostname} \"bash -l -c '{probe_cmd}'\""
                result = subprocess.run(
                    full_cmd, shell=True, capture_output=True, text=True, timeout=15
                )

                if result.returncode != 0:
                    error_msg = self._clean_ssh_output(result.stderr or result.stdout)
                    if "not found" in error_msg.lower():
                        import re

                        match = re.search(
                            r"([a-zA-Z0-9\-_/.]+): command not found", error_msg
                        )
                        cmd_name = match.group(1) if match else "the probe tool"
                        error_msg = f"Command '{cmd_name}' not found on remote host. Please ensure it is installed or use an absolute path in the probe configuration."

                    hm.update_metrics(
                        label, "N/A", "N/A", "N/A", "N/A", "N/A", last_probe_success=False, who=remote_users
                    )
                    return {"success": False, "error": f"Probe failed: {error_msg.strip()}"}

                output = self._clean_ssh_output(result.stdout).strip()
                if not output:
                    return {"success": False, "error": "No output from probe"}

                parts = output.split(",")
                if len(parts) >= 3:
                    gpu_usage = parts[0].strip()
                    gpu_temp = parts[1].strip()
                    mem_used = parts[2].strip()
                    mem_usage = mem_used
                    if len(parts) >= 4:
                        try:
                            used = float(mem_used)
                            total = float(parts[3].strip())
                            mem_usage = f"{(used/total)*100:.1f}%"
                        except (ValueError, ZeroDivisionError):
                            pass

                    hm.update_metrics(
                        label,
                        gpu_usage=f"{gpu_usage}%",
                        gpu_temp=f"{gpu_temp} C",
                        mem_usage=mem_usage,
                        last_probe_success=True,
                        who=remote_users,
                    )
                    return {
                        "success": True,
                        "label": label,
                        "message": "Host refreshed successfully",
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unexpected probe output format: {output}",
                    }

            except Exception as e:
                hm.update_metrics(
                    label, "N/A", "N/A", "N/A", "N/A", "N/A", last_probe_success=False, who=remote_users
                )
                return {"success": False, "error": f"Probe execution failed: {str(e)}"}
        finally:
            with self._probing_lock:
                self.PROBING_HOSTS.discard(label)

    def get_terminal_cmd(self, label: str):
        """Returns the SSH command to open a terminal for the host."""
        hm = HostManager.get_instance()
        info = self._get_host_info(hm, label)
        if info:
            hostname = info.get("hostname")
            return {"success": True, "cmd": f"ssh {hostname}"}
        return {"success": False, "error": "Host not found"}

    def open_terminal(self, label: str):
        """Opens a terminal window on the server host and brings it to front."""
        hm = HostManager.get_instance()
        info = self._get_host_info(hm, label)
        if not info:
            return {"success": False, "error": "Host not found"}

        hostname = info.get("hostname")
        cmd = f"ssh {hostname}"

        # Try iTerm2 first, then fall back to default Terminal
        try:
            # Check if iTerm2 is installed
            iterm_check = subprocess.run(
                ["which", "iterm2"], capture_output=True
            )  # This is a simplification
            # Better way to check for iTerm2 is to try the osascript

            # Try iTerm2
            iterm_script = f'tell application "iTerm" to create window with default profile, then tell current session of current window to write text "{cmd}"'
            subprocess.run(["osascript", "-e", iterm_script], check=True)
            subprocess.run(
                ["osascript", "-e", 'tell application "iTerm" to activate'], check=True
            )
            return {"success": True, "message": f"iTerm2 opened for {hostname}"}
        except Exception:
            try:
                # Fallback to default Terminal
                script = f'tell application "Terminal" to do script "{cmd}"\ntell application "Terminal" to activate'
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": f"Terminal opened for {hostname}"}
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to open any terminal: {str(e)}",
                }
