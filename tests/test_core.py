import pytest
import os
from pathlib import Path
from cloudmesh.ai.monitor.core import HostManager

@pytest.fixture
def temp_config(tmp_path):
    config_path = tmp_path / "hosts.yaml"
    status_path = tmp_path / "hosts-status.yaml"
    return str(config_path), str(status_path)

def test_host_manager_singleton():
    hm1 = HostManager.get_instance()
    hm2 = HostManager.get_instance()
    assert hm1 is hm2

def test_add_and_get_host(temp_config):
    config_path, status_path = temp_config
    # Force a new instance for testing with temp paths
    HostManager._instance = None 
    hm = HostManager(config_path=config_path, status_path=status_path)
    
    hm.add_host("test-host", "1.2.3.4", active=True, refresh_interval=5)
    
    info = hm.get_host_info("test-host")
    assert info["hostname"] == "1.2.3.4"
    assert info["active"] is True
    assert info["refresh_interval"] == 5

def test_toggle_active(temp_config):
    config_path, status_path = temp_config
    HostManager._instance = None
    hm = HostManager(config_path=config_path, status_path=status_path)
    
    hm.add_host("test-host", "1.2.3.4", active=True)
    hm.set_active("test-host", False)
    assert hm.get_host_info("test-host")["active"] is False
    
    hm.set_active("test-host", True)
    assert hm.get_host_info("test-host")["active"] is True

def test_host_ordering(temp_config):
    config_path, status_path = temp_config
    HostManager._instance = None
    hm = HostManager(config_path=config_path, status_path=status_path)
    
    hm.add_host("h1", "1.1.1.1")
    hm.add_host("h2", "2.2.2.2")
    hm.add_host("h3", "3.3.3.3")
    
    # Initial order should be h1, h2, h3
    ordered = [label for label, info in hm.get_hosts_ordered()]
    assert ordered == ["h1", "h2", "h3"]
    
    hm.move_host("h3", "up") # h1, h3, h2
    ordered = [label for label, info in hm.get_hosts_ordered()]
    assert ordered == ["h1", "h3", "h2"]
    
    hm.move_host("h3", "up") # h3, h1, h2
    ordered = [label for label, info in hm.get_hosts_ordered()]
    assert ordered == ["h3", "h1", "h2"]

def test_remove_host(temp_config):
    config_path, status_path = temp_config
    HostManager._instance = None
    hm = HostManager(config_path=config_path, status_path=status_path)
    
    hm.add_host("test-host", "1.2.3.4")
    assert "test-host" in hm.hosts_data
    
    hm.remove_host("test-host")
    assert "test-host" not in hm.hosts_data