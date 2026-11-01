# Verify: Stack & architecture · spec 0001 · updated 2026-11-01
_Steps derived from spec 0001 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

Run these from the repo root on the lab server. `sudo` needs your password, so you run the root steps yourself.

## Commands
- [x] `uv sync --locked` on a fresh checkout → installs the locked dependencies with no changes to `uv.lock` → AC-3
- [x] `uv run pytest` as your normal user, with no network → all tests pass → AC-3
- [x] `.venv/bin/nile-lab plan --offline --config examples/lab.sample.yaml` (no sudo) → exits `2` with "must run as root" and never mentions the config → AC-2
- [x] `.venv/bin/nile-lab plan --config /nonexistent.yaml` (no sudo) → still the root message, not a file error (root is checked before the config is read) → AC-2
- [x] `sudo .venv/bin/nile-lab plan --offline --config examples/lab.sample.yaml | diff - tests/fixtures/plan.sample.txt` → no diff, exit `0` (true while Docker and the units are not installed yet) → AC-1
- [x] `sudo .venv/bin/nile-lab plan --offline --json --config examples/lab.sample.yaml | python3 -m json.tool | diff - <(python3 -m json.tool tests/fixtures/plan.sample.json)` → no diff → AC-1
- [x] The plan output groups actions under `host`, `docker`, `clients`, and shows `cloudflare: skipped (offline)` → AC-1
- [x] Before and after the plan, compare `ls /etc/systemd/system/nile-lab-* /srv/nile-lab 2>&1` and `ip -br link` → identical (plan changed nothing) → AC-1
- [x] `sudo .venv/bin/nile-lab plan --offline --detailed-exitcode -c examples/lab.sample.yaml; echo $?` → `3` → AC-5
- [x] `sudo .venv/bin/nile-lab validate -c tests/fixtures/lab.invalid.yaml; echo $?` → `2`, one line each for `server_name`, `clients.0.image`, `clients.0.wifi_dongle_mac`, `clients.1.os`, and the token value never appears → AC-5
- [x] `sudo touch /etc/systemd/system/nile-lab-boot.service` (no managed header), run the plan → it lists `unit nile-lab-boot.service` under `foreign, ignored` and has no create for it; then `sudo rm` that file → AC-4

## Value sourcing (real devices on this server)
- [x] Copy the sample to a temp file, set `wifi_dongle_mac` to a real dongle (for example `48:22:54:30:5d:28`), plan → `win01` shows `dongle 48:22:54:30:5d:28 on usb 1-1.2.1.1.2.4` with no `!` line; change to a second dongle and the USB port changes with it (the dongle is picked by MAC, never by model) → dongle hostbus/hostport row
- [x] In the same file set `parent_mac` to `eno2`'s MAC (`74:86:7a:ed:7a:b5`) → `port1` resolves to `eno2`, and the docker line reads `macvlan on eno2` → macvlan parent row
- [x] Set `mgmt_network.subnet` to `10.1.255.0/25` (overlaps the `eno1` route) → exit `2`, `refused: ... overlaps host route 10.1.255.0/24` → nile-mgmt subnet row
- [x] Set a client `mgmt_ip` outside the subnet, or to `.1` → validate exits `2` naming that client → management IP row
- [x] Set `image: dockurr/windows:latest`, or drop the tag → validate exits `2` on `clients.0.image` → image reference row
- [x] `sudo .venv/bin/nile-lab validate -c <temp file>` while `NILE_LAB_CONFIG` points elsewhere → the `--config` flag wins; with no flag, the env var wins over `/srv/nile-lab/lab.yaml` → config path row

## Acceptance-criteria coverage
- AC-1: golden text and JSON diffs, phase grouping, nothing changed
- AC-2: both no sudo runs
- AC-3: locked sync and pytest
- AC-4: the foreign unit step (unit tests also cover foreign containers and networks)
- AC-5: detailed exit code and the invalid config run
