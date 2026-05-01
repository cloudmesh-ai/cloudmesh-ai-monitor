import pytest
from unittest.mock import MagicMock, patch, ANY
import subprocess
from cloudmesh.ai.command.monitor_plugin import MonitorPlugin

@pytest.fixture
def plugin():
    return MonitorPlugin()

@pytest.fixture
def mock_hm():
    with patch('cloudmesh.ai.command.monitor_plugin.HostManager') as mock:
        instance = mock.get_instance.return_value
        # Setup default mock data
        instance.get_hosts_ordered.return_value = [
            ("host1", {"hostname": "h1.example.com", "active": True, "refresh_interval": 10, "gpu_usage": "10%", "gpu_temp": "40 C", "mem_usage": "20%"}),
            ("host2", {"hostname": "h2.example.com", "active": False, "refresh_interval": 10, "gpu_usage": "0%", "gpu_temp": "30 C", "mem_usage": "0%"}),
        ]
        instance.hosts_data = {"host1": {}, "host2": {}}
        yield instance

def test_get_data(plugin, mock_hm):
    data = plugin.get_data()
    assert len(data) == 2
    assert data[0]["label"] == "host1"
    assert data[0]["hostname"] == "h1.example.com"
    assert data[1]["active"] is False

def test_update_interval(plugin, mock_hm):
    result = plugin.update_interval(20)
    assert result["success"] is True
    assert result["updated"] == 1  # Only host1 is active
    mock_hm.add_host.assert_called_once()

def test_update_host_active(plugin, mock_hm):
    result = plugin.update_host_active("host1", 0)
    assert result["success"] is True
    assert result["active"] is False
    mock_hm.set_active.assert_called_with("host1", False)

def test_refresh_host_inactive(plugin, mock_hm):
    # Host2 is inactive
    result = plugin.refresh_host("host2", automatic=True)
    assert result["success"] is True
    assert "skipping automatic probe" in result["message"]

@patch('subprocess.run')
def test_refresh_host_ssh_success(mock_run, plugin, mock_hm):
    # Mock SSH output: gpu_util, gpu_temp, mem_used, mem_total
    mock_run.return_value = MagicMock(
        returncode=0, 
        stdout="50, 60, 1000, 4000", 
        stderr=""
    )
    
    # Setup host with a standard probe command
    mock_hm.get_hosts_ordered.return_value = [
        ("host1", {"hostname": "h1.example.com", "active": True, "probe_cmd": "nvidia-smi ..."})
    ]
    
    result = plugin.refresh_host("host1")
    assert result["success"] is True
    assert "refreshed successfully" in result["message"]
    mock_hm.update_metrics.assert_called()

@patch('subprocess.run')
def test_refresh_host_ssh_auth_failure(mock_run, plugin, mock_hm):
    mock_run.return_value = MagicMock(
        returncode=255, 
        stdout="", 
        stderr="Permission denied (publickey)."
    )
    
    result = plugin.refresh_host("host1")
    assert result["success"] is False
    assert "SSH Authentication failed" in result["error"]

@patch('subprocess.run')
def test_refresh_host_timeout(mock_run, plugin, mock_hm):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh ...", timeout=15)
    
    result = plugin.refresh_host("host1")
    assert result["success"] is False
    assert "timed out" in result["error"]

@patch('importlib.import_module')
def test_refresh_host_python_probe(mock_import, plugin, mock_hm):
    # Mock the dynamic function
    mock_module = MagicMock()
    mock_func = MagicMock(return_value={
        "gpu_usage": "30%", "gpu_temp": "50 C", "mem_usage": "40%", 
        "cpu_usage": "10%", "cpu_temp": "40 C"
    })
    setattr(mock_module, "cm_dgx_smi", mock_func)
    mock_import.return_value = mock_module
    
    # Setup host with Python probe path
    mock_hm.get_hosts_ordered.return_value = [
        ("host1", {"hostname": "h1.example.com", "active": True, "probe_cmd": "cloudmesh.ai.monitor.probe.cm-dgx-smi h1 0"})
    ]
    
    result = plugin.refresh_host("host1")
    assert result["success"] is True
    assert "Python probe cm_dgx_smi executed successfully" in result["message"]
    mock_func.assert_called()

@patch('subprocess.run')
def test_open_terminal_iterm(mock_run, plugin, mock_hm):
    # Mock iTerm2 check (simplified)
    # In the actual code, it tries osascript. We mock subprocess.run for osascript.
    mock_run.return_value = MagicMock(returncode=0)
    
    result = plugin.open_terminal("host1")
    assert result["success"] is True
    assert "iTerm2 opened" in result["message"]
    assert mock_run.call_count >= 1

def test_open_terminal_host_not_found(plugin, mock_hm):
    mock_hm.get_hosts_ordered.return_value = []
    result = plugin.open_terminal("unknown")
    assert result["success"] is False
    assert "Host not found" in result["error"]