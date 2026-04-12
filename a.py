import sys
import os

# Add src directory to sys.path to allow importing from the package
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from cloudmesh.ai.monitor.terminalgui.core import cm_mac_smi

def test_cm_mac_smi():
    print("Testing cm_mac_smi on localhost...")
    result = cm_mac_smi("localhost")
    print(f"Result: {result}")
    
    if result.startswith("Error"):
        print("\n❌ Test Failed")
    else:
        print("\n✅ Test Passed")
        print(f"Parsed Metrics (Util, Temp, MemUsed, MemTotal): {result}")

if __name__ == "__main__":
    test_cm_mac_smi()
