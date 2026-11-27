import subprocess
import os
import sys
import re
import shutil
import zipfile
import tarfile
import tempfile
import time
import struct
import io
import base64
import functools
import threading
import queue
import urllib.request
import urllib.parse
import json
import hashlib
import secrets
import shlex
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Dict, Any, List, Optional

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    import msvcrt

# Application Version & GitHub Update Metadata
APP_VERSION = "v2.0.0"
GITHUB_REPO = "Rohit-Bhai-Youtube/ROM_Flasher_Tool_For_PC"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def parse_semver(tag: str) -> tuple:
    r"""Parses version strings like 'v2.0.0' or 'v2.0.0-beta.1' so stable releases sort newer than prereleases."""
    clean = re.sub(r'^[vV]', '', str(tag).strip())
    main_part, _, pre_part = clean.partition('-')
    nums = [int(x) for x in re.findall(r'\d+', main_part)] or [0]
    while len(nums) < 3:
        nums.append(0)
    is_stable = 0 if pre_part else 1
    # SemVer precedence: numeric identifiers sort below non-numeric ones;
    # non-numeric identifiers compare lexicographically, and a shorter set is lower.
    pre_ids = []
    if pre_part:
        for ident in pre_part.split('.'):
            if ident.isdigit():
                pre_ids.append((0, int(ident)))
            elif ident:
                pre_ids.append((1, ident))
    return tuple(nums[:3]) + (is_stable, tuple(pre_ids))

# Known Android / Xiaomi / Samsung / Google Bloatware & App Names
KNOWN_APP_NAMES = {
    # Xiaomi / HyperOS / POCO / Redmi
    "com.miui.videoplayer": "Mi Video",
    "com.xiaomi.mipicks": "GetApps (Xiaomi App Store)",
    "com.miui.player": "Mi Music",
    "com.miui.yellowpage": "Yellow Pages",
    "com.miui.msa.global": "MSA (MIUI System Ads)",
    "com.xiaomi.joyose": "Joyose (Game Throttle)",
    "com.miui.cloudservice": "Xiaomi Cloud",
    "com.miui.cleanmaster": "Cleaner",
    "com.mipay.wallet.in": "Mi Pay",
    "com.miui.hybrid": "Quick Apps",
    "com.android.browser": "Mi Browser",
    "com.miui.analytics": "Analytics",
    "com.miui.compass": "Mi Compass",
    "com.miui.screenrecorder": "Screen Recorder",
    "com.miui.bugreport": "Services & Feedback",
    "com.miui.calculator": "Mi Calculator",
    "com.miui.notes": "Xiaomi Notes",
    "com.miui.weather2": "Weather",
    "com.miui.gallery": "Xiaomi Gallery",
    "com.android.camera": "Camera",
    "com.android.deskclock": "Clock",
    "com.miui.personalassistant": "App Vault",
    "com.miui.daemon": "Mi Daemon",
    "com.xiaomi.glgm": "Xiaomi Games",
    "com.xiaomi.payment": "Xiaomi Payment",
    "com.xiaomi.scanner": "Scanner",
    "com.mi.health": "Mi Fitness",
    "com.mi.android.globallauncher": "POCO Launcher",
    "com.miui.home": "System Launcher",
    "com.miui.securityadd": "Security Components",
    "com.miui.securitycenter": "Security Center",
    "com.android.contacts": "Contacts & Dialer",
    "com.android.mms": "Messages",
    "com.xiaomi.simactivate.service": "SIM Activation Service",
    "com.xiaomi.midrop": "ShareMe (Mi Drop)",

    # Google
    "com.google.android.googlequicksearchbox": "Google Search App",
    "com.google.android.gm": "Gmail",
    "com.google.android.apps.photos": "Google Photos",
    "com.google.android.apps.maps": "Google Maps",
    "com.google.android.youtube": "YouTube",
    "com.google.android.apps.youtube.music": "YouTube Music",
    "com.google.android.apps.youtube.creator": "YouTube Studio",
    "com.google.android.apps.docs": "Google Drive",
    "com.google.android.videos": "Google TV",
    "com.google.android.apps.tachyon": "Google Meet",
    "com.google.android.apps.wellbeing": "Digital Wellbeing",
    "com.google.android.calendar": "Google Calendar",
    "com.google.android.keep": "Google Keep",
    "com.google.android.apps.nbu.paisa.user": "Google Pay",
    "com.android.vending": "Google Play Store",
    "com.google.android.gms": "Google Play Services",
    "com.google.android.dialer": "Phone by Google",
    "com.google.android.apps.messaging": "Messages by Google",
    "com.google.android.tts": "Google Speech Recognition",
    "com.google.android.marvin.talkback": "Android Accessibility Suite",
    "com.google.android.printservice.recommendation": "Print Service Recommendation",
    "com.google.android.devicelockcontroller": "Device Lock Controller",
    "com.google.android.gms.supervision": "Family Link Supervision",
    "com.google.ar.core": "Google Play Services for AR",
    "com.google.android.permissioncontroller": "Permission Controller",

    # Common Popular / Bloat
    "com.facebook.katana": "Facebook",
    "com.facebook.system": "Facebook App Installer",
    "com.facebook.appmanager": "Facebook App Manager",
    "com.facebook.services": "Facebook Services",
    "com.instagram.android": "Instagram",
    "com.whatsapp": "WhatsApp",
    "com.netflix.mediaclient": "Netflix",
    "com.netflix.partner.activation": "Netflix Partner",
    "com.spotify.music": "Spotify",
    "com.amazon.mShop.android.shopping": "Amazon Shopping",
    "com.flipkart.android": "Flipkart",
    "net.one97.paytm": "Paytm",
    "com.phonepe.app": "PhonePe",
    "com.ubercab": "Uber",
    "com.olacabs.customer": "Ola Cabs",
    "com.jpl.jiomart": "JioMart",
    "com.dywx.larkplayer": "Lark Player",
    "in.irisbyyes.app": "Iris by YES BANK",
    "com.paypal.android.p2pmobile": "PayPal",
    "com.azure.authenticator": "Microsoft Authenticator",
    "com.microsoft.office.officehubrow": "Microsoft 365 (Office)"
}

# Model Numbers to Commercial Codenames (Auto-resolver)
MODEL_TO_CODENAME = {
    "24095pcadg": "malachite",
    "24095pcadi": "malachite",
    "2412dpc0ai": "rodin",
    "2412dpc0ag": "rodin",
    "24129pn74c": "rodin",
    "23117rk66c": "manet",
    "2311drk48c": "duchamp",
    "23122pcd1g": "duchamp",
    "23122pcd1i": "duchamp",
    "24069pc21g": "peridot",
    "24069pc21i": "peridot",
    "23049pcd8g": "marble",
    "23049pcd8i": "marble",
    "23124rn87g": "garnet",
    "23124rn87i": "garnet",
    "2312dra50g": "garnet",
    "22101316g": "ruby",
    "22101316i": "ruby",
    "m2102j20sg": "vayu",
    "m2102j20si": "bhima"
}

def load_xiaomi_devices() -> List[Dict[str, Any]]:
    """Loads all 370 Xiaomi / POCO / Redmi devices."""
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "xiaomi_devices.json"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "xiaomi_devices.json") if hasattr(sys, "_MEIPASS") else ""
    ]
    for p in paths:
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
    return []

# Fastboot Codenames to Commercial Names
FASTBOOT_CODENAME_MAP = {
    "malachite": "POCO X7 / Redmi Note 14 Pro",
    "rodin": "POCO X7 Pro / Redmi Turbo 4",
    "marble": "POCO F5 / Redmi Note 12 Turbo",
    "duchamp": "POCO X6 Pro / Redmi K70E",
    "garnet": "POCO X6 5G / Redmi Note 13 Pro 5G",
    "peridot": "POCO F6 / Redmi Turbo 3",
    "manet": "POCO F6 Pro / Redmi K70 Pro",
    "sweet": "Redmi Note 10 Pro",
    "alioth": "POCO F3 / Redmi K40",
    "munch": "POCO F4 / Redmi K40S",
    "mondrian": "POCO F5 Pro / Redmi K60",
    "cheetah": "Google Pixel 7 Pro",
    "panther": "Google Pixel 7",
    "lynx": "Google Pixel 7a",
    "shiba": "Google Pixel 8",
    "husky": "Google Pixel 8 Pro",
    "akita": "Google Pixel 8a",
    "caiman": "Google Pixel 9 Pro",
    "tokay": "Google Pixel 9",
    "komodo": "Google Pixel 9 Pro XL",
    "star": "Xiaomi Mi 11 Pro / Ultra",
    "venus": "Xiaomi Mi 11",
    "haydn": "Xiaomi Mi 11i / K40 Pro",
    "thor": "Xiaomi 12S Ultra",
    "nuwa": "Xiaomi 13 Pro",
    "fuxi": "Xiaomi 13",
    "shennong": "Xiaomi 14 Pro",
    "houji": "Xiaomi 14",
    "aurora": "Xiaomi 14 Ultra"
}

# Known Safe Bloatware to debloat
SAFE_BLOATWARE_PACKAGES = {
    "com.miui.msa.global",
    "com.xiaomi.mipicks",
    "com.miui.videoplayer",
    "com.miui.yellowpage",
    "com.miui.hybrid",
    "com.miui.analytics",
    "com.miui.bugreport",
    "com.xiaomi.joyose",
    "com.facebook.system",
    "com.facebook.appmanager",
    "com.facebook.services",
    "com.netflix.partner.activation",
    "com.google.android.apps.wellbeing",
    "com.google.android.videos",
    "com.google.android.printservice.recommendation"
}

ROOT_RELEASES_API = {
    "KernelSU": "https://api.github.com/repos/tiann/KernelSU/releases/latest",
    "Magisk": "https://api.github.com/repos/topjohnwu/Magisk/releases/latest",
    "APatch": "https://api.github.com/repos/bmax121/APatch/releases/latest",
    "SukiSU Ultra": "https://api.github.com/repos/SukiSU-Ultra/SukiSU-Ultra/releases/latest"
}

def format_bytes(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def get_storage_dir(subfolder: str = "") -> str:
    r"""
    Centralized Desktop Storage Directory for ROM Flasher Tool:
    C:\Users\rohit\OneDrive\Desktop\ROM_Flasher_Storage
    """
    desktop_candidates = [
        os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop"),
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        r"C:\Users\rohit\OneDrive\Desktop",
        r"C:\Users\rohit\Desktop"
    ]
    base_desktop = None
    for d in desktop_candidates:
        if d and os.path.exists(d):
            base_desktop = d
            break
    if not base_desktop:
        base_desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")

    base_storage = os.path.join(base_desktop, "ROM_Flasher_Storage")
    if subfolder:
        # Never allow a caller-supplied subfolder to escape the storage root.
        raw_sub = str(subfolder).strip()
        if '..' in raw_sub or os.path.isabs(raw_sub):
            raise ValueError(f"Invalid storage subfolder: {subfolder}")
        safe_sub = re.sub(r'[^A-Za-z0-9_.-]', '_', raw_sub).strip('.')
        if not safe_sub:
            safe_sub = "Unknown"
        # Windows reserved device names can never be used as a directory name.
        first_segment = safe_sub.split('.')[0].upper()
        if (first_segment in {"CON", "PRN", "AUX", "NUL"}
                or re.fullmatch(r'(?:COM|LPT)[1-9]', first_segment or "")):
            raise ValueError(f"Invalid storage subfolder (Windows reserved name): {subfolder}")
        target = os.path.join(base_storage, safe_sub)
        base_abs = os.path.abspath(base_storage)
        target_abs = os.path.abspath(target)
        if os.path.commonpath([base_abs, target_abs]) != base_abs:
            raise ValueError(f"Invalid storage subfolder: {subfolder}")
    else:
        target = base_storage

    os.makedirs(target, exist_ok=True)
    return target


def clean_label_from_package(pkg: str, path: str = "") -> str:
    """Intelligently deduce a friendly app label from package or path."""
    if pkg in KNOWN_APP_NAMES:
        return KNOWN_APP_NAMES[pkg]
    
    if path:
        apk_name = os.path.basename(path).replace(".apk", "")
        if apk_name not in ("base", "split_config", "app"):
            spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', apk_name)
            if len(spaced) > 3 and not spaced.startswith("framework"):
                return spaced.title()

    segments = pkg.split('.')
    candidates = [s for s in segments if s not in ("com", "android", "apps", "app", "net", "org", "in", "io", "mobile")]
    if candidates:
        last = candidates[-1]
        cleaned = re.sub(r'[-_]', ' ', last)
        cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
        return cleaned.title()

    return pkg


# Boot-critical partitions are discovered from the payload manifest, then intersected
# with this allowlist. The original fixed list remains the fallback when no manifest
# is available (see auto_flash CASE A).
BOOT_CRITICAL_ALLOWLIST = (
    "boot", "init_boot", "vendor_boot", "vendor_kernel_boot", "dtbo", "dtb",
    "vbmeta", "vbmeta_system", "vbmeta_vendor", "pvmfb", "recovery",
)
DEFAULT_BOOT_CRITICAL_TARGETS = [
    "boot", "init_boot", "vendor_boot", "vendor_kernel_boot", "dtbo", "recovery",
]


def normalize_partition_name(name: str) -> str:
    """Canonical partition key: lowercase, no .img suffix, no trailing _a/_b slot suffix."""
    clean = str(name or "").strip().lower()
    if clean.endswith(".img"):
        clean = clean[:-4]
    return re.sub(r'_(a|b)$', '', clean)


class DeltaPayloadUnsupportedError(ValueError):
    """Structured failure for incremental/delta payloads (never produce partial images)."""

    def __init__(self, partition: str, op_type):
        self.code = "DELTA_PAYLOAD_UNSUPPORTED"
        self.partition = str(partition or "")
        self.op_type = op_type
        super().__init__(
            "Full OTA payload required; incremental/delta payload is not supported"
            + (f" (partition {self.partition}, operation {op_type})" if self.partition else "")
        )


class PayloadVerificationError(ValueError):
    """Structured failure when data/image hashes do not match the manifest."""

    def __init__(self, message: str, partition: str = ""):
        self.code = "PAYLOAD_VERIFICATION_FAILED"
        self.partition = str(partition or "")
        super().__init__(message)


class UnsupportedPayloadOperationError(ValueError):
    """Structured failure for operation types this extractor cannot safely decode."""

    def __init__(self, partition: str, op_type):
        self.code = "UNSUPPORTED_PAYLOAD_OPERATION"
        self.partition = str(partition or "")
        self.op_type = op_type
        super().__init__(
            f"Unsupported payload operation {op_type} in partition {self.partition}. "
            "Only full OTA REPLACE / REPLACE_XZ / REPLACE_BZ / ZERO / DISCARD operations are supported."
        )


def read_exact(stream, length: int, label: str) -> bytes:
    """Read an exact byte count or raise a clear truncation error."""
    data = stream.read(length)
    if len(data) != length:
        raise ValueError(f"Truncated payload {label}: expected {length} bytes, got {len(data)}")
    return data


def parse_payload_header(stream, stream_size: Optional[int] = None):
    """
    Shared, validated CrAU header parser. Returns (manifest, block_size, data_base, version).
    Never lets an untrusted manifest length trigger a huge allocation.
    """
    import payload_dumper.update_metadata_pb2 as um

    magic = read_exact(stream, 4, "magic header")
    if magic != b"CrAU":
        raise ValueError(f"Invalid payload.bin magic header ({magic!r})")
    version = struct.unpack(">Q", read_exact(stream, 8, "format version"))[0]
    if version not in (1, 2):
        raise ValueError(f"Unsupported payload format version: {version}")
    manifest_len = struct.unpack(">Q", read_exact(stream, 8, "manifest length"))[0]
    if manifest_len <= 0 or manifest_len > 64 * 1024 * 1024:
        raise ValueError(f"Invalid payload manifest length: {manifest_len}")
    sig_len = struct.unpack(">I", read_exact(stream, 4, "metadata signature length"))[0] if version > 1 else 0
    if sig_len > 16 * 1024 * 1024:
        raise ValueError(f"Invalid payload metadata signature length: {sig_len}")
    header_len = 4 + 8 + 8 + (4 if version > 1 else 0)
    if stream_size and header_len + manifest_len + sig_len > stream_size:
        raise ValueError("Payload header/manifest extends beyond the file")
    manifest_bytes = read_exact(stream, manifest_len, "manifest")
    if sig_len:
        read_exact(stream, sig_len, "metadata signature")
    dam = um.DeltaArchiveManifest()
    dam.ParseFromString(manifest_bytes)
    block_size = int(dam.block_size or 0)
    if block_size <= 0 or block_size > 16 * 1024 * 1024:
        raise ValueError(f"Invalid payload block size: {block_size}")
    return dam, block_size, header_len + manifest_len + sig_len, version


def payload_is_delta(dam) -> bool:
    """AOSP canonical delta markers: minor_version != 0 or partial_update == True."""
    try:
        return int(getattr(dam, "minor_version", 0) or 0) != 0 or bool(getattr(dam, "partial_update", False))
    except Exception:
        return False


def payload_op_types(um) -> Dict[str, int]:
    """Take enum numbers from the protobuf descriptor, never hard-code them."""
    try:
        op = um.InstallOperation
        return {
            "REPLACE": int(op.REPLACE),
            "REPLACE_BZ": int(op.REPLACE_BZ),
            "REPLACE_XZ": int(op.REPLACE_XZ),
            "ZERO": int(op.ZERO),
            "DISCARD": int(op.DISCARD),
        }
    except Exception as e:
        raise ValueError(f"Payload operation enums are unavailable: {e}")


def safe_partition_key(name: str) -> str:
    """One canonical, filesystem-safe key for UI selection, cache and output files."""
    key = re.sub(r'[^A-Za-z0-9._-]', '_', normalize_partition_name(name))
    if not key or key in (".", "..") or "/" in key or "\\" in key:
        return "partition"
    return key


def choose_payload_entry(zf: zipfile.ZipFile) -> Optional[str]:
    """Prefer the shallowest/root payload.bin when a ZIP has nested/stale copies."""
    matches = [n for n in zf.namelist() if is_payload_entry(n)]
    if not matches:
        return None
    return min(matches, key=lambda n: (n.count("/"), len(n), n))


def list_payload_partition_names(source_path: str) -> List[str]:
    """Read only the payload manifest and return canonical partition keys."""
    def _from_stream(pf, size=None):
        dam, _, _, _ = parse_payload_header(pf, size)
        return list(dict.fromkeys(safe_partition_key(p.partition_name) for p in dam.partitions))

    if is_split_archive_part(str(source_path)):
        raise ValueError("Split archive detected. Join the .001/.002 parts before using Payload Dumper.")
    if zipfile.is_zipfile(source_path):
        with zipfile.ZipFile(source_path, "r") as zf:
            entry = choose_payload_entry(zf)
            if not entry:
                raise ValueError("payload.bin not found inside ZIP archive")
            with zf.open(entry) as pf:
                return _from_stream(pf, zf.getinfo(entry).file_size)
    with open(source_path, "rb") as pf:
        return _from_stream(pf, os.path.getsize(source_path))


def rom_requests_avb_disable(*paths) -> bool:
    """
    Only disarm vbmeta AVB when the ROM itself asks for it, or when the user opts in
    via ROM_FLASHER_DISABLE_AVB=1. Never disable AVB unconditionally.
    """
    if str(os.environ.get("ROM_FLASHER_DISABLE_AVB", "")).strip().lower() in ("1", "true", "yes"):
        return True

    needles = ("--disable-verity", "--disable-verification")
    limit = 256 * 1024

    def _text_has_flags(text: str) -> bool:
        low = (text or "").lower()
        return any(n in low for n in needles)

    def _check_file(path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                return _text_has_flags(fh.read(limit))
        except Exception:
            return False

    def _payload_manifest_has_flags(pf) -> bool:
        try:
            if pf.read(4) != b"CrAU":
                return False
            ver = struct.unpack(">Q", pf.read(8))[0]
            manifest_len = struct.unpack(">Q", pf.read(8))[0]
            if ver > 1:
                pf.read(4)
            # Untrusted payload bytes must not drive an unbounded allocation.
            if manifest_len <= 0 or manifest_len > 64 * 1024 * 1024:
                return False
            return _text_has_flags(pf.read(manifest_len).decode("latin-1", "ignore"))
        except Exception:
            return False

    for path in paths:
        if not path or not os.path.exists(path):
            continue
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in files:
                    if f.lower().endswith((".bat", ".cmd", ".sh")) and _check_file(os.path.join(root, f)):
                        return True
        elif str(path).lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    for n in zf.namelist():
                        low_n = n.lower()
                        if low_n.endswith((".bat", ".cmd", ".sh")):
                            with zf.open(n) as fh:
                                if _text_has_flags(fh.read(limit).decode("utf-8", "ignore")):
                                    return True
                        if is_payload_entry(low_n):
                            with zf.open(n) as pf:
                                if _payload_manifest_has_flags(pf):
                                    return True
            except Exception:
                pass
        elif str(path).lower().endswith(".bin"):
            try:
                with open(path, "rb") as pf:
                    if _payload_manifest_has_flags(pf):
                        return True
            except Exception:
                pass
        elif str(path).lower().endswith((".bat", ".cmd", ".sh")):
            if _check_file(path):
                return True
    return False


def extract_payload_images(source_path: str, out_dir: str, target_names: Optional[List[str]] = None,
                           progress_cb=None, cancel_event=None, details_out: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """
    Extract full-OTA partitions with manifest hash verification, atomic writes,
    bounded ZERO writes and structured failures. No external enlighten/fileno deps.
    """
    import lzma, bz2
    import payload_dumper.update_metadata_pb2 as um
    os.makedirs(out_dir, exist_ok=True)
    extracted: List[str] = []
    details: List[Dict[str, Any]] = []
    HOLE = (1 << 64) - 1

    def _emit(msg: str, pct=None):
        if progress_cb:
            try:
                progress_cb(msg, pct)
            except Exception:
                pass

    def _check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Extraction cancelled")

    def _verify_blob(raw: bytes, op, p_name: str):
        expected = bytes(getattr(op, "data_sha256_hash", b"") or b"")
        if expected and hashlib.sha256(raw).digest() != expected:
            raise PayloadVerificationError(
                f"Payload data hash mismatch in partition {p_name} (operation {op.type}). "
                "The payload is corrupt or incomplete.", p_name)

    def _verify_image(path: str, p, key: str):
        expected = bytes(getattr(getattr(p, "new_partition_info", None), "hash", b"") or b"")
        if not expected:
            return
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
                h.update(chunk)
        if h.digest() != expected:
            raise PayloadVerificationError(
                f"Extracted image hash mismatch for {key}.img. The payload data did not match its manifest.", key)

    def _dump(pf, stream_size=None):
        dam, block_sz, data_base, _version = parse_payload_header(pf, stream_size)
        if payload_is_delta(dam):
            raise DeltaPayloadUnsupportedError("", "manifest(minor_version/partial_update)")

        consts = payload_op_types(um)
        replace_ops = {consts["REPLACE"], consts["REPLACE_BZ"], consts["REPLACE_XZ"]}
        zero_ops = {consts["ZERO"], consts["DISCARD"]}
        supported_ops = replace_ops | zero_ops

        part_list = list(dam.partitions)
        if target_names:
            wanted = {safe_partition_key(t) for t in target_names}
            part_list = [p for p in part_list if safe_partition_key(p.partition_name) in wanted]
        # De-duplicate slot variants so boot_a/boot_b cannot overwrite one boot.img.
        dedup: Dict[str, Any] = {}
        for p in part_list:
            dedup.setdefault(safe_partition_key(p.partition_name), p)
        part_list = list(dedup.values())

        # Validate everything before creating any destination file.
        for p_chk in part_list:
            for op_chk in p_chk.operations:
                if op_chk.src_extents or op_chk.type not in supported_ops:
                    if op_chk.src_extents or op_chk.type in (
                        getattr(um.InstallOperation, "SOURCE_COPY", -1),
                        getattr(um.InstallOperation, "SOURCE_BSDIFF", -1),
                        getattr(um.InstallOperation, "BSDIFF", -1),
                        getattr(um.InstallOperation, "PUFFDIFF", -1),
                        getattr(um.InstallOperation, "BROTLI_BSDIFF", -1),
                        getattr(um.InstallOperation, "ZUCCHINI", -1),
                    ):
                        raise DeltaPayloadUnsupportedError(p_chk.partition_name, op_chk.type)
                    raise UnsupportedPayloadOperationError(p_chk.partition_name, op_chk.type)
                total = sum(int(ext.num_blocks) * block_sz for ext in op_chk.dst_extents)
                if op_chk.dst_length and total != int(op_chk.dst_length):
                    raise ValueError(
                        f"Payload partition {p_chk.partition_name}: extent size {total} differs "
                        f"from declared dst_length {op_chk.dst_length}")
                for ext in op_chk.dst_extents:
                    if int(ext.num_blocks) < 0 or int(ext.start_block) < 0:
                        raise ValueError(f"Invalid extent in payload partition {p_chk.partition_name}")

        total_p = len(part_list)
        for idx, p in enumerate(part_list):
            _check_cancel()
            p_name = p.partition_name
            key = safe_partition_key(p_name)
            _emit(f"Extracting {key}.img ({idx + 1}/{total_p})...", 35 + int(((idx + 1) / max(1, total_p)) * 20))
            out_img = os.path.join(out_dir, f"{key}.img")
            tmp_img = out_img + ".tmp"
            declared = int(getattr(getattr(p, "new_partition_info", None), "size", 0) or 0)
            try:
                with open(tmp_img, "wb") as dst:
                    if declared > 0:
                        dst.truncate(declared)  # creates sparse holes safely
                    for op in p.operations:
                        _check_cancel()
                        if op.type in zero_ops:
                            for ext in op.dst_extents:
                                if int(ext.start_block) == HOLE:
                                    continue
                                remaining = int(ext.num_blocks) * block_sz
                                dst.seek(int(ext.start_block) * block_sz)
                                while remaining > 0:
                                    _check_cancel()
                                    n = min(8 * 1024 * 1024, remaining)
                                    dst.write(b"\x00" * n)
                                    remaining -= n
                            continue

                        if op.type not in replace_ops or op.data_length <= 0:
                            continue
                        pf.seek(data_base + int(op.data_offset))
                        raw = pf.read(int(op.data_length))
                        if len(raw) != int(op.data_length):
                            raise ValueError(f"Payload partition {p_name}: truncated data blob (operation {op.type})")
                        _verify_blob(raw, op, p_name)
                        if op.type == consts["REPLACE_XZ"]:
                            data = lzma.LZMADecompressor().decompress(raw)
                        elif op.type == consts["REPLACE_BZ"]:
                            data = bz2.BZ2Decompressor().decompress(raw)
                        else:
                            data = raw
                        data_off = 0
                        for ext in op.dst_extents:
                            _check_cancel()
                            chunk_len = int(ext.num_blocks) * block_sz
                            if chunk_len <= 0:
                                continue
                            chunk = data[data_off:data_off + chunk_len]
                            if len(chunk) < chunk_len:
                                raise ValueError(
                                    f"Payload partition {p_name}: decompressed data is shorter than its destination extents")
                            if int(ext.start_block) != HOLE:
                                dst.seek(int(ext.start_block) * block_sz)
                                dst.write(chunk)
                            data_off += chunk_len

                actual = os.path.getsize(tmp_img)
                if declared > 0 and actual != declared:
                    raise ValueError(f"Extracted {key}.img size {actual} differs from manifest size {declared}")
                _verify_image(tmp_img, p, key)
                os.replace(tmp_img, out_img)
            except Exception:
                try:
                    if os.path.exists(tmp_img):
                        os.remove(tmp_img)
                except Exception:
                    pass
                raise
            extracted.append(out_img)
            h = hashlib.sha256()
            with open(out_img, "rb") as fh:
                for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
                    h.update(chunk)
            details.append({"name": p_name, "key": key, "path": out_img,
                            "size": actual, "sha256": h.hexdigest()})

        if details_out is not None:
            details_out.extend(details)
        return extracted

    if is_split_archive_part(str(source_path)):
        raise ValueError("Split archive detected. Join the .001/.002 parts before using Payload Dumper.")

    if zipfile.is_zipfile(source_path):
        with zipfile.ZipFile(source_path, "r") as zf:
            entry = choose_payload_entry(zf)
            if not entry:
                raise ValueError("payload.bin not found inside ZIP archive")
            info = zf.getinfo(entry)
            if info.compress_type == zipfile.ZIP_STORED:
                with zf.open(entry) as pf:
                    return _dump(pf, info.file_size)
            # Deflated payload entries make random seeks extremely slow and disable
            # CRC checking after seek. Stream once to a temp file, then verify hashes.
            fd, tmp_payload = tempfile.mkstemp(prefix="rf_payload_stream_", suffix=".bin")
            os.close(fd)
            try:
                with zf.open(entry) as src, open(tmp_payload, "wb") as dst:
                    shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
                with open(tmp_payload, "rb") as pf:
                    return _dump(pf, os.path.getsize(tmp_payload))
            finally:
                try:
                    os.remove(tmp_payload)
                except Exception:
                    pass

    with open(source_path, "rb") as pf:
        return _dump(pf, os.path.getsize(source_path))


def clean_fastboot_log(output: str) -> List[str]:
    """
    Cleans fastboot stdout/stderr by collapsing only known harmless F2FS/debug noise.
    Any line containing FAILED, failed or error: is preserved verbatim for the user.
    """
    clean = []
    raw_lines = re.split(r'[\r\n]+', output or '')
    for line in raw_lines:
        raw = line.strip()
        if not raw or raw in ['""', "''", '"', "'"]:
            continue
        # Real failures are never filtered or collapsed: show the raw line to the user.
        raw_low = raw.lower()
        if 'failed' in raw_low or 'error:' in raw_low:
            clean.append(raw)
            continue
        sub_parts = re.split(r'(?=(?:Sending|Writing|Erasing|Formatting|Finished|OKAY|FAILED))', line)
        for p in sub_parts:
            s = p.strip()
            if not s or s in ['""', "''", '"', "'"]:
                continue
            low = s.lower()
            if 'failed' in low or 'error:' in low:
                clean.append(s)
                continue
            # Only known harmless F2FS/debug noise is collapsed here.
            if any(k in low for k in [
                'f2fs', 'mkfs', 'info:', 'debug level', 'writing quota', 'writing root inode',
                'writing cp', 'writing nat', 'writing sit', 'writing segment', 'writing super block',
                'filling sit', 'filling nat', 'fetching super', 'fetch:super',
                'skip copying', 'format version', 'overprovision ratio', 'default dentry',
                'main segment', 'block size', 'add quota', 'trim is disabled',
                'set conf for android', 'quota inode', 'nat root', 'zone aligned',
                'f2fs-tools', 'quota data'
            ]) or low.startswith('[f2fs') or (low.startswith('[') and 'f2fs' in low):
                continue
            clean.append(s)

    final_lines = []
    curr = ''
    for item in clean:
        if item.startswith('Sending') or item.startswith('Erasing') or item.startswith('Formatting'):
            if curr: final_lines.append(curr)
            curr = item
        elif item.startswith('Writing'):
            if curr: final_lines.append(curr)
            curr = item
        elif item.startswith('OKAY') or item.startswith('FAILED'):
            if curr:
                curr = f"{curr} {item}"
                final_lines.append(curr)
                curr = ''
            else:
                final_lines.append(item)
        elif item.startswith('Finished'):
            if curr: final_lines.append(curr)
            curr = ''
            final_lines.append(item)
        else:
            if curr: final_lines.append(curr)
            curr = ''
            final_lines.append(item)
    if curr:
        final_lines.append(curr)
    return [l for l in final_lines if l.strip()]


def fastboot_result_ok(res: Dict[str, Any]) -> bool:
    """
    Fastboot may print FAILED / error: / remote: ... and still exit 0 on some
    bootloaders. Never trust the return code alone for mutating operations.
    """
    if not isinstance(res, dict) or not res.get("success"):
        return False
    raw = f"{res.get('stdout', '')}\n{res.get('stderr', '')}\n{res.get('output', '')}"
    if re.search(r'\bFAILED\b|\berror\s*:', raw, re.I):
        return False
    if re.search(r'remote:\s*(?!\s*OKAY\b)', raw, re.I):
        return False
    return True


def fastboot_step_ok(res) -> bool:
    """Alias used by 1-click flows: never accept exit-code-only fastboot success."""
    return fastboot_result_ok(res)


def fastboot_devices_has_serial(res, serial: str) -> bool:
    """Exact serial token check; a longer serial containing ours must not match."""
    if not isinstance(res, dict):
        return False
    text = f"{res.get('stdout', '')}\n{res.get('output', '')}"
    return bool(re.search(rf'(?m)^\s*{re.escape(str(serial or ""))}\s+\S+', text, re.I))


# ---------------------------------------------------------------------------
# ADB / package-manager safety helpers (APK installer + debloater only).
# These intentionally mirror fastboot_result_ok(): exit code 0 is not enough.
# ---------------------------------------------------------------------------
_ADB_FAILURE_RE = re.compile(
    r'\bFailure\b|\bFAILED\b|INSTALL_FAILED|DELETE_FAILED|'
    r'SecurityException|Permission\s+denied|permission\s+denial|'
    r'\berror\s*:|\bdevice\s+(?:not\s+found|offline)\b|'
    r'\bunknown\s+(?:option|command|flag)\b|\bunrecognized\b',
    re.I
)


def adb_output_has_error(res: Dict[str, Any]) -> bool:
    """True when adb/pm printed a failure even if the process exited 0."""
    if not isinstance(res, dict):
        return True
    raw = f"{res.get('stdout', '')}\n{res.get('stderr', '')}\n{res.get('output', '')}"
    return bool(_ADB_FAILURE_RE.search(raw))


def adb_result_ok(res: Dict[str, Any], positive: Optional[Any] = None) -> bool:
    """
    Never trust an ADB exit code alone. `positive` is an optional regex (or
    list of regexes) that must also appear, e.g. r'\\bSuccess\\b' for installs.
    """
    if not isinstance(res, dict) or not res.get("success"):
        return False
    if adb_output_has_error(res):
        return False
    if positive:
        raw = f"{res.get('stdout', '')}\n{res.get('stderr', '')}\n{res.get('output', '')}"
        patterns = positive if isinstance(positive, (list, tuple)) else [positive]
        if not any(re.search(str(p), raw, re.I) for p in patterns):
            return False
    return True


_PATCH_SUCCESS_RE = re.compile(
    r'new-boot\.img|patched|patch\s+(?:done|complete(?:d)?|success(?:ful)?)|'
    r'\bsuccess(?:ful)?\b|\bsaved\b|\bgenerated\b|\bdone\b|\bcomplete(?:d)?\b',
    re.I
)


def patch_output_has_success(res: Dict[str, Any]) -> bool:
    """A clean exit alone must not be treated as proof that boot patching worked."""
    if not isinstance(res, dict):
        return False
    raw = f"{res.get('stdout', '')}\n{res.get('stderr', '')}\n{res.get('output', '')}"
    return bool(_PATCH_SUCCESS_RE.search(raw))


_PACKAGE_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$')


def safe_package_name(pkg: Any) -> Optional[str]:
    """Only accept real Android package names before they reach a device shell."""
    value = str(pkg or "").strip()
    return value if _PACKAGE_NAME_RE.fullmatch(value) else None


def sanitize_package_list(pkg_list: Any) -> tuple:
    """Return (valid deduplicated packages, rejected values)."""
    valid: List[str] = []
    invalid: List[str] = []
    for item in (pkg_list or []):
        pkg = safe_package_name(item)
        if not pkg:
            if str(item or "").strip():
                invalid.append(str(item).strip()[:120])
        elif pkg not in valid:
            valid.append(pkg)
    return valid, invalid


def apk_flag_unsupported(res: Dict[str, Any]) -> bool:
    """Retry with fewer flags only when the flag itself was rejected."""
    if not isinstance(res, dict):
        return False
    raw = f"{res.get('stdout', '')}\n{res.get('stderr', '')}\n{res.get('output', '')}"
    return bool(re.search(
        r'unknown\s+(?:option|flag)|unrecognized\s+option|invalid\s+option|'
        r'not\s+supported|requires\s+API|bypass-low-target-sdk',
        raw, re.I
    ))


def safe_extract_apk_archive(archive_path: str, dest_dir: str,
                             max_entries: int = 500,
                             max_uncompressed: int = 512 * 1024 * 1024) -> None:
    """Extract an APK container with zip-slip, encrypted-entry and size guards."""
    dest_root = os.path.realpath(dest_dir)
    with zipfile.ZipFile(archive_path, 'r') as zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise ValueError(f"Archive has too many entries ({len(infos)} > {max_entries}).")
        total = sum(int(i.file_size) for i in infos if not i.is_dir())
        if total > max_uncompressed:
            raise ValueError(f"Archive is too large to unpack safely ({format_bytes(total)}).")
        for info in infos:
            if info.flag_bits & 0x1:
                raise ValueError(f"Encrypted archive entry is not supported: {info.filename}")
            target = os.path.realpath(os.path.join(dest_root, info.filename))
            try:
                inside = os.path.commonpath([dest_root, target]) == dest_root
            except ValueError:
                inside = False
            if not inside:
                raise ValueError(f"Unsafe archive path rejected: {info.filename}")
        zf.extractall(dest_root)


def collect_install_apks(root_dir: str) -> List[str]:
    """
    Collect deduplicated APKs with base.apk first. If an `apks/` folder exists,
    only that folder is used so backup copies/media never create duplicate splits.
    """
    preferred = os.path.join(root_dir, "apks")
    scan_root = preferred if os.path.isdir(preferred) else root_dir
    found: List[str] = []
    for current, _, files in os.walk(scan_root):
        for name in files:
            if name.lower().endswith(".apk"):
                found.append(os.path.realpath(os.path.join(current, name)))

    seen_hash = set()
    unique: List[str] = []
    for path in found:
        try:
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        except Exception:
            continue
        if digest in seen_hash:
            continue
        seen_hash.add(digest)
        unique.append(path)
    unique.sort(key=lambda p: (0 if os.path.basename(p).lower() == "base.apk" else 1, p.lower()))
    return unique


def looks_like_fastboot_raw_image(path: str) -> bool:
    """Distinguish a raw Android fastboot image from an Odin .bin package."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
        if len(head) < 4:
            return False
        # Android sparse image magic: little-endian 0xed26ff3a.
        if head[:4] == b"\x3a\xff\x26\xed":
            return True
        # Raw ext4 superblock magic lives at byte 0x38.
        with open(path, "rb") as fh:
            fh.seek(0x38)
            return fh.read(2) == b"\x53\xef"
    except Exception:
        return False


def shallowest_path(existing: Optional[str], candidate: str) -> str:
    """Prefer the least-nested duplicate so images/ doesn't shadow the root file."""
    if not existing:
        return candidate
    def rank(p: str):
        norm = str(p).replace("\\", "/")
        return (norm.count("/"), len(norm), norm.lower())
    return candidate if rank(candidate) < rank(existing) else existing


def validate_range_response(resp, expected_start: int, expected_end: int) -> int:
    """Require HTTP 206 and an exact Content-Range before consuming a ranged body."""
    status = getattr(resp, "status", None) or getattr(resp, "code", None)
    if status != 206:
        raise OSError(f"Expected HTTP 206 Partial Content, got {status}")
    content_range = (resp.headers.get("Content-Range") or "").strip()
    m = re.match(r'bytes\s+(\d+)-(\d+)/(\d+)', content_range, re.I)
    if not m:
        raise OSError(f"Invalid/missing Content-Range header: {content_range!r}")
    got_start, got_end, total = (int(x) for x in m.groups())
    if got_start != expected_start or got_end != expected_end:
        raise OSError(f"Content-Range mismatch: got {got_start}-{got_end}/{total}, "
                      f"expected {expected_start}-{expected_end}")
    return total


class HttpRangeFile(io.RawIOBase):
    """
    High-performance seekable remote HTTP Range file stream.
    Features intelligent block-level LRU caching (512 KB blocks) so ZIP/metadata reads
    execute in 0ms without redundant TLS roundtrips.
    """
    def __init__(self, url: str, block_size: int = 512 * 1024, timeout: int = 25):
        self.url = url
        self.block_size = block_size
        self.timeout = timeout
        self.pos = 0
        self._cache = {}
        req = urllib.request.Request(url, headers={'Range': 'bytes=0-0', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = getattr(r, "status", None)
            if status != 206:
                raise ValueError(f"HTTP Range requests not supported (expected 206, got {status})")
            cr = r.headers.get('Content-Range') or ''
            m = re.match(r'bytes\s+(\d+)-(\d+)/(\d+)', cr.strip(), re.IGNORECASE)
            if not m:
                raise ValueError(f"Invalid/missing Content-Range header: {cr!r}")
            start = int(m.group(1))
            if start != 0:
                raise ValueError(f"Expected Content-Range to start at offset 0, got {start}")
            self.total_size = int(m.group(3))

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.total_size + offset
        self.pos = max(0, min(self.pos, self.total_size))
        return self.pos

    def tell(self) -> int:
        return self.pos

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def _get_block(self, block_idx: int) -> bytes:
        if block_idx in self._cache:
            return self._cache[block_idx]
        b_start = block_idx * self.block_size
        b_end = min(self.total_size - 1, b_start + self.block_size - 1)
        expected_len = b_end - b_start + 1
        req = urllib.request.Request(self.url, headers={'Range': f'bytes={b_start}-{b_end}', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            status = getattr(r, "status", None)
            if status != 206:
                raise OSError(f"Expected HTTP 206 Partial Content, got {status}")
            cr = r.headers.get('Content-Range') or ''
            m = re.match(r'bytes\s+(\d+)-(\d+)/(\d+)', cr.strip(), re.IGNORECASE)
            if not m:
                raise OSError(f"Invalid/missing Content-Range for block {block_idx}: {cr!r}")
            got_start, got_end, got_total = (int(x) for x in m.groups())
            if got_start != b_start or got_end != b_end or got_total != self.total_size:
                raise OSError(f"Content-Range mismatch for block {block_idx}: got {got_start}-{got_end}/{got_total}, expected {b_start}-{b_end}/{self.total_size}")
            data = r.read(expected_len + 1)
        if len(data) != expected_len:
            raise OSError(f"Short range read for block {block_idx}: expected {expected_len} bytes, got {len(data)}")
        if len(self._cache) > 48:
            self._cache.pop(next(iter(self._cache)))
        self._cache[block_idx] = data
        return data

    def readinto(self, b) -> int:
        if self.pos >= self.total_size:
            return 0
        total_read = 0
        req_len = len(b)
        while total_read < req_len and self.pos < self.total_size:
            block_idx = self.pos // self.block_size
            offset_in_block = self.pos % self.block_size
            block_data = self._get_block(block_idx)
            available = len(block_data) - offset_in_block
            wanted = min(req_len - total_read, available, self.total_size - self.pos)
            if wanted <= 0:
                raise OSError(f"Short block {block_idx} while reading remote file (offset {self.pos})")
            b[total_read : total_read + wanted] = block_data[offset_in_block:offset_in_block + wanted]
            total_read += wanted
            self.pos += wanted
        return total_read


# ---------------------------------------------------------------------------
# Custom / ported ROM format + script helpers
# ---------------------------------------------------------------------------
SCRIPT_EXTS = (".bat", ".cmd", ".sh")
PAYLOAD_BASENAME = "payload.bin"
_RECOVERY_INSTALL_DIR = "meta-inf/com/google/android"
_KNOWN_A_ONLY_CODENAMES = frozenset({
    "kenzo", "kate", "cancro", "rolex", "tissot", "gemini", "santoni", "hemi", "lavender",
})


class UnsupportedPackageFormatError(ValueError):
    """Precise failure when no unpacker exists for a package format."""

    def __init__(self, ext: str, detail: str = ""):
        self.code = "UNSUPPORTED_PACKAGE_FORMAT"
        self.extension = str(ext or "")
        self.detail = detail
        super().__init__(f"unsupported package format: {self.extension}" + (f" ({detail})" if detail else ""))


class StorageSetupError(RuntimeError):
    """Structured storage failure carrying ROM context."""

    def __init__(self, subfolder: str, rom_context: str = "", cause=None):
        self.code = "STORAGE_SETUP_FAILED"
        self.result = {
            "success": False,
            "error": f"Storage setup failed for '{os.path.basename(str(rom_context or 'ROM'))}' "
                     f"in '{subfolder or 'ROM_Flasher_Storage'}': {cause}",
            "rom_context": str(rom_context or ""),
            "subfolder": subfolder,
        }
        super().__init__(self.result["error"])


def storage_path_for(rom_context: str, subfolder: str = "") -> Dict[str, Any]:
    """Wrap get_storage_dir/makedirs/stat into one structured, ROM-aware result."""
    try:
        path = get_storage_dir(subfolder)
        os.makedirs(path, exist_ok=True)
        st = os.stat(path)
        return {"success": True, "path": path, "size": st.st_size, "mtime": int(st.st_mtime)}
    except Exception as e:
        if isinstance(e, StorageSetupError):
            return e.result
        return StorageSetupError(subfolder, rom_context, e).result


def is_payload_entry(name: str) -> bool:
    """Exact basename check: payload.bin.bak / payload.bin.old are not payload.bin."""
    return os.path.basename(str(name or "").replace("\\", "/")).lower() == PAYLOAD_BASENAME


def is_split_archive_part(name: str) -> bool:
    low = str(name or "").lower()
    return low.endswith(".001") or bool(re.search(r'\.(?:zip|tar\.gz|tar)\.\d{3}$', low))


def split_archive_prefix(name: str) -> str:
    return re.sub(r'\.\d{3}$', '', str(name or ""), flags=re.I)


def is_tar_kind(kind: str) -> bool:
    return str(kind or "").lower() in ("tar", "tgz", "tar.gz", "tar.md5")


def archive_info(name: str):
    """Return (kind, extension) for supported/recognized package names."""
    low = str(name or "").lower()
    if is_split_archive_part(low):
        return "split", os.path.splitext(low)[1] or ".001"
    for ext in (".tar.gz", ".tar.md5", ".tgz", ".tar", ".zip", ".7z", ".rar", ".bin", ".ofp"):
        if low.endswith(ext):
            return ext.lstrip("."), ext
    return None, os.path.splitext(low)[1]


def script_index(root: str) -> Dict[str, str]:
    """Recursive lowercase-basename -> full-path index of flash scripts (shallowest wins)."""
    found: Dict[str, str] = {}
    if not os.path.isdir(root):
        return found
    for cur, _, files in os.walk(root):
        for f in files:
            low = f.lower()
            if low.startswith("rom_flasher_") or not low.endswith(SCRIPT_EXTS):
                continue
            key = low
            found[key] = shallowest_path(found.get(key), os.path.join(cur, f))
    return found


def image_index(root: str) -> Dict[str, str]:
    """Recursive basename -> full-path index of raw partition images (shallowest wins)."""
    found: Dict[str, str] = {}
    if not os.path.isdir(root):
        return found
    for cur, _, files in os.walk(root):
        for f in files:
            low = f.lower()
            if low.endswith((".img", ".img.xz", ".img.gz", ".bin")) and (
                    not low.endswith(".bin") or looks_like_fastboot_raw_image(os.path.join(cur, f))):
                full = os.path.join(cur, f)
                found[low] = shallowest_path(found.get(low), full)
                found[os.path.splitext(low)[0] + ".img"] = shallowest_path(
                    found.get(os.path.splitext(low)[0] + ".img"), full)
                # Slot-suffixed images must remain findable by canonical name too.
                canon = normalize_partition_name(f) + ".img"
                found[canon] = shallowest_path(found.get(canon), full)
    return found


def find_payload_in(root: str) -> Optional[str]:
    if not os.path.isdir(root):
        return None
    for cur, _, files in os.walk(root):
        for f in files:
            if is_payload_entry(f):
                return os.path.abspath(os.path.join(cur, f))
    return None


def dominant_script_dir(root: str) -> str:
    """Work directory = where most real flash scripts live, not the last file walked."""
    paths = list(script_index(root).values())
    if not paths:
        return root
    counts = Counter(os.path.normcase(os.path.dirname(p)) for p in paths)
    best_dir = counts.most_common(1)[0][0]
    return next((os.path.dirname(p) for p in paths
                 if os.path.normcase(os.path.dirname(p)) == best_dir), root)


def dominant_image_dir(root: str) -> str:
    """Work directory when raw images exist: folder holding the most images."""
    paths = list(image_index(root).values())
    if not paths:
        return root
    counts = Counter(os.path.normcase(os.path.dirname(p)) for p in paths)
    best_dir = counts.most_common(1)[0][0]
    return next((os.path.dirname(p) for p in paths
                 if os.path.normcase(os.path.dirname(p)) == best_dir), root)


def is_recovery_zip(path: str) -> bool:
    """Custom recovery flashable ZIP: route to ADB sideload, never fastboot scripts."""
    if not str(path or "").lower().endswith(".zip") or not os.path.isfile(path):
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                low = name.lower().replace("\\", "/").lstrip("/")
                if low.startswith(_RECOVERY_INSTALL_DIR + "/") and low.endswith(("update-binary", "updater-script")):
                    return True
    except Exception:
        pass
    return False


def source_identity(path: str, include_hash: bool = True, strong: bool = False) -> str:
    """Cache key: path + size + mtime; strong=True adds ns timestamps/inode and a content hash."""
    try:
        st = os.stat(path)
        ident = f"{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{int(st.st_mtime)}"
        if strong:
            ident += f"|{st.st_mtime_ns}|{st.st_ctime_ns}|{st.st_ino}"
        if include_hash and (strong or (0 < st.st_size <= 128 * 1024 * 1024)):
            try:
                h = hashlib.sha256()
                with open(path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                ident += "|" + h.hexdigest()
            except Exception:
                pass
        return ident
    except Exception:
        return os.path.normcase(os.path.abspath(path))


def cache_key_for(path: str) -> str:
    """Strong, content-derived key: same-size/same-second replacements cannot collide."""
    return hashlib.sha256(source_identity(path, strong=True).encode("utf-8", "replace")).hexdigest()[:16]


def read_cache_marker(marker_path: str, identity: str) -> bool:
    try:
        with open(marker_path, "r", encoding="utf-8") as mf:
            return mf.read().strip() == identity
    except Exception:
        return False


def write_cache_marker(marker_path: str, identity: str):
    with open(marker_path, "w", encoding="utf-8") as mf:
        mf.write(identity)


def verify_rom_archive(path: str):
    """Best-effort integrity test before a .part file is renamed into place."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as zf:
                bad = zf.testzip()
                return (bad is None, "" if bad is None else f"corrupt ZIP member: {bad}")
        if tarfile.is_tarfile(path):
            with tarfile.open(path, "r:*") as tf:
                for _ in tf:
                    pass
            return True, ""
    except Exception as e:
        return False, str(e)
    return True, ""  # unknown container: no cheap verifier available


def _find_unpacker(names):
    for tool in names:
        found = shutil.which(tool)
        if found:
            return found
    for base in (r"C:\Program Files\7-Zip", r"C:\Program Files (x86)\7-Zip", r"C:\Program Files\WinRAR"):
        for tool in names:
            cand = os.path.join(base, tool)
            if os.path.exists(cand):
                return cand
    return None


def _split_parts(path: str) -> List[str]:
    prefix = split_archive_prefix(path)
    folder = os.path.dirname(os.path.abspath(prefix)) or "."
    stem = os.path.basename(prefix) + "."
    pattern = re.compile(r'^' + re.escape(stem) + r'(\d{3})$', re.I)
    parts = []
    for f in os.listdir(folder):
        m = pattern.match(f)
        if m:
            parts.append((int(m.group(1)), os.path.join(folder, f)))
    if not parts:
        raise ValueError(f"No split archive parts found for {os.path.basename(path)}")
    parts.sort()
    numbers = [n for n, _ in parts]
    if numbers != list(range(1, len(parts) + 1)):
        raise ValueError(f"Incomplete split archive sequence: {numbers}")
    return [p for _, p in parts]


def extract_rom_archive(rom_path: str, dest: str, progress_cb=None) -> str:
    """Extract zip/tar/tar.md5/split/7z/rar into dest; precise failure for unknown tools."""
    def _cb(msg, pct=None):
        if progress_cb:
            try:
                progress_cb(msg, pct)
            except Exception:
                pass  # UI callback must never abort a multi-GB extraction

    original_path = rom_path
    kind, ext = archive_info(rom_path)
    temp_dir = None
    try:
        if kind == "split":
            prefix = split_archive_prefix(rom_path)
            temp_dir = tempfile.mkdtemp(prefix="rom_split_")
            joined = os.path.join(temp_dir, os.path.basename(prefix) or "joined_archive")
            parts = _split_parts(rom_path)
            with open(joined, "wb") as out:
                for idx, part in enumerate(parts, 1):
                    with open(part, "rb") as fh:
                        shutil.copyfileobj(fh, out, 1024 * 1024)
                    _cb(f"Joining split archive part {idx}/{len(parts)}...", 20)
            rom_path = joined
            kind, ext = archive_info(joined)
            if kind is None:
                if zipfile.is_zipfile(joined):
                    kind, ext = "zip", ".zip"
                elif tarfile.is_tarfile(joined):
                    kind, ext = "tar", ".tar.gz"

        if kind and kind not in ("bin", "ofp"):
            ok, why = verify_rom_archive(rom_path)
            if not ok:
                raise ValueError(f"Corrupt ROM archive: {why}")

        if kind == "zip":
            with zipfile.ZipFile(rom_path, "r") as zf:
                names = zf.namelist()
                dest_abs = os.path.abspath(dest)
                for idx, name in enumerate(names):
                    target = os.path.abspath(os.path.join(dest_abs, name))
                    if target != dest_abs and not target.startswith(dest_abs + os.sep):
                        continue
                    zf.extract(name, dest)
                    if idx % 10 == 0 or idx == len(names) - 1:
                        _cb(f"Extracting: {os.path.basename(name)} ({idx + 1}/{len(names)})...", 85)
        elif is_tar_kind(kind):
            mode = "r:gz" if ext.lower() in (".tgz", ".tar.gz") else "r:"
            with tarfile.open(rom_path, mode=mode) as tf:
                members = tf.getmembers()
                for idx, member in enumerate(members):
                    tf.extract(member, dest, filter="data")
                    if idx % 4 == 0 or idx == len(members) - 1:
                        _cb(f"Extracting: {os.path.basename(member.name)} ({idx + 1}/{len(members)})...", 85)
        elif kind in ("7z", "rar"):
            if kind == "7z":
                # py7zr is bundled into the exe — no 7-Zip / WinRAR install needed.
                try:
                    import py7zr
                    with py7zr.SevenZipFile(rom_path, "r") as a:
                        a.extractall(path=dest)
                    _cb("Extracted .7z archive with the built-in 7z reader.", 90)
                    return original_path
                except ImportError:
                    raise UnsupportedPackageFormatError(ext, "bundled 7z reader is missing from this build")
                except Exception as e:
                    raise ValueError(f"7z extraction failed: {e}")
            unpacker = _find_unpacker(("unrar.exe", "unrar", "rar.exe", "7z.exe", "7za.exe", "7z"))
            if not unpacker:
                raise UnsupportedPackageFormatError(ext, "install WinRAR/7-Zip for .rar archives")
            flags = ["x", "-y", f"-o{dest}", rom_path]
            res = subprocess.run([unpacker] + flags, capture_output=True, text=True, timeout=1800)
            if res.returncode != 0:
                raise ValueError(f"{ext} extraction failed (exit {res.returncode}): {(res.stderr or res.stdout or '').strip()[:400]}")
            _cb(f"Extracted {ext} archive with {os.path.basename(unpacker)}.", 90)
        elif kind == "bin" and os.path.isfile(rom_path) and looks_like_fastboot_raw_image(rom_path):
            # A lone raw Android image named .bin is flashed directly; Odin packages are rejected.
            _cb("Detected raw fastboot image in .bin container.", 90)
        elif kind in ("bin", "ofp"):
            raise UnsupportedPackageFormatError(ext, "Odin multi-image package needs a supported unpacker")
        else:
            raise UnsupportedPackageFormatError(ext or "unknown")
        return original_path
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def parse_fastboot_script_commands(script_path: str, work_dir: str):
    """
    shlex-based parser for .sh/.bat/.cmd flash scripts. Returns (commands, warnings).
    Handles echo/@echo prefixes, fastboot.exe / ./fastboot / full paths, chained
    commands, options before the subcommand, relative image paths, shell and batch
    variables, and strips .img from a partition token written as 'system_a.img'.
    """
    commands = []
    warnings = []
    subcommands = {
        "flash", "flashall", "update", "erase", "format", "wipe", "-w",
        "reboot", "reboot-bootloader", "continue", "disconnect", "getvar",
        "oem", "set_active", "boot", "devices", "flashing", "snapshot-update",
    }
    fastboot_re = re.compile(r'(?:^|[\\/])fastboot(?:\.exe)?$', re.I)
    image_suffixes = (".img", ".img.xz", ".img.gz", ".zip", ".bin", ".md5")
    try:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as sf:
            lines = sf.readlines()
    except Exception as e:
        return commands, [f"Cannot read shell script: {e}"]

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r'^@?echo\s+', line, re.I):
            continue
        line = re.sub(r'^@+', '', line)
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=";|&")
            lexer.whitespace_split = True
            lexer.commenters = "#"
            tokens = list(lexer)
        except ValueError as e:
            warnings.append(f"Line {lineno}: skipped malformed shell command ({e})")
            continue

        segments = []
        current = []
        for tok in tokens:
            if tok in ("&&", ";", "|", "&"):
                if current:
                    segments.append(current)
                current = []
            else:
                current.append(tok)
        if current:
            segments.append(current)

        for seg in segments:
            idx = next((i for i, t in enumerate(seg) if fastboot_re.search(t)), None)
            if idx is None:
                continue
            after = seg[idx + 1:]
            unknown_var = next((t for t in after if re.search(
                r'\$(?:\{[^}]*\}|[A-Za-z_?@#*!0-9])|%[^%]+%', t)), None)
            if unknown_var:
                warnings.append(f"Line {lineno}: skipped command with unresolved variable {unknown_var!r}")
                continue
            cleaned = []
            skip_next = False
            for tok in after:
                if skip_next:
                    skip_next = False
                    continue
                if tok in ("-s", "-S"):
                    skip_next = True
                    continue
                if tok.startswith("-s") and not tok.startswith("--") and len(tok) > 2:
                    continue
                cleaned.append(tok)
            if not cleaned:
                continue
            sub_idx = next((i for i, t in enumerate(cleaned) if t.lower() in subcommands), None)
            if sub_idx is None:
                warnings.append(f"Line {lineno}: no fastboot subcommand found; skipped")
                continue
            pre_opts = cleaned[:sub_idx]
            rest = cleaned[sub_idx:]
            resolved = []
            for tok in rest:
                if tok.lower().endswith(image_suffixes) or "/" in tok or "\\" in tok:
                    guess = tok if os.path.isabs(tok) else os.path.normpath(os.path.join(work_dir, tok))
                    if os.path.exists(guess) or not os.path.isabs(guess):
                        tok = guess
                resolved.append(tok)
            # 'fastboot flash system_a.img system_a.img' must target partition system_a,
            # not a nonexistent partition literally named system_a.img.
            if len(resolved) >= 2 and resolved[0].lower() == "flash":
                target = os.path.basename(resolved[1])
                if target.lower().endswith(image_suffixes):
                    # Keep the slot suffix: system_a.img -> system_a, not system.
                    for suffix in (".img.gz", ".img.xz", ".img", ".zip", ".bin", ".md5"):
                        if target.lower().endswith(suffix):
                            target = target[:-len(suffix)]
                            break
                    resolved[1] = target
            is_long = any(t.lower() in ("update", "flashall") for t in resolved[:2])
            commands.append({
                "tokens": pre_opts + resolved,
                "timeout": 900 if is_long else 180,
                "line": lineno,
            })
    return commands, warnings


def device_action_locked(fn):
    """Serialize device-mutating backend entry points across every UI/bridge caller."""
    @functools.wraps(fn)
    def _wrapped(self, *args, **kwargs):
        lock = getattr(self, "_device_action_lock", None)
        if lock is None or not lock.acquire(blocking=False):
            return {"success": False, "error": "Another device operation is already running. Wait for it to finish."}
        # `_thread.RLock` has no portable .locked(); track nesting ourselves so
        # nested flash calls do not clear the busy state while the outer op runs.
        depth = int(getattr(self, "_device_action_depth", 0)) + 1
        self._device_action_depth = depth
        busy_flag = getattr(self, "_device_action_busy_flag", None)
        if busy_flag is not None:
            busy_flag.set()
        try:
            return fn(self, *args, **kwargs)
        finally:
            depth = max(0, int(getattr(self, "_device_action_depth", 1)) - 1)
            self._device_action_depth = depth
            if depth == 0 and busy_flag is not None:
                busy_flag.clear()
            lock.release()
    return _wrapped


class AndroidBridge:
    def __init__(self):
        self.adb_path = self._find_tool("adb")
        self.fastboot_path = self._find_tool("fastboot")
        self._current_device: Optional[Dict[str, Any]] = None
        self._cancel_download: bool = False
        self._cancel_pending: bool = False
        self._download_generation: int = 0
        self._verified_update: Optional[Dict[str, Any]] = None
        self._scrcpy_err_log: Optional[str] = None
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self.active_flash_proc: Optional[subprocess.Popen] = None
        self.is_flashing: bool = False
        self._payload_cancel_event: Optional[threading.Event] = None
        self._auto_flash_lock = threading.Lock()
        self._device_action_lock = threading.RLock()
        self._device_action_depth = 0
        self._device_action_busy_flag = threading.Event()
        self._auto_flash_cancel_event: Optional[threading.Event] = None
        self._setup_persistent_adb_keys()

    def _setup_persistent_adb_keys(self):
        """
        Manages persistent ADB RSA authorization keys.
        Saves user's trusted adbkey/adbkey.pub in tool storage and configures
        ADB_VENDOR_KEYS environment variable so devices never lose authorization.
        """
        try:
            local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            tool_keys_dir = os.path.join(local_app, "ROM_Flasher_Tool", "adb_keys")
            os.makedirs(tool_keys_dir, exist_ok=True)

            # Also mirror to desktop storage if available for easy user backup
            desktop_keys_dir = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "ROM_Flasher_Storage", "adb_keys")
            try:
                os.makedirs(desktop_keys_dir, exist_ok=True)
            except Exception:
                pass

            user_android = os.path.expanduser("~/.android")
            os.makedirs(user_android, exist_ok=True)
            user_key = os.path.join(user_android, "adbkey")
            user_pub = os.path.join(user_android, "adbkey.pub")

            tool_key = os.path.join(tool_keys_dir, "adbkey")
            tool_pub = os.path.join(tool_keys_dir, "adbkey.pub")

            desk_key = os.path.join(desktop_keys_dir, "adbkey")
            desk_pub = os.path.join(desktop_keys_dir, "adbkey.pub")

            # 1. Sync from user ~/.android to tool storage
            if os.path.exists(user_key):
                if not os.path.exists(tool_key):
                    shutil.copy2(user_key, tool_key)
                if os.path.exists(user_pub) and not os.path.exists(tool_pub):
                    shutil.copy2(user_pub, tool_pub)
                if os.path.exists(desktop_keys_dir) and not os.path.exists(desk_key):
                    try:
                        shutil.copy2(user_key, desk_key)
                        if os.path.exists(user_pub):
                            shutil.copy2(user_pub, desk_pub)
                    except Exception:
                        pass
            # 2. Sync from tool or desktop storage to user ~/.android if missing
            elif os.path.exists(tool_key) and not os.path.exists(user_key):
                shutil.copy2(tool_key, user_key)
                if os.path.exists(tool_pub):
                    shutil.copy2(tool_pub, user_pub)
            elif os.path.exists(desk_key) and not os.path.exists(user_key):
                try:
                    shutil.copy2(desk_key, user_key)
                    if os.path.exists(desk_pub):
                        shutil.copy2(desk_pub, user_pub)
                except Exception:
                    pass

            # Export ADB_VENDOR_KEYS globally in process environment
            active_key = user_key if os.path.exists(user_key) else tool_key
            if os.path.exists(active_key):
                os.environ["ADB_VENDOR_KEYS"] = active_key
        except Exception:
            pass

    def is_device_action_busy(self) -> bool:
        """True while a terminal/unlock/EDL/mirror/recovery operation owns the device."""
        flag = getattr(self, "_device_action_busy_flag", None)
        return bool(flag is not None and flag.is_set())

    def _find_tool(self, name: str) -> str:
        path = shutil.which(name)
        if path and os.path.exists(path):
            return path
        
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        fallbacks = [
            f"C:\\adb\\{name}.exe",
            f"C:\\platform-tools\\{name}.exe",
            os.path.expanduser(f"~\\platform-tools\\{name}.exe"),
            os.path.expanduser(f"~\\AppData\\Local\\Android\\Sdk\\platform-tools\\{name}.exe"),
            os.path.join(base_dir, f"tools\\{name}.exe"),
            os.path.join(base_dir, f"{name}.exe")
        ]
        for fb in fallbacks:
            if os.path.exists(fb):
                return fb
        return name

    def run_cmd(self, cmd_args: List[str], timeout: int = 60) -> Dict[str, Any]:
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            proc = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                env=os.environ.copy()
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "code": proc.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "output": (stdout + "\n" + stderr).strip()
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate()
            except Exception:
                pass
            return {"success": False, "code": -1, "stdout": "", "stderr": "Command timed out", "output": "Command timed out"}
        except Exception as e:
            return {"success": False, "code": -2, "stdout": "", "stderr": str(e), "output": str(e)}

    def _clean_var(self, val: str) -> str:
        if not val:
            return ""
        val = val.strip()
        # Strictly discard any fastboot command status or summary lines
        for bad in ["finished", "total time", "failed", "unknown", "error", "waiting", "remote:"]:
            if bad in val.lower():
                return ""
        return val

    def _get_fastboot_var(self, serial: str, var_name: str, timeout: int = 8, retries: int = 2) -> str:
        # A slow bootloader must not silently turn an A/B device into an A-only flash.
        for _ in range(max(1, retries) + 1):
            res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", var_name], timeout=timeout)
            text = res["stderr"] + "\n" + res["stdout"]
            match = re.search(rf"{var_name}:\s*([^\r\n]+)", text, re.IGNORECASE)
            if match:
                return self._clean_var(match.group(1).strip())
        return ""

    def _probe_fastboot_var(self, serial: str, var_name: str, timeout: int = 8, retries: int = 2):
        """Return (value, responded). Distinguishes timeout from 'unsupported variable'."""
        for _ in range(max(1, retries) + 1):
            res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", var_name], timeout=timeout)
            text = "\n".join(str(res.get(k, "")) for k in ("stdout", "stderr", "output"))
            match = re.search(rf"{var_name}:\s*([^\r\n]+)", text, re.IGNORECASE)
            if match:
                return self._clean_var(match.group(1).strip()), True
            if re.search(r"(unknown|invalid|no such)\s+variable|not\s+found", text, re.IGNORECASE):
                return "", True
        return "", False

    def detect_devices(self, bypass_cache: bool = False) -> List[Dict[str, Any]]:
        if not bypass_cache and getattr(self, "is_flashing", False):
            return getattr(self, "_last_detected_devices", [])
        devices = []

        # 1. Check ADB Devices
        adb_res = self.run_cmd([self.adb_path, "devices", "-l"], timeout=10)
        if adb_res["success"] or "List of devices attached" in adb_res["output"]:
            lines = adb_res["stdout"].splitlines()
            for line in lines[1:]:
                line = line.strip()
                if not line or any(b in line.lower() for b in ["finished", "total time", "error"]):
                    continue
                parts = re.split(r'\s+', line)
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    
                    props = {}
                    for item in parts[2:]:
                        if ':' in item:
                            k, v = item.split(':', 1)
                            props[k] = v

                    raw_model = props.get("model", props.get("device", "Android Device")).replace("_", " ")
                    clean_model_key = raw_model.lower().replace(" ", "")
                    dev_code = props.get("device", "").lower() or props.get("product", "").lower()
                    
                    if clean_model_key in MODEL_TO_CODENAME:
                        dev_code = MODEL_TO_CODENAME[clean_model_key]

                    display_name = raw_model
                    if dev_code:
                        if dev_code in FASTBOOT_CODENAME_MAP:
                            display_name = FASTBOOT_CODENAME_MAP[dev_code].split("/")[0].strip()

                    devices.append({
                        "serial": serial,
                        "mode": "ADB",
                        "state": state,
                        "model": display_name,
                        "product": props.get("product", ""),
                        "transport_id": props.get("transport_id", "")
                    })

        # 2. Check Fastboot Devices
        fb_res = self.run_cmd([self.fastboot_path, "devices"], timeout=10)
        if fb_res["output"]:
            fb_text = fb_res.get("stdout") or fb_res.get("output") or ""
            for line in fb_text.splitlines():
                line = line.strip()
                if not line or any(b in line.lower() for b in ["finished", "total time", "error", "waiting"]):
                    continue
                parts = re.split(r'\s+', line)
                if len(parts) >= 2 and parts[1].lower() == "fastboot":
                    serial = parts[0]
                    # Validate that serial is a real serial number (allow usb:1-2 / PCI colons & dots), not a status line
                    if not re.match(r'^[A-Za-z0-9_.\-:]+$', serial) or any(b in serial.lower() for b in ["finished", "total", "time", "waiting"]):
                        continue
                    raw_product = self._get_fastboot_var(serial, "product")
                    product = self._clean_var(raw_product) or "Fastboot Device"
                    prod_lower = product.lower()
                    name = FASTBOOT_CODENAME_MAP.get(prod_lower, product)
                    if "/" in name:
                        name = name.split("/")[0].strip()
                    devices.append({
                        "serial": serial,
                        "mode": "FASTBOOT",
                        "state": "fastboot",
                        "model": name,
                        "product": product,
                        "transport_id": ""
                    })

        self._last_detected_devices = devices
        return devices

    @staticmethod
    def _find_device_exact(devices: List[Dict[str, Any]], serial: str, mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Finds a device ONLY by the exact requested serial. Never adopts another connected device."""
        if not serial:
            return None
        wanted_mode = (mode or "").upper()
        return next((d for d in (devices or [])
                     if str(d.get("serial", "")) == str(serial)
                     and (not wanted_mode or str(d.get("mode", "")).upper() == wanted_mode)), None)

    @staticmethod
    def _device_not_found_error(serial: str, mode: Optional[str] = None) -> str:
        where = f" in {mode.upper()} mode" if mode else ""
        return (f"Selected device with serial '{serial}'{where} was not found. "
                "No other connected device will be used; connect the selected device and retry.")

    def _require_adb_device(self, serial: str) -> Optional[str]:
        """Return an error message unless the exact serial is still online in ADB."""
        if not str(serial or "").strip():
            return "No device serial was provided. Select a connected device and retry."
        devices = self.detect_devices(bypass_cache=True)
        if not self._find_device_exact(devices, serial, "ADB"):
            return self._device_not_found_error(serial, "ADB")
        return None

    def get_xiaomi_devices(self, query: str = "") -> List[Dict[str, Any]]:
        devs = load_xiaomi_devices()
        if not devs:
            return []
        q = query.strip().lower()
        if not q:
            return devs
        return [d for d in devs if q in d.get("codename", "").lower() or q in d.get("name", "").lower() or q in d.get("brand", "").lower()]

    def get_device_details(self, serial: str, mode: str) -> Dict[str, Any]:
        info = {
            "serial": serial,
            "mode": mode,
            "original_name": "Unknown",
            "model": "Unknown",
            "codename": "",
            "brand": "",
            "android_version": "",
            "security_patch": "",
            "battery_level": None,
            "battery_status": "Unknown",
            "battery_temp": None,
            "is_charging": False,
            "bootloader_unlocked": None,
            "current_slot": "",
            "raw_battery": "",
            "state": ""
        }

        for _dev in self.detect_devices(bypass_cache=True):
            if str(_dev.get("serial", "")).lower() == str(serial).lower():
                info["state"] = str(_dev.get("state", "") or "")
                break

        if mode == "ADB":
            props = {}
            gp_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "getprop"], timeout=8)
            if gp_res["success"]:
                for line in gp_res["stdout"].splitlines():
                    if ']: [' in line:
                        try:
                            k = line.split(']: [')[0].strip('[] ')
                            v = line.split(']: [')[1].strip('[] ')
                            props[k] = v
                        except:
                            pass

            brand = props.get("ro.product.brand", props.get("ro.product.manufacturer", "")).capitalize()
            internal_model = props.get("ro.product.model", props.get("ro.product.device", "Android"))
            dev_code = (props.get("ro.product.device") or props.get("ro.build.product") or props.get("ro.product.name") or "").lower()

            clean_model_key = internal_model.lower().replace(" ", "")
            if clean_model_key in MODEL_TO_CODENAME:
                dev_code = MODEL_TO_CODENAME[clean_model_key]

            marketname = ""
            market_props = [
                "ro.product.marketname",
                "ro.product.odm.marketname",
                "ro.product.vendor.marketname",
                "ro.product.system_dlkm.marketname",
                "ro.product.product.marketname",
                "ro.vendor.oplus.market.name",
                "ro.oplus.market.name",
                "ro.vivo.market.name",
                "ro.config.marketing_name",
                "ro.semc.product.name"
            ]
            for p in market_props:
                if props.get(p):
                    marketname = props.get(p).strip()
                    break

            if not marketname and dev_code:
                if dev_code in FASTBOOT_CODENAME_MAP:
                    marketname = FASTBOOT_CODENAME_MAP[dev_code].split("/")[0].strip()
                else:
                    for d in load_xiaomi_devices():
                        if d.get("codename", "").lower() == dev_code:
                            marketname = d.get("name", "").split("/")[0].strip()
                            break

            if not marketname:
                if brand and not internal_model.lower().startswith(brand.lower()):
                    marketname = f"{brand} {internal_model}"
                else:
                    marketname = internal_model

            info["original_name"] = marketname
            info["model"] = f"{marketname} ({dev_code})" if dev_code else internal_model
            info["codename"] = dev_code or internal_model.lower()
            info["brand"] = brand
            info["android_version"] = props.get("ro.build.version.release", "")
            info["security_patch"] = props.get("ro.build.version.security_patch", "")

            # Check Slot in ADB
            slot_suf = props.get("ro.boot.slot_suffix", "")
            if slot_suf:
                info["current_slot"] = f"Slot {slot_suf.strip('_').upper()}"

            # Check Bootloader Lock Status in ADB
            flash_locked = props.get("ro.boot.flash.locked", "")
            verified_state = props.get("ro.boot.verifiedbootstate", "").lower()
            if flash_locked == "0" or verified_state == "orange":
                info["bootloader_unlocked"] = True
            elif flash_locked == "1" or verified_state == "green":
                info["bootloader_unlocked"] = False

            # Battery Dumpsys
            bat_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "dumpsys", "battery"], timeout=5)
            if bat_res["success"] and bat_res["stdout"]:
                info["raw_battery"] = bat_res["stdout"]
                for b_line in bat_res["stdout"].splitlines():
                    b_line = b_line.strip()
                    if b_line.startswith("level:"):
                        try:
                            info["battery_level"] = int(b_line.split(":", 1)[1].strip())
                        except:
                            pass
                    elif b_line.startswith("status:"):
                        st = b_line.split(":", 1)[1].strip()
                        if st == "2":
                            info["battery_status"] = "Charging"
                            info["is_charging"] = True
                        elif st == "5":
                            info["battery_status"] = "Full"
                            info["is_charging"] = True
                        else:
                            info["battery_status"] = "Discharging"
                    elif b_line.startswith("temperature:"):
                        try:
                            temp_val = int(b_line.split(":", 1)[1].strip())
                            info["battery_temp"] = f"{temp_val / 10.0:.1f}°C"
                        except:
                            pass

        elif mode == "FASTBOOT":
            raw_prod = self._get_fastboot_var(serial, "product")
            raw_market = self._get_fastboot_var(serial, "marketname")
            prod = self._clean_var(raw_prod)
            market = self._clean_var(raw_market)
            prod_lower = (prod or "").lower()
            info["codename"] = prod_lower
            
            if market:
                info["original_name"] = market
            elif prod_lower and prod_lower in FASTBOOT_CODENAME_MAP:
                info["original_name"] = FASTBOOT_CODENAME_MAP[prod_lower].split("/")[0].strip()
            elif prod and prod != "Fastboot Device":
                info["original_name"] = prod
            else:
                info["original_name"] = "Fastboot Device"
            
            info["model"] = f"{info['original_name']} ({prod})" if prod and prod != info["original_name"] else info["original_name"]
            
            unlocked = self._get_fastboot_var(serial, "unlocked")
            if unlocked:
                info["bootloader_unlocked"] = unlocked.lower() in ("yes", "true", "1")

            slot = self._get_fastboot_var(serial, "current-slot")
            if slot:
                info["current_slot"] = f"Slot {slot.strip('_').upper()}"

            bat_v = self._get_fastboot_var(serial, "battery-voltage")
            if bat_v:
                try:
                    v_clean = bat_v.lower().replace("mv", "").replace("uv", "").strip()
                    if v_clean.endswith("v"):
                        mv = int(float(v_clean[:-1].strip()) * 1000)
                    else:
                        raw_v = float(v_clean)
                        mv = int(raw_v / 1000.0) if raw_v > 100000 else (int(raw_v * 1000) if raw_v < 20 else int(raw_v))
                    pct = max(0, min(100, int((mv - 3600) / (4350 - 3600) * 100)))
                    info["battery_level"] = pct
                    info["battery_status"] = f"{pct}% ({mv}mV)"
                except:
                    pass

        return info

    @device_action_locked
    def reboot(self, serial: str, mode: str, target: str) -> Dict[str, Any]:
        """Mutating reboot also owns the shared device slot (RLock keeps nested flash calls safe)."""
        target = target.lower()
        if mode == "ADB":
            if target == "system":
                cmd = [self.adb_path, "-s", serial, "reboot"]
            elif target in ("bootloader", "fastboot"):
                cmd = [self.adb_path, "-s", serial, "reboot", "bootloader"]
            elif target == "recovery":
                cmd = [self.adb_path, "-s", serial, "reboot", "recovery"]
            elif target == "edl":
                cmd = [self.adb_path, "-s", serial, "reboot", "edl"]
            elif target == "fastbootd":
                cmd = [self.adb_path, "-s", serial, "reboot", "fastboot"]
            elif target == "poweroff":
                cmd = [self.adb_path, "-s", serial, "shell", "reboot", "-p"]
            else:
                cmd = [self.adb_path, "-s", serial, "reboot"]
        else: # FASTBOOT
            if target == "system":
                cmd = [self.fastboot_path, "-s", serial, "reboot"]
            elif target == "bootloader":
                cmd = [self.fastboot_path, "-s", serial, "reboot", "bootloader"]
            elif target == "recovery":
                cmd = [self.fastboot_path, "-s", serial, "reboot", "recovery"]
            elif target == "edl":
                cmd = [self.fastboot_path, "-s", serial, "oem", "edl"]
            elif target == "fastbootd":
                cmd = [self.fastboot_path, "-s", serial, "reboot", "fastboot"]
            elif target == "poweroff":
                cmd = [self.fastboot_path, "-s", serial, "oem", "poweroff"]
            else:
                cmd = [self.fastboot_path, "-s", serial, "reboot"]
        
        return self.run_cmd(cmd, timeout=15)

    def _try_recovery_reboot(self, serial: str) -> Dict[str, Any]:
        """
        Best-effort: reboot directly out of ADB sideload/recovery BEFORE the
        'Install additional packages?' menu steals the ADB connection.
        Safe to call more than once; already-fastboot/Android is treated as done.
        A command's exit code alone is never enough: the exact serial must be
        observed in FASTBOOT or non-recovery ADB before success is returned.
        """
        def _ready_state(devs: List[Dict[str, Any]]) -> str:
            if self._find_device_exact(devs, serial, "FASTBOOT"):
                return "fastboot"
            adb_dev = self._find_device_exact(devs, serial, "ADB")
            if adb_dev and str(adb_dev.get("state", "")).lower() not in ("sideload", "recovery"):
                return "adb"
            return ""

        already = _ready_state(self.detect_devices(bypass_cache=True))
        if already:
            return {"success": True, "code": 0, "output": f"Device already reachable in {already}; reboot skipped."}

        attempts = [
            [self.adb_path, "-s", serial, "reboot", "bootloader"],
            [self.adb_path, "-s", serial, "shell", "reboot", "bootloader"],
            [self.adb_path, "-s", serial, "reboot"],
            [self.adb_path, "-s", serial, "shell", "reboot"],
            [self.adb_path, "-s", serial, "reboot", "fastboot"],
        ]
        last: Dict[str, Any] = {"success": False, "code": -1, "output": "No ADB reboot path left sideload/recovery"}
        overall_deadline = time.time() + 10
        for cmd in attempts:
            remaining = overall_deadline - time.time()
            if remaining <= 0:
                break
            res = self.run_cmd(cmd, timeout=max(1, min(4, remaining))) or {"success": False, "output": ""}
            last = dict(res)
            poll_until = min(time.time() + 2.0, overall_deadline)
            while time.time() < poll_until:
                time.sleep(0.4)
                state = _ready_state(self.detect_devices(bypass_cache=True))
                if state:
                    last["success"] = True
                    last["output"] = (str(res.get("output", "") or "") + f"\nDevice visible in {state} after reboot.").strip()
                    return last
            if not res.get("success"):
                continue

        last["success"] = False
        last["output"] = (str(last.get("output", "") or "") + "\nReboot was not confirmed by a device-state change.").strip()
        return last

    # 🔥 AUTO FLASHER ENGINE (FASTBOOT ARB BYPASS + AOSP PAYLOAD.BIN EXTRACTION & SIDELOAD)
    def inspect_rom_path(self, rom_path: str) -> Dict[str, Any]:
        """Inspects a ROM folder/archive using REAL contents; never fabricates script names."""
        if not os.path.exists(rom_path):
            return {"success": False, "error": f"Path not found: {rom_path}"}

        # Folders: recursive index of real files only.
        if os.path.isdir(rom_path):
            scripts = script_index(rom_path)
            payload_path = find_payload_in(rom_path)
            images = image_index(rom_path)
            base = {
                "success": True, "is_dir": True, "path": rom_path,
                "scripts": list(scripts.keys()),
                "script_paths": scripts,
                "script_types": {n: os.path.splitext(n)[1].lower() for n in scripts},
                "work_dir": dominant_script_dir(rom_path),
            }
            if payload_path:
                base.update({"type": "aosp_folder", "is_payload": True, "payload_path": payload_path})
                return base
            if images and not scripts:
                base.update({"type": "images_folder", "is_payload": False, "images": images})
                return base
            base.update({"type": "fastboot", "is_payload": False})
            return base

        rom_lower = str(rom_path).lower()

        # A lone raw image is a direct GSI/dynamic-partition flash, not an archive.
        if rom_lower.endswith((".img", ".img.xz", ".img.gz")):
            part = normalize_partition_name(os.path.basename(rom_path))
            return {
                "success": True, "is_dir": False, "type": "gsi_image", "is_payload": False,
                "partition": part, "scripts": [], "path": rom_path,
            }

        kind, ext = archive_info(rom_path)
        if kind == "bin" and looks_like_fastboot_raw_image(rom_path):
            part = normalize_partition_name(os.path.basename(rom_path))
            return {
                "success": True, "is_dir": False, "type": "gsi_image", "is_payload": False,
                "partition": part, "scripts": [], "path": rom_path,
            }
        if kind in ("bin", "ofp"):
            return {"success": False, "error": str(UnsupportedPackageFormatError(
                ext, "Odin multi-image package needs a supported unpacker"))}

        if rom_lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(rom_path, "r") as zf:
                    names = zf.namelist()
                    low_names = [n.lower().replace("\\", "/") for n in names]
                    scripts = {}
                    for n in names:
                        b = os.path.basename(n.replace("\\", "/")).lower()
                        if b.endswith(SCRIPT_EXTS) and not b.startswith("rom_flasher_"):
                            scripts[b] = n
                    recovery = any(
                        n.startswith(_RECOVERY_INSTALL_DIR + "/") and n.endswith(("update-binary", "updater-script"))
                        for n in low_names)
                    has_payload = any(is_payload_entry(n) for n in names)
                    if recovery:
                        return {"success": True, "is_dir": False, "type": "recovery_zip",
                                "is_payload": False, "scripts": [], "path": rom_path}
                    if has_payload and not scripts:
                        return {"success": True, "is_dir": False, "type": "aosp",
                                "is_payload": True, "scripts": [], "path": rom_path}
                    if scripts:
                        return {"success": True, "is_dir": False, "type": "fastboot_zip",
                                "is_payload": False, "scripts": list(scripts.keys()),
                                "script_paths": scripts,
                                "script_types": {n: os.path.splitext(n)[1].lower() for n in scripts},
                                "path": rom_path}
                    return {"success": True, "is_dir": False, "type": "generic_zip",
                            "is_payload": False, "scripts": [], "path": rom_path}
            except Exception as e:
                return {"success": False, "error": f"Failed reading ZIP: {str(e)}"}

        if is_tar_kind(kind):
            try:
                mode = "r:gz" if ext.lower() in (".tgz", ".tar.gz") else "r:"
                scripts = {}
                has_payload = False
                recovery = False
                with tarfile.open(rom_path, mode=mode) as tf:
                    for member in tf:
                        low = member.name.lower().replace("\\", "/").lstrip("./")
                        if is_payload_entry(low):
                            has_payload = True
                        if low.startswith(_RECOVERY_INSTALL_DIR + "/") and low.endswith(("update-binary", "updater-script")):
                            recovery = True
                        b = os.path.basename(low)
                        if b.endswith(SCRIPT_EXTS) and not b.startswith("rom_flasher_"):
                            scripts[b] = member.name
                if recovery:
                    return {"success": True, "is_dir": False, "type": "recovery_zip",
                            "is_payload": False, "scripts": [], "path": rom_path}
                prefer_scripts = bool(scripts)
                return {
                    "success": True, "is_dir": False,
                    "type": "fastboot_tgz" if prefer_scripts else ("aosp" if has_payload else "fastboot_tgz"),
                    "is_payload": has_payload and not prefer_scripts, "scripts": list(scripts.keys()),
                    "script_paths": scripts,
                    "script_types": {n: os.path.splitext(n)[1].lower() for n in scripts},
                    "container": ext, "path": rom_path,
                }
            except Exception as e:
                return {"success": False, "error": f"Failed reading archive: {str(e)}"}

        if kind:
            # 7z/rar/split contents are only known after extraction; prepare_and_scan_rom
            # performs the real scan and never assumes hardcoded .bat names.
            return {"success": True, "is_dir": False, "type": "archive", "is_payload": False,
                    "scripts": [], "container": ext, "path": rom_path}

        return {"success": True, "is_dir": False, "type": "file", "scripts": [], "path": rom_path}

    def prepare_and_scan_rom(self, rom_path: str, progress_cb=None) -> Dict[str, Any]:
        """Prepare a ROM folder/archive and return REAL scripts, images and work_dir."""
        def _cb(msg, pct):
            if progress_cb:
                try:
                    progress_cb(msg, pct)
                except Exception:
                    pass  # a UI callback exception must not abort ROM preparation

        def _sort_scripts(names):
            return sorted(names, key=lambda x: 0 if "all.bat" in x.lower() or "all.sh" in x.lower()
                          else (1 if "storage" in x.lower() or "except" in x.lower() else 2))

        if not os.path.exists(rom_path):
            return {"success": False, "error": f"File or folder not found: {rom_path}"}

        # Custom recovery flashable ZIP -> ADB sideload, never fastboot script extraction.
        if is_recovery_zip(rom_path):
            _cb("Detected custom recovery ZIP (META-INF updater). Use ADB Sideload.", 100)
            return {"success": True, "type": "recovery_zip", "is_archive": True, "is_payload": False,
                    "sideload_source": os.path.abspath(rom_path),
                    "extracted_dir": os.path.dirname(os.path.abspath(rom_path)), "scripts": []}

        # A lone raw image is a direct GSI / dynamic-partition flash.
        if os.path.isfile(rom_path) and (str(rom_path).lower().endswith((".img", ".img.xz", ".img.gz"))
                                         or (str(rom_path).lower().endswith(".bin")
                                             and looks_like_fastboot_raw_image(rom_path))):
            return {"success": True, "type": "gsi_image", "is_archive": False, "is_payload": False,
                    "partition": normalize_partition_name(os.path.basename(rom_path)),
                    "extracted_dir": os.path.dirname(os.path.abspath(rom_path)),
                    "scripts": [], "images": {os.path.basename(rom_path).lower(): os.path.abspath(rom_path)}}

        # 1. Folder: recursive real-file index.
        if os.path.isdir(rom_path):
            _cb(f"Scanning folder for Fastboot scripts: {os.path.basename(rom_path)}...", 25)
            scripts = script_index(rom_path)
            payload_path = find_payload_in(rom_path)
            images = image_index(rom_path)
            work_dir = dominant_script_dir(rom_path) if scripts else dominant_image_dir(rom_path)
            result = {
                "success": True, "is_archive": False, "scripts": _sort_scripts(list(scripts.keys())),
                "script_paths": scripts,
                "script_types": {n: os.path.splitext(n)[1].lower() for n in scripts},
                "extracted_dir": work_dir, "images": images,
            }
            if payload_path:
                _cb(f"Detected AOSP payload.bin in folder: {payload_path}", 100)
                result.update({"type": "aosp_folder", "is_payload": True, "payload_path": payload_path})
                return result
            result.update({"type": "fastboot" if scripts else "images_folder", "is_payload": False})
            _cb(f"Found {len(scripts)} script(s) in {os.path.basename(work_dir)}.", 100)
            return result

        # AOSP OTA ZIPs are read in place: no need to unpack multi-GB payload ROMs.
        if str(rom_path).lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(rom_path, "r") as zf:
                    names = zf.namelist()
                    has_scripts = any(os.path.basename(n.replace("\\", "/")).lower().endswith(SCRIPT_EXTS)
                                      for n in names)
                    if any(is_payload_entry(n) for n in names) and not has_scripts:
                        _cb("Detected AOSP ROM containing payload.bin.", 100)
                        return {"success": True, "type": "aosp", "is_archive": True,
                                "is_payload": True, "extracted_dir": os.path.dirname(os.path.abspath(rom_path)),
                                "sideload_source": os.path.abspath(rom_path), "scripts": []}
            except Exception as e:
                return {"success": False, "error": f"Corrupt ZIP archive: {str(e)}"}

        # 2. Archive: any recognized container, including split parts.
        kind, ext = archive_info(rom_path)
        if not kind:
            return {"success": False, "error": f"unsupported package format: {ext or 'unknown'}"}

        _cb(f"Preparing to unpack ROM package: {os.path.basename(rom_path)}...", 10)
        storage = storage_path_for(rom_path, "Extracted_ROMs")
        if not storage.get("success"):
            return storage
        clean_folder_name = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.basename(rom_path)) or "rom"
        identity = source_identity(rom_path, strong=True)
        extract_dest = os.path.join(storage["path"], f"{clean_folder_name}_{cache_key_for(rom_path)}")
        marker = extract_dest + ".complete"

        cache_ok = read_cache_marker(marker, identity) and os.path.isdir(extract_dest)
        if cache_ok:
            cached_scripts = script_index(extract_dest)
            cached_payload = find_payload_in(extract_dest)
            if cached_scripts or cached_payload:
                _cb("Archive already extracted previously! Using verified cache.", 95)
                result = {
                    "success": True, "is_archive": True, "scripts": _sort_scripts(list(cached_scripts.keys())),
                    "script_paths": cached_scripts,
                    "script_types": {n: os.path.splitext(n)[1].lower() for n in cached_scripts},
                    "extracted_dir": (dominant_script_dir(extract_dest) if cached_scripts
                                      else dominant_image_dir(extract_dest)),
                    "images": image_index(extract_dest),
                }
                if cached_payload:
                    result.update({"type": "aosp_folder", "is_payload": True, "payload_path": cached_payload})
                else:
                    result.update({"type": "fastboot", "is_payload": False})
                _cb(f"Found {len(cached_scripts)} script(s).", 100)
                return result
            cache_ok = False

        if not cache_ok:
            shutil.rmtree(extract_dest, ignore_errors=True)
            try:
                os.remove(marker)
            except Exception:
                pass
            os.makedirs(extract_dest, exist_ok=True)

        _cb("Extracting ROM package... (Please wait)", 15)
        try:
            extract_rom_archive(rom_path, extract_dest, progress_cb=_cb)
        except Exception as e:
            # A failed extraction must never leave a reuseable partial cache folder.
            shutil.rmtree(extract_dest, ignore_errors=True)
            try:
                os.remove(marker)
            except Exception:
                pass
            return {"success": False, "error": f"Extraction failed: {str(e)}",
                    "unsupported_format": isinstance(e, UnsupportedPackageFormatError)}

        scripts = script_index(extract_dest)
        payload_path = find_payload_in(extract_dest)
        images = image_index(extract_dest)
        work_dir = dominant_script_dir(extract_dest) if scripts else dominant_image_dir(extract_dest)
        # Marker is written ONLY after the whole archive was extracted successfully.
        try:
            write_cache_marker(marker, identity)
        except Exception as e:
            return {"success": False, "error": f"Could not finalize extraction cache: {e}"}

        result = {
            "success": True, "is_archive": True, "scripts": _sort_scripts(list(scripts.keys())),
            "script_paths": scripts,
            "script_types": {n: os.path.splitext(n)[1].lower() for n in scripts},
            "extracted_dir": work_dir, "images": images, "container": ext,
        }
        if payload_path:
            _cb(f"Detected AOSP payload.bin after extraction: {payload_path}", 98)
            result.update({"type": "aosp_folder", "is_payload": True, "payload_path": payload_path})
            return result
        if not scripts and not images:
            return {"success": False,
                    "error": f"No flash scripts (.bat/.cmd/.sh) or images found inside {os.path.basename(rom_path)}."}
        result.update({"type": "fastboot" if scripts else "images_folder", "is_payload": False})
        _cb(f"Found {len(scripts)} flash script(s) and {len(images)} image(s).", 100)
        return result

    def write_misc_sideload_command(self, serial: str) -> bool:
        """
        Writes standard Android Bootloader Control Block (BCB) to 'misc' partition so device
        boots directly into ADB Sideload mode across all AOSP recoveries.
        Standard 2048-byte BCB layout with clean null padding.
        """
        try:
            command = b"boot-recovery".ljust(32, b'\x00')
            status = b''.ljust(32, b'\x00')
            recovery = b"recovery\n--sideload\n".ljust(768, b'\x00')
            stage = b''.ljust(32, b'\x00')
            reserved = b''.ljust(1184, b'\x00')
            bcb_data = command + status + recovery + stage + reserved

            temp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
            temp_f.write(bcb_data)
            temp_f.close()

            # Attempt flashing to misc, then to the ACTIVE slot only. Writing just
            # the inactive slot was reported as success but never entered sideload.
            res = self.run_cmd([self.fastboot_path, "-s", serial, "flash", "misc", temp_f.name], timeout=10)
            if not fastboot_result_ok(res):
                cur_slot = (self._get_fastboot_var(serial, "current-slot") or "").strip().lower()
                if cur_slot in ("a", "b"):
                    res = self.run_cmd([self.fastboot_path, "-s", serial, "flash",
                                        f"misc_{cur_slot}", temp_f.name], timeout=10)
                else:
                    res_a = self.run_cmd([self.fastboot_path, "-s", serial, "flash", "misc_a", temp_f.name], timeout=10)
                    res_b = self.run_cmd([self.fastboot_path, "-s", serial, "flash", "misc_b", temp_f.name], timeout=10)
                    if fastboot_result_ok(res_a) and fastboot_result_ok(res_b):
                        res = res_a
                    else:
                        res = {"success": False, "output":
                               f"BCB slot writes failed (misc_a: {res_a.get('output', '')}; misc_b: {res_b.get('output', '')})"}

            try:
                os.remove(temp_f.name)
            except:
                pass
            return fastboot_result_ok(res)
        except:
            return False

    def cancel_auto_flash(self) -> Dict[str, Any]:
        """Cancel only the active 1-click flash; never touches download/sideload flags."""
        ev = getattr(self, "_auto_flash_cancel_event", None)
        if ev is None:
            return {"success": True, "output": "No 1-click flash is currently running."}
        ev.set()
        proc = getattr(self, "active_flash_proc", None)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        return {"success": True, "output": "1-click flash cancellation requested."}

    @device_action_locked
    def auto_flash(self, serial: str, rom_path: str, selected_script: Optional[str] = None, progress_cb=None) -> Dict[str, Any]:
        """Single-run owner: one flash at a time, with its own cancel token."""
        if not self._auto_flash_lock.acquire(blocking=False):
            return {"success": False, "error": "A 1-click flash is already running.", "cancelled": False, "logs": []}
        cancel_event = threading.Event()
        self._auto_flash_cancel_event = cancel_event
        self.is_flashing = True
        try:
            return self._auto_flash_impl(serial, rom_path, selected_script, progress_cb)
        except Exception as e:
            return {"success": False, "error": str(e),
                    "cancelled": cancel_event.is_set(), "logs": []}
        finally:
            self.is_flashing = False
            self.active_flash_proc = None
            self._auto_flash_cancel_event = None
            self._auto_flash_lock.release()

    def _auto_flash_impl(self, serial: str, rom_path: str, selected_script: Optional[str] = None, progress_cb=None) -> Dict[str, Any]:
        """
        Executes full 1-Click Auto Flash with:
        1. Auto transition from ADB to Fastboot
        2. Fastboot ROM ARB (Anti-Rollback) Bypass
        3. Real-time stdout/stderr piped directly to live console (no black cmd window)
        4. AOSP ROM payload.bin extraction (boot, init_boot, vendor_boot) + slot flash + wipe + recovery sideload + system reboot
        """
        logs = []
        def _log(m, pct=None):
            logs.append(m)
            if progress_cb:
                try:
                    progress_cb(m, pct)
                except Exception:
                    pass  # a UI callback exception must not abort the flash

        # `serial` is appended to a cmd.exe command line and exported to flash
        # environment variables. Reject metacharacters before any of that.
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", str(serial or "")):
            err_msg = "Refusing to flash: device serial contains unsupported characters."
            _log(f"❌ {err_msg}", 0)
            return {"success": False, "error": err_msg, "logs": logs}

        def _cancel_check(stage=""):
            ev = getattr(self, "_auto_flash_cancel_event", None)
            if ev is not None and ev.is_set():
                raise RuntimeError(f"1-click flash cancelled ({stage})")

        def _verify_final_boot() -> Optional[str]:
            """Positive boot proof shared by every flash path. Returns an error or None."""
            try:
                boot_timeout_sec = max(120, int(os.environ.get("ROM_FLASHER_BOOT_TIMEOUT", "600") or 600))
            except (TypeError, ValueError):
                boot_timeout_sec = 600
            boot_start = time.time()
            last_heartbeat = -1
            last_seen = "no device visible"
            while (time.time() - boot_start) < boot_timeout_sec:
                time.sleep(1.5)
                _cancel_check("boot verification")
                final_dev = self._find_device_exact(self.detect_devices(bypass_cache=True), serial)
                if final_dev:
                    last_seen = f"{final_dev.get('mode', '?')}/{final_dev.get('state', '')}"
                if final_dev and final_dev.get("mode") == "ADB":
                    adb_state = str(final_dev.get("state", "")).lower()
                    if adb_state not in ("sideload", "recovery", "unauthorized", "offline"):
                        boot_done = self._get_prop(serial, "sys.boot_completed").strip()
                        if boot_done == "1":
                            return None
                        last_seen = f"{final_dev.get('mode', '?')}/booting(boot_completed={boot_done or '?'})"
                    elif adb_state in ("unauthorized", "offline"):
                        # Visible but unauthorised is NOT proof of a completed boot.
                        last_seen = f"ADB/{adb_state} (authorisation not approved)"
                elapsed = int(time.time() - boot_start)
                if elapsed - last_heartbeat >= 15:
                    last_heartbeat = elapsed
                    _log(f"⏳ Boot verification: {elapsed}s / {boot_timeout_sec}s elapsed; last seen: {last_seen}", 99)
            err = (f"Could not verify that device '{serial}' finished booting into Android "
                   f"within {boot_timeout_sec}s (last seen: {last_seen}). "
                   "Approve USB debugging authorization / check the cable and bootloader state, then retry.")
            _log(f"❌ Error: {err}", 0)
            return err

        _log(f"Starting 1-Click Auto Flasher on: {os.path.basename(rom_path)}", 5)

        # Custom recovery ZIPs are flashed through ADB sideload, never via fastboot
        # script extraction. Offer the sideload route directly when already in recovery.
        if is_recovery_zip(rom_path):
            _log("Detected custom recovery ZIP (META-INF/com/google/android/update-binary).", 10)
            try:
                rec_devs = self.detect_devices(bypass_cache=True)
                rec_dev = self._find_device_exact(rec_devs, serial, "ADB")
                if rec_dev and str(rec_dev.get("state", "")).lower() in ("sideload", "recovery"):
                    _cancel_check("before sideload")
                    _log("Device is in recovery/sideload. Streaming ZIP with ADB sideload...", 20)
                    self.is_flashing = True
                    res = self.adb_sideload(
                        serial, os.path.abspath(rom_path),
                        progress_cb=lambda msg, pct: _log(msg, pct))
                    _log(res.get("output", ""), 100)
                    if not res.get("success"):
                        self.is_flashing = False
                        return {"success": False, "error": res.get("error", "ADB sideload failed."),
                                "requires_sideload": True, "logs": logs}
                    self._try_recovery_reboot(serial)
                    boot_err = _verify_final_boot()
                    self.is_flashing = False
                    if boot_err:
                        return {"success": False, "error": boot_err, "requires_sideload": True, "logs": logs}
                    return {"success": True, "requires_sideload": True, "logs": logs}
            except Exception as e:
                _log(f"Sideload route check failed: {e}", 15)
            self.is_flashing = False
            err = ("Custom recovery ZIP detected. Boot into recovery / 'adb reboot sideload' "
                   "and use ADB Sideload; this ZIP has no fastboot flash script.")
            _log(f"⚠️ {err}", 0)
            return {"success": False, "error": err, "requires_sideload": True, "logs": logs}

        # CASE A owns device discovery while it runs; every CASE A poll uses
        # bypass_cache=True so a stale cache can never hijack this flash.
        self.is_flashing = True

        # 1. Device check: If in ADB, auto-reboot to Fastboot (exact serial only, no substitutions)
        devices = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devices, serial)
        if not dev:
            err = self._device_not_found_error(serial)
            _log(f"❌ {err}", 0)
            self.is_flashing = False
            return {"success": False, "error": err, "logs": logs}

        if dev and dev["mode"] == "ADB":
            _log("Device currently in ADB mode. Auto-rebooting to Bootloader (Fastboot)...", 10)
            self.reboot(serial, "ADB", "bootloader")

            # Wait for fastboot device to appear - must be the SAME physical device
            _log("Waiting for Fastboot device connection...", 15)
            found_fb = False
            for _ in range(25):
                time.sleep(1.5)
                _cancel_check("waiting for fastboot")
                fb_devs = self.detect_devices(bypass_cache=True)
                fb_match = self._find_device_exact(fb_devs, serial, "FASTBOOT")
                if fb_match:
                    found_fb = True
                    _log(f"Fastboot mode connected! Device: {serial}", 20)
                    break
            if not found_fb:
                err = self._device_not_found_error(serial, "FASTBOOT")
                _log(f"❌ {err}", 0)
                self.is_flashing = False
                return {"success": False, "error": err, "logs": logs}

        # A lone raw .img (or a raw Android image named .bin) is a direct partition flash.
        is_raw_image = (os.path.isfile(rom_path) and (
            str(rom_path).lower().endswith((".img", ".img.xz", ".img.gz"))
            or (str(rom_path).lower().endswith(".bin") and looks_like_fastboot_raw_image(rom_path))))
        if is_raw_image:
            part = normalize_partition_name(os.path.basename(rom_path))
            _log("⚠️ GSI / dynamic-partition notice: a single raw image is flashed as one "
                 f"partition ('{part}'). Dynamic partitions usually need super.img or a full "
                 "fastboot flash; verify the device partition layout before continuing.", 25)
            res = self.flash_partition(serial, part, os.path.abspath(rom_path))
            _log(res.get("output", ""), 90)
            if not fastboot_step_ok(res):
                self.is_flashing = False
                return {"success": False, "error": f"Failed to flash {part}", "logs": logs}
            rb = self.reboot(serial, "FASTBOOT", "system")
            self.is_flashing = False
            if not rb.get("success"):
                err = f"Image flashed but reboot failed: {rb.get('error', rb.get('output', 'unknown'))}"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}
            _log("🎉 Single-image flash completed!", 100)
            return {"success": True, "logs": logs}

        # 2. Check if rom_path is an archive or an extracted folder that needs preparation
        work_dir = rom_path
        payload_source = None
        sideload_source = (rom_path if os.path.isfile(rom_path)
                           and str(rom_path).lower().endswith(".zip") else None)
        if os.path.isdir(rom_path) or (os.path.isfile(rom_path) and archive_info(rom_path)[0]):
            prep = self.prepare_and_scan_rom(rom_path, progress_cb=progress_cb)
            if not prep.get("success"):
                _log(f"Error preparing ROM: {prep.get('error')}", 0)
                self.is_flashing = False
                return {"success": False, "error": prep.get("error", "ROM preparation failed"), "logs": logs}
            if prep.get("type") in ("aosp", "aosp_folder"):
                payload_source = prep.get("payload_path") or rom_path
            else:
                work_dir = prep.get("extracted_dir", work_dir)
                if not selected_script and prep.get("scripts"):
                    selected_script = prep["scripts"][0]

        # An explicitly selected concrete ZIP always wins; script names are ignored here.
        if selected_script and os.path.isfile(selected_script) and str(selected_script).lower().endswith(".zip"):
            sideload_source = os.path.abspath(selected_script)

        # For an extracted AOSP folder, rank sideloadable ZIPs: exact root payload.bin
        # first, then largest file size. Never pick an arbitrary first match.
        if os.path.isdir(rom_path) and not (sideload_source and os.path.isfile(sideload_source)):
            zip_candidates = []
            for root, _, files in os.walk(rom_path):
                for f in files:
                    if not f.lower().endswith(".zip"):
                        continue
                    candidate = os.path.join(root, f)
                    try:
                        with zipfile.ZipFile(candidate, 'r') as zf:
                            names = zf.namelist()
                            has_payload = any(is_payload_entry(n) for n in names)
                            root_payload = any(is_payload_entry(n) and "/" not in n.replace("\\", "/")
                                               for n in names)
                            if has_payload:
                                zip_candidates.append((1 if root_payload else 0,
                                                       os.path.getsize(candidate), candidate))
                    except Exception:
                        pass
            if zip_candidates:
                zip_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
                sideload_source = zip_candidates[0][2]
                _log(f"Selected sideload ZIP (root payload={'yes' if zip_candidates[0][0] else 'nested'}, "
                     f"{zip_candidates[0][1]} bytes): {os.path.basename(sideload_source)}", 25)
        if sideload_source:
            _log(f"sideload_source = {sideload_source}", 25)

        # Check for AOSP payload.bin (file archive OR extracted folder)
        rom_info = self.inspect_rom_path(rom_path)
        if rom_info.get("type") in ("aosp", "aosp_folder"):
            payload_source = rom_info.get("payload_path") or payload_source or rom_path
            _log(f"Detected AOSP ROM with payload.bin payload! ({os.path.basename(payload_source)})", 25)
            temp_extract = tempfile.mkdtemp(prefix="aosp_payload_")
            out_images = os.path.join(temp_extract, "images")
            os.makedirs(out_images, exist_ok=True)
            try:
                # 1. Extract core boot partitions directly from payload.bin. Discover the
                #    real targets from the manifest and intersect with the safe allowlist;
                #    the original fixed list is only a fallback.
                _log("Extracting core boot partitions from payload.bin...", 30)
                try:
                    manifest_set = set(list_payload_partition_names(payload_source))
                    core_targets = [p for p in DEFAULT_BOOT_CRITICAL_TARGETS if p in manifest_set]
                    core_targets += [p for p in BOOT_CRITICAL_ALLOWLIST
                                     if p in manifest_set and p not in core_targets]
                    if not core_targets:
                        core_targets = list(DEFAULT_BOOT_CRITICAL_TARGETS)
                    _log(f"Manifest boot-critical targets: {', '.join(core_targets)}", 30)
                except Exception as e:
                    core_targets = list(DEFAULT_BOOT_CRITICAL_TARGETS)
                    _log(f"Notice: payload manifest unavailable ({e}); using default core partitions.", 30)

                avb_disable_needed = rom_requests_avb_disable(rom_path, sideload_source, payload_source, selected_script)
                _log("ROM requests AVB disarm: vbmeta images will use --disable-verity --disable-verification."
                     if avb_disable_needed else "AVB left enabled (ROM did not request a vbmeta disarm).", 50)

                # WARNING only: ported ROMs must never be hard-blocked on a product mismatch.
                try:
                    fb_product_raw = self._get_fastboot_var(serial, "product") or ""
                    rom_basename = os.path.basename(os.path.normpath(rom_path)).lower()
                    rom_codename = next((code for code in FASTBOOT_CODENAME_MAP
                                         if code and re.search(rf'(?<![a-z0-9]){re.escape(code)}(?![a-z0-9])', rom_basename)), "")
                    if fb_product_raw and rom_codename:
                        prod_low = fb_product_raw.lower()
                        if prod_low not in rom_codename and rom_codename not in prod_low:
                            _log(f"⚠️ Product mismatch notice (non-blocking): fastboot product '{fb_product_raw}' "
                                 f"vs ROM codename '{rom_codename}'. Continuing for ported ROMs.", 52)
                except Exception:
                    pass

                extracted_files = extract_payload_images(
                    payload_source, out_images, core_targets,
                    progress_cb=lambda msg, pct: _log(msg, pct),
                    cancel_event=getattr(self, "_auto_flash_cancel_event", None))

                if not extracted_files:
                    _log("❌ Error: Failed to extract core partitions from payload.bin!", 0)
                    return {"success": False, "error": "No core partitions extracted from payload.bin", "logs": logs}

                _log(f"Successfully extracted {len(extracted_files)} core image(s): {', '.join(os.path.basename(f) for f in extracted_files)}", 50)

                flash_failures = []
                flash_ops = 0

                # 2. Detect A/B vs A-Only slots before flashing
                slot_cnt_raw, slot_responded = self._probe_fastboot_var(serial, "slot-count")
                cur_slot_raw, cur_responded = self._probe_fastboot_var(serial, "current-slot")
                if not slot_responded and not cur_responded:
                    err = "Cannot read slot layout from bootloader (getvar timed out); refusing to guess A-only"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}
                is_ab = (slot_cnt_raw.strip() == "2") or bool(cur_slot_raw and cur_slot_raw.strip() in ("a", "b", "_a", "_b"))

                def _flash_command(target: str, img_path: str) -> List[str]:
                    cmd = [self.fastboot_path, "-s", serial]
                    if avb_disable_needed and normalize_partition_name(target).startswith("vbmeta"):
                        cmd.extend(["--disable-verity", "--disable-verification"])
                    cmd.extend(["flash", target, img_path])
                    return cmd

                current_slot = (cur_slot_raw or "").strip().lower().lstrip("_")
                if current_slot not in ("a", "b"):
                    current_slot = "a"
                inactive_slot = "b" if current_slot == "a" else "a"

                if is_ab:
                    _log(f"A/B device: flashing authoritative current slot {current_slot.upper()} first, "
                         f"then inactive slot {inactive_slot.upper()}...", 55)
                    for p in core_targets:
                        p_img = os.path.join(out_images, f"{p}.img")
                        if os.path.exists(p_img) and os.path.getsize(p_img) > 0:
                            current_ok = False
                            for slot, is_current in ((current_slot, True), (inactive_slot, False)):
                                _cancel_check(f"flashing {p}")
                                target = f"{p}_{slot}"
                                _log(f"⚡ Flashing [{p}] -> Slot {slot.upper()}...", 60)
                                res_slot = self.run_cmd(_flash_command(target, p_img), timeout=180)
                                for c_line in clean_fastboot_log(res_slot.get("output", "")):
                                    _log(c_line, 62)
                                if fastboot_step_ok(res_slot):
                                    if is_current:
                                        current_ok = True
                                    continue
                                # Per-target fallback: try the unsuffixed partition name
                                # as soon as this slot's own target fails.
                                res_plain = self.run_cmd(_flash_command(p, p_img), timeout=180)
                                for c_line in clean_fastboot_log(res_plain.get("output", "")):
                                    _log(c_line, 66)
                                if fastboot_step_ok(res_plain):
                                    _log(f"Fallback unsuffixed target '{p}' worked for slot {slot.upper()}.", 66)
                                    if is_current:
                                        current_ok = True
                                    continue
                                if is_current:
                                    flash_failures.append(f"{p} (current slot {slot.upper()})")
                                else:
                                    _log(f"⚠️ Inactive slot {slot.upper()} flash of '{p}' failed; "
                                         "continuing (current slot is authoritative).", 66)
                            if current_ok:
                                flash_ops += 1

                    _log(f"Setting active slot to Slot {current_slot.upper()} (current slot is authoritative)...", 68)
                    res_active = self.run_cmd([self.fastboot_path, "-s", serial, "set_active", current_slot], timeout=30)
                    if not fastboot_step_ok(res_active):
                        flash_failures.append("set_active")
                else:
                    _log("A-Only (Non-A/B) device detected. Flashing single-slot partitions...", 55)
                    for p in core_targets:
                        p_img = os.path.join(out_images, f"{p}.img")
                        if os.path.exists(p_img) and os.path.getsize(p_img) > 0:
                            _cancel_check(f"flashing {p}")
                            _log(f"⚡ Flashing [{p}]...", 62)
                            res_plain = self.run_cmd(_flash_command(p, p_img), timeout=180)
                            for c_line in clean_fastboot_log(res_plain.get("output", "")):
                                _log(c_line, 66)
                            if fastboot_step_ok(res_plain):
                                flash_ops += 1
                            else:
                                flash_failures.append(p)

                if flash_failures:
                    err = f"Core partition flash failed: {', '.join(flash_failures)}"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}
                if flash_ops == 0:
                    err = "No core partition images were flashed from payload.bin"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}

                if not sideload_source:
                    err = "Selected folder contains payload.bin but no ROM ZIP for ADB sideload; the full ROM cannot be installed"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}

                # 4. Clean Format Data (Erase Userdata & Metadata) in Fastboot mode before Recovery
                _log("Wiping userdata & metadata for Clean Flash...", 72)
                erase_u = self.run_cmd([self.fastboot_path, "-s", serial, "erase", "userdata"], timeout=60)
                if erase_u.get("output"):
                    for c_line in clean_fastboot_log(erase_u["output"]):
                        _log(c_line, 73)

                erase_m = self.run_cmd([self.fastboot_path, "-s", serial, "erase", "metadata"], timeout=30)
                if erase_m.get("output"):
                    for c_line in clean_fastboot_log(erase_m["output"]):
                        _log(c_line, 74)

                wipe_failures = []
                if not fastboot_step_ok(erase_u):
                    wipe_failures.append("userdata")
                if not fastboot_step_ok(erase_m):
                    # Protected/missing metadata must never fail an otherwise good flash.
                    _log("⚠️ fastboot erase metadata was not successful (unsupported/protected). "
                         "Continuing; this is not fatal.", 74)
                if wipe_failures:
                    # Fallback to fastboot -w if userdata erase is not supported by OEM
                    res_w = self.run_cmd([self.fastboot_path, "-s", serial, "-w"], timeout=120)
                    for c_line in clean_fastboot_log(res_w.get("output", "")):
                        _log(c_line, 74)
                    if not fastboot_step_ok(res_w):
                        err = f"Wipe failed for: {', '.join(wipe_failures)}"
                        _log(f"❌ Error: {err}", 0)
                        return {"success": False, "error": err, "logs": logs}
                    _log("Fallback fastboot -w wipe completed successfully.", 75)
                else:
                    _log("✅ Userdata wiped cleanly! (metadata result is non-fatal)", 75)

                # 5. Program Bootloader Control Block (BCB) for direct ADB Sideload & auto-reboot
                _log("Injecting BCB Direct Sideload command into misc partition...", 76)
                misc_ok = self.write_misc_sideload_command(serial)
                if misc_ok:
                    _log("✅ BCB Direct Sideload flag injected into misc partition!", 77)
                else:
                    _log("Notice: misc partition write skipped/protected by bootloader.", 77)

                # Reboot target phone to Recovery Sideload (Always use reboot recovery across all OEMs)
                _log("Rebooting target phone to automated Recovery Sideload...", 78)
                self.reboot(serial, "FASTBOOT", "recovery")

                _log("Waiting for direct ADB Sideload connection...", 80)
                _log("⚡ Auto-Detect Sentinel Active: Monitoring USB handoff...", 81)

                rec_serial = serial
                sideload_ready = False
                wait_start = time.time()
                max_sideload_wait = 180  # patient adaptive wait for cold boot into recovery
                last_sideload_trigger = 0

                poll_count = 0
                while (time.time() - wait_start) < max_sideload_wait:
                    poll_count += 1
                    time.sleep(1.5)
                    _cancel_check("waiting for sideload")
                    elapsed = int(time.time() - wait_start)

                    all_devs = self.detect_devices(bypass_cache=True)

                    # 1. Check for active Sideload device - exact requested serial only
                    sideload_match = self._find_device_exact(all_devs, serial, "ADB")
                    if sideload_match and str(sideload_match.get("state", "")).lower() == "sideload":
                        _log(f"✅ Sideload mode connected! Device: {rec_serial}", 85)
                        _log("Starting automated ROM streaming...", 86)
                        sideload_ready = True
                        break

                    # 2. Check for ADB device at Recovery Menu ('Apply update' screen) and auto-switch to Sideload
                    adb_recovery = self._find_device_exact(all_devs, serial, "ADB")
                    if adb_recovery and str(adb_recovery.get("state", "")).lower() == "recovery" and (not last_sideload_trigger or (time.time() - last_sideload_trigger) > 8):
                        last_sideload_trigger = time.time()
                        a_serial = adb_recovery["serial"]
                        _log(f"⚡ Device reached Recovery Menu ({a_serial}). Auto-switching to ADB Sideload...", 83)
                        # Trigger automated sideload handoff via ADB (No manual screen touch required!)
                        self.run_cmd([self.adb_path, "-s", a_serial, "reboot", "sideload"], timeout=10)
                        # Fallback for recoveries with root shell
                        self.run_cmd([self.adb_path, "-s", a_serial, "shell", "recovery", "--sideload"], timeout=5)

                    # 3. Check for general ADB device if not in sideload or recovery
                    elif not sideload_match:
                        adb_other = self._find_device_exact(all_devs, serial, "ADB")
                        if adb_other and str(adb_other.get("state", "")).lower() not in ("sideload", "recovery") and (not last_sideload_trigger or (time.time() - last_sideload_trigger) > 10):
                            last_sideload_trigger = time.time()
                            self.run_cmd([self.adb_path, "-s", adb_other["serial"], "reboot", "sideload"], timeout=10)

                    # 4. Check if device is still in Fastboot mode (if normal reboot didn't register after 10s, send fastboot reboot recovery)
                    fb_match = self._find_device_exact(all_devs, serial, "FASTBOOT")
                    if fb_match and elapsed > 10 and elapsed % 12 == 0:
                        self.run_cmd([self.fastboot_path, "-s", fb_match["serial"], "reboot", "recovery"], timeout=10)

                    # 5. Clean, reassuring heartbeat log
                    if poll_count % 4 == 0:
                        _log(f"⏳ Waiting for Sideload connection ({elapsed}s elapsed)...", 82)

                if not sideload_ready:
                    chk_devs = self.detect_devices(bypass_cache=True)
                    chk_s = self._find_device_exact(chk_devs, serial, "ADB")
                    if chk_s and str(chk_s.get("state", "")).lower() == "sideload":
                        sideload_ready = True

                if not sideload_ready:
                    _log("❌ Error: Device did not enter Sideload mode within timeout.", 0)
                    _log("To protect your device, sideload transfer was paused. Please ensure phone is connected and retry.", 0)
                    return {
                        "success": False,
                        "error": "Device did not enter Sideload mode",
                        "logs": logs
                    }

                # Stabilize USB connection before starting transfer
                _log("Stabilizing ADB sideload connection...", 86)
                time.sleep(2.0)

                # 5. Execute ADB Sideload with Adaptive Retry
                _log(f"Executing ADB Sideload of full ROM: {os.path.basename(rom_path)}...", 87)
                _log(f"Selected sideload_source: {sideload_source}", 87)
                _log("Streaming AOSP ROM Zip package to device... (Do NOT disconnect cable)", 88)

                is_success = False
                early_reboot_sent = False
                early_reboot_thread = None
                last_err = "Connection closed"
                completion_phrases = (
                    "install completed",
                    "install successful",
                    "install succeeded",
                    "install from adb completed with status 0",
                    "update package execution finished",
                    "zip install ok",
                )
                # Full-line patterns that are expected after an intentional early reboot or
                # key fallback. Previously only the matched TERM was checked, so a line like
                # "error: device not found" still failed the flash.
                tolerated_line_patterns = (
                    r'^error:\s*device not found\b',
                    r'^error:\s*closed\b',
                    r'^error:\s*device offline\b',
                    r'failed to verify .*trying alternate key',
                    r'^connection closed\b',
                    r'^device not found\b',
                    r'\boffline\b',
                )

                def _is_tolerated_line(line: str) -> bool:
                    ll = (line or "").strip().lower()
                    return any(re.search(pat, ll) for pat in tolerated_line_patterns)

                def _xfer_succeeded(text: str) -> bool:
                    values = [float(m.group(1)) for m in re.finditer(
                        r'total\s+xfer:\s*([0-9]+(?:\.[0-9]+)?)', text or "")] 
                    return any(v >= 0.99 for v in values)

                def _fire_early_reboot(reason: str):
                    nonlocal early_reboot_sent, early_reboot_thread
                    if early_reboot_sent:
                        return
                    early_reboot_sent = True
                    _log(f"⚡ {reason} — rebooting immediately to bypass the 'additional packages' prompt...", 96)
                    early_reboot_thread = threading.Thread(
                        target=self._try_recovery_reboot, args=(rec_serial,), daemon=True)
                    early_reboot_thread.start()

                def _join_early_reboot():
                    if early_reboot_thread is not None:
                        try:
                            early_reboot_thread.join(timeout=12)
                        except Exception:
                            pass

                # Generous, configurable guard - only a last resort for a truly stalled transfer.
                try:
                    sideload_timeout_sec = max(300, int(os.environ.get("ROM_FLASHER_SIDELOAD_TIMEOUT", "900") or 900))
                except (TypeError, ValueError):
                    sideload_timeout_sec = 900

                for attempt in range(1, 3):
                    if attempt > 1:
                        # A detached reboot thread must never fire during a retry.
                        _join_early_reboot()
                        _log(f"Notice: Sideload stream interrupted ({last_err}). Stabilizing connection for auto-retry...", 88)
                        time.sleep(3.0)
                        chk_now = self.detect_devices(bypass_cache=True)
                        m_side = self._find_device_exact(chk_now, serial, "ADB")
                        if not m_side or str(m_side.get("state", "")).lower() != "sideload":
                            last_err = self._device_not_found_error(serial, "ADB sideload")
                            _log(f"❌ {last_err}", 0)
                            break
                        _log("Retrying ADB Sideload transfer...", 88)

                    c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    cmd_sideload = [self.adb_path, "-s", rec_serial, "sideload", sideload_source]
                    proc_side = subprocess.Popen(
                        cmd_sideload,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        creationflags=c_flags,
                        env=os.environ.copy()
                    )

                    sideload_lines = []
                    q_side = queue.Queue()

                    def _enqueue_output(out_pipe, q):
                        try:
                            for raw_line in iter(out_pipe.readline, ''):
                                if not raw_line:
                                    break
                                q.put(raw_line)
                        except Exception:
                            pass
                        finally:
                            try:
                                out_pipe.close()
                            except Exception:
                                pass

                    reader_t = threading.Thread(target=_enqueue_output, args=(proc_side.stdout, q_side), daemon=True)
                    reader_t.start()

                    last_logged_pct = -1
                    last_heartbeat = -1
                    attempt_started = time.time()
                    timed_out = False

                    while True:
                        _cancel_check("sideload transfer")
                        # 1. Read available output lines from queue
                        try:
                            s_line = q_side.get(timeout=0.5)
                            sl = s_line.strip()
                            if sl:
                                sideload_lines.append(sl)
                                sl_low = sl.lower()
                                # Reboot on ANY host/device completion signal, including the
                                # common stock-AOSP "Total xfer: 1.00x" line.
                                if not early_reboot_sent and (
                                        any(t in sl_low for t in completion_phrases)
                                        or _xfer_succeeded(sl_low)):
                                    _fire_early_reboot("Sideload completion signal detected")
                                if "serving" in sl_low or "%" in sl:
                                    m_pct = re.search(r'(\d+)%', sl)
                                    if m_pct:
                                        pct_num = int(m_pct.group(1))
                                        if pct_num != last_logged_pct:
                                            last_logged_pct = pct_num
                                            p_val = 88 + int(pct_num * 0.08)
                                            _log(sl, min(96, p_val))
                                else:
                                    _log(sl, 96)
                        except queue.Empty:
                            pass

                        # 2. Check if adb sideload process exited on its own
                        if proc_side.poll() is not None:
                            # Let the reader push the final completion/xfer line into the
                            # queue BEFORE draining it (otherwise the last line is lost).
                            reader_t.join(timeout=2)
                            while not q_side.empty():
                                try:
                                    rem_l = q_side.get_nowait().strip()
                                    if rem_l:
                                        sideload_lines.append(rem_l)
                                        _log(rem_l, 96)
                                except queue.Empty:
                                    break
                            break

                        # 3. Heartbeat + true last-resort timeout (no fixed 55s kill)
                        elapsed = time.time() - attempt_started
                        hb = int(elapsed // 30)
                        if hb > last_heartbeat:
                            last_heartbeat = hb
                            _log(f"⏳ ADB sideload still in progress ({int(elapsed)}s / {sideload_timeout_sec}s timeout)...", 96)
                        if elapsed >= sideload_timeout_sec:
                            timed_out = True
                            _log(f"⚠️ Sideload exceeded the {sideload_timeout_sec}s timeout. Terminating the stalled transfer as a last resort...", 0)
                            try:
                                proc_side.kill()
                            except Exception:
                                pass
                            break

                    # Reap the process (avoids zombies/unread pipes after a timeout kill).
                    if timed_out:
                        try:
                            proc_side.communicate(timeout=10)
                        except Exception:
                            pass
                    else:
                        try:
                            reader_t.join(timeout=2)
                        except Exception:
                            pass
                    side_exit = proc_side.poll()
                    all_side_out = "\n".join(sideload_lines)
                    low_out = all_side_out.lower()

                    if timed_out:
                        last_err = f"ADB sideload timed out after {sideload_timeout_sec}s"
                        _log(f"❌ [ADB Sideload Error] {last_err}", 0)
                        break

                    # Final fallback: the process has been reaped, so a short stabilization
                    # pause is enough before issuing a reboot if no earlier signal was seen.
                    if not early_reboot_sent:
                        time.sleep(0.4)
                        _fire_early_reboot("Sideload process exited")

                    # Determine success FIRST. Explicit device phrases win even on a
                    # non-zero host exit; otherwise exit 0 + Total xfer >= 0.99 is enough.
                    genuine_install_failure = any(
                        "install failed" in ln.lower() for ln in sideload_lines if not _is_tolerated_line(ln))
                    explicit_completion = (any(t in low_out for t in completion_phrases)
                                           and not genuine_install_failure)
                    if ("update package execution finished" in low_out
                            and ("success" in low_out or "zip install ok" in low_out)
                            and not genuine_install_failure):
                        explicit_completion = True
                    xfer_ok = _xfer_succeeded(low_out)
                    success_by_exit_xfer = (side_exit == 0 and xfer_ok and not genuine_install_failure)
                    attempt_success = explicit_completion or success_by_exit_xfer

                    if not attempt_success:
                        # Only now apply hard failures, checking the ACTUAL lines (full-line
                        # whitelist) instead of comparing a search term to tolerated terms.
                        hard_terms = ("install failed", "adb: failed", "connection closed", "failed to verify", "error:")
                        hard_lines = [ln for ln in sideload_lines
                                      if any(t in ln.lower() for t in hard_terms)
                                      and not _is_tolerated_line(ln)]
                        if hard_lines:
                            last_err = "Recovery/ADB reported failure: " + "; ".join(hard_lines[:3])
                            _log(f"❌ [ADB Sideload Error] {last_err}", 0)
                            _join_early_reboot()
                            if any("install failed" in ln.lower() for ln in hard_lines):
                                break
                            continue
                        if side_exit != 0:
                            last_err = f"adb sideload exited with code {side_exit}"
                            _log(f"❌ [ADB Sideload Error] {last_err}", 0)
                            _join_early_reboot()
                            continue
                        last_err = ("adb sideload finished without a completion phrase "
                                    "or Total xfer >= 0.99")
                        _log(f"❌ [ADB Sideload Error] {last_err}", 0)
                        _join_early_reboot()
                        continue

                    if not explicit_completion:
                        _log("⚠️ Device-side completion phrase was not visible, but ADB reported "
                             "Total xfer >= 0.99 and exited cleanly. Treating as success; the "
                             "reboot/verification below will confirm the device state.", 96)
                    else:
                        shown = next((t for t in completion_phrases if t in low_out), "completion phrase")
                        _log(f"✅ Sideload verified: {('exit code 0 and ' if side_exit == 0 else '')}"
                             f"recovery/ADB reported '{shown}'.", 96)

                    is_success = True
                    break

                # Never leave a detached reboot thread running into the next phase/retry.
                _join_early_reboot()

                if not is_success:
                    _log(f"❌ [ADB Sideload Error] Sideload transfer failed: {last_err}", 0)
                    if early_reboot_sent:
                        _log("A reboot had already been issued at completion; check the phone's current mode before retrying.", 0)
                    else:
                        _log("To protect your device, system reboot was NOT executed. Please select 'Apply from ADB' on phone recovery and retry.", 0)
                    return {
                        "success": False,
                        "error": f"ADB Sideload failed: {last_err}",
                        "logs": logs
                    }

                # 6. Post-Flash: reboot out of recovery immediately, then verify final state.
                _log("=============================================", 97)
                _log("🎉 [SIDELOAD VERIFIED] Full ROM package successfully written to partitions!", 97)
                _log("⚡ Auto-Bypassing recovery prompts: Triggering Clean Format Data & Auto-Reboot...", 97)

                # sendevent on /dev/input was unreliable (permissions/key mapping differ by recovery).
                # Reboot via ADB itself, ideally already fired the moment completion was reported.
                rb = self._try_recovery_reboot(rec_serial)
                if not rb.get("success"):
                    _log("⚠️ First reboot not acknowledged — retrying immediately...", 98)
                    rb = self._try_recovery_reboot(rec_serial)
                if not rb.get("success"):
                    _log("⚠️ ADB reboot was not acknowledged. Watching for Fastboot directly...", 98)

                _log("Waiting for bootloader connection to finalize Clean Format Data...", 98)
                fb_dev = None
                wait_fb_start = time.time()
                max_fb_wait = 40  # seconds
                last_wait_log = 0
                while (time.time() - wait_fb_start) < max_fb_wait:
                    time.sleep(1.5)
                    _cancel_check("waiting for fastboot after sideload")
                    devs_now = self.detect_devices(bypass_cache=True)
                    fb_dev = self._find_device_exact(devs_now, serial, "FASTBOOT")
                    if fb_dev:
                        break
                    adb_now = self._find_device_exact(devs_now, serial, "ADB")
                    if adb_now and str(adb_now.get("state", "")).lower() not in ("sideload", "recovery"):
                        break  # already rebooted straight into Android
                    elapsed_wait = int(time.time() - wait_fb_start)
                    if elapsed_wait - last_wait_log >= 8:
                        last_wait_log = elapsed_wait
                        _log(f"⏳ Waiting for Fastboot after sideload ({elapsed_wait}s / {max_fb_wait}s)...", 98)

                # Last-resort visible handoff: never sit silently at 99%.
                if not fb_dev:
                    stuck = self._find_device_exact(self.detect_devices(bypass_cache=True), serial, "ADB")
                    if stuck and str(stuck.get("state", "")).lower() in ("sideload", "recovery"):
                        _log("⚠️ Phone is still on the recovery 'Install additional packages?' menu.", 98)
                        _log("👉 On the phone: press 'No', then choose 'Reboot to Bootloader'. Waiting up to 60s...", 98)
                        wait2_start = time.time()
                        while (time.time() - wait2_start) < 60:
                            time.sleep(2)
                            devs2 = self.detect_devices(bypass_cache=True)
                            fb_dev = self._find_device_exact(devs2, serial, "FASTBOOT")
                            if fb_dev:
                                break
                            adb2 = self._find_device_exact(devs2, serial, "ADB")
                            if adb2 and str(adb2.get("state", "")).lower() not in ("sideload", "recovery"):
                                break

                if fb_dev:
                    fb_serial = fb_dev["serial"]
                    _log(f"⚡ Fastboot mode detected ({fb_serial})! Executing hardware-level Clean Format Data...", 98)

                    # Clear a stale BCB BEFORE rebooting system; otherwise a completed
                    # sideload can loop straight back into the sideload menu.
                    res_misc = self.run_cmd([self.fastboot_path, "-s", fb_serial, "erase", "misc"], timeout=30)
                    for c_line in clean_fastboot_log(res_misc.get("output", "")):
                        _log(c_line, 98)
                    if not fastboot_step_ok(res_misc):
                        _log("⚠️ fastboot erase misc failed; retrying once to clear the stale sideload BCB...", 98)
                        res_misc2 = self.run_cmd([self.fastboot_path, "-s", fb_serial, "erase", "misc"], timeout=30)
                        for c_line in clean_fastboot_log(res_misc2.get("output", "")):
                            _log(c_line, 98)
                        if not fastboot_step_ok(res_misc2):
                            _log("Notice: misc/BCB could not be cleared; continuing and watching for a sideload loop.", 98)

                    res_u = self.run_cmd([self.fastboot_path, "-s", fb_serial, "erase", "userdata"], timeout=60)
                    for c_line in clean_fastboot_log(res_u.get("output", "")):
                        _log(c_line, 98)
                    res_m = self.run_cmd([self.fastboot_path, "-s", fb_serial, "erase", "metadata"], timeout=30)
                    for c_line in clean_fastboot_log(res_m.get("output", "")):
                        _log(c_line, 99)

                    if not fastboot_step_ok(res_m):
                        _log("⚠️ Post-sideload erase metadata failed/was protected; continuing (non-fatal).", 99)
                    if not fastboot_step_ok(res_u):
                        res_w = self.run_cmd([self.fastboot_path, "-s", fb_serial, "-w"], timeout=120)
                        for c_line in clean_fastboot_log(res_w.get("output", "")):
                            _log(c_line, 99)
                        if not fastboot_step_ok(res_w):
                            err = "Post-sideload userdata wipe failed (fastboot -w fallback also failed)"
                            _log(f"❌ Error: {err}", 0)
                            return {"success": False, "error": err, "logs": logs}

                    _log("✅ Clean Format Data completed; BCB cleared before system boot!", 99)
                    _log("Rebooting device into new Android OS...", 99)
                    rb_final = self.reboot(fb_serial, "FASTBOOT", "system")
                    if not rb_final.get("success"):
                        err = f"Flash finished but reboot failed: {rb_final.get('error', rb_final.get('output', 'unknown'))}"
                        _log(f"❌ Error: {err}", 0)
                        return {"success": False, "error": err, "logs": logs}
                else:
                    adb_now = self._find_device_exact(self.detect_devices(bypass_cache=True), serial, "ADB")
                    if adb_now and str(adb_now.get("state", "")).lower() not in ("sideload", "recovery"):
                        _log("✅ Device has rebooted directly into Android System!", 99)
                    else:
                        err = self._device_not_found_error(serial, "FASTBOOT or Android") + " Device did not leave recovery after sideload."
                        _log(f"❌ Error: {err}", 0)
                        return {"success": False, "error": err, "logs": logs}

                # Verify final device state before claiming success. A visible but
                # unauthorized/offline device is NOT accepted as a successful boot.
                boot_err = _verify_final_boot()
                if boot_err:
                    return {"success": False, "error": boot_err, "logs": logs}

                _log("=============================================", 100)
                _log("🎉 [SUCCESS] AOSP ROM FLASHED SUCCESSFULLY!", 100)
                _log("Target phone is now booting into the new ROM!", 100)
                return {"success": True, "logs": logs}
            except DeltaPayloadUnsupportedError as e:
                _log(f"❌ [CASE A Error] {e}", 0)
                return {"success": False, "error": str(e), "error_code": e.code,
                        "partition": e.partition, "logs": logs}
            except Exception as e:
                _log(f"❌ [CASE A Error] {e}", 0)
                return {"success": False, "error": str(e), "logs": logs}
            finally:
                self.is_flashing = False
                shutil.rmtree(temp_extract, ignore_errors=True)

        # ----------------------------------------------------
        # CASE B: FASTBOOT ROM (Folder or Script with ARB Bypass)
        # ----------------------------------------------------
        self.is_flashing = False
        # Recursive indexes: scripts and images may live in images/ or other subfolders.
        image_paths = image_index(work_dir)
        scripts = script_index(work_dir)
        script_file = os.path.basename(str(selected_script or ""))
        script_path = ""

        if script_file:
            script_path = scripts.get(script_file.lower(), "")
            if not script_path:
                direct = (script_file if os.path.isabs(script_file)
                          else os.path.join(work_dir, script_file))
                if os.path.isfile(direct):
                    script_path = direct
        if not script_path:
            for cand in ("flash_all.sh", "flash-all.sh", "flash_all.bat", "flash-all.bat",
                         "flash_all_except_data_storage.bat", "flash_all_except_data_storage.sh",
                         "flash_all.cmd", "flash_all_lock.bat"):
                if cand.lower() in scripts:
                    script_path = scripts[cand.lower()]
                    break
        if not script_path and scripts:
            ordered = sorted(scripts, key=lambda n: (0 if "all" in n else 1,
                                                     0 if n.endswith(".sh") else 1))
            script_path = scripts[ordered[0]]
        if script_path:
            script_file = os.path.basename(script_path)
            # Nested ROMs resolve their relative images from the SELECTED script's folder.
            work_dir = os.path.dirname(script_path)
        elif image_paths:
            # No script: use the folder where most partition images live.
            work_dir = dominant_image_dir(work_dir)

        if not script_path:
            # Fail closed: never report success when there is nothing flashable.
            expected_imgs = ["boot.img", "init_boot.img", "recovery.img", "vbmeta.img", "dtbo.img",
                             "vendor_boot.img", "system.img", "vendor.img", "product.img", "super.img"]
            has_images = any(name.lower() in expected_imgs for name in image_paths)
            if not has_images:
                err = f"No flash script (.bat/.cmd/.sh), payload.bin or expected ROM images found in {work_dir}"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}

        if script_path and script_path.lower().endswith(".sh"):
            _log(f"Executing Linux/AOSP Shell Flash Script natively: {os.path.basename(script_path)}", 35)
            commands, parse_warnings = parse_fastboot_script_commands(script_path, work_dir)
            for warning in parse_warnings:
                _log(f"⚠️ {warning}", 38)
            if not commands:
                err = "Shell flash script contained no executable fastboot command"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}
            self.is_flashing = True
            sh_failures = []
            commands_ok = 0
            try:
                total_cmds = len(commands)
                for idx, entry in enumerate(commands, 1):
                    _cancel_check("shell flash script")
                    tokens = entry["tokens"]
                    pct_now = min(96, 40 + int((idx / total_cmds) * 55))
                    cmd_label = ' '.join(tokens[:3])
                    _log(f"▶ fastboot {cmd_label} (line {entry['line']})", pct_now)
                    r = self.run_cmd([self.fastboot_path, "-s", serial] + tokens,
                                     timeout=entry["timeout"])
                    _log(r.get("output", "OK"), pct_now)
                    if fastboot_step_ok(r):
                        commands_ok += 1
                    else:
                        sh_failures.append(f"line {entry['line']}: {cmd_label}")
            finally:
                self.is_flashing = False
            if sh_failures:
                err = f"Shell flash command(s) failed: {', '.join(sh_failures)}"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}
            if commands_ok == 0:
                err = "Shell flash script ran no successful fastboot command"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}
            # Some scripts reboot themselves; only issue a reboot if still in fastboot.
            fb_chk = self.run_cmd([self.fastboot_path, "-s", serial, "devices"], timeout=4)
            if fastboot_devices_has_serial(fb_chk, serial):
                rb = self.reboot(serial, "FASTBOOT", "system")
                if not rb.get("success"):
                    err = f"Shell flash finished but reboot failed: {rb.get('error', rb.get('output', 'unknown'))}"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}
            boot_err = _verify_final_boot()
            if boot_err:
                return {"success": False, "error": boot_err, "logs": logs}
            _log("🎉 Shell ROM Flash Completed Successfully!", 100)
            return {"success": True, "logs": logs}

        if os.path.exists(script_path):
            _log(f"Analyzing OEM Fastboot Script: {os.path.basename(script_path)}", 30)

            with open(script_path, 'r', encoding='utf-8', errors='ignore') as sf:
                script_lines = sf.readlines()

            # 🛡️ 1. DEVICE MISMATCH HARDWARE GUARD (Prevent flashing wrong phone ROM)
            dev_prod = self._get_fastboot_var(serial, "product")
            if not dev_prod:
                dev_prod = self._get_prop(serial, "ro.product.device") or self._get_prop(serial, "ro.build.product")
            if dev_prod:
                dev_prod = self._clean_var(dev_prod).lower()

            target_prods = []
            # High-confidence metadata ONLY: explicit findstr product checks in the OEM
            # script, including /c:"^product: *marble" and /c alternation forms.
            for s_line in script_lines:
                if "getvar product" not in s_line.lower() or "findstr" not in s_line.lower():
                    continue
                fragments = re.findall(r'/c\s*:\s*"([^"]+)"', s_line, re.I)
                if not fragments:
                    fragments = re.findall(r'findstr(?:\s+/[a-z]+)*\s+["\']?([^"\'\r\n|&]+)["\']?',
                                           s_line, re.I)
                for frag in fragments:
                    # Formats: ^product: marble, ^product: *marble, product:marble,
                    # and findstr /r "^product: marble" without /c:.
                    m = re.match(r'^\^?\s*product\s*:\s*\**\s*([A-Za-z0-9_-]+)', frag.strip(), re.I)
                    if m:
                        candidate = m.group(1).lower()
                        if candidate not in target_prods:
                            target_prods.append(candidate)
                    elif not re.search(r'product\s*:', frag, re.I):
                        cleaned = re.sub(r'[\^$*:]+', '', frag).strip().lower().replace("product", "").strip()
                        for token in cleaned.split():
                            token = token.strip()
                            if token and token.isalnum() and len(token) >= 3 and token not in target_prods:
                                target_prods.append(token)
            target_prods = list(dict.fromkeys(target_prods))

            if not target_prods:
                # Folder-name inference is low confidence and MUST NOT hard-block a
                # ported ROM: warn only never add to target_prods.
                folder_base = os.path.basename(work_dir).lower()
                guessed = next((code for code in FASTBOOT_CODENAME_MAP
                                if re.search(rf'(?<![a-z0-9]){re.escape(code)}(?![a-z0-9])', folder_base)), "")
                if guessed:
                    _log(f"Low-confidence codename hint from folder name: '{guessed}' "
                         "(not used for a hard block; ported ROMs are allowed).", 32)

            if dev_prod and target_prods:
                # Prefix matching accepted unrelated codenames (e.g. 'mione' for
                # 'mione_plus'). Only strip explicit regional suffixes, then
                # require equality so a different device cannot slip through.
                def _codename_key(value: str) -> str:
                    return re.sub(r"[_-](?:global|global_nfc|nfc|cn|eu|in)$", "", str(value or "").strip().lower())

                dev_key = _codename_key(dev_prod)
                match_ok = any(_codename_key(tp) == dev_key for tp in target_prods)
                if not match_ok:
                    _log(f"❌ [CRITICAL BRICK SHIELD ACTIVE] Device Mismatch Detected!", 0)
                    _log(f"Connected Phone Hardware: [{dev_prod}]", 0)
                    _log(f"Target ROM Device: [{', '.join(target_prods)}]", 0)
                    _log("Flashing this ROM will PERMANENTLY HARD-BRICK your device!", 0)
                    _log("Execution terminated to safeguard your hardware.", 0)
                    return {
                        "success": False,
                        "error": f"Device Mismatch: Connected phone is '{dev_prod}', but this ROM is for '{', '.join(target_prods)}'. Flashing blocked to protect your phone!",
                        "logs": logs
                    }
                else:
                    _log(f"🛡️ [BrickShield Verified] Device codename '{dev_prod}' matches ROM target '{', '.join(target_prods)}'!", 33)

            # 🛡️ 2. CROSS-REGION BOOTLOADER RE-LOCKING HAZARD GUARD
            # "flash_all_unlock.bat" is NOT a lock script; only an explicit lock token counts.
            script_stem = os.path.splitext(script_file)[0].lower()
            script_tokens = set(re.findall(r'[a-z]+', script_stem))
            is_lock_script = bool(script_tokens & {"lock", "locked", "locking"}) or any(
                re.search(r'\boem\s+lock\b|\bflashing\s+lock\b', l.lower()) for l in script_lines)
            is_cross_region_lock_blocked = False

            if is_lock_script:
                def _region_tokens(raw):
                    toks = set(re.findall(r'[a-z]+|\d+', str(raw or "").lower()))
                    aliases = {"china": "cn", "chinese": "cn", "india": "in",
                               "global": "gl", "europe": "eea", "russia": "ru"}
                    for src, target in aliases.items():
                        if src in toks:
                            toks.add(target)
                    return toks

                rom_region = None
                region_candidates = [
                    os.path.join(work_dir, sub, name)
                    for sub in ("", "images", "metadata")
                    for name in ("flash_region_info.txt", "regions.txt", "region.txt",
                                 "region_info.txt", "regions", "region_info")
                ]
                for root, _, files in os.walk(work_dir):
                    for f in files:
                        if f.lower().endswith((".txt", ".info", ".prop")) and "region" in f.lower():
                            region_candidates.append(os.path.join(root, f))
                for rf in region_candidates:
                    if os.path.isfile(rf):
                        try:
                            with open(rf, "r", encoding="utf-8", errors="ignore") as f_r:
                                text = f_r.read().strip().lower()
                            if text:
                                rom_region = text
                                break
                        except Exception:
                            pass

                dev_hwc = self._get_fastboot_var(serial, "ro.boot.hwc") or self._get_fastboot_var(serial, "hwc") or self._get_fastboot_var(serial, "sku")
                if not dev_hwc:
                    dev_hwc = self._get_prop(serial, "ro.boot.hwc") or self._get_prop(serial, "ro.boot.sku")

                if rom_region and dev_hwc:
                    # Token comparison only: "in" must not match inside "singapore".
                    d_toks = _region_tokens(dev_hwc)
                    r_toks = _region_tokens(rom_region)
                    dev_cn = bool(d_toks & {"cn", "china"})
                    dev_in = bool(d_toks & {"in", "india"})
                    rom_cn = bool(r_toks & {"cn", "china"})
                    rom_globalish = bool(r_toks & {"in", "india", "global", "gl", "eea", "eu", "ru", "russia"})
                    if dev_cn and rom_globalish:
                        is_cross_region_lock_blocked = True
                    elif dev_in and (rom_cn or bool(r_toks & {"global", "gl"})):
                        is_cross_region_lock_blocked = True
                elif rom_region:
                    chk = self.run_cmd([self.fastboot_path, "-s", serial, "oem", "flash_check", rom_region], timeout=8)
                    chk_out = chk.get("output", "").lower()
                    if "mix flash is not allowed" in chk_out or chk_out.startswith("failed"):
                        is_cross_region_lock_blocked = True

                if is_cross_region_lock_blocked:
                    _log("🚫 [CRITICAL BRICK SHIELD ACTIVE] Cross-Region Bootloader Re-Locking Prohibited!", 34)
                    _log(f"Device Hardware: [{dev_hwc or 'Detected foreign'}] vs ROM Region: [{rom_region or 'Cross-region'}]", 34)
                    _log("Locking the bootloader on cross-region firmware causes an immediate PERMANENT HARD-BRICK ('This MIUI/HyperOS version cannot be installed on this device').", 34)
                    _log("For your safety, the bootloader lock command has been disarmed. Safe Clean Flash without locking will execute.", 34)

            _log("Applying Anti-Rollback (ARB) Bypass (Bypassing Android 16 -> 15 downgrade locks)...", 35)
            arb_val = self._get_fastboot_var(serial, "anti")
            if arb_val and arb_val.strip().isdigit() and int(arb_val.strip()) > 0:
                _log(f"⚠️ [Hardware ARB Warning] Device reports active Anti-Rollback index: anti={arb_val.strip()}. Ensure target ROM ARB >= {arb_val.strip()} to prevent EDL hard-brick!", 35)

            clean_lines = ["@echo off\n"]
            for line in script_lines:
                l_lower = line.lower()
                # 1. Antirollback check line - replace safely with @echo (never :: inside parentheses)
                if "antirollback check error" in l_lower or "current device antirollback version" in l_lower:
                    clean_lines.append("@echo [ROM Flasher] Anti-Rollback (ARB) verification bypassed.\n")
                # 2. Product mismatch check
                elif "missmatching image and device" in l_lower or "mismatching image and device" in l_lower:
                    clean_lines.append("@echo [ROM Flasher] Device product verification passed.\n")
                # 3. Region mix flash check
                elif "mix flash is not allowed" in l_lower or "oem flash_check" in l_lower:
                    clean_lines.append("@echo [ROM Flasher] Region flash verification bypassed.\n")
                # 4. Cross-region lock disarm
                elif is_cross_region_lock_blocked and ("oem lock" in l_lower or "flashing lock" in l_lower):
                    clean_lines.append("@echo [ROM Flasher BrickShield] Bootloader lock disarmed to protect cross-region hardware.\n")
                # 5. Interactive pause / blocking variants (pause>nul, timeout /t, choice, ...)
                elif re.match(r'^\s*@?(?:pause\b|timeout\s+/t\b|choice\b)[^\r\n]*$', line, re.I):
                    clean_lines.append("@echo [ROM Flasher] Flash continuing...\n")
                # 6. Keep interactive set /p intact so user gets popup prompt!
                else:
                    clean_lines.append(line)

            clean_bat = os.path.join(work_dir, "rom_flasher_arb_clean.bat")
            # ASCII-only output keeps cmd.exe from garbling OEM menu text under any codepage.
            ascii_lines = [unicodedata.normalize("NFKD", ln).encode("ascii", "ignore").decode("ascii")
                           for ln in clean_lines]
            try:
                with open(clean_bat, 'w', encoding='ascii', errors='replace', newline='') as cf:
                    cf.writelines(ascii_lines)
            except Exception as e:
                err = f"Cannot write generated flash script to {work_dir}: {e}"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}

            _log("Starting fastboot flash execution in Live Console...", 40)

            # Ensure fastboot directory is at the front of PATH
            cmd_env = os.environ.copy()
            fb_dir = os.path.dirname(self.fastboot_path) if os.path.exists(self.fastboot_path) else r"C:\adb"
            cmd_env["PATH"] = f"{fb_dir};{work_dir};" + cmd_env.get("PATH", "")
            cmd_env["FASTBOOT_DEVICE"] = serial
            cmd_env["ANDROID_SERIAL"] = serial

            # Execute with device serial so %* expands to -s <serial>
            cmd_args = ["cmd.exe", "/c", clean_bat]
            if serial:
                cmd_args.extend(["-s", serial])

            c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.is_flashing = True
            bat_rc = -1
            bat_out = ""
            bat_err = ""
            # Initialized before Popen so a start failure cannot raise UnboundLocalError.
            bat_output_lines = []

            try:
                proc = subprocess.Popen(
                    cmd_args,
                    cwd=work_dir,
                    env=cmd_env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=c_flags
                )
                self.active_flash_proc = proc

                kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None

                def _get_pipe_avail(handle):
                    if not kernel32 or not handle:
                        return 0
                    avail = wintypes.DWORD()
                    res = kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None)
                    return avail.value if res else 0

                h_out = msvcrt.get_osfhandle(proc.stdout.fileno()) if sys.platform == "win32" else None

                buf = ""
                prompt_logged = False
                last_recv_time = time.time()
                step_pct = 40
                recent_menu_lines = []

                def _emit_prompt_popup(prompt_line):
                    ctx_text = "\n".join(recent_menu_lines[-6:])
                    payload = json.dumps({"prompt": prompt_line, "context": ctx_text})
                    _log(f"__PROMPT_JSON__:{payload}", min(95, step_pct))
                    _log(f"⌨️ [Interactive Prompt]: {prompt_line}", min(95, step_pct))

                def _process_stream_line(line_s):
                    nonlocal step_pct
                    if not line_s:
                        return
                    bat_output_lines.append(line_s)
                    l_low = line_s.lower()

                    # Detect interactive script prompts (e.g. [y/N], [1/2], Clean/Dirty Flash, continue?)
                    is_prompt = not any(f in l_low for f in ['sending', 'writing', 'erasing', 'formatting', 'finished', 'okay', 'failed', 'sparse', 'fastboot']) and any(p in l_low for p in ["[y/n", "(y/n", "[1/", "[1-", "choice", "press any key", "do you want to", "continue?", "enter choice", "clean flash", "dirty flash", "format data"])
                    if is_prompt:
                        _emit_prompt_popup(line_s)
                        return

                    # Track recent non-fastboot menu lines for popup context
                    if not any(f in l_low for f in ['sending', 'writing', 'erasing', 'formatting', 'fastboot', 'okay', 'finished']):
                        recent_menu_lines.append(line_s)
                        if len(recent_menu_lines) > 8:
                            recent_menu_lines.pop(0)

                    # Filter out command echoes, raw paths, and batch error exit guards
                    if "fastboot" in l_low or "||" in line_s or line_s.startswith("@echo") or line_s.startswith("echo ") or line_s.startswith("echo\"") or line_s.startswith("echo'"):
                        if " flash " in l_low:
                            parts = line_s.split()
                            try:
                                f_idx = [p.lower() for p in parts].index("flash")
                                if f_idx + 1 < len(parts):
                                    part_name = parts[f_idx + 1].strip('"\'')
                                    _log(f"⚡ Flashing: [{part_name}]", min(95, step_pct))
                            except:
                                pass
                        elif " erase " in l_low:
                            parts = line_s.split()
                            try:
                                e_idx = [p.lower() for p in parts].index("erase")
                                if e_idx + 1 < len(parts):
                                    part_name = parts[e_idx + 1].strip('"\'')
                                    _log(f"🧹 Erasing: [{part_name}]", min(95, step_pct))
                            except:
                                pass
                        elif "set_active" in l_low:
                            parts = line_s.split()
                            try:
                                s_idx = [p.lower() for p in parts].index("set_active")
                                if s_idx + 1 < len(parts):
                                    slot_name = parts[s_idx + 1].strip('"\'')
                                    _log(f"🔄 Setting Active Slot: [{slot_name}]", min(95, step_pct))
                            except:
                                pass
                        elif "[rom flasher" in l_low:
                            _log(line_s, min(95, step_pct))
                        return

                    if line_s.endswith(">") or ">fastboot" in line_s:
                        return

                    # Clean fastboot output through dedicated cleaner
                    cleaned_lines = clean_fastboot_log(line_s)
                    for c_msg in cleaned_lines:
                        c_low = c_msg.lower()
                        if "okay" in c_low or "finished" in c_low:
                            _log(c_msg, min(95, step_pct))
                            step_pct = min(95, step_pct + 1)
                        elif "error" in c_low or "failed" in c_low:
                            _log(f"❌ {c_msg}", min(95, step_pct))
                        else:
                            _log(c_msg, min(95, step_pct))

                while proc.poll() is None or (h_out and _get_pipe_avail(h_out) > 0):
                    _cancel_check("OEM flash script")
                    avail = _get_pipe_avail(h_out) if h_out else 0
                    if avail > 0:
                        raw_data = proc.stdout.read(avail)
                        text = raw_data.decode('utf-8', errors='replace')
                        buf += text
                        last_recv_time = time.time()
                        prompt_logged = False

                        while "\n" in buf:
                            one_line, buf = buf.split("\n", 1)
                            _process_stream_line(one_line.strip())
                    else:
                        stripped_buf = buf.strip()
                        if stripped_buf:
                            b_low = stripped_buf.lower()
                            # Never treat fastboot transfer lines as interactive prompts!
                            is_fb_action = any(f in b_low for f in [
                                'sending', 'writing', 'erasing', 'formatting', 'finished', 'okay', 
                                'failed', 'sparse', 'fastboot', 'rebooting', 'bytes'
                            ])
                            is_prompt = not is_fb_action and (
                                any(p in b_low for p in [
                                    "[y/n", "(y/n", "[1/", "[1-", "choice", "press any key", 
                                    "do you want to", "continue?", "enter choice", "select:",
                                    "proceed?", "are you sure", "y/n"
                                ]) or stripped_buf.endswith("?") or stripped_buf.endswith(":") or 
                                (stripped_buf.endswith("]") and any(c in b_low for c in ["y/n", "1/", "1-"]))
                            )

                            if is_prompt and not prompt_logged and (time.time() - last_recv_time > 0.15):
                                _emit_prompt_popup(stripped_buf)
                                prompt_logged = True
                                buf = ""
                        time.sleep(0.04)

                if buf.strip():
                    _process_stream_line(buf.strip())

                bat_out, bat_err = proc.communicate()
                bat_rc = proc.returncode
            except Exception as e:
                err = f"Failed to execute OEM flash script: {e}"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs,
                        "partial_output": "\n".join(bat_output_lines)[-4000:]}
            finally:
                self.active_flash_proc = None
                self.is_flashing = False

            try:
                os.remove(clean_bat)
            except:
                pass

            # Many custom OEM scripts omit `|| exit /b 1` and still print FAILED;
            # cmd.exe returncode 0 alone is NOT proof of success.
            raw_bat_output = "\n".join(
                bat_output_lines + ([bat_out] if bat_out else []) + ([bat_err] if bat_err else []))
            hard_fail_lines = [
                line.strip() for line in raw_bat_output.splitlines()
                if re.search(r'\bFAILED\b|remote:|error:', line, re.I)
            ]
            for c_line in clean_fastboot_log(raw_bat_output):
                if re.search(r'\bFAILED\b|remote:|error:', c_line, re.I):
                    _log(f"❌ {c_line}", 0)
            if bat_rc != 0:
                err = f"OEM flash script failed (exit code {bat_rc})"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}
            if hard_fail_lines:
                err = ("OEM flash script reported failures despite exit code 0: "
                       + hard_fail_lines[0][:300])
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}

            _log("Fastboot ROM flashing finished! Verifying system reboot...", 98)
            fb_chk = self.run_cmd([self.fastboot_path, "-s", serial, "devices"], timeout=4)
            if fastboot_devices_has_serial(fb_chk, serial):
                _log("Rebooting device to System...", 99)
                rb = self.reboot(serial, "FASTBOOT", "system")
                if not rb.get("success"):
                    err = f"OEM script finished but reboot failed: {rb.get('error', rb.get('output', 'unknown'))}"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}
            else:
                _log("Device automatically rebooting to System!", 99)
            boot_err = _verify_final_boot()
            if boot_err:
                return {"success": False, "error": boot_err, "logs": logs}
            _log("🎉 1-Click Fastboot Flash Completed Successfully! Device rebooting.", 100)
            return {"success": True, "logs": logs}

        # Fallback: Sequential partition flash if images found
        self.is_flashing = True
        _log("Scanning and flashing individual partition images sequentially...", 40)
        # vbmeta first (AVB state), then boot chain, then dynamic/data images.
        order = [
            "vbmeta.img", "vbmeta_system.img", "vbmeta_vendor.img", "boot.img",
            "init_boot.img", "vendor_boot.img", "vendor_kernel_boot.img", "dtbo.img",
            "dtb.img", "recovery.img", "system.img", "system_ext.img", "vendor.img",
            "product.img", "odm.img", "odm_dlkm.img", "pvmfb.img", "super.img",
        ]
        pct = 45
        flashed = 0
        fallback_failures = []
        try:
            for img_name in order:
                _cancel_check("sequential image flash")
                # Recursive index first: images/ and slot-suffixed files must be found too.
                part = normalize_partition_name(img_name)
                ip = (image_paths.get(img_name)
                      or image_paths.get(part + ".img")
                      or os.path.join(work_dir, img_name))
                if os.path.isfile(ip):
                    _log(f"Flashing partition [{part}]...", pct)
                    res = self.flash_partition(serial, part, ip)
                    _log(res.get("output", ""), pct)
                    if fastboot_step_ok(res):
                        flashed += 1
                    else:
                        fallback_failures.append(part)
                    pct = min(92, pct + 6)

            if fallback_failures or flashed == 0:
                err = (f"Sequential flash failed for: {', '.join(fallback_failures)}" if fallback_failures
                       else "No expected ROM images were found or flashed")
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}

            # Clean-data guarantee: wipe data/metadata before the first boot.
            _log("Wiping userdata & metadata for clean flash...", 94)
            res_u = self.run_cmd([self.fastboot_path, "-s", serial, "erase", "userdata"], timeout=60)
            if not fastboot_step_ok(res_u):
                res_w = self.run_cmd([self.fastboot_path, "-s", serial, "-w"], timeout=120)
                _log(res_w.get("output", ""), 95)
                if not fastboot_step_ok(res_w):
                    err = "Sequential flash wipe failed (erase userdata and fastboot -w)"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}
            res_m = self.run_cmd([self.fastboot_path, "-s", serial, "erase", "metadata"], timeout=30)
            if not fastboot_step_ok(res_m):
                _log("⚠️ metadata erase was not successful (unsupported/protected); continuing.", 95)

            slot_raw, slot_responded = self._probe_fastboot_var(serial, "slot-count")
            cur_raw, cur_responded = self._probe_fastboot_var(serial, "current-slot")
            if slot_raw.strip() == "2" and cur_raw.strip().lower() in ("a", "b"):
                res_active = self.run_cmd([self.fastboot_path, "-s", serial, "set_active",
                                           cur_raw.strip().lower()], timeout=30)
                if not fastboot_step_ok(res_active):
                    err = f"set_active failed for slot {cur_raw.strip().lower()}"
                    _log(f"❌ Error: {err}", 0)
                    return {"success": False, "error": err, "logs": logs}
            elif not slot_responded and not cur_responded:
                _log("⚠️ Could not read slot layout after image flash; skipped set_active.", 95)

            _log("Flashing completed! Auto-rebooting system...", 98)
            rb = self.reboot(serial, "FASTBOOT", "system")
            if not rb.get("success"):
                err = f"Flash finished but reboot failed: {rb.get('error', rb.get('output', 'unknown'))}"
                _log(f"❌ Error: {err}", 0)
                return {"success": False, "error": err, "logs": logs}
            boot_err = _verify_final_boot()
            if boot_err:
                return {"success": False, "error": boot_err, "logs": logs}
            _log("🎉 Auto Flash Finished!", 100)
            return {"success": True, "logs": logs}
        finally:
            self.is_flashing = False

    # 🔥 GKI & BOOT IMAGE DEEP ARCHITECTURE INSPECTION (ANDROID 13–16 / GKI 2.0)
    @staticmethod
    def inspect_boot_image(file_path: str) -> Dict[str, Any]:
        """
        Deep inspection of Android boot image header (v0-v4 / GKI 2.0).
        Detects header version, kernel size, ramdisk size, and GKI init_boot architecture.
        """
        if not file_path or not os.path.exists(file_path):
            return {"valid": False, "error": "File does not exist"}

        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, "rb") as f:
                data = f.read(64)

            if len(data) < 44 or data[:8] != b"ANDROID!":
                return {
                    "valid": False,
                    "is_android_boot": False,
                    "header_version": -1,
                    "kernel_size": 0,
                    "ramdisk_size": 0,
                    "is_gki_no_ramdisk": False,
                    "is_init_boot": False,
                    "has_ramdisk": False,
                    "error": "Not an Android boot image (missing ANDROID! magic / truncated header)",
                    "name": os.path.basename(file_path)
                }

            # v3/v4 store the header version at offset 24 and header_size at offset 20.
            # Older images store it at offset 40 (v1/v2) with header_size at 36 (v2) or page_size at 28 (v0/v1).
            hv24 = struct.unpack("<I", data[24:28])[0] if len(data) >= 28 else -1
            hv40 = struct.unpack("<I", data[40:44])[0]
            if hv24 in (3, 4):
                header_version = hv24
                header_size = struct.unpack("<I", data[20:24])[0]
                kernel_size, ramdisk_size = struct.unpack("<II", data[8:16])
            elif hv40 in (3, 4):
                # Legacy tooling sometimes writes v3/v4 version at offset 40; locate header_size there too.
                header_version = hv40
                hs12 = struct.unpack("<I", data[12:16])[0]
                hs20 = struct.unpack("<I", data[20:24])[0] if len(data) >= 24 else 0
                header_size = hs12 if 44 <= hs12 <= file_size else hs20
                kernel_size, ramdisk_size = struct.unpack("<II", data[8:16])
            else:
                header_version = hv40
                if header_version > 4:
                    return {"valid": False, "error": f"Unsupported boot header version {header_version}", "name": os.path.basename(file_path)}
                kernel_size = struct.unpack("<I", data[8:12])[0]
                ramdisk_size = struct.unpack("<I", data[16:20])[0]
                header_size = (
                    struct.unpack("<I", data[36:40])[0] if header_version == 2 and len(data) >= 40
                    else struct.unpack("<I", data[28:32])[0] if len(data) >= 32
                    else 64
                )

            if header_version > 4:
                return {"valid": False, "error": f"Unsupported boot header version {header_version}", "name": os.path.basename(file_path)}
            if header_size < 44 or header_size > file_size:
                return {"valid": False, "error": f"Invalid boot header_size ({header_size})", "name": os.path.basename(file_path)}
            required_size = header_size + kernel_size + ramdisk_size
            if file_size < required_size:
                return {
                    "valid": False,
                    "error": f"Truncated boot image: file is {file_size} bytes, needs at least {required_size} bytes",
                    "name": os.path.basename(file_path)
                }

            is_gki_no_ramdisk = (header_version >= 3 and ramdisk_size == 0)
            is_init_boot = ("init_boot" in os.path.basename(file_path).lower()) or (header_version >= 3 and kernel_size == 0 and ramdisk_size > 0)

            return {
                "valid": True,
                "is_android_boot": True,
                "header_version": header_version,
                "header_size": header_size,
                "kernel_size": kernel_size,
                "ramdisk_size": ramdisk_size,
                "is_gki_no_ramdisk": is_gki_no_ramdisk,
                "is_init_boot": is_init_boot,
                "has_ramdisk": ramdisk_size > 0,
                "name": os.path.basename(file_path)
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_boot_image_selection(self, file_path: str, serial: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates selected boot image against connected device architecture.
        Auto-switch to init_boot.img is only allowed when 'has-slot:init_boot == yes'
        is read from the exact requested serial via fastboot. Never inferred from Android version.
        """
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "blocked": True, "error": "File does not exist"}

        info = self.inspect_boot_image(file_path)
        if not info.get("valid"):
            return {
                "success": False, "blocked": True,
                "error": info.get("error") or "Invalid or corrupt boot image.",
                "reason": "INVALID_BOOT_IMAGE"
            }

        base_name = os.path.basename(file_path).lower()
        dir_name = os.path.dirname(file_path)

        # Fail closed: only an exact-serial fastboot query can confirm init_boot.
        confirmed_init_boot = False
        if serial:
            fb_ib = (self._get_fastboot_var(serial, "has-slot:init_boot") or "").strip().lower()
            confirmed_init_boot = (fb_ib == "yes")

        gki_hazard = bool(info.get("is_gki_no_ramdisk")) or (
            "boot.img" in base_name and "init_boot" not in base_name and info.get("header_version", 0) >= 3
        )

        if gki_hazard:
            companion = None
            if confirmed_init_boot:
                cands = [
                    os.path.join(dir_name, "init_boot.img"),
                    os.path.join(dir_name, "..", "images", "init_boot.img"),
                    os.path.join(dir_name, "images", "init_boot.img")
                ]
                companion = next((c for c in cands if os.path.exists(c)), None)
            if companion:
                return {
                    "success": True,
                    "blocked": False,
                    "switched": True,
                    "original": file_path,
                    "target": companion,
                    "reason": "GKI_AUTO_SWITCHED",
                    "message": "GKI Guard: 'has-slot:init_boot=yes' confirmed for this exact device. Switched to companion 'init_boot.img' to prevent a bootloop!"
                }
            reason = "INIT_BOOT_NOT_CONFIRMED" if not confirmed_init_boot else "GKI_ZERO_RAMDISK_HAZARD"
            message = (
                "⚠️ Blocked: init_boot partition could NOT be confirmed for the exact target serial via fastboot "
                "(or the device is ADB-only). Do not patch boot.img blindly — connect in Fastboot or select 'init_boot.img' explicitly."
                if not confirmed_init_boot else
                "⚠️ Blocked: GKI kernel-only boot.img has no ramdisk and no valid companion 'init_boot.img' was found. Please select 'init_boot.img'."
            )
            return {
                "success": False,
                "blocked": True,
                "switched": False,
                "original": file_path,
                "target": file_path,
                "hazard": True,
                "reason": reason,
                "error": message,
                "message": message
            }

        return {
            "success": True,
            "blocked": False,
            "switched": False,
            "target": file_path,
            "hazard": False,
            "info": info
        }

    # 🔥 ROOT STUDIO (MAGISK, KERNELSU, APATCH, SUKISU ULTRA + DOWNLOAD BOOT)
    def _get_or_create_superkey(self, name: str) -> str:
        """Returns a stable, per-installation random 32-hex superkey (never a hardcoded secret)."""
        keys_dir = get_storage_dir("Root_Tools")
        os.makedirs(keys_dir, exist_ok=True)
        key_file = os.path.join(keys_dir, "superkeys.json")
        data = {}
        try:
            with open(key_file, "r", encoding="utf-8") as kf:
                loaded = json.load(kf)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

        key = data.get(name)
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key):
            key = secrets.token_hex(16)
            data[name] = key
            try:
                tmp_key_file = key_file + ".tmp"
                with open(tmp_key_file, "w", encoding="utf-8") as kf:
                    json.dump(data, kf, indent=2)
                os.replace(tmp_key_file, key_file)
            except Exception as e:
                # A patcher key that cannot be persisted will not match the manager app.
                raise RuntimeError(f"Could not persist root superkey: {e}")
        return key

    def download_root_framework(self, framework_name: str) -> Dict[str, Any]:
        # Explicit whitelist: an unknown framework must never fall through to Magisk.
        if framework_name not in ROOT_RELEASES_API:
            return {"success": False, "output": f"Unknown root framework: {framework_name}"}
        api_url = ROOT_RELEASES_API[framework_name]
        out_dir = get_storage_dir("Root_Tools")
        os.makedirs(out_dir, exist_ok=True)

        manifest_path = os.path.join(out_dir, "trusted_apks.json")

        def _slug(value: str) -> str:
            return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

        fw_key = _slug(framework_name)

        def _load_all_trusted() -> Dict[str, Dict[str, str]]:
            """New format: {framework: {filename: sha256}}. Legacy flat pins are migrated by name."""
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    obj = json.load(mf)
                if not isinstance(obj, dict):
                    return {}
            except Exception:
                return {}

            result: Dict[str, Dict[str, str]] = {}
            if any(isinstance(v, dict) for v in obj.values()):
                for fw, entries in obj.items():
                    if isinstance(entries, dict):
                        result[_slug(fw)] = {
                            str(k).lower(): str(v).lower()
                            for k, v in entries.items()
                            if isinstance(k, str) and isinstance(v, str)
                        }
            else:
                for k, v in obj.items():
                    if not (isinstance(k, str) and isinstance(v, str)):
                        continue
                    owner = next((f for f in ROOT_RELEASES_API if _slug(f) in _slug(k)), None)
                    if owner:
                        result.setdefault(_slug(owner), {})[k.lower()] = v.lower()
            return result

        def _save_all_trusted(trusted: Dict[str, Dict[str, str]]) -> None:
            tmp_manifest = manifest_path + ".tmp"
            with open(tmp_manifest, "w", encoding="utf-8") as mf:
                json.dump(trusted, mf, indent=2)
            os.replace(tmp_manifest, manifest_path)

        def _sha256_file(path: str) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as sf:
                for block in iter(lambda: sf.read(1024 * 1024), b""):
                    h.update(block)
            return h.hexdigest()

        all_trusted = _load_all_trusted()
        fw_trusted = all_trusted.get(fw_key, {})
        # Offline fallback only for APKs pinned to THIS framework and hash-matched.
        fallback_candidates = [
            os.path.join(out_dir, name)
            for name in fw_trusted
            if name.lower().endswith(".apk") and os.path.isfile(os.path.join(out_dir, name))
        ]

        temp_dl = None
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "ROM-Flasher-Tool"})
            with urllib.request.urlopen(req, timeout=12) as response:
                data = json.loads(response.read().decode())

            assets = data.get("assets", [])
            download_url = None
            filename = f"{framework_name}.apk"

            for a in assets:
                name = a.get("name", "")
                n_low = name.lower()
                if n_low.endswith(".apk") and "debug" not in n_low and "spoofed" not in n_low:
                    download_url = a.get("browser_download_url")
                    filename = name
                    if "release" in n_low:
                        break
            if not download_url:
                for a in assets:
                    name = a.get("name", "")
                    if name.lower().endswith(".apk"):
                        download_url = a.get("browser_download_url")
                        filename = name
                        break

            if not download_url:
                raise ValueError(f"No APK asset found in {framework_name} release.")
            if urllib.parse.urlparse(download_url).scheme != "https":
                raise ValueError("Refusing non-HTTPS APK download.")

            safe_apk_name = re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(filename)) or f"{framework_name.replace(' ', '_')}.apk"
            out_file = os.path.join(out_dir, safe_apk_name)
            temp_dl = out_file + ".download"
            dl_req = urllib.request.Request(download_url, headers={"User-Agent": "ROM-Flasher-Tool"})
            with urllib.request.urlopen(dl_req, timeout=60) as dl_resp, open(temp_dl, "wb") as f_out:
                shutil.copyfileobj(dl_resp, f_out)
            if os.path.getsize(temp_dl) <= 0:
                raise ValueError("Downloaded APK is empty.")

            # A pin is a trust anchor: a mismatched download is rejected, never re-pinned.
            digest = _sha256_file(temp_dl)
            pinned = fw_trusted.get(safe_apk_name.lower()) or fw_trusted.get(os.path.basename(filename).lower())
            if pinned and pinned != digest:
                raise ValueError(
                    f"APK hash mismatch for {framework_name}: pinned {pinned[:12]}..., downloaded {digest[:12]}... "
                    "Refusing to install an unverified root manager."
                )
            os.replace(temp_dl, out_file)
            temp_dl = None

            # First successful download creates the pin; later downloads must match it.
            fw_trusted[safe_apk_name.lower()] = digest
            fw_trusted[os.path.basename(filename).lower()] = digest
            all_trusted[fw_key] = fw_trusted
            _save_all_trusted(all_trusted)

            return {"success": True, "path": out_file, "filename": filename, "version": data.get("tag_name", "latest")}
        except Exception as e:
            for fb in fallback_candidates:
                fb_name = os.path.basename(fb).lower()
                expected = fw_trusted.get(fb_name)
                if not expected or os.path.getsize(fb) <= 0:
                    continue
                try:
                    if _sha256_file(fb).lower() != expected:
                        continue
                except Exception:
                    continue
                return {"success": True, "path": fb, "filename": os.path.basename(fb), "version": "offline_cached"}
            return {"success": False, "output": f"Failed downloading {framework_name}: {str(e)} (no hash-verified cached APK)"}
        finally:
            if temp_dl and os.path.exists(temp_dl):
                try:
                    os.remove(temp_dl)
                except Exception:
                    pass

    def install_root_workflow(self, serial: str, framework_name: str, boot_img_path: Optional[str] = None) -> Dict[str, Any]:
        logs = [f"Starting Root Workflow for [{framework_name}]..."]
        if framework_name not in ROOT_RELEASES_API:
            err_msg = f"Unsupported root framework '{framework_name}'. Choose Magisk, KernelSU, APatch or SukiSU Ultra."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}
        # 1. Download or resolve latest release APK
        logs.append(f"Resolving {framework_name} Manager APK...")
        dl_res = self.download_root_framework(framework_name)
        if not dl_res["success"]:
            logs.append(dl_res["output"])
            return {"success": False, "logs": logs}

        apk_path = dl_res["path"]
        logs.append(f"Ready: {dl_res['filename']} ({dl_res.get('version')})")

        # 2. Check Device Connection
        devices = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devices, serial)
        if not dev:
            err_msg = f"Exact target device [{serial}] is not connected in ADB or Fastboot mode. Refusing to use any other device."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}

        # Install APK to device via ADB
        if dev["mode"] == "ADB":
            logs.append(f"Installing {framework_name} manager to device via ADB...")
            inst_res = self.universal_install_app(serial, apk_path)
            logs.extend(inst_res.get("logs", []))
            if not inst_res.get("success"):
                err_msg = f"Failed to install {framework_name} manager APK on {serial}."
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "logs": logs}

        # 3. Real In-App Native Boot Patching & Fastboot Flashing
        if not boot_img_path or not os.path.exists(boot_img_path):
            err_msg = f"{framework_name} Manager APK installed, but NO boot/init_boot image was provided or found. Please select or download stock boot.img / init_boot.img to patch and root!"
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}

        if boot_img_path and os.path.exists(boot_img_path):
            logs.append(f"Analyzing Boot Image: {boot_img_path}")
            orig_boot_img_path = boot_img_path

            # Fail-closed shared boot-image guard. APatch intentionally patches boot.img's
            # kernel, so its target selection is handled separately below.
            if framework_name != "APatch":
                boot_check = self.validate_boot_image_selection(boot_img_path, serial)
                if boot_check.get("message"):
                    logs.append(str(boot_check["message"]))
                if not boot_check.get("success") or boot_check.get("blocked"):
                    err_msg = boot_check.get("error") or "Boot image rejected by the exact-device safety guard."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                if boot_check.get("switched") and boot_check.get("target"):
                    boot_img_path = boot_check["target"]
                    logs.append(f"Target safely updated to: {boot_img_path}")

            # 🛡️ ARCHITECTURE-AWARE TARGET GUARD (Android 10–17)
            # - KernelSU / Magisk / SukiSU Ultra: patch init_boot.img on Android 13+ GKI (or boot.img on Android 10-12 / non-init_boot)
            # - APatch (kptools + kpimg): MUST patch kernel inside boot.img (never init_boot.img)
            # APatch (and SukiSU's kptools fallback) always patch the Linux kernel in boot.img.
            # Magisk / KernelSU / SukiSU ksud patch init_boot.img on GKI devices.
            is_kernel_patcher = (framework_name == "APatch")
            suki_key = self._get_or_create_superkey("SukiSU")
            apatch_key = self._get_or_create_superkey("APatch")

            b_info = self.inspect_boot_image(boot_img_path)
            if not b_info.get("valid"):
                err_msg = f"Invalid/corrupt boot image: {b_info.get('error', 'unknown error')}"
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "logs": logs}
            is_gki_zero_ramdisk = b_info.get("is_gki_no_ramdisk", False)
            base_bname = os.path.basename(boot_img_path).lower()
            dir_name = os.path.dirname(boot_img_path)

            if is_kernel_patcher:
                # APatch & SukiSU Ultra (kptools) require boot.img (contains Linux kernel)
                if "init_boot" in base_bname:
                    boot_cands = [
                        os.path.join(dir_name, "boot.img"),
                        os.path.join(dir_name, "..", "images", "boot.img"),
                        os.path.join(dir_name, "images", "boot.img")
                    ]
                    companion_boot = next((c for c in boot_cands if os.path.exists(c)), None)
                    if companion_boot:
                        logs.append(f"🛡️ [Kernel Patcher Guard] [{framework_name}] patches the Linux kernel directly.")
                        logs.append(f"Auto-switching target from init_boot.img to companion boot.img: {companion_boot}")
                        boot_img_path = companion_boot
                    else:
                        return {
                            "success": False,
                            "error": f"{framework_name} requires 'boot.img' (contains the Linux kernel), not 'init_boot.img'. Please select boot.img.",
                            "logs": logs
                        }
            elif is_gki_zero_ramdisk or ("boot.img" in base_bname and "init_boot" not in base_bname):
                cands = [
                    os.path.join(dir_name, "init_boot.img"),
                    os.path.join(dir_name, "..", "images", "init_boot.img"),
                    os.path.join(dir_name, "images", "init_boot.img")
                ]
                companion_init_boot = next((c for c in cands if os.path.exists(c)), None)

                if is_gki_zero_ramdisk:
                    if companion_init_boot:
                        logs.append(f"🛡️ [GKI Architecture Guard] Android 13+ GKI boot.img detected (Header v{b_info.get('header_version', 4)})!")
                        logs.append(f"Notice: 'boot.img' has 0-byte ramdisk (Kernel-only image: {b_info.get('kernel_size', 0)//1024} KB).")
                        logs.append("Ramdisk resides in 'init_boot.img'. Automatically switching target to companion init_boot...")
                        boot_img_path = companion_init_boot
                        logs.append(f"Target safely updated to: {boot_img_path}")
                    else:
                        logs.append("❌ [CRITICAL DM-VERITY GUARD] Root Workflow Terminated to Safeguard Hardware!")
                        logs.append(f"Selected 'boot.img' contains NO ramdisk (kernel_size={b_info.get('kernel_size')}, ramdisk_size=0).")
                        logs.append("On Android 13+ GKI devices, root must be patched into 'init_boot.img'.")
                        return {
                            "success": False,
                            "error": "GKI Ramdisk Hazard: Selected boot.img has 0-byte ramdisk. Please select 'init_boot.img' from your ROM images folder to avoid a bootloop.",
                            "logs": logs
                        }
                elif companion_init_boot:
                    dev_ver = dev.get("version", "") if dev else ""
                    if not dev_ver and serial:
                        dev_ver = self._get_prop(serial, "ro.build.version.release")
                    try:
                        ver_num = int(float(dev_ver)) if dev_ver else 0
                    except:
                        ver_num = 0

                    confirmed_ib = (self._get_fastboot_var(serial, "has-slot:init_boot") or "").strip().lower() == "yes"
                    if confirmed_ib:
                        logs.append(f"🛡️ [GKI Architecture Guard] Exact device [{serial}] confirmed dedicated init_boot partition.")
                        logs.append(f"Auto-switching target from boot.img to companion: {companion_init_boot}")
                        boot_img_path = companion_init_boot

            part = "init_boot" if "init_boot" in os.path.basename(boot_img_path).lower() else "boot"

            # If device is in ADB mode: perform real on-device native patch execution!
            if dev and dev["mode"] == "ADB":
                logs.append(f"Executing In-App Native Direct Patching for [{framework_name}]...")
                # Unique staging directory: a stale new-boot.img from an earlier run must
                # never be mistaken for this patcher's output.
                remote_dir = f"/data/local/tmp/rf_patch_{os.getpid()}_{int(time.time() * 1000)}"

                def _cleanup_remote():
                    c = self.run_cmd([self.adb_path, "-s", serial, "shell", "rm", "-rf", remote_dir], timeout=10)
                    if not adb_result_ok(c):
                        logs.append(f"⚠️ Could not clean remote patch folder {remote_dir}: {c.get('output', '')}")

                self.run_cmd([self.adb_path, "-s", serial, "shell", "rm", "-rf", remote_dir], timeout=10)
                mkdir_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "mkdir", "-p", remote_dir], timeout=10)
                if not adb_result_ok(mkdir_res):
                    err_msg = f"Could not create patch staging folder on device: {mkdir_res.get('output', '')}"
                    logs.append(f"❌ {err_msg}")
                    _cleanup_remote()
                    return {"success": False, "error": err_msg, "logs": logs}

                # Detect device ABI cleanly (supports arm64-v8a, armeabi-v7a, x86_64)
                abi_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "getprop", "ro.product.cpu.abi"], timeout=10)
                dev_abi = abi_res["stdout"].strip().lower() or "arm64-v8a"
                if "arm64" in dev_abi or "aarch64" in dev_abi:
                    target_abi = "arm64-v8a"
                elif "armeabi" in dev_abi or "arm" in dev_abi:
                    target_abi = "armeabi-v7a"
                elif "x86_64" in dev_abi:
                    target_abi = "x86_64"
                else:
                    target_abi = "x86"

                # Push stock boot/init_boot to device as input.img
                logs.append(f"Pushing stock {os.path.basename(boot_img_path)} to device patcher...")
                push_stock = self.run_cmd([self.adb_path, "-s", serial, "push", boot_img_path, f"{remote_dir}/input.img"], timeout=60)
                if not adb_result_ok(push_stock):
                    err_msg = f"Failed to push stock image to device: {push_stock.get('output', '')}"
                    logs.append(f"❌ {err_msg}")
                    _cleanup_remote()
                    return {"success": False, "error": err_msg, "logs": logs}

                # Extract native binaries from APK
                logs.append(f"Extracting {target_abi} patch tools from {os.path.basename(apk_path)}...")
                temp_tools = tempfile.mkdtemp(prefix="rf_patch_bin_")
                patch_ok = False
                try:
                    with zipfile.ZipFile(apk_path, 'r') as zf:
                        znames = zf.namelist()

                        def _push_entry(entry_name, remote_name):
                            local_f = os.path.join(temp_tools, remote_name)
                            with open(local_f, 'wb') as f:
                                f.write(zf.read(entry_name))
                            pushed = self.run_cmd([self.adb_path, "-s", serial, "push", local_f, f"{remote_dir}/{remote_name}"], timeout=30)
                            if not adb_result_ok(pushed):
                                raise RuntimeError(f"Failed to push patch tool {remote_name}: {pushed.get('output', '')}")

                        if framework_name == "KernelSU":
                            ksud_entry = next((n for n in znames if f"lib/{target_abi}/libksud.so" in n), None) or next((n for n in znames if n.endswith("libksud.so")), None)
                            if ksud_entry:
                                _push_entry(ksud_entry, "ksud")
                            self.run_cmd([self.adb_path, "-s", serial, "shell", "chmod", "-R", "755", remote_dir], timeout=10)
                            logs.append("Executing [ksud boot-patch] on device...")
                            patch_res = self.run_cmd([self.adb_path, "-s", serial, "shell", f"cd {remote_dir} && ./ksud boot-patch -b input.img -o . --out-name new-boot.img --allow-shell"], timeout=60)
                            logs.append(patch_res["output"])
                            patch_ok = adb_result_ok(patch_res) and patch_output_has_success(patch_res)
                            if not patch_ok and adb_result_ok(patch_res):
                                logs.append(f"⚠️ {framework_name} patcher exited cleanly but printed no success marker; refusing empty-output success.")

                        elif framework_name == "SukiSU Ultra":
                            # SukiSU Nova obfuscates ksud (e.g. liblaapkjdiji.so ~6.8MB) or ships libksud.so
                            ksud_entry = (
                                next((n for n in znames if f"lib/{target_abi}/libksud.so" in n), None)
                                or next((n for n in znames if f"lib/{target_abi}/liblaapkjdiji.so" in n), None)
                                or next((n for n in znames if n.endswith("libksud.so")), None)
                            )
                            if not ksud_entry:
                                # Fallback: pick the largest native .so (>2MB) in lib/<abi>/ excluding kptools/busybox/adbroot
                                abi_libs = [
                                    (n, zf.getinfo(n).file_size)
                                    for n in znames
                                    if n.startswith(f"lib/{target_abi}/") and n.endswith(".so")
                                    and not any(x in n for x in ("kptools", "busybox", "adbroot"))
                                ]
                                abi_libs.sort(key=lambda x: x[1], reverse=True)
                                if abi_libs and abi_libs[0][1] > 2_000_000:
                                    ksud_entry = abi_libs[0][0]

                            # Always defined: a missing ksud entry must not raise NameError
                            # and be misreported as a "corrupt APK" by the outer handler.
                            patch_res = {"success": False, "stdout": "", "stderr": "", "output": ""}
                            if ksud_entry:
                                _push_entry(ksud_entry, "ksud")
                                self.run_cmd([self.adb_path, "-s", serial, "shell", "chmod", "-R", "755", remote_dir], timeout=10)
                                logs.append(f"Executing [SukiSU Ultra ksud boot-patch] ({os.path.basename(ksud_entry)}) on device...")
                                patch_res = self.run_cmd([self.adb_path, "-s", serial, "shell", f"cd {remote_dir} && ./ksud boot-patch -b input.img -o . --out-name new-boot.img --allow-shell"], timeout=90)
                                logs.append(patch_res["output"])
                                patch_ok = adb_result_ok(patch_res) and patch_output_has_success(patch_res)
                                if not patch_ok and adb_result_ok(patch_res):
                                    logs.append(f"⚠️ {framework_name} patcher exited cleanly but printed no success marker; refusing empty-output success.")
                            # Fallback is only for a FAILED/absent ksud patch. Running it after a
                            # successful ksud patch would overwrite the good result and can flash
                            # a kptools-patched boot.img into the wrong partition.
                            if not patch_ok:
                                kptools_entry = next((n for n in znames if f"lib/{target_abi}/libkptools.so" in n), None)
                                kpimg_entry = next((n for n in znames if n.endswith("kpimg")), None)
                                if kptools_entry and kpimg_entry:
                                    # kptools patches the Linux kernel inside boot.img (not init_boot.img)
                                    if "init_boot" in os.path.basename(boot_img_path).lower():
                                        d_dir = os.path.dirname(boot_img_path)
                                        k_cands = [orig_boot_img_path, os.path.join(d_dir, "boot.img"), os.path.join(d_dir, "images", "boot.img")]
                                        k_boot = next((c for c in k_cands if c and os.path.exists(c) and "init_boot" not in os.path.basename(c).lower()), None)
                                        if not k_boot:
                                            return {"success": False, "error": "SukiSU kptools fallback requires 'boot.img' (Linux kernel), not 'init_boot.img'.", "logs": logs}
                                        logs.append(f"🛡️ [Kernel Patcher Guard] Switching SukiSU kptools target to boot.img: {k_boot}")
                                        boot_img_path = k_boot
                                        part = "boot"
                                        repush = self.run_cmd([self.adb_path, "-s", serial, "push", boot_img_path, f"{remote_dir}/input.img"], timeout=60)
                                        if not adb_result_ok(repush):
                                            raise RuntimeError(f"Failed to push kptools boot.img: {repush.get('output', '')}")
                                    _push_entry(kptools_entry, "kptools")
                                    _push_entry(kpimg_entry, "kpimg")
                                    chmod_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "chmod", "-R", "755", remote_dir], timeout=10)
                                    if not adb_result_ok(chmod_res):
                                        raise RuntimeError(f"Failed to mark patch tools executable: {chmod_res.get('output', '')}")
                                    logs.append("Executing [SukiSU kptools] fallback patch on device...")
                                    patch_res = self.run_cmd([self.adb_path, "-s", serial, "shell", f"cd {remote_dir} && ./kptools -p -i input.img -k kpimg -s {suki_key} -o new-boot.img"], timeout=90)
                                    logs.append(patch_res["output"])
                                    patch_ok = adb_result_ok(patch_res) and patch_output_has_success(patch_res)
                                    if not patch_ok and adb_result_ok(patch_res):
                                        logs.append(f"⚠️ {framework_name} patcher exited cleanly but printed no success marker; refusing empty-output success.")

                        elif framework_name == "APatch":
                            apatch_assets = {
                                f"lib/{target_abi}/libkptools.so": "kptools",
                                f"lib/{target_abi}/libkpatch.so": "kpatch",
                                f"lib/{target_abi}/libbusybox.so": "busybox",
                                "assets/kpimg": "kpimg",
                                "assets/boot_patch.sh": "boot_patch.sh",
                                "assets/util_functions.sh": "util_functions.sh"
                            }
                            for zp, rn in apatch_assets.items():
                                if zp in znames:
                                    _push_entry(zp, rn)
                                else:
                                    cand = next((n for n in znames if n.endswith(rn) and (target_abi in n or not n.startswith("lib/"))), None)
                                    if cand:
                                        _push_entry(cand, rn)
                            self.run_cmd([self.adb_path, "-s", serial, "shell", "chmod", "-R", "755", remote_dir], timeout=10)
                            logs.append("Executing [APatch boot_patch.sh] kernel injection on device...")
                            apatch_cmd = f"cd {remote_dir} && if [ -f boot_patch.sh ]; then /system/bin/sh boot_patch.sh {apatch_key} input.img; else ./kptools -p -i input.img -k kpimg -s {apatch_key} -o new-boot.img; fi"
                            patch_res = self.run_cmd([self.adb_path, "-s", serial, "shell", apatch_cmd], timeout=90)
                            logs.append(patch_res["output"])
                            patch_ok = adb_result_ok(patch_res) and patch_output_has_success(patch_res)
                            if not patch_ok and adb_result_ok(patch_res):
                                logs.append(f"⚠️ {framework_name} patcher exited cleanly but printed no success marker; refusing empty-output success.")

                        elif framework_name == "Magisk":
                            logs.append(f"Targeting device ABI: {dev_abi} (using {target_abi})...")
                            magisk_binaries = {
                                f"lib/{target_abi}/libmagiskboot.so": "magiskboot",
                                f"lib/{target_abi}/libmagiskinit.so": "magiskinit",
                                f"lib/{target_abi}/libmagisk.so": "magisk",
                                f"lib/{target_abi}/libinit-ld.so": "init-ld",
                                f"lib/{target_abi}/libbusybox.so": "busybox",
                                f"lib/{target_abi}/libmagiskpolicy.so": "magiskpolicy",
                                "assets/boot_patch.sh": "boot_patch.sh",
                                "assets/util_functions.sh": "util_functions.sh",
                                "assets/stub.apk": "stub.apk"
                            }
                            for zip_entry, dest_name in magisk_binaries.items():
                                if zip_entry in znames:
                                    _push_entry(zip_entry, dest_name)
                                else:
                                    cand = next((n for n in znames if n.endswith(dest_name) and (target_abi in n or not n.startswith("lib/"))), None)
                                    if cand:
                                        _push_entry(cand, dest_name)

                            self.run_cmd([self.adb_path, "-s", serial, "shell", "chmod", "-R", "755", remote_dir], timeout=10)
                            logs.append("Executing Magisk ramdisk patch on device...")
                            magisk_cmd = f"cd {remote_dir} && KEEPVERITY=true KEEPFORCEENCRYPT=true PATCHVBMETAFLAG=false /system/bin/sh boot_patch.sh input.img"
                            patch_res = self.run_cmd([self.adb_path, "-s", serial, "shell", magisk_cmd], timeout=90)
                            logs.append(patch_res["output"])
                            patch_ok = adb_result_ok(patch_res) and patch_output_has_success(patch_res)
                            if not patch_ok and adb_result_ok(patch_res):
                                logs.append(f"⚠️ {framework_name} patcher exited cleanly but printed no success marker; refusing empty-output success.")

                        else:
                            # Unknown frameworks must never silently fall through to a
                            # patcher that was written for a different root manager.
                            raise RuntimeError(f"No in-app patcher is implemented for {framework_name}")
                except Exception as zip_err:
                    err_msg = f"Corrupt or unreadable cached APK ({os.path.basename(apk_path)}): {zip_err}"
                    logs.append(f"❌ {err_msg}")
                    _cleanup_remote()
                    return {"success": False, "error": err_msg, "logs": logs}
                finally:
                    shutil.rmtree(temp_tools, ignore_errors=True)

                if not patch_ok:
                    err_msg = f"{framework_name} patch process failed on the device. Stock image untouched."
                    logs.append(f"❌ {err_msg}")
                    _cleanup_remote()
                    return {"success": False, "error": err_msg, "logs": logs}

                # Locate generated patched image on device
                ls_res = self.run_cmd([self.adb_path, "-s", serial, "shell", f"ls {remote_dir}/new-boot.img {remote_dir}/*patched*.img {remote_dir}/magisk_patched*.img 2>/dev/null"], timeout=10)
                patched_remote = None
                expected_path = re.compile(rf"^{re.escape(remote_dir)}/[A-Za-z0-9_.-]+\.img$")
                for candidate in (ls_res.get("stdout", "") or "").splitlines():
                    candidate = candidate.strip()
                    if expected_path.fullmatch(candidate):
                        patched_remote = candidate
                        break
                    if candidate:
                        logs.append(f"⚠️ Ignoring unexpected patcher output path: {candidate[:120]}")

                if patched_remote:
                    logs.append(f"Patched image generated successfully: {patched_remote}")
                    patched_name = f"patched_{os.path.splitext(os.path.basename(boot_img_path))[0]}_{int(time.time())}.img"
                    patched_local = os.path.join(os.path.dirname(boot_img_path), patched_name)
                    pull_res = self.run_cmd([self.adb_path, "-s", serial, "pull", patched_remote, patched_local], timeout=60)
                    patched_size = os.path.getsize(patched_local) if os.path.exists(patched_local) else 0
                    patched_magic = b""
                    if patched_size > 0:
                        try:
                            with open(patched_local, "rb") as pf:
                                patched_magic = pf.read(8)
                        except Exception:
                            patched_magic = b""
                    if not adb_result_ok(pull_res) or patched_size < 4096 or patched_size > 2 * 1024 * 1024 * 1024 or patched_magic != b"ANDROID!":
                        err_msg = f"Pulled patched image failed validation (magic={patched_magic!r}, size={patched_size}). Refusing to flash."
                        logs.append(f"❌ {err_msg}")
                        _cleanup_remote()
                        return {"success": False, "error": err_msg, "logs": logs}
                    logs.append(f"Pulled patched image to PC: {patched_local} ({patched_size//1024} KB)")
                else:
                    logs.append(f"❌ [Root Patcher Error] Failed to generate patched boot image on device!")
                    logs.append(f"Device patcher script failed to produce a valid output image for [{framework_name}].")
                    logs.append("Flashing aborted to prevent bootloop. Stock partitions remain 100% untouched.")
                    _cleanup_remote()
                    return {"success": False, "error": f"{framework_name} patching failed on device. Stock boot preserved.", "logs": logs}

                _cleanup_remote()

                # Reboot to Fastboot Mode
                logs.append("Auto-rebooting device to Bootloader (Fastboot Mode)...")
                reboot_res = self.reboot(serial, "ADB", "bootloader")
                if not adb_result_ok(reboot_res):
                    err_msg = f"Reboot to Fastboot failed for [{serial}]: {reboot_res.get('output', '')}"
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                time.sleep(3)

                # Wait for Fastboot connection
                fb_serial = serial
                fb_found = False
                for _ in range(20):
                    time.sleep(1.5)
                    fb_devs = self.detect_devices(bypass_cache=True)
                    fb = self._find_device_exact(fb_devs, serial, "FASTBOOT")
                    if fb:
                        fb_serial = fb["serial"]
                        fb_found = True
                        break
                if not fb_found:
                    err_msg = f"Exact target [{serial}] did not appear in FASTBOOT after reboot. Refusing to flash another device."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}

                # Flash ONLY the active slot on A/B devices so the inactive slot remains a safe anti-bootloop fallback
                has_slot = self._get_fastboot_var(fb_serial, f"has-slot:{part}")
                target_part = part
                if has_slot and "yes" in has_slot.lower():
                    cur_slot = self._get_fastboot_var(fb_serial, "current-slot").strip("_").lower()
                    if cur_slot in ("a", "b"):
                        target_part = f"{part}_{cur_slot}"
                        logs.append(f"🛡️ [A/B Slot Safety] Flashing active slot [{target_part}] only (inactive slot preserved as fallback).")

                logs.append(f"Flashing rooted image to [{target_part}] in Fastboot ({fb_serial})...")
                f_res = self.flash_partition(fb_serial, target_part, patched_local)
                logs.append(f_res.get("output", ""))
                flash_ok = fastboot_step_ok(f_res)

                logs.append("Rebooting device to System...")
                reboot_res = self.reboot(fb_serial, "FASTBOOT", "system")
                if not fastboot_result_ok(reboot_res):
                    err_msg = f"Reboot to system failed for [{fb_serial}]: {reboot_res.get('output', '')}"
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                if not flash_ok:
                    err_msg = f_res.get("output") or f"Failed to flash {part} in Fastboot."
                    logs.append(f"❌ Root flashing failed: {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}

                logs.append(f"🎉 1-Click Root for [{framework_name}] completed successfully! Phone is now rooted.")
                return {"success": True, "logs": logs}

            else:
                # Device is already in FASTBOOT: the stock image cannot be patched here.
                err_msg = (
                    f"Device [{serial}] is already in FASTBOOT. Refusing to flash the unpatched/stock "
                    f"{os.path.basename(boot_img_path)} — that would never grant root. "
                    "Boot into Android with an internet connection, install the manager APK, patch the "
                    "boot/init_boot image in the app, then retry with the patched image."
                )
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "logs": logs}

        logs.append(f"Root injection for [{framework_name}] completed successfully!")
        return {"success": True, "logs": logs}

    def uninstall_root_workflow(self, serial: str, stock_boot_path: Optional[str] = None) -> Dict[str, Any]:
        logs = ["Starting Root Uninstaller..."]
        # Package removal is ADB-only. A device that is offline/in Fastboot must
        # not turn every "device not found" error into a harmless "not installed".
        device_err = self._require_adb_device(serial)
        if device_err:
            logs.append(f"❌ {device_err}")
            return {"success": False, "error": device_err, "failed_packages": [], "logs": logs}
        # 1. Remove Root manager APKs (all known package IDs)
        root_pkgs = [
            "com.topjohnwu.magisk",
            "me.weishu.kernelsu",
            "me.bmax.apatch",
            "io.github.bmax121.apatch",
            "com.sukisu.nova",
            "org.sukisu.ultra",
            "me.garfieldhan.sukisu"
        ]
        logs.append("Uninstalling root manager applications from device...")
        failed_pkgs = []
        for pkg in root_pkgs:
            u_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "uninstall", pkg], timeout=15)
            if adb_result_ok(u_res):
                logs.append(f"✅ Removed {pkg}")
            elif re.search(r"(?:package|pkg)\s+.*?not found", u_res.get("output", "") or "", re.I):
                # Only an explicit PACKAGE-level miss is "not installed". An ADB
                # "device '<serial>' not found" must stay a real failure.
                logs.append(f"• {pkg} was not installed; skipped")
            else:
                failed_pkgs.append(pkg)
                logs.append(f"⚠️ Could not remove {pkg}: {u_res.get('output', '')}")

        # 2. Restore Stock Boot / Init_Boot if provided
        if stock_boot_path and os.path.exists(stock_boot_path):
            logs.append(f"Analyzing stock restore image: {stock_boot_path}...")
            part = "init_boot" if "init_boot" in os.path.basename(stock_boot_path).lower() else "boot"
            restore_targets = [(part, stock_boot_path)]

            # If restoring from a ROM images folder on GKI, also restore companion image so APatch (boot) & KSU/Magisk/SukiSU (init_boot) are both wiped
            img_dir = os.path.dirname(stock_boot_path)
            if part == "boot":
                b_info = self.inspect_boot_image(stock_boot_path)
                cand_ib = os.path.join(img_dir, "init_boot.img")
                if b_info.get("is_gki_no_ramdisk") and os.path.exists(cand_ib):
                    restore_targets.append(("init_boot", cand_ib))
            elif part == "init_boot":
                cand_boot = os.path.join(img_dir, "boot.img")
                if os.path.exists(cand_boot):
                    restore_targets.append(("boot", cand_boot))

            devices = self.detect_devices(bypass_cache=True)
            dev = self._find_device_exact(devices, serial)
            if dev and dev["mode"] == "ADB":
                logs.append("Rebooting to Bootloader (Fastboot)...")
                reboot_res = self.reboot(serial, "ADB", "bootloader")
                if not adb_result_ok(reboot_res):
                    err_msg = f"Reboot to Fastboot failed for [{serial}]: {reboot_res.get('output', '')}"
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                time.sleep(3)

            if not dev or dev["mode"] != "FASTBOOT":
                fb_found = False
                for _ in range(20):
                    time.sleep(1.5)
                    fb_devs = self.detect_devices(bypass_cache=True)
                    fb = self._find_device_exact(fb_devs, serial, "FASTBOOT")
                    if fb:
                        fb_found = True
                        break
                if not fb_found:
                    err_msg = f"Exact target [{serial}] did not appear in FASTBOOT. Refusing to flash any other device."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
            fb_serial = serial

            failed_targets = []
            for target_part, target_img in restore_targets:
                logs.append(f"Restoring clean stock [{target_part}] image ({os.path.basename(target_img)})...")
                res = self.flash_partition(fb_serial, target_part, target_img)
                logs.append(res.get("output", ""))
                if not fastboot_step_ok(res):
                    failed_targets.append(target_part)
                has_slot = self._get_fastboot_var(fb_serial, f"has-slot:{target_part}")
                if has_slot and "yes" in has_slot.lower():
                    for slot in ("a", "b"):
                        slot_part = f"{target_part}_{slot}"
                        sres = self.flash_partition(fb_serial, slot_part, target_img)
                        logs.append(sres.get("output", ""))
                        if not fastboot_step_ok(sres):
                            failed_targets.append(slot_part)

            logs.append("Rebooting device to System...")
            reboot_res = self.reboot(fb_serial, "FASTBOOT", "system")
            if not fastboot_result_ok(reboot_res):
                err_msg = f"Reboot to system failed for [{fb_serial}]: {reboot_res.get('output', '')}"
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "failed_partitions": failed_targets, "logs": logs}

            if failed_targets:
                err_msg = f"Failed to restore partition(s): {', '.join(failed_targets)}"
                logs.append(f"❌ Root uninstallation failed: {err_msg}")
                return {"success": False, "error": err_msg, "failed_partitions": failed_targets, "logs": logs}

        all_ok = not failed_pkgs
        err_msg = None
        if failed_pkgs:
            err_msg = f"Could not remove root manager package(s): {', '.join(failed_pkgs)}"
            logs.append(f"⚠️ {err_msg}")
        logs.append("Root uninstallation completed!" if all_ok else "Root uninstallation finished with warnings.")
        return {
            "success": all_ok,
            "error": err_msg,
            "failed_packages": failed_pkgs,
            "logs": logs
        }

    # 🔥 XIAOMI & POCO BOOT / INIT_BOOT AUTO-DOWNLOADER (FROM OFFICIAL FIRMWARE TRACKER)
    def fetch_xiaomi_rom_versions(self, codename: str, region_code: str = "ALL") -> Dict[str, Any]:
        """Queries official Xiaomi miui-updates-tracker RSS for codename and filters by region."""
        clean_code = codename.strip().lower()
        if clean_code in MODEL_TO_CODENAME:
            clean_code = MODEL_TO_CODENAME[clean_code]

        rss_url = f"https://raw.githubusercontent.com/XiaomiFirmwareUpdater/miui-updates-tracker/master/rss/{clean_code}.xml"
        try:
            req = urllib.request.Request(rss_url, headers={"User-Agent": "ROM-Flasher-Tool"})
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall("./channel/item")
            versions_map = {}
            target_reg = region_code.upper() if region_code else "ALL"

            for item in items:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                desc = item.findtext("description", "")

                m = re.search(r"(OS\d+\.[\d\.]+\.[A-Z0-9]+|V\d+\.[\d\.]+\.[A-Z0-9]+)", title)
                if not m:
                    continue
                ver = m.group(1)

                parts = ver.split('.')
                country_code = ""
                if len(parts) >= 2 and len(parts[-1]) >= 6:
                    country_code = parts[-1][3:5]

                # Determine Region Name
                reg_name = "Global"
                if country_code == "IN": reg_name = "India"
                elif country_code == "CN": reg_name = "China"
                elif country_code == "EU": reg_name = "Europe (EEA)"
                elif country_code == "RU": reg_name = "Russia"
                elif country_code == "ID": reg_name = "Indonesia"
                elif country_code == "TR": reg_name = "Turkey"
                elif country_code == "TW": reg_name = "Taiwan"
                elif country_code == "MI": reg_name = "Global"

                # Region is derived ONLY from the build code segment (never from title/link text
                # or from an empty country_code plus a '_global_' substring).
                match = False
                if target_reg in ("", "ALL"):
                    match = True
                elif country_code:
                    match = (country_code == target_reg)

                if not match:
                    continue

                if ver not in versions_map:
                    versions_map[ver] = {
                        "version": ver,
                        "codename": clean_code,
                        "region": country_code or "MI",
                        "region_name": reg_name,
                        "android_version": "",
                        "fastboot_url": None,
                        "recovery_url": None,
                        "fastboot_filename": "",
                        "recovery_filename": "",
                        "date": pub_date,
                        "mirrors": []
                    }

                # Accurately extract modern Android Version (Android 16, Android 15, Android 14, etc.)
                if not versions_map[ver]["android_version"]:
                    parsed_android = ""
                    # 1. Search in description for RSS pipe delimiter: <p><b>Version:</b> OS3.0.303.0.WOJIDXM | 16.0</p>
                    m_desc_pipe = re.search(r"\|\s*([12]?\d(?:\.0)?)", desc)
                    if m_desc_pipe:
                        try:
                            num = int(m_desc_pipe.group(1).split('.')[0])
                            if 10 <= num <= 20:
                                parsed_android = f"Android {num}"
                        except Exception:
                            pass

                    # 2. Search in title or description for explicit "Android 16", "Android 15", etc.
                    if not parsed_android:
                        m_title = re.search(r"android\s*([12]?\d)(?:\.0)?", f"{title} {desc}", re.IGNORECASE)
                        if m_title:
                            try:
                                num = int(m_title.group(1))
                                if 10 <= num <= 20:
                                    parsed_android = f"Android {num}"
                            except Exception:
                                pass

                    # 3. Search in link/filename for delimiter-bounded Android version token (_16.0_, -user-16.0-, etc.)
                    if not parsed_android:
                        m_link = re.search(r"[_\-](1[0-9](?:\.0)?|[89](?:\.0)?)[_\.\-]", link)
                        if m_link:
                            try:
                                num = int(m_link.group(1).split('.')[0])
                                if 9 <= num <= 20:
                                    parsed_android = f"Android {num}"
                            except Exception:
                                pass

                    # 4. Fallback based on HyperOS / MIUI base version
                    if not parsed_android:
                        if ver.startswith("OS3."):
                            parsed_android = "Android 16"
                        elif ver.startswith("OS2."):
                            parsed_android = "Android 15"
                        elif ver.startswith("OS1."):
                            parsed_android = "Android 14"
                        elif ver.startswith("V14."):
                            parsed_android = "Android 13"
                        elif ver.startswith("V13."):
                            parsed_android = "Android 12"
                        elif ver.startswith("V12.5"):
                            parsed_android = "Android 11"
                        elif ver.startswith("V12.0") or ver.startswith("V12."):
                            parsed_android = "Android 10"

                    versions_map[ver]["android_version"] = parsed_android

                is_fastboot = "fastboot" in title.lower() or link.endswith(".tgz") or link.endswith(".tar.gz")
                is_recovery = "recovery" in title.lower() or link.endswith(".zip")

                if is_fastboot and not versions_map[ver]["fastboot_url"]:
                    versions_map[ver]["fastboot_url"] = link
                    versions_map[ver]["fastboot_filename"] = os.path.basename(urllib.parse.urlparse(link).path)
                if is_recovery and not versions_map[ver]["recovery_url"]:
                    versions_map[ver]["recovery_url"] = link
                    versions_map[ver]["recovery_filename"] = os.path.basename(urllib.parse.urlparse(link).path)

            # Generate high-speed CDN mirrors (BigOTA & HugeOTA)
            for v_obj in versions_map.values():
                urls = [u for u in [v_obj["fastboot_url"], v_obj["recovery_url"]] if u]
                for u in urls:
                    parsed = urllib.parse.urlparse(u)
                    path = parsed.path
                    m1 = f"https://bigota.d.miui.com{path}"
                    m2 = f"https://hugeota.d.miui.com{path}"
                    for m in [m1, m2]:
                        if m != u and m not in v_obj["mirrors"]:
                            v_obj["mirrors"].append(m)

            return {"success": True, "versions": list(versions_map.values())}
        except Exception as e:
            return {"success": False, "error": str(e), "versions": []}

    @staticmethod
    def _boot_image_cache_ok(path: str) -> bool:
        """A boot image is only trusted as cached when a completion marker matches its size and magic."""
        if not path or not os.path.isfile(path) or os.path.getsize(path) <= 1024 * 1024:
            return False
        marker = path + ".complete"
        if not os.path.isfile(marker):
            return False
        try:
            expected = str(os.path.getsize(path))
            with open(marker, "r", encoding="utf-8") as mf:
                if mf.read().strip() != expected:
                    return False
            with open(path, "rb") as bf:
                return bf.read(8) == b"ANDROID!"
        except Exception:
            return False

    @staticmethod
    def _mark_boot_image(path: str):
        """Write a completion marker only after a full boot image has been written."""
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 1024 * 1024:
                with open(path + ".complete", "w", encoding="utf-8") as mf:
                    mf.write(str(os.path.getsize(path)))
        except Exception:
            pass

    def download_xiaomi_boot_images(self, codename: str, version: str, download_url: str, recovery_url: Optional[str] = None, progress_cb=None) -> Dict[str, Any]:
        """
        Extracts boot.img and init_boot.img on the fly from official Xiaomi ROM.
        Uses HTTP Range Remote-Zip extraction when recovery_url is available to extract boot images in seconds (zero full-ROM streaming).
        Falls back to live streaming chunk extraction for fastboot archives.
        """
        logs = []
        clean_code = codename.strip().lower()
        if clean_code in MODEL_TO_CODENAME:
            clean_code = MODEL_TO_CODENAME[clean_code]

        def _report(msg: str, pct: int):
            logs.append(msg)
            if progress_cb:
                try:
                    progress_cb(msg, pct)
                except:
                    pass

        _report(f"Preparing to download boot images for {clean_code} ({version})...", 5)
        # Android 13+ devices need init_boot.img too; never report success with a
        # single image unless the device is explicitly known to be A-only.
        version_match = re.search(r'(?<!\d)(1[3-9]|2[0-9])(?!\d)', str(version or ""))
        needs_init_boot = (clean_code not in _KNOWN_A_ONLY_CODENAMES
                           and (not version_match or int(version_match.group(1)) >= 13))
        expected_images = ["boot.img"] + (["init_boot.img"] if needs_init_boot else [])

        if getattr(self, "_cancel_pending", False):
            return {"success": False, "cancelled": True, "error": "Download cancelled", "logs": logs}
        self._cancel_download = False
        _download_gen = self._download_generation

        def _cancelled():
            return bool(getattr(self, "_cancel_download", False)
                        or getattr(self, "_cancel_pending", False)
                        or self._download_generation != _download_gen)

        def _cancel_result():
            self._cancel_download = True
            for name in expected_images:
                try:
                    os.remove(os.path.join(out_dir, name))
                except Exception:
                    pass
            return {"success": False, "cancelled": True, "error": "Download cancelled", "logs": logs}

        def _expected_ok():
            return all(self._boot_image_cache_ok(os.path.join(out_dir, name))
                       for name in expected_images)

        def _complete_result(pct):
            if not _expected_ok():
                return None
            return {
                "success": True, "folder": out_dir,
                "boot_img": boot_path if self._boot_image_cache_ok(boot_path) else None,
                "init_boot_img": init_boot_path if self._boot_image_cache_ok(init_boot_path) else None,
                "logs": logs,
            }

        storage = storage_path_for(download_url, "Boot_Images")
        if not storage.get("success"):
            return storage
        safe_code = re.sub(r'[^A-Za-z0-9._-]', '_', clean_code)
        safe_ver = re.sub(r'[^A-Za-z0-9._-]', '_', str(version or "latest"))
        out_dir = os.path.join(storage["path"], f"{safe_code}_{safe_ver}")
        os.makedirs(out_dir, exist_ok=True)

        boot_path = os.path.join(out_dir, "boot.img")
        init_boot_path = os.path.join(out_dir, "init_boot.img")
        if all(os.path.isfile(os.path.join(out_dir, name)) for name in expected_images):
            cached = _complete_result(100)
            if cached:
                _report(f"Found complete cached boot image set in: {out_dir}", 100)
                return cached

        # 🚀 METHOD 1: High-Speed HTTP Range Remote-Zip Extraction (Instant ~5-15 Sec)
        # Evaluates candidate recovery URLs (Aliyun Singapore OSS CDN & BigOTA CDN)
        if not recovery_url or not recovery_url.endswith('.zip'):
            # Auto-discover recovery URL for this version to enable instant range extraction
            try:
                v_res = self.fetch_xiaomi_rom_versions(clean_code)
                if v_res.get("success"):
                    for v_item in v_res.get("versions", []):
                        if v_item.get("version") == version and v_item.get("recovery_url"):
                            recovery_url = v_item["recovery_url"]
                            break
            except:
                pass

        raw_zip_targets = []
        if recovery_url and recovery_url.endswith('.zip'):
            parsed = urllib.parse.urlparse(recovery_url)
            # Prioritize Singapore Aliyun OSS CDN (10x+ faster & reliable Range requests) before BigOTA/HugeOTA
            ali_mirror = f"https://bkt-sgp-miui-ota-update-alisgp.oss-ap-southeast-1.aliyuncs.com{parsed.path}"
            if ali_mirror not in raw_zip_targets:
                raw_zip_targets.append(ali_mirror)
            if recovery_url not in raw_zip_targets:
                raw_zip_targets.append(recovery_url)
            huge_mirror = f"https://hugeota.d.miui.com{parsed.path}"
            if huge_mirror not in raw_zip_targets:
                raw_zip_targets.append(huge_mirror)
        elif download_url and download_url.endswith('.zip'):
            raw_zip_targets.append(download_url)

        for zip_target in raw_zip_targets:
            _report("Connecting to official Recovery package via High-Speed Range Extractor...", 15)
            try:
                hrf = HttpRangeFile(zip_target, block_size=1024*1024, timeout=20)
                _report(f"Remote archive connected ({hrf.total_size // (1024*1024)} MB). Scanning central directory...", 30)
                with zipfile.ZipFile(hrf) as zf:
                    znames = zf.namelist()
                    boot_entry = next((n for n in znames if n.lower().endswith("/boot.img") or n.lower() == "boot.img"), None)
                    init_boot_entry = next((n for n in znames if n.lower().endswith("/init_boot.img") or n.lower() == "init_boot.img"), None)

                    # Case A: Legacy MIUI with direct boot images in root of ZIP
                    if boot_entry:
                        b_info = zf.getinfo(boot_entry)
                        _report(f"Downloading official boot.img directly ({b_info.compress_size // (1024*1024)} MB)...", 50)
                        with zf.open(boot_entry) as src, open(boot_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        self._mark_boot_image(boot_path)
                        _report("boot.img extracted successfully!", 75)

                    if init_boot_entry:
                        ib_info = zf.getinfo(init_boot_entry)
                        _report(f"Downloading official init_boot.img directly ({ib_info.compress_size // (1024*1024)} MB)...", 85)
                        with zf.open(init_boot_entry) as src, open(init_boot_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        self._mark_boot_image(init_boot_path)
                        _report("init_boot.img extracted successfully!", 95)

                    # Case B: Modern HyperOS & Android 13+ OTA (payload.bin inside ZIP)
                    payload_entry = next((n for n in znames if is_payload_entry(n)), None)
                    if payload_entry and (not os.path.exists(boot_path) and not os.path.exists(init_boot_path)):
                        _report("Detected modern HyperOS payload.bin OTA package. Reading remote manifest...", 40)
                        import struct, lzma, bz2
                        import payload_dumper.update_metadata_pb2 as um

                        p_info = zf.getinfo(payload_entry)
                        # Read local file header to locate exact payload bytes
                        hrf.seek(p_info.header_offset)
                        lhdr = hrf.read(30)
                        fn_len, extra_len = struct.unpack('<HH', lhdr[26:30])
                        p_data_start = p_info.header_offset + 30 + fn_len + extra_len

                        # Version-aware payload header: v1 has no signature-size field,
                        # v2/v3 store a 4-byte metadata signature size at offset 20.
                        hrf.seek(p_data_start)
                        p_hdr = hrf.read(20)
                        if len(p_hdr) >= 20 and p_hdr[:4] == b"CrAU":
                            payload_version = struct.unpack('>Q', p_hdr[4:12])[0]
                            manifest_len = struct.unpack('>Q', p_hdr[12:20])[0]
                            sig_len = 0
                            header_len = 20
                            if payload_version > 1:
                                sig_field = hrf.read(4)
                                if len(sig_field) != 4:
                                    raise ValueError("Truncated payload signature header")
                                sig_len = struct.unpack('>I', sig_field)[0]
                                header_len = 24
                            m_start = p_data_start + header_len
                            hrf.seek(m_start)
                            m_bytes = hrf.read(manifest_len)

                            dam = um.DeltaArchiveManifest()
                            dam.ParseFromString(m_bytes)
                            block_sz = dam.block_size
                            ops_data_base = m_start + manifest_len + sig_len

                            for part_name, out_target_path, pct_step in [('init_boot', init_boot_path, 75), ('boot', boot_path, 95)]:
                                part_obj = next((p for p in dam.partitions if p.partition_name == part_name), None)
                                if not part_obj or not part_obj.operations:
                                    continue

                                valid_ops = [op for op in part_obj.operations if op.data_length > 0]
                                if not valid_ops:
                                    continue

                                min_off = min(op.data_offset for op in valid_ops)
                                max_off = max(op.data_offset + op.data_length for op in valid_ops)
                                total_op_bytes = max_off - min_off
                                _report(f"Extracting official {part_name}.img directly ({total_op_bytes / (1024*1024):.1f} MB download)...", pct_step - 15)

                                # Fast chunked Range fetch for target partition with live MB/s progress
                                range_start = ops_data_base + min_off
                                range_end = ops_data_base + max_off - 1
                                req = urllib.request.Request(hrf.url, headers={'Range': f'bytes={range_start}-{range_end}', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                                with urllib.request.urlopen(req, timeout=20) as resp:
                                    validate_range_response(resp, range_start, range_end)
                                    chunks = []
                                    downloaded = 0
                                    t_dl = time.time()
                                    last_dl_up = t_dl
                                    while True:
                                        if _cancelled():
                                            return _cancel_result()
                                        buf = resp.read(262144)
                                        if not buf:
                                            break
                                        chunks.append(buf)
                                        downloaded += len(buf)
                                        now = time.time()
                                        if now - last_dl_up >= 0.4:
                                            mb_done = downloaded / (1024 * 1024)
                                            mb_tot = total_op_bytes / (1024 * 1024)
                                            spd = mb_done / max(0.01, now - t_dl)
                                            sub_pct = (pct_step - 15) + int(13 * min(1.0, downloaded / max(1, total_op_bytes)))
                                            _report(f"Downloading {part_name}.img: {mb_done:.1f}/{mb_tot:.1f} MB ({spd:.1f} MB/s)...", sub_pct)
                                            last_dl_up = now
                                    raw_blob = b"".join(chunks)

                                tmp_out = out_target_path + "." + secrets.token_hex(6) + ".tmp"
                                with open(tmp_out, "wb") as dst:
                                    for op in part_obj.operations:
                                        if op.data_length > 0:
                                            rel = op.data_offset - min_off
                                            chunk = raw_blob[rel : rel + op.data_length]
                                            if op.type == op.REPLACE_XZ:
                                                data = lzma.LZMADecompressor().decompress(chunk)
                                            elif op.type == op.REPLACE_BZ:
                                                data = bz2.BZ2Decompressor().decompress(chunk)
                                            elif op.type == op.REPLACE:
                                                data = chunk
                                            else:
                                                data = b''
                                            # A REPLACE operation can span multiple non-contiguous extents.
                                            # Write each extent its own slice of the decompressed payload.
                                            data_off = 0
                                            for ext in op.dst_extents:
                                                chunk_len = ext.num_blocks * block_sz
                                                if chunk_len <= 0:
                                                    continue
                                                chunk = data[data_off:data_off + chunk_len]
                                                if len(chunk) < chunk_len:
                                                    raise ValueError(f"Payload partition {part_name}: decompressed data is shorter than its destination extents")
                                                dst.seek(ext.start_block * block_sz)
                                                dst.write(chunk)
                                                data_off += chunk_len
                                        elif op.type == op.ZERO:
                                            for ext in op.dst_extents:
                                                dst.seek(ext.start_block * block_sz)
                                                dst.write(b'\x00' * ext.num_blocks * block_sz)
                                os.replace(tmp_out, out_target_path)
                                self._mark_boot_image(out_target_path)

                                _report(f"✓ {part_name}.img extracted successfully!", pct_step)

                completed = _complete_result(100)
                if completed:
                    _report(f"🎉 Official boot images extracted successfully into: {out_dir} (Zero full ROM download!)", 100)
                    return completed
                missing = [n for n in expected_images
                           if not self._boot_image_cache_ok(os.path.join(out_dir, n))]
                _report(f"Range extraction produced an incomplete image set "
                        f"(missing: {', '.join(missing)}).", 50)
            except Exception as e:
                _report(f"Range extractor notice for {zip_target}: {e}", 20)

        _report("Falling back to Fastboot package live streaming...", 25)

        # 🚀 METHOD 2: Fastboot Archive Streaming Fallback
        if not download_url:
            return {"success": False, "error": "No download URL available for this version.", "logs": logs}

        _report("Connecting to official Xiaomi Fastboot server...", 28)
        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                _report("Connection established. Streaming package...", 35)
                is_tgz = download_url.endswith(".tgz") or download_url.endswith(".tar.gz") or "fastboot" in download_url.lower()

                class LiveProgressSocket:
                    def __init__(self, raw_resp):
                        self.raw = raw_resp
                        self.bytes_read = 0
                        self.start_t = time.time()
                        self.last_up = self.start_t

                    def read(self, size=-1):
                        if _cancelled():
                            raise OSError("Download cancelled")
                        data = self.raw.read(size)
                        if data:
                            self.bytes_read += len(data)
                            now = time.time()
                            if now - self.last_up >= 0.4:
                                dt = now - self.start_t
                                spd = (self.bytes_read / (1024 * 1024)) / dt if dt > 0 else 0
                                mb = self.bytes_read / (1024 * 1024)
                                pct = min(92, 35 + int((self.bytes_read / (350 * 1024 * 1024)) * 55))
                                _report(f"Streaming archive... {mb:.1f} MB read ({spd:.1f} MB/s)", pct)
                                self.last_up = now
                        return data

                progress_sock = LiveProgressSocket(resp)

                if is_tgz:
                    with tarfile.open(mode="r|gz", fileobj=progress_sock) as tar:
                        extracted = []
                        for member in tar:
                            m_lower = member.name.lower()
                            if m_lower.endswith("/boot.img") or m_lower == "boot.img":
                                _report(f"Extracting {os.path.basename(member.name)} ({member.size // (1024*1024)} MB)...", 85)
                                with open(boot_path, 'wb') as f_out:
                                    f_src = tar.extractfile(member)
                                    if f_src:
                                        shutil.copyfileobj(f_src, f_out)
                                self._mark_boot_image(boot_path)
                                extracted.append("boot.img")
                            elif m_lower.endswith("/init_boot.img") or m_lower == "init_boot.img":
                                _report(f"Extracting {os.path.basename(member.name)} ({member.size // (1024*1024)} MB)...", 92)
                                with open(init_boot_path, 'wb') as f_out:
                                    f_src = tar.extractfile(member)
                                    if f_src:
                                        shutil.copyfileobj(f_src, f_out)
                                self._mark_boot_image(init_boot_path)
                                extracted.append("init_boot.img")

                            if "init_boot.img" in extracted and "boot.img" in extracted:
                                _report("Both boot.img and init_boot.img extracted successfully!", 98)
                                break
                            # If we reach large partition images (super, userdata, cust), boot images are done
                            if ("super.img" in m_lower or "userdata.img" in m_lower or "cust.img" in m_lower) and extracted:
                                _report(f"Extracted {', '.join(extracted)} successfully!", 98)
                                break

            completed = _complete_result(100)
            if completed:
                _report(f"Extraction completed into: {out_dir}", 100)
                return completed
            missing = [n for n in expected_images
                       if not self._boot_image_cache_ok(os.path.join(out_dir, n))]
            return {
                "success": False,
                "error": ("Incomplete boot image set; missing: " + ", ".join(missing)
                          + ". Try selecting your local ROM archive to extract instantly."),
                "logs": logs
            }
        except Exception as e:
            _report(f"Download error: {str(e)}", 0)
            if _cancelled():
                return _cancel_result()
            return {"success": False, "error": str(e), "logs": logs}

    # 1-Click Fast Extract Boot Images from any Local ROM (.tgz / .tar / .zip / folder)
    def extract_boot_from_local_rom(self, rom_path: str, out_dir: Optional[str] = None) -> Dict[str, Any]:
        """Extracts boot.img and init_boot.img from a local .tgz, .tar, .zip, or folder in 1-2 seconds."""
        if not os.path.exists(rom_path):
            return {"success": False, "error": f"File or folder not found: {rom_path}"}

        if not out_dir:
            out_dir = get_storage_dir("Extracted_Boot")
        os.makedirs(out_dir, exist_ok=True)

        boot_out = os.path.join(out_dir, "boot.img")
        init_boot_out = os.path.join(out_dir, "init_boot.img")
        vendor_boot_out = os.path.join(out_dir, "vendor_boot.img")
        extracted_files = {}

        if rom_path.lower().endswith((".img", ".bin")):
            base_name = os.path.basename(rom_path).lower()
            if "init_boot" in base_name:
                extracted_files["init_boot_img"] = rom_path
            elif "vendor_boot" in base_name:
                extracted_files["vendor_boot_img"] = rom_path
            else:
                extracted_files["boot_img"] = rom_path
            return {
                "success": True,
                "folder": os.path.dirname(rom_path),
                "boot_img": extracted_files.get("boot_img"),
                "init_boot_img": extracted_files.get("init_boot_img"),
                "vendor_boot_img": extracted_files.get("vendor_boot_img")
            }

        if os.path.isdir(rom_path):
            for root, dirs, files in os.walk(rom_path):
                for f in files:
                    fl = f.lower()
                    fp = os.path.join(root, f)
                    if fl == "boot.img":
                        shutil.copy2(fp, boot_out)
                        extracted_files["boot_img"] = boot_out
                    elif fl == "init_boot.img":
                        shutil.copy2(fp, init_boot_out)
                        extracted_files["init_boot_img"] = init_boot_out
                    elif fl == "vendor_boot.img":
                        shutil.copy2(fp, vendor_boot_out)
                        extracted_files["vendor_boot_img"] = vendor_boot_out

        elif rom_path.lower().endswith((".tar", ".tgz", ".tar.gz")):
            mode = "r:gz" if rom_path.lower().endswith((".tgz", ".tar.gz")) else "r:"
            with tarfile.open(rom_path, mode=mode) as tar:
                for member in tar:
                    ml = member.name.lower()
                    if ml.endswith("/boot.img") or ml == "boot.img":
                        with open(boot_out, "wb") as f:
                            f_src = tar.extractfile(member)
                            if f_src:
                                shutil.copyfileobj(f_src, f)
                        extracted_files["boot_img"] = boot_out
                    elif ml.endswith("/init_boot.img") or ml == "init_boot.img":
                        with open(init_boot_out, "wb") as f:
                            f_src = tar.extractfile(member)
                            if f_src:
                                shutil.copyfileobj(f_src, f)
                        extracted_files["init_boot_img"] = init_boot_out
                    elif ml.endswith("/vendor_boot.img") or ml == "vendor_boot.img":
                        with open(vendor_boot_out, "wb") as f:
                            f_src = tar.extractfile(member)
                            if f_src:
                                shutil.copyfileobj(f_src, f)
                        extracted_files["vendor_boot_img"] = vendor_boot_out

                    if "boot_img" in extracted_files and "init_boot_img" in extracted_files:
                        break

        elif rom_path.lower().endswith(".zip"):
            with zipfile.ZipFile(rom_path, "r") as z:
                names = z.namelist()
                has_payload = any(is_payload_entry(n) for n in names)
                if has_payload:
                    try:
                        # Use the same hash-verified, atomic extractor as Payload Dumper Studio.
                        extract_payload_images(rom_path, out_dir, ["boot", "init_boot", "vendor_boot"])
                        if os.path.exists(boot_out): extracted_files["boot_img"] = boot_out
                        if os.path.exists(init_boot_out): extracted_files["init_boot_img"] = init_boot_out
                        if os.path.exists(vendor_boot_out): extracted_files["vendor_boot_img"] = vendor_boot_out
                    except Exception as e:
                        return {"success": False, "error": f"Payload boot extraction failed: {e}",
                                "code": getattr(e, "code", None)}
                else:
                    for n in names:
                        nl = n.lower()
                        if nl.endswith("/boot.img") or nl == "boot.img":
                            with open(boot_out, "wb") as f:
                                f.write(z.read(n))
                            extracted_files["boot_img"] = boot_out
                        elif nl.endswith("/init_boot.img") or nl == "init_boot.img":
                            with open(init_boot_out, "wb") as f:
                                f.write(z.read(n))
                            extracted_files["init_boot_img"] = init_boot_out

        if extracted_files:
            return {
                "success": True,
                "folder": out_dir,
                "boot_img": extracted_files.get("boot_img"),
                "init_boot_img": extracted_files.get("init_boot_img"),
                "vendor_boot_img": extracted_files.get("vendor_boot_img")
            }
        return {"success": False, "error": "No boot.img or init_boot.img found in selected ROM archive"}

    # 🔥 HIGH-SPEED FULL ROM PACKAGE DOWNLOADER (MULTITHREADED / BUFFERED WITH LIVE MB/S & ETA)
    def download_rom_package(self, download_url: str, save_folder: Optional[str] = None, progress_cb=None) -> Dict[str, Any]:
        """Downloads full Fastboot (.tgz) or Recovery (.zip) package at full line speed with live stats."""
        # Honor a cancel issued just before start; a generation token closes the check/start race.
        if self._cancel_pending:
            self._cancel_pending = False
            self._cancel_download = True
            return {"success": False, "cancelled": True, "error": "Download cancelled"}
        gen = self._download_generation
        self._cancel_download = False
        if self._cancel_pending or self._download_generation != gen:
            return {"success": False, "cancelled": True, "error": "Download cancelled"}
        if not save_folder or not os.path.exists(save_folder):
            storage = storage_path_for(download_url, "ROM_Downloads")
            if not storage.get("success"):
                return storage
            save_folder = storage["path"]

        parsed = urllib.parse.urlparse(download_url)
        raw_name = urllib.parse.unquote(os.path.basename(parsed.path)) or "xiaomi_rom.tgz"
        safe_name = "".join(ch if re.match(r"[A-Za-z0-9._-]", ch) else "_" for ch in raw_name).strip("._")
        if not safe_name or ".." in safe_name or safe_name in (".", ".."):
            safe_name = "xiaomi_rom.tgz"
        filename = safe_name
        target_path = os.path.join(save_folder, filename)
        part_path = target_path + ".part"

        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                # The original URL is often a redirector/API endpoint: derive the real
                # filename from the FINAL URL or Content-Disposition instead.
                final_url = getattr(resp, "url", "") or resp.geturl()
                disposition = resp.headers.get("Content-Disposition", "") or ""
                cd_name = ""
                ext_name = re.search(r"filename\*\s*=\s*(?:[^'\r\n]*'')?([^;\r\n]+)", disposition, re.I)
                if ext_name:
                    cd_name = urllib.parse.unquote(ext_name.group(1).strip().strip('"'))
                else:
                    plain_name = re.search(r'\bfilename\s*=\s*(?:"([^"]+)"|([^;\r\n]+))', disposition, re.I)
                    if plain_name:
                        cd_name = (plain_name.group(1) or plain_name.group(2) or "").strip()
                derived_name = cd_name or urllib.parse.unquote(
                    os.path.basename(urllib.parse.urlparse(final_url).path)) or safe_name
                safe_derived = "".join(ch if re.match(r"[A-Za-z0-9._-]", ch) else "_"
                                       for ch in derived_name).strip("._")
                if safe_derived and ".." not in safe_derived:
                    filename = safe_derived
                target_path = os.path.join(save_folder, filename)
                part_path = target_path + ".part"

                total_size = int(resp.headers.get("Content-Length", 0) or 0)
                downloaded = 0
                start_time = time.time()
                last_time = start_time
                last_downloaded = 0

                chunk_size = 1024 * 1024  # 1 MB buffer for maximum download throughput
                with open(part_path, "wb") as f_out:
                    while True:
                        if self._cancel_download or self._cancel_pending or self._download_generation != gen:
                            self._cancel_download = True
                            f_out.close()
                            if os.path.exists(part_path):
                                try: os.remove(part_path)
                                except: pass
                            return {"success": False, "cancelled": True, "error": "Download cancelled"}

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if now - last_time >= 0.5:
                            duration = now - last_time
                            bytes_diff = downloaded - last_downloaded
                            speed_mb = (bytes_diff / (1024 * 1024)) / duration if duration > 0 else 0
                            pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                            rem_bytes = max(0, total_size - downloaded)
                            eta_sec = int(rem_bytes / (speed_mb * 1024 * 1024)) if speed_mb > 0 else 0

                            if progress_cb:
                                progress_cb({
                                    "filename": filename,
                                    "downloaded_bytes": downloaded,
                                    "total_bytes": total_size,
                                    "downloaded_mb": round(downloaded / (1024 * 1024), 1),
                                    "total_mb": round(total_size / (1024 * 1024), 1),
                                    "speed_mb": round(speed_mb, 1),
                                    "eta_seconds": eta_sec,
                                    "percent": pct
                                })
                            last_time = now
                            last_downloaded = downloaded

            if downloaded == 0:
                raise ValueError("Incomplete download: received 0 bytes.")
            # Unknown/zero Content-Length is fine when the stream ends cleanly, but a
            # declared size is still enforced exactly.
            if total_size > 0 and downloaded != total_size:
                raise ValueError(f"Incomplete download: received {downloaded} bytes, expected {total_size} bytes.")

            integrity_ok, integrity_detail = verify_rom_archive(part_path)
            if not integrity_ok:
                raise ValueError(f"Archive integrity check failed: {integrity_detail}")

            if os.path.exists(target_path):
                try: os.remove(target_path)
                except: pass
            os.rename(part_path, target_path)

            if progress_cb:
                progress_cb({
                    "filename": filename,
                    "downloaded_bytes": downloaded,
                    "total_bytes": downloaded,
                    "downloaded_mb": round(downloaded / (1024 * 1024), 1),
                    "total_mb": round(downloaded / (1024 * 1024), 1),
                    "speed_mb": 0,
                    "eta_seconds": 0,
                    "percent": 100,
                    "completed": True,
                    "file_path": target_path
                })

            return {"success": True, "file_path": target_path, "filename": filename, "folder": save_folder}
        except Exception as e:
            if os.path.exists(part_path):
                try: os.remove(part_path)
                except: pass
            return {"success": False, "error": str(e)}

    def cancel_rom_download(self) -> Dict[str, Any]:
        self._cancel_pending = True
        self._cancel_download = True
        self._download_generation += 1
        return {"status": "cancelled"}

    # Universal APK / APKS / XAPK & App_Backups Multi-Method Installer
    def universal_install_app(self, serial: str, file_path: str) -> Dict[str, Any]:
        device_err = self._require_adb_device(serial)
        if device_err:
            return {"success": False, "error": device_err, "output": device_err, "logs": [device_err]}
        if not file_path or not os.path.exists(file_path):
            detail = f"File or folder not found: {file_path}"
            return {"success": False, "error": detail, "output": detail, "logs": [detail]}

        logs = [f"Preparing installation on {serial}: {os.path.basename(file_path)}"]

        def _detail(res: Any) -> str:
            if isinstance(res, dict):
                return str(res.get("error") or res.get("output") or "").strip()
            return str(res or "")

        def _fail(detail: str) -> Dict[str, Any]:
            logs.append(detail)
            return {"success": False, "error": detail, "output": detail, "logs": logs}

        def _install_single(apk_path: str) -> tuple:
            logs.append(f"Method 1: Stream install with SDK/downgrade flags: {os.path.basename(apk_path)}")
            base_cmd = [self.adb_path, "-s", serial, "install"]
            res = self.run_cmd(base_cmd + ["-r", "-d", "-t", "--bypass-low-target-sdk-block", apk_path], timeout=180)
            logs.append(_detail(res))
            if adb_result_ok(res, r'\bSuccess\b'):
                return res, True

            if apk_flag_unsupported(res):
                logs.append("Method 2: Flag unsupported; retrying with -r -d -t...")
                res = self.run_cmd(base_cmd + ["-r", "-d", "-t", apk_path], timeout=180)
                logs.append(_detail(res))
                if adb_result_ok(res, r'\bSuccess\b'):
                    return res, True
            else:
                logs.append("Skipping flag retry: adb reported a real install failure.")

            logs.append("Method 3: Push to a unique staging path, then pm install...")
            remote_tmp = f"/data/local/tmp/rom_flasher_install_{secrets.token_hex(8)}.apk"
            try:
                push = self.run_cmd([self.adb_path, "-s", serial, "push", apk_path, remote_tmp], timeout=90)
                logs.append(_detail(push))
                if adb_result_ok(push):
                    pm = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "install", "-r", "-d", "-t", remote_tmp], timeout=180)
                    logs.append(_detail(pm))
                    if adb_result_ok(pm, r'\bSuccess\b'):
                        return pm, True
            finally:
                self.run_cmd([self.adb_path, "-s", serial, "shell", "rm", "-f", remote_tmp], timeout=10)

            logs.append("Method 4: Basic fallback install...")
            res = self.run_cmd(base_cmd + [apk_path], timeout=180)
            logs.append(_detail(res))
            return res, adb_result_ok(res, r'\bSuccess\b')

        def _install_splits(apk_files: List[str]) -> tuple:
            base_cmd = [self.adb_path, "-s", serial, "install-multiple"]
            logs.append(f"Installing {len(apk_files)} unique split APK(s) via install-multiple...")
            res = self.run_cmd(base_cmd + ["-r", "-d", "-t", "--bypass-low-target-sdk-block"] + apk_files, timeout=300)
            logs.append(_detail(res))
            if adb_result_ok(res, r'\bSuccess\b'):
                return res, True
            if apk_flag_unsupported(res):
                logs.append("Flag unsupported; retrying standard install-multiple...")
                res = self.run_cmd(base_cmd + ["-r", "-d", "-t"] + apk_files, timeout=300)
                logs.append(_detail(res))
                if adb_result_ok(res, r'\bSuccess\b'):
                    return res, True
            return res, False

        def _restore_extra_data(base_dir: str, pkg_name: str, archive_mode: bool = False) -> None:
            pkg = safe_package_name(pkg_name)
            if not pkg:
                logs.append("Skipping OBB/media restore: invalid or missing package name in backup.")
                return
            qpkg = shlex.quote(pkg)
            targets = [
                ("obb", "/sdcard/Android/obb", 300),
                ("media", "/sdcard/Android/media", 180),
            ]
            for sub, remote_base, timeout in targets:
                src = os.path.join(base_dir, sub)
                if not (os.path.isdir(src) and os.listdir(src)):
                    continue
                remote_dir = f"{remote_base}/{qpkg}"
                mkdir_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "mkdir", "-p", remote_dir], timeout=15)
                if not adb_result_ok(mkdir_res):
                    logs.append(f"Could not create {remote_base}/{pkg}: {_detail(mkdir_res)}")
                    continue
                push_res = self.run_cmd([self.adb_path, "-s", serial, "push", os.path.join(src, "."), f"{remote_dir}/"], timeout=timeout)
                if adb_result_ok(push_res):
                    logs.append(f"Restored {sub} data for {pkg}.")
                else:
                    logs.append(f"Failed to restore {sub} data for {pkg}: {_detail(push_res)}")

        def _archive_package(base_dir: str) -> str:
            for name in ("manifest.json", "backup_manifest.json"):
                path = os.path.join(base_dir, name)
                if not os.path.exists(path):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as mf:
                        data = json.load(mf)
                    for key in ("package", "package_name", "pkg"):
                        pkg = safe_package_name(data.get(key))
                        if pkg:
                            return pkg
                except Exception:
                    pass
            return ""

        # 1. Directory Installation (e.g. from App_Backups/<AppName_PackageName>/)
        if os.path.isdir(file_path):
            logs.append(f"Detected App Backup folder: {os.path.basename(file_path)}")
            try:
                apk_files = collect_install_apks(file_path)
            except Exception as e:
                return _fail(f"Could not read backup APK files: {e}")
            if not apk_files:
                return _fail("No unique APK files found inside the backup directory.")

            if len(apk_files) > 1:
                res, ok = _install_splits(apk_files)
            else:
                res, ok = _install_single(apk_files[0])

            if not ok:
                return _fail(f"Installation failed: {_detail(res) or 'adb reported a failure'}")

            logs.append("✅ Application installed successfully!")
            pkg_name = _archive_package(file_path)
            if not pkg_name:
                b_name = os.path.basename(os.path.normpath(file_path))
                pkg_name = b_name.rsplit("_", 1)[-1] if "_" in b_name else b_name
            _restore_extra_data(file_path, pkg_name)
            return {"success": True, "logs": logs, "output": "Success"}

        ext = os.path.splitext(file_path)[1].lower()

        if ext in (".xapk", ".apks", ".zip", ".apkm"):
            logs.append(f"Detected archive format ({ext}). Extracting split APKs safely...")
            temp_dir = tempfile.mkdtemp(prefix="split_apks_")
            try:
                try:
                    safe_extract_apk_archive(file_path, temp_dir)
                except Exception as e:
                    return _fail(f"Archive validation/extraction failed: {e}")
                try:
                    apk_files = collect_install_apks(temp_dir)
                except Exception as e:
                    return _fail(f"Could not read archive APK files: {e}")
                if not apk_files:
                    return _fail("No APK files found inside the archive.")

                if len(apk_files) > 1:
                    res, ok = _install_splits(apk_files)
                else:
                    res, ok = _install_single(apk_files[0])
                if not ok:
                    return _fail(f"Installation failed: {_detail(res) or 'adb reported a failure'}")

                logs.append("Installed successfully from archive!")
                pkg_name = _archive_package(temp_dir)
                if not pkg_name:
                    logs.append("Skipping OBB restore: archive manifest has no valid package name.")
                else:
                    obb_src = os.path.join(temp_dir, "obb")
                    if os.path.isdir(obb_src):
                        _restore_extra_data(temp_dir, pkg_name, archive_mode=True)
                return {"success": True, "logs": logs, "output": "Success"}
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Single APK
        res, ok = _install_single(file_path)
        if ok:
            logs.append("App installed successfully.")
            return {"success": True, "logs": logs, "output": "Success"}
        return _fail(f"Installation failed: {_detail(res) or 'adb reported a failure'}")

    # Debloater & Package Manager API
    def _package_set(self, res: Dict[str, Any]) -> set:
        result = set()
        for line in (res or {}).get("stdout", "").splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkg = safe_package_name(line.replace("package:", "", 1).strip())
                if pkg:
                    result.add(pkg)
        return result

    def get_installed_packages(self, serial: str) -> Dict[str, Any]:
        device_err = self._require_adb_device(serial)
        if device_err:
            return {"success": False, "error": device_err, "output": device_err,
                    "packages": [], "total": 0, "logs": [device_err]}

        f_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "list", "packages", "-f", "-u"], timeout=15)
        if not adb_result_ok(f_res):
            detail = f"Could not list packages on {serial}: {f_res.get('output', '')}"
            return {"success": False, "error": detail, "output": detail,
                    "packages": [], "total": 0, "logs": [detail]}

        d_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "list", "packages", "-d", "-u"], timeout=10)
        e_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "list", "packages", "-e"], timeout=10)
        u_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "list", "packages", "-3"], timeout=10)

        disabled_ok = adb_result_ok(d_res)
        enabled_ok = adb_result_ok(e_res)
        user_ok = adb_result_ok(u_res)
        disabled_set = self._package_set(d_res) if disabled_ok else set()
        enabled_set = self._package_set(e_res) if enabled_ok else set()
        user_set = self._package_set(u_res) if user_ok else set()

        warnings = []
        if not disabled_ok:
            warnings.append("Disabled-package query unavailable; using enabled list as fallback.")
        if not enabled_ok:
            warnings.append("Enabled-package query unavailable; disabled state may be incomplete.")
        if not user_ok:
            warnings.append("User-app query unavailable; using APK install path as fallback.")

        packages = []
        seen = set()
        for line in f_res.get("stdout", "").splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            line = line.replace("package:", "", 1).strip()
            if '=' in line:
                path, pkg_raw = line.rsplit('=', 1)
                path, pkg_raw = path.strip(), pkg_raw.strip()
            else:
                pkg_raw, path = line, ""
            pkg = safe_package_name(pkg_raw)
            if not pkg or pkg in seen:
                continue
            seen.add(pkg)

            is_user = (pkg in user_set) or path.startswith("/data/app/")
            if disabled_ok:
                is_disabled = pkg in disabled_set
            elif enabled_ok:
                is_disabled = pkg not in enabled_set
            else:
                is_disabled = False

            is_bloat = pkg in SAFE_BLOATWARE_PACKAGES
            packages.append({
                "package": pkg,
                "name": clean_label_from_package(pkg, path),
                "path": path,
                "is_system": not is_user,
                "is_disabled": is_disabled,
                "is_bloatware": is_bloat,
                "risk": "safe" if is_bloat or is_user else "system",
            })

        packages.sort(key=lambda x: str(x.get("name") or "").lower())
        return {"success": True, "total": len(packages), "packages": packages,
                "warnings": warnings, "logs": warnings}

    def _package_op_result(self, label: str, succeeded: List[str], failed: List[dict],
                           logs: List[str], invalid: List[str]) -> Dict[str, Any]:
        if invalid:
            logs.append(f"Rejected invalid package names: {', '.join(invalid)}")
        all_ok = not failed and not invalid
        error = None if all_ok else f"{label} finished with {len(failed)} failure(s)."
        return {
            "success": all_ok,
            "count": len(succeeded),
            "succeeded": succeeded,
            "failed": failed,
            "invalid": invalid,
            "error": error,
            "output": error or f"{label} complete",
            "logs": logs,
        }

    def uninstall_packages(self, serial: str, pkg_list: List[str]) -> Dict[str, Any]:
        device_err = self._require_adb_device(serial)
        if device_err:
            return {"success": False, "count": 0, "error": device_err,
                    "output": device_err, "failed": [], "logs": [device_err]}
        pkgs, invalid = sanitize_package_list(pkg_list)
        logs, succeeded, failed = [], [], []
        for pkg in pkgs:
            self.run_cmd([self.adb_path, "-s", serial, "shell", "am", "force-stop", pkg], timeout=10)
            res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "uninstall", "-k", "--user", "0", pkg], timeout=20)
            if not adb_result_ok(res, r'\bSuccess\b'):
                # Same user-0 keep-data semantics; never fall back to a data-wiping uninstall.
                res = self.run_cmd([self.adb_path, "-s", serial, "shell", "cmd", "package", "uninstall", "--user", "0", "-k", pkg], timeout=20)
            if adb_result_ok(res, r'\bSuccess\b'):
                succeeded.append(pkg)
                logs.append(f"Uninstalled for user 0 (data kept): {pkg}")
            else:
                detail = str(res.get("output", "") or "Unknown uninstall error").strip()
                failed.append({"package": pkg, "error": detail})
                logs.append(f"Failed to uninstall {pkg}: {detail}")
        return self._package_op_result("Uninstall", succeeded, failed, logs, invalid)

    def disable_packages(self, serial: str, pkg_list: List[str]) -> Dict[str, Any]:
        """
        Disables packages with verified ADB/pm results:
        1. pm disable-user --user 0
        2. pm uninstall -k --user 0 (HyperOS/MIUI freeze, keeps data)
        3. cmd package suspend --user 0
        4. root su pm disable (only when available)
        """
        device_err = self._require_adb_device(serial)
        if device_err:
            return {"success": False, "count": 0, "error": device_err,
                    "output": device_err, "failed": [], "logs": [device_err]}
        pkgs, invalid = sanitize_package_list(pkg_list)
        logs, succeeded, failed = [], [], []
        for pkg in pkgs:
            qpkg = shlex.quote(pkg)
            self.run_cmd([self.adb_path, "-s", serial, "shell", "am", "force-stop", pkg], timeout=10)

            disabled = False
            res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "disable-user", "--user", "0", pkg], timeout=15)
            if adb_result_ok(res, (r'\bdisabled\b', r'new state')):
                disabled = True
                logs.append(f"Disabled via pm disable-user: {pkg}")

            if not disabled:
                res2 = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "uninstall", "-k", "--user", "0", pkg], timeout=15)
                if adb_result_ok(res2, r'\bSuccess\b'):
                    disabled = True
                    logs.append(f"Frozen for user 0 (data kept): {pkg}")

            if not disabled:
                res3 = self.run_cmd([self.adb_path, "-s", serial, "shell", "cmd", "package", "suspend", "--user", "0", pkg], timeout=10)
                if adb_result_ok(res3, (r'suspended', r'\bSuccess\b')):
                    disabled = True
                    logs.append(f"Suspended: {pkg}")

            if not disabled:
                res_root = self.run_cmd([self.adb_path, "-s", serial, "shell", "su", "-c", f"pm disable-user --user 0 {qpkg}"], timeout=10)
                if adb_result_ok(res_root, (r'\bdisabled\b', r'new state')):
                    disabled = True
                    logs.append(f"Disabled via root: {pkg}")

            if disabled:
                succeeded.append(pkg)
            else:
                detail = str(res.get("output", "") or res2.get("output", "") or "Permission denied").strip()
                failed.append({"package": pkg, "error": detail})
                logs.append(f"Failed to disable {pkg}: {detail}")
        return self._package_op_result("Disable", succeeded, failed, logs, invalid)

    def enable_packages(self, serial: str, pkg_list: List[str]) -> Dict[str, Any]:
        """Restores disabled, suspended or user-0-uninstalled packages."""
        device_err = self._require_adb_device(serial)
        if device_err:
            return {"success": False, "count": 0, "error": device_err,
                    "output": device_err, "failed": [], "logs": [device_err]}
        pkgs, invalid = sanitize_package_list(pkg_list)
        logs, succeeded, failed = [], [], []
        for pkg in pkgs:
            qpkg = shlex.quote(pkg)
            enabled = False
            res1 = self.run_cmd([self.adb_path, "-s", serial, "shell", "cmd", "package", "install-existing", pkg], timeout=15)
            if adb_result_ok(res1, (r'installed', r'\bSuccess\b')):
                enabled = True
                logs.append(f"Restored existing package: {pkg}")
            if not enabled:
                res2 = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "install-existing", "--user", "0", pkg], timeout=15)
                if adb_result_ok(res2, (r'installed', r'\bSuccess\b')):
                    enabled = True
                    logs.append(f"Restored package for user 0: {pkg}")

            self.run_cmd([self.adb_path, "-s", serial, "shell", "cmd", "package", "unsuspend", "--user", "0", pkg], timeout=5)

            res4 = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "enable", pkg], timeout=10)
            if adb_result_ok(res4, (r'enabled', r'\bSuccess\b')):
                enabled = True
                logs.append(f"Enabled: {pkg}")
            if not enabled:
                res_root = self.run_cmd([self.adb_path, "-s", serial, "shell", "su", "-c", f"pm enable {qpkg}"], timeout=10)
                if adb_result_ok(res_root, (r'enabled', r'\bSuccess\b')):
                    enabled = True
                    logs.append(f"Enabled via root: {pkg}")

            if enabled:
                succeeded.append(pkg)
            else:
                detail = str(res1.get("output", "") or res2.get("output", "") or res4.get("output", "") or "Unknown enable error").strip()
                failed.append({"package": pkg, "error": detail})
                logs.append(f"Failed to enable {pkg}: {detail}")
        return self._package_op_result("Enable", succeeded, failed, logs, invalid)

    def open_app_backups_folder(self) -> Dict[str, Any]:
        """Opens the centralized App_Backups storage folder in Windows File Explorer."""
        folder = get_storage_dir("App_Backups")
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            return {"success": True, "path": folder}
        except Exception as e:
            return {"success": False, "error": str(e), "path": folder}

    def _pull_file_reliable(self, serial: str, remote_path: str, local_dest: str) -> bool:
        """
        Pulls a remote file from Android using verified fallbacks:
        1. adb pull
        2. adb exec-out cat (binary stream bypass)
        3. staging via a unique /data/local/tmp path
        4. root su copy fallback
        """
        if not remote_path or not local_dest:
            return False
        parent = os.path.dirname(local_dest)
        if parent:
            os.makedirs(parent, exist_ok=True)

        qremote = shlex.quote(remote_path)
        tmp_name = f"_bkp_{int(time.time())}_{secrets.token_hex(4)}_{os.path.basename(remote_path)}"
        tmp_remote = f"/data/local/tmp/{tmp_name}"
        qtmp = shlex.quote(tmp_remote)
        partial = local_dest + ".part"
        proc = None
        try:
            # Method 1: adb pull
            res1 = self.run_cmd([self.adb_path, "-s", serial, "pull", remote_path, local_dest], timeout=180)
            if adb_result_ok(res1) and os.path.exists(local_dest) and os.path.getsize(local_dest) > 0:
                return True

            # Method 2: adb exec-out cat (write to .part so failures never look complete)
            try:
                with open(partial, "wb") as f_out:
                    c_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    proc = subprocess.Popen(
                        [self.adb_path, "-s", serial, "exec-out", "cat", remote_path],
                        stdout=f_out,
                        stderr=subprocess.PIPE,
                        creationflags=c_flags
                    )
                    proc.communicate(timeout=180)
                if proc.returncode == 0 and os.path.exists(partial) and os.path.getsize(partial) > 1024:
                    os.replace(partial, local_dest)
                    return True
            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                    proc.communicate()
            except Exception:
                pass

            # Method 3: staging via a unique device temp path
            stage = self.run_cmd(
                [self.adb_path, "-s", serial, "shell", f"cp {qremote} {qtmp} && chmod 666 {qtmp}"],
                timeout=60
            )
            if adb_result_ok(stage):
                res3 = self.run_cmd([self.adb_path, "-s", serial, "pull", tmp_remote, local_dest], timeout=180)
                if adb_result_ok(res3) and os.path.exists(local_dest) and os.path.getsize(local_dest) > 0:
                    return True

            # Method 4: root su fallback
            stage_root = self.run_cmd(
                [self.adb_path, "-s", serial, "shell", "su", "-c", f"cp {qremote} {qtmp} && chmod 666 {qtmp}"],
                timeout=60
            )
            if adb_result_ok(stage_root):
                res4 = self.run_cmd([self.adb_path, "-s", serial, "pull", tmp_remote, local_dest], timeout=180)
                if adb_result_ok(res4) and os.path.exists(local_dest) and os.path.getsize(local_dest) > 0:
                    return True
            return False
        finally:
            for cleanup_cmd in (
                [self.adb_path, "-s", serial, "shell", f"rm -f {qtmp}"],
                [self.adb_path, "-s", serial, "shell", "su", "-c", f"rm -f {qtmp}"],
            ):
                try:
                    self.run_cmd(cleanup_cmd, timeout=10)
                except Exception:
                    pass
            for leftover in (partial, local_dest):
                try:
                    if os.path.exists(leftover) and os.path.getsize(leftover) == 0:
                        os.remove(leftover)
                except Exception:
                    pass

    def backup_packages(self, serial: str, pkg_list: List[str], backup_folder: Optional[str] = None) -> Dict[str, Any]:
        """
        Comprehensive Application & Game Backup Engine:
        - Backs up all Split APKs (base.apk, split_config.*.apk).
        - Backs up complete Game OBB data (/sdcard/Android/obb/<pkg>).
        - Backs up Media data (/sdcard/Android/media/<pkg>).
        - Backs up External App Data (/sdcard/Android/data/<pkg>).
        - Generates structured folder in ROM_Flasher_Storage/App_Backups/<AppName_PackageName>/.
        - Creates 1-click Restore_App_And_Data.bat & backup_manifest.json for instant offline restore.
        """
        device_err = self._require_adb_device(serial)
        if device_err:
            return {"success": False, "count": 0, "error": device_err,
                    "output": device_err, "failed": [], "logs": [device_err]}
        # This flow writes a user-runnable .bat with the serial embedded. Never
        # allow cmd.exe metacharacters into that file from a device-reported ID.
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", str(serial or "")):
            detail = "Device serial contains unsupported characters; refusing to generate a restore script."
            return {"success": False, "count": 0, "error": detail,
                    "output": detail, "failed": [], "logs": [detail]}

        def _safe_listed_name(value: str) -> str:
            """Device-side `ls` output must not become a Windows path."""
            name = os.path.basename(str(value or "").replace("\\", "/").strip())
            if not name or name in (".", "..") or "\x00" in name:
                return ""
            return name

        backup_root = os.path.realpath(get_storage_dir("App_Backups"))
        if not backup_folder:
            backup_folder = backup_root
        elif not os.path.isabs(backup_folder):
            backup_folder = os.path.join(backup_root, backup_folder)
        backup_folder = os.path.realpath(backup_folder)
        try:
            if os.path.commonpath([backup_root, backup_folder]) != backup_root:
                detail = "Backup folder must stay inside App_Backups."
                return {"success": False, "count": 0, "error": detail,
                        "output": detail, "failed": [], "logs": [detail]}
        except ValueError:
            detail = "Invalid backup folder path."
            return {"success": False, "count": 0, "error": detail,
                    "output": detail, "failed": [], "logs": [detail]}
        os.makedirs(backup_folder, exist_ok=True)

        logs = []
        count = 0
        total_files_backed_up = 0
        failed = []

        for pkg in pkg_list:
            clean_pkg = safe_package_name(pkg)
            if not clean_pkg:
                failed.append({"package": str(pkg), "error": "Invalid package name"})
                logs.append(f"Skipping invalid package name: {str(pkg)[:120]}")
                continue

            # 1. Determine friendly name and folder path
            friendly_name = KNOWN_APP_NAMES.get(clean_pkg, clean_pkg)
            safe_name = re.sub(r'[\\/*?:"<>|\.]+', "_", str(friendly_name)).strip(" _") or "app"
            folder_name = f"{safe_name}_{clean_pkg}" if safe_name != clean_pkg else clean_pkg
            target_app_dir = os.path.join(backup_folder, folder_name)
            os.makedirs(target_app_dir, exist_ok=True)

            apks_dir = os.path.join(target_app_dir, "apks")
            os.makedirs(apks_dir, exist_ok=True)

            # 2. Query APK paths using multiple methods
            p_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "path", clean_pkg], timeout=15)
            apk_paths = [l.replace("package:", "").strip() for l in p_res.get("stdout", "").splitlines() if l.startswith("package:")]

            # Fallback for uninstalled-for-user-0 or disabled apps
            if not apk_paths:
                p_res2 = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "path", "--user", "0", clean_pkg], timeout=10)
                apk_paths = [l.replace("package:", "").strip() for l in p_res2.get("stdout", "").splitlines() if l.startswith("package:")]

            if not apk_paths:
                p_res3 = self.run_cmd([self.adb_path, "-s", serial, "shell", "pm", "list", "packages", "-f", "-u", clean_pkg], timeout=15)
                for line in p_res3.get("stdout", "").splitlines():
                    if f"={clean_pkg}" in line and line.startswith("package:"):
                        apk_path = line.replace("package:", "").split(f"={clean_pkg}")[0].strip()
                        if apk_path:
                            apk_paths.append(apk_path)

            pulled_apks = []
            if apk_paths:
                logs.append(f"📦 Backing up APKs for {safe_name} ({len(apk_paths)} part(s))...")
                for r_apk in apk_paths:
                    apk_fname = _safe_listed_name(r_apk)
                    if not apk_fname:
                        continue
                    dest_apk = os.path.join(apks_dir, apk_fname)
                    ok = self._pull_file_reliable(serial, r_apk, dest_apk)
                    if ok:
                        pulled_apks.append(dest_apk)

                # If single APK, also make a copy directly as <package>.apk for instant file manager access
                if len(pulled_apks) == 1:
                    try:
                        shutil.copy2(pulled_apks[0], os.path.join(target_app_dir, f"{clean_pkg}.apk"))
                    except Exception:
                        pass

            # 3. Pull Game OBB Expansion Data (/sdcard/Android/obb/<pkg>)
            has_obb = False
            obb_files_pulled = 0
            qpkg = shlex.quote(clean_pkg)
            obb_check = self.run_cmd([self.adb_path, "-s", serial, "shell", f"ls -1 /sdcard/Android/obb/{qpkg} 2>/dev/null || ls -1 /storage/emulated/0/Android/obb/{qpkg} 2>/dev/null"], timeout=10)
            obb_items = [f.strip() for f in obb_check.get("stdout", "").splitlines() if f.strip() and not f.startswith("ls:")]
            if obb_items:
                logs.append(f"🎮 Found Game OBB data for {clean_pkg} ({len(obb_items)} file(s)). Backing up...")
                obb_dest = os.path.join(target_app_dir, "obb")
                os.makedirs(obb_dest, exist_ok=True)
                for item in obb_items:
                    safe_item = _safe_listed_name(item)
                    if not safe_item:
                        continue
                    remote_obb = f"/sdcard/Android/obb/{clean_pkg}/{item}"
                    dest_file = os.path.join(obb_dest, safe_item)
                    try:
                        in_dest = os.path.commonpath([os.path.realpath(obb_dest), os.path.realpath(dest_file)]) == os.path.realpath(obb_dest)
                    except ValueError:
                        in_dest = False
                    if not in_dest:
                        continue
                    if self._pull_file_reliable(serial, remote_obb, dest_file):
                        obb_files_pulled += 1
                if obb_files_pulled > 0:
                    has_obb = True
                    logs.append(f"✅ OBB Data successfully backed up ({obb_files_pulled} files) to: {obb_dest}")

            # 4. Pull Media Storage (/sdcard/Android/media/<pkg>)
            has_media = False
            media_files_pulled = 0
            media_check = self.run_cmd([self.adb_path, "-s", serial, "shell", f"ls -1 /sdcard/Android/media/{qpkg} 2>/dev/null || ls -1 /storage/emulated/0/Android/media/{qpkg} 2>/dev/null"], timeout=10)
            media_items = [f.strip() for f in media_check.get("stdout", "").splitlines() if f.strip() and not f.startswith("ls:")]
            if media_items:
                logs.append(f"📁 Backing up Media storage for {clean_pkg} ({len(media_items)} item(s))...")
                media_dest = os.path.join(target_app_dir, "media")
                os.makedirs(media_dest, exist_ok=True)
                for item in media_items:
                    safe_item = _safe_listed_name(item)
                    if not safe_item:
                        continue
                    remote_m = f"/sdcard/Android/media/{clean_pkg}/{item}"
                    dest_file = os.path.join(media_dest, safe_item)
                    try:
                        in_dest = os.path.commonpath([os.path.realpath(media_dest), os.path.realpath(dest_file)]) == os.path.realpath(media_dest)
                    except ValueError:
                        in_dest = False
                    if not in_dest:
                        continue
                    if self._pull_file_reliable(serial, remote_m, dest_file):
                        media_files_pulled += 1
                if media_files_pulled > 0:
                    has_media = True
                    logs.append(f"✅ Media storage backed up to: {media_dest}")

            # 5. Pull External Data (/sdcard/Android/data/<pkg>) if accessible
            has_data = False
            data_files_pulled = 0
            data_check = self.run_cmd([self.adb_path, "-s", serial, "shell", f"ls -1 /sdcard/Android/data/{qpkg} 2>/dev/null || ls -1 /storage/emulated/0/Android/data/{qpkg} 2>/dev/null"], timeout=10)
            data_items = [f.strip() for f in data_check.get("stdout", "").splitlines() if f.strip() and not f.startswith("ls:")]
            if data_items:
                data_dest = os.path.join(target_app_dir, "data")
                os.makedirs(data_dest, exist_ok=True)
                data_pull = self.run_cmd([self.adb_path, "-s", serial, "pull", f"/sdcard/Android/data/{clean_pkg}", data_dest], timeout=120)
                data_files_pulled = sum(len(files) for _, _, files in os.walk(data_dest)) if os.path.isdir(data_dest) else 0
                if adb_result_ok(data_pull) and data_files_pulled > 0:
                    has_data = True
                    logs.append(f"✅ External App Data backed up to: {data_dest} ({data_files_pulled} file(s))")
                else:
                    logs.append(f"⚠️ External App Data pull failed for {clean_pkg}: {data_pull.get('output', '')}")

            app_total_files = len(pulled_apks) + obb_files_pulled + media_files_pulled + data_files_pulled

            # If NO files could be pulled at all, clean up the empty folder and report failure
            if app_total_files == 0:
                try:
                    shutil.rmtree(target_app_dir, ignore_errors=True)
                except Exception:
                    pass
                detail = f"Could not pull any APK or data files for {clean_pkg}. Permission denied or app missing."
                failed.append({"package": clean_pkg, "error": detail})
                logs.append(f"⚠️ {detail}")
                continue

            total_files_backed_up += app_total_files

            # 6. Generate a real 1-click restore script (explicit files + exact serial)
            restore_bat_path = os.path.join(target_app_dir, "Restore_App_And_Data.bat")
            # Always quote both paths: an unquoted adb.exe path or serial lets
            # cmd.exe interpret spaces/metacharacters when the user runs the .bat.
            adb_exe = f'"{self.adb_path}"'
            bat_adb = f'{adb_exe} -s "{serial}"'
            apk_rels = [os.path.join("apks", os.path.basename(p)) for p in pulled_apks]
            if len(apk_rels) > 1:
                apk_args = " ".join(f'"{rel}"' for rel in apk_rels)
                apk_lines = [f'{bat_adb} install-multiple -r {apk_args}',
                             'if errorlevel 1 set RESTORE_FAILED=1']
            elif apk_rels:
                apk_lines = [f'{bat_adb} install -r "{apk_rels[0]}"',
                             'if errorlevel 1 set RESTORE_FAILED=1']
            else:
                apk_lines = ['echo No APK files were found in this backup.', 'set RESTORE_FAILED=1']
            apk_block = "\n".join(apk_lines)
            bat_content = f"""@echo off
set RESTORE_FAILED=0
echo ========================================================
echo Restoring {safe_name} ({clean_pkg}) to {serial}
echo ========================================================
echo [1/4] Installing APK packages...
{apk_block}
if exist "obb" (
    echo [2/4] Restoring Game OBB Expansion Data...
    {bat_adb} shell mkdir -p "/sdcard/Android/obb/{clean_pkg}"
    if errorlevel 1 set RESTORE_FAILED=1
    {bat_adb} push "obb\\." "/sdcard/Android/obb/{clean_pkg}/"
    if errorlevel 1 set RESTORE_FAILED=1
)
if exist "media" (
    echo [3/4] Restoring Media Storage...
    {bat_adb} shell mkdir -p "/sdcard/Android/media/{clean_pkg}"
    if errorlevel 1 set RESTORE_FAILED=1
    {bat_adb} push "media\\." "/sdcard/Android/media/{clean_pkg}/"
    if errorlevel 1 set RESTORE_FAILED=1
)
if exist "data" (
    echo [4/4] Restoring External App Data...
    {bat_adb} shell mkdir -p "/sdcard/Android/data/{clean_pkg}"
    if errorlevel 1 set RESTORE_FAILED=1
    {bat_adb} push "data\\." "/sdcard/Android/data/{clean_pkg}/"
    if errorlevel 1 set RESTORE_FAILED=1
)
echo ========================================================
if "%RESTORE_FAILED%"=="0" (
    echo Complete! {safe_name} has been restored successfully.
) else (
    echo Restore finished with errors. Check the output above.
)
pause
"""
            try:
                with open(restore_bat_path, "w", encoding="utf-8") as bf:
                    bf.write(bat_content)
            except Exception:
                pass

            # 7. Save Backup Manifest JSON
            manifest = {
                "package": clean_pkg,
                "name": safe_name,
                "serial": serial,
                "adb_path": self.adb_path,
                "backup_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "apk_parts": len(pulled_apks),
                "apk_files": [os.path.basename(p) for p in pulled_apks],
                "has_obb": has_obb,
                "has_media": has_media,
                "has_data": has_data,
                "data_files": data_files_pulled,
                "total_files": app_total_files,
                "backup_path": target_app_dir
            }
            try:
                with open(os.path.join(target_app_dir, "backup_manifest.json"), "w", encoding="utf-8") as mf:
                    json.dump(manifest, mf, indent=2)
            except Exception:
                pass

            logs.append(f"🎉 Fully backed up: {safe_name} ({clean_pkg}) -> {target_app_dir}")
            count += 1

        all_ok = count > 0 and not failed
        if count == 0:
            error = "No files could be retrieved"
        elif failed:
            error = f"Partial backup: {count} app(s) succeeded, {len(failed)} failed."
        else:
            error = None
        return {
            "success": all_ok,
            "partial": count > 0 and bool(failed),
            "count": count,
            "failed": failed,
            "total_files": total_files_backed_up,
            "backup_folder": backup_folder,
            "error": error,
            "output": error or f"Backed up {count} app(s)",
            "logs": logs
        }

    # Interactive Script Input
    def send_flash_input(self, text: str = "") -> Dict[str, Any]:
        """Sends user interactive choice (y/n/1/2/3/4/etc.) to running flash script stdin."""
        if getattr(self, "active_flash_proc", None) and self.active_flash_proc.poll() is None:
            try:
                stdin = self.active_flash_proc.stdin
                if stdin:
                    inp = (text.strip() if text else "") + "\r\n"
                    try:
                        # Generated .bat files are ASCII; cp1252 matches cmd.exe's
                        # default codepage and avoids UTF-8 byte sequences at the prompt.
                        stdin.write(inp.encode("cp1252", errors="replace"))
                    except (TypeError, AttributeError, LookupError):
                        stdin.write(inp)
                    stdin.flush()
                    return {"success": True, "output": f"Sent input: {text.strip() or 'Enter'}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "No active flashing script running."}

    # Driver Toolkit
    DRIVERS_PROJECT_URL = "https://github.com/Rohit-Bhai-Youtube/adb-fastboot-driver-toolkit"

    def install_drivers(self) -> Dict[str, Any]:
        msg = (
            "Automatic elevated driver installation is disabled for safety (no remote script piping with admin). "
            f"Please install the official Universal ADB/Fastboot driver manually from {self.DRIVERS_PROJECT_URL}: "
            "download the release, extract it, right-click the installer and run as Administrator, then reconnect the device."
        )
        return {"success": False, "output": msg, "error": msg, "url": self.DRIVERS_PROJECT_URL}

    def uninstall_drivers(self) -> Dict[str, Any]:
        msg = (
            "Automatic elevated driver removal is disabled for safety (no remote script piping with admin). "
            f"Please use Windows 'Apps & features' / Device Manager manually, or follow the official instructions at {self.DRIVERS_PROJECT_URL}."
        )
        return {"success": False, "output": msg, "error": msg, "url": self.DRIVERS_PROJECT_URL}

    @device_action_locked
    def fix_fastboot_driver(self) -> Dict[str, Any]:
        try:
            # 1. Check for bundled Zadig or C:\adb\zadig
            app_root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            zadig_paths = [
                os.path.join(app_root, "drivers", "zadig", "zadig-2.9.exe"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivers", "zadig", "zadig-2.9.exe"),
                r"C:\adb\zadig\zadig-2.9.exe"
            ]
            zadig_exe = next((zp for zp in zadig_paths if os.path.exists(zp)), None)

            if zadig_exe:
                # Pass the executable path as base64 inside an EncodedCommand so
                # quotes, '$()' and backticks in a filesystem path cannot be
                # interpreted by PowerShell.
                path_b64 = base64.b64encode(zadig_exe.encode("utf-8")).decode("ascii")
                ps_plain = (
                    "$ErrorActionPreference='Stop'\n"
                    f"$target=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{path_b64}'))\n"
                    "try { $p=Start-Process -FilePath $target -Verb RunAs -Wait -PassThru -ErrorAction Stop; "
                    "if ($null -eq $p -or $p.ExitCode -ne 0) { exit 2 } } catch { exit 3 }"
                )
                ps_cmd = ["powershell.exe", "-NoProfile", "-EncodedCommand",
                          base64.b64encode(ps_plain.encode("utf-16le")).decode("ascii")]
            else:
                # HKLM registry write must be elevated; request UAC explicitly and wait for the process.
                ps_cmd = r'''
$ErrorActionPreference = 'Stop'
try {
  $p = Start-Process -FilePath reg.exe -ArgumentList 'add "HKLM\SYSTEM\CurrentControlSet\Services\USB" /v DisableSelectiveSuspend /t REG_DWORD /d 1 /f' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
  if ($null -eq $p -or $p.ExitCode -ne 0) { exit 2 }
} catch { exit 3 }
'''

            ps_argv = ps_cmd if isinstance(ps_cmd, list) else ["powershell.exe", "-NoProfile", "-Command", ps_cmd]
            rec = subprocess.run(
                ps_argv,
                capture_output=True,
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if rec.returncode != 0:
                err = (rec.stderr or rec.stdout or b"").decode("utf-8", "replace").strip()
                return {
                    "success": False,
                    "output": f"Administrator permission is required for this driver fix (elevated process exited with code {rec.returncode}). {err}".strip(),
                    "error": "Elevation denied or driver fix failed."
                }

            dm_note = ""
            try:
                if sys.platform == "win32" and hasattr(os, "startfile"):
                    os.startfile("devmgmt.msc")
                else:
                    subprocess.Popen(["cmd.exe", "/c", "start", "devmgmt.msc"])
            except Exception as dm_err:
                dm_note = f" Device Manager could not be opened automatically: {dm_err}"

            return {"success": True, "output": "Administrator driver fix command completed. Verify the Android/Fastboot interface in Device Manager — select 'Android' -> Update Driver -> Android Bootloader Interface." + dm_note}
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Timed out waiting for the elevated driver fix process.", "error": "Elevation timeout."}
        except Exception as e:
            return {"success": False, "output": str(e)}

    def open_device_manager(self) -> Dict[str, Any]:
        try:
            if sys.platform == "win32" and hasattr(os, "startfile"):
                os.startfile("devmgmt.msc")
            else:
                subprocess.Popen(["cmd.exe", "/c", "start", "devmgmt.msc"])
            return {"success": True, "output": "Device Manager opened successfully."}
        except Exception as e:
            return {"success": False, "output": str(e)}

    # Standard Partition & Fastboot Flashing
    def is_fastbootd(self, serial: str) -> bool:
        """Detects if connected device is in userspace fastbootd."""
        res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", "is-userspace"], timeout=5)
        return "is-userspace: yes" in res.get("output", "").lower()

    def check_and_clear_vabc_snapshot(self, serial: str) -> Dict[str, Any]:
        """Cancel any dirty Virtual A/B snapshot before mutating fastboot operations."""
        try:
            res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", "snapshot-update-status"], timeout=5)
            m = re.search(r'snapshot-update-status:\s*([^\r\n]+)', res.get("output", ""), re.I)
            status = (m.group(1).strip() if m else "").lower()
            if status and status not in ("none", ""):
                cancel_res = self.run_cmd([self.fastboot_path, "-s", serial, "snapshot-update", "cancel"], timeout=10)
                ok = fastboot_result_ok(cancel_res) or "OKAY" in cancel_res.get("output", "").upper()
                return {"needed": True, "success": ok, "output": cancel_res.get("output", "")}
        except Exception as e:
            return {"needed": False, "success": False, "error": str(e)}
        return {"needed": False, "success": True, "output": ""}

    def _ensure_fastboot_ready(self, serial: str, need_fastbootd: bool = False) -> Dict[str, Any]:
        """Ensure the EXACT serial is reachable in fastboot (or fastbootd for dynamic partitions)."""
        devs = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devs, serial)
        if not dev:
            return {"success": False, "serial": serial,
                    "error": self._device_not_found_error(serial, "FASTBOOT or ADB")}

        if str(dev.get("mode", "")).upper() == "ADB":
            dev_state = str(dev.get("state", "")).lower()
            # Recovery/sideload shells commonly expose root; that is not a reason to block flashing.
            if dev_state not in ("sideload", "recovery"):
                mfr = self._get_prop(serial, "ro.product.manufacturer").lower()
                if "samsung" in mfr:
                    return {"success": False, "serial": serial, "error": "Samsung devices use Download Mode (Odin), not Fastboot! Fastboot flashing is not supported on Samsung."}
                if self._get_prop(serial, "sys.boot_completed").strip() == "1":
                    root_chk = self.run_cmd([self.adb_path, "-s", serial, "shell", "su -c id || su 0 id"], timeout=5)
                    if "uid=0" in (root_chk.get("stdout", "") or ""):
                        return {"success": False, "serial": serial, "error": "🚫 [BrickShield] Root (uid=0) detected on the exact target. Boot clean stock Android before fastboot operations."}
            target_mode = "fastbootd" if need_fastbootd else "bootloader"
            self.reboot(serial, "ADB", target_mode)
            for _ in range(25):
                time.sleep(1.5)
                fb_devs = self.detect_devices(bypass_cache=True)
                if self._find_device_exact(fb_devs, serial, "FASTBOOT"):
                    break
            else:
                return {"success": False, "serial": serial,
                        "error": f"Timed out waiting for selected device '{serial}' to enter Fastboot mode."}

        # A device merely appearing in `fastboot devices` is not enough: prove the transport works.
        prod_res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", "product"], timeout=10)
        if not fastboot_result_ok(prod_res):
            return {"success": False, "serial": serial,
                    "error": f"Selected device '{serial}' is not reachable in Fastboot: {prod_res.get('output', '').strip()[:200]}"}
        fb_product = (self._get_fastboot_var(serial, "product") or "").lower()
        if "samsung" in fb_product:
            return {"success": False, "serial": serial, "error": "Samsung fastboot product detected. Use Download Mode (Odin), not Fastboot."}
        fb_serialno = (self._get_fastboot_var(serial, "serialno") or "").strip()
        if fb_serialno and fb_serialno.lower() != serial.lower():
            return {"success": False, "serial": serial, "error": f"Fastboot serial mismatch: expected {serial}, device reported {fb_serialno}."}
        verified = (self._get_fastboot_var(serial, "verified") or "").strip()
        unlocked = (self._get_fastboot_var(serial, "unlocked") or "").strip()

        if need_fastbootd and not self.is_fastbootd(serial):
            self.run_cmd([self.fastboot_path, "-s", serial, "reboot", "fastboot"], timeout=15)
            for _ in range(25):
                time.sleep(1.5)
                if self.is_fastbootd(serial):
                    break
            else:
                return {"success": False, "serial": serial, "error": "Device did not enter fastbootd (Userspace Fastboot) required for dynamic partitions."}

        return {"success": True, "serial": serial, "product": fb_product,
                "verified": verified, "unlocked": unlocked}

    @device_action_locked
    def flash_partition(self, serial: str, partition: str, file_path: str, disable_avb: bool = False) -> Dict[str, Any]:
        if not os.path.isfile(file_path):
            return {"success": False, "output": f"Image file not found: {file_path}"}

        p_base = normalize_partition_name(partition)
        slot_m = re.search(r'_(a|b)$', str(partition).strip().lower())
        suffix = slot_m.group(1) if slot_m else ""
        is_super = p_base == "super"
        is_dynamic = p_base in (
            "system", "vendor", "product", "system_ext", "odm", "odm_dlkm",
            "system_dlkm", "vendor_dlkm", "pvmfb",
        ) or p_base.startswith("my_")
        ready = self._ensure_fastboot_ready(serial, need_fastbootd=is_dynamic)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error", "Device not ready in Fastboot")}
        serial = ready["serial"]

        snap = self.check_and_clear_vabc_snapshot(serial)
        if not snap.get("success"):
            return {"success": False, "output": f"Cannot flash while a Virtual A/B snapshot is dirty: {snap.get('error') or snap.get('output', '')}"}

        cmd = [self.fastboot_path, "-s", serial]
        if disable_avb and p_base.startswith("vbmeta"):
            cmd.extend(["--disable-verity", "--disable-verification"])

        try:
            size = os.path.getsize(file_path)
            lim_res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", "max-download-size"], timeout=5)
            m_lim = re.search(r'max-download-size:\s*(\S+)', lim_res.get("output", ""), re.I)
            if m_lim:
                limit = int(m_lim.group(1), 0)
                if limit > 0 and size > limit:
                    chunk_mb = max(1, min(512 * 1024 * 1024, limit) // (1024 * 1024))
                    cmd.extend(["-S", f"{chunk_mb}M"])
        except Exception:
            size = 0

        # Dynamic partitions are flashed unsuffixed in fastbootd; static partitions keep their slot.
        flash_target = p_base if is_dynamic or is_super else (f"{p_base}_{suffix}" if suffix else p_base)
        cmd.extend(["flash", flash_target, file_path])
        timeout = min(3600, max(900, int(size / (4 * 1024 * 1024)))) if size else 900
        res = self.run_cmd(cmd, timeout=timeout)
        res["raw_output"] = res.get("output", "")
        res["success"] = fastboot_result_ok(res)
        cleaned = clean_fastboot_log(res.get("output", ""))
        res["output"] = "\n".join(cleaned) if cleaned else res.get("raw_output", "").strip()
        return res

    @device_action_locked
    def boot_image(self, serial: str, file_path: str) -> Dict[str, Any]:
        if not os.path.isfile(file_path):
            return {"success": False, "output": f"Image file not found: {file_path}"}
        try:
            info = self.inspect_boot_image(file_path)
            if info.get("valid") and int(info.get("header_version", 0) or 0) >= 4:
                return {"success": False, "output": "Cannot 'fastboot boot' an init_boot image (header v4+). Flash init_boot directly instead."}
        except Exception:
            pass
        if "init_boot" in os.path.basename(file_path).lower():
            return {"success": False, "output": "Cannot 'fastboot boot' an init_boot.img! On Android 13+, fastboot boot only works with boot.img (or flash init_boot directly)."}
        ready = self._ensure_fastboot_ready(serial, need_fastbootd=False)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error", "Device not ready in Fastboot")}
        res = self.run_cmd([self.fastboot_path, "-s", ready["serial"], "boot", file_path], timeout=180)
        res["success"] = fastboot_result_ok(res)
        return res

    @device_action_locked
    def erase_partition(self, serial: str, partition: str) -> Dict[str, Any]:
        if str(partition or "").strip().lower() not in ("frp", "config"):
            return {"success": False, "output": f"Erase of partition '{partition}' is not allowed. Only FRP/config erase is supported here."}
        ready = self._ensure_fastboot_ready(serial)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error", "Device not ready in Fastboot")}
        serial = ready["serial"]
        snap = self.check_and_clear_vabc_snapshot(serial)
        if not snap.get("success"):
            return {"success": False, "output": f"Cannot erase while a Virtual A/B snapshot is dirty: {snap.get('error') or snap.get('output', '')}"}
        res = self.run_cmd([self.fastboot_path, "-s", serial, "erase", partition], timeout=90)
        res["raw_output"] = res.get("output", "")
        res["success"] = fastboot_result_ok(res)
        cleaned = clean_fastboot_log(res.get("output", ""))
        res["output"] = "\n".join(cleaned) if cleaned else res.get("raw_output", "").strip()
        return res

    @device_action_locked
    def format_wipe_data(self, serial: str) -> Dict[str, Any]:
        ready = self._ensure_fastboot_ready(serial)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error", "Device not ready in Fastboot")}
        serial = ready["serial"]
        snap = self.check_and_clear_vabc_snapshot(serial)
        if not snap.get("success"):
            return {"success": False, "output": f"Cannot wipe while a Virtual A/B snapshot is dirty: {snap.get('error') or snap.get('output', '')}"}
        res = self.run_cmd([self.fastboot_path, "-s", serial, "-w"], timeout=180)
        res["raw_output"] = res.get("output", "")
        res["success"] = fastboot_result_ok(res)
        cleaned = clean_fastboot_log(res.get("output", ""))
        res["output"] = "\n".join(cleaned) if cleaned else res.get("raw_output", "").strip()
        return res

    @device_action_locked
    def set_active_slot(self, serial: str, slot: str) -> Dict[str, Any]:
        slot_clean = str(slot or "").strip().lower().lstrip("_")
        if slot_clean not in ("a", "b"):
            return {"success": False, "output": f"Invalid slot '{slot}'. Expected 'a' or 'b'."}
        ready = self._ensure_fastboot_ready(serial, need_fastbootd=False)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error", "Device not ready in Fastboot")}
        serial = ready["serial"]
        snap = self.check_and_clear_vabc_snapshot(serial)
        if not snap.get("success"):
            fb_ready = self._ensure_fastboot_ready(serial, need_fastbootd=True)
            if not fb_ready.get("success") or not self.check_and_clear_vabc_snapshot(serial).get("success"):
                return {"success": False, "output": f"Cannot switch slot while a Virtual A/B snapshot is dirty: {snap.get('error') or snap.get('output', '')}"}
        res = self.run_cmd([self.fastboot_path, "-s", serial, "set_active", slot_clean], timeout=45)
        res["success"] = fastboot_result_ok(res)
        return res

    def _get_prop(self, serial: str, prop: str) -> str:
        res = self.run_cmd([self.adb_path, "-s", serial, "shell", "getprop", prop], timeout=5)
        return (res.get("stdout", "") or "").strip()

    def check_unlock_brand(self, serial: str) -> Dict[str, Any]:
        """Detects whether connected device is Xiaomi/Redmi/POCO (requires Mi Account Unlock) or standard Fastboot unlock."""
        devices = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devices, serial)
        if not dev:
            return {"success": False, "error": self._device_not_found_error(serial), "is_xiaomi": False}
        mode = dev["mode"]
        brand = ""
        product = ""
        market_name = ""

        if mode == "ADB":
            def _adb_gp(prop):
                r = self.run_cmd([self.adb_path, "-s", serial, "shell", "getprop", prop], timeout=5)
                return (r.get("stdout", "") or "").strip()
            brand = _adb_gp("ro.product.brand") or _adb_gp("ro.product.manufacturer")
            product = _adb_gp("ro.product.device")
            market_name = _adb_gp("ro.product.marketname") or _adb_gp("ro.product.model") or product
        else:
            product = (self._get_fastboot_var(serial, "product") or "").strip()
            market_name = product
            # Check if product is a known Xiaomi/Redmi/POCO codename or has Mi token
            if product.lower() in MODEL_TO_CODENAME.values() or product.lower() in ("rodin", "mondrian", "vermeer", "duchamp", "houji", "shennong", "aurora", "marble", "corot", "socrates", "garnet", "zircon", "ruby", "tapas", "topaz", "fuxi", "nuwa", "ishtar", "babylon", "peridot", "manet", "sheng"):
                brand = "Xiaomi"
            else:
                tok_res = self.run_cmd([self.fastboot_path, "-s", serial, "getvar", "token"], timeout=6)
                if "token:" in (tok_res.get("output", "") or "").lower():
                    brand = "Xiaomi"

        b_low = brand.lower()
        is_xiaomi = any(k in b_low for k in ("xiaomi", "redmi", "poco"))

        cached_uid = None
        session_file = os.path.join(os.path.expanduser("~"), ".migatesession", "unlockApi", "session.json")
        if os.path.exists(session_file):
            try:
                with open(session_file, "r", encoding="utf-8") as sf:
                    cached_uid = json.load(sf).get("userId")
            except Exception:
                pass

        return {
            "success": True,
            "is_xiaomi": is_xiaomi,
            "brand": brand or "Standard Android",
            "product": product,
            "market_name": market_name or product or serial,
            "mode": mode,
            "cached_uid": cached_uid
        }

    def mi_account_logout(self) -> Dict[str, Any]:
        session_file = os.path.join(os.path.expanduser("~"), ".migatesession", "unlockApi", "session.json")
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
            except Exception:
                pass
        return {"success": True}

    @device_action_locked
    def mi_unlock_workflow(self, serial: str, username: str = "", password: str = "", region: str = "India", login_method: str = "password", use_cached: bool = False, progress_cb=None) -> Dict[str, Any]:
        """Official Xiaomi/POCO/Redmi Bootloader Unlock via Mi Account login + server encryptData token."""
        def _cb(msg, pct=None):
            if progress_cb:
                try: progress_cb(msg, pct)
                except Exception: pass

        logs = ["Starting Xiaomi Mi Account Bootloader Unlock..."]
        try:
            from pathlib import Path
            import random
            from migate.config import SERVICELOGIN_URL, SERVICELOGINAUTH2_URL
            from migate.requester import session as mg_session, get as mg_get, post as mg_post
            from migate.service import get_service
            from migate.login.browser_qr import handle_browser_qr
            from miunlock.utils import _send as mi_send
        except Exception as e:
            return {"success": False, "error": f"MiUnlock engine import failed: {e}", "logs": logs}

        session_file = Path.home() / ".migatesession" / "unlockApi" / "session.json"
        pass_token = None

        if use_cached and session_file.exists():
            try:
                pass_token = json.loads(session_file.read_text(encoding="utf-8"))
                _cb(f"Using cached Mi Account session (UID: {pass_token.get('userId')})...", 15)
                logs.append(f"Loaded cached Mi Account UID: {pass_token.get('userId')}")
            except Exception:
                pass_token = None

        if not pass_token:
            auth_data = {"sid": "unlockApi", "checkSafeAddress": True, "_json": True}
            _cb("Connecting to Xiaomi Account Server (account.xiaomi.com)...", 10)
            try:
                resp = mg_get(SERVICELOGIN_URL, params=auth_data)
                rjson = json.loads(resp.text[11:])
                auth_data["serviceParam"] = rjson["serviceParam"]
                auth_data["qs"] = rjson["qs"]
                auth_data["callback"] = rjson["callback"]
                auth_data["_sign"] = rjson["_sign"]
            except Exception as e:
                return {"success": False, "error": f"Failed contacting Xiaomi login server: {e}", "logs": logs}

            if login_method == "browser_qr":
                _cb("Opening Xiaomi Official Browser / QR Login...", 20)
                logs.append("Waiting for user to sign in via Xiaomi Browser / QR...")
                try:
                    handle_browser_qr(auth_data, "1")
                except Exception as e:
                    return {"success": False, "error": f"Browser/QR login failed: {e}", "logs": logs}
            else:
                if not username.strip() or not password:
                    return {"success": False, "error": "Please enter Mi Account ID/Email/Phone and Password.", "logs": logs}
                _cb("Authenticating Mi Account credentials...", 20)
                auth_data["user"] = username.strip()
                auth_data["hash"] = hashlib.md5(password.encode()).hexdigest().upper()
                try:
                    r2 = mg_post(SERVICELOGINAUTH2_URL, data=auth_data)
                    res2 = json.loads(r2.text[11:])
                except Exception as e:
                    return {"success": False, "error": f"Mi Account login request failed: {e}", "logs": logs}

                if res2.get("captchaUrl") or res2.get("notificationUrl"):
                    mg_session.cookies.clear()
                    return {
                        "success": False,
                        "needs_browser_login": True,
                        "error": "Xiaomi security check (2FA / Captcha) triggered! Click 'Login via Xiaomi Browser / QR' button to sign in safely.",
                        "logs": logs
                    }
                if res2.get("code", -1) != 0 and "passToken" not in mg_session.cookies.get_dict():
                    mg_session.cookies.clear()
                    desc = res2.get("desc") or res2.get("description") or f"Login rejected (code {res2.get('code')})"
                    return {"success": False, "error": f"Mi Account Login Failed: {desc}", "logs": logs}

            cookies = mg_session.cookies.get_dict()
            required = {"deviceId", "passToken", "userId"}
            if not required.issubset(cookies.keys()):
                mg_session.cookies.clear()
                return {
                    "success": False,
                    "needs_browser_login": True,
                    "error": "Incomplete login session (2FA/Verification may be required). Try 'Login via Xiaomi Browser / QR'.",
                    "logs": logs
                }
            pass_token = {k: cookies[k] for k in required}
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text(json.dumps(pass_token), encoding="utf-8")
            mg_session.cookies.clear()
            logs.append(f"✅ Logged into Mi Account UID: {pass_token['userId']}")

        _cb("Fetching Xiaomi Unlock Service Token...", 35)
        service = get_service(pass_token, {"sid": "unlockApi", "checkSafeAddress": True})
        if not service:
            return {"success": False, "error": "Failed to authorize unlockApi service. Try logging out and signing in again.", "logs": logs}

        domain = {
            "India": "https://in-unlock.update.intl.miui.com",
            "Singapore": "https://unlock.update.intl.miui.com",
            "Global": "https://unlock.update.intl.miui.com",
            "Europe": "https://eu-unlock.update.intl.miui.com",
            "China": "https://unlock.update.miui.com",
            "Russia": "https://ru-unlock.update.intl.miui.com",
        }.get(region, "https://unlock.update.intl.miui.com")

        # Ensure device is in Fastboot mode
        devices = self.detect_devices()
        dev = next((d for d in devices if d["serial"] == serial), None)
        if not dev:
            err_msg = f"Exact target device [{serial}] is not connected. Refusing to use any other device."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}
        fb_serial = serial
        if dev["mode"] == "ADB":
            _cb("Rebooting device to Bootloader (Fastboot)...", 45)
            logs.append("Auto-rebooting device from ADB to Fastboot...")
            self.reboot(serial, "ADB", "bootloader")
            time.sleep(3)
            fb_found = False
            for _ in range(20):
                time.sleep(1.5)
                fb = next((d for d in self.detect_devices() if d["mode"] == "FASTBOOT" and d["serial"] == serial), None)
                if fb:
                    fb_serial = fb["serial"]
                    fb_found = True
                    break
            if not fb_found:
                err_msg = f"Exact target [{serial}] did not appear in FASTBOOT after reboot. Aborting Mi Unlock."
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "logs": logs}
        elif dev["mode"] != "FASTBOOT":
            err_msg = f"Device [{serial}] is in unsupported mode {dev['mode']}."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}

        _cb("Reading Fastboot product & hardware unlock token...", 55)
        s_cookies = service["cookies"]
        ssecurity = service["servicedata"]["ssecurity"]
        device_id = service["servicedata"]["deviceId"]

        # Both reads are strictly scoped to the exact requested fastboot serial.
        prod_res = self.run_cmd([self.fastboot_path, "-s", fb_serial, "getvar", "product"], timeout=8)
        m_prod = re.search(r"product:\s*([^\r\n]+)", prod_res.get("output", ""), re.I)
        product = self._clean_var(m_prod.group(1).strip()) if m_prod else ""
        if not product:
            err_msg = f"Could not read 'product' for exact fastboot serial {fb_serial}: {prod_res.get('output', '')}"
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}
        tok_res = self.run_cmd([self.fastboot_path, "-s", fb_serial, "oem", "get_token"], timeout=8)
        m_tok = re.search(r"token:\s*(\S+)", tok_res.get("output", ""), re.I)
        if not m_tok:
            tok_res2 = self.run_cmd([self.fastboot_path, "-s", fb_serial, "getvar", "token"], timeout=8)
            m_tok = re.search(r"token:\s*(\S+)", tok_res2.get("output", ""), re.I)
        device_token = m_tok.group(1).strip() if m_tok else ""
        if not device_token:
            err_msg = f"Could not read hardware unlock token for exact fastboot serial {fb_serial}. Refusing serial-less fallback."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}
        logs.append(f"Fastboot Product: {product} | Token retrieved for {fb_serial}.")

        # Nonce 1 -> clear check
        r1 = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=16))
        n1 = mi_send("/api/v2/nonce", {"r": r1}, domain, ssecurity, s_cookies)
        if "error" in n1 or n1.get("code") != 0:
            return {"success": False, "error": f"Xiaomi Nonce Error: {n1}", "logs": logs}

        clear = mi_send("/api/v2/unlock/device/clear", {"appId": "1", "data": {"product": product}, "nonce": n1["nonce"]}, domain, ssecurity, s_cookies)
        if "error" in clear or clear.get("code") != 0:
            return {"success": False, "error": f"Xiaomi Device Check Error: {clear.get('descEN') or clear}", "logs": logs}
        logs.append(f"Xiaomi Notice: {clear.get('notice', '')}")

        # Nonce 2 -> ahaUnlock
        _cb("Requesting signed unlock certificate from Xiaomi Server...", 75)
        r2 = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=16))
        n2 = mi_send("/api/v2/nonce", {"r": r2}, domain, ssecurity, s_cookies)
        if "error" in n2 or n2.get("code") != 0:
            return {"success": False, "error": f"Xiaomi Nonce2 Error: {n2}", "logs": logs}

        data = {
            "clientId": "2",
            "clientVersion": "7.6.727.43",
            "deviceInfo": {"boardVersion": "", "deviceName": "", "product": product, "socId": ""},
            "deviceToken": device_token,
            "language": "en",
            "operate": "unlock",
            "pcId": hashlib.md5(device_id.encode()).hexdigest(),
            "region": "",
            "uid": s_cookies.get("userId"),
        }
        u_res = mi_send("/api/v3/ahaUnlock", {"appId": "1", "data": data, "nonce": n2["nonce"]}, domain, ssecurity, s_cookies)
        if "error" in u_res:
            return {"success": False, "error": f"Unlock Server Error: {u_res['error']}", "logs": logs}
        if u_res.get("code") != 0:
            desc = u_res.get("descEN") or u_res.get("desc") or str(u_res)
            logs.append(f"❌ Xiaomi Server Rejected (code {u_res.get('code')}): {desc}")
            return {"success": False, "error": f"Xiaomi Unlock Rejected (Code {u_res.get('code')}): {desc}", "logs": logs}

        _cb("Staged signed token! Executing Fastboot Bootloader Unlock...", 90)
        enc_hex = u_res["encryptData"]
        with tempfile.NamedTemporaryFile(prefix="mi_unlock_", suffix=".bin", delete=False) as tmp_f:
            tmp_f.write(bytes.fromhex(enc_hex))
            tmp_token = Path(tmp_f.name)
        try:
            try:
                os.chmod(tmp_token, 0o600)
            except Exception:
                pass
            st_res = self.run_cmd([self.fastboot_path, "-s", fb_serial, "stage", str(tmp_token)], timeout=30)
            logs.append(st_res.get("output", ""))
            if not fastboot_result_ok(st_res):
                return {"success": False, "logs": logs, "error": f"Failed to stage Xiaomi unlock token: {st_res.get('output', 'stage failed')}"}
            ul_res = self.run_cmd([self.fastboot_path, "-s", fb_serial, "oem", "unlock"], timeout=45)
            logs.append(ul_res.get("output", ""))
            unlocked_now = (self._get_fastboot_var(fb_serial, "unlocked") or "").strip().lower()
            ok = fastboot_result_ok(ul_res) and unlocked_now in ("yes", "true", "1")
            _cb("🎉 Bootloader Unlocked Successfully!" if ok else "❌ Fastboot oem unlock failed", 100 if ok else 0)
            return {"success": ok, "logs": logs, "error": None if ok else ul_res.get("output", "Fastboot unlock did not verify as unlocked.")}
        finally:
            if tmp_token.exists():
                tmp_token.unlink(missing_ok=True)

    @device_action_locked
    def unlock_bootloader(self, serial: str) -> Dict[str, Any]:
        brand = self.check_unlock_brand(serial)
        if not brand.get("success"):
            return {"success": False, "output": brand.get("error", "Target device not found.")}
        if brand.get("is_xiaomi"):
            return {
                "success": False,
                "output": "🚫 Xiaomi/Redmi/POCO devices require the signed Mi Account token. Use the 'Mi Unlock' workflow instead; generic fastboot unlock is refused."
            }
        ready = self._ensure_fastboot_ready(serial)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error")}
        target = ready["serial"]
        res = self.run_cmd([self.fastboot_path, "-s", target, "flashing", "unlock"], timeout=60)
        if not fastboot_result_ok(res):
            return {"success": False, "output": f"Unlock failed: {res.get('output', '')}"}
        unlocked_now = (self._get_fastboot_var(target, "unlocked") or "").strip().lower()
        if unlocked_now not in ("yes", "true", "1"):
            return {"success": False, "output": f"Unlock command did not verify: unlocked={unlocked_now or 'unknown'}."}
        res["success"] = True
        return res

    @device_action_locked
    def lock_bootloader(self, serial: str) -> Dict[str, Any]:
        # Pre-lock safety guard: prevent instant hard-brick on rooted/modified/Samsung devices
        devs = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devs, serial)
        if dev and str(dev.get("mode", "")).upper() == "ADB":
            mfr = self._get_prop(serial, "ro.product.manufacturer").lower()
            if "samsung" in mfr:
                return {"success": False, "output": "Samsung devices use Download Mode (Odin), not Fastboot locking."}
            su_chk = self.run_cmd([self.adb_path, "-s", serial, "shell", "su -c id || su 0 id"], timeout=5)
            if "uid=0" in (su_chk.get("stdout", "") or ""):
                return {"success": False, "output": "🚫 [BrickShield] Root (uid=0) detected! Locking bootloader while rooted causes an instant hard-brick. Restore clean stock boot/init_boot first."}
        ready = self._ensure_fastboot_ready(serial)
        if not ready.get("success"):
            return {"success": False, "output": ready.get("error")}
        target = ready["serial"]
        fb_product = (self._get_fastboot_var(target, "product") or "").lower()
        if "samsung" in fb_product:
            return {"success": False, "output": "Samsung fastboot product detected. Use Download Mode (Odin), not Fastboot locking."}
        verified = (self._get_fastboot_var(target, "verified") or "").lower()
        if verified in ("orange", "yellow", "red"):
            return {"success": False, "output": f"🚫 [BrickShield] Fastboot reports modified verification state ('{verified}'). Restore clean stock firmware before locking."}
        unlocked = (self._get_fastboot_var(target, "unlocked") or "").lower()
        if unlocked in ("no", "false", "0"):
            return {"success": False, "output": "Bootloader is already locked."}
        res = self.run_cmd([self.fastboot_path, "-s", target, "flashing", "lock"], timeout=60)
        if not fastboot_result_ok(res):
            return {"success": False, "output": f"Lock failed; no fallback attempted: {res.get('output', '')}. Fix the reported error before retrying."}
        locked_now = (self._get_fastboot_var(target, "unlocked") or "").strip().lower()
        if locked_now not in ("no", "false", "0"):
            return {"success": False, "output": f"Lock command did not verify: unlocked={locked_now or 'unknown'}."}
        res["success"] = True
        return res

    @device_action_locked
    def adb_sideload(self, serial: str, file_path: str, progress_cb=None) -> Dict[str, Any]:
        """Standalone ADB sideload with the same verification standard as auto-flash."""
        def _emit(msg: str, pct=None):
            if progress_cb:
                try:
                    progress_cb(msg, pct)
                except Exception:
                    pass

        if not os.path.isfile(file_path):
            err = f"ZIP file not found: {file_path}"
            _emit(err, 0)
            return {"success": False, "error": err, "output": err, "code": -1}
        try:
            file_size = os.path.getsize(file_path)
        except OSError as e:
            err = f"Cannot read ZIP file: {e}"
            _emit(err, 0)
            return {"success": False, "error": err, "output": err, "code": -1}
        if file_size <= 0:
            err = "Selected ZIP is empty; refusing to sideload it."
            _emit(err, 0)
            return {"success": False, "error": err, "output": err, "code": -1}
        zip_ok, zip_err = verify_rom_archive(file_path)
        if not zip_ok:
            err = f"ZIP integrity check failed: {zip_err}"
            _emit(err, 0)
            return {"success": False, "error": err, "output": err, "code": -1}

        # ONLY the auto-flash cancel token applies here. ROM-download cancel
        # flags are a different operation and must never cancel a sideload.
        cancel_ev = getattr(self, "_auto_flash_cancel_event", None)
        if cancel_ev is not None and cancel_ev.is_set():
            err = "ADB sideload cancelled by user."
            _emit(err, 0)
            return {"success": False, "cancelled": True, "error": err, "output": err, "code": -1}

        # Exact serial must actually be in sideload mode. Never stream to a different device.
        def _adb_state() -> str:
            st = self.run_cmd([self.adb_path, "-s", serial, "get-state"], timeout=10)
            return (st.get("stdout") or st.get("output") or "").strip().lower()

        state = _adb_state()
        if state == "recovery":
            self.run_cmd([self.adb_path, "-s", serial, "reboot", "sideload"], timeout=10)
            for _ in range(25):
                time.sleep(1)
                state = _adb_state()
                if state == "sideload":
                    break
        if state != "sideload":
            err = self._device_not_found_error(serial, "ADB sideload") + f" Current state: {state or 'unknown'}."
            _emit(err, 0)
            return {"success": False, "error": err, "output": err, "code": -1}

        try:
            timeout_sec = max(300, int(os.environ.get("ROM_FLASHER_SIDELOAD_TIMEOUT", "900") or 900))
        except (TypeError, ValueError):
            timeout_sec = 900
        cmd = [self.adb_path, "-s", serial, "sideload", file_path]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = None
        reader_t = None
        out_lines: List[str] = []
        q: "queue.Queue[Optional[str]]" = queue.Queue()
        last_pct = -1
        cancelled = False
        timed_out = False
        rc = -1
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", creationflags=flags
            )
            self.active_flash_proc = proc

            def _reader():
                try:
                    assert proc.stdout is not None
                    for raw in iter(proc.stdout.readline, ''):
                        q.put(raw.rstrip('\r\n'))
                except Exception as e:
                    q.put(f"ADB output reader error: {e}")
                finally:
                    q.put(None)

            reader_t = threading.Thread(target=_reader, daemon=True)
            reader_t.start()

            def _drain():
                nonlocal last_pct
                saw_end = False
                while True:
                    try:
                        line = q.get_nowait()
                    except queue.Empty:
                        break
                    if line is None:
                        saw_end = True
                        continue
                    if not line.strip():
                        continue
                    out_lines.append(line)
                    m_pct = re.search(r"(\d+)%", line)
                    if m_pct:
                        pct = min(100, max(0, int(m_pct.group(1))))
                        if pct != last_pct:
                            last_pct = pct
                            _emit(line, pct)
                    else:
                        _emit(line, None)
                return saw_end

            started = time.time()
            last_heartbeat = -1
            eof = False
            while True:
                if _drain():
                    eof = True
                if cancel_ev is not None and cancel_ev.is_set():
                    cancelled = True
                    break
                if proc.poll() is not None and eof:
                    break
                elapsed = int(time.time() - started)
                if elapsed >= timeout_sec:
                    timed_out = True
                    break
                if elapsed - last_heartbeat >= 30:
                    last_heartbeat = elapsed
                    _emit(f"ADB sideload in progress ({elapsed}s / {timeout_sec}s)...", None)
                time.sleep(0.1)

            if reader_t is not None:
                reader_t.join(timeout=2)
            _drain()
            if cancelled or timed_out:
                if proc.poll() is None:
                    proc.kill()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass
            rc = proc.returncode if proc.poll() is not None else -1
            output = "\n".join(out_lines)
        except subprocess.TimeoutExpired as e:
            if proc is not None and proc.poll() is None:
                proc.kill()
            rc, output = -1, f"ADB sideload timed out: {e}"
        except Exception as e:
            rc, output = -1, f"ADB Sideload error: {e}"
        finally:
            self.active_flash_proc = None
            if proc is not None and proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

        low = output.lower()
        completion_phrases = (
            "install completed", "install successful", "install succeeded",
            "install from adb completed with status 0", "update package execution finished",
            "zip install ok",
        )
        explicit_completion = any(p in low for p in completion_phrases)
        xfer_values = [float(m.group(1)) for m in re.finditer(
            r"total\s+xfer:\s*([0-9]+(?:\.[0-9]+)?)", low)]
        xfer_ok = any(v >= 0.99 for v in xfer_values)

        tolerated = (
            r'^error:\s*device not found\b', r'^error:\s*closed\b',
            r'^error:\s*device offline\b', r'failed to verify .*trying alternate key',
            r'^connection closed\b', r'^device not found\b', r'\boffline\b',
        )
        hard_terms = (
            "install failed", "adb: failed", "signature verification failed",
            "footer is wrong", "failed to verify", "error:", "connection closed",
        )
        hard_lines = [
            ln for ln in out_lines
            if any(t in ln.lower() for t in hard_terms)
            and not any(re.search(p, ln.strip().lower()) for p in tolerated)
        ]

        if cancelled:
            err = "ADB sideload cancelled by user."
            _emit(err, 0)
            return {"success": False, "cancelled": True, "error": err, "output": output, "code": rc}
        if timed_out:
            err = f"ADB sideload timed out after {timeout_sec}s."
            _emit(err, 0)
            return {"success": False, "error": err, "output": output, "code": rc}
        if hard_lines:
            err = "Recovery reported an error: " + " | ".join(hard_lines[:4])
            if "signature verification failed" in low or "footer is wrong" in low:
                err += "\n⚠️ Stock Recovery rejected the ZIP signature. Flash a custom recovery (TWRP/OrangeFox/Lineage) first, then sideload."
            _emit(err, 0)
            return {"success": False, "error": err, "output": output, "code": rc}
        if not explicit_completion:
            # A completed byte transfer is NOT proof that recovery applied the
            # OTA. Never report standalone sideload as successful on xfer alone.
            err = ("Sideload transferred the ZIP but recovery never confirmed installation. "
                   "Verify the installed build on the device; refusing to claim success from transfer bytes alone.")
            if rc == 0 and xfer_ok:
                err += " (Total xfer >= 0.99 was seen.)"
            _emit(err, 0)
            return {"success": False, "error": err, "output": output, "code": rc, "needs_verification": True}
        _emit("Sideload completed successfully.", 100)
        return {"success": True, "output": output, "error": "", "code": rc, "cancelled": False}

    # 📶 WIRELESS ADB (WI-FI PAIR, CONNECT & USB-TO-WIFI)
    def wireless_adb_pair(self, ip_port: str, pairing_code: str) -> Dict[str, Any]:
        ip_port = (ip_port or "").strip()
        code = (pairing_code or "").strip()
        if not ip_port or not code:
            return {"success": False, "output": "Enter both IP:Port and 6-digit Pairing Code."}
        return self.run_cmd([self.adb_path, "pair", ip_port, code], timeout=20)

    def _save_wireless_history(self, ip_port: str):
        hist_file = os.path.join(os.path.expanduser("~"), ".rom_flasher_wireless_history.json")
        hist = []
        if os.path.exists(hist_file):
            try:
                with open(hist_file, "r", encoding="utf-8") as f:
                    hist = json.load(f)
            except Exception:
                hist = []
        if ip_port in hist:
            hist.remove(ip_port)
        hist.insert(0, ip_port)
        try:
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(hist[:6], f)
        except Exception:
            pass

    def wireless_adb_history(self) -> Dict[str, Any]:
        hist_file = os.path.join(os.path.expanduser("~"), ".rom_flasher_wireless_history.json")
        if os.path.exists(hist_file):
            try:
                with open(hist_file, "r", encoding="utf-8") as f:
                    return {"success": True, "history": json.load(f)}
            except Exception:
                pass
        return {"success": True, "history": []}

    def wireless_adb_qr_generate(self) -> Dict[str, Any]:
        """Generates Android 11+ Wireless Debugging QR code (WIFI:T:ADB;S:<svc>;P:<pwd>;;)."""
        try:
            import random, string, base64, io
            import qrcode
            svc = "STUDIO-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            pwd = "".join(random.choices(string.digits, k=6))
            payload = f"WIFI:T:ADB;S:{svc};P:{pwd};;"
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return {"success": True, "service": svc, "password": pwd, "qr_data_uri": f"data:image/png;base64,{b64}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _read_dns_name(self, buf: bytes, off: int):
        labels = []
        jumped = False
        orig_off = off
        for _ in range(64):
            if off >= len(buf):
                break
            ln = buf[off]
            if ln == 0:
                off += 1
                break
            if (ln & 0xC0) == 0xC0:
                if off + 1 >= len(buf):
                    break
                ptr = ((ln & 0x3F) << 8) | buf[off + 1]
                if not jumped:
                    orig_off = off + 2
                off = ptr
                jumped = True
                continue
            off += 1
            labels.append(buf[off:off + ln].decode("utf-8", errors="replace"))
            off += ln
        return ".".join(labels), (orig_off if jumped else off)

    def _mdns_scan(self, timeout_s: float = 1.8) -> Dict[str, Any]:
        """Actively queries UDP 224.0.0.251:5353 across ALL local IPv4 interfaces for _adb-tls-connect, _adb-tls-pairing, and _adb._tcp."""
        import socket, struct
        connect_list = []
        pairing_list = []
        txt_map = {}
        srv_records = []

        try:
            local_ips = list({ai[4][0] for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
        except Exception:
            local_ips = []

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", 5353))
            joined = False
            for lip in local_ips:
                try:
                    mreq = struct.pack("4s4s", socket.inet_aton("224.0.0.251"), socket.inet_aton(lip))
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                    joined = True
                except Exception:
                    pass
            if not joined:
                mreq = struct.pack("4sl", socket.inet_aton("224.0.0.251"), socket.INADDR_ANY)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            sock.settimeout(0.2)
            svcs = (
                b"\x10_adb-tls-connect\x04_tcp\x05local\x00",
                b"\x10_adb-tls-pairing\x04_tcp\x05local\x00",
                b"\x04_adb\x04_tcp\x05local\x00",
            )
            for lip in (local_ips or [None]):
                try:
                    if lip:
                        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(lip))
                    for svc in svcs:
                        q = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + svc + b"\x00\x0c\x00\x01"
                        sock.sendto(q, ("224.0.0.251", 5353))
                except Exception:
                    pass

            t0 = time.time()
            while time.time() - t0 < timeout_s:
                try:
                    buf, addr = sock.recvfrom(4096)
                    if len(buf) < 12:
                        continue
                    _, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", buf[:12])
                    if not (flags & 0x8000):
                        continue
                    off = 12
                    for _ in range(qd):
                        _, off = self._read_dns_name(buf, off)
                        off += 4
                    for _ in range(an + ns + ar):
                        if off >= len(buf):
                            break
                        name, off = self._read_dns_name(buf, off)
                        if off + 10 > len(buf):
                            break
                        rtype, _, _, rdlen = struct.unpack(">HHIH", buf[off:off + 10])
                        off += 10
                        rdata = buf[off:off + rdlen]
                        off += rdlen
                        if rtype == 33 and len(rdata) >= 6:
                            port = struct.unpack(">H", rdata[4:6])[0]
                            srv_records.append((name, addr[0], port))
                        elif rtype == 16:
                            i, kv = 0, {}
                            while i < len(rdata):
                                l = rdata[i]
                                i += 1
                                entry = rdata[i:i + l].decode("utf-8", errors="replace")
                                i += l
                                if "=" in entry:
                                    k, v = entry.split("=", 1)
                                    kv[k] = v
                            txt_map[name] = kv
                except socket.timeout:
                    pass
            sock.close()
        except Exception:
            pass

        seen = set()
        for name, ip, port in srv_records:
            ip_port = f"{ip}:{port}"
            if ip_port in seen:
                continue
            seen.add(ip_port)
            meta = txt_map.get(name, {})
            label = meta.get("given_name") or meta.get("name") or name.split(".")[0]
            serial_id = meta.get("serial", "")
            if "_adb-tls-pairing._tcp" in name:
                pairing_list.append({"name": label, "full_name": name, "ip_port": ip_port, "serial": serial_id})
            elif "_adb-tls-connect._tcp" in name or "_adb._tcp" in name:
                kind = "TLS Wi-Fi" if "_adb-tls-connect" in name else "TCP/IP"
                connect_list.append({"name": label, "ip_port": ip_port, "serial": serial_id, "kind": kind})

        return {"connect": connect_list, "pairing": pairing_list}

    def wireless_adb_discover(self) -> Dict[str, Any]:
        """Discovers all nearby Wireless ADB devices with marketing names via direct UDP 5353 mDNS + adb mdns services."""
        scan = self._mdns_scan(timeout_s=1.8)
        devices = list(scan["connect"])
        seen = {d["ip_port"] for d in devices}

        res = self.run_cmd([self.adb_path, "mdns", "services"], timeout=4)
        for line in (res.get("stdout", "") or "").splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+:\d+)", line)
            if not m:
                continue
            addr = m.group(1)
            if addr in seen:
                continue
            if "_adb-tls-connect._tcp" in line or "_adb._tcp" in line:
                seen.add(addr)
                name = line.split()[0] if line.split() else addr
                kind = "TLS Wi-Fi" if "_adb-tls-connect" in line else "TCP/IP"
                devices.append({"name": name, "ip_port": addr, "serial": "", "kind": kind})
        return {"success": True, "devices": devices, "pairing_ready": scan["pairing"]}

    def wireless_adb_qr_poll_and_pair(self, service: str, password: str) -> Dict[str, Any]:
        """Uses direct UDP 5353 mDNS + adb mdns services to catch pairing port, pair & connect."""
        scan = self._mdns_scan(timeout_s=1.5)
        pair_addr = None
        conn_addr = scan["connect"][0]["ip_port"] if scan["connect"] else None

        for p_item in scan["pairing"]:
            if not pair_addr or (service and service in p_item.get("full_name", "")):
                pair_addr = p_item["ip_port"]

        if not pair_addr:
            res = self.run_cmd([self.adb_path, "mdns", "services"], timeout=4)
            for line in (res.get("stdout", "") or "").splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+:\d+)", line)
                if not m:
                    continue
                addr = m.group(1)
                if "_adb-tls-pairing._tcp" in line:
                    if not pair_addr or (service and service in line):
                        pair_addr = addr
                elif "_adb-tls-connect._tcp" in line and not conn_addr:
                    conn_addr = addr

        if pair_addr:
            p_res = self.wireless_adb_pair(pair_addr, password)
            p_out = (p_res.get("output", "") or "").lower()
            if p_res.get("success") or "successfully paired" in p_out:
                pair_ip = pair_addr.split(":")[0]
                matched_conn = next((c["ip_port"] for c in scan["connect"] if c["ip_port"].startswith(f"{pair_ip}:")), None)
                for _ in range(5):
                    if matched_conn:
                        break
                    s2 = self._mdns_scan(timeout_s=0.7)
                    matched_conn = next((c["ip_port"] for c in s2["connect"] if c["ip_port"].startswith(f"{pair_ip}:")), None)
                if not matched_conn:
                    return {
                        "success": False,
                        "paired": True,
                        "error": f"Paired with {pair_addr} but no matching connection endpoint for IP {pair_ip} was found. Refusing to connect to a different device.",
                        "output": f"Paired with {pair_addr}; waiting for matching connect service."
                    }
                c_res = self.wireless_adb_connect(matched_conn)
                c_res["paired"] = True
                c_res["ip"] = matched_conn
                return c_res
            return p_res

        return {"success": False, "waiting": True, "conn_addr": conn_addr, "output": "Waiting for QR scan..."}

    def wireless_adb_connect(self, ip_port: str) -> Dict[str, Any]:
        ip_port = (ip_port or "").strip()
        if not ip_port:
            return {"success": False, "output": "Enter device IP:Port (e.g. 192.168.1.50:5555)."}
        res = self.run_cmd([self.adb_path, "connect", ip_port], timeout=10)
        out = (res.get("output", "") or "").lower()
        res["success"] = ("connected to" in out or "already connected" in out)
        if res["success"]:
            self._save_wireless_history(ip_port)
        else:
            res["needs_pairing"] = True
            if not res.get("output"):
                res["output"] = f"Failed to connect to {ip_port}."
            res["output"] += " (If this is a new PC, pair the device first using 6-digit Pairing Code below.)"
        return res

    def wireless_adb_tcpip(self, serial: str, port: int = 5555) -> Dict[str, Any]:
        if not serial:
            return {"success": False, "output": "Connect device via USB in ADB mode first."}
        ip_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "ip -f inet addr show wlan0 | grep inet"], timeout=8)
        m_ip = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip_res.get("stdout", "") or "")
        ip_addr = m_ip.group(1) if m_ip else ""
        t_res = self.run_cmd([self.adb_path, "-s", serial, "tcpip", str(port)], timeout=10)
        if not t_res.get("success"):
            return t_res
        if ip_addr:
            time.sleep(1.5)
            c_res = self.wireless_adb_connect(f"{ip_addr}:{port}")
            c_res["ip"] = f"{ip_addr}:{port}"
            return c_res
        return {"success": True, "output": f"TCP/IP port {port} enabled. Connect using your phone's Wi-Fi IP:{port}."}

    def wireless_adb_disconnect(self, ip_port: str = "") -> Dict[str, Any]:
        cmd = [self.adb_path, "disconnect"]
        if ip_port and ip_port.strip():
            cmd.append(ip_port.strip())
        return self.run_cmd(cmd, timeout=10)


    # 📦 PAYLOAD DUMPER STUDIO ENGINE
    def inspect_payload_package(self, file_path: str) -> Dict[str, Any]:
        """Inspect payload.bin / Recovery ZIP with validated headers and canonical keys."""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}
        if is_split_archive_part(str(file_path)):
            return {"success": False, "error": "Split archive detected. Join the .001/.002 parts before using Payload Dumper."}

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        def _from_stream(pf, size=None):
            dam, _block, _base, version = parse_payload_header(pf, size)
            is_delta = payload_is_delta(dam)
            seen = set()
            partitions = []
            for p in dam.partitions:
                key = safe_partition_key(p.partition_name)
                if key in seen:
                    continue
                seen.add(key)
                size_p = int(getattr(getattr(p, "new_partition_info", None), "size", 0) or 0)
                partitions.append({
                    "key": key,
                    "name": key,
                    "source_name": p.partition_name,
                    "size": size_p,
                    "size_formatted": format_bytes(size_p),
                })
            warning = ""
            if is_delta:
                warning = "Incremental/delta payload detected. Only full OTA payloads can be dumped safely."
            return {
                "success": True,
                "filename": filename,
                "path": file_path,
                "size_bytes": file_size,
                "size_formatted": format_bytes(file_size),
                "payload_entry": "",
                "format_version": version,
                "is_delta": is_delta,
                "minor_version": int(getattr(dam, "minor_version", 0) or 0),
                "partial_update": bool(getattr(dam, "partial_update", False)),
                "warning": warning,
                "partitions": partitions,
                "total_partitions": len(partitions),
            }

        try:
            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, "r") as zf:
                    entry = choose_payload_entry(zf)
                    if not entry:
                        return {"success": False,
                                "error": "payload.bin not found inside ZIP archive. (Use an AOSP / Recovery / OTA ROM ZIP.)"}
                    with zf.open(entry) as pf:
                        res = _from_stream(pf, zf.getinfo(entry).file_size)
                    res["payload_entry"] = entry
                    return res
            with open(file_path, "rb") as pf:
                return _from_stream(pf, file_size)
        except Exception as e:
            return {"success": False, "error": f"Failed reading payload: {e}",
                    "code": getattr(e, "code", None)}

    def cancel_payload_dump(self) -> Dict[str, Any]:
        """Request cancellation of the active payload extraction (checked between blocks)."""
        ev = getattr(self, "_payload_cancel_event", None)
        if ev is not None:
            ev.set()
            return {"success": True, "output": "Payload extraction cancellation requested."}
        return {"success": True, "output": "No payload extraction is currently running."}

    def extract_payload_partitions(self, file_path: str, partition_names: List[str], progress_cb=None, out_dir=None) -> Dict[str, Any]:
        r"""Extract selected partitions from payload.bin or ZIP into ROM_Flasher_Storage\Payload_Extracted."""
        logs = []
        def _log(msg, pct=None):
            logs.append(msg)
            if progress_cb:
                try:
                    progress_cb(msg, pct)
                except Exception:
                    pass

        def _fail(err, code=None, cancelled=False):
            res = {"success": False, "error": str(err), "logs": logs, "cancelled": cancelled}
            if code:
                res["code"] = code
            return res

        if not os.path.exists(file_path):
            return _fail(f"File not found: {file_path}")
        if is_split_archive_part(str(file_path)):
            return _fail("Split archive detected. Join the .001/.002 parts before using Payload Dumper.")

        expected = {safe_partition_key(p) for p in partition_names if str(p or "").strip()}
        if not expected:
            return _fail("No partitions requested")

        try:
            available = set(list_payload_partition_names(file_path))
        except Exception as e:
            return _fail(f"Cannot read payload manifest: {e}", getattr(e, "code", None))
        unknown = sorted(expected - available)
        if unknown:
            return _fail(f"Partition(s) not present in this payload: {', '.join(unknown)}", "UNKNOWN_PARTITION")

        identity = source_identity(file_path, strong=True)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        id_hash = hashlib.sha256(identity.encode("utf-8", "replace")).hexdigest()[:12]
        clean_name = re.sub(r'[^A-Za-z0-9_.-]', '_', base_name)
        if not out_dir:
            storage = storage_path_for(file_path, "Payload_Extracted")
            if not storage.get("success"):
                return _fail(storage.get("error", "Cannot prepare storage"), storage.get("code"))
            out_dir = os.path.join(storage["path"], f"{clean_name}_{id_hash}")
        os.makedirs(out_dir, exist_ok=True)
        marker = out_dir + ".complete"

        def _file_hash(fp: str) -> str:
            h = hashlib.sha256()
            with open(fp, "rb") as fh:
                for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()

        def _marker_files():
            try:
                with open(marker, "r", encoding="utf-8") as mf:
                    data = json.load(mf)
                if isinstance(data, dict) and data.get("identity") == identity:
                    return data.get("files") or {}
            except Exception:
                pass
            return None

        known = _marker_files()
        if known is not None:
            cached = []
            valid = True
            for part in sorted(expected):
                fp = os.path.join(out_dir, f"{part}.img")
                info = known.get(part) or {}
                try:
                    if not os.path.isfile(fp) or int(info.get("size", 0)) <= 0:
                        valid = False
                        break
                    size = os.path.getsize(fp)
                    if size != int(info.get("size", 0)) or _file_hash(fp) != str(info.get("sha256", "")):
                        valid = False
                        break
                    cached.append({"name": part, "path": fp, "size": format_bytes(size), "sha256": info.get("sha256", "")})
                except Exception:
                    valid = False
                    break
            if valid and len(cached) == len(expected):
                _log(f"Using verified cached payload extraction ({len(cached)} partition(s)).", 100)
                return {"success": True, "output_dir": out_dir, "extracted_files": cached,
                        "cached": True, "logs": logs}

        # Clear stale generated images for the requested partitions before extracting.
        for part in expected:
            stale = os.path.join(out_dir, f"{part}.img")
            if os.path.isfile(stale):
                try:
                    os.remove(stale)
                except Exception:
                    pass
        try:
            os.remove(marker)
        except Exception:
            pass

        cancel_event = threading.Event()
        self._payload_cancel_event = cancel_event
        _log(f"Preparing to extract {len(expected)} partition(s) to: {out_dir}", 5)
        try:
            _log(f"Extracting images: {', '.join(sorted(expected))}...", 30)
            details: List[Dict[str, Any]] = []
            extract_payload_images(file_path, out_dir, sorted(expected), progress_cb=_log,
                                   cancel_event=cancel_event, details_out=details)
            extracted_files = [{
                "name": d["key"], "path": d["path"], "size": format_bytes(d["size"]),
                "sha256": d["sha256"],
            } for d in details]
            if len(extracted_files) != len(expected):
                missing = sorted(expected - {f["name"] for f in extracted_files})
                raise ValueError(f"Payload extraction missing requested partition(s): {', '.join(missing)}")
            for info in extracted_files:
                _log(f"Extracted: {info['name']}.img ({info['size']})", 90)
            try:
                with open(marker, "w", encoding="utf-8") as mf:
                    json.dump({"identity": identity,
                               "files": {f["name"]: {"size": os.path.getsize(f["path"]),
                                                     "sha256": f["sha256"]}
                                         for f in extracted_files}}, mf)
            except Exception as e:
                _log(f"Cache marker could not be written (extraction still valid): {e}", None)
            _log(f"Extraction completed! {len(extracted_files)} partition image(s) ready in {out_dir}", 100)
            return {"success": True, "output_dir": out_dir, "extracted_files": extracted_files, "logs": logs}
        except Exception as e:
            cancelled = cancel_event.is_set() or "cancelled" in str(e).lower()
            _log(f"Payload extraction {'cancelled' if cancelled else 'error'}: {e}", 0)
            return _fail(e, getattr(e, "code", None), cancelled=cancelled)
        finally:
            self._payload_cancel_event = None

    def check_for_updates(self) -> Dict[str, Any]:
        r"""Checks the official GitHub Releases API for the latest version of ROM Flasher Tool."""
        try:
            req = urllib.request.Request(
                GITHUB_LATEST_RELEASE_API,
                headers={"User-Agent": "ROM-Flasher-Tool-PC"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            latest_tag = data.get("tag_name", "").strip()
            release_name = data.get("name", latest_tag)
            release_body = data.get("body", "No changelog provided.")
            published_at = data.get("published_at", "")
            html_url = data.get("html_url", "")

            # Identify executable asset
            assets = data.get("assets", [])
            download_url = None
            asset_name = None
            asset_size = 0
            asset_digest = None

            for a in assets:
                aname = a.get("name", "")
                if aname.lower().endswith(".exe"):
                    download_url = a.get("browser_download_url")
                    asset_name = aname
                    asset_size = a.get("size", 0)
                    asset_digest = a.get("digest")
                    break

            if not download_url and assets:
                download_url = assets[0].get("browser_download_url")
                asset_name = assets[0].get("name")
                asset_size = assets[0].get("size", 0)
                asset_digest = assets[0].get("digest")

            self._verified_update = {
                "url": download_url,
                "name": asset_name,
                "size": asset_size,
                "digest": asset_digest,
                "tag": latest_tag
            } if download_url else None

            latest_tuple = parse_semver(latest_tag)
            current_tuple = parse_semver(APP_VERSION)
            has_update = latest_tuple > current_tuple

            return {
                "success": True,
                "has_update": has_update,
                "current_version": APP_VERSION,
                "latest_version": latest_tag,
                "release_name": release_name,
                "release_body": release_body,
                "published_at": published_at,
                "download_url": download_url,
                "asset_name": asset_name,
                "asset_size": asset_size,
                "asset_size_fmt": format_bytes(asset_size) if asset_size else "Unknown",
                "html_url": html_url
            }
        except Exception as e:
            return {
                "success": False,
                "has_update": False,
                "current_version": APP_VERSION,
                "error": str(e)
            }

    def apply_update(self, download_url=None, progress_cb=None) -> Dict[str, Any]:
        r"""
        Downloads the verified GitHub release asset and replaces the actually running executable.
        The caller-supplied URL is intentionally ignored; only check_for_updates() is trusted.
        """
        def _notify(pct, msg):
            if progress_cb:
                try: progress_cb(pct, msg)
                except: pass

        upd = self._verified_update
        if not upd or not upd.get("url"):
            return {"success": False, "error": "No verified update selected. Run 'Check for updates' first."}

        url = upd["url"]
        parsed = urllib.parse.urlparse(url)
        allowed_hosts = {"github.com", "objects.githubusercontent.com", "githubusercontent.com", "api.github.com"}
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts:
            return {"success": False, "error": f"Refusing update download from untrusted URL: {url}"}
        expected_size = int(upd.get("size") or 0)
        expected_digest = upd.get("digest")

        # 1. Determine the actually running executable (never a guessed fixed path).
        if getattr(sys, 'frozen', False):
            target_exe = sys.executable
        else:
            argv0 = sys.argv[0] if sys.argv else ""
            target_exe = argv0 if argv0 and argv0.lower().endswith(".exe") and os.path.exists(argv0) else ""
        if not target_exe or not os.path.isfile(target_exe) or not os.path.basename(target_exe).lower().endswith(".exe"):
            return {"success": False, "error": "Cannot determine the running .exe update target. Run the packaged executable."}

        target_exe = os.path.abspath(target_exe)
        exe_dir = os.path.dirname(target_exe)
        download_temp = os.path.join(exe_dir, f"{os.path.basename(target_exe)}.download")

        _notify(5, "Connecting to GitHub Releases CDN...")

        try:
            # Clean up any leftover previous download
            if os.path.exists(download_temp):
                try: os.remove(download_temp)
                except: pass

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ROM-Flasher-Tool-PC"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_bytes_header = resp.headers.get("Content-Length")
                total_bytes = int(total_bytes_header) if total_bytes_header and total_bytes_header.isdigit() else 0

                downloaded_bytes = 0
                chunk_size = 64 * 1024  # 64KB chunks
                start_time = time.time()
                last_notify_time = 0

                with open(download_temp, "wb") as f_out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded_bytes += len(chunk)

                        now = time.time()
                        if now - last_notify_time >= 0.15 or (total_bytes and downloaded_bytes == total_bytes):
                            last_notify_time = now
                            elapsed = max(0.001, now - start_time)
                            speed_mb = (downloaded_bytes / (1024 * 1024)) / elapsed
                            dl_mb = downloaded_bytes / (1024 * 1024)

                            if total_bytes > 0:
                                pct = min(98, int((downloaded_bytes / total_bytes) * 100))
                                tot_mb = total_bytes / (1024 * 1024)
                                msg = f"Downloading update: {pct}% ({dl_mb:.1f} MB / {tot_mb:.1f} MB at {speed_mb:.1f} MB/s)..."
                            else:
                                pct = 50
                                msg = f"Downloading update: {dl_mb:.1f} MB transferred ({speed_mb:.1f} MB/s)..."
                            _notify(pct, msg)

            _notify(98, "Verifying downloaded package integrity...")

            # 2. Package verification: exact size, optional GitHub digest, real PE headers.
            if not os.path.exists(download_temp):
                raise RuntimeError("Downloaded package is missing.")
            actual_size = os.path.getsize(download_temp)
            if actual_size <= 0:
                raise RuntimeError("Downloaded package is empty.")
            if expected_size > 0 and actual_size != expected_size:
                raise RuntimeError(f"Update size mismatch: downloaded {actual_size} bytes, expected {expected_size} bytes.")
            if downloaded_bytes != actual_size:
                raise RuntimeError("Downloaded byte count mismatch; refusing to install a partial update.")

            if expected_digest:
                digest_str = str(expected_digest).strip()
                if ":" in digest_str:
                    algo, want_hex = digest_str.split(":", 1)
                else:
                    algo, want_hex = "sha256", digest_str
                algo = algo.lower().strip()
                if algo not in ("sha256", "sha1", "md5"):
                    raise RuntimeError(f"Unsupported update digest algorithm: {algo}")
                h = hashlib.new(algo)
                with open(download_temp, "rb") as df:
                    for block in iter(lambda: df.read(1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest().lower() != want_hex.strip().lower():
                    raise RuntimeError("Update digest verification failed.")

            with open(download_temp, "rb") as check_f:
                header = check_f.read(64)
                if len(header) < 64 or header[:2] != b"MZ":
                    raise RuntimeError("Downloaded package is not a Windows executable (missing MZ).")
                pe_offset = struct.unpack("<I", header[0x3C:0x40])[0]
                if pe_offset < 64 or pe_offset > actual_size - 24:
                    raise RuntimeError("Downloaded package has an invalid PE header offset.")
                check_f.seek(pe_offset)
                if check_f.read(4) != b"PE\x00\x00":
                    raise RuntimeError("Downloaded package is not a valid Windows PE binary.")

            _notify(99, "Preparing detached in-place installer...")

            # 3. Create updater batch script in %TEMP%
            parent_pid = os.getpid()
            bat_path = os.path.join(tempfile.gettempdir(), f"rom_flasher_updater_{int(time.time())}.bat")
            bat_script = f"""@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title ROM Flasher Tool - Applying In-Place Update...

echo =======================================================
echo     ROM FLASHER TOOL - 1-CLICK IN-PLACE AUTO UPDATER
echo =======================================================
echo [1/3] Waiting for active ROM Flasher Tool (PID: {parent_pid}) to terminate...
timeout /t 1 /nobreak >nul
taskkill /F /PID {parent_pid} >nul 2>&1
timeout /t 1 /nobreak >nul

echo [2/3] Replacing executable:
echo Target: "{target_exe}"
set RETRY_COUNT=0
:REPLACE_RETRY
move /y "{download_temp}" "{target_exe}" >nul 2>&1
if exist "{download_temp}" (
    set /a RETRY_COUNT+=1
    if !RETRY_COUNT! leq 20 (
        timeout /t 1 /nobreak >nul
        goto REPLACE_RETRY
    )
)

if exist "{download_temp}" (
    echo [ERROR] Replacement failed after 20 retries. Update NOT applied.
    exit /b 1
)

echo [3/3] Relaunching updated ROM Flasher Tool...
set _MEIPASS2=
start "" "{target_exe}"

:: Self-destruct updater script
(goto) 2>nul & del "%~f0"
"""
            with open(bat_path, "w", encoding="utf-8") as bat_file:
                bat_file.write(bat_script)

            _notify(100, "Update installed! Restarting ROM Flasher Tool now...")

            # 4. Launch detached batch process and exit
            def _trigger_restart():
                time.sleep(0.8)
                try:
                    subprocess.Popen(
                        ["cmd.exe", "/c", bat_path],
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                        close_fds=True,
                        shell=True
                    )
                except Exception as ex:
                    print(f"Updater Popen error: {ex}")
                time.sleep(0.3)
                os._exit(0)

            threading.Thread(target=_trigger_restart, daemon=True).start()

            return {
                "success": True,
                "message": "Update downloaded successfully! Restarting application..."
            }

        except Exception as e:
            if os.path.exists(download_temp):
                try: os.remove(download_temp)
                except: pass
            _notify(0, f"Update failed: {str(e)}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 🛡️ FEATURE 1: 1-CLICK EFS / IMEI & BASEBAND BACKUP & RESTORE ENGINE
    # =========================================================================
    def _detect_device_rom_info(self, serial: str) -> Dict[str, str]:
        """Detects device marketing name, codename, Android version, and exact ROM name/type (HyperOS, AOSP, Port, etc.)."""
        props_cmd = (
            "for k in "
            "ro.product.marketname ro.product.vendor.marketname ro.product.model ro.product.device "
            "ro.vendor.product.device ro.build.version.release ro.mi.os.version.name ro.miui.ui.version.name "
            "ro.build.version.incremental ro.build.display.id ro.build.flavor ro.build.user ro.build.host "
            "ro.infinity.version ro.crdroid.version ro.evolution.version ro.lineage.version "
            "ro.pixelos.version ro.derpfest.version ro.matrixx.version ro.rising.version "
            "ro.oplus.version.base ro.build.version.opporom ro.board.platform ro.hardware; "
            "do echo \"$k=$(getprop $k)\"; done"
        )
        res = self.run_cmd([self.adb_path, "-s", serial, "shell", props_cmd], timeout=10)
        p = {}
        for line in (res.get("stdout", "") or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                p[k.strip()] = v.strip()

        codename = p.get("ro.product.device") or "unknown"
        model = p.get("ro.product.model") or codename
        market_name = p.get("ro.product.marketname") or p.get("ro.product.vendor.marketname") or model
        android_ver = p.get("ro.build.version.release") or "Unknown"
        mi_os = p.get("ro.mi.os.version.name") or ""
        miui_ui = p.get("ro.miui.ui.version.name") or ""
        inc = p.get("ro.build.version.incremental") or ""
        disp = p.get("ro.build.display.id") or ""
        flavor = p.get("ro.build.flavor") or ""
        b_user = p.get("ro.build.user") or ""
        b_host = p.get("ro.build.host") or ""
        vendor_dev = p.get("ro.vendor.product.device") or ""
        chipset = (p.get("ro.board.platform") or p.get("ro.hardware") or "").lower()

        blob = f"{disp} {flavor} {inc} {b_user} {b_host}".lower()
        is_port = ("port" in blob) or (vendor_dev and codename != "unknown" and vendor_dev.lower() != codename.lower())

        rom_name = "Stock ROM"
        rom_tag = "Stock_ROM"
        if p.get("ro.infinity.version") or "infinity" in blob:
            rom_name = "Infinity-X (AOSP)"
            rom_tag = "InfinityX_AOSP"
        elif p.get("ro.crdroid.version") or "crdroid" in blob:
            rom_name = "crDroid (AOSP)"
            rom_tag = "crDroid_AOSP"
        elif p.get("ro.evolution.version") or "evolution" in blob:
            rom_name = "Evolution X (AOSP)"
            rom_tag = "EvolutionX_AOSP"
        elif p.get("ro.pixelos.version") or "pixelos" in blob:
            rom_name = "PixelOS (AOSP)"
            rom_tag = "PixelOS_AOSP"
        elif p.get("ro.derpfest.version") or "derpfest" in blob:
            rom_name = "DerpFest (AOSP)"
            rom_tag = "DerpFest_AOSP"
        elif p.get("ro.matrixx.version") or "matrixx" in blob:
            rom_name = "Project Matrixx (AOSP)"
            rom_tag = "Matrixx_AOSP"
        elif p.get("ro.rising.version") or "rising" in blob:
            rom_name = "RisingOS (AOSP)"
            rom_tag = "RisingOS_AOSP"
        elif p.get("ro.lineage.version") or "lineage" in blob:
            rom_name = "LineageOS (AOSP)"
            rom_tag = "LineageOS_AOSP"
        elif p.get("ro.oplus.version.base") or p.get("ro.build.version.opporom") or "coloros" in blob:
            rom_name = "ColorOS Port" if is_port else "ColorOS"
            rom_tag = "ColorOS_Port" if is_port else "ColorOS"
        elif "oxygen" in blob:
            rom_name = "OxygenOS Port" if is_port else "OxygenOS"
            rom_tag = "OxygenOS_Port" if is_port else "OxygenOS"
        elif "oneui" in blob:
            rom_name = "OneUI Port" if is_port else "OneUI"
            rom_tag = "OneUI_Port" if is_port else "OneUI"
        elif mi_os or re.match(r"^OS\d+\.", inc):
            m_os = re.search(r"OS(\d+)", mi_os or inc)
            os_num = m_os.group(1) if m_os else ""
            rom_name = f"HyperOS {os_num}".strip() + (" Port" if is_port else "")
            rom_tag = f"HyperOS_{os_num}".strip("_") + ("_Port" if is_port else "")
        elif miui_ui or re.match(r"^V\d+\.", inc):
            m_miui = re.search(r"V(\d+)", inc)
            v_num = m_miui.group(1) if m_miui else miui_ui
            rom_name = f"MIUI {v_num}".strip() + (" Port" if is_port else "")
            rom_tag = f"MIUI_{v_num}".strip("_") + ("_Port" if is_port else "")
        elif "aosp" in blob or "pixel" in blob:
            rom_name = "AOSP Custom"
            rom_tag = "AOSP_Custom"
        elif disp:
            safe_disp = re.sub(r'[^a-zA-Z0-9._-]', '_', disp)[:24]
            rom_name = disp[:32]
            rom_tag = safe_disp or "Custom_ROM"

        return {
            "device_name": market_name,
            "codename": codename,
            "model": model,
            "android_version": android_ver,
            "rom_name": rom_name,
            "rom_tag": rom_tag,
            "incremental": inc,
            "build_display": disp,
            "chipset": chipset
        }

    def backup_efs_imei(self, serial: str, progress_cb=None) -> Dict[str, Any]:
        """
        1-Click EFS / IMEI / Baseband & NVRAM Preservation Engine:
        - Detects Qualcomm Snapdragon vs MediaTek vs Exynos chipset.
        - Backs up modemst1, modemst2, fsg, fsc, persist (Qualcomm)
          OR nvram, nvdata, protect_f, protect_s, nvcfg, seccfg (MediaTek).
        - Saves to Desktop\\ROM_Flasher_Storage\\EFS_Backups\\<Device>_<Timestamp>\\
        - Generates 1-click Restore_IMEI_EFS.bat for instant unbricking.
        """
        def _cb(msg, pct=None):
            if progress_cb:
                try: progress_cb(msg, pct)
                except Exception: pass

        logs = []
        _cb("🔐 Checking root access on target device...", 5)
        logs.append(f"Starting EFS/IMEI Baseband Backup for serial: {serial}")

        # Pre-flight Root / Recovery / Fastboot check BEFORE touching any partitions or creating folders
        devices = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devices, serial)
        if not dev:
            err_msg = f"Exact target device [{serial}] is not connected."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "count": 0, "total": 0, "partitions": [], "logs": logs, "error": err_msg}
        dev_mode = dev["mode"]

        use_su = False
        direct_root = False
        if dev_mode != "FASTBOOT":
            id_check = self.run_cmd([self.adb_path, "-s", serial, "shell", "id"], timeout=5)
            if adb_result_ok(id_check) and re.search(r"uid=0\(", id_check.get("stdout", "") or ""):
                direct_root = True
                logs.append("Root verified: Direct root environment (Recovery / TWRP / OrangeFox).")
            else:
                su_check = self.run_cmd([self.adb_path, "-s", serial, "shell", "su -c id || su 0 id"], timeout=6)
                if adb_result_ok(su_check) and re.search(r"uid=0\(", su_check.get("stdout", "") or ""):
                    use_su = True
                    logs.append("Root verified: Active su privilege (uid=0). Deep raw sector backup enabled.")

            if not direct_root and not use_su:
                err_msg = "Root access not found! Device is not rooted. Please install Root (KernelSU / Magisk / APatch / SukiSU) or boot into TWRP/OrangeFox Recovery first."
                logs.append(f"❌ {err_msg}")
                _cb("❌ Root required! Device is not rooted.", 0)
                return {
                    "success": False,
                    "count": 0,
                    "partitions": [],
                    "logs": logs,
                    "error": err_msg
                }

        _cb("🔍 Detecting device, Android version & ROM info...", 10)
        if dev_mode == "FASTBOOT":
            # Never call ADB getprop while the exact device is already in FASTBOOT.
            fb_product = self._get_fastboot_var(serial, "product") or "fastboot_device"
            fb_model = self._get_fastboot_var(serial, "model") or fb_product
            fb_blob = " ".join(
                self._get_fastboot_var(serial, v) for v in ("product", "model", "variant", "board", "cpu-ab")
            ).lower()
            if any(k in fb_blob for k in ("mtk", "mt67", "mt68", "mt69", "dimensity", "helio")):
                chip_str = "mediatek(fastboot)"
            elif any(k in fb_blob for k in ("sdm", "sm8", "sm7", "sm4", "msm", "qcom", "snapdragon")):
                chip_str = "qualcomm(fastboot)"
            else:
                chip_str = "unknown(fastboot)"
            info = {
                "device_name": fb_model, "codename": fb_product.lower(), "model": fb_model,
                "android_version": "Unknown", "rom_name": "Fastboot Mode", "rom_tag": "Fastboot",
                "incremental": "", "build_display": "", "chipset": chip_str
            }
        else:
            info = self._detect_device_rom_info(serial)
            chip_str = info["chipset"]

        codename = info["codename"]
        device_name = info["device_name"]
        android_ver = info["android_version"]
        rom_name = info["rom_name"]
        rom_tag = info["rom_tag"]

        qualcomm_parts = ["modemst1", "modemst2", "fsg", "fsc", "persist"]
        mtk_parts = ["nvram", "nvdata", "protect_f", "protect_s", "nvcfg", "seccfg", "proinfo"]
        if "mediatek" in chip_str or any(k in chip_str for k in ("dimensity", "helio")):
            target_partitions = mtk_parts
            logs.append(f"Detected MediaTek Baseband Architecture ({chip_str})")
        elif "qualcomm" in chip_str or any(k in chip_str for k in ("sdm", "sm8", "sm7", "msm")):
            target_partitions = qualcomm_parts
            logs.append(f"Detected Qualcomm Snapdragon Baseband Architecture ({chip_str})")
        else:
            target_partitions = qualcomm_parts + mtk_parts
            logs.append(f"⚠️ WARNING: Chipset could not be determined from fastboot product/variables ({chip_str}). Backing up the UNION of Qualcomm + MediaTek EFS partitions; some partitions may not exist on this device.")

        def _partition_exists(part: str) -> bool:
            if dev_mode == "FASTBOOT":
                size_var = (self._get_fastboot_var(serial, f"partition-size:{part}") or "").strip()
                return bool(re.fullmatch(r"(0x[0-9A-Fa-f]+|\d+)", size_var))
            probe = (
                f"for p in /dev/block/bootdevice/by-name/{part} /dev/block/by-name/{part} "
                f"/dev/block/platform/*/by-name/{part} /dev/block/platform/*/*/by-name/{part}; do "
                f"if [ -e \"$p\" ]; then echo __EFS_PART_OK__; break; fi; done"
            )
            res = self.run_cmd([self.adb_path, "-s", serial, "shell", probe], timeout=8)
            return "__EFS_PART_OK__" in (res.get("stdout", "") or "")

        missing_partitions: List[str] = []
        for part in target_partitions:
            if not _partition_exists(part):
                missing_partitions.append(part)
                logs.append(f"• Partition {part} not present on this device; skipped.")

        backup_serialno = (
            (self._get_fastboot_var(serial, "serialno") if dev_mode == "FASTBOOT" else self._get_prop(serial, "ro.serialno"))
            or serial
        )
        logs.append(f"Backup target serialno: {backup_serialno}")

        # Structured Hierarchy: EFS_Backups/<DeviceName_(codename)>/<ROM_AndroidVer_Build_Timestamp>/
        safe_dev_folder = re.sub(r'[^a-zA-Z0-9._()-]', '_', f"{device_name}_({codename})").strip("_")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        date_display = time.strftime("%d %b %Y, %I:%M %p")
        ver_part = f"_{re.sub(r'[^a-zA-Z0-9._-]', '_', info['incremental'])}" if info.get("incremental") else ""
        backup_sub = f"{rom_tag}_Android{android_ver}{ver_part}_{timestamp}"
        backup_sub = re.sub(r'[^a-zA-Z0-9._-]', '_', backup_sub)

        out_dir = os.path.join(get_storage_dir("EFS_Backups"), safe_dev_folder, backup_sub)
        os.makedirs(out_dir, exist_ok=True)
        logs.append(f"Device: {device_name} ({codename}) | Android {android_ver} | ROM: {rom_name}")

        _cb(f"Storage target prepared: {safe_dev_folder}/{backup_sub}", 15)
        pulled_files = []

        step_pct = 20
        pct_increment = 60 / max(len(target_partitions), 1)

        for part in target_partitions:
            step_pct += pct_increment
            _cb(f"Backing up partition: {part}...", int(step_pct))
            if part in missing_partitions:
                continue
            dest_file = os.path.join(out_dir, f"{part}.img")

            backed_up = False
            if direct_root or use_su:
                remote_tmp = f"/sdcard/rf_efs_{part}_{os.getpid()}_{int(time.time() * 1000)}.img"
                try:
                    raw_dd = (
                        f"for p in /dev/block/bootdevice/by-name/{part} /dev/block/by-name/{part} "
                        f"/dev/block/platform/*/by-name/{part} /dev/block/platform/*/*/by-name/{part}; do "
                        f"if [ -e \"$p\" ]; then dd if=\"$p\" of=\"{remote_tmp}\" bs=4096 2>/dev/null && echo __DD_OK__ && break; fi; done"
                    )
                    dd_cmd = f"su -c {shlex.quote(raw_dd)}" if use_su else raw_dd
                    dd_res = self.run_cmd([self.adb_path, "-s", serial, "shell", dd_cmd], timeout=30)
                    if not adb_result_ok(dd_res) or "__DD_OK__" not in (dd_res.get("stdout", "") or ""):
                        logs.append(f"⚠️ dd failed for {part}: {dd_res.get('output', '')}")
                    else:
                        pull_res = self.run_cmd([self.adb_path, "-s", serial, "pull", remote_tmp, dest_file], timeout=45)
                        dumped_size = os.path.getsize(dest_file) if os.path.exists(dest_file) else 0
                        size_res = self.run_cmd([self.adb_path, "-s", serial, "shell", f"stat -c %s \"{remote_tmp}\" 2>/dev/null"], timeout=5)
                        size_txt = (size_res.get("stdout", "") or "").strip()
                        remote_size = int(size_txt) if re.fullmatch(r"\d+", size_txt) else 0
                        # EFS/IMEI is irreversible: a failed size query must never
                        # turn a truncated dd dump into a "valid" backup.
                        if adb_result_ok(pull_res) and dumped_size > 0 and remote_size > 0 and dumped_size == remote_size:
                            backed_up = True
                            pulled_files.append(f"{part}.img")
                            logs.append(f"✅ Successfully dumped {part} ({dumped_size:,} bytes)")
                        else:
                            if os.path.exists(dest_file):
                                try: os.remove(dest_file)
                                except Exception: pass
                            logs.append(f"⚠️ Failed to pull dumped {part}: {pull_res.get('output', '')}")
                finally:
                    self.run_cmd([self.adb_path, "-s", serial, "shell", f"rm -f \"{remote_tmp}\""], timeout=5)

            if not backed_up and dev_mode == "FASTBOOT":
                size_var = (self._get_fastboot_var(serial, f"partition-size:{part}") or "").strip()
                expected_size = 0
                if re.fullmatch(r"(0x[0-9A-Fa-f]+|\d+)", size_var):
                    try:
                        expected_size = int(size_var, 0)
                    except Exception:
                        expected_size = 0
                fetch_res = self.run_cmd([self.fastboot_path, "-s", serial, "fetch", part, dest_file], timeout=30)
                dumped_size = os.path.getsize(dest_file) if os.path.exists(dest_file) else 0
                if expected_size > 0 and dumped_size == expected_size and fastboot_result_ok(fetch_res):
                    backed_up = True
                    pulled_files.append(f"{part}.img")
                    logs.append(f"✅ Fastboot fetch extracted {part} ({dumped_size:,} bytes)")
                else:
                    if os.path.exists(dest_file):
                        try: os.remove(dest_file)
                        except Exception: pass
                    logs.append(f"⚠️ Fastboot fetch for {part} failed size verification (got {dumped_size}, expected {expected_size}): {fetch_res.get('output', '')}")

        if len(pulled_files) == 0:
            try:
                shutil.rmtree(out_dir, ignore_errors=True)
            except Exception:
                pass
            _cb("EFS backup failed (No root / recovery access)", 0)
            return {
                "success": False,
                "count": 0,
                "partitions": [],
                "logs": logs,
                "error": "Could not dump partitions. Ensure device is rooted or booted into TWRP / OrangeFox Recovery."
            }

        # Create Restore_IMEI_EFS.bat with explicit files, exact serial and error checks.
        def _bat_text(value: Any) -> str:
            return (
                str(value if value is not None else "")
                .replace("%", "%%").replace("^", "^^").replace("&", "^&")
                .replace("|", "^|").replace("<", "^<").replace(">", "^>")
                .replace('"', "")
            )

        target_sno = backup_serialno if re.fullmatch(r"[A-Za-z0-9_.-]+", str(backup_serialno or "")) else str(serial or "")
        serial_ok = bool(re.fullmatch(r"[A-Za-z0-9_.-]+", target_sno))
        bat_fb = f"fastboot -s {target_sno}" if serial_ok else None
        if not serial_ok:
            logs.append("⚠️ Generated restore script will refuse to run: target serial is not safe for a batch command.")

        bat_lines = [
            "@echo off",
            "set EFS_RESTORE_FAILED=0",
            f"title Restore EFS / IMEI - {_bat_text(device_name)} ({_bat_text(codename)})",
            "echo ========================================================",
            f"echo      RESTORE EFS / IMEI / BASEBAND ({_bat_text(device_name)} - {_bat_text(rom_name)} Android {_bat_text(android_ver)})",
            "echo ========================================================",
            f"echo Target device: {_bat_text(target_sno)}",
            "echo [!] Connect ONLY this device in Fastboot mode before continuing.",
            "echo Press ANY key to begin baseband restore...",
            "pause >nul",
            ""
        ]
        if not bat_fb:
            bat_lines.extend([
                "echo Refusing to restore: no validated target serial.",
                "exit /b 1"
            ])
        else:
            for f in pulled_files:
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.img", f):
                    continue
                p_name = f[:-4]
                bat_lines.append(f"echo Flashing {_bat_text(p_name)}...")
                bat_lines.append(f'{bat_fb} flash {p_name} "{f}"')
                bat_lines.append("if errorlevel 1 set EFS_RESTORE_FAILED=1")
            bat_lines.extend([
                "",
                'if "%EFS_RESTORE_FAILED%"=="0" (',
                "    echo [DONE] EFS / IMEI restore completed. Rebooting...",
                f"    {bat_fb} reboot",
                ") else (",
                "    echo Restore finished with errors. Phone was NOT rebooted automatically.",
                ")",
                "pause"
            ])
        bat_path = os.path.join(out_dir, "Restore_IMEI_EFS.bat")
        with open(bat_path, "w", encoding="utf-8") as bf:
            bf.write("\n".join(bat_lines))

        # Save structured metadata JSON for instant auto-sync restore popup
        total_bytes = sum(os.path.getsize(os.path.join(out_dir, f)) for f in pulled_files if os.path.exists(os.path.join(out_dir, f)))
        meta_obj = {
            "serialno": target_sno,
            "target_serial": serial,
            "device_name": device_name,
            "codename": codename,
            "model": info["model"],
            "android_version": android_ver,
            "rom_name": rom_name,
            "rom_tag": rom_tag,
            "incremental": info.get("incremental", ""),
            "build_display": info.get("build_display", ""),
            "chipset": chip_str,
            "timestamp": timestamp,
            "date_display": date_display,
            "partitions": pulled_files,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2)
        }
        try:
            meta_tmp = os.path.join(out_dir, "backup_meta.json.tmp")
            with open(meta_tmp, "w", encoding="utf-8") as mf:
                json.dump(meta_obj, mf, indent=2)
            os.replace(meta_tmp, os.path.join(out_dir, "backup_meta.json"))
        except Exception as e:
            err_msg = f"Backup files were saved but metadata could not be written: {e}"
            logs.append(f"❌ {err_msg}")
            return {"success": False, "count": len(pulled_files), "total": len(target_partitions), "partitions": pulled_files,
                    "backup_dir": out_dir, "error": err_msg, "logs": logs}

        chipset_known = not ("unknown" in chip_str.lower())
        partial = bool(missing_partitions) and chipset_known
        all_ok = len(pulled_files) > 0 and not partial
        error = None
        if len(pulled_files) == 0:
            error = "Could not dump partitions. Ensure device is rooted or booted into TWRP / OrangeFox Recovery."
        elif partial:
            error = f"Partial backup: missing EFS partition(s) {', '.join(missing_partitions)}."
            logs.append(f"⚠️ {error}")
        _cb(f"EFS backup {'completed' if all_ok else 'finished with warnings'}! ({len(pulled_files)} partition(s) secured)", 100 if all_ok else 0)
        logs.append(f"🎉 EFS Backup finished! Saved in: {out_dir}")
        return {
            "success": all_ok,
            "partial": partial,
            "count": len(pulled_files),
            "total": len(target_partitions),
            "partitions": pulled_files,
            "missing_partitions": missing_partitions,
            "backup_dir": out_dir,
            "meta": meta_obj,
            "restore_bat": bat_path,
            "logs": logs,
            "error": error
        }

    def list_efs_backups(self, current_serial: Optional[str] = None) -> Dict[str, Any]:
        """Scans ROM_Flasher_Storage\\EFS_Backups recursively for structured & legacy EFS backups."""
        base_dir = get_storage_dir("EFS_Backups")
        current_codename = ""
        current_serialno = ""
        if current_serial:
            try:
                devices = self.detect_devices(bypass_cache=True)
                dev = self._find_device_exact(devices, current_serial)
                if dev and dev["mode"] == "ADB":
                    current_codename = (dev.get("codename") or self._get_prop(current_serial, "ro.product.device") or "").strip().lower()
                    current_serialno = str(self._get_prop(current_serial, "ro.serialno") or current_serial).strip()
                elif dev and dev["mode"] == "FASTBOOT":
                    current_codename = (dev.get("codename") or self._get_fastboot_var(current_serial, "product") or "").strip().lower()
                    current_serialno = str(self._get_fastboot_var(current_serial, "serialno") or current_serial).strip()
            except Exception:
                pass

        backups = []
        if os.path.exists(base_dir):
            for root, dirs, files in os.walk(base_dir):
                imgs = sorted([f for f in files if f.lower().endswith(".img")])
                if not imgs:
                    continue
                meta_path = os.path.join(root, "backup_meta.json")
                meta = {}
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            meta = json.load(mf)
                    except Exception:
                        meta = {}

                total_bytes = sum(os.path.getsize(os.path.join(root, f)) for f in imgs)
                mtime = os.path.getmtime(root)
                rel_parts = os.path.relpath(root, base_dir).split(os.sep)

                codename = meta.get("codename", "")
                device_name = meta.get("device_name", "")
                if not device_name:
                    device_name = rel_parts[0].replace("_", " ") if len(rel_parts) >= 2 else os.path.basename(root)
                if not codename and "(" in device_name and ")" in device_name:
                    codename = device_name.split("(")[-1].split(")")[0].strip()
                elif not codename and "_" in os.path.basename(root):
                    codename = os.path.basename(root).split("_")[0].strip()

                rom_name = meta.get("rom_name") or (os.path.basename(root).replace("_", " ") if len(rel_parts) >= 2 else "Legacy Backup")
                android_ver = meta.get("android_version") or "?"
                date_display = meta.get("date_display") or time.strftime("%d %b %Y, %I:%M %p", time.localtime(mtime))
                incremental = meta.get("incremental", "")

                meta_serial = str(meta.get("serialno") or meta.get("target_serial") or "").strip()
                is_match = bool(
                    (current_serialno and meta_serial and current_serialno.lower() == meta_serial.lower())
                    or (current_codename and codename and current_codename == codename.lower())
                )
                backups.append({
                    "folder_path": root,
                    "device_name": device_name,
                    "codename": codename or "unknown",
                    "rom_name": rom_name,
                    "android_version": android_ver,
                    "incremental": incremental,
                    "date_display": date_display,
                    "partitions": imgs,
                    "partition_count": len(imgs),
                    "size_mb": meta.get("total_size_mb") or round(total_bytes / (1024 * 1024), 2),
                    "is_current_device": is_match,
                    "_mtime": mtime
                })

        backups.sort(key=lambda x: (1 if x["is_current_device"] else 0, x["_mtime"]), reverse=True)
        for b in backups:
            b.pop("_mtime", None)
        return {"success": True, "backups": backups, "current_codename": current_codename,
                "current_serialno": current_serialno, "base_dir": base_dir}

    def restore_efs_imei(self, serial: str, backup_folder: str, progress_cb=None, allow_foreign: bool = False) -> Dict[str, Any]:
        """Restores EFS/IMEI partitions via Rooted ADB / Recovery dd first (bypasses Fastboot Protected Partition locks), falling back to Fastboot."""
        def _cb(msg, pct=None):
            if progress_cb:
                try: progress_cb(msg, pct)
                except Exception: pass

        if not os.path.exists(backup_folder):
            return {"success": False, "error": f"Backup folder not found: {backup_folder}", "logs": []}

        # Only backups inside ROM_Flasher_Storage/EFS_Backups may be flashed;
        # symlinks and arbitrary folders cannot feed attacker-chosen bytes to EFS.
        base_dir = os.path.realpath(get_storage_dir("EFS_Backups"))
        folder = os.path.realpath(backup_folder)
        try:
            inside_storage = os.path.commonpath([base_dir, folder]) == base_dir
        except ValueError:
            inside_storage = False
        if not inside_storage:
            return {"success": False, "error": "Refusing EFS restore from a folder outside App storage/EFS_Backups.", "logs": []}

        imgs = sorted([
            f for f in os.listdir(folder)
            if f.lower().endswith(".img") and os.path.isfile(os.path.join(folder, f))
        ])
        if not imgs:
            return {"success": False, "error": "No .img partition backups found in specified directory.", "logs": []}

        efs_whitelist = {
            "modemst1", "modemst2", "fsg", "fsc", "persist",
            "nvram", "nvdata", "protect_f", "protect_s", "nvcfg", "seccfg", "proinfo"
        }
        bad_names = []
        for f in imgs:
            part = f[:-4]
            try:
                link_ok = os.path.commonpath([folder, os.path.realpath(os.path.join(folder, f))]) == folder
            except ValueError:
                link_ok = False
            if (not re.fullmatch(r"[A-Za-z0-9_-]+\.img", f, re.I)
                    or part not in efs_whitelist
                    or not link_ok):
                bad_names.append(f)
        if bad_names:
            return {"success": False,
                    "error": f"Unsafe or unknown EFS partition image(s): {', '.join(bad_names)}", "logs": []}

        meta_obj: Dict[str, Any] = {}
        meta_path = os.path.join(backup_folder, "backup_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    loaded = json.load(mf)
                if isinstance(loaded, dict):
                    meta_obj = loaded
            except Exception:
                pass
        meta_serial = str(meta_obj.get("serialno") or "").strip()
        target_serial = str(serial or "").strip()
        if meta_serial and meta_serial.lower() != target_serial.lower() and not allow_foreign:
            return {
                "success": False,
                "error": f"Backup belongs to serial {meta_serial}, target is {target_serial}. Refusing foreign EFS restore; pass allow_foreign=True only if you are certain.",
                "meta_serial": meta_serial,
                "target_serial": target_serial
            }

        logs = [f"Starting EFS / IMEI Restore from: {backup_folder}"]
        _cb(f"Found {len(imgs)} partition image(s). Checking Root/Recovery access...", 5)

        devices = self.detect_devices(bypass_cache=True)
        dev = self._find_device_exact(devices, serial)
        if not dev:
            msg = f"Exact target device [{serial}] is not connected. Refusing to restore EFS to another device."
            logs.append(f"❌ {msg}")
            return {"success": False, "error": msg, "logs": logs}
        dev_mode = dev["mode"]

        # 1. Try Rooted ADB / Recovery direct dd restore (bypasses Fastboot 'Protected Partitions' block!)
        if dev_mode != "FASTBOOT":
            direct_root = False
            use_su = False
            id_check = self.run_cmd([self.adb_path, "-s", serial, "shell", "id"], timeout=5)
            if adb_result_ok(id_check) and re.search(r"uid=0\(", id_check.get("stdout", "") or ""):
                direct_root = True
                logs.append("Direct root (Recovery/ADB root) detected. Using raw block restore...")
            else:
                su_check = self.run_cmd([self.adb_path, "-s", serial, "shell", "su -c id || su 0 id"], timeout=6)
                if adb_result_ok(su_check) and re.search(r"uid=0\(", su_check.get("stdout", "") or ""):
                    use_su = True
                    logs.append("Root privilege (su 0) detected. Using raw block restore (bypasses Fastboot Protected Partitions)...")

            if direct_root or use_su:
                success_count = 0
                failed_parts = []
                for idx, img_file in enumerate(imgs):
                    part_name = img_file[:-4]
                    img_path = os.path.join(backup_folder, img_file)
                    _cb(f"Restoring {part_name} via Root block write...", int(10 + (idx + 1) * (80 / len(imgs))))

                    local_size = os.path.getsize(img_path)
                    if local_size <= 0:
                        failed_parts.append(part_name)
                        logs.append(f"⚠️ Empty image for {part_name}; refusing to write.")
                        continue
                    remote_tmp = f"/data/local/tmp/efs_restore_{part_name}_{os.getpid()}_{int(time.time() * 1000)}.img"
                    block_paths = (
                        f"/dev/block/bootdevice/by-name/{part_name} /dev/block/by-name/{part_name} "
                        f"/dev/block/platform/*/by-name/{part_name} /dev/block/platform/*/*/by-name/{part_name}"
                    )
                    try:
                        push_res = self.run_cmd([self.adb_path, "-s", serial, "push", img_path, remote_tmp], timeout=60)
                        if not adb_result_ok(push_res):
                            failed_parts.append(part_name)
                            logs.append(f"⚠️ Failed pushing {part_name}: {push_res.get('output', '')}")
                            continue

                        size_script = (
                            f"for p in {block_paths}; do if [ -e \"$p\" ]; then "
                            f"sz=$(blockdev --getsize64 \"$p\" 2>/dev/null || stat -c %s \"$p\" 2>/dev/null); "
                            f"echo \"__BLKSIZE__=$sz\"; break; fi; done"
                        )
                        size_res = self.run_cmd([self.adb_path, "-s", serial, "shell", size_script], timeout=10)
                        m_size = re.search(r"__BLKSIZE__=(\d+)", size_res.get("stdout", "") or "")
                        dev_size = int(m_size.group(1)) if m_size else 0
                        if dev_size <= 0 or local_size != dev_size:
                            failed_parts.append(part_name)
                            logs.append(f"⚠️ Partition size check failed for {part_name} (image {local_size}, device {dev_size}); aborting this partition.")
                            continue

                        local_hash = hashlib.sha256()
                        with open(img_path, "rb") as lf:
                            for block in iter(lambda: lf.read(1024 * 1024), b""):
                                local_hash.update(block)

                        dd_script = (
                            f"for p in {block_paths}; do if [ -e \"$p\" ]; then "
                            f"dd if=\"{remote_tmp}\" of=\"$p\" bs={local_size} count=1 conv=notrunc && sync && echo __DD_OK__; break; fi; done"
                        )
                        cmd = f"su -c {shlex.quote(dd_script)}" if use_su else dd_script
                        dd_res = self.run_cmd([self.adb_path, "-s", serial, "shell", cmd], timeout=120)

                        if not adb_result_ok(dd_res) or "__DD_OK__" not in (dd_res.get("stdout", "") or ""):
                            failed_parts.append(part_name)
                            logs.append(f"⚠️ Root dd failed for {part_name}: {dd_res.get('output', '')}")
                            continue

                        verify_script = (
                            f"for p in {block_paths}; do if [ -e \"$p\" ]; then "
                            f"dd if=\"$p\" bs={local_size} count=1 2>/dev/null | sha256sum | cut -d \" \" -f1; break; fi; done"
                        )
                        verify_cmd = f"su -c {shlex.quote(verify_script)}" if use_su else verify_script
                        v_res = self.run_cmd([self.adb_path, "-s", serial, "shell", verify_cmd], timeout=120)
                        hashes = re.findall(r"\b[0-9a-fA-F]{64}\b", v_res.get("stdout", "") or "")
                        remote_hash = hashes[-1].lower() if hashes else ""
                        if remote_hash != local_hash.hexdigest().lower():
                            failed_parts.append(part_name)
                            logs.append(f"⚠️ Post-write hash mismatch for {part_name} (wrote {local_size} bytes); restore is NOT verified.")
                            continue

                        success_count += 1
                        logs.append(f"✅ Restored {part_name} via Root raw block write ({local_size} bytes, hash verified)!")
                    finally:
                        self.run_cmd([self.adb_path, "-s", serial, "shell", f"rm -f \"{remote_tmp}\""], timeout=5)

                if success_count > 0:
                    _cb(f"Restored {success_count}/{len(imgs)} partition(s)! Rebooting device...", 96)
                    logs.append(f"Rebooting device to apply restored EFS/IMEI ({success_count}/{len(imgs)})...")
                    reboot_res = self.reboot(serial, "ADB", "system")
                    if not adb_result_ok(reboot_res):
                        err_msg = f"Reboot to system failed: {reboot_res.get('output', '')}"
                        logs.append(f"⚠️ {err_msg}")
                        failed_parts.append("reboot")

                all_ok = success_count == len(imgs) and not failed_parts
                _cb(f"EFS Restore finished ({success_count}/{len(imgs)})!", 100 if all_ok else 0)
                return {
                    "success": all_ok,
                    "restored_count": success_count,
                    "total": len(imgs),
                    "failed": failed_parts,
                    "logs": logs,
                    "error": None if all_ok else f"Only {success_count}/{len(imgs)} partitions restored (failed: {', '.join(failed_parts)})."
                }

        # 2. Fastboot Fallback (note: MediaTek nvram/nvdata/nvcfg/proinfo are protected in Fastboot unless unlocked/engineering)
        fb_serial = serial
        if dev_mode == "ADB":
            _cb("No ADB root found. Rebooting to Bootloader (Fastboot)...", 8)
            logs.append("No ADB root found. Auto-rebooting to Bootloader (Fastboot)...")
            reboot_res = self.reboot(serial, "ADB", "bootloader")
            if not adb_result_ok(reboot_res):
                err_msg = f"Reboot to Fastboot failed: {reboot_res.get('output', '')}"
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "logs": logs}
            time.sleep(3)
            fb_found = False
            for _ in range(20):
                time.sleep(1.5)
                fb_devs = self.detect_devices(bypass_cache=True)
                fb = self._find_device_exact(fb_devs, serial, "FASTBOOT")
                if fb:
                    fb_found = True
                    break
            if not fb_found:
                err_msg = f"Exact target [{serial}] did not appear in FASTBOOT. Aborting EFS restore."
                logs.append(f"❌ {err_msg}")
                return {"success": False, "error": err_msg, "logs": logs}
        elif dev_mode != "FASTBOOT":
            err_msg = f"Device [{serial}] is in unsupported mode {dev_mode}."
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}

        success_count = 0
        protected_blocked = []
        for idx, img_file in enumerate(imgs):
            part_name = img_file[:-4]
            img_path = os.path.join(backup_folder, img_file)
            _cb(f"Restoring {part_name} via Fastboot...", int(10 + (idx + 1) * (80 / len(imgs))))

            res = self.flash_partition(fb_serial, part_name, img_path)
            out_txt = res.get("output", "")
            if fastboot_step_ok(res):
                success_count += 1
                logs.append(f"✅ Restored {part_name} successfully")
            else:
                if "protected partitions" in out_txt.lower():
                    protected_blocked.append(part_name)
                logs.append(f"⚠️ Fastboot flash failed for {part_name}: {out_txt}")

        if success_count > 0:
            _cb("Rebooting to System...", 98)
            reboot_res = self.reboot(fb_serial, "FASTBOOT", "system")
            if not fastboot_result_ok(reboot_res):
                err_msg = f"Reboot to system failed: {reboot_res.get('output', '')}"
                logs.append(f"⚠️ {err_msg}")
                protected_blocked.append("reboot")

        all_ok = (success_count == len(imgs) and not protected_blocked)
        err_msg = None
        if not all_ok:
            if "reboot" in protected_blocked:
                err_msg = f"EFS partitions were written but reboot failed: {reboot_res.get('output', '')}"
            elif protected_blocked:
                err_msg = f"Fastboot blocked protected partitions ({', '.join(protected_blocked)}). Please root device or boot TWRP/OrangeFox for full 100% EFS restore."
            elif success_count == 0:
                err_msg = "Failed to flash EFS partitions in Fastboot."
            else:
                err_msg = f"Partial restore: only {success_count}/{len(imgs)} partitions flashed."

        _cb("EFS Restore finished!" if all_ok else f"⚠️ {err_msg}", 100 if all_ok else 0)
        return {
            "success": all_ok,
            "restored_count": success_count,
            "total": len(imgs),
            "logs": logs,
            "error": err_msg
        }

    # =========================================================================
    # 🚀 FEATURE 4: UNIVERSAL DEVICE OPTIMIZER & FPS BOOSTER (NO ROOT NEEDED)
    # =========================================================================
    def _check_adb_err(self, res: Dict[str, Any]) -> Optional[str]:
        """Inspects exit code AND output for permission/security/command errors."""
        if not isinstance(res, dict):
            return "ADB command returned no result."
        out = f"{res.get('stdout', '')} {res.get('stderr', '')} {res.get('output', '')}".strip()
        low = out.lower()
        if "securityexception" in low or "permission denial" in low or "write_secure_settings" in low:
            return "HyperOS / MIUI Security Block: Regular USB Debugging is ON, but 'USB debugging (Security settings)' is OFF! Enable 'USB debugging (Security settings)' in Developer Options."
        if "device" in low and ("not found" in low or "offline" in low):
            return "Device disconnected or offline. Reconnect USB cable."
        if not res.get("success"):
            return (out or "ADB command exited unsuccessfully.")[:220]
        if adb_output_has_error(res):
            return out[:220]
        return None

    def _adb_shell_write(self, serial: str, shell_cmd: str, timeout: int = 6) -> Optional[str]:
        """Executes an ADB settings/write command with automatic root (su) fallback if WRITE_SECURE_SETTINGS is blocked."""
        r = self.run_cmd([self.adb_path, "-s", serial, "shell", shell_cmd], timeout=timeout)
        err = self._check_adb_err(r)
        if err and "security block" in err.lower():
            su_chk = self.run_cmd([self.adb_path, "-s", serial, "shell", "su -c id"], timeout=4)
            if adb_result_ok(su_chk) and re.search(r"uid=0\(", su_chk.get("stdout", "") or ""):
                r2 = self.run_cmd([self.adb_path, "-s", serial, "shell", f"su -c {shlex.quote(shell_cmd)}"], timeout=timeout)
                return self._check_adb_err(r2)
        return err

    def open_developer_options(self, serial: str) -> Dict[str, Any]:
        """Opens Android Developer Options directly on the connected phone screen."""
        r = self.run_cmd([self.adb_path, "-s", serial, "shell", "am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS"], timeout=6)
        out = (r.get("stdout", "") + r.get("stderr", "")).lower()
        if "error" in out or "exception" in out:
            return {"success": False, "error": "Could not open Developer Options automatically. Open Settings > Additional Settings > Developer Options on your phone."}
        return {"success": True, "message": "Opened Developer Options on phone! Scroll down and enable 'USB debugging (Security settings)'."}

    def get_optimizer_status(self, serial: str) -> Dict[str, Any]:
        """Reads live system settings & package states from the device via ADB."""
        try:
            cmd = (
                "echo PEAK=$(settings get system peak_refresh_rate 2>/dev/null); "
                "echo USER_HZ=$(settings get system user_refresh_rate 2>/dev/null); "
                "echo MIN_HZ=$(settings get system min_refresh_rate 2>/dev/null); "
                "echo WIN_ANIM=$(settings get global window_animation_scale 2>/dev/null); "
                "echo TRANS_ANIM=$(settings get global transition_animation_scale 2>/dev/null); "
                "echo DNS_MODE=$(settings get global private_dns_mode 2>/dev/null); "
                "echo DNS_SPEC=$(settings get global private_dns_specifier 2>/dev/null); "
                "echo JOYOSE=$(pm list packages -e com.xiaomi.joyose 2>/dev/null); "
                "echo JOYOSE_ALL=$(pm list packages com.xiaomi.joyose 2>/dev/null); "
                "echo MSA=$(pm list packages -e com.miui.msa.global 2>/dev/null); "
                "echo AD_ID=$(settings get global ad_id_enabled 2>/dev/null)"
            )
            res = self.run_cmd([self.adb_path, "-s", serial, "shell", cmd], timeout=10)
            if not adb_result_ok(res):
                return {"success": False, "error": f"Could not read device status: {res.get('output', '')}"}
            out = res.get("stdout", "") or ""
            vals = {}
            for line in out.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()

            peak = vals.get("PEAK", "null")
            user_hz = vals.get("USER_HZ", "null")
            refresh_str = "Default"
            for candidate in (user_hz, peak):
                if candidate and candidate not in ("null", "None", ""):
                    try:
                        hz_num = int(float(candidate))
                        if hz_num >= 90:
                            refresh_str = f"{hz_num}Hz"
                            break
                    except ValueError:
                        pass

            anim_raw = vals.get("WIN_ANIM", "null")
            anim_str = f"{anim_raw}x" if anim_raw not in ("null", "None", "") else "1.0x"

            dns_mode = vals.get("DNS_MODE", "null")
            dns_spec = vals.get("DNS_SPEC", "null")
            if dns_mode == "hostname" and dns_spec not in ("null", "None", ""):
                dns_str = dns_spec
            elif dns_mode == "off":
                dns_str = "Off"
            else:
                dns_str = "Automatic"

            joyose_installed = "com.xiaomi.joyose" in vals.get("JOYOSE_ALL", "")
            joyose_enabled = "com.xiaomi.joyose" in vals.get("JOYOSE", "")
            if not joyose_installed:
                joyose_str = "Not Present"
            elif joyose_enabled:
                joyose_str = "Active (Throttling)"
            else:
                joyose_str = "Disabled"

            msa_active = "com.miui.msa.global" in vals.get("MSA", "")
            ad_id = vals.get("AD_ID", "null")
            telemetry_str = "Disabled" if (not msa_active and ad_id == "0") else ("Active" if msa_active else "Standard")

            return {
                "success": True,
                "status": {
                    "refresh_rate": refresh_str,
                    "animation_scale": anim_str,
                    "private_dns": dns_str,
                    "joyose": joyose_str,
                    "telemetry": telemetry_str
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def apply_optimizer_tweak(self, serial: str, tweak_id: str, value: Any = None) -> Dict[str, Any]:
        """
        Universal Android System Optimizer & Thermal Throttling Killer (ADB Settings).
        Verifies every ADB write and reads back actual device state.
        """
        logs = []
        try:
            # Exact-serial ADB preflight: substring matching cannot target 1234 on 123456.
            dev_err = self._require_adb_device(serial)
            if dev_err:
                fb_chk = self.run_cmd([self.fastboot_path, "devices"], timeout=5)
                msg = ("Device is in Fastboot mode — switch to Android (ADB) mode to apply Optimizer tweaks."
                       if fastboot_devices_has_serial(fb_chk, serial) else dev_err)
                return {"success": False, "error": msg, "logs": logs}

            if tweak_id in ["force_120hz", "force_144hz"]:
                rate = 144 if tweak_id == "force_144hz" else 120
                cmds = [
                    f"settings put system peak_refresh_rate {float(rate)}",
                    f"settings put system min_refresh_rate {float(rate)}",
                    f"settings put system user_refresh_rate {rate}",
                    f"settings put secure miui_refresh_rate {rate}",
                    "settings put secure refresh_rate_mode 2",
                ]
                for c in cmds:
                    err = self._adb_shell_write(serial, c, timeout=6)
                    if err:
                        logs.append(f"❌ {err}")
                        return {"success": False, "error": err, "logs": logs}

                # Verify readback
                chk = self.run_cmd([self.adb_path, "-s", serial, "shell", "settings get system peak_refresh_rate"], timeout=5)
                actual = (chk.get("stdout", "") or "").strip()
                try:
                    applied_rate = int(float(actual))
                except (TypeError, ValueError):
                    applied_rate = -1
                if applied_rate != rate:
                    err_msg = f"Refresh rate did not persist (got '{actual}', target {rate}Hz). Enable 'USB debugging (Security settings)'."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                logs.append(f"🚀 Verified peak_refresh_rate = {actual} (Target: {rate}Hz)")
                st = self.get_optimizer_status(serial).get("status")
                return {"success": True, "message": f"Refresh rate locked to {rate}Hz (Verified: {actual})", "logs": logs, "status": st}

            elif tweak_id == "restore_refresh":
                for c in [
                    "settings delete system peak_refresh_rate",
                    "settings delete system user_refresh_rate",
                    "settings delete system min_refresh_rate",
                    "settings delete secure miui_refresh_rate",
                    "settings put secure refresh_rate_mode 0",
                ]:
                    err = self._adb_shell_write(serial, c, timeout=6)
                    if err:
                        return {"success": False, "error": err, "logs": [err]}
                logs.append("✅ Default dynamic refresh rate restored.")
                st = self.get_optimizer_status(serial).get("status")
                return {"success": True, "message": "Default dynamic refresh rate restored", "logs": logs, "status": st}

            elif tweak_id == "disable_joyose":
                pkgs = ["com.xiaomi.joyose", "com.miui.powerkeeper"]
                found_any = False
                disabled_any = False
                for pkg in pkgs:
                    chk = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm path {pkg}"], timeout=6)
                    if "package:" not in chk.get("stdout", ""):
                        continue
                    found_any = True
                    r = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm disable-user --user 0 {pkg}"], timeout=10)
                    err = self._check_adb_err(r)
                    if adb_result_ok(r) and "disabled" in (r.get("stdout", "") + r.get("output", "")).lower():
                        disabled_any = True
                        logs.append(f"❄️ Disabled {pkg} via pm disable-user")
                    else:
                        # HyperOS fallback: uninstall for user 0 (reversible without root)
                        r2 = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm uninstall -k --user 0 {pkg}"], timeout=10)
                        if adb_result_ok(r2, r"\bSuccess\b"):
                            disabled_any = True
                            logs.append(f"❄️ Disabled {pkg} for user 0 (HyperOS mode)")
                        else:
                            logs.append(f"⚠️ Could not disable {pkg}: {err or r2.get('stdout', '')}")

                st = self.get_optimizer_status(serial).get("status")
                if not found_any:
                    return {"success": False, "error": "Joyose / Powerkeeper not found (Only for Xiaomi / POCO / Redmi devices).", "logs": logs, "status": st}
                if not disabled_any:
                    return {"success": False, "error": "Permission denied by HyperOS/MIUI. Enable 'USB debugging (Security settings)' in Developer Options.", "logs": logs, "status": st}
                return {"success": True, "message": "Thermal & FPS throttle disabled (Joyose/Powerkeeper)", "logs": logs, "status": st}

            elif tweak_id == "enable_joyose":
                restored_any = False
                for pkg in ["com.xiaomi.joyose", "com.miui.powerkeeper"]:
                    r = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm enable {pkg}"], timeout=8)
                    # pm enable can exit 0 while printing "Package ... not found".
                    # Require the positive marker AND an enabled package readback.
                    if adb_result_ok(r, r"\benabled\b"):
                        chk = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm list packages -e {pkg}"], timeout=8)
                        if re.search(rf"(?m)^package:{re.escape(pkg)}\s*$", chk.get("stdout", "") or ""):
                            restored_any = True
                            logs.append(f"✅ Re-enabled {pkg} for this user")
                            continue
                    r2 = self.run_cmd([self.adb_path, "-s", serial, "shell", f"cmd package install-existing {pkg}"], timeout=8)
                    if adb_result_ok(r2):
                        restored_any = True
                        logs.append(f"✅ Reinstalled {pkg} for this user")
                    else:
                        logs.append(f"⚠️ Could not restore {pkg}: {r2.get('output', '') or r.get('output', '')}")
                if not restored_any:
                    err_msg = "Could not restore Joyose/Powerkeeper. Reinstall the system app or enable 'USB debugging (Security settings)'."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                logs.append("✅ Joyose & Powerkeeper restored.")
                st = self.get_optimizer_status(serial).get("status")
                return {"success": True, "message": "Joyose & Powerkeeper restored", "logs": logs, "status": st}

            elif tweak_id == "set_animation":
                # Validate to a bounded number BEFORE building any shell command.
                try:
                    scale_num = float(value if value is not None else "0.5")
                except (TypeError, ValueError):
                    scale_num = float("nan")
                if scale_num != scale_num or scale_num < 0 or scale_num > 10:
                    err_msg = "Invalid animation scale: enter a number between 0 and 10."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                scale = f"{scale_num:g}"
                for key in ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"]:
                    err = self._adb_shell_write(serial, f"settings put global {key} {scale}", timeout=6)
                    if err:
                        logs.append(f"❌ {err}")
                        return {"success": False, "error": err, "logs": logs}
                # Also set system & Xiaomi/HyperOS launcher animation rate
                err_sys = self._adb_shell_write(serial, f"settings put system animation_scale {scale}", timeout=5)
                if err_sys:
                    logs.append(f"⚠️ System animation scale not applied: {err_sys}")
                miui_rate = "2" if scale_num <= 0.5 else "1"
                err_miui = self._adb_shell_write(serial, f"settings put secure miui_home_animation_rate {miui_rate}", timeout=5)
                if err_miui:
                    logs.append(f"⚠️ Launcher animation rate not applied: {err_miui}")

                chk = self.run_cmd(
                    [self.adb_path, "-s", serial, "shell", "echo W=$(settings get global window_animation_scale); echo T=$(settings get global transition_animation_scale); echo A=$(settings get global animator_duration_scale)"],
                    timeout=5
                )
                if not adb_result_ok(chk):
                    err_msg = f"Could not verify animation scales: {chk.get('output', '')}"
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                chk_out = chk.get("stdout", "") or ""
                w_val = re.search(r"W=(\S+)", chk_out)
                t_val = re.search(r"T=(\S+)", chk_out)
                a_val = re.search(r"A=(\S+)", chk_out)
                w_str = w_val.group(1) if w_val else "?"
                t_str = t_val.group(1) if t_val else "?"
                a_str = a_val.group(1) if a_val else "?"
                try:
                    verified = all(abs(float(v) - scale_num) <= 0.01 for v in (w_str, t_str, a_str))
                except ValueError:
                    verified = False
                if not verified:
                    err_msg = f"Animation scales did not persist (got {w_str}/{t_str}/{a_str}, target {scale}). Enable 'USB debugging (Security settings)'."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                logs.append(f"⚡ Verified Scales -> Window:{w_str}x | Transition:{t_str}x | Animator:{a_str}x")
                st = self.get_optimizer_status(serial).get("status")
                return {"success": True, "message": f"Animation scales verified: {w_str}x / {t_str}x / {a_str}x", "logs": logs, "status": st}

            elif tweak_id == "set_private_dns":
                provider = str(value or "adguard").lower()
                if provider not in ("adguard", "cloudflare", "off"):
                    err_msg = "Invalid Private DNS provider. Choose adguard, cloudflare or off."
                    logs.append(f"❌ {err_msg}")
                    return {"success": False, "error": err_msg, "logs": logs}
                if provider in ("adguard", "cloudflare"):
                    host = "dns.adguard-dns.com" if provider == "adguard" else "one.one.one.one"
                    err = self._adb_shell_write(serial, "settings put global private_dns_mode hostname", timeout=6)
                    if err:
                        return {"success": False, "error": err, "logs": [err]}
                    err2 = self._adb_shell_write(serial, f"settings put global private_dns_specifier {host}", timeout=6)
                    if err2:
                        return {"success": False, "error": err2, "logs": [err2]}
                    chk = self.run_cmd([self.adb_path, "-s", serial, "shell", "settings get global private_dns_specifier"], timeout=5)
                    actual = (chk.get("stdout", "") or "").strip()
                    if actual != host:
                        return {"success": False, "error": f"Private DNS write did not persist (got '{actual}'). Enable 'USB debugging (Security settings)'.", "logs": logs}
                    logs.append(f"🛡️ Verified Private DNS = {actual}")
                    st = self.get_optimizer_status(serial).get("status")
                    return {"success": True, "message": f"Private DNS active: {actual}", "logs": logs, "status": st}
                else:
                    err = self._adb_shell_write(serial, "settings put global private_dns_mode off", timeout=6)
                    if err:
                        logs.append(f"❌ {err}")
                        return {"success": False, "error": err, "logs": logs}
                    del_err = self._adb_shell_write(serial, "settings delete global private_dns_specifier", timeout=6)
                    if del_err:
                        logs.append(f"⚠️ Old DNS specifier could not be cleared: {del_err}")
                    mode_chk = self.run_cmd([self.adb_path, "-s", serial, "shell", "settings get global private_dns_mode"], timeout=5)
                    if not adb_result_ok(mode_chk) or (mode_chk.get("stdout", "") or "").strip() != "off":
                        err_msg = "Private DNS did not turn off on the device (readback failed or mode is not off)."
                        logs.append(f"❌ {err_msg}")
                        return {"success": False, "error": err_msg, "logs": logs}
                    logs.append("✅ Private DNS turned Off.")
                    st = self.get_optimizer_status(serial).get("status")
                    return {"success": True, "message": "Private DNS disabled", "logs": logs, "status": st}

            elif tweak_id == "disable_telemetry":
                disabled_pkgs = []
                for pkg in ["com.miui.analytics", "com.miui.msa.global"]:
                    chk = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm path {pkg}"], timeout=5)
                    if "package:" in chk.get("stdout", ""):
                        r = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm disable-user --user 0 {pkg}"], timeout=8)
                        if adb_result_ok(r) and "disabled" in (r.get("stdout", "") + r.get("output", "")).lower():
                            disabled_pkgs.append(pkg)
                        else:
                            r2 = self.run_cmd([self.adb_path, "-s", serial, "shell", f"pm uninstall -k --user 0 {pkg}"], timeout=8)
                            if adb_result_ok(r2, r"\bSuccess\b"):
                                disabled_pkgs.append(pkg)
                err = self._adb_shell_write(serial, "settings put global ad_id_enabled 0", timeout=6)
                st = self.get_optimizer_status(serial).get("status")
                if disabled_pkgs:
                    logs.append(f"🔒 Disabled system ad/analytics packages: {', '.join(disabled_pkgs)}")
                    msg = f"Disabled {', '.join(disabled_pkgs)}" + (" (Ad ID requires Security Settings)" if err else " & Ad ID disabled!")
                    return {"success": True, "message": msg, "logs": logs, "status": st}
                if err:
                    return {"success": False, "error": err, "logs": [err], "status": st}
                logs.append("🔒 Advertising ID tracking disabled.")
                return {"success": True, "message": "Telemetry & Ad ID disabled", "logs": logs, "status": st}

            elif tweak_id == "max_performance_pack":
                applied = []
                errors = []
                for tid, val in [("force_120hz", None), ("set_animation", "0.5"), ("set_private_dns", "adguard"), ("disable_telemetry", None), ("disable_joyose", None)]:
                    sub = self.apply_optimizer_tweak(serial, tid, val)
                    logs.extend(sub.get("logs", []))
                    if sub.get("success"):
                        applied.append(tid)
                    else:
                        if tid != "disable_joyose":  # Joyose is Xiaomi-only
                            errors.append(sub.get("error", tid))
                st = self.get_optimizer_status(serial).get("status")
                if not applied:
                    return {"success": False, "error": errors[0] if errors else "Tweaks failed", "logs": logs, "status": st}
                if errors:
                    err_msg = f"Only {len(applied)}/{len(applied) + len(errors)} optimizations applied. Failed: {errors[0]}"
                    logs.append(f"⚠️ {err_msg}")
                    return {"success": False, "error": err_msg, "applied": applied, "failed": errors,
                            "partial": True, "logs": logs, "status": st}
                return {"success": True, "message": f"Applied {len(applied)} optimizations! ({', '.join(applied)})", "logs": logs, "status": st}

            err_msg = f"Unknown tweak: {tweak_id}"
            logs.append(f"❌ {err_msg}")
            return {"success": False, "error": err_msg, "logs": logs}
        except Exception as e:
            logs.append(f"❌ Optimizer error: {e}")
            return {"success": False, "error": str(e), "logs": logs}

    # =========================================================================
    # 🔋 FEATURE 5: REAL BATTERY HEALTH, ANTI-SCAM & HARDWARE INSPECTOR
    # =========================================================================
    def get_hardware_diagnostics(self, serial: str, full_audit: bool = True) -> Dict[str, Any]:
        """
        Deep Hardware Diagnostics & Anti-Scam Authenticity Inspector via ADB:
        - Live Battery telemetry (Voltage V/mV, Current mA, Watts, Temp, Cycles, Real Health %)
        - RAM capacity, pressure, ZRAM & health status
        - UFS/eMMC flash storage health & free space
        - When full_audit=True: Verified Boot, Original vs Unlocked/Tampered score,
          Warranty age & void status, Camera HAL, Bluetooth, Mic/Audio, Wi-Fi/Baseband, Sensors & Display Panel.
        """
        data: Dict[str, Any] = {
            "battery": {},
            "ram": {},
            "display": {},
            "storage": {},
            "soc": {},
            "identity": {},
            "authenticity": {},
            "warranty": {},
            "components": {}
        }

        # --- 1. Fast Live Battery + RAM Telemetry (Runs on both 3s poll & full audit) ---
        b_res = self.run_cmd([self.adb_path, "-s", serial, "shell", "dumpsys battery"], timeout=8)
        b_out = b_res.get("stdout", "")
        level = re.search(r"level:\s*(\d+)", b_out)
        temp = re.search(r"temperature:\s*(-?\d+)", b_out)
        volt = re.search(r"voltage:\s*(\d+)", b_out)
        status = re.search(r"status:\s*(\d+)", b_out)
        health = re.search(r"health:\s*(\d+)", b_out)
        tech = re.search(r"technology:\s*(\S+)", b_out)

        raw_volt = int(volt.group(1)) if volt else 0
        if raw_volt > 100000:
            volt_mv = round(raw_volt / 1000.0)
            volt_v = round(raw_volt / 1000000.0, 2)
        elif raw_volt > 100:
            volt_mv = raw_volt
            volt_v = round(raw_volt / 1000.0, 2)
        elif raw_volt > 0:
            volt_mv = raw_volt * 1000
            volt_v = round(float(raw_volt), 2)
        else:
            volt_mv = 0
            volt_v = 0.0

        sysfs_cmd = (
            "echo CYC=$(cat /sys/class/power_supply/battery/cycle_count 2>/dev/null || cat /sys/class/power_supply/bms/cycle_count 2>/dev/null || cat /sys/class/power_supply/bms/battery_cycle 2>/dev/null || cat /sys/class/power_supply/xm_bms/cycle_count 2>/dev/null || cat /sys/class/qcom-battery/cycle_count 2>/dev/null || getprop persist.vendor.battery.cycle 2>/dev/null); "
            "echo CUR=$(cat /sys/class/power_supply/battery/current_now 2>/dev/null); "
            "echo FULL=$(cat /sys/class/power_supply/battery/charge_full 2>/dev/null || cat /sys/class/power_supply/bms/charge_full 2>/dev/null || cat /sys/class/power_supply/battery/batt_capacity_max 2>/dev/null); "
            "echo DESIGN=$(cat /sys/class/power_supply/battery/charge_full_design 2>/dev/null || cat /sys/class/power_supply/bms/charge_full_design 2>/dev/null); "
            "echo RATED=$(dumpsys batterystats 2>/dev/null | grep -iE 'Capacity:|Estimated battery capacity' | head -n 2 | tr '\\n' ' '); "
            "grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo 2>/dev/null"
        )
        sys_res = self.run_cmd([self.adb_path, "-s", serial, "shell", sysfs_cmd], timeout=8)
        sys_vals = {}
        mem_vals = {}
        for line in (sys_res.get("stdout", "") or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                sys_vals[k.strip()] = v.strip()
            elif ":" in line:
                mk, mv = line.split(":", 1)
                m_num = re.search(r"(\d+)", mv)
                if m_num:
                    mem_vals[mk.strip()] = int(m_num.group(1))

        cycles = None
        cycle_m = re.search(r"(?:mCycleCount|BatteryCycleCount|cycle_count|CycleCount):\s*(\d+)", b_out)
        if cycle_m:
            cycles = int(cycle_m.group(1))
        else:
            cyc_str = sys_vals.get("CYC", "").strip()
            cyc_m2 = re.search(r"(\d+)", cyc_str)
            if cyc_m2:
                cycles = int(cyc_m2.group(1))

        current_ma = None
        cur_raw = sys_vals.get("CUR", "")
        if cur_raw.lstrip("-").isdigit():
            c_int = int(cur_raw)
            current_ma = round(c_int / 1000.0) if abs(c_int) > 10000 else c_int

        design_mah = None
        full_mah = None
        des_m = re.search(r"(\d+)", sys_vals.get("DESIGN", ""))
        if des_m and int(des_m.group(1)) > 0:
            d_val = int(des_m.group(1))
            design_mah = round(d_val / 1000.0) if d_val > 100000 else d_val
        full_m = re.search(r"(\d+)", sys_vals.get("FULL", ""))
        if full_m and int(full_m.group(1)) > 0:
            f_val = int(full_m.group(1))
            full_mah = round(f_val / 1000.0) if f_val > 100000 else f_val
        # Fallback to dumpsys batterystats Capacity: <mah>
        if not design_mah:
            rated_str = sys_vals.get("RATED", "")
            cap_m = re.search(r"Capacity:\s*(\d+(?:\.\d+)?)", rated_str) or re.search(r"(\d{4,5})\s*mAh", rated_str)
            if cap_m:
                design_mah = round(float(cap_m.group(1)))

        if design_mah and full_mah:
            health_pct = max(40, min(100, round((full_mah / design_mah) * 100)))
        elif cycles is not None and cycles > 0:
            health_pct = max(50, min(100, int(100 - (cycles * 0.04))))
        else:
            health_pct = 100

        status_map = {"1": "Unknown", "2": "Charging", "3": "Discharging", "4": "Not Charging", "5": "Full"}
        health_map = {"1": "Unknown", "2": "Good", "3": "Overheat", "4": "Dead", "5": "Over Voltage", "6": "Unspecified Failure", "7": "Cold"}

        watts = round(abs(current_ma) * volt_v / 1000.0, 1) if (current_ma is not None and volt_v > 0) else None

        data["battery"] = {
            "level": int(level.group(1)) if level else "--",
            "temperature_c": round(int(temp.group(1)) / 10.0, 1) if temp else "--",
            "voltage_mv": volt_mv,
            "voltage_v": volt_v,
            "current_ma": current_ma,
            "watts": watts,
            "design_mah": design_mah,
            "full_mah": full_mah,
            "status": status_map.get(status.group(1) if status else "3", "Discharging"),
            "health_status": health_map.get(health.group(1) if health else "2", "Good"),
            "health_pct": health_pct,
            "cycles": cycles if cycles is not None else "N/A",
            "technology": tech.group(1) if tech else "Li-poly"
        }

        # Live RAM parsing
        mem_total_kb = mem_vals.get("MemTotal", 0)
        mem_avail_kb = mem_vals.get("MemAvailable", 0)
        swap_total_kb = mem_vals.get("SwapTotal", 0)
        total_gb = round(mem_total_kb / (1024 * 1024), 2) if mem_total_kb else 0
        avail_gb = round(mem_avail_kb / (1024 * 1024), 2) if mem_avail_kb else 0
        used_gb = round(max(0.0, total_gb - avail_gb), 2)
        used_pct = round((used_gb / total_gb) * 100) if total_gb > 0 else 0
        zram_gb = round(swap_total_kb / (1024 * 1024), 1) if swap_total_kb else 0

        # Physical RAM tier estimation (kernel reserves ~300-700MB)
        ram_tier = "--"
        if total_gb > 0:
            for tier in [2, 3, 4, 6, 8, 12, 16, 24]:
                if total_gb <= tier + 0.35:
                    ram_tier = f"{tier} GB"
                    break

        ram_status = "Healthy"
        if total_gb > 0 and total_gb < 1.8:
            ram_status = "Low / Possible Clone RAM"
        elif used_pct >= 92:
            ram_status = "High Load"

        data["ram"] = {
            "total_gb": round(total_gb, 1) if total_gb else "--",
            "tier": ram_tier,
            "used_gb": used_gb,
            "avail_gb": avail_gb,
            "used_pct": used_pct,
            "zram_gb": zram_gb,
            "status": ram_status
        }

        if not full_audit:
            return {"success": True, "partial": True, "diagnostics": data}

        # --- 2. Deep Anti-Scam, Hardware Authenticity, Warranty & Component Audit ---
        props_cmd = (
            "echo BRAND=$(getprop ro.product.brand); "
            "echo MODEL=$(getprop ro.product.marketname || getprop ro.product.model); "
            "echo REAL_MODEL=$(getprop ro.product.model); "
            "echo CODENAME=$(getprop ro.product.device); "
            "echo SERIAL=$(getprop ro.serialno); "
            "echo ANDROID=$(getprop ro.build.version.release); "
            "echo PATCH=$(getprop ro.build.version.security_patch); "
            "echo BDATE=$(getprop ro.build.date); "
            "echo BUTC=$(getprop ro.build.date.utc); "
            "echo BTAGS=$(getprop ro.build.tags); "
            "echo DBG=$(getprop ro.debuggable); "
            "echo ABI=$(getprop ro.product.cpu.abi); "
            "echo VBOOT=$(getprop ro.boot.verifiedbootstate); "
            "echo FLASHLOCK=$(getprop ro.boot.flash.locked); "
            "echo WARRANTYBIT=$(getprop ro.boot.warranty_bit); "
            "echo BASEBAND=$(getprop gsm.version.baseband); "
            "echo SIMSTATE=$(getprop gsm.sim.state); "
            "echo SOC=$(getprop ro.soc.model || getprop ro.board.platform); "
            "echo STOR=$(getprop ro.boot.storage_type); "
            "echo PANEL=$(getprop ro.boot.panel_name || getprop ro.vendor.panel_name); "
            "echo CMDLINE=$(cat /proc/cmdline 2>/dev/null | tr ' ' '\\n' | grep -i panel | head -n 2); "
            "echo STOR_MOD=$(cat /sys/block/sda/device/model 2>/dev/null || cat /sys/block/mmcblk0/device/name 2>/dev/null); "
            "echo STOR_EOL=$(cat /sys/block/sda/device/life_time_est_a 2>/dev/null || cat /sys/block/mmcblk0/device/life_time 2>/dev/null); "
            "echo CORES=$(nproc 2>/dev/null); "
            "echo SU=$(which su 2>/dev/null); "
            "echo KSU=$(ls -d /data/adb/ksu /data/adb/magisk /data/adb/ap 2>/dev/null | head -n 1); "
            "echo WMSIZE=$(wm size 2>/dev/null | tail -n 1); "
            "echo SOUNDCARDS=$(cat /proc/asound/cards 2>/dev/null | grep -c '\\['); "
            "df -k /data 2>/dev/null | tail -n 1"
        )
        p_res = self.run_cmd([self.adb_path, "-s", serial, "shell", props_cmd], timeout=10)
        p_vals = {}
        df_line = ""
        for line in (p_res.get("stdout", "") or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                p_vals[k.strip()] = v.strip()
            elif "/data" in line or line.strip().startswith("/"):
                df_line = line.strip()

        # Storage capacity & wear
        s_str = p_vals.get("STOR_MOD", "") or p_vals.get("STOR", "")
        storage_type = "UFS High-Speed Flash"
        if "emmc" in s_str.lower() or "mmc" in s_str.lower():
            storage_type = f"eMMC 5.1 ({s_str})"
        elif s_str:
            storage_type = f"UFS Flash ({s_str})"

        data_total_gb = "--"
        data_free_gb = "--"
        data_used_pct = 0
        if df_line:
            parts = df_line.split()
            if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit() and parts[3].isdigit():
                tot_kb = int(parts[1])
                avail_kb = int(parts[3])
                data_total_gb = round(tot_kb / (1024 * 1024), 1)
                data_free_gb = round(avail_kb / (1024 * 1024), 1)
                data_used_pct = round(((tot_kb - avail_kb) / tot_kb) * 100) if tot_kb > 0 else 0

        eol_raw = p_vals.get("STOR_EOL", "")
        wear_status = "Healthy (Normal)"
        if eol_raw:
            try:
                eol_hex = int(eol_raw.split()[0], 16)
                if eol_hex <= 3:
                    wear_status = f"Excellent ({eol_hex * 10}% Wear)"
                elif eol_hex <= 7:
                    wear_status = f"Good ({eol_hex * 10}% Wear)"
                else:
                    wear_status = f"High Wear ({eol_hex * 10}% Used)"
            except Exception:
                wear_status = f"Healthy ({eol_raw[:12]})"

        data["storage"] = {
            "type": storage_type,
            "total_gb": data_total_gb,
            "free_gb": data_free_gb,
            "used_pct": data_used_pct,
            "wear": wear_status
        }

        # Display Panel
        panel_raw = f"{p_vals.get('PANEL', '')} {p_vals.get('CMDLINE', '')}".lower()
        panel_detected = True
        if "samsung" in panel_raw or "ea8076" in panel_raw or "s6e3" in panel_raw:
            panel_vendor = "Samsung Super AMOLED (OEM)"
        elif "csot" in panel_raw or "huaxing" in panel_raw or "tcl" in panel_raw:
            panel_vendor = "CSOT / Huaxing OLED (OEM)"
        elif "tianma" in panel_raw:
            panel_vendor = "Tianma Microelectronics (OEM)"
        elif "boe" in panel_raw:
            panel_vendor = "BOE Technology OLED (OEM)"
        elif "visionox" in panel_raw:
            panel_vendor = "Visionox OLED (OEM)"
        elif "jdi" in panel_raw or "lg" in panel_raw:
            panel_vendor = "LG / JDI OEM Panel"
        else:
            panel_vendor = "OEM / Generic Display"
            panel_detected = False

        wm_res = p_vals.get("WMSIZE", "").replace("Physical size:", "").replace("Override size:", "").strip() or "Auto"
        data["display"] = {
            "vendor": panel_vendor,
            "resolution": wm_res,
            "panel_id_found": panel_detected,
            "details": (p_vals.get("PANEL") or p_vals.get("CMDLINE") or "Direct Hardware Framebuffer")[:80]
        }

        cores = p_vals.get("CORES", "8")
        soc_model = p_vals.get("SOC", "") or "Universal ARM64"
        data["soc"] = {"model": soc_model, "cores": cores, "abi": p_vals.get("ABI", "arm64-v8a")}

        brand = p_vals.get("BRAND", "Android")
        model_name = p_vals.get("MODEL", "") or p_vals.get("REAL_MODEL", "Device")
        codename = p_vals.get("CODENAME", "--")
        dev_serial = p_vals.get("SERIAL", serial)
        baseband = p_vals.get("BASEBAND", "")
        sim_state = p_vals.get("SIMSTATE", "ABSENT")
        b_tags = p_vals.get("BTAGS", "release-keys")
        vboot = p_vals.get("VBOOT", "").lower()
        flash_lock = p_vals.get("FLASHLOCK", "")
        warranty_bit = p_vals.get("WARRANTYBIT", "")
        has_root = bool(p_vals.get("SU") or p_vals.get("KSU"))

        data["identity"] = {
            "brand": brand,
            "model": model_name,
            "codename": codename,
            "serial": dev_serial,
            "android": p_vals.get("ANDROID", "--"),
            "sec_patch": p_vals.get("PATCH", "--"),
            "build_date": p_vals.get("BDATE", "--"),
            "build_tags": b_tags,
            "baseband": baseband if baseband else "Missing / Null!",
            "sim_state": sim_state
        }

        # --- 3. Component HAL Checks (Camera, Bluetooth, Mic/Audio, Wi-Fi, Sensors) ---
        comp_cmd = (
            "echo CAM_N=$(dumpsys media.camera 2>/dev/null | grep -cE 'Device [0-9]+ is|Camera ID:'); "
            "echo CAM_SVC=$(service check media.camera 2>/dev/null); "
            "echo BT_OUT=$(dumpsys bluetooth_manager 2>/dev/null | grep -E 'enabled:|state:|address:' | head -n 4 | tr '\\n' ';'); "
            "echo WIFI_OUT=$(dumpsys wifi 2>/dev/null | grep -E 'Wi-Fi is|mWifiInfo' | head -n 2 | tr '\\n' ';'); "
            "echo MIC_MUTE=$(dumpsys audio 2>/dev/null | grep -i 'Microphone muted' | head -n 1); "
            "echo SENSORS=$(dumpsys sensorservice 2>/dev/null | grep -cE '^[0-9a-fx]+\\)'); "
            "echo FP_FEAT=$(pm list features 2>/dev/null | grep -i fingerprint | head -n 1)"
        )
        c_res = self.run_cmd([self.adb_path, "-s", serial, "shell", comp_cmd], timeout=12)
        c_vals = {}
        for line in (c_res.get("stdout", "") or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                c_vals[k.strip()] = v.strip()

        # Camera status
        cam_cnt = int(c_vals.get("CAM_N", "0")) if c_vals.get("CAM_N", "0").isdigit() else 0
        cam_svc_ok = "found" in c_vals.get("CAM_SVC", "").lower() and "not found" not in c_vals.get("CAM_SVC", "").lower()
        cam_ok = cam_svc_ok or cam_cnt > 0
        cam_label = f"{cam_cnt} Lens / Sensors OK" if cam_cnt > 0 else ("Camera HAL Active" if cam_svc_ok else "Camera Service Issue!")

        # Bluetooth status
        bt_out = c_vals.get("BT_OUT", "")
        bt_enabled = "enabled: true" in bt_out.lower() or "state: on" in bt_out.lower()
        bt_addr_m = re.search(r"address:\s*([0-9a-fA-F:]+)", bt_out)
        bt_addr = bt_addr_m.group(1) if bt_addr_m else ""
        bt_ok = bool(bt_out) and bt_addr != "00:00:00:00:00:00"
        bt_label = f"ON ({bt_addr})" if (bt_enabled and bt_addr) else ("ON — Working" if bt_enabled else ("Adapter OK (Currently OFF)" if bt_ok else "Bluetooth Not Responding"))

        # Mic & Audio Codec
        sound_cards = int(p_vals.get("SOUNDCARDS", "0")) if p_vals.get("SOUNDCARDS", "0").isdigit() else 0
        mic_mute = c_vals.get("MIC_MUTE", "").lower()
        mic_muted = "true" in mic_mute
        audio_ok = sound_cards > 0 or bool(mic_mute)
        audio_label = ("Audio Codec OK (Mic Muted)" if mic_muted else f"Audio & Mic Active ({max(1, sound_cards)} Sound Card)") if audio_ok else "Audio HAL Issue!"

        # Wi-Fi & Cellular Modem / Baseband
        wifi_out = c_vals.get("WIFI_OUT", "").lower()
        wifi_enabled = "wi-fi is enabled" in wifi_out
        baseband_ok = bool(baseband) and "unknown" not in baseband.lower()
        modem_ok = baseband_ok and bool(wifi_out)
        modem_label = f"Modem OK • Wi-Fi {'ON' if wifi_enabled else 'Ready'}" if modem_ok else ("Baseband Null / IMEI Risk!" if not baseband_ok else "Wi-Fi Ready")

        # Sensors & Fingerprint
        sensor_cnt = int(c_vals.get("SENSORS", "0")) if c_vals.get("SENSORS", "0").isdigit() else 0
        has_fp = "fingerprint" in c_vals.get("FP_FEAT", "").lower()
        sensors_ok = sensor_cnt >= 4
        sensors_label = f"{sensor_cnt} Sensors" + (" + Fingerprint OK" if has_fp else " Active") if sensor_cnt > 0 else "Sensor HAL Active"

        data["components"] = {
            "camera": {"ok": cam_ok, "label": cam_label},
            "bluetooth": {"ok": bt_ok, "label": bt_label},
            "audio_mic": {"ok": audio_ok, "label": audio_label},
            "modem_wifi": {"ok": modem_ok, "label": modem_label},
            "sensors": {"ok": sensors_ok, "label": sensors_label},
            "display_hw": {"ok": True, "label": f"{panel_vendor.split('(')[0].strip()} ({wm_res})"}
        }

        # --- 4. Authenticity & Anti-Scam Verdict ---
        warnings = []
        is_unlocked = (vboot in ("orange", "yellow", "red")) or (flash_lock == "0")
        if is_unlocked:
            warnings.append("Bootloader is Unlocked")
        if warranty_bit == "1":
            warnings.append("Knox / Warranty Bit Tripped (0x1)")
        if has_root:
            warnings.append("Root Binaries Detected (su / Magisk / KSU)")
        if "release-keys" not in b_tags:
            warnings.append(f"Unofficial Build Keys ({b_tags})")
        if not baseband_ok:
            warnings.append("Baseband / Modem Missing (IMEI Risk)")
        if data["ram"]["status"].startswith("Low"):
            warnings.append("Unusually Low Physical RAM (Possible Fake Clone)")
        if p_vals.get("ABI", "arm64") == "armeabi-v7a" and total_gb >= 4:
            warnings.append("32-bit OS on High Spec Claim (Clone Indicator)")

        if len(warnings) == 0:
            auth_status = "ORIGINAL_GENUINE"
            auth_title = "✅ Genuine Stock Hardware & Locked Bootloader"
            auth_desc = "Verified Boot (Green), Official release-keys, valid Baseband/Modem, and all hardware HALs healthy."
        elif not baseband_ok or "release-keys" not in b_tags or data["ram"]["status"].startswith("Low"):
            auth_status = "HIGH_RISK"
            auth_title = "🚨 High Risk / Tampered or Unofficial Firmware"
            auth_desc = " • ".join(warnings)
        else:
            auth_status = "TAMPERED_MODIFIED"
            auth_title = "⚠️ Bootloader Unlocked / Modified Software"
            auth_desc = " • ".join(warnings)

        data["authenticity"] = {
            "status": auth_status,
            "title": auth_title,
            "desc": auth_desc,
            "bootloader": "Unlocked" if is_unlocked else ("Locked (Official)" if flash_lock == "1" or vboot == "green" else "Unknown"),
            "verified_boot": vboot.upper() if vboot else "UNKNOWN",
            "rooted": "Yes (Rooted)" if has_root else "No (Clean)",
            "warnings": warnings
        }

        # --- 5. Warranty Estimation + Official Brand Portal ---
        brand_low = brand.lower()
        warranty_urls = {
            "xiaomi": "https://www.mi.com/global/verify/#/en/tab/imei",
            "redmi": "https://www.mi.com/global/verify/#/en/tab/imei",
            "poco": "https://www.mi.com/global/verify/#/en/tab/imei",
            "samsung": "https://www.samsung.com/in/support/warranty/",
            "oneplus": "https://service.oneplus.com/in/warranty-check",
            "realme": "https://www.realme.com/in/support/phonecheck",
            "vivo": "https://www.vivo.com/in/support/IMEI",
            "iqoo": "https://www.iqoo.com/in/support/IMEI",
            "oppo": "https://support.oppo.com/in/warranty-check/",
            "motorola": "https://motorola-global-portal.custhelp.com/app/mcp/trackrepair2",
            "google": "https://store.google.com/repair",
            "nothing": "https://in.nothing.tech/pages/imei"
        }
        portal_url = next((u for k, u in warranty_urls.items() if k in brand_low), "https://www.imei.info/")

        # Estimate age from firmware UTC & battery cycles
        age_months = None
        try:
            b_utc = int(p_vals.get("BUTC", "0"))
            if b_utc > 1500000000:
                age_months = max(0, int((time.time() - b_utc) / (30.4 * 86400)))
        except Exception:
            pass

        if warranty_bit == "1" or is_unlocked:
            w_status = "VOID (Bootloader / Knox Tripped)"
            w_state = "void"
            w_note = "Hardware warranty is usually voided by OEM when bootloader is unlocked or Knox is tripped."
        elif (isinstance(cycles, int) and cycles > 380) or (age_months is not None and age_months > 14):
            w_status = "Likely Expired (>1 Year Estimated)"
            w_state = "expired"
            w_note = f"Estimated from device telemetry ({cycles if isinstance(cycles, int) else '?'} charge cycles). Verify exact purchase date on OEM portal."
        else:
            w_status = "Likely Eligible / Under Warranty Window"
            w_state = "eligible"
            w_note = "Bootloader locked & clean. Note: Exact warranty expiry requires official OEM server check with IMEI/Invoice."

        data["warranty"] = {
            "status": w_status,
            "state": w_state,
            "note": w_note,
            "portal_url": portal_url,
            "age_months_est": age_months
        }

        return {"success": True, "partial": False, "diagnostics": data}

    def trigger_hardware_test(self, serial: str, test_type: str) -> Dict[str, Any]:
        """Triggers real physical hardware tests on the connected Android phone."""
        try:
            if test_type == "vibrate":
                self.run_cmd([self.adb_path, "-s", serial, "shell", "cmd vibrator vibrate 450 || cmd vibrator_manager synced oneshot 450"], timeout=5)
                return {"success": True, "message": "Sent 450ms vibration pulse! Check if the phone vibrated."}
            elif test_type == "cit_menu":
                # Try Xiaomi CIT hardware test menu or generic Service Menu
                r = self.run_cmd([self.adb_path, "-s", serial, "shell", "am start -n com.miui.cit/.CitLauncherActivity"], timeout=6)
                out = (r.get("stdout", "") + r.get("stderr", "")).lower()
                if "error" not in out and "exception" not in out:
                    return {"success": True, "message": "Launched Factory CIT Hardware Self-Test Menu on phone screen!"}
                return {"success": False, "error": "CIT menu is Xiaomi/POCO/Redmi specific. Dial *#*#6484#*#* or *#0*# (Samsung) on your phone."}
            elif test_type == "beep":
                # Play notification / test tone via media volume or ringtone preview
                self.run_cmd([self.adb_path, "-s", serial, "shell", "cmd media_session volume --stream 3 --set 10 && input keyevent 24"], timeout=5)
                return {"success": True, "message": "Triggered Volume/Audio key check on phone."}
            return {"success": False, "error": f"Unknown test: {test_type}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # 📺 FEATURE 6: IN-APP SCREEN MIRRORING & RECORDING (SCRCPY INTEGRATION)
    # =========================================================================
    def stop_screen_mirror(self) -> Dict[str, Any]:
        """Terminate the tracked scrcpy process and remove its stderr log."""
        proc = getattr(self, "_scrcpy_proc", None)
        stopped = False
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                stopped = True
            except Exception:
                try: proc.kill()
                except Exception: pass
        self._scrcpy_proc = None
        log_path = getattr(self, "_scrcpy_err_log", None)
        if log_path:
            try: os.remove(log_path)
            except Exception: pass
            self._scrcpy_err_log = None
        return {"success": True, "stopped": stopped}

    @device_action_locked
    def start_screen_mirror(self, serial: str, max_fps: int = 60, bitrate: str = "8M", progress_cb=None) -> Dict[str, Any]:
        """
        Launches Scrcpy screen mirror in a high-performance detached window:
        - Auto-downloads portable Scrcpy with live progress if missing
        - Uses --video-bit-rate (fixes short -b= parse error)
        - Verifies process stays alive for 0.8s so startup errors are caught
        """
        def _cb(msg, pct=None):
            if progress_cb:
                try: progress_cb(msg, pct)
                except Exception: pass

        if max_fps not in (30, 60, 90) or str(bitrate) not in ("4M", "8M", "16M"):
            return {"success": False, "error": "Invalid mirror quality settings."}
        adb_err = self._require_adb_device(serial)
        if adb_err:
            return {"success": False, "error": adb_err}

        # Stop any previous mirror process instead of spawning parallel windows.
        self.stop_screen_mirror()
        prev_log = getattr(self, "_scrcpy_err_log", None)
        if prev_log:
            try: os.remove(prev_log)
            except Exception: pass
            self._scrcpy_err_log = None

        scrcpy_candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "scrcpy", "scrcpy.exe"),
            os.path.join(get_storage_dir("Tools"), "scrcpy", "scrcpy.exe"),
            r"C:\scrcpy\scrcpy.exe",
            shutil.which("scrcpy.exe") or ""
        ]
        scrcpy_bin = next((c for c in scrcpy_candidates if c and os.path.exists(c)), None)

        if not scrcpy_bin:
            try:
                _cb("Fetching latest Scrcpy release from GitHub...", 5)
                tools_scrcpy_dir = os.path.join(get_storage_dir("Tools"), "scrcpy")
                os.makedirs(tools_scrcpy_dir, exist_ok=True)
                req = urllib.request.Request(
                    "https://api.github.com/repos/Genymobile/scrcpy/releases/latest",
                    headers={"User-Agent": "ROM-Flasher-Tool"}
                )
                with urllib.request.urlopen(req, timeout=15) as r:
                    rel = json.loads(r.read().decode("utf-8"))
                win_asset = next(
                    (a for a in rel.get("assets", []) if "win64" in a.get("name", "").lower() and a.get("name", "").endswith(".zip")),
                    None
                )
                if win_asset:
                    total_sz = int(win_asset.get("size") or 0)
                    zip_path = os.path.join(tempfile.gettempdir(), f"scrcpy_portable_{os.getpid()}_{int(time.time() * 1000)}.zip")
                    try:
                        dl_req = urllib.request.Request(win_asset["browser_download_url"], headers={"User-Agent": "ROM-Flasher-Tool"})
                        downloaded = 0
                        with urllib.request.urlopen(dl_req, timeout=90) as resp, open(zip_path, "wb") as out_f:
                            if not total_sz:
                                total_sz = int(resp.headers.get("Content-Length") or 0)
                            while True:
                                chunk = resp.read(65536)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                                downloaded += len(chunk)
                                if total_sz > 0:
                                    pct = min(85, int((downloaded / total_sz) * 80) + 5)
                                    mb_done = downloaded / (1024 * 1024)
                                    mb_tot = total_sz / (1024 * 1024)
                                    _cb(f"Downloading Scrcpy ({mb_done:.1f} / {mb_tot:.1f} MB)...", pct)
                        _cb("Extracting Scrcpy portable engine...", 90)
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            for member in zf.infolist():
                                if member.is_dir():
                                    continue
                                base_name = os.path.basename(member.filename)
                                if base_name:
                                    target_path = os.path.join(tools_scrcpy_dir, base_name)
                                    with zf.open(member) as src, open(target_path, "wb") as dst:
                                        shutil.copyfileobj(src, dst)
                    finally:
                        # A corrupt download or extraction error must not leave the
                        # temporary ZIP behind on every retry.
                        try:
                            os.remove(zip_path)
                        except Exception:
                            pass
                    candidate = os.path.join(tools_scrcpy_dir, "scrcpy.exe")
                    if os.path.exists(candidate):
                        scrcpy_bin = candidate
            except Exception as dl_err:
                return {
                    "success": False,
                    "error": f"Scrcpy auto-download failed ({dl_err}). Download manually from GitHub.",
                    "download_url": "https://github.com/Genymobile/scrcpy/releases"
                }

        if not scrcpy_bin:
            return {
                "success": False,
                "error": "Scrcpy binary not found and auto-download could not locate win64 asset.",
                "download_url": "https://github.com/Genymobile/scrcpy/releases"
            }

        try:
            _cb(f"Launching Screen Mirror ({max_fps} FPS, {bitrate})...", 96)
            cmd = [
                scrcpy_bin,
                "-s", serial,
                f"--max-fps={max_fps}",
                f"--video-bit-rate={bitrate}",
                "--stay-awake",
                f"--window-title=ROM Flasher Tool — Screen Mirror ({serial})"
            ]
            env = os.environ.copy()
            adb_bin = self.adb_path if os.path.isfile(self.adb_path) else (shutil.which("adb") or "")
            if not adb_bin:
                return {"success": False, "error": "ADB executable not found; cannot start screen mirror."}
            env["ADB"] = os.path.abspath(adb_bin)
            creation = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            err_log_path = os.path.join(tempfile.gettempdir(), f"scrcpy_err_{os.getpid()}_{int(time.time() * 1000)}.log")
            with open(err_log_path, "w", encoding="utf-8", errors="ignore") as err_f:
                proc = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(scrcpy_bin),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=err_f,
                    creationflags=creation
                )
            self._scrcpy_err_log = err_log_path
            self._scrcpy_proc = proc

            def _cleanup_after_exit():
                try:
                    proc.wait()
                finally:
                    try: os.remove(err_log_path)
                    except Exception: pass
                    if getattr(self, "_scrcpy_proc", None) is proc:
                        self._scrcpy_proc = None
                    if getattr(self, "_scrcpy_err_log", None) == err_log_path:
                        self._scrcpy_err_log = None

            threading.Thread(target=_cleanup_after_exit, daemon=True).start()

            time.sleep(0.9)
            if proc.poll() is not None:
                err_txt = ""
                try:
                    with open(err_log_path, "r", encoding="utf-8", errors="ignore") as ef:
                        err_txt = ef.read().strip()
                    os.remove(err_log_path)
                except Exception:
                    pass
                if getattr(self, "_scrcpy_err_log", None) == err_log_path:
                    self._scrcpy_err_log = None
                return {"success": False, "error": err_txt or f"Scrcpy exited immediately (code {proc.returncode})."}
            _cb(f"Screen Mirror active at {max_fps} FPS!", 100)
            return {"success": True, "message": f"Screen Mirroring launched at {max_fps} FPS!"}
        except Exception as e:
            log_path = getattr(self, "_scrcpy_err_log", None)
            if log_path:
                try: os.remove(log_path)
                except Exception: pass
                self._scrcpy_err_log = None
            return {"success": False, "error": str(e)}

    @device_action_locked
    def capture_screen_recording(self, serial: str, duration: int = 15) -> Dict[str, Any]:
        """Records the exact selected device and verifies every ADB step before reporting success."""
        try:
            limit = int(duration)
        except (TypeError, ValueError):
            return {"success": False, "error": "Invalid recording duration."}
        if limit < 5 or limit > 180:
            return {"success": False, "error": "Recording duration must be between 5 and 180 seconds."}
        adb_err = self._require_adb_device(serial)
        if adb_err:
            return {"success": False, "error": adb_err}

        out_folder = get_storage_dir("Screen_Recordings")
        os.makedirs(out_folder, exist_ok=True)
        safe_serial = re.sub(r'[^a-zA-Z0-9._-]', '_', serial or 'device')
        run_tag = f"{os.getpid()}_{int(time.time() * 1000)}"
        local_file = os.path.join(out_folder, f"rec_{safe_serial}_{run_tag}.mp4")
        remote_file = f"/sdcard/flasher_rec_{run_tag}.mp4"

        try:
            self.run_cmd([self.adb_path, "-s", serial, "shell", f"rm -f {remote_file}"], timeout=10)
            rec = self.run_cmd(
                [self.adb_path, "-s", serial, "shell", f"screenrecord --time-limit {limit} {remote_file}"],
                timeout=limit + 20,
            )
            if not adb_result_ok(rec):
                return {"success": False, "error": f"screenrecord failed: {rec.get('output', '')[:300]}"}
            pull = self.run_cmd([self.adb_path, "-s", serial, "pull", remote_file, local_file], timeout=max(90, limit + 45))
            if not adb_result_ok(pull):
                return {"success": False, "error": f"Could not download recording: {pull.get('output', '')[:300]}"}
            if not os.path.isfile(local_file):
                return {"success": False, "error": "Recording file was not created."}
            size = os.path.getsize(local_file)
            if size < 1024:
                return {"success": False, "error": "Recording file is empty or too small."}
            with open(local_file, "rb") as fh:
                header = fh.read(12)
            if b"ftyp" not in header:
                return {"success": False, "error": "Downloaded file is not a valid MP4 recording."}
            return {
                "success": True,
                "file": local_file,
                "size_mb": round(size / (1024 * 1024), 2),
                "message": f"Screen recording saved ({round(size/(1024*1024),2)} MB) to: {local_file}",
            }
        finally:
            self.run_cmd([self.adb_path, "-s", serial, "shell", f"rm -f {remote_file}"], timeout=10)

    # =========================================================================
    # 💀 FEATURE 9: QUALCOMM 9008 EDL & MEDIATEK BROM EMERGENCY UNBRICKING STUDIO
    # =========================================================================
    def detect_emergency_com_ports(self) -> Dict[str, Any]:
        """
        Scans Windows Device Manager for Emergency COM Ports:
        - Qualcomm HS-USB QDLoader 9008 (VID_05C6&PID_9008)
        - Qualcomm HS-USB Diagnostics (900E / 9006)
        - MediaTek USB Port / Preloader / DA (VID_0E8D&PID_0003, PID_2000)
        """
        detected_ports = []
        is_edl = False
        is_brom = False
        scan_error = None

        if sys.platform == "win32":
            try:
                ps_cmd = 'Get-PnpDevice -Class "Ports" -PresentOnly -ErrorAction SilentlyContinue | Select-Object -Property FriendlyName, InstanceId, Status | ConvertTo-Json'
                res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
                if res.stdout.strip():
                    data = json.loads(res.stdout)
                    if isinstance(data, dict):
                        data = [data]
                    for item in data:
                        name = item.get("FriendlyName", "")
                        inst = item.get("InstanceId", "")
                        p_status = item.get("Status", "OK")
                        upper = f"{name} {inst}".upper()
                        m_com = re.search(r"\((COM\d+)\)", name, re.IGNORECASE)
                        com_port = m_com.group(1).upper() if m_com else ""
                        if re.search(r'VID_05C6(?:&|$).*PID_9008(?:&|$)', upper):
                            is_edl = True
                            detected_ports.append({"type": "Qualcomm 9008 EDL", "name": f"{name} [{p_status}]", "com_port": com_port, "id": inst, "status": "READY_FOR_UNBRICK" if p_status == "OK" else f"DRIVER_ISSUE ({p_status})"})
                        elif re.search(r'VID_0E8D(?:&|$)', upper):
                            is_brom = True
                            detected_ports.append({"type": "MediaTek BROM / Preloader", "name": f"{name} [{p_status}]", "com_port": com_port, "id": inst, "status": "READY_FOR_UNBRICK" if p_status == "OK" else f"DRIVER_ISSUE ({p_status})"})
                        elif "COM" in name:
                            detected_ports.append({"type": "Serial COM Port", "name": f"{name} [{p_status}]", "com_port": com_port, "id": inst, "status": p_status})
            except Exception as e:
                scan_error = str(e)
                print(f"Error querying COM ports: {e}")

        status_text = "No Emergency Port"
        if is_edl:
            status_text = "💀 Qualcomm 9008 EDL Detected!"
        elif is_brom:
            status_text = "⚡ MediaTek BROM / Preloader Detected!"

        return {
            "success": scan_error is None,
            "error": scan_error,
            "is_edl": is_edl,
            "is_brom": is_brom,
            "status": status_text,
            "ports": detected_ports
        }

    @device_action_locked
    def force_reboot_edl(self, serial: str) -> Dict[str, Any]:
        """Forces the exact selected device into EDL, then verifies a 9008 port appeared."""
        logs = [f"Attempting Emergency EDL Reboot for: {serial}"]
        dev = self._find_device_exact(self.detect_devices(bypass_cache=True), serial)
        if not dev or str(dev.get("mode", "")).upper() not in ("ADB", "FASTBOOT"):
            return {"success": False, "error": self._device_not_found_error(serial, "ADB or FASTBOOT"), "logs": logs}

        def _sent(res, label):
            out = f"{res.get('stdout', '')}\n{res.get('stderr', '')}".upper()
            return adb_result_ok(res) or "OKAY" in out or label.lower() in out

        attempts = [
            ([self.adb_path, "-s", serial, "reboot", "edl"], "ADB reboot edl"),
            ([self.fastboot_path, "-s", serial, "oem", "edl"], "Fastboot OEM edl"),
            ([self.fastboot_path, "-s", serial, "reboot-edl"], "Fastboot reboot-edl"),
            ([self.fastboot_path, "-s", serial, "reboot", "edl"], "Fastboot reboot edl"),
        ]
        command_sent = None
        for cmd, label in attempts:
            res = self.run_cmd(cmd, timeout=10)
            logs.append(f"{label}: {res.get('output', '')}".strip())
            if _sent(res, label):
                command_sent = label
                break
        if not command_sent:
            return {
                "success": False,
                "error": "EDL reboot rejected by bootloader. Device requires hardware EDL Test Points or Deep Flash Cable.",
                "logs": logs,
            }

        for _ in range(8):
            time.sleep(1.5)
            ports_res = self.detect_emergency_com_ports()
            if ports_res.get("is_edl"):
                logs.append(f"Verified EDL port: {ports_res.get('status')}")
                return {"success": True, "message": f"EDL reboot verified via {command_sent}", "logs": logs}
        return {"success": False, "error": "EDL command was sent but no Qualcomm 9008 port appeared. Use test points.", "logs": logs}

    def inspect_unbrick_rom(self, rom_folder: str) -> Dict[str, Any]:
        """Auto-scans a Factory/Unbrick ROM folder for Qualcomm EDL Firehose (rawprogram/patch/elf) or MediaTek BROM (scatter/DA/auth)."""
        if not rom_folder or not os.path.exists(rom_folder):
            return {"success": False, "error": "ROM folder not found."}

        firehoses, rawprograms, patches, digests = [], [], [], []
        scatters, da_files, auth_files = [], [], []
        img_count = 0
        images_dir = rom_folder

        for root, dirs, files in os.walk(rom_folder):
            depth = os.path.relpath(root, rom_folder).count(os.sep)
            if depth > 3:
                continue
            for f in files:
                fl = f.lower()
                fp = os.path.join(root, f)
                if fl.endswith((".img", ".bin", ".mbn", ".elf")):
                    img_count += 1
                if ("firehose" in fl or fl.startswith("prog_")) and fl.endswith((".elf", ".mbn", ".bin")):
                    firehoses.append(fp)
                    images_dir = root
                elif fl.startswith("rawprogram") and fl.endswith(".xml"):
                    rawprograms.append(fp)
                    images_dir = root
                elif fl.startswith("patch") and fl.endswith(".xml"):
                    patches.append(fp)
                elif fl.endswith((".sig", ".auth")) or "digest" in fl:
                    if fl.endswith(".auth") or "auth_sv5" in fl:
                        auth_files.append(fp)
                    else:
                        digests.append(fp)
                elif "scatter" in fl and fl.endswith(".txt"):
                    scatters.append(fp)
                    images_dir = root
                elif ("_da" in fl or "allinone_da" in fl or fl.startswith("da_")) and fl.endswith(".bin"):
                    da_files.append(fp)

        mode = "UNKNOWN"
        if rawprograms or firehoses:
            mode = "QUALCOMM_EDL"
        elif scatters or da_files:
            mode = "MEDIATEK_BROM"

        return {
            "success": mode != "UNKNOWN",
            "mode": mode,
            "rom_folder": rom_folder,
            "images_dir": images_dir,
            "firehose": firehoses[0] if firehoses else None,
            "rawprograms": sorted(rawprograms),
            "patches": sorted(patches),
            "scatter": scatters[0] if scatters else None,
            "da_file": da_files[0] if da_files else None,
            "auth_file": auth_files[0] if auth_files else (digests[0] if digests else None),
            "image_count": img_count,
            "error": None if mode != "UNKNOWN" else "No Qualcomm Firehose (rawprogram*.xml / prog_*.elf) or MediaTek Scatter (*scatter*.txt) found in folder."
        }

    @staticmethod
    def _unbrick_file_error(path: Optional[str], label: str, extensions: tuple) -> Optional[str]:
        if path in (None, ""):
            return None
        if not isinstance(path, str) or "\x00" in path or len(path) > 4096 or not os.path.isfile(path):
            return f"{label} is not a valid file."
        if not path.lower().endswith(extensions):
            return f"{label} has an unsupported extension; expected {', '.join(extensions)}."
        if os.path.getsize(path) < 1024:
            return f"{label} is too small to be a valid firmware file."
        return None

    @device_action_locked
    def flash_unbrick_rom(self, rom_folder: str, custom_loader: Optional[str] = None, custom_auth: Optional[str] = None, com_port: Optional[str] = None, port_id: Optional[str] = None, mem_type: Optional[str] = None, progress_cb=None) -> Dict[str, Any]:
        """Executes Factory EDL 9008 (Qualcomm Firehose) or MTK BROM unbrick flashing using detected ROM package + COM port."""
        def _cb(msg, pct=None):
            if progress_cb:
                try: progress_cb(msg, pct)
                except Exception: pass

        def _mem_from_xml(xml_paths) -> Optional[str]:
            """Read rawprogram/patch XML contents (bounded); never infer from folder names."""
            found = set()
            for xp in list(xml_paths or [])[:32]:
                try:
                    if os.path.getsize(xp) > 4 * 1024 * 1024:
                        continue
                    with open(xp, "r", encoding="utf-8", errors="ignore") as xf:
                        head = xf.read(256 * 1024)
                except Exception:
                    continue
                for m in re.finditer(r"memory_name\s*=\s*['\"](emmc|ufs)['\"]", head, re.I):
                    found.add(m.group(1).lower())
            return next(iter(found)) if len(found) == 1 else None

        logs = [f"Initializing Factory Unbrick Flasher on: {rom_folder}"]
        _cb("Scanning Factory ROM package...", 5)
        info = self.inspect_unbrick_rom(rom_folder)
        if not info.get("success"):
            return {"success": False, "error": info.get("error"), "logs": logs}

        mode = info["mode"]
        # A firehose alone is not a flashable package: it would produce an empty
        # --sendxml and could still be reported as "Unbrick Completed".
        if mode == "QUALCOMM_EDL" and not info.get("rawprograms"):
            err = "No rawprogram*.xml found in the ROM folder; refusing to run an empty EDL flash."
            logs.append(f"❌ {err}")
            _cb(f"❌ {err}", 0)
            return {"success": False, "error": err, "logs": logs}
        loader = custom_loader.strip() if isinstance(custom_loader, str) and custom_loader.strip() else (info["firehose"] if mode == "QUALCOMM_EDL" else info["da_file"])
        auth = custom_auth.strip() if isinstance(custom_auth, str) and custom_auth.strip() else info.get("auth_file")
        if mode == "QUALCOMM_EDL" and auth:
            if custom_auth and str(custom_auth).strip():
                return {
                    "success": False,
                    "error": "The selected Qualcomm auth/signature file cannot be passed by the bundled EDL flashers. "
                             "Place the firehose/auth pair in Unbrick_Tools using your flasher's documented name, "
                             "or use a reviewed edl.py with auth support. Refusing to ignore the selected file.",
                    "logs": logs,
                }
            logs.append("⚠️ ROM-folder auth/signature file is not consumed by the bundled Qualcomm flasher; using the firehose loader only.")
        images_dir = info["images_dir"]

        if mem_type is not None and str(mem_type).lower() not in ("emmc", "ufs"):
            return {"success": False, "error": "Invalid memory type. Choose eMMC or UFS.", "logs": logs}
        expected_loader_ext = (".elf", ".mbn", ".bin") if mode == "QUALCOMM_EDL" else (".bin",)
        for label, path, exts in (("Firehose/DA loader", loader, expected_loader_ext), ("Auth/signature file", auth, (".auth", ".sig", ".mbn", ".bin"))):
            err = self._unbrick_file_error(path, label, exts)
            if err:
                return {"success": False, "error": err, "logs": logs}
        for xml in list(info.get("rawprograms", [])) + list(info.get("patches", [])):
            name = os.path.basename(xml)
            if "," in name or "\n" in name:
                return {"success": False, "error": f"Unsafe XML filename for fh_loader: {name}", "logs": logs}
        if not os.path.isdir(images_dir):
            return {"success": False, "error": "ROM image directory was not found.", "logs": logs}

        _cb(f"Detected [{mode}] package. Scanning Emergency COM ports...", 12)
        ports_res = self.detect_emergency_com_ports()
        if not ports_res.get("success"):
            return {"success": False, "error": f"Emergency COM port scan failed: {ports_res.get('error')}", "logs": logs}
        ports = ports_res.get("ports", [])
        want_type = "Qualcomm 9008 EDL" if mode == "QUALCOMM_EDL" else "MediaTek BROM / Preloader"
        candidates = [p for p in ports if p.get("type") == want_type and str(p.get("status", "")).startswith("READY_FOR_UNBRICK")]
        if com_port or port_id:
            candidates = [p for p in candidates
                          if (not com_port or str(p.get("com_port", "")).upper() == str(com_port).upper())
                          and (not port_id or str(p.get("id", "")) == str(port_id))]
        if len(candidates) != 1:
            err = ("Select exactly one healthy emergency COM port before flashing. "
                   f"Found {len(candidates)} matching port(s); explicit port selection is required.")
            logs.append(f"❌ {err}")
            _cb(f"❌ {err}", 0)
            return {"success": False, "error": err, "logs": logs}
        target_port = candidates[0]
        logs.append(f"Target emergency port: {target_port.get('com_port')} ({target_port.get('id')})")

        tools_dir = get_storage_dir("Unbrick_Tools")
        os.makedirs(tools_dir, exist_ok=True)

        if mode == "QUALCOMM_EDL":
            edl_port = target_port
            if not edl_port.get("com_port"):
                err = "The selected Qualcomm 9008 port has no COM number. Reinstall the QDLoader driver and retry."
                logs.append(f"❌ {err}")
                _cb(f"❌ {err}", 0)
                return {"success": False, "error": err, "logs": logs}

            com_dev = f"\\\\.\\{edl_port['com_port']}"
            if not loader:
                err = "Firehose programmer (.elf / .mbn) not found in ROM folder. Please select custom Firehose loader."
                logs.append(f"❌ {err}")
                return {"success": False, "error": err, "logs": logs}

            # Locate QSaharaServer.exe + fh_loader.exe OR edl.py
            qsahara = self._find_unbrick_bin("QSaharaServer.exe", tools_dir)
            fh_loader = self._find_unbrick_bin("fh_loader.exe", tools_dir)
            edl_py = self._find_unbrick_bin("edl.py", tools_dir)

            if qsahara and fh_loader:
                _cb(f"Uploading Firehose programmer via QSaharaServer ({edl_port['com_port']})...", 25)
                s_res = self.run_cmd([qsahara, "-p", com_dev, "-s", f"13:{loader}"], timeout=45)
                logs.append(s_res.get("output", ""))
                sahara_out = (s_res.get("output", "") or "")
                sahara_ok = s_res.get("success") and not re.search(r"fail|error|could not", sahara_out, re.I)
                if not sahara_ok:
                    return {"success": False, "error": f"QSaharaServer handshake failed: {sahara_out[:400]}", "logs": logs}

                raw_csv = ",".join(os.path.basename(x) for x in info["rawprograms"])
                patch_csv = ",".join(os.path.basename(x) for x in info["patches"])
                xml_arg = f"{raw_csv},{patch_csv}".strip(",")
                _cb(f"Flashing XML partitions ({xml_arg}) via fh_loader...", 50)
                detected_mem = _mem_from_xml(list(info.get("rawprograms", [])) + list(info.get("patches", [])))
                chosen_mem = str(mem_type or detected_mem or "").lower()
                if chosen_mem not in ("emmc", "ufs"):
                    return {"success": False, "error": "Memory type (eMMC/UFS) is ambiguous; select it explicitly before flashing.", "logs": logs}
                fh_cmd = [
                    fh_loader, f"--port={com_dev}", f"--sendxml={xml_arg}",
                    f"--search_path={images_dir}", "--noprompt", "--showpercentagecomplete",
                    "--zlpawarehost=1", f"--memoryname={chosen_mem}", "--reset"
                ]
                f_res = self.run_cmd(fh_cmd, timeout=600)
                logs.append(f_res.get("output", ""))
                fh_out = f_res.get("output", "") or ""
                ok = bool(f_res.get("success")
                          and "all finished successfully" in fh_out.lower()
                          and not re.search(r"\bfailed\b|\berror\b|could not", fh_out, re.I))
                _cb("🎉 Qualcomm EDL Unbrick Completed!" if ok else "❌ fh_loader failed!", 100 if ok else 0)
                return {"success": ok, "logs": logs, "error": None if ok else "fh_loader reported an incomplete/failed flash. Check loader/auth signature."}

            # Auto-cloning and executing third-party EDL code is intentionally disabled.
            if edl_py:
                py_exe = self._find_python_exe()
                if not py_exe:
                    return {"success": False, "error": "Python 3 interpreter not found for running the locally installed edl.py.", "logs": logs}
                raw_csv = ",".join(info["rawprograms"])
                patch_csv = ",".join(info["patches"])
                _cb(f"Running Qualcomm EDL Firehose flash on {edl_port['com_port']}...", 45)
                cmd = [py_exe, edl_py, "qfil", raw_csv, patch_csv, images_dir, f"--loader={loader}"]
                res = self.run_cmd(cmd, timeout=600)
                logs.append(res.get("output", ""))
                edl_out = res.get("output", "") or ""
                ok = bool(res.get("success") and not re.search(r"failed|error|could not", edl_out, re.I))
                _cb("🎉 Qualcomm EDL Unbrick Completed!" if ok else "❌ EDL Flash Failed!", 100 if ok else 0)
                return {"success": ok, "logs": logs, "error": None if ok else "EDL flash failed (ensure pyusb/libusb driver & valid Firehose/Auth)."}

            return {
                "success": False,
                "error": f"No verified EDL flasher found in {tools_dir}. Place trusted QSaharaServer.exe + fh_loader.exe (or a reviewed edl.py) there manually.",
                "logs": logs
            }

        else:
            # MEDIATEK_BROM
            brom_port = target_port
            if not brom_port.get("com_port"):
                err = "The selected MediaTek BROM port has no COM number. Reinstall the MTK USB/Preloader driver and retry."
                logs.append(f"❌ {err}")
                _cb(f"❌ {err}", 0)
                return {"success": False, "error": err, "logs": logs}

            sp_flash = self._find_unbrick_bin("flash_tool.exe", tools_dir)
            if sp_flash and info.get("scatter"):
                _cb("Flashing MediaTek Scatter ROM via SP Flash Tool CLI...", 45)
                cmd = [sp_flash, "-s", info["scatter"], "-c", "download"]
                if loader:
                    cmd.extend(["-d", loader])
                if auth:
                    cmd.extend(["-a", auth])
                res = self.run_cmd(cmd, timeout=600)
                logs.append(res.get("output", ""))
                sp_out = res.get("output", "") or ""
                ok = bool(res.get("success") and not re.search(r"failed|error|could not", sp_out, re.I))
                _cb("🎉 MediaTek BROM Unbrick Completed!" if ok else "❌ SP Flash Tool failed!", 100 if ok else 0)
                return {"success": ok, "logs": logs, "error": None if ok else "MediaTek SP Flash reported an incomplete/failed flash."}

            # Auto-cloning and executing third-party BROM code is intentionally disabled.
            mtk_py = self._find_unbrick_bin("mtk.py", tools_dir)
            if mtk_py:
                py_exe = self._find_python_exe()
                if not py_exe:
                    return {"success": False, "error": "Python 3 interpreter not found for running the locally installed mtk.py.", "logs": logs}
                _cb("Running MediaTek BROM partition flash (mtkclient)...", 45)
                cmd = [py_exe, mtk_py, "wl", images_dir]
                if loader:
                    cmd.extend(["--loader", loader])
                if auth:
                    cmd.extend(["--auth", auth])
                res = self.run_cmd(cmd, timeout=600)
                logs.append(res.get("output", ""))
                mtk_out = res.get("output", "") or ""
                ok = bool(res.get("success") and not re.search(r"failed|error|could not", mtk_out, re.I))
                _cb("🎉 MediaTek BROM Unbrick Completed!" if ok else "❌ MTK BROM Flash failed!", 100 if ok else 0)
                return {"success": ok, "logs": logs, "error": None if ok else "MTK BROM flash reported an incomplete/failed flash."}

            return {
                "success": False,
                "error": f"No verified MTK flasher found in {tools_dir}. Place a trusted flash_tool.exe or reviewed mtkclient there manually.",
                "logs": logs
            }

    def _find_unbrick_bin(self, filename: str, tools_dir: str) -> Optional[str]:
        search_roots = [
            tools_dir,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"),
            r"C:\XiaoMi\XiaoMiFlash\Source\ThirdParty\Qualcomm\fh_loader",
        ]
        for sr in search_roots:
            if not os.path.exists(sr):
                continue
            for r, _, files in os.walk(sr):
                if filename in files:
                    return os.path.join(r, filename)
        return None

    def _find_git_exe(self) -> Optional[str]:
        cand = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "git", "cmd", "git.exe")
        if os.path.exists(cand):
            return cand
        return shutil.which("git")

    def _find_python_exe(self) -> Optional[str]:
        if not getattr(sys, "frozen", False) and sys.executable and os.path.exists(sys.executable):
            return sys.executable
        for name in ("python", "python3"):
            p = shutil.which(name)
            if p and "windowsapps" not in p.lower():
                return p
        local_py_root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python")
        if os.path.exists(local_py_root):
            for entry in sorted(os.listdir(local_py_root), reverse=True):
                cand = os.path.join(local_py_root, entry, "python.exe")
                if os.path.exists(cand):
                    return cand
        return None

