from nile_lab.adapters import host
from nile_lab.model import MANAGED_HEADER


def make_usb_nic(root, name, mac, port, flags="0x1003"):
    usb = root / "devices" / port
    intf = usb / f"{port}:1.0"
    intf.mkdir(parents=True)
    (usb / "busnum").write_text("1\n")
    nic = root / "net" / name
    nic.mkdir(parents=True)
    (nic / "address").write_text(mac + "\n")
    (nic / "flags").write_text(flags + "\n")
    (nic / "device").symlink_to(intf)


def test_reads_usb_port_path_and_link_state(tmp_path):
    make_usb_nic(tmp_path, "wlx1", "48:22:54:30:5D:28", "1-1.2.4")
    eth = tmp_path / "net" / "eno1"
    eth.mkdir()
    (eth / "address").write_text("74:86:7a:ed:7a:b4\n")
    (eth / "flags").write_text("0x1002\n")

    by_name = {i.name: i for i in host.read_interfaces(tmp_path / "net")}
    assert by_name["wlx1"].mac == "48:22:54:30:5d:28"
    assert by_name["wlx1"].usb_port == "1-1.2.4"
    assert by_name["wlx1"].up
    assert by_name["eno1"].usb_port is None
    assert not by_name["eno1"].up


def test_reads_usb_devices_skipping_interfaces_and_hubs(tmp_path):
    for name in ("1-1.2.4", "1-1.2.4:1.0", "usb1"):
        d = tmp_path / name
        d.mkdir()
        (d / "busnum").write_text("1\n")
        (d / "devnum").write_text("34\n")
        (d / "idVendor").write_text("2357\n")
        (d / "idProduct").write_text("012d\n")
    devs = host.read_usb_devices(tmp_path)
    assert [(d.port, d.busnum, d.devnum, d.vendor, d.product) for d in devs] == [("1-1.2.4", 1, 34, "2357", "012d")]


def test_unit_files_need_the_managed_header(tmp_path):
    (tmp_path / "nile-lab-boot.service").write_text(f"{MANAGED_HEADER}\n[Unit]\n")
    (tmp_path / "nile-lab-monitor.service").write_text("[Unit]\n")
    (tmp_path / "other.service").write_text(f"{MANAGED_HEADER}\n")
    units = {u.name: u.managed for u in host.read_unit_files(tmp_path)}
    assert units == {"nile-lab-boot.service": True, "nile-lab-monitor.service": False}


def fake_ip(monkeypatch, routes=None, fail=False):
    import json
    import subprocess

    def run(cmd, **kwargs):
        if fail:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(routes), "")

    monkeypatch.setattr("nile_lab.adapters.host.subprocess.run", run)


def test_routes_keep_unicast_destinations_only(monkeypatch):
    fake_ip(monkeypatch, [
        {"dst": "default", "gateway": "10.1.255.1"},
        {"dst": "10.1.255.0/24"},
        {"dst": "10.1.255.0/24", "table": "main"},
        {"dst": "10.1.255.20", "type": "local", "table": "local"},
        {"dst": "192.168.9.9", "type": "unicast"},
        {"dst": "255.255.255.255", "type": "broadcast"},
    ])
    assert host.read_routes() == ("10.1.255.0/24", "192.168.9.9/32")


def test_routes_are_empty_when_ip_fails(monkeypatch):
    fake_ip(monkeypatch, fail=True)
    assert host.read_routes() == ()


def test_missing_sysfs_and_unit_dirs_read_as_empty(tmp_path):
    gone = tmp_path / "nope"
    assert host.read_interfaces(gone) == ()
    assert host.read_usb_devices(gone) == ()
    assert host.read_unit_files(gone) == ()


def test_loopback_and_interfaces_without_mac_are_skipped(tmp_path):
    for name, mac in (("lo", "00:00:00:00:00:00"), ("tun0", "")):
        d = tmp_path / name
        d.mkdir()
        (d / "address").write_text(mac + "\n")
    assert host.read_interfaces(tmp_path) == ()


def test_pci_nic_has_no_usb_port(tmp_path):
    pci = tmp_path / "devices" / "0000:00:1f.6"
    pci.mkdir(parents=True)
    nic = tmp_path / "net" / "eno1"
    nic.mkdir(parents=True)
    (nic / "address").write_text("74:86:7a:ed:7a:b4\n")
    (nic / "device").symlink_to(pci)
    (iface,) = host.read_interfaces(tmp_path / "net")
    assert iface.usb_port is None


def test_empty_unit_file_is_not_managed(tmp_path):
    (tmp_path / "nile-lab-boot.service").write_text("")
    (tmp_path / "nile-lab-monitor.service").write_text(f"[Unit]\n{MANAGED_HEADER}\n")
    assert all(not u.managed for u in host.read_unit_files(tmp_path))
