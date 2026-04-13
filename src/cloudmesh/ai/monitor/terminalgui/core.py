"""
Core logic for the Terminal GUI monitoring framework.
"""
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
import subprocess
import requests
import re
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

    def add_host(self, label: str, hostname: str, active: bool = True, refresh_interval: int = 10, probe_cmd: Optional[str] = None):
        """Adds or updates a host in the configuration using label as the unique key."""
        default_probe = "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        if label in self.hosts_data:
            # Update existing host, preserving current metrics
            self.hosts_data[label]["hostname"] = hostname
            self.hosts_data[label]["active"] = active
            self.hosts_data[label]["refresh_interval"] = refresh_interval
            self.hosts_data[label]["probe_cmd"] = probe_cmd or self.hosts_data[label].get("probe_cmd", default_probe)
        else:
            # Add new host
            self.hosts_data[label] = {
                "hostname": hostname,
                "active": active,
                "gpu_usage": "N/A",
                "gpu_temp": "N/A",
                "mem_usage": "N/A",
                "cpu_usage": "N/A",
                "cpu_temp": "N/A",
                "refresh_interval": refresh_interval,
                "probe_cmd": probe_cmd or default_probe
            }
            # Add to order list
            if "cloudmesh" in self.full_cfg and "ai" in self.full_cfg["cloudmesh"]:
                order = self.full_cfg["cloudmesh"]["ai"].setdefault("host_order", [])
                if label not in order:
                    order.append(label)
        self.save()

    def update_metrics(self, label: str, gpu_usage: Any, gpu_temp: Any, mem_usage: Any, cpu_usage: Any = "N/A", cpu_temp: Any = "N/A", last_probe_success=None):
        """Updates the metrics for a host in the configuration file."""
        if label in self.hosts_data:
            self.hosts_data[label]["gpu_usage"] = gpu_usage
            self.hosts_data[label]["gpu_temp"] = gpu_temp
            self.hosts_data[label]["mem_usage"] = mem_usage
            self.hosts_data[label]["cpu_usage"] = cpu_usage
            self.hosts_data[label]["cpu_temp"] = cpu_temp
            if last_probe_success is not None:
                self.hosts_data[label]["last_probe_success"] = last_probe_success
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
        else:
            # Fallback to add_host if old_label not found
            self.add_host(new_label, hostname, active, refresh_interval, probe_cmd)

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

def cm_dgx_smi(hostname: str, devices: str = "0"):
    """
    Returns a string mimicking:
    utilization.gpu, temperature.gpu, memory.used, memory.total, cpu_util, cpu_temp
    Designed for NVIDIA DGX nodes.
    Supports multiple GPUs via the 'devices' parameter (e.g., "0,1,2,4").
    Uses nvidia-smi for GPU and standard Linux tools for CPU/RAM.
    """
    try:
        # 1. GPU Metrics via nvidia-smi
        # We include 'index' to filter by the requested devices
        gpu_cmd = "nvidia-smi --query-gpu=index,utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        success_gpu, gpu_res = RemoteExecutor.run_command(hostname, gpu_cmd)
        if not success_gpu or not gpu_res:
            return f"Error: nvidia-smi failed on {hostname}"
        
        requested_devices = [d.strip() for d in devices.split(",")]
        
        utils, temps, percs, totals = [], [], [], []
        
        for line in gpu_res.splitlines():
            parts = [x.strip() for x in line.split(',')]
            if len(parts) >= 5:
                idx, util, temp, used, total = parts[:5]
                if idx in requested_devices:
                    utils.append(util)
                    temps.append(temp)
                    try:
                        u_val = float(used)
                        t_val = float(total)
                        perc = round((u_val / t_val) * 100, 1) if t_val > 0 else 0
                        gb = round(t_val / 1024, 1)
                        percs.append(f"{perc}/{gb}")
                        totals.append(gb)
                    except ValueError:
                        percs.append("N/A")
                        totals.append(None)
        
        if not utils:
            return f"Error: No matching GPUs found for devices {devices} on {hostname}"
            
        # Memory: store as list of [perc, total]
        mem_list = []
        for p, t in zip(percs, totals):
            if p != "N/A" and t is not None:
                try:
                    # percs currently contains "perc/gb" strings from lines 192
                    p_val = float(p.split('/')[0])
                    mem_list.append([p_val, t])
                except (ValueError, IndexError):
                    mem_list.append(["N/A", "N/A"])
            else:
                mem_list.append(["N/A", "N/A"])

        # 2. CPU Usage via top
        cpu_u_cmd = "top -bn1 | head -n 7"
        success_cpu_u, cpu_u_res = RemoteExecutor.run_command(hostname, cpu_u_cmd)
        cpu_util = "N/A"
        if success_cpu_u and cpu_u_res:
            for line in cpu_u_res.splitlines():
                if "Cpu(s)" in line:
                    match = re.search(r"(\d+\.\d+)\s+id", line)
                    if match:
                        try:
                            idle = float(match.group(1))
                            cpu_util = str(round(100.0 - idle, 2))
                        except ValueError:
                            pass
                    break

        # 3. CPU Temp via sensors/sysfs
        cpu_temp = "N/A"
        success_s, s_res = RemoteExecutor.run_command(hostname, "sensors")
        if success_s and s_res:
            # Try specific labels first
            for line in s_res.splitlines():
                if any(label in line for label in ["Package id 0", "Core 0", "CPU Temp", "Composite"]):
                    temp_match = re.search(r"(\+?\d+\.\d+)", line)
                    if temp_match:
                        cpu_temp = temp_match.group(1).replace("+", "")
                        break
            
            # Fallback: just find the first temperature-looking value in sensors output
            if cpu_temp == "N/A":
                temp_match = re.search(r"(\+?\d+\.\d+)\s*°C", s_res)
                if temp_match:
                    cpu_temp = temp_match.group(1).replace("+", "")
        
        if cpu_temp == "N/A":
            # 1. Try sysfs hwmon (most common on modern Ubuntu/DGX)
            # Broaden search to any file containing 'temp' and 'input'
            success_hw, hw_res = RemoteExecutor.run_command(hostname, "find /sys/class/hwmon/hwmon* -name '*temp*input*' -exec cat {} + 2>/dev/null")
            if success_hw and hw_res:
                hw_temps = []
                for line in hw_res.splitlines():
                    val = line.strip()
                    if val.isdigit():
                        hw_temps.append(int(val))
                if hw_temps:
                    # hwmon temps are usually in millidegrees
                    cpu_temp = str(round(max(hw_temps) / 1000.0, 2))

        if cpu_temp == "N/A":
            # 2. Try thermal_zone
            # Broaden search to any file containing 'temp'
            success_t, t_res = RemoteExecutor.run_command(hostname, "find /sys/class/thermal/thermal_zone* -name '*temp*' -exec cat {} + 2>/dev/null")
            if success_t and t_res:
                t_temps = []
                for line in t_res.splitlines():
                    val = line.strip()
                    if val.isdigit():
                        t_temps.append(int(val))
                if t_temps:
                    cpu_temp = str(round(max(t_temps) / 1000.0, 2))

        if cpu_temp == "N/A":
            # 2b. Direct path fallbacks (last resort for sysfs)
            # Try the most common paths directly
            direct_paths = [
                "/sys/class/thermal/thermal_zone0/temp",
                "/sys/class/hwmon/hwmon0/temp1_input",
                "/sys/class/hwmon/hwmon1/temp1_input",
                "/sys/class/hwmon/hwmon2/temp1_input",
            ]
            for path in direct_paths:
                success_p, p_res = RemoteExecutor.run_command(hostname, f"cat {path} 2>/dev/null")
                if success_p and p_res:
                    val = p_res.strip()
                    if val.isdigit():
                        cpu_temp = str(round(int(val) / 1000.0, 2))
                        break

        return {
            "gpu_usage": [float(x) for x in utils],
            "gpu_temp": [float(x) for x in temps],
            "mem_usage": mem_list,
            "cpu_usage": [float(cpu_util)] if cpu_util != "N/A" else ["N/A"],
            "cpu_temp": [float(cpu_temp)] if cpu_temp != "N/A" else ["N/A"]
        }

    except Exception as e:
        return f"Error retrieving DGX metrics: {e}"

def cm_spark_smi(hostname: str):
    """
    Returns a string mimicking:
    utilization.gpu, temperature.gpu, memory.used, memory.total, cpu_util, cpu_temp
    Designed for NVIDIA Spark/GPU nodes.
    Uses nvidia-smi for GPU and standard Linux tools for CPU/RAM.
    """
    try:
        # 1. GPU Metrics via nvidia-smi (Strictly NVIDIA)
        # We query utilization, temperature, and memory.
        gpu_cmd = "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        success_gpu, gpu_res = RemoteExecutor.run_command(hostname, gpu_cmd)
        if not success_gpu or not gpu_res:
            return f"Error: nvidia-smi failed on {hostname}"
        
        # Process all GPUs to support the requested formatting
        utils, temps, percs, totals = [], [], [], []
        for line in gpu_res.splitlines():
            parts = [x.strip() for x in line.split(',')]
            if len(parts) >= 4:
                u, t, used, total = parts[:4]
                utils.append(u)
                temps.append(t)
                try:
                    u_val = float(used)
                    t_val = float(total)
                    perc = round((u_val / t_val) * 100, 1) if t_val > 0 else 0
                    gb = round(t_val / 1024, 1)
                    percs.append(f"{perc}/{gb}")
                    totals.append(gb)
                except ValueError:
                    percs.append("N/A")
                    totals.append(None)

        if not utils:
            return f"Error: nvidia-smi failed on {hostname}"

        # Memory: store as list of [perc, total]
        mem_list = []
        # Check if we actually have valid GPU memory data
        has_valid_gpu_mem = any(t is not None for t in totals)
        
        if not has_valid_gpu_mem:
            # Fallback to system memory if no valid GPU memory found
            success_mem, mem_res = RemoteExecutor.run_command(hostname, "cat /proc/meminfo")
            if success_mem and mem_res:
                mem_data = {}
                for line in mem_res.splitlines():
                    if ':' in line:
                        key, val = line.split(':', 1)
                        match = re.search(r"(\d+)", val)
                        if match:
                            mem_data[key.strip()] = int(match.group(1))
                total_kb = mem_data.get("MemTotal", 0)
                avail_kb = mem_data.get("MemAvailable", mem_data.get("MemFree", 0))
                if total_kb > 0:
                    total_gb = round(total_kb / (1024*1024), 1)
                    used_kb = total_kb - avail_kb
                    perc = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0
                    mem_list.append([perc, total_gb])
                else:
                    mem_list.append(["N/A", "N/A"])
            else:
                mem_list.append(["N/A", "N/A"])
        else:
            for p, t in zip(percs, totals):
                if p != "N/A" and t is not None:
                    try:
                        p_val = float(p.split('/')[0])
                        mem_list.append([p_val, t])
                    except (ValueError, IndexError):
                        mem_list.append(["N/A", "N/A"])
                else:
                    mem_list.append(["N/A", "N/A"])

        # 2. CPU Usage via top (Linux) - Get raw top summary and parse in Python
        cpu_u_cmd = "top -bn1 | head -n 7"
        success_cpu_u, cpu_u_res = RemoteExecutor.run_command(hostname, cpu_u_cmd)
        cpu_util = "N/A"
        if success_cpu_u and cpu_u_res:
            for line in cpu_u_res.splitlines():
                if "Cpu(s)" in line:
                    # Look for the idle percentage (e.g., "99.4 id")
                    match = re.search(r"(\d+\.\d+)\s+id", line)
                    if match:
                        try:
                            idle = float(match.group(1))
                            cpu_util = str(round(100.0 - idle, 2))
                        except ValueError:
                            pass
                    break

        # 3. CPU Temp via sensors/sysfs (Linux) - Get raw data and parse in Python
        cpu_temp = "N/A"
        # Try sensors first
        success_s, s_res = RemoteExecutor.run_command(hostname, "sensors")
        if success_s and s_res:
            for line in s_res.splitlines():
                if "Package id 0" in line or "Core 0" in line:
                    # Extract temperature (e.g., "+32.0°C")
                    temp_match = re.search(r"(\+?\d+\.\d+)", line)
                    if temp_match:
                        cpu_temp = temp_match.group(1).replace("+", "")
                        break
        
        # Fallback to sysfs if sensors failed or didn't find temp
        if cpu_temp == "N/A":
            success_t, t_res = RemoteExecutor.run_command(hostname, "cat /sys/class/thermal/thermal_zone*/temp")
            if success_t and t_res:
                first_temp = t_res.splitlines()[0].strip()
                if first_temp.isdigit():
                    cpu_temp = str(round(int(first_temp) / 1000.0, 2))

        return {
            "gpu_usage": [float(x) for x in utils],
            "gpu_temp": [float(x) for x in temps],
            "mem_usage": mem_list,
            "cpu_usage": [float(cpu_util)] if cpu_util != "N/A" else ["N/A"],
            "cpu_temp": [float(cpu_temp)] if cpu_temp != "N/A" else ["N/A"]
        }

    except Exception as e:
        return f"Error retrieving spark metrics: {e}"

def cm_mac_smi(hostname: str):
    """
    Returns a string mimicking:
    utilization.gpu, temperature.gpu, memory.used, memory.total
    """
    try:
        # Determine if the host is local
        import socket
        local_hostname = socket.gethostname()
        is_local = hostname.lower() in ["localhost", "127.0.0.1", local_hostname.lower()]

        if is_local:
            try:
                # 1. Get GPU and Thermal data (requires sudo)
                cmd = ["sudo", "-n", "powermetrics", "--samplers", "gpu_power,thermal", "-n", "1", "-i", "500"]
                res = subprocess.check_output(cmd).decode('utf-8')
                
                # Memory info is also local
                mem_total_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
                mem_total_mib = mem_total_bytes // (1024**2)
                vm_stat = subprocess.check_output(["vm_stat"]).decode('utf-8')
                pages_active = int(re.search(r"Pages active:\s+(\d+)", vm_stat).group(1))
                mem_used_mib = (pages_active * 4096) // (1024**2)
            except subprocess.CalledProcessError as e:
                if e.returncode == 64:
                    return "Error: powermetrics failed (exit 64). This usually means sudo requires a password. Please add 'youruser ALL=(ALL) NOPASSWD: /usr/bin/powermetrics' to /etc/sudoers."
                return f"Error retrieving metrics: {e}"
        else:
            # Remote execution via SSH
            # We combine the commands into one SSH call to be efficient
            remote_cmd = (
                "sudo -n powermetrics --samplers gpu_power,thermal -n 1 -i 500 && "
                "sysctl -n hw.memsize && "
                "vm_stat"
            )
            success, res = RemoteExecutor.run_command(hostname, remote_cmd)
            if not success:
                return f"Error retrieving metrics from {hostname}: {res}"
            
            # Split the combined output
            # powermetrics output is large, sysctl is one line, vm_stat is several
            parts = res.split("\n\n") # This is a bit fragile, but powermetrics usually ends with a block
            # Better: split by the known markers
            # Since we know the order: powermetrics, then memsize, then vm_stat
            # Let's find the last two lines/blocks
            lines = res.splitlines()
            # The last line of vm_stat is usually the end.
            # The line before vm_stat starts is the memsize.
            # Let's find the memsize line (it's just a number)
            mem_total_mib = 0
            mem_used_mib = 0
            
            # Find the line that is just a large number (memsize)
            for i in range(len(lines)-1, -1, -1):
                line = lines[i].strip()
                if line.isdigit() and int(line) > 10**9:
                    mem_total_mib = int(line) // (1024**2)
                    # The lines after this are vm_stat
                    vm_stat_text = "\n".join(lines[i+1:])
                    pages_match = re.search(r"Pages active:\s+(\d+)", vm_stat_text)
                    if pages_match:
                        pages_active = int(pages_match.group(1))
                        mem_used_mib = (pages_active * 4096) // (1024**2)
                    break
            
            # The rest is powermetrics
            # We can just use the whole 'res' for the regexes as they are specific
        
        # Parse Utilization (GPU HW active residency)
        util_match = re.search(r"GPU HW active residency:\s+(\d+\.\d+)%", res)
        util = util_match.group(1) if util_match else "0.0"

        # Parse Temperature (GPU die temperature) - very flexible regex
        temp_match = re.search(r"GPU.*?(?:temperature|temp).*?(\d+\.\d+)", res, re.IGNORECASE)
        temp = temp_match.group(1) if temp_match else "N/A"

        # Parse CPU Usage (Average of all cores)
        cpu_match = re.search(r"CPU average utilization:\s+(\d+\.\d+)%", res)
        cpu_util = cpu_match.group(1) if cpu_match else "0.0"

        # Parse CPU Temperature - very flexible regex for different Mac chips/samplers
        cpu_temp_match = re.search(r"CPU.*?(?:temperature|temp).*?(\d+\.\d+)", res, re.IGNORECASE)
        if not cpu_temp_match:
            # Fallback for thermal sampler which might just say "Temperature: ..." or "Die temperature: ..."
            cpu_temp_match = re.search(r"(?:Temperature|Die temperature).*?(\d+\.\d+)", res, re.IGNORECASE)
        cpu_temp = cpu_temp_match.group(1) if cpu_temp_match else "N/A"

        # Fallback to smctemp if temperatures are still N/A
        if temp == "N/A" or cpu_temp == "N/A":
            if temp == "N/A":
                success_g, res_g = RemoteExecutor.run_command(hostname, "smctemp -g")
                if success_g and res_g:
                    match_g = re.search(r"(\d+\.\d+)", res_g)
                    if match_g:
                        temp = match_g.group(1)
            
            if cpu_temp == "N/A":
                success_c, res_c = RemoteExecutor.run_command(hostname, "smctemp -c")
                if success_c and res_c:
                    match_c = re.search(r"(\d+\.\d+)", res_c)
                    if match_c:
                        cpu_temp = match_c.group(1)

        # Format memory as list of [perc, total]
        try:
            total_gb = round(mem_total_mib / 1024, 1)
            perc = round((mem_used_mib / mem_total_mib) * 100, 1) if mem_total_mib > 0 else 0
            mem_list = [[perc, total_gb]]
        except (TypeError, ZeroDivisionError):
            mem_list = [["N/A", "N/A"]]

        return {
            "gpu_usage": [float(util)],
            "gpu_temp": [float(temp)] if temp != "N/A" else ["N/A"],
            "mem_usage": mem_list,
            "cpu_usage": [float(cpu_util)],
            "cpu_temp": [float(cpu_temp)] if cpu_temp != "N/A" else ["N/A"]
        }

    except Exception as e:
        return f"Error retrieving metrics: {e}"

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
    def run_command(hostname: str, command: str) -> Tuple[bool, str]:
        """Runs a non-interactive command and returns (success, output/error)."""
        # Print the command being issued in black for debugging/transparency
        console.print(f"[black]Executing on {hostname}: {command}[/black]")
        
        import socket
        local_hostname = socket.gethostname()
        is_local = hostname.lower() in ["localhost", "127.0.0.1", local_hostname.lower()]

        if is_local:
            # Run locally without SSH
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
                success = result.returncode == 0
                output = result.stdout.strip() if success else (result.stderr.strip() or f"Command failed with return code {result.returncode}")
            except Exception as e:
                success, output = False, str(e)
        else:
            # Run via SSH
            cmd = ["ssh", hostname, command]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                success = result.returncode == 0
                output = result.stdout.strip() if success else (result.stderr.strip() or f"Command failed with return code {result.returncode}")
            except Exception as e:
                success, output = False, str(e)
        
        # Print the result of the command in black
        console.print(f"[black]Result: {output}[/black]")
        return success, output

    @staticmethod
    def probe_hardware(hostname: str) -> Dict[str, str]:
        """Probes the remote host for GPU and CPU hardware types."""
        results = {"gpu": "unknown", "cpu": "unknown"}
        success, _ = RemoteExecutor.run_command(hostname, "nvidia-smi -L")
        if success:
            results["gpu"] = "nvidia"
        else:
            success_amd, _ = RemoteExecutor.run_command(hostname, "lspci | grep -i vga | grep -i amd")
            success_rocm, _ = RemoteExecutor.run_command(hostname, "rocm-smi")
            if success_amd or success_rocm:
                results["gpu"] = "amd"
            else:
                results["gpu"] = "none"
            
        success_cpu, cpu_info = RemoteExecutor.run_command(hostname, "lscpu")
        if success_cpu:
            cpu_info_lower = cpu_info.lower()
            if "genuineintel" in cpu_info_lower:
                results["cpu"] = "intel"
            elif "authenticamd" in cpu_info_lower:
                results["cpu"] = "amd"
            elif "aarch64" in cpu_info_lower or "arm" in cpu_info_lower:
                results["cpu"] = "arm"
        return results