"""Docker adapter: wraps the docker CLI. Only the read side exists so far."""

from __future__ import annotations

import json
import shutil
import subprocess

from nile_lab.model import Container, DockerNetwork


TIMEOUT = 30  # seconds; a hung daemon must not hang plan


class DockerError(Exception):
    pass


def available() -> bool:
    return shutil.which("docker") is not None


def _run(*args: str) -> str:
    try:
        res = subprocess.run(["docker", *args], capture_output=True, text=True, check=True, timeout=TIMEOUT)
    except subprocess.CalledProcessError as e:
        raise DockerError(f"docker {args[0]} failed: {e.stderr.strip()}") from None
    except subprocess.TimeoutExpired:
        raise DockerError(f"docker {args[0]} timed out after {TIMEOUT}s (is the daemon stuck?)") from None
    except OSError as e:
        raise DockerError(f"docker {args[0]} could not run: {e.strerror}") from None
    return res.stdout


def _labels(raw: str | dict | None) -> dict[str, str]:
    # `docker ps --format json` gives "k=v,k=v"; inspect gives a dict.
    # A piece with no "=" is a comma inside the previous value, so glue it back on.
    if isinstance(raw, dict):
        return raw
    out: dict[str, str] = {}
    last = None
    for piece in (raw or "").split(","):
        k, sep, v = piece.partition("=")
        if sep:
            out[k] = v
            last = k
        elif last is not None:
            out[last] += f",{piece}"
    return out


def _json_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def list_containers() -> tuple[Container, ...]:
    rows = _json_lines(_run("ps", "-a", "--filter", "name=^nile-", "--format", "{{json .}}"))
    return tuple(
        Container(r["Names"], r.get("State") == "running", _labels(r.get("Labels"))) for r in rows
    )


def list_networks() -> tuple[DockerNetwork, ...]:
    names = [r["Name"] for r in _json_lines(_run("network", "ls", "--format", "{{json .}}"))]
    names = [n for n in names if n.startswith("nile-")]
    if not names:
        return ()
    out = []
    for n in json.loads(_run("network", "inspect", *names)):
        subnets = tuple(c["Subnet"] for c in (n.get("IPAM") or {}).get("Config") or [] if "Subnet" in c)
        out.append(DockerNetwork(n["Name"], n["Driver"], subnets, _labels(n.get("Labels"))))
    return tuple(out)
