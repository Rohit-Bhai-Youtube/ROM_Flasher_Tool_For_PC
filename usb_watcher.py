import time
import subprocess
import os
import sys
import shutil
import re

def find_tool(name):
    """Locate a platform tool via PATH, bundled tools/, script dir, then legacy C:\\adb."""
    found = shutil.which(name)
    if found:
        return found

    exe_name = name + ".exe" if sys.platform == "win32" else name
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "tools", exe_name),
        os.path.join(script_dir, exe_name),
    ]
    if sys.platform == "win32":
        candidates.extend([
            os.path.join("C:\\adb", exe_name),
            os.path.join("C:\\platform-tools", exe_name),
            os.path.expanduser(f"~\\platform-tools\\{exe_name}"),
            os.path.expanduser(f"~\\AppData\\Local\\Android\\Sdk\\platform-tools\\{exe_name}"),
        ])

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None

def check_devices():
    # Check ADB
    adb_path = find_tool("adb")
    if adb_path:
        try:
            proc = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=5)
            lines = [l.strip() for l in proc.stdout.splitlines()[1:] if l.strip()]
            for l in lines:
                if re.match(r"^\S+\s+(device|recovery|sideload)$", l):
                    return True
        except Exception:
            pass

    # Check Fastboot
    fastboot_path = find_tool("fastboot")
    if fastboot_path:
        try:
            proc2 = subprocess.run([fastboot_path, "devices"], capture_output=True, text=True, timeout=5)
            for l in proc2.stdout.splitlines():
                if re.match(r"^\S+\s+fastboot\b", l.strip()):
                    return True
        except Exception:
            pass

    return False

def is_tool_running():
    try:
        proc = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ROM_Flasher_Tool.exe"], capture_output=True, text=True)
        return "rom_flasher_tool.exe" in proc.stdout.lower()
    except Exception:
        return False

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(base_dir, "ROM_Flasher_Tool.exe")
    if not os.path.exists(exe_path):
        exe_path = os.path.join(os.path.dirname(base_dir), "ROM_Flasher_Tool.exe")

    print("USB Watcher active: Listening for ADB & Fastboot device connections...")
    was_connected = False

    while True:
        connected = check_devices()
        if connected and not was_connected:
            print("Android Device detected on USB!")
            if not is_tool_running():
                print(f"Auto-launching ROM Flasher Tool: {exe_path}")
                subprocess.Popen([exe_path])
        was_connected = connected
        time.sleep(2.5)

if __name__ == "__main__":
    main()
