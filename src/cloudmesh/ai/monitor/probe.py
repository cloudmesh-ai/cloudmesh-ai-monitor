"""
Probing logic for cloudmesh-ai monitoring.
"""
import subprocess
import re
import socket
from typing import Tuple, Optional, List, Dict, Any
from rich.console import Console
from cloudmesh.ai.common.logging import get_logger

# Logging configuration
logger = get_logger("cloudmesh.ai.monitor.probe")
console = Console()

class RemoteExecutor:
    """Handles execution of commands on remote hosts via SSH."""
    @staticmethod
    def run_interactive(hostname: str, tool: str):
        """Runs an interactive tool (top, nvtop, etc.) on a remote host."""
        cmd = ["ssh", "-t", hostname, tool]
        try:
            subprocess.run(cmd)
        except Exception as e:
            logger.error(f"Error launching {tool} on {hostname}: {e}")
            console.print(f"[bold red]Error launching {tool} on {hostname}:[/bold red] {e}")

    @staticmethod
    def run_command(hostname: str, command: str, input_data: Optional[str] = None) -> Tuple[bool, str]:
        """Runs a non-interactive command and returns (success, output/error)."""
        # Print the command being issued in black for debugging/transparency
        console.print(f"[black]Executing on {hostname}: {command}[/black]")
        logger.debug(f"Executing on {hostname}: {command}")
        
        local_hostname = socket.gethostname()
        is_local = hostname.lower() in ["localhost", "127.0.0.1", local_hostname.lower()]

        if is_local:
            # Run locally without SSH
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10, input=input_data)
                success = result.returncode == 0
                output = result.stdout.strip() if success else (result.stderr.strip() or f"Command failed with return code {result.returncode}")
            except Exception as e:
                success, output = False, str(e)
        else:
            # Run via SSH
            cmd = ["ssh", hostname, command]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, input=input_data)
                success = result.returncode == 0
                output = result.stdout.strip() if success else (result.stderr.strip() or f"Command failed with return code {result.returncode}")
            except Exception as e:
                success, output = False, str(e)
        
        # Print the result of the command in black
        console.print(f"[black]Result: {output}[/black]")
        if not success:
            logger.warning(f"Command failed on {hostname}: {command}. Result: {output}")
        else:
            logger.debug(f"Command succeeded on {hostname}: {command}")
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

def cm_dgx_smi(hostname: str, devices: Optional[str] = None):
    """
    Returns a string mimicking:
    utilization.gpu, temperature.gpu, memory.used, memory.total, cpu_util, cpu_temp
    Designed for NVIDIA DGX nodes.
    Supports multiple GPUs via the 'devices' parameter (e.g., "0,1,2,4").
    Uses nvidia-smi for GPU and standard Linux tools for CPU/RAM.
    """
    try:
        # 1. GPU Metrics via nvidia-smi
        gpu_cmd = "nvidia-smi --query-gpu=index,utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        success_gpu, gpu_res = RemoteExecutor.run_command(hostname, gpu_cmd)
        if not success_gpu or not gpu_res:
            err = f"Error: nvidia-smi failed on {hostname}"
            logger.error(err)
            return err
        
        requested_devices = [d.strip() for d in devices.split(",")] if devices else None
        
        utils, temps, percs, totals = [], [], [], []
        
        for line in gpu_res.splitlines():
            parts = [x.strip() for x in line.split(',')]
            if len(parts) >= 5:
                idx, util, temp, used, total = parts[:5]
                if requested_devices is None or idx in requested_devices:
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
            err = f"Error: No matching GPUs found on {hostname}" if devices is None else f"Error: No matching GPUs found for devices {devices} on {hostname}"
            logger.error(err)
            return err
            
        mem_list = []
        for p, t in zip(percs, totals):
            if p != "N/A" and t is not None:
                try:
                    p_val = float(p.split('/')[0])
                    mem_list.append([p_val, t])
                except (ValueError, IndexError):
                    mem_list.append(["N/A", "N/A"])
            else:
                mem_list.append(["N/A", "N/A"])

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

        cpu_temp = "N/A"
        success_s, s_res = RemoteExecutor.run_command(hostname, "sensors")
        if success_s and s_res:
            for line in s_res.splitlines():
                if any(label in line for label in ["Package id 0", "Core 0", "CPU Temp", "Composite"]):
                    temp_match = re.search(r"(\+?\d+\.\d+)", line)
                    if temp_match:
                        cpu_temp = temp_match.group(1).replace("+", "")
                        break
            if cpu_temp == "N/A":
                temp_match = re.search(r"(\+?\d+\.\d+)\s*°C", s_res)
                if temp_match:
                    cpu_temp = temp_match.group(1).replace("+", "")
        
        if cpu_temp == "N/A":
            success_hw, hw_res = RemoteExecutor.run_command(hostname, "find /sys/class/hwmon/hwmon* -name '*temp*input*' -exec cat {} + 2>/dev/null")
            if success_hw and hw_res:
                hw_temps = []
                for line in hw_res.splitlines():
                    val = line.strip()
                    if val.isdigit():
                        hw_temps.append(int(val))
                if hw_temps:
                    cpu_temp = str(round(max(hw_temps) / 1000.0, 2))

        if cpu_temp == "N/A":
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
        err = f"Error retrieving DGX metrics: {e}"
        logger.exception(err)
        return err

def cm_spark_smi(hostname: str):
    """
    Returns a string mimicking:
    utilization.gpu, temperature.gpu, memory.used, memory.total, cpu_util, cpu_temp
    Designed for NVIDIA Spark/GPU nodes.
    Uses nvidia-smi for GPU and standard Linux tools for CPU/RAM.
    """
    try:
        gpu_cmd = "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
        success_gpu, gpu_res = RemoteExecutor.run_command(hostname, gpu_cmd)
        if not success_gpu or not gpu_res:
            err = f"Error: nvidia-smi failed on {hostname}"
            logger.error(err)
            return err
        
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
            err = f"Error: nvidia-smi failed on {hostname}"
            logger.error(err)
            return err

        mem_list = []
        has_valid_gpu_mem = any(t is not None for t in totals)
        
        if not has_valid_gpu_mem:
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

        cpu_temp = "N/A"
        success_s, s_res = RemoteExecutor.run_command(hostname, "sensors")
        if success_s and s_res:
            for line in s_res.splitlines():
                if "Package id 0" in line or "Core 0" in line:
                    temp_match = re.search(r"(\+?\d+\.\d+)", line)
                    if temp_match:
                        cpu_temp = temp_match.group(1).replace("+", "")
                        break
        
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
        err = f"Error retrieving spark metrics: {e}"
        logger.exception(err)
        return err

def cm_mac_smi(hostname: str):
    """
    Returns a string mimicking:
    utilization.gpu, temperature.gpu, memory.used, memory.total
    """
    try:
        local_hostname = socket.gethostname()
        is_local = hostname.lower() in ["localhost", "127.0.0.1", local_hostname.lower()]

        if is_local:
            try:
                cmd = ["sudo", "-n", "powermetrics", "--samplers", "gpu_power,thermal", "-n", "1", "-i", "500"]
                res_obj = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                res = res_obj.stdout
                
                mem_res = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
                mem_total_bytes = int(mem_res.stdout.strip())
                mem_total_mib = mem_total_bytes // (1024**2)
                
                vm_res = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
                vm_stat = vm_res.stdout
                pages_active = int(re.search(r"Pages active:\s+(\d+)", vm_stat).group(1))
                mem_used_mib = (pages_active * 4096) // (1024**2)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                if getattr(e, 'returncode', None) == 64:
                    return "Error: powermetrics failed (exit 64). This usually means sudo requires a password. Please add 'youruser ALL=(ALL) NOPASSWD: /usr/bin/powermetrics' to /etc/sudoers."
                return f"Error retrieving metrics: {e}"
        else:
            remote_cmd = (
                "sudo -n powermetrics --samplers gpu_power,thermal -n 1 -i 500 && "
                "sysctl -n hw.memsize && "
                "vm_stat"
            )
            success, res = RemoteExecutor.run_command(hostname, remote_cmd)
            if not success:
                return f"Error retrieving metrics from {hostname}: {res}"
            
            lines = res.splitlines()
            mem_total_mib = 0
            mem_used_mib = 0
            
            for i in range(len(lines)-1, -1, -1):
                line = lines[i].strip()
                if line.isdigit() and int(line) > 10**9:
                    mem_total_mib = int(line) // (1024**2)
                    vm_stat_text = "\n".join(lines[i+1:])
                    pages_match = re.search(r"Pages active:\s+(\d+)", vm_stat_text)
                    if pages_match:
                        pages_active = int(pages_match.group(1))
                        mem_used_mib = (pages_active * 4096) // (1024**2)
                    break
        
        util_match = re.search(r"GPU HW active residency:\s+(\d+\.\d+)%", res)
        util = util_match.group(1) if util_match else "0.0"

        temp_match = re.search(r"GPU.*?(?:temperature|temp).*?(\d+\.\d+)", res, re.IGNORECASE)
        temp = temp_match.group(1) if temp_match else "N/A"

        cpu_match = re.search(r"CPU average utilization:\s+(\d+\.\d+)%", res)
        cpu_util = cpu_match.group(1) if cpu_match else "0.0"

        cpu_temp_match = re.search(r"CPU.*?(?:temperature|temp).*?(\d+\.\d+)", res, re.IGNORECASE)
        if not cpu_temp_match:
            cpu_temp_match = re.search(r"(?:Temperature|Die temperature).*?(\d+\.\d+)", res, re.IGNORECASE)
        cpu_temp = cpu_temp_match.group(1) if cpu_temp_match else "N/A"

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
        err = f"Error retrieving metrics: {e}"
        logger.exception(err)
        return err