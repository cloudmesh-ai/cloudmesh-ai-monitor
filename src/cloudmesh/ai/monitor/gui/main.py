from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Any
from contextlib import asynccontextmanager
import uvicorn
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from cloudmesh.ai.monitor.terminalgui.core import HostManager, RemoteExecutor, cm_dgx_smi, cm_spark_smi, cm_mac_smi
from cloudmesh.ai.monitor.gui.renderer import CellRenderer

async def trigger_initial_probes():
    """Trigger an initial probe for all active hosts on startup."""
    print("Triggering initial probes for all active hosts...")
    for label, info in hm.get_hosts_ordered():
        if info.get("active", True):
            # Reset timer immediately but keep last known values and success status
            hm.update_metrics(
                label, 
                info.get("gpu_usage", "N/A"), 
                info.get("gpu_temp", "N/A"), 
                info.get("mem_usage", "N/A"), 
                cpu_usage=info.get("cpu_usage", "N/A"), 
                cpu_temp=info.get("cpu_temp", "N/A"), 
                last_probe_success=info.get("last_probe_success")
            )
            in_flight_probes.add(label)
            
            hostname = info.get("hostname")
            default_probe = "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
            probe_cmd = info.get("probe_cmd") or default_probe
            print(f"[INFO] Starting initial probe | Host: {label} ({hostname}) | Cmd: {probe_cmd}")
            asyncio.create_task(run_probe_with_timeout(label, hostname, probe_cmd))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    await trigger_initial_probes()
    print("Starting background scheduler loop...")
    scheduler_task = asyncio.create_task(scheduler_loop())
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        print("Background scheduler loop stopped.")

app = FastAPI(title="Cloudmesh AI Monitor API", lifespan=lifespan)
hm = HostManager()
executor = RemoteExecutor()
in_flight_probes = set()
next_probe_time = {} # Maps label -> datetime of next allowed probe

# Global mapping of internal probe function names to the actual functions
PROBE_FUNCTIONS = {
    "cm_dgx_smi": cm_dgx_smi,
    "cm_spark_smi": cm_spark_smi,
    "cm_mac_smi": cm_mac_smi,
}

# Removed duplicate PROBE_FUNCTIONS mapping

class HostConfig(BaseModel):
    hostname: str
    label: str
    probe_cmd: Optional[str] = None
    refresh_interval: Optional[int] = 10
    active: Optional[bool] = True

class HostStatus(BaseModel):
    label: str
    hostname: str
    active: bool
    refresh_interval: int
    probe_cmd: Optional[str] = None
    gpu_usage: Any # Rendered as {"text": str, "color": str}
    gpu_temp: Any # Rendered as {"text": str, "color": str}
    mem_usage: Any # Rendered as {"text": str, "color": str}
    cpu_usage: Any # Rendered as {"text": str, "color": str}
    cpu_temp: Any # Rendered as {"text": str, "color": str}
    last_probe_success: Optional[bool] = None
    last_updated: Optional[str] = None
    is_probing: bool = False
    is_stale: bool = False

@app.get("/api/hosts", response_model=List[HostStatus])
async def get_hosts():
    hosts = []
    for label, info in hm.get_hosts_ordered():
        # Calculate if the host is stale (last update > interval)
        is_stale = False
        last_updated_str = info.get("probe", {}).get("time")
        interval = info.get("refresh_interval", 10)
        
        if not last_updated_str:
            is_stale = True
        else:
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
                now = datetime.now(last_updated.tzinfo) if last_updated.tzinfo else datetime.now()
                if (now - last_updated) >= timedelta(seconds=interval):
                    is_stale = True
            except (ValueError, TypeError):
                is_stale = True

        hosts.append(HostStatus(
            label=label,
            hostname=info.get("hostname", "N/A"),
            active=info.get("active", True),
            refresh_interval=interval,
            probe_cmd=info.get("probe_cmd"),
            gpu_usage=CellRenderer.render_cell("gpu_usage", info.get("gpu_usage", "N/A")),
            gpu_temp=CellRenderer.render_cell("gpu_temp", info.get("gpu_temp", "N/A")),
            mem_usage=CellRenderer.render_cell("mem_usage", info.get("mem_usage", "N/A")),
            cpu_usage=CellRenderer.render_cell("cpu_usage", info.get("cpu_usage", "N/A")),
            cpu_temp=CellRenderer.render_cell("cpu_temp", info.get("cpu_temp", "N/A")),
            last_probe_success=info.get("last_probe_success"),
            last_updated=last_updated_str,
            is_probing=(label in in_flight_probes),
            is_stale=is_stale
        ))
    return hosts

@app.post("/api/hosts")
async def add_host(config: HostConfig):
    hm.add_host(config.label, config.hostname, config.active, config.refresh_interval, config.probe_cmd)
    return {"status": "success"}

@app.put("/api/hosts/{label}")
async def update_host(label: str, config: HostConfig):
    if label != config.label:
        hm.rename_host(label, config.label, config.hostname, config.active, config.refresh_interval, config.probe_cmd)
    else:
        hm.add_host(config.label, config.hostname, config.active, config.refresh_interval, config.probe_cmd)
    return {"status": "success"}

@app.delete("/api/hosts/{label}")
async def delete_host(label: str):
    hm.remove_host(label)
    return {"status": "success"}

@app.post("/api/hosts/{label}/toggle")
async def toggle_host(label: str):
    info = hm.get_host_info(label)
    if not info:
        raise HTTPException(status_code=404, detail="Host not found")
    new_active = not info.get("active", True)
    hm.set_active(label, new_active)
    return {"status": "success", "active": new_active}

async def run_probe_with_timeout(label: str, hostname: str, probe_cmd: str, timeout: int = 30):
    """Wraps perform_probe with a timeout to prevent hanging threads from blocking the system."""
    try:
        await asyncio.wait_for(asyncio.to_thread(perform_probe, label, hostname, probe_cmd), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[ERROR] Probe timed out after {timeout}s | Host: {label}")
        # Ensure the host is removed from in-flight probes so it can be probed again
        in_flight_probes.discard(label)
        hm.update_metrics(label, "N/A", "N/A", "N/A", last_probe_success=False)
    except Exception as e:
        print(f"[ERROR] Unexpected error during probe for {label}: {e}")
        in_flight_probes.discard(label)

def perform_probe(label: str, hostname: str, probe_cmd: str):
    """Core logic to probe a host and update metrics."""
    try:
        # Normalize probe_cmd for matching (strip whitespace and treat - as _)
        normalized_cmd = probe_cmd.strip().replace('-', '_') if probe_cmd else ""
        
        # Find if any internal probe name is the start of the command
        matched_probe = None
        for probe_name in PROBE_FUNCTIONS:
            if normalized_cmd == probe_name or normalized_cmd.startswith(probe_name + " "):
                matched_probe = probe_name
                break
        
        if matched_probe:
            # Execute internal Python probe function
            try:
                result = PROBE_FUNCTIONS[matched_probe](hostname)
                if isinstance(result, dict):
                    # Extract metrics and update
                    gpu_u = result.get("gpu_usage", "N/A")
                    gpu_t = result.get("gpu_temp", "N/A")
                    mem_u = result.get("mem_usage", "N/A")
                    cpu_u = result.get("cpu_usage", "N/A")
                    cpu_t = result.get("cpu_temp", "N/A")
                    
                    hm.update_metrics(
                        label, 
                        gpu_u, gpu_t, mem_u, 
                        cpu_usage=cpu_u, cpu_temp=cpu_t, 
                        last_probe_success=True
                    )
                else:
                    # result is an error string
                    hm.update_metrics(label, "N/A", "N/A", "N/A", last_probe_success=False)
            except Exception:
                hm.update_metrics(label, "N/A", "N/A", "N/A", last_probe_success=False)
        else:
            # Execute as a raw shell command via SSH
            success, output = executor.run_command(hostname, probe_cmd)
            if success:
                hm.update_metrics(label, "Probed", "Probed", "Probed", last_probe_success=True)
            else:
                hm.update_metrics(label, "N/A", "N/A", "N/A", last_probe_success=False)
    finally:
        in_flight_probes.discard(label)
        print(f"[INFO] Probe completed | Host: {label}")
        # Once a probe is completed, the new probe start time is set to now + interval
        info = hm.get_host_info(label)
        if info:
            interval = info.get("refresh_interval", 10)
            next_probe_time[label] = datetime.now() + timedelta(seconds=interval)

@app.post("/api/hosts/{label}/probe")
async def probe_host(label: str, background_tasks: BackgroundTasks):
    if label in in_flight_probes:
        return {"status": "already_probing", "message": "A probe is already ongoing for this host."}

    info = hm.get_host_info(label)
    if not info:
        raise HTTPException(status_code=404, detail="Host not found")
    
    hostname = info.get("hostname")
    default_probe = "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
    probe_cmd = info.get("probe_cmd") or default_probe
    
    print(f"[INFO] Starting manual probe | Host: {label} ({hostname}) | Cmd: {probe_cmd}")
    in_flight_probes.add(label)
    background_tasks.add_task(run_probe_with_timeout, label, hostname, probe_cmd)
    return {"status": "probing"}

async def scheduler_loop():
    """Background loop that triggers probes based on refresh_interval."""
    while True:
        try:
            now = datetime.now()
            for label, info in hm.get_hosts_ordered():
                if not info.get("active", True):
                    continue
                
                # A host can only issue one probe at a time
                if label in in_flight_probes:
                    continue

                # Check if it's time for a new probe
                next_time = next_probe_time.get(label)
                if next_time is None or now >= next_time:
                    # Trigger probe
                    in_flight_probes.add(label)
                    
                    hostname = info.get("hostname")
                    default_probe = "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits"
                    probe_cmd = info.get("probe_cmd") or default_probe
                    
                    print(f"[INFO] Starting scheduled probe | Host: {label} ({hostname}) | Cmd: {probe_cmd}")
                    # Run probe in a separate thread to avoid blocking the loop
                    asyncio.create_task(run_probe_with_timeout(label, hostname, probe_cmd))
            
            # Sleep for a short period before checking again
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Scheduler error: {e}")
            await asyncio.sleep(5)

# Removed deprecated startup_event in favor of lifespan

# Serve static files for the frontend
# Use absolute path relative to this file to ensure it works regardless of CWD
current_dir = Path(__file__).parent
static_dir = current_dir / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

def start_gui(port: int = 8000):
    """Start the Web GUI server."""
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start_gui()
