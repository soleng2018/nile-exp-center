from pathlib import Path

import pytest

from nile_lab import config
from nile_lab.model import ActualState, NetInterface, UsbDevice

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SAMPLE = ROOT / "examples" / "lab.sample.yaml"


def fresh_server() -> ActualState:
    """This server before bootstrap: no docker, no units, real NICs (none match the sample MACs)."""
    return ActualState(
        interfaces=(
            NetInterface("eno1", "74:86:7a:ed:7a:b4", True),
            NetInterface("eno2", "74:86:7a:ed:7a:b5", False),
            NetInterface("wlx482254305d28", "48:22:54:30:5d:28", False, "1-1.2.1.1.2.4"),
        ),
        usb_devices=(UsbDevice("1-1.2.1.1.2.4", 1, 34, "2357", "012d"),),
        host_routes=("10.1.255.0/24",),
    )


@pytest.fixture
def sample_cfg() -> config.LabConfig:
    return config.load(SAMPLE)


@pytest.fixture
def as_root(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 0)


@pytest.fixture
def fake_observe(monkeypatch):
    """Replace the real adapters; tests set `.state` to change what is observed."""

    class Fake:
        state = fresh_server()

    fake = Fake()
    monkeypatch.setattr("nile_lab.observe.observe", lambda: fake.state)
    return fake
