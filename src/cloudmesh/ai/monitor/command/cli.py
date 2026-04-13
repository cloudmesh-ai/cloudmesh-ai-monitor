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
    def dashboard_cmd():
        """Real-time fleet dashboard."""
        gui = get_gui_framework()
        if gui == "terminalgui":
            app = CloudmeshAIMonitorApp()
            app.run()
        elif gui == "grafana":
            console.print("[yellow]Grafana dashboard is not yet implemented.[/yellow]")
        else:
            console.print(f"[red]Unsupported GUI framework: {gui}[/red]")

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