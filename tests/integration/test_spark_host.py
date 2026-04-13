import pytest
from src.cloudmesh.ai.monitor.terminalgui.core import cm_spark_smi

# We use a marker to identify integration tests that require a real host
# This allows running unit tests separately from integration tests
pytest.mark.integration = pytest.mark.marker("integration")

@pytest.mark.integration
def test_cm_spark_smi_real_host():
    """
    Integration test that verifies cm_spark_smi against the actual 'spark' host.
    This ensures that the SSH connection, remote commands, and parsing logic
    all work together in the real environment.
    """
    hostname = "spark"
    
    # Execute the real probe
    result = cm_spark_smi(hostname)
    
    # 1. Verify we didn't get an error string
    assert isinstance(result, dict), f"Expected dict from cm_spark_smi, got {type(result)}: {result}"
    
    # 2. Verify all expected keys are present
    expected_keys = {"gpu_usage", "gpu_temp", "mem_usage", "cpu_usage", "cpu_temp"}
    assert expected_keys.issubset(result.keys()), f"Missing keys in result: {expected_keys - result.keys()}"
    
    # 3. Verify memory usage is not N/A (the specific bug we fixed)
    # mem_usage should be a list of [perc, total]
    mem_usage = result["mem_usage"]
    assert len(mem_usage) > 0, "mem_usage list should not be empty"
    
    first_mem = mem_usage[0]
    assert len(first_mem) == 2, f"mem_usage entry should have 2 values [perc, total], got {first_mem}"
    assert first_mem[0] != "N/A", f"Memory percentage should be a number, got {first_mem[0]}"
    assert first_mem[1] != "N/A", f"Memory total should be a number, got {first_mem[1]}"
    
    # 4. Verify types are correct (floats/ints)
    assert isinstance(first_mem[0], (int, float)), f"Memory percentage should be numeric, got {type(first_mem[0])}"
    assert isinstance(first_mem[1], (int, float)), f"Memory total should be numeric, got {type(first_mem[1])}"

    print(f"\nIntegration test passed for {hostname}: {result}")