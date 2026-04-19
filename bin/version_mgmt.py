import sys
import re
import os

VERSION_FILE = "VERSION"

def get_version():
    with open(VERSION_FILE, "r") as f:
        return f.read().strip()

def set_version(version):
    with open(VERSION_FILE, "w") as f:
        f.write(version)

def calculate_next_versions(version):
    # Match base version (x.y.z) and optional dev part (devN)
    match = re.match(r"(\d+\.\d+\.\d+)(?:\.dev(\d+))?", version)
    if not match:
        print(f"Error: Version {version} does not match expected format x.y.z[.devN]")
        sys.exit(1)

    base = match.group(1)
    dev = int(match.group(2)) if match.group(2) else 0

    # Next Patch: increment the last digit of base
    parts = base.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    next_patch = ".".join(parts)

    # Next Dev: base.dev(N+1)
    next_dev = f"{base}.dev{dev + 1}"

    return base, next_patch, next_dev

def main():
    if len(sys.argv) < 2:
        print("Usage: python version_mgmt.py [version|patch]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "version":
        version = get_version()
        base, next_patch, next_dev = calculate_next_versions(version)
        print(f"Current:   {version}")
        print("Suggested Next Steps:")
        print(f"  Release:   make patch V={base}")
        print(f"  Patch:     make patch V={next_patch}")
        print(f"  Dev:       make patch V={next_dev}")
    elif cmd == "patch":
        if len(sys.argv) < 3:
            print("Usage: python version_mgmt.py patch <version>")
            sys.exit(1)
        new_version = sys.argv[2]
        set_version(new_version)
        print(f"Version updated to {new_version} in {VERSION_FILE}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()