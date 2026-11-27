import os
import sys
import subprocess
import shutil

def build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    print("Building ROM Flasher Tool executable...")
    
    icon_path = os.path.join(base_dir, "icon.ico")
    ui_data = f"ui{os.pathsep}ui"
    devices_data = f"xiaomi_devices.json{os.pathsep}."
    drivers_data = f"drivers{os.pathsep}drivers"
    tools_data = f"tools{os.pathsep}tools"
    root_tools_data = f"root_tools{os.pathsep}root_tools"
    
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name=ROM_Flasher_Tool_For_PC",
        f"--icon={icon_path}",
        f"--add-data={ui_data}",
        f"--add-data={devices_data}",
        f"--add-data={drivers_data}",
        f"--add-data={tools_data}",
        f"--add-data={root_tools_data}",
        "--hidden-import=webview",
        "--hidden-import=webview.platforms.winforms",
        "--hidden-import=clr",
        "--hidden-import=pythonnet",
        "--hidden-import=payload_dumper",
        "--hidden-import=payload_dumper.dumper",
        "--hidden-import=payload_dumper.update_metadata_pb2",
        "--hidden-import=google.protobuf",
        "--hidden-import=miunlock",
        "--hidden-import=migate",
        "--hidden-import=pyaes",
        "--hidden-import=requests",
        "--hidden-import=qrcode",
        "--hidden-import=py7zr",
        "main.py"
    ]

    print("Running command:", " ".join(cmd))
    proc = subprocess.run(cmd)
    if proc.returncode == 0:
        exe_src = os.path.join(base_dir, "dist", "ROM_Flasher_Tool_For_PC.exe")
        exe_dst = os.path.join(base_dir, "ROM_Flasher_Tool_For_PC.exe")
        desktop_dst = os.path.join(os.path.dirname(base_dir), "ROM_Flasher_Tool_For_PC.exe")
        
        if os.path.exists(exe_src):
            shutil.copy2(exe_src, exe_dst)
            print(f"Copied executable to: {exe_dst}")
            try:
                shutil.copy2(exe_src, desktop_dst)
                print(f"Copied executable to Desktop: {desktop_dst}")
            except Exception as e:
                print(f"Notice: {e}")
        print("Build succeeded!")
    else:
        print("Build failed with returncode:", proc.returncode)

if __name__ == "__main__":
    build()
