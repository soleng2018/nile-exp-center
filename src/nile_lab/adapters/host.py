"""Host adapter: read side for sysfs (NICs, USB), routes and systemd unit files."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nile_lab.model import MANAGED_HEADER, NetInterface, UnitFile, UsbDevice

IFF_UP = 0x1
UNIT_DIR = Path("/etc/systemd/system")
USB_DIR = Path("/sys/bus/usb/devices")
NET_DIR = Path("/sys/class/net")


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def usb_port_of(iface_dir: Path) -> str | None:
    """USB port path (e.g. "1-1.2.4") of a network interface, or None if not USB."""
    try:
        dev = (iface_dir / "device").resolve(strict=True)
    except OSError:
        return None
    # device -> ".../1-1.2.4/1-1.2.4:1.0"; the parent dir is the USB device.
    if ":" not in dev.name or not (dev.parent / "busnum").exists():
        return None
    return dev.parent.name


def read_interfaces(net_dir: Path = NET_DIR) -> tuple[NetInterface, ...]:
    out = []
    for d in sorted(net_dir.iterdir()) if net_dir.exists() else []:
        mac = _read(d / "address")
        if not mac or d.name == "lo":
            continue
        flags = int(_read(d / "flags") or "0", 16)
        out.append(NetInterface(d.name, mac.lower(), bool(flags & IFF_UP), usb_port_of(d)))
    return tuple(out)


def read_usb_devices(usb_dir: Path = USB_DIR) -> tuple[UsbDevice, ...]:
    out = []
    for d in sorted(usb_dir.iterdir()) if usb_dir.exists() else []:
        if ":" in d.name or d.name.startswith("usb"):
            continue  # interfaces and root hubs
        bus, num = _read(d / "busnum"), _read(d / "devnum")
        if bus is None or num is None:
            continue
        out.append(
            UsbDevice(d.name, int(bus), int(num), _read(d / "idVendor") or "", _read(d / "idProduct") or "")
        )
    return tuple(out)


def read_routes() -> tuple[str, ...] | None:
    """Destination CIDRs, or None when the routes could not be read (never fail open)."""
    try:
        res = subprocess.run(["ip", "-j", "route", "show", "table", "all"], capture_output=True, text=True,
                             check=True, timeout=10)
        rows = json.loads(res.stdout or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    routes = []
    for r in rows:
        dst = r.get("dst", "")
        if dst and dst != "default" and r.get("type", "unicast") == "unicast":
            routes.append(dst if "/" in dst else f"{dst}/32")
    return tuple(sorted(set(routes)))


def read_unit_files(unit_dir: Path = UNIT_DIR) -> tuple[UnitFile, ...]:
    out = []
    for f in sorted(unit_dir.glob("nile-lab-*")) if unit_dir.exists() else []:
        if not f.is_file():
            continue  # drop-in dirs like nile-lab-boot.service.d are not units
        head = (_read(f) or "").splitlines()[:1]
        out.append(UnitFile(f.name, head == [MANAGED_HEADER]))
    return tuple(out)
