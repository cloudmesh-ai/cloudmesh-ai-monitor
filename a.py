import sys
import os

# Add src directory to sys.path to allow importing from the package
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from cloudmesh.ai.monitor.terminalgui.core import mac_smi

def test_mac_smi():
    print("Testing mac_smi on localhost...")
    result = mac_smi("localhost")
    print(f"Result: {result}")
    
    if result.startswith("Error"):
        print("\n❌ Test Failed")
    else:
        print("\n✅ Test Passed")
        print(f"Parsed Metrics (Util, Temp, MemUsed, MemTotal): {result}")

if __name__ == "__main__":
    test_mac_smi()