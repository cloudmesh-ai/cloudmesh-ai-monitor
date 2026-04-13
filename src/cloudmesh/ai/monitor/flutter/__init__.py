"""
Flutter-based monitoring for cloudmesh-ai.
This module provides formatting utilities to ensure the Flutter GUI 
displays multi-GPU metrics correctly.
"""

from typing import Any, List, Union
from cloudmesh.ai.monitor.terminalgui.core import HostManager

def render_metric(value: Any, metric_type: str) -> str:
    """
    Renders raw metrics (lists) into user-friendly display strings.
    Mirrors the logic used in the Terminal GUI.
    """
    if not value or value == "N/A":
        return ""

    # Handle case where value might still be a string (legacy or error)
    if isinstance(value, str):
        if value == "N/A": return ""
        if metric_type == "mem":
            parts = value.split()
            mem_list = []
            for p in parts:
                if "/" in p:
                    mem_list.append(p.split("/", 1))
                else:
                    mem_list.append([p, "N/A"])
            value = mem_list
        else:
            value = value.split()

    if not value:
        return ""

    if metric_type in ("temp", "usage"):
        # Normalize value to a list
        if isinstance(value, str):
            if value.startswith("[") and value.endswith("]"):
                import ast
                try:
                    value = ast.literal_eval(value)
                except Exception:
                    value = value.split()
            else:
                value = value.split()
        elif not isinstance(value, (list, tuple)):
            value = [value]

        vals = " ".join([str(v) for v in value if v != "N/A"])
        if not vals:
            return ""
        
        suffix = "°C" if metric_type == "temp" else "%"
        return f"{vals}{suffix}"
    elif metric_type == "mem":
        percs = []
        totals = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                p, t = item[0], item[1]
                if p != "N/A": percs.append(f"{p}%")
                if t != "N/A": totals.append(str(t))
            elif item != "N/A":
                percs.append(str(item))
        
        perc_str = " ".join(percs)
        
        if not perc_str and not totals:
            return ""
        
        if not totals:
            return perc_str
        
        unique_totals = list(set(totals))
        if len(unique_totals) == 1:
            size = unique_totals[0]
            count = len(totals)
            total_str = f"{count}*{size}GB" if count > 1 else f"{size}GB"
        else:
            total_str = f"{', '.join(totals)} GB"
        
        return f"{perc_str} ({total_str})"
    
    return str(value)

def get_formatted_metrics():
    """
    Fetches all hosts from HostManager and returns their metrics 
    formatted for the Flutter GUI.
    """
    hm = HostManager()
    formatted_data = []
    
    for label, info in hm.get_hosts_ordered():
        formatted_data.append({
            "label": label,
            "hostname": info.get("hostname", "N/A"),
            "active": info.get("active", True),
            "interval": f"{info.get('refresh_interval', 10)}s",
            "gpu_usage": render_metric(info.get("gpu_usage"), "usage"),
            "gpu_temp": render_metric(info.get("gpu_temp"), "temp"),
            "mem_usage": render_metric(info.get("mem_usage"), "mem"),
            "cpu_usage": render_metric(info.get("cpu_usage"), "usage"),
            "cpu_temp": render_metric(info.get("cpu_temp"), "temp"),
        })
        
    return formatted_data