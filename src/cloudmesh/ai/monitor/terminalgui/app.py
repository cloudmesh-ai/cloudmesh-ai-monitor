"""
Textual-based TUI for cloudmesh-ai monitoring.
"""

import time
import logging
import sys
from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    DataTable,
    Static,
    Input,
    Button,
    Label,
    Checkbox,
)
from textual.containers import Horizontal, Vertical, Center, Middle
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual.events import Key

# Ensure these are available in your PYTHONPATH
from cloudmesh.ai.monitor.terminalgui.core import HostManager, RemoteExecutor, cm_mac_smi, cm_spark_smi, cm_dgx_smi


class DetailScreen(ModalScreen):
    """A modal screen that displays row details."""
    def __init__(self, row_data: list):
        super().__init__()
        self.row_data = row_data

    def compose(self) -> ComposeResult:
        # Use the original columns from the dashboard
        cols = ["Hostname", "Label", "Active", "Interval", "GPU Usage", "GPU Temp", "Memory Usage (GB)", "CPU Usage", "CPU Temp"]
        details = ""
        for col, val in zip(cols, self.row_data):
            details += f"[bold cyan]{col}:[/]   {val}\n"
        
        with Middle():
            with Center():
                yield Static(details, id="detail_panel")
                yield Static("Press any key to close", id="hint")

    def on_key(self, event: Key) -> None:
        self.app.pop_screen()

class ProbeResultScreen(ModalScreen):
    """A modal screen that displays the raw output of a probe command."""
    def __init__(self, output: str):
        super().__init__()
        self.output = output

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Vertical(
                    Static("🔍 Probe Result", id="form_title"),
                    Static(self.output, id="detail_panel"),
                    Horizontal(
                        Button("Close", variant="error", id="close_btn"),
                        id="form_buttons",
                    ),
                    id="form_container",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close_btn":
            self.app.pop_screen()

class DashboardScreen(Screen):
    """Screen for the real-time fleet dashboard."""

    def _clean_probe_output(self, output: str) -> str:
        """Removes SSH warnings and noise from the probe output."""
        if not output:
            return ""
        lines = output.splitlines()
        cleaned = [
            line for line in lines 
            if not line.strip().startswith("**") 
            and "WARNING" not in line.upper() 
            and "vulnerable to" not in line.lower()
        ]
        return "\n".join(cleaned).strip()

    def _get_full_probe_cmd(self, probe_cmd: str) -> str:
        """Ensures the probe command starts with nvidia-smi."""
        if not probe_cmd:
            return "nvidia-smi"
        probe_cmd = probe_cmd.strip()
        if probe_cmd.startswith("nvidia-smi"):
            return probe_cmd
        return f"nvidia-smi {probe_cmd}"

    def _format_metric(self, value: str) -> str:
        """Returns an empty string if the value is 'N/A', otherwise returns the value."""
        if not value or "N/A" in value:
            return ""
        return value

    BINDINGS = [
        Binding("a", "add_host", "Add Host"),
        Binding("e", "edit_host", "Edit Host"),
        Binding("u", "move_up", "Move Up"),
        Binding("d", "move_down", "Move Down"),
        Binding("r", "refresh_host", "Refresh Host"),
        Binding("R", "refresh_all", "Refresh All"),
        Binding("q", "quit", "Quit"),
        Binding("t", "toggle_active", "Toggle Active"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("🚀 Cloudmesh AI Monitor Dashboard", id="title"),
            DataTable(id="metrics_table"),
            id="dashboard_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.last_updated = {}
        table = self.query_one(DataTable)
        
        # KEY: Enable cell-level navigation for specific column interactions
        table.cursor_type = "cell"
        
        table.add_columns(
            "Label",
            "Hostname",
            "Active",
            "Interval",
            "GPU Usage",
            "GPU Temp",
            "Memory Usage (GB)",
            "CPU Usage",
            "CPU Temp",
        )
        self.update_metrics()
        self.set_interval(1, self.tick)

    def tick(self) -> None:
        """Periodic check to see if any host needs a metric refresh."""
        hm = HostManager()
        now = time.time()
        needs_refresh = False

        for host, info in hm.hosts_data.items():
            interval = info.get("refresh_interval", 10)
            last = self.last_updated.get(host, 0)
            if now - last >= interval:
                needs_refresh = True
                break

        if needs_refresh:
            self.update_metrics()

    def update_metrics(self) -> None:
        """Updates the table metrics. Clears and rebuilds to ensure consistency after edits."""
        hm = HostManager()
        table = self.query_one(DataTable)
        
        now = time.time()
        
        # Preserve cursor position
        selected_label = None
        coord = table.cursor_coordinate
        if coord:
            try:
                # Use row index from coordinate to get the row key
                row_idx = coord[0]
                row_keys = list(table.rows.keys())
                if 0 <= row_idx < len(row_keys):
                    row_key = row_keys[row_idx]
                    selected_label = table.get_row(row_key)[0]
            except Exception:
                pass

        # Clear table to ensure deleted/renamed hosts are removed
        table.clear()

        for label, info in hm.get_hosts_ordered():
            hostname = info.get("hostname", "N/A")
            active = info.get("active", True)
            interval = info.get("refresh_interval", 10)
            
            if active and (now - self.last_updated.get(label, 0) >= interval):
                self.last_updated[label] = now
                self.run_worker(lambda l=label: self.refresh_host_metrics(l), thread=True)

            gpu_usage = info.get("gpu_usage", "N/A")
            gpu_temp = info.get("gpu_temp", "N/A")
            mem_usage = info.get("mem_usage", "N/A")
            cpu_usage = info.get("cpu_usage", "N/A")
            cpu_temp = info.get("cpu_temp", "N/A")
            active_status = "True" if active else "False"

            # Color the interval based on last probe success
            last_success = info.get("last_probe_success")
            if last_success is True:
                interval_str = f"[green]{interval}s[/]"
            elif last_success is False:
                interval_str = f"[red]{interval}s[/]"
            else:
                interval_str = f"{interval}s"

            table.add_row(
                label, 
                hostname, 
                active_status, 
                interval_str, 
                self._format_metric(gpu_usage), 
                self._format_metric(gpu_temp), 
                self._format_metric(mem_usage), 
                self._format_metric(cpu_usage), 
                self._format_metric(cpu_temp)
            )

        # Restore cursor position
        if selected_label:
            for idx, row_key in enumerate(table.rows):
                if table.get_row(row_key)[0] == selected_label:
                    # Move cursor to the first cell of the matching row
                    # Using a tuple (row, col) for maximum compatibility
                    table.cursor_coordinate = (idx, 0)
                    break

    def refresh_host_metrics(self, label: str) -> None:
        """Worker to fetch GPU data without blocking the UI."""
        hm = HostManager()
        info = hm.get_host_info(label)
        if not info:
            return
            
        hostname = info.get("hostname")
        if not hostname:
            return

        # Use custom probe command if available, otherwise use default
        probe_cmd_raw = info.get("probe_cmd", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits")
        probe_cmd = probe_cmd_raw.strip()
        
        if probe_cmd.startswith("cm-mac-smi"):
            parts = probe_cmd.split()
            target_host = parts[1] if len(parts) > 1 else hostname
            gpu_data = cm_mac_smi(target_host)
            success = not gpu_data.startswith("Error")
        elif probe_cmd.startswith("cm-spark-smi"):
            parts = probe_cmd.split()
            target_host = parts[1] if len(parts) > 1 else hostname
            gpu_data = cm_spark_smi(target_host)
            success = not gpu_data.startswith("Error")
        elif probe_cmd.startswith("cm-dgx-smi"):
            parts = probe_cmd.split()
            # Format: cm-dgx-smi [target_host] [devices]
            if len(parts) > 2:
                target_host = parts[1]
                devices = parts[2]
            elif len(parts) == 2:
                # Could be 'cm-dgx-smi target_host' or 'cm-dgx-smi devices'
                # If the second part contains a comma, it's likely devices
                if "," in parts[1]:
                    target_host = hostname
                    devices = parts[1]
                else:
                    target_host = parts[1]
                    devices = "0"
            else:
                target_host = hostname
                devices = "0"
            
            gpu_data = cm_dgx_smi(target_host, devices)
            success = not gpu_data.startswith("Error")
        else:
            executor = RemoteExecutor()
            full_cmd = self._get_full_probe_cmd(probe_cmd)
            success, gpu_data = executor.run_command(
                hostname,
                full_cmd,
            )
            gpu_data = self._clean_probe_output(gpu_data)
        
        if success and gpu_data:
            lines = gpu_data.splitlines()
            utils, temps, mems, cpu_utils, cpu_temps = [], [], [], [], []
            # Check if this is a special cm- probe that already provides formatted memory
            is_special_probe = any(probe_cmd.startswith(prefix) for prefix in ["cm-mac-smi", "cm-spark-smi", "cm-dgx-smi"])

            for line in lines:
                parts = line.split(",")
                if len(parts) >= 4:
                    p = [x.strip() for x in parts]
                    utils.append(f"{p[0]}%")
                    temps.append(f"{p[1]}°C")
                    
                    if is_special_probe:
                        # Special probes already return formatted memory in p[2] (e.g., "0.7%/24GB")
                        mems.append(p[2])
                    else:
                        try:
                            used_gb = float(p[2]) / 1024
                            total_gb = float(p[3]) / 1024
                            mems.append(f"{used_gb:.2f}/{total_gb:.2f}")
                        except (ValueError, IndexError):
                            mems.append(f"{p[2]}/{p[3]}")
                    
                    if len(parts) >= 6:
                        cpu_utils.append(f"{p[4]}%")
                        cpu_temps.append(f"{p[5]}°C")
 
            gpu_usage = " ".join(utils) or "N/A"
            gpu_temp = " ".join(temps) or "N/A"
            mem_usage = " ".join(mems) or "N/A"
            cpu_usage = " ".join(cpu_utils) or "N/A"
            cpu_temp = " ".join(cpu_temps) or "N/A"
        else:
            gpu_usage, gpu_temp, mem_usage, cpu_usage, cpu_temp = "N/A", "N/A", "N/A", "N/A", "N/A"
 
        # For non-Mac/non-Spark/non-DGX hosts, we need to fetch CPU metrics separately as nvidia-smi doesn't provide them
        if not probe_cmd.startswith("cm-mac-smi") and not probe_cmd.startswith("cm-spark-smi") and not probe_cmd.startswith("cm-dgx-smi") and success:
            executor = RemoteExecutor()
            # CPU Usage: 100% - idle
            cpu_usage_cmd = "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1\"%\"}'"
            # CPU Temp: try sensors, then fallback to sysfs
            cpu_temp_cmd = "sensors | grep 'Package id 0' | awk '{print $4}' || cat /sys/class/thermal/thermal_zone0/temp | awk '{print $1/1000\"°C\"}'"
            
            cpu_u_success, cpu_u_val = executor.run_command(hostname, cpu_usage_cmd)
            cpu_t_success, cpu_t_val = executor.run_command(hostname, cpu_temp_cmd)
            
            if cpu_u_success: cpu_usage = cpu_u_val
            if cpu_t_success: cpu_temp = cpu_t_val

        hm = HostManager()
        hm.update_metrics(label, gpu_usage, gpu_temp, mem_usage, cpu_usage=cpu_usage, cpu_temp=cpu_temp, last_probe_success=success)
        self.app.call_from_thread(self.update_metrics)

    def action_toggle_active(self) -> None:
        """Toggles active status for the current row, regardless of focused cell."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        
        if coord:
            try:
                # Use row index from coordinate to get the row key
                row_idx = coord[0]
                row_keys = list(table.rows.keys())
                if 0 <= row_idx < len(row_keys):
                    row_key = row_keys[row_idx]
                    label = table.get_row(row_key)[0]
                
                # Use HostManager as the source of truth for the current state
                hm = HostManager()
                info = hm.get_host_info(label)
                current_active = info.get("active", True) if info else True
                new_active = not current_active
                
                # Update backend
                hm.set_active(label, new_active)
                
                # Update the "Active" cell (column index 2)
                cols = list(table.columns.values()) if isinstance(table.columns, dict) else table.columns
                active_col_key = cols[2].key
                new_val = "True" if new_active else "False"
                table.update_cell(row_key, active_col_key, new_val)
            except Exception:
                pass

    def action_edit_host(self) -> None:
        """Pops up edit screen for the current row, regardless of cell focused."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        if coord:
            try:
                # Use row index from coordinate to get the row key
                row_idx = coord[0]
                row_keys = list(table.rows.keys())
                if 0 <= row_idx < len(row_keys):
                    row_key = row_keys[row_idx]
                    label = table.get_row(row_key)[0]
                    self.app.push_screen(AddHostScreen(host_to_edit=label))
            except Exception:
                pass

    def action_move_up(self) -> None:
        """Moves the selected host up in the list."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        if coord:
            # Use row index from coordinate to get the row key
            row_idx = coord[0]
            row_keys = list(table.rows.keys())
            if 0 <= row_idx < len(row_keys):
                row_key = row_keys[row_idx]
                label = table.get_row(row_key)[0]
                self.notify(f"Moving {label} up")
                hm = HostManager()
                hm.move_host(label, "up")
                self.update_metrics()

    def action_move_down(self) -> None:
        """Moves the selected host down in the list."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        if coord:
            # Use row index from coordinate to get the row key
            row_idx = coord[0]
            row_keys = list(table.rows.keys())
            if 0 <= row_idx < len(row_keys):
                row_key = row_keys[row_idx]
                label = table.get_row(row_key)[0]
                self.notify(f"Moving {label} down")
                hm = HostManager()
                hm.move_host(label, "down")
                self.update_metrics()

    def action_refresh_host(self) -> None:
        """Refreshes metrics for the selected host."""
        table = self.query_one(DataTable)
        coord = table.cursor_coordinate
        if coord:
            try:
                # Use row index from coordinate to get the row key
                row_idx = coord[0]
                row_keys = list(table.rows.keys())
                if 0 <= row_idx < len(row_keys):
                    row_key = row_keys[row_idx]
                    label = table.get_row(row_key)[0]
                    self.refresh_host_metrics(label)
            except Exception:
                pass

    def action_refresh_all(self) -> None:
        """Refreshes metrics for all active hosts."""
        hm = HostManager()
        for host, info in hm.hosts_data.items():
            if info.get("active", True):
                self.refresh_host_metrics(host)
        self.update_metrics()

    def action_add_host(self) -> None:
        self.app.push_screen(AddHostScreen())

    def action_quit(self) -> None:
        self.app.exit()


class AddHostScreen(Screen):
    """Form screen for host configuration."""

    BINDINGS = [
        Binding("p", "probe", "Probe"),
        Binding("u", "save", "Update"),
        Binding("c", "cancel", "Cancel"),
        Binding("r", "delete", "Remove"),
    ]

    def __init__(self, host_to_edit: str = None):
        super().__init__()
        self.host_to_edit = host_to_edit # This is now the label

    def compose(self) -> ComposeResult:
        title = "📝 Edit Host" if self.host_to_edit else "➕ Add New Host"
        yield Header()
        yield Vertical(
            Static(title, id="form_title"),
            Vertical(
                Horizontal(Label("Hostname:"), Input(id="hostname"), classes="form-row"),
                Horizontal(Label("Label:"), Input(id="label"), classes="form-row"),
                Horizontal(Label("Probe Cmd:"), Input(id="probe_cmd"), classes="form-row"),
                Horizontal(Label("Refresh (s):"), Input(value="10", id="refresh_interval"), classes="form-row"),
                Horizontal(Label("Active:"), Checkbox("Active", value=True, id="active"), classes="form-row"),
                id="form_fields",
            ),
            Horizontal(
                Button("Update" if self.host_to_edit else "Save", variant="success", id="save_btn"),
                Button("Probe", variant="primary", id="probe_btn"),
                Button("Cancel", variant="error", id="cancel_btn"),
                Button("Remove", variant="error", id="rem_btn"),
                id="form_buttons",
            ),
            id="form_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        if self.host_to_edit:
            hm = HostManager()
            info = hm.get_host_info(self.host_to_edit)
            if info:
                self.query_one("#hostname", Input).value = info.get("hostname", "")
                self.query_one("#label", Input).value = self.host_to_edit
                self.query_one("#probe_cmd", Input).value = info.get("probe_cmd", "")
                self.query_one("#refresh_interval", Input).value = str(info.get("refresh_interval", 10))
                self.query_one("#active", Checkbox).value = info.get("active", True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        hm = HostManager()
        if event.button.id == "cancel_btn":
            self.action_cancel()
        elif event.button.id == "rem_btn":
            self.action_delete()
        elif event.button.id == "save_btn":
            self.action_save()
        elif event.button.id == "probe_btn":
            self.action_probe()

    def action_save(self) -> None:
        hm = HostManager()
        hostname = self.query_one("#hostname", Input).value
        label = self.query_one("#label", Input).value
        probe_cmd = self.query_one("#probe_cmd", Input).value
        active = self.query_one("#active", Checkbox).value
        try:
            refresh = int(self.query_one("#refresh_interval", Input).value)
        except ValueError:
            refresh = 10
        
        if label and hostname:
            # Handle renaming: if label changed, use rename_host to preserve metrics
            if self.host_to_edit and label != self.host_to_edit:
                hm.rename_host(self.host_to_edit, label, hostname, active, refresh, probe_cmd)
            else:
                hm.add_host(label, hostname, active, refresh, probe_cmd)
            
            self.app.pop_screen()
            self._refresh_parent()
        elif not label:
            # In a real app, we'd show an error message here
            pass

    def action_delete(self) -> None:
        hm = HostManager()
        label = self.query_one("#label", Input).value
        if label:
            hm.remove_host(label)
            self.app.pop_screen()
            self._refresh_parent()

    def action_probe(self) -> None:
        """Executes the current probe command and shows the result in a popup."""
        hostname = self.query_one("#hostname", Input).value
        probe_cmd = self.query_one("#probe_cmd", Input).value
        
        if not hostname or not probe_cmd:
            self.app.notify("Hostname and Probe Cmd are required to probe", severity="error")
            return

        self.app.notify(f"Probing {hostname}...", severity="information")
        
        # Handle special internal commands first
        stripped_cmd = probe_cmd.strip()
        if stripped_cmd.startswith("cm-mac-smi"):
            parts = stripped_cmd.split()
            target_host = parts[1] if len(parts) > 1 else hostname
            full_cmd = stripped_cmd
            
            # Immediate debug print
            debug_start = f"\n[DEBUG] Starting Probe (Internal) | Host: {target_host} | Cmd: {full_cmd}\n"
            sys.stderr.write(debug_start)
            sys.stderr.flush()
            with open("probe_debug.log", "a") as f:
                f.write(debug_start)
            
            output = cm_mac_smi(target_host)
            success = not output.startswith("Error")
        elif stripped_cmd.startswith("cm-spark-smi"):
            parts = stripped_cmd.split()
            target_host = parts[1] if len(parts) > 1 else hostname
            full_cmd = stripped_cmd
            
            # Immediate debug print
            debug_start = f"\n[DEBUG] Starting Probe (Internal) | Host: {target_host} | Cmd: {full_cmd}\n"
            sys.stderr.write(debug_start)
            sys.stderr.flush()
            with open("probe_debug.log", "a") as f:
                f.write(debug_start)
            
            output = cm_spark_smi(target_host)
            success = not output.startswith("Error")
        elif stripped_cmd.startswith("cm-dgx-smi"):
            parts = stripped_cmd.split()
            # Format: cm-dgx-smi [target_host] [devices]
            if len(parts) > 2:
                target_host = parts[1]
                devices = parts[2]
            elif len(parts) == 2:
                if "," in parts[1]:
                    target_host = hostname
                    devices = parts[1]
                else:
                    target_host = parts[1]
                    devices = "0"
            else:
                target_host = hostname
                devices = "0"
            
            full_cmd = stripped_cmd
            
            # Immediate debug print
            debug_start = f"\n[DEBUG] Starting Probe (Internal) | Host: {target_host} | Devices: {devices} | Cmd: {full_cmd}\n"
            sys.stderr.write(debug_start)
            sys.stderr.flush()
            with open("probe_debug.log", "a") as f:
                f.write(debug_start)
            
            output = cm_dgx_smi(target_host, devices)
            success = not output.startswith("Error")
        else:
            full_cmd = self.app.screen._get_full_probe_cmd(probe_cmd) if isinstance(self.app.screen, DashboardScreen) else (probe_cmd if probe_cmd.startswith("nvidia-smi") else f"nvidia-smi {probe_cmd}")
            
            # Immediate debug print to stderr and file to verify the action started
            debug_start = f"\n[DEBUG] Starting Probe | Host: {hostname} | Cmd: {full_cmd}\n"
            sys.stderr.write(debug_start)
            sys.stderr.flush()
            with open("probe_debug.log", "a") as f:
                f.write(debug_start)

            # Run the probe command
            executor = RemoteExecutor()
            success, output = executor.run_command(hostname, full_cmd)
        
        # Clean the output to remove SSH warnings
        # Since _clean_probe_output is in DashboardScreen, we can access it via app.screen if it's a DashboardScreen
        # or just implement a static helper. For now, we'll use a simple cleaning logic here or call the method.
        if isinstance(self.app.screen, DashboardScreen):
            output = self.app.screen._clean_probe_output(output)
        else:
            # Fallback cleaning if not on DashboardScreen
            if output:
                output = "\n".join([l for l in output.splitlines() if not l.strip().startswith("**")])

        self.app.notify("Probe command returned", severity="information")

        # Log to the logger, stderr, and file for maximum visibility
        status = "SUCCESS" if success else "FAILED"
        # Use the full_cmd determined during execution
        debug_msg = f"\n[DEBUG] Probe {status} | Host: {hostname} | Cmd: '{full_cmd}'\nOutput:\n{output}\n{'-'*60}\n"
        
        logging.debug(debug_msg)
        sys.stderr.write(debug_msg)
        sys.stderr.flush()
        with open("probe_debug.log", "a") as f:
            f.write(debug_msg)
        
        self.app.notify(f"Debug output sent to stderr and probe_debug.log", severity="information")
        self.app.push_screen(ProbeResultScreen(output))

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def _refresh_parent(self):
        # Refresh parent screen metrics if applicable
        if isinstance(self.app.screen, DashboardScreen):
            self.app.screen.update_metrics()


class CloudmeshAIMonitorApp(App):
    """Main Textual Application with fixed CSS."""
    title = "Cloudmesh AI Monitor Dashboard"

    BINDINGS = [
        Binding("escape", "quit", "Quit"),
    ]

    CSS = """
    #title, #form_title {
        text-align: center;
        text-style: bold;
        margin: 1 0;
        color: $accent;
    }
    #dashboard_container { padding: 1 2; }
    DataTable { 
        height: 1fr; 
        border: round $primary; 
    }
    DataTable > .datatable--cursor {
        background: $accent 30%;
    }
    #form_container {
        align: center middle;
        width: 100%;
        height: auto;
        border: thick $primary;
        padding: 1 2;
        background: $surface;
    }
    .form-row { height: auto; margin: 1 0; }
    .form-row Label { width: 15; text-align: right; margin-right: 2; }
    .form-row Input { width: 1fr; }
    #form_buttons { align: center middle; height: auto; margin-top: 1; }
    #form_buttons Button { margin: 0 1; }
    #detail_panel {
        width: 50;
        height: auto;
        background: $surface;
        border: thick $accent;
        padding: 1 2;
        content-align: left middle;
    }
    #hint { text-align: center; color: $text-disabled; margin-top: 1; }
    """

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())

    def action_quit(self) -> None:
        self.exit()


def run_app():
    app = CloudmeshAIMonitorApp()
    app.run()


if __name__ == "__main__":
    run_app()