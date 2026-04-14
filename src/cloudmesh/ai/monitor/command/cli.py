"""
CLI implementation for cloudmesh-ai monitor.
Delegates to the framework specified by CMC_GUI.
"""
import os
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from cloudmesh.ai.monitor.terminalgui.core import HostManager, RemoteExecutor
from cloudmesh.ai.monitor.terminalgui.app import CloudmeshAIMonitorApp
from cloudmesh.ai.monitor.gui.main import start_gui
from cloudmesh.ai.monitor.llm_checker import LLMChecker

console = Console()

def get_gui_framework():
    return os.getenv("CMC_GUI", "terminalgui")

def create_cli():
    """Create and return the click group for the monitor CLI."""
    @click.group()
    def wrapper():
        pass

    @wrapper.group(name="monitor")
    def main():
        """cloudmesh-ai-monitor: Observability for AI infrastructure."""
        pass

    @main.group(name="setup")
    def setup_group():
        """Manage the monitoring host configuration."""
        pass

    @setup_group.command(name="add")
    @click.argument("hostname")
    @click.option("--label", help="Friendly label for the host.")
    def setup_add(hostname, label):
        """Add a new host to the monitoring list."""
        hm = HostManager()
        hm.add_host(hostname, label)
        console.print(f"[green]Added host {hostname} to configuration.[/green]")

    @setup_group.command(name="remove")
    @click.argument("hostname")
    def setup_remove(hostname):
        """Remove a host from the monitoring list."""
        hm = HostManager()
        hm.remove_host(hostname)
        console.print(f"[yellow]Removed host {hostname} from configuration.[/yellow]")

    @setup_group.command(name="activate")
    @click.argument("hostname")
    def setup_activate(hostname):
        """Activate a host for monitoring."""
        hm = HostManager()
        hm.set_active(hostname, True)
        console.print(f"[green]Host {hostname} activated.[/green]")

    @setup_group.command(name="deactivate")
    @click.argument("hostname")
    def setup_deactivate(hostname):
        """Deactivate a host for monitoring."""
        hm = HostManager()
        hm.set_active(hostname, False)
        console.print(f"[yellow]Host {hostname} deactivated.[/yellow]")

    @main.command(name="run")
    @click.argument("identifier")
    @click.argument("tool", type=click.Choice(["top", "nvtop", "nvitop"]))
    def run_tool_cmd(identifier, tool):
        """Run an interactive monitoring tool on a remote host or label."""
        hm = HostManager()
        hostname = hm.resolve_host(identifier)
        if not hostname:
            console.print(f"[bold red]Error: Could not resolve host or label '{identifier}'[/bold red]")
            return
        console.print(f"[blue]Launching {tool} on {hostname}...[/blue]")
        RemoteExecutor.run_interactive(hostname, tool)

    @main.command(name="stats")
    @click.argument("stat_type", type=click.Choice(["gpu", "cpu"]))
    @click.argument("identifiers", nargs=-1, required=True)
    def stats_cmd(stat_type, identifiers):
        """Check GPU or CPU stats across multiple hosts."""
        hm = HostManager()
        executor = RemoteExecutor()
        table = Table(title=f"Fleet {stat_type.upper()} Statistics")
        table.add_column("Host", style="cyan")
        table.add_column("Label", style="magenta")
        if stat_type == "gpu":
            table.add_column("GPU Load/Temp", justify="right")
            cmd = "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu --format=csv,noheader,nounits | head -n 1"
        else:
            table.add_column("CPU Load", justify="right")
            cmd = "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'"

        for ident in identifiers:
            hostname = hm.resolve_host(ident)
            if not hostname: continue
            
            info = hm.get_host_info(hostname)
            if not info.get("active", True):
                continue
                
            label = info.get("label", "N/A")
            output = executor.run_command(hostname, cmd)
            val = output if output else "Error/Unavailable"
            if stat_type == "gpu" and "," in val:
                u, t = val.split(",")
                val = f"{u.strip()}% / {t.strip()}°C"
            table.add_row(hostname, label, val)
        console.print(table)

    @main.command(name="probe")
    @click.argument("hosts", nargs=-1, required=True)
    @click.option("--config", default="~/.config/cloudmesh/ai/hosts.yaml", help="Path to the hosts YAML config file.")
    def probe_cmd(hosts, config):
        """Probe remote hosts to automatically detect GPU and CPU hardware and update config."""
        from pathlib import Path
        from cloudmesh.ai.common.io import load_yaml, dump_yaml
        
        config_path = Path(config).expanduser()
        full_cfg = load_yaml(config_path) or {"cloudmesh": {"ai": {"hosts": {}}}}
        hosts_cfg = full_cfg["cloudmesh"]["ai"].setdefault("hosts", {})
        executor = RemoteExecutor()
        console.print(f"[blue]Probing {len(hosts)} host(s)...[/blue]")
        for host in hosts:
            console.print(f"Probing {host}...", end=" ")
            hw = executor.probe_hardware(host)
            if host not in hosts_cfg:
                hosts_cfg[host] = {"active": True}
            hosts_cfg[host].update(hw)
            console.print(f"[green]Found GPU: {hw['gpu']}, CPU: {hw['cpu']}[/green]")
        dump_yaml(config_path, full_cfg)
        console.print(Panel(f"Updated configuration saved to [bold cyan]{config_path}[/bold cyan]", title="Probe Complete", border_style="green"))

    @main.command(name="dashboard")
    @click.option("-g", "--gui", is_flag=True, help="Launch the Web GUI dashboard.")
    @click.option("-t", "--terminal", is_flag=True, help="Launch the Terminal UI dashboard.")
    @click.option("-p", "--port", type=int, default=8000, help="Port to run the Web GUI on.")
    def dashboard_cmd(gui, terminal, port):
        """Real-time fleet dashboard."""
        if gui:
            console.print(f"[blue]Launching Web GUI on http://localhost:{port}...[/blue]")
            start_gui(port=port)
        elif terminal or not (gui or terminal):
            # Default to TUI if -t is passed or no flag is provided
            app = CloudmeshAIMonitorApp()
            app.run()
        else:
            # This case is technically covered by the logic above, but for clarity:
            app = CloudmeshAIMonitorApp()
            app.run()

    @main.command(name="check-exporter")
    @click.option("--url", default="http://localhost:9100/metrics", help="URL of the GPU exporter metrics endpoint.")
    def check_exporter_cmd(url):
        """Verify that the Prometheus GPU exporter is running and healthy."""
        import requests
        console.print(f"[blue]Checking GPU Exporter at {url}...[/blue]")
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and "nvidia_gpu" in response.text:
                console.print(Panel("[bold green]GPU Exporter is healthy![/bold green]", border_style="green"))
            else:
                console.print(Panel(f"[bold red]Exporter unhealthy. Status: {response.status_code}[/bold red]", border_style="red"))
        except Exception as e:
            console.print(Panel(f"[bold red]Could not connect: {e}[/bold red]", border_style="red"))

    @main.command(name="oom-check")
    def oom_check_cmd():
        """Scan system logs for Out-of-Memory (OOM) events."""
        import subprocess
        from pathlib import Path
        console.print("[blue]Scanning for OOM events...[/blue]")
        oom_events = []
        try:
            dmesg_out = subprocess.check_output(["dmesg"], text=True, stderr=subprocess.DEVNULL)
            for line in dmesg_out.splitlines():
                if "out of memory" in line.lower() or "oom-killer" in line.lower():
                    oom_events.append(f"[dmesg] {line.strip()}")
        except Exception:
            pass
        
        if not oom_events:
            console.print(Panel("[bold green]No OOM events detected.[/bold green]", border_style="green"))
        else:
            console.print(Panel(f"[bold red]Detected {len(oom_events)} OOM event(s)![/bold red]", border_style="red"))
            table = Table(title="OOM Event Log")
            table.add_column("Event", style="red")
            for event in oom_events[-10:]:
                table.add_row(event)
            console.print(table)

    @main.command(name="grafana-snapshot")
    @click.option("--dashboard-id", required=True, help="The ID of the Grafana dashboard.")
    @click.option("--url", default="http://grafana.local", help="Base URL of the Grafana instance.")
    def grafana_snapshot_cmd(dashboard_id, url):
        """Generate a link to a Grafana snapshot for the current state."""
        snapshot_url = f"{url}/d/{dashboard_id}?orgId=1&from=now-1h&to=now"
        console.print(Panel(f"Grafana Dashboard Link:\n[bold cyan]{snapshot_url}[/bold cyan]", title="Grafana Integration", border_style="blue"))

    @main.group(name="health")
    def health_group():
        """Check the health status of various system components."""
        pass

    @click.group(name="status")
    def status_group():
        """Get the current status of a specific component."""
        pass
    
    health_group.add_command(status_group)

    @status_group.command(name="disk")
    @click.argument("identifier")
    @click.option("--password", help="Sudo password for smartctl.")
    @click.option("--usage", is_flag=True, help="Include columns for total and used disk capacity.")
    def disk_health_cmd(identifier, password, usage):
        """Check disk health status and optional usage using smartctl scan."""
        hm = HostManager()
        hostname = hm.resolve_host(identifier)
        if not hostname:
            console.print(f"[bold red]Error: Could not resolve host '{identifier}'[/bold red]")
            return

        if not password:
            password = click.prompt(f"Sudo password for {hostname}", hide_input=True)
            if not password: password = None

        executor = RemoteExecutor()
        console.print(f"[blue]Scanning disks on {hostname}...[/blue]")

        # 1. Get device list using lsblk (more reliable than smartctl --scan)
        lsblk_cmd = "lsblk -dn -o NAME"
        success, disks_out = executor.run_command(hostname, lsblk_cmd)
        
        if not success or not disks_out:
            console.print("[bold red]Error: Could not retrieve disk list from lsblk.[/bold red]")
            return

        disks = [d.strip() for d in disks_out.split('\n') if d.strip() and not d.strip().startswith('loop')]

        table = Table(title=f"Disk Health Status: {hostname}")
        table.add_column("Device", style="cyan")
        table.add_column("Type", style="magenta")
        
        if usage:
            table.add_column("Total Size", justify="right")
            table.add_column("Used", justify="right")
            
        table.add_column("Health", justify="center")

        for disk_name in disks:
            dev_path = f"/dev/{disk_name}"
            
            # Determine likely type for smartctl
            dev_type = "nvme" if "nvme" in disk_name else "ata"
            dev_flag = f"-d {dev_type}"
            
            # 2. Run detailed check
            # We use -a to get attributes (needed for usage) and health status
            cmd_args = f"-a {dev_path} {dev_flag}"
            smart_cmd = f"sudo -S smartctl {cmd_args}" if password else f"sudo -n smartctl {cmd_args}"
            _, smart_out = executor.run_command(hostname, smart_cmd, input_data=password)
            
            smart_out = smart_out or ""
            out_lower = smart_out.lower()

            # Parse Health
            health_status = "Unknown"
            warnings = []

            # 1. Overall Health Check
            if "passed" in out_lower or "ok" in out_lower:
                health_status = "PASSED"
            elif "failed" in out_lower:
                health_status = "FAILED"

            # 2. Sophisticated Attribute Analysis
            if dev_type == "ata":
                # Critical SATA attributes to monitor
                critical_attrs = {
                    "5": "Reallocated_Sector_Ct",
                    "197": "Current_Pending_Sector",
                    "198": "Offline_Uncorrectable",
                }
                for line in smart_out.splitlines():
                    parts = line.split()
                    if len(parts) > 0 and parts[0].isdigit():
                        attr_id = parts[0]
                        if attr_id in critical_attrs:
                            raw_val = parts[-1]
                            # Remove any (Average X) suffix
                            raw_val = raw_val.split(' ')[0]
                            if raw_val != "0":
                                warnings.append(f"{critical_attrs[attr_id]}:{raw_val}")
            elif dev_type == "nvme":
                # Critical NVMe attributes
                if "Critical Warning:" in smart_out:
                    # Extract value after colon
                    val = smart_out.split("Critical Warning:")[1].split('\n')[0].strip()
                    if val != "0x00":
                        warnings.append(f"CritWarn:{val}")
                if "Media and Data Integrity Errors:" in smart_out:
                    val = smart_out.split("Media and Data Integrity Errors:")[1].split('\n')[0].strip()
                    if val != "0":
                        warnings.append(f"IntegrityErr:{val}")

            # 3. Final Health Determination
            if health_status == "FAILED":
                health = "[red]FAILED[/red]"
            elif warnings:
                warn_str = ", ".join(warnings)
                health = f"[yellow]WARNING ({warn_str})[/yellow]"
            elif health_status == "PASSED":
                health = "[green]PASSED[/green]"
            else:
                health = "[yellow]Unknown[/yellow]"
                
                # Fallback: If it's an 'sd' device and health is unknown, probe partitions (next level)
                if dev_path.startswith('/dev/sd'):
                    part_cmd = f"lsblk {dev_path} -n -o NAME | grep -v '^{dev_path.split('/')[-1]}$'"
                    p_success, p_out = executor.run_command(hostname, part_cmd)
                    if p_success and p_out:
                        partitions = [p.strip() for p in p_out.split('\n') if p.strip()]
                        for p_name in partitions:
                            p_path = f"/dev/{p_name}"
                            p_smart_cmd = f"sudo -S smartctl -H {p_path} {dev_flag} {dev_type}" if password else f"sudo -n smartctl -H {p_path} {dev_flag} {dev_type}"
                            _, p_smart_out = executor.run_command(hostname, p_smart_cmd, input_data=password)
                            p_out_lower = (p_smart_out or "").lower()
                            if "passed" in p_out_lower or "ok" in p_out_lower:
                                health = "[green]PASSED[/green]"
                                break
                            elif "failed" in p_out_lower:
                                health = "[red]FAILED[/red]"
                                break

            # Parse Usage (Optional)
            row_data = [dev_path, dev_type]
            if usage:
                total_size = "N/A"
                used_size = "N/A"
                
                for s_line in smart_out.splitlines():
                    # Logic for NVMe
                    if "Total NVM Capacity" in s_line:
                        total_size = s_line.split('[')[-1].split(']')[0] if '[' in s_line else s_line.split(':')[-1].strip()
                    if "Data Units Written" in s_line:
                        used_size = s_line.split('[')[-1].split(']')[0] if '[' in s_line else s_line.split(':')[-1].strip()
                    
                    # Logic for SATA/SCSI
                    if "User Capacity" in s_line:
                        total_size = s_line.split('[')[-1].split(']')[0] if '[' in s_line else s_line.split(':')[-1].strip()

                row_data.extend([total_size, used_size])
            
            row_data.append(health)
            table.add_row(*row_data)

        console.print(table)

    @main.command(name="llm-check")
    @click.option("--host", default="dgx", help="Target host.")
    @click.option("--port", default=8001, help="Target port.")
    @click.option("--key-path", default="~/gemma/server_master_key.txt", help="Path to API key file.")
    @click.option("--json", is_flag=True, help="Output results in JSON format.")
    def llm_check_cmd(host, port, key_path, json):
        """Check LLM connectivity, health, and performance metrics."""
        checker = LLMChecker(host, port, key_path)
        
        proc_ok, details = checker.check_process()
        if not proc_ok:
            checker.print_summary()
            return
        
        checker.check_gpu_status()
        checker.check_tunnel()
        
        server_ok, model_id = checker.probe_server()
        if server_ok:
            checker.probe_chat(model_id)
            checker.fetch_diagnostics()
            checker.log("LLM Server is UP and responding.", "OK")
        else:
            checker.log("LLM Server is DOWN or unreachable.", "FAIL")
    
        if json:
            print(checker.to_json())
        else:
            checker.print_summary()

    return wrapper

entry_point = create_cli