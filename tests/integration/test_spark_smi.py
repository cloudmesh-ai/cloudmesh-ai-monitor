import unittest
from unittest.mock import patch, MagicMock
from src.cloudmesh.ai.monitor.terminalgui.core import cm_spark_smi, RemoteExecutor

class TestCmSparkSmi(unittest.TestCase):
    def setUp(self):
        self.hostname = "test-host"

    @patch('src.cloudmesh.ai.monitor.terminalgui.core.RemoteExecutor.run_command')
    def test_gpu_memory_success(self, mock_run):
        """Test that valid GPU memory is correctly parsed and used."""
        def side_effect(host, cmd):
            if "nvidia-smi" in cmd:
                # util, temp, used, total
                return True, "10, 45, 2048, 8192"
            if "top" in cmd:
                return True, "Cpu(s): 5.0 us, 2.0 sy, 0.0 ni, 93.0 id"
            if "sensors" in cmd:
                return True, "Package id 0: +40.0°C"
            return False, ""

        mock_run.side_effect = side_effect
        
        result = cm_spark_smi(self.hostname)
        
        # used=2048, total=8192 -> 25% / 8.0GB
        self.assertEqual(result['mem_usage'], [[25.0, 8.0]])
        self.assertEqual(result['gpu_usage'], [10.0])
        self.assertEqual(result['gpu_temp'], [45.0])

    @patch('src.cloudmesh.ai.monitor.terminalgui.core.RemoteExecutor.run_command')
    def test_gpu_memory_na_fallback_to_system(self, mock_run):
        """Test that [N/A] GPU memory triggers fallback to /proc/meminfo."""
        def side_effect(host, cmd):
            if "nvidia-smi" in cmd:
                # GPU metrics present, but memory is N/A
                return True, "10, 45, [N/A], [N/A]"
            if "cat /proc/meminfo" in cmd:
                # Total: 128GB, Available: 64GB -> 50% used
                return True, "MemTotal: 134217728 kB\nMemAvailable: 67108864 kB"
            if "top" in cmd:
                return True, "Cpu(s): 5.0 us, 2.0 sy, 0.0 ni, 93.0 id"
            if "sensors" in cmd:
                return True, "Package id 0: +40.0°C"
            return False, ""

        mock_run.side_effect = side_effect
        
        result = cm_spark_smi(self.hostname)
        
        # Should fallback to system memory: 50% of 128GB
        self.assertEqual(result['mem_usage'], [[50.0, 128.0]])
        self.assertEqual(result['gpu_usage'], [10.0])

    @patch('src.cloudmesh.ai.monitor.terminalgui.core.RemoteExecutor.run_command')
    def test_all_memory_fail(self, mock_run):
        """Test that if both GPU and system memory fail, it returns N/A."""
        def side_effect(host, cmd):
            if "nvidia-smi" in cmd:
                return True, "10, 45, [N/A], [N/A]"
            if "cat /proc/meminfo" in cmd:
                return False, "Permission denied"
            return True, "some output"

        mock_run.side_effect = side_effect
        
        result = cm_spark_smi(self.hostname)
        
        self.assertEqual(result['mem_usage'], [["N/A", "N/A"]])

    @patch('src.cloudmesh.ai.monitor.terminalgui.core.RemoteExecutor.run_command')
    def test_nvidia_smi_failure(self, mock_run):
        """Test that if nvidia-smi fails completely, an error string is returned."""
        mock_run.return_value = (False, "command not found")
        
        result = cm_spark_smi(self.hostname)
        
        self.assertTrue(result.startswith("Error: nvidia-smi failed"))

if __name__ == '__main__':
    unittest.main()