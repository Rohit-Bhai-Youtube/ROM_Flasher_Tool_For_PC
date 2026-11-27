import os
import sys
import io
import json
import math
import re
import shlex
import shutil
import threading
import time
import webview
import ctypes
import functools
import inspect

# Safe stdout/stderr streams to prevent 'NoneType' object has no attribute 'fileno' in windowed mode
class SafeStream(io.StringIO):
    def __init__(self):
        super().__init__()
        # Each stream gets its own valid devnull descriptor (no console required).
        self._fd = os.open(os.devnull, os.O_WRONLY)
    def fileno(self): return self._fd
    def isatty(self): return False
    def flush(self): pass

if sys.stdout is None or not hasattr(sys.stdout, 'fileno'):
    sys.stdout = SafeStream()

if sys.stderr is None or not hasattr(sys.stderr, 'fileno'):
    sys.stderr = SafeStream()

from backend import AndroidBridge, get_storage_dir

bridge = AndroidBridge()

# Bridge-level allowlists. The UI can be closed/tampered with, so every
# device-mutating call is validated again before it reaches backend.py.
ROOT_FRAMEWORK_WHITELIST = {"Magisk", "KernelSU", "APatch", "SukiSU Ultra"}
OPTIMIZER_TWEAK_WHITELIST = {
    "force_120hz", "force_144hz", "restore_refresh",
    "disable_joyose", "enable_joyose", "set_animation",
    "set_private_dns", "disable_telemetry", "max_performance_pack",
}
_SERIAL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_COM_PORT_RE = re.compile(r"^COM\d{1,4}$", re.IGNORECASE)
TERMINAL_DANGEROUS_TOKENS = {
    "-w", "flashall", "flash:raw", "erase", "format", "wipe", "flash", "update",
    "rm", "dd", "mkfs", "shred", "clear", "unlock", "lock", "edl",
}
TERMINAL_DANGEROUS_PHRASES = (
    "oem unlock", "oem lock", "flashing unlock", "flashing lock", "erase userdata",
    "erase metadata", "pm clear", "fastboot -w", "install ", "push ", "pull ",
)
READONLY_ADB_SHELL_COMMANDS = {
    "getprop", "settings", "dumpsys", "pm", "wm", "screenrecord", "input", "am", "content",
}
MIRROR_FPS_ALLOWLIST = {30, 60, 90}
MIRROR_BITRATE_ALLOWLIST = {"4M", "8M", "16M"}
UNBRICK_MEMORY_TYPES = {"emmc", "ufs"}
MAX_PATH_LEN = 4096


def _clean_serial(serial):
    if not isinstance(serial, str):
        return None
    serial = serial.strip()
    return serial if _SERIAL_RE.fullmatch(serial) else None


def _serial_cleaned(fn):
    """Validate/normalize the `serial` argument before any bridge method uses it."""
    optional_serial = False
    try:
        params = list(inspect.signature(fn).parameters.values())
        names = [p.name for p in params]
        idx = names.index('serial') - 1  # 'self' is not in args
        optional_serial = params[names.index('serial')].default is None
    except (TypeError, ValueError):
        idx = None
        optional_serial = False

    @functools.wraps(fn)
    def _wrapped(self, *args, **kwargs):
        if 'serial' in kwargs:
            value = kwargs['serial']
            clean = value if value is None and optional_serial else _clean_serial(value)
            if clean is None and not (value is None and optional_serial):
                return {'success': False, 'error': 'Invalid device serial.'}
            kwargs['serial'] = clean
        elif idx is not None and idx < len(args):
            value = args[idx]
            clean = value if value is None and optional_serial else _clean_serial(value)
            if clean is None and not (value is None and optional_serial):
                return {'success': False, 'error': 'Invalid device serial.'}
            args = list(args)
            args[idx] = clean
        return fn(self, *args, **kwargs)
    return _wrapped


def _path_error(path, required=False):
    if path is None or path == "":
        return None if not required else "A file/folder path is required."
    if not isinstance(path, str):
        return "Invalid file/folder path."
    if "\x00" in path or len(path) > MAX_PATH_LEN:
        return "Invalid file/folder path."
    return None


def _bounded_int(value, low, high):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def _optimizer_value_error(tweak_id, value):
    """Reject anything that could become a shell token inside backend.py."""
    if tweak_id == "set_animation":
        try:
            n = float(value)
        except (TypeError, ValueError):
            return "Invalid animation scale. Use a number between 0 and 10."
        if not math.isfinite(n) or n < 0 or n > 10:
            return "Invalid animation scale. Use a number between 0 and 10."
        return None
    if tweak_id == "set_private_dns":
        if str(value or "").lower() not in ("adguard", "cloudflare", "off"):
            return "Invalid Private DNS provider."
        return None
    if value not in (None, ""):
        return "This optimization does not accept a custom value."
    return None


class Api:
    def __init__(self):
        self._window = None
        self._async_state_lock = threading.Lock()
        self._async_download_busy = False
        self._active_run_ids = {}

    def set_window(self, window):
        self._window = window

    def _eval_js_raw(self, script):
        """Evaluate JS and report delivery success (used where fallback handling matters)."""
        if not self._window:
            return False
        try:
            result = self._window.evaluate_js(script)
            return True if result is None else bool(result)
        except Exception:
            return False

    def _eval_js(self, script):
        """Best-effort fire-and-forget evaluation for progress callbacks."""
        return self._eval_js_raw(script)

    @staticmethod
    def _safe_pct(pct):
        """Return a clamped, JSON-safe progress number (or None) for JS callbacks."""
        if isinstance(pct, bool) or not isinstance(pct, (int, float)):
            return None
        if not math.isfinite(pct):
            return None
        return max(0.0, min(100.0, float(pct)))

    @staticmethod
    def _api_error(exc, shape=None):
        """Return a structured error instead of leaking an exception into JS."""
        result = {"success": False, "error": str(exc)}
        if shape:
            result.update(shape)
        return result

    def _run_async(self, work, done_callback_name, extra_args=None):
        """Run off the UI thread; serialize downloads and ignore superseded run callbacks."""
        if not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*', str(done_callback_name or "")):
            raise ValueError("Invalid JS callback name")

        extra = list(extra_args or [])
        run_id = extra[0] if extra else None
        owns_download_slot = False

        def _invoke(args):
            # A stale completion from an older run must never move the UI backwards.
            with self._async_state_lock:
                if run_id is not None and self._active_run_ids.get(done_callback_name) != run_id:
                    return True
            call = (f"(function(){{ if (typeof window.{done_callback_name} !== 'function') return false; "
                    f"try {{ window.{done_callback_name}({', '.join(args)}); }} catch (e) "
                    f"{{ console.error(e); }} return true; }})()")
            return self._eval_js_raw(call)

        with self._async_state_lock:
            if run_id is not None:
                # A newer run supersedes the older one; its late callback is dropped.
                self._active_run_ids[done_callback_name] = run_id
            if done_callback_name in ("onRomDownloadComplete", "onPayloadDumpComplete"):
                if self._async_download_busy:
                    return {"success": False, "error": "Another download/dump is already running."}
                self._async_download_busy = True
                owns_download_slot = True

        def _run():
            try:
                error_text = None
                try:
                    res = work()
                    if not isinstance(res, dict):
                        res = None
                except Exception as e:
                    res = None
                    error_text = str(e) or "Unknown backend error"
                if res is None:
                    res = {"success": False, "error": error_text or "Invalid result from backend"}
                try:
                    payload = json.dumps(res)
                except Exception as e:
                    payload = json.dumps({
                        "success": False,
                        "error": f"Failed to serialize backend result: {e}",
                    })
                args = [payload] + [json.dumps(x) for x in extra]
                if not _invoke(args):
                    fallback_args = [json.dumps({"success": False, "error": "Callback delivery failed"})] + [json.dumps(x) for x in extra]
                    _invoke(fallback_args)
            finally:
                if owns_download_slot:
                    with self._async_state_lock:
                        self._async_download_busy = False

        threading.Thread(target=_run, daemon=True).start()

    def check_environment(self):
        """Check if ADB and Fastboot exist."""
        def _resolve(path, bare_names):
            if os.path.basename(str(path)).lower() in bare_names:
                found = shutil.which(path)
                return (found or path), bool(found)
            return path, os.path.isfile(path)

        adb_path, adb_ok = _resolve(bridge.adb_path, ("adb", "adb.exe"))
        fb_path, fb_ok = _resolve(bridge.fastboot_path, ("fastboot", "fastboot.exe"))
        return {
            "adb": adb_path,
            "fastboot": fb_path,
            "adb_ok": adb_ok,
            "fastboot_ok": fb_ok
        }

    def detect_devices(self):
        return bridge.detect_devices()

    @_serial_cleaned
    def get_device_details(self, serial, mode):
        return bridge.get_device_details(serial, mode)

    @_serial_cleaned
    def reboot(self, serial, mode, target):
        return bridge.reboot(serial, mode, target)

    @_serial_cleaned
    def flash_partition(self, serial, partition, file_path, disable_avb=False):
        return bridge.flash_partition(serial, partition, file_path, disable_avb)

    @_serial_cleaned
    def boot_image(self, serial, file_path):
        return bridge.boot_image(serial, file_path)

    @_serial_cleaned
    def adb_sideload(self, serial, file_path):
        def work():
            def _cb(msg, pct):
                safe_msg = json.dumps(msg)
                pct_val = json.dumps(self._safe_pct(pct))
                self._eval_js(f"window.onSideloadProgress && window.onSideloadProgress({safe_msg}, {pct_val});")
            return bridge.adb_sideload(serial, file_path, progress_cb=_cb)
        self._run_async(work, "onSideloadComplete")
        return {"status": "started"}

    def wireless_adb_pair(self, ip_port, pairing_code):
        return bridge.wireless_adb_pair(ip_port, pairing_code)

    def wireless_adb_connect(self, ip_port):
        return bridge.wireless_adb_connect(ip_port)

    @_serial_cleaned
    def wireless_adb_tcpip(self, serial, port=5555):
        return bridge.wireless_adb_tcpip(serial, port)

    def wireless_adb_disconnect(self, ip_port=""):
        return bridge.wireless_adb_disconnect(ip_port)

    def wireless_adb_history(self):
        return bridge.wireless_adb_history()

    def wireless_adb_discover(self):
        return bridge.wireless_adb_discover()

    def wireless_adb_qr_generate(self):
        return bridge.wireless_adb_qr_generate()

    def wireless_adb_qr_poll_and_pair(self, service, password):
        return bridge.wireless_adb_qr_poll_and_pair(service, password)

    @_serial_cleaned
    def erase_partition(self, serial, partition):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        if str(partition or "").strip().lower() not in ("frp", "config"):
            return {"success": False, "error": "Only FRP/config erase is allowed."}
        return bridge.erase_partition(clean_serial, str(partition).strip().lower())

    @_serial_cleaned
    def format_data(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        return bridge.format_wipe_data(clean_serial)

    @_serial_cleaned
    def set_slot(self, serial, slot):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        if str(slot or "").strip().lower() not in ("a", "b"):
            return {"success": False, "error": "Invalid slot. Expected 'a' or 'b'."}
        return bridge.set_active_slot(clean_serial, str(slot).strip().lower())

    @_serial_cleaned
    def check_unlock_brand(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial.", "is_xiaomi": False}
        return bridge.check_unlock_brand(clean_serial)

    def mi_account_logout(self):
        return bridge.mi_account_logout()

    @_serial_cleaned
    def mi_unlock_device(self, serial, username="", password="", region="India", login_method="password", use_cached=False, run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        if not isinstance(region, str) or region not in ("India", "Singapore", "Europe", "China", "Russia"):
            return {"success": False, "error": "Invalid Mi Unlock region."}
        if not isinstance(login_method, str) or login_method not in ("password", "browser_qr"):
            return {"success": False, "error": "Invalid Mi login method."}

        def work():
            def _cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    args = [safe_msg, pct_val]
                    if run_id is not None:
                        args.append(json.dumps(run_id))
                    self._eval_js(f"window.onMiUnlockProgress && window.onMiUnlockProgress({', '.join(args)});")
            return bridge.mi_unlock_workflow(
                clean_serial, username=username, password=password, region=region,
                login_method=login_method, use_cached=bool(use_cached), progress_cb=_cb
            )
        self._run_async(work, "onMiUnlockComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    @_serial_cleaned
    def unlock_bootloader(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        return bridge.unlock_bootloader(clean_serial)

    @_serial_cleaned
    def lock_bootloader(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        return bridge.lock_bootloader(clean_serial)

    # Universal APK / APKS / XAPK Installer
    @_serial_cleaned
    def install_app(self, serial, file_path):
        if not serial or not file_path:
            return {"success": False, "error": "A target device and package file are required."}
        try:
            return bridge.universal_install_app(serial, file_path)
        except Exception as e:
            return self._api_error(e)

    # Debloater & App Manager APIs
    @_serial_cleaned
    def get_installed_packages(self, serial):
        if not serial:
            return {"success": False, "error": "No target device selected.", "packages": [], "total": 0}
        try:
            return bridge.get_installed_packages(serial)
        except Exception as e:
            return self._api_error(e, {"packages": [], "total": 0})

    @_serial_cleaned
    def uninstall_packages(self, serial, pkg_list):
        if not serial or not isinstance(pkg_list, list):
            return {"success": False, "error": "Invalid uninstall request.", "count": 0, "failed": []}
        try:
            return bridge.uninstall_packages(serial, pkg_list)
        except Exception as e:
            return self._api_error(e, {"count": 0, "failed": []})

    @_serial_cleaned
    def disable_packages(self, serial, pkg_list):
        if not serial or not isinstance(pkg_list, list):
            return {"success": False, "error": "Invalid disable request.", "count": 0, "failed": []}
        try:
            return bridge.disable_packages(serial, pkg_list)
        except Exception as e:
            return self._api_error(e, {"count": 0, "failed": []})

    @_serial_cleaned
    def enable_packages(self, serial, pkg_list):
        if not serial or not isinstance(pkg_list, list):
            return {"success": False, "error": "Invalid enable request.", "count": 0, "failed": []}
        try:
            return bridge.enable_packages(serial, pkg_list)
        except Exception as e:
            return self._api_error(e, {"count": 0, "failed": []})

    @_serial_cleaned
    def backup_packages(self, serial, pkg_list, folder_path=None):
        if not serial or not isinstance(pkg_list, list):
            return {"success": False, "error": "Invalid backup request.", "count": 0, "failed": []}
        try:
            if not folder_path:
                from backend import get_storage_dir
                folder_path = get_storage_dir("App_Backups")
            return bridge.backup_packages(serial, pkg_list, folder_path)
        except Exception as e:
            return self._api_error(e, {"count": 0, "failed": []})

    def open_app_backups_folder(self):
        return bridge.open_app_backups_folder()

    def install_drivers(self):
        return bridge.install_drivers()

    def uninstall_drivers(self):
        return bridge.uninstall_drivers()

    def fix_fastboot_driver(self):
        return bridge.fix_fastboot_driver()

    def open_storage_subfolder(self, subfolder):
        from backend import get_storage_dir
        safe_sub = re.sub(r'[^A-Za-z0-9_.-]', '_', str(subfolder or "").strip()).strip(".")
        if not safe_sub:
            return {"success": False, "error": "Invalid subfolder name"}
        folder = get_storage_dir(safe_sub)
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)
        return {"success": True, "path": folder}

    # 🔥 AUTO FLASHER ENGINE
    def inspect_rom(self, rom_path):
        return bridge.inspect_rom_path(rom_path)

    def prepare_and_scan_rom(self, rom_path, run_id=None):
        def work():
            def progress_cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    args = [safe_msg, pct_val]
                    if run_id is not None:
                        args.append(json.dumps(run_id))
                    self._eval_js(f"window.onRomScanProgress && window.onRomScanProgress({', '.join(args)});")

            return bridge.prepare_and_scan_rom(rom_path, progress_cb=progress_cb)

        extra = [run_id] if run_id is not None else None
        self._run_async(work, "onRomScanComplete", extra_args=extra)
        return {"status": "started", "run_id": run_id}

    @_serial_cleaned
    def auto_flash_rom(self, serial, rom_path, selected_script=None, run_id=None):
        def work():
            def progress_cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    args = [safe_msg, pct_val]
                    if run_id is not None:
                        args.append(json.dumps(run_id))
                    self._eval_js(f"window.onAutoFlashProgress && window.onAutoFlashProgress({', '.join(args)});")

            return bridge.auto_flash(serial, rom_path, selected_script, progress_cb=progress_cb)

        extra = [run_id] if run_id is not None else None
        self._run_async(work, "onAutoFlashComplete", extra_args=extra)
        return {"status": "started", "run_id": run_id}

    def cancel_auto_flash(self):
        return bridge.cancel_auto_flash()

    # 🔥 ROOT STUDIO ENGINE
    def download_root_framework(self, framework_name):
        return bridge.download_root_framework(framework_name)

    @_serial_cleaned
    def install_root(self, serial, framework_name, boot_img_path=None, run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        if framework_name not in ROOT_FRAMEWORK_WHITELIST:
            return {"success": False, "error": "Unsupported root framework."}
        path_err = _path_error(boot_img_path)
        if path_err:
            return {"success": False, "error": path_err}

        def work():
            return bridge.install_root_workflow(clean_serial, framework_name, boot_img_path)
        self._run_async(work, "onRootComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    @_serial_cleaned
    def uninstall_root(self, serial, stock_boot_path=None, run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        path_err = _path_error(stock_boot_path)
        if path_err:
            return {"success": False, "error": path_err}

        def work():
            return bridge.uninstall_root_workflow(clean_serial, stock_boot_path)
        self._run_async(work, "onRootUninstallComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    # 🔥 XIAOMI & POCO BOOT / INIT_BOOT AUTO-DOWNLOADER
    def get_xiaomi_devices(self, query=""):
        if not isinstance(query, str):
            return []
        return bridge.get_xiaomi_devices(query)

    def fetch_xiaomi_versions(self, codename, region="ALL"):
        if not isinstance(codename, str) or not isinstance(region, str):
            return {"success": False, "error": "Invalid device codename or region."}
        return bridge.fetch_xiaomi_rom_versions(codename, region)

    def download_xiaomi_boot(self, codename, version, download_url, recovery_url=None):
        def work():
            def progress_cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    self._eval_js(f"window.onXiaomiBootProgress && window.onXiaomiBootProgress({safe_msg}, {pct_val});")

            return bridge.download_xiaomi_boot_images(codename, version, download_url, recovery_url=recovery_url, progress_cb=progress_cb)

        self._run_async(work, "onXiaomiBootDownloadComplete")
        return {"status": "started"}

    # 🔥 FASTBOOT & RECOVERY FULL ROM DOWNLOADER
    def download_full_rom(self, download_url, save_folder=None):
        if (not isinstance(download_url, str)
                or not download_url.lower().startswith(("http://", "https://"))):
            return {"success": False, "error": "Invalid ROM download URL."}
        if save_folder is not None:
            if not isinstance(save_folder, str) or not save_folder.strip():
                return {"success": False, "error": "Invalid download folder."}
            try:
                storage_root = os.path.realpath(get_storage_dir())
                chosen = os.path.realpath(save_folder)
                if (os.path.commonpath([storage_root, chosen]) != storage_root
                        or not os.path.isdir(chosen)):
                    return {"success": False, "error": "Download folder must be an existing folder inside ROM_Flasher_Storage."}
            except Exception:
                return {"success": False, "error": "Invalid download folder."}

        def work():
            def progress_cb(data):
                if self._window:
                    safe_data = json.dumps(data)
                    self._eval_js(f"window.onRomDownloadProgress && window.onRomDownloadProgress({safe_data});")

            return bridge.download_rom_package(download_url, save_folder, progress_cb=progress_cb)

        self._run_async(work, "onRomDownloadComplete")
        return {"status": "started"}

    def cancel_rom_download(self):
        return bridge.cancel_rom_download()

    # 📦 PAYLOAD DUMPER STUDIO APIS
    def inspect_payload(self, file_path):
        return bridge.inspect_payload_package(file_path)

    def dump_payload(self, file_path, partition_names, run_id=None):
        def work():
            def progress_cb(msg, pct):
                safe_msg = json.dumps(msg)
                pct_val = json.dumps(self._safe_pct(pct))
                args = [safe_msg, pct_val]
                if run_id is not None:
                    args.append(json.dumps(run_id))
                self._eval_js(f"window.onPayloadDumpProgress && window.onPayloadDumpProgress({', '.join(args)});")

            return bridge.extract_payload_partitions(file_path, partition_names, progress_cb=progress_cb)

        extra = [run_id] if run_id is not None else None
        self._run_async(work, "onPayloadDumpComplete", extra_args=extra)
        return {"status": "started", "run_id": run_id}

    def cancel_payload_dump(self):
        return bridge.cancel_payload_dump()

    def extract_boot_from_file(self, file_path):
        return bridge.extract_boot_from_local_rom(file_path)

    @_serial_cleaned
    def validate_boot_image(self, file_path, serial=None):
        return bridge.validate_boot_image_selection(file_path, serial)

    def open_in_explorer(self, file_or_folder_path):
        import subprocess
        if not isinstance(file_or_folder_path, str) or not file_or_folder_path.strip():
            return {"success": False, "error": "Invalid path."}
        target = os.path.abspath(file_or_folder_path)
        if not os.path.exists(target):
            return {"success": False, "error": "Path not found"}
        try:
            if os.path.isdir(target):
                os.startfile(target)
            else:
                # argv list + shell=False: quotes/metacharacters cannot become commands.
                subprocess.Popen(["explorer.exe", f"/select,{target}"], shell=False)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": f"Could not open path: {e}"}

    def open_browser_url(self, url):
        import webbrowser
        if not isinstance(url, str) or not url.startswith("https://"):
            return {"success": False, "error": "Only HTTPS URLs may be opened."}
        webbrowser.open(url)
        return {"success": True}

    def open_external_url(self, url):
        return self.open_browser_url(url)

    def check_for_updates(self):
        """Check GitHub Releases for new updates."""
        return bridge.check_for_updates()

    def apply_update(self, download_url=None):
        """Download latest release and replace executable in-place.
        The JS-supplied URL is untrusted; the backend uses the one stored by check_for_updates()."""
        if getattr(bridge, "is_flashing", False) or getattr(bridge, "active_flash_proc", None):
            return {"success": False, "error": "Cannot update while a flash/scan is running"}
        if getattr(bridge, "is_device_action_busy", lambda: False)():
            return {"success": False, "error": "Cannot update while a device operation is running"}
        with self._async_state_lock:
            if self._async_download_busy:
                return {"success": False, "error": "Cannot update while a download/dump is running"}
        def _cb(pct, status_text):
            if self._window:
                try:
                    safe_pct = json.dumps(self._safe_pct(pct))
                    js = f"if (window.onUpdateDownloadProgress) window.onUpdateDownloadProgress({safe_pct}, {json.dumps(status_text)});"
                    self._eval_js(js)
                except Exception:
                    pass
        return bridge.apply_update(None, progress_cb=_cb)

    def send_flash_input(self, text=""):
        return bridge.send_flash_input(text)

    def run_custom_cmd(self, command_str, force=False):
        raw_cmd = str(command_str or "").strip()
        try:
            tokens = shlex.split(raw_cmd, posix=False)
            parts = [
                token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'") else token
                for token in tokens
            ]
        except Exception:
            return {"success": False, "output": "Invalid command syntax"}
        if not parts:
            return {"success": False, "output": "Empty command"}
        normalized_cmd = shlex.join(parts)

        if bridge.is_device_action_busy():
            return {"success": False, "output": "Another device operation is already running; terminal command blocked."}

        # Confirm before any command that can erase, overwrite, unlock or delete data.
        lower_cmd = raw_cmd.lower()
        lower_parts = []
        for token in parts:
            lower_parts.extend(token.lower().replace('"', '').split())
        is_destructive = (
            any(p in TERMINAL_DANGEROUS_TOKENS or p.startswith(("mkfs.", "flash:", "erase:")) for p in lower_parts)
            or any(phrase in lower_cmd for phrase in TERMINAL_DANGEROUS_PHRASES)
        )
        if force is not True and is_destructive:
            return {"success": False, "needs_confirmation": True, "output": f"Destructive command requires confirmation: {normalized_cmd}"}

        # Device-touching commands must name the exact target; no implicit default device.
        serial_idx = parts.index("-s") if "-s" in parts else (-1)
        target_serial = _clean_serial(parts[serial_idx + 1]) if serial_idx >= 0 and serial_idx + 1 < len(parts) else None
        if is_destructive and not target_serial:
            return {"success": False, "output": "Destructive terminal commands must include '-s <exact-serial>'."}

        # adb shell is restricted to declared read-only/inspection verbs.
        # Global options such as `-s SERIAL` come BEFORE `shell`; find the real
        # shell token, reject duplicate targets and device-side shell chaining.
        tool_name = parts[0].lower()
        if tool_name == "adb":
            shell_idx = -1
            s_count = 0
            i = 1
            while i < len(parts):
                opt = parts[i].lower()
                if opt == "shell":
                    shell_idx = i
                    break
                if opt == "-s":
                    s_count += 1
                    i += 2
                    continue
                if opt in ("-e", "-t", "-a", "-d", "-L", "-p", "-P"):
                    i += 2
                    continue
                i += 1
            if s_count > 1:
                return {"success": False, "output": "Only one '-s <serial>' is allowed."}
            if shell_idx >= 0:
                remote = " ".join(parts[shell_idx + 1:])
                if re.search(r"[;&|`$<>\r\n]|\$\(|\$\{|&&|\|\|", remote):
                    return {"success": False, "output": "Shell chaining/metacharacters are not allowed in the safe terminal."}
                shell_tokens = remote.lower().split()
                shell_verb = shell_tokens[0] if shell_tokens else ""
                if shell_verb not in READONLY_ADB_SHELL_COMMANDS:
                    return {"success": False, "output": f"adb shell verb '{shell_verb}' is not allowed in the safe terminal."}

        # Never launch a second adb/fastboot process while a flash is running with no stdin pipe.
        if getattr(bridge, "is_flashing", False) and not getattr(bridge, "active_flash_proc", None):
            return {"success": False, "output": f"A flash is already running; use the prompt bar to send input to it instead of launching: {normalized_cmd}"}

        # If flashing script is actively running, route input straight to script's stdin!
        if (getattr(bridge, "is_flashing", False) or getattr(bridge, "active_flash_proc", None)) and bridge.active_flash_proc:
            return bridge.send_flash_input(command_str)

        tool = parts[0].lower()
        if tool == "adb":
            parts[0] = bridge.adb_path
        elif tool == "fastboot":
            parts[0] = bridge.fastboot_path
        else:
            if getattr(bridge, "active_flash_proc", None):
                return bridge.send_flash_input(command_str)
            return {"success": False, "output": f"Only 'adb' and 'fastboot' commands are allowed. Got: {tool}"}

        return bridge.run_cmd(parts, timeout=120)

    def open_file_dialog(self, file_type="all"):
        if not self._window:
            return None
        
        file_types = {
            "img": ("Image Files (*.img;*.bin;*.sin)", "All Files (*.*)"),
            "zip": ("ZIP Files (*.zip)", "All Files (*.*)"),
            "tgz": ("Fastboot ROM Archives (*.tgz;*.tar;*.tar.gz;*.zip)", "All Files (*.*)"),
            "boot_source": ("Boot Images / ROM Archives (*.img;*.bin;*.tgz;*.tar;*.tar.gz;*.zip)", "All Files (*.*)"),
            "rom_package": ("ROM Archives (*.tgz;*.tar;*.tar.gz;*.zip;*.bin;*.img)", "All Files (*.*)"),
            "payload": ("Payload and ROM Files (*.bin;*.zip)", "All Files (*.*)"),
            "apk": ("Android App Files (*.apk;*.xapk;*.apks;*.apkm;*.zip)", "All Files (*.*)"),
            "loader": ("EDL Loader / DA Files (*.elf;*.mbn;*.bin)", "All Files (*.*)"),
            "auth": ("EDL Auth / Signature Files (*.auth;*.sig;*.mbn;*.bin)", "All Files (*.*)"),
            "all": ("All Files (*.*)",)
        }
        if not isinstance(file_type, str):
            file_type = "all"
        filters = file_types.get(file_type, file_types["all"])
        try:
            res = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=filters)
            if res and len(res) > 0:
                return res[0]
        except Exception:
            # Callers expect a path string or None; a dict would flow into file APIs.
            return None
        return None

    def open_folder_dialog(self):
        if not self._window:
            return None
        try:
            res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            if res and len(res) > 0:
                return res[0]
        except Exception:
            return None
        return None

    # 🛡️ FEATURE 1: EFS / IMEI ENGINE APIS
    @_serial_cleaned
    def backup_efs(self, serial, run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}

        def work():
            def _cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    safe_run = json.dumps(run_id)
                    self._eval_js(f"window.onEfsBackupProgress && window.onEfsBackupProgress({safe_msg}, {pct_val}, {safe_run});")
            return bridge.backup_efs_imei(clean_serial, progress_cb=_cb)
        self._run_async(work, "onEfsBackupComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    def list_efs_backups(self, current_serial=None):
        if current_serial is not None:
            current_serial = _clean_serial(current_serial)
            if not current_serial:
                return {"success": False, "backups": [], "error": "Invalid serial."}
        return bridge.list_efs_backups(current_serial)

    @_serial_cleaned
    def restore_efs(self, serial, folder_path, run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        path_err = _path_error(folder_path, required=True)
        if path_err:
            return {"success": False, "error": path_err}

        def work():
            def _cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    safe_run = json.dumps(run_id)
                    self._eval_js(f"window.onEfsRestoreProgress && window.onEfsRestoreProgress({safe_msg}, {pct_val}, {safe_run});")
            return bridge.restore_efs_imei(clean_serial, folder_path, progress_cb=_cb)
        self._run_async(work, "onEfsRestoreComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    # 🚀 FEATURE 4: OPTIMIZER & FPS BOOSTER APIS
    @_serial_cleaned
    def get_optimizer_status(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        return bridge.get_optimizer_status(clean_serial)

    @_serial_cleaned
    def apply_optimizer_tweak(self, serial, tweak_id, value=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        if not isinstance(tweak_id, str) or tweak_id not in OPTIMIZER_TWEAK_WHITELIST:
            return {"success": False, "error": "Unknown optimization."}
        value_err = _optimizer_value_error(tweak_id, value)
        if value_err:
            return {"success": False, "error": value_err}
        return bridge.apply_optimizer_tweak(clean_serial, tweak_id, value)

    @_serial_cleaned
    def open_developer_options(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        return bridge.open_developer_options(clean_serial)

    # 🔋 FEATURE 5: HARDWARE & BATTERY DIAGNOSTICS APIS
    @_serial_cleaned
    def get_hardware_diagnostics(self, serial, full_audit=True):
        return bridge.get_hardware_diagnostics(serial, full_audit=full_audit)

    @_serial_cleaned
    def trigger_hardware_test(self, serial, test_type):
        return bridge.trigger_hardware_test(serial, test_type)

    # 📺 FEATURE 6: SCREEN MIRRORING & RECORDING APIS
    @_serial_cleaned
    def start_screen_mirror(self, serial, max_fps=60, bitrate="8M", run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        try:
            fps_value = int(max_fps)
        except (TypeError, ValueError):
            return {"success": False, "error": "Invalid mirror FPS."}
        if (fps_value not in MIRROR_FPS_ALLOWLIST
                or not isinstance(bitrate, str) or bitrate not in MIRROR_BITRATE_ALLOWLIST):
            return {"success": False, "error": "Unsupported mirror quality settings."}

        def work():
            def _cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    args = [safe_msg, pct_val]
                    if run_id is not None:
                        args.append(json.dumps(run_id))
                    self._eval_js(f"window.onMirrorProgress && window.onMirrorProgress({', '.join(args)});")
            return bridge.start_screen_mirror(clean_serial, fps_value, str(bitrate), progress_cb=_cb)
        self._run_async(work, "onMirrorComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    def stop_screen_mirror(self):
        return bridge.stop_screen_mirror()

    @_serial_cleaned
    def capture_screen_recording(self, serial, duration=15, run_id=None):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        limit = _bounded_int(duration, 5, 180)
        if limit is None:
            return {"success": False, "error": "Recording duration must be a whole number from 5 to 180 seconds."}

        def work():
            return bridge.capture_screen_recording(clean_serial, limit)
        self._run_async(work, "onScreenRecordingComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}

    # 💀 FEATURE 9: EMERGENCY EDL & BROM UNBRICK APIS
    def detect_emergency_com_ports(self):
        return bridge.detect_emergency_com_ports()

    @_serial_cleaned
    def force_reboot_edl(self, serial):
        clean_serial = _clean_serial(serial)
        if not clean_serial:
            return {"success": False, "error": "Invalid or missing target device serial."}
        return bridge.force_reboot_edl(clean_serial)

    def inspect_unbrick_rom(self, rom_folder):
        path_err = _path_error(rom_folder, required=True)
        if path_err:
            return {"success": False, "error": path_err}
        return bridge.inspect_unbrick_rom(rom_folder)

    def flash_unbrick_rom(self, rom_folder, custom_loader=None, custom_auth=None, com_port=None, port_id=None, mem_type=None, run_id=None):
        path_err = _path_error(rom_folder, required=True)
        if path_err:
            return {"success": False, "error": path_err}
        for label, path in (("Loader", custom_loader), ("Auth", custom_auth)):
            err = _path_error(path)
            if err:
                return {"success": False, "error": f"{label}: {err}"}
        if com_port is not None and not _COM_PORT_RE.fullmatch(str(com_port).strip()):
            return {"success": False, "error": "Invalid emergency COM port."}
        if port_id is not None and (not isinstance(port_id, str) or len(port_id) > 512):
            return {"success": False, "error": "Invalid emergency port ID."}
        if mem_type is not None and (not isinstance(mem_type, str) or mem_type.lower() not in UNBRICK_MEMORY_TYPES):
            return {"success": False, "error": "Invalid memory type. Choose eMMC or UFS."}

        def work():
            def _cb(msg, pct):
                if self._window:
                    safe_msg = json.dumps(msg)
                    pct_val = json.dumps(self._safe_pct(pct))
                    args = [safe_msg, pct_val]
                    if run_id is not None:
                        args.append(json.dumps(run_id))
                    self._eval_js(f"window.onUnbrickProgress && window.onUnbrickProgress({', '.join(args)});")
            return bridge.flash_unbrick_rom(
                rom_folder, custom_loader=custom_loader, custom_auth=custom_auth,
                com_port=com_port, port_id=port_id, mem_type=mem_type, progress_cb=_cb,
            )
        self._run_async(work, "onUnbrickComplete", extra_args=[run_id] if run_id is not None else None)
        return {"status": "started", "run_id": run_id}


# =============================================================================
# 🛡️ ANTI-REVERSE ENGINEERING, ANTI-TAMPER & DECOY HONEYPOT SHIELD
# =============================================================================
def __verify_runtime_integrity__():
    """
    Active Anti-Debugging & Anti-Decompilation Sentinel:
    - Detects active Windows kernel debuggers & remote debuggers.
    - Detection is logged and non-fatal by default; termination only happens
      when ROM_FLASHER_STRICT_ANTIDEBUG=1 is explicitly set.
    """
    def _on_detection(reason):
        try:
            print(f"[ROM Flasher Tool] Anti-debug notice: {reason}", file=sys.stderr)
        except Exception:
            pass
        try:
            if os.environ.get("ROM_FLASHER_STRICT_ANTIDEBUG") == "1":
                os._exit(0)
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            # 1. Native Windows IsDebuggerPresent
            if ctypes.windll.kernel32.IsDebuggerPresent():
                _on_detection("debugger detected")
            
            # 2. Native Remote Debugger Check
            is_remote_debugged = ctypes.c_bool(False)
            ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(is_remote_debugged)
            )
            if is_remote_debugged.value:
                _on_detection("remote debugger detected")
        except Exception:
            pass

def __dump_auth_keys_and_tokens__():
    """HONEYPOT DECOY: Misleads reverse engineers if bytecode is disassembled."""
    return "TAMPER_DETECTED: CHECKSUM_MISMATCH_ENCRYPTED_SECTOR_0xDEADBEEF"

def __bypass_security_license__():
    """HONEYPOT DECOY: Emits fake corrupted instructions."""
    return [0x7F, 0x45, 0x4C, 0x46, 0x02, 0x01, 0x01, 0x00]


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def apply_dark_titlebar_to_window(window):
    """
    Applies Windows 11 / Windows 10 Immersive Dark Theme to the native title bar,
    window buttons (minimize, maximize, close), and border to perfectly match the Apple Liquid Glass theme.
    """
    def _apply():
        if sys.platform != "win32":
            return
        time.sleep(0.4)
        for _ in range(20):
            try:
                hwnd = None
                if hasattr(window, 'native') and hasattr(window.native, 'Handle'):
                    try: hwnd = int(window.native.Handle)
                    except: pass
                if not hwnd:
                    hwnd = ctypes.windll.user32.FindWindowW(None, "ROM Flasher Tool")

                if hwnd:
                    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                    DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
                    DWMWA_CAPTION_COLOR = 35  # Windows 11 caption bar color (0x00BBGGRR)
                    DWMWA_TEXT_COLOR = 36     # Windows 11 title text color
                    DWMWA_BORDER_COLOR = 34   # Windows 11 window border color

                    val = ctypes.c_int(1)
                    res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val))
                    if res != 0:
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(val), ctypes.sizeof(val))

                    # Caption color matching theme background (#080c14 -> BGR: 0x00140C08)
                    caption_color = ctypes.c_int(0x00140C08)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption_color), ctypes.sizeof(val))

                    # Title text color: Pure Crisp White (0x00FFFFFF)
                    text_color = ctypes.c_int(0x00FFFFFF)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text_color), ctypes.sizeof(val))

                    # Subtle Dark Border color
                    border_color = ctypes.c_int(0x002A1A0C)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(border_color), ctypes.sizeof(val))
                    break
            except Exception:
                pass
            time.sleep(0.3)

    threading.Thread(target=_apply, daemon=True).start()

def main():
    __verify_runtime_integrity__()
    base_dir = get_base_dir()
    html_path = os.path.join(base_dir, "ui", "index.html")

    api = Api()
    window = webview.create_window(
        title="ROM Flasher Tool",
        url=f"file://{html_path}",
        js_api=api,
        width=1280,
        height=850,
        min_size=(1020, 720),
        maximized=True, # 🔥 ALWAYS OPEN IN FULLSCREEN / MAXIMIZED
        background_color="#08090e",
        easy_drag=False
    )
    api.set_window(window)
    apply_dark_titlebar_to_window(window)
    webview.start(debug=False)

if __name__ == "__main__":
    main()
