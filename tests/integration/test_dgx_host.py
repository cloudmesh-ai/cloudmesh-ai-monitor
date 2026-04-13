import pytest
from src.cloudmesh.ai.monitor.terminalgui.core import cm_dgx_smi

# We use a marker to identify integration tests that require a real host
pytest.mark.integration = pytest.mark.marker("integration")

@pytest.mark.integration
def test_cm_dgx_smi_real_host():
    """
    Integration test that verifies cm_dgx_smi against the actual 'dgx' host.
    """
    hostname = "dgx"
    devices = "0"
    
    # Execute the real probe
    result = cm_dgx_smi(hostname, devices=devices)
    
    # 1. Verify we didn't get an error string
    assert isinstance(result, dict), f"Expected dict from cm_dgx_smi, got {type(result)}: {result}"
    
    # 2. Verify all expected keys are present
    expected_keys = {"gpu_usage", "gpu_temp", "mem_usage", "cpu_usage", "cpu_temp"}
    assert expected_keys.issubset(result.keys()), f"Missing keys in result: {expected_keys - result.keys()}"
    
    # 3. Verify GPU metrics are present and numeric
    # Since we requested device "0", we expect at least one entry
    assert len(result["gpu_usage"]) > 0, "gpu_usage list should not be empty"
    assert isinstance(result["gpu_usage"][0], float), f"gpu_usage should be float, got {type(result['gpu_usage'][0])}"
    
    assert len(result["gpu_temp"]) > 0, "gpu_temp list should not be empty"
    assert isinstance(result["gpu_temp"][0], float), f"gpu_temp should be float, got {type(result['gpu_temp'][0])}"
    
    # 4. Verify memory usage is present and numeric
    mem_usage = result["mem_usage"]
    assert len(mem_usage) > 0, "mem_usage list should not be empty"
    first_mem = mem_usage[0]
    assert len(first_mem) == 2, f"mem_usage entry should have 2 values [perc, total], got {first_mem}"
    assert isinstance(first_mem[0], (int, float)), f"Memory percentage should be numeric, got {type(first_mem[0])}"
    assert isinstance(first_mem[1], (int, float)), f"Memory total should be numeric, got {type(first_mem[1])}"

    print(f"\nIntegration test passed for {hostname}: {result}")