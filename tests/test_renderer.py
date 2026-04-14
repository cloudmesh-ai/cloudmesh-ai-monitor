import pytest
from cloudmesh.ai.monitor.renderer import CellRenderer

def test_render_usage():
    # Single value
    assert CellRenderer.render_cell("gpu_usage", 10)["text"] == "10%"
    assert CellRenderer.render_cell("gpu_usage", 85)["color"] == "text-red-400 font-bold"
    assert CellRenderer.render_cell("gpu_usage", 65)["color"] == "text-yellow-400"
    assert CellRenderer.render_cell("gpu_usage", 30)["color"] == "text-green-400"
    
    # Multiple values
    assert CellRenderer.render_cell("gpu_usage", [10, 20])["text"] == "10 20%"
    assert CellRenderer.render_cell("gpu_usage", [10, 85])["color"] == "text-red-400 font-bold"
    
    # N/A values
    assert CellRenderer.render_cell("gpu_usage", "N/A")["text"] == "N/A"
    assert CellRenderer.render_cell("gpu_usage", [10, "N/A"])["text"] == "10%"
    assert CellRenderer.render_cell("gpu_usage", ["N/A", "N/A"])["text"] == "N/A"
    assert CellRenderer.render_cell("gpu_usage", None)["text"] == "N/A"

def test_render_temp():
    # Single value
    assert CellRenderer.render_cell("gpu_temp", 45)["text"] == "45°C"
    assert CellRenderer.render_cell("gpu_temp", 85)["color"] == "text-red-400 font-bold"
    
    # Multiple values
    assert CellRenderer.render_cell("gpu_temp", [45, 50])["text"] == "45 50°C"
    assert CellRenderer.render_cell("gpu_temp", [45, 85])["color"] == "text-red-400 font-bold"
    
    # N/A values
    assert CellRenderer.render_cell("gpu_temp", "N/A")["text"] == "N/A"
    assert CellRenderer.render_cell("gpu_temp", [45, "N/A"])["text"] == "45°C"

def test_render_mem():
    # Single GPU: [[perc, total]]
    assert CellRenderer.render_cell("mem_usage", [[10, 80]])["text"] == "10% (80GB)"
    
    # Multiple GPUs: [[perc, total], [perc, total]]
    assert CellRenderer.render_cell("mem_usage", [[10, 80], [20, 80]])["text"] == "10 20% (2*80GB)"
    
    # Multiple GPUs different sizes
    assert CellRenderer.render_cell("mem_usage", [[10, 80], [20, 40]])["text"] == "10 20% (80, 40 GB)"
    
    # Single value (fallback)
    assert CellRenderer.render_cell("mem_usage", 10)["text"] == "10%"
    
    # N/A values
    assert CellRenderer.render_cell("mem_usage", "N/A")["text"] == "N/A"
    assert CellRenderer.render_cell("mem_usage", [["N/A", "N/A"]])["text"] == "N/A"

def test_render_cell_default():
    # Test default renderer for unknown columns
    assert CellRenderer.render_cell("unknown_col", "some_value")["text"] == "some_value"
    assert CellRenderer.render_cell("unknown_col", "some_value")["color"] == "text-slate-400"