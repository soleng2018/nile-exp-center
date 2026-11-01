# 0001. Python declarative reconciler for the Nile client VM lab

**Date**: 2026-10-31
**Status**: In Progress

## Summary

The lab is driven by one Python command line tool, `nile-lab`. It reads your single config file (the desired state), looks at what is really running on this server and in Cloudflare (the actual state), works out the difference (a plan), and applies only that difference. The same loop gives you fresh installs, safe reruns that add only new clients, a dry run, and recovery after a reboot. Nothing extra is stored: everything the tool creates carries an ownership label or name prefix, so your one config file stays the only thing to back up, and the tool never touches anything it did not create (such as the `nova` tunnel or Authentik).

## Requirements

Light criteria for the scaffold sub task of scope feature 1 (the full behavior is specced by features 3 to 10).

**User stories**:
- As the lab operator, I want one command that shows what it would change before it changes anything, so that I can trust a rerun on a live lab.

**Acceptance criteria**:
- **AC-1**: On this server, `sudo nile-lab plan --offline --config examples/lab.sample.yaml` loads the sample config shipped with the scaffold, prints the planned actions grouped by phase (host, docker, clients, cloudflare marked `skipped (offline)`), matches the golden output in `tests/fixtures/plan.sample.txt` (with `--json`, the golden JSON), and changes nothing on the host, in Docker, or in Cloudflare.
- **AC-5**: Exit codes follow the *CLI contract*: an invalid sample config exits `2` and names each bad field, and `plan --detailed-exitcode` exits `3` when changes are pending.
- **AC-2**: `nile-lab` run without root exits non zero with a clear message, before it reads the config.
- **AC-3**: `uv sync --locked` on a fresh checkout installs the exact locked dependencies, and `uv run pytest` passes with no root, no KVM, and no network (unit tests use fake adapters).
- **AC-4**: The planner never emits an action against a resource that lacks the `nile-lab` ownership marker (see *Ownership contract*); an unowned resource found during observation is reported as `foreign, ignored`.

## Decision

**Chosen option**: Option 1: Python declarative reconciler, generated compose per client, systemd and udev (see [rationale.md](rationale.md)).

One Python CLI (`nile-lab`) runs a plan then apply reconcile loop over four phases (host, docker, clients, cloudflare). It keeps no state file and identifies what it owns through labels and name prefixes. It is driven by systemd for boot and monitoring.

**Implementation skills**: none installed yet (see `## Follow-up`).

## Rationale

Reasoning and options: see [rationale.md](rationale.md).

## Proposed stack

| Layer | Choice | Reason |
|---|---|---|
| Architecture pattern | Declarative reconciler (desired state, observe, plan, apply) | Delta runs, dry run, and reboot recovery all come from one loop instead of three separate code paths. |
| Language | Python 3.13, a uv managed interpreter (pinned in `.python-version`) | Good YAML, validation and HTTP libraries; pinning through uv avoids depending on whichever `python3` Ubuntu 26.04 ships, and never touches system Python. |
| Packaging | uv with `pyproject.toml` and a committed `uv.lock`; installs with `uv sync --locked` | The same dependencies install on every rebuild of the server. |
| CLI | Typer | Subcommands from type hinted functions, with help text for free. |
| Config and validation | YAML (`ruamel.yaml` or `PyYAML` safe loader, picked in spec for feature 3) validated by pydantic v2 models, secrets typed as `SecretStr` | Strict validation catches YAML's implicit typing quirks; `SecretStr` keeps secrets out of reprs and logs. Schema is owned by feature 3. |
| State | No state that needs a backup. Actual state is read live, and ownership is marked by labels, prefixes and markers. Only throwaway runtime state (monitor counters, pending events) lives in `/run/nile-lab/` (tmpfs, cleared at reboot) | Keeps `lab.yaml` the single backup file; nothing durable can drift from reality. |
| Tunnel connector | `cloudflared` on the host as `nile-lab-cloudflared.service` (systemd, `After=network-online.target`, independent of the VMs), a remotely managed tunnel whose ingress is set through the API, token in `/etc/nile-lab/tunnel.token` (`0600`, rewritten on apply) | The host reaches every VM's management IP on the bridge; no `config.yml` to drift. |
| VM runtime | `dockur/windows` and `dockur/macos` on KVM, one generated `compose.yaml` per client, one compose project per client (`nile-<client>`) | Isolates each client's delta, matches the `docker-clients` reference (with Traefik labels removed), and stays debuggable by hand. |
| Docker access | `docker` and `docker compose` CLI through `subprocess`, behind one adapter module; reads use `--format json` filtered by our labels | The same commands you run by hand; one adapter is easy to fake in tests. |
| Guest startup scripts | Jinja2 templates in the repo (PowerShell for Windows, shell for macOS), rendered per client | Reviewable, and the rendered output is hashed for delta detection. |
| Cloudflare | Our own thin client: `httpx` plus pydantic models for only the endpoints used (tunnel, tunnel config, DNS, Access apps, Targets, policies, read only IdP lookup) | Browser RDP and Targets are newer API surface; a thin client cannot break on SDK major releases and is easy to mock. |
| Host integration | systemd units and udev rules rendered from templates; USB dongles resolved from sysfs | Native to Ubuntu, and survives reboots without extra daemons. |
| Boot recovery | `nile-lab-boot.service` (oneshot, after `docker.service`, `network-online.target` and `systemd-udev-settle.service`, waiting up to a set timeout for each configured dongle and wired port to appear) runs `nile-lab apply --yes --local-only`; containers use `restart: "no"` | Re-resolves each dongle's USB address before any VM starts, so no VM races ahead on a stale address. Cloudflare config lives remotely and needs no write at boot. |
| Monitoring | `nile-lab monitor`, a long running daemon under `nile-lab-monitor.service` (`Restart=always`): polls VM health (the shared *Health model*) on an interval, plus reacts to udev events for dongles | Fast dongle recovery. Failure counters persist in `/run/nile-lab/monitor.json`, so a crash of the monitor does not reset backoff. Event library and policy are specced in feature 10. |
| Privileges | Runs as root (`sudo nile-lab ...`); systemd units run as root | Needs udev, systemd, network and Docker; honest for a single purpose lab server. |
| Logging | Structured logs to stdout/stderr, captured by journald; one central redaction filter | Nothing extra to rotate; `journalctl -u nile-lab-*` shows everything. |
| Tests | pytest. `tests/unit` with fake adapters (default run); `tests/integration` with markers `host` and `cloudflare`, run on this dev server | Fast loop without root, plus real proof on the actual host and Cloudflare account. |
| Lint and format | Decided in scope feature 2 (`/audit`) from the scaffolded project | Out of this decision on purpose. |

### Components and module layout

```
pyproject.toml  uv.lock  .python-version
src/nile_lab/
  cli.py              Typer app: validate, plan, apply, status, monitor
  config/             pydantic models + YAML loader (schema from feature 3)
  model.py            Resource, Action, Plan, Health types (pure data)
  observe.py          builds ActualState by calling each adapter's read side
  planner.py          PURE function: (DesiredState, ActualState) -> Plan
  apply.py            runs a Plan phase by phase; stops a client on its first failure
  render.py           Jinja2 rendering + content hash
  adapters/
    host.py           sysfs USB/MAC resolver, udev rules, systemd units, links
    docker.py         docker / docker compose subprocess wrapper
    cloudflare.py     httpx client for the endpoints listed above
  monitor.py          daemon loop (feature 10)
  log.py              structured logging + secret redaction filter
  templates/          compose.yaml.j2, windows/*.j2, macos/*.j2, systemd/*.j2, udev/*.j2
tests/unit/  tests/integration/  tests/fixtures/   (recorded docker, sysfs, Cloudflare JSON + golden plans)
examples/lab.sample.yaml                         (no real secrets)
```

Rule: only `adapters/` touches the outside world. `planner.py` and `render.py` are pure, so the planner is fully unit testable.

### Reconcile loop and phases

`apply` = load config → observe → plan → print plan → confirm (y/N, skipped with `--yes`) → apply. `plan` stops after printing. Phases run in this order:

1. **host**: packages and services from feature 4, udev rules, systemd units, macvlan parent links (up, no IP)
2. **docker**: shared networks (the management bridge `nile-mgmt`, macvlan networks)
3. **clients**: one client at a time: resolve the dongle or wired port, render files, hash, then `docker compose -p nile-<client> up -d` when needed (see *Change detection*). `up -d` does not wait for the Windows or macOS install to finish; progress shows in `status` through the *Health model*.
4. **cloudflare**: tunnel, tunnel ingress config, DNS records, Targets, Access apps, policies. Skipped by `--local-only` and `--offline`.

**Failure rules**: a host or docker phase failure aborts the run. A client failure stops that client only, and the others continue. The cloudflare phase runs for every client whose client phase succeeded and skips the rest. The exit code is `1` if anything failed.

Action kinds: `create`, `update`, `recreate`, `noop`, `orphan`. **Delete is out of scope** for this pass (scope keeps *Remove or change a client* deferred): an owned resource with no matching config entry is reported as `orphan` and left alone.

### Management network and reachability

- Every VM's management interface sits on one Docker bridge network, `nile-mgmt`, whose subnet comes from config (one subnet for the whole lab). Each client's management IP is explicit in config inside that subnet.
- `cloudflared` on the host reaches VMs **only** through their management IPs. macvlan and WiFi carry client traffic only (the host cannot reach macvlan IPs anyway).
- Before creating `nile-mgmt`, the tool checks (read only) that the subnet does not overlap any host route or interface, or any route on any existing Cloudflare tunnel (including `nova`). On overlap it refuses with exit code `2`.
- Guest startup scripts own route preference: the WiFi or wired client interface always gets a lower route metric (preferred) than the management interface. Features 5 and 9 implement this rule; they don't redefine it.

### Device identity (dongles and wired ports)

- **Dongles**: config names each one by its WiFi MAC. The host driver binds normally, so a free dongle shows as a network interface. The resolver goes from MAC through sysfs to the USB physical port path (for example `3-2.1`), then to `hostbus` and `hostport` for QEMU. The port path is stored on the container as label `lab.nile.usb=<port path>`.
- **A dongle a running VM has already claimed** has no host interface, so its MAC can't be seen. The resolver then trusts the owning container's `lab.nile.usb` label, provided that port still holds a device with the T3U vendor and product ID. Otherwise the dongle is reported as `missing`.
- **Wired ports**: config names each macvlan parent by its MAC. The resolver finds the current interface name on every run, so a renamed `enoN` doesn't break a client.
- Vendor and product ID alone are never used to pick a device, because all 11 dongles are identical.

### Change detection

Two hashes per client, both stored as container labels:
- `lab.nile.spec-hash`: sha256 of the rendered compose file, guest scripts, and the pinned image reference (`image` in config defaults to a pinned tag, never `latest`).
- `lab.nile.runtime-hash`: sha256 of the resolved USB address or wired interface.

| Situation | Normal `apply` | Boot (`--local-only --yes`) |
|---|---|---|
| Container missing | `create` | `create` |
| Container stopped, hashes match | start | start |
| Only the runtime hash differs | `recreate` | `recreate` (the disk is kept) |
| The spec hash differs on a **running** VM | `recreate`, needs a confirmation per client (`--yes` alone is not enough; pass `--recreate <client>` or `--recreate-all`) | never; reported as pending |

Feature 8 adds the table of config field classes (which edits are cosmetic, which force a recreate, which are immutable and rejected).

### Health model (shared by `status`, boot and the monitor)

`model.py` defines one `Health` enum and one `observe_health(client)` function. Features 5, 7, 9 and 10 use it and don't define their own.

| State | Meaning |
|---|---|
| `absent` | no owned container |
| `stopped` | container exists, not running |
| `installing` | container running, RDP or VNC port not answering yet, inside the install window from config |
| `healthy` | container running and the RDP (3389) or VNC port answers on the management IP |
| `degraded` | running, but the port doesn't answer after the install window, or the dongle or wired port is `missing` |
| `failed` | the monitor gave up after its retry limit (from `/run/nile-lab/monitor.json`) |

### CLI contract

- Commands: `validate`, `plan`, `apply`, `status`, `monitor`. All require root except `--help`.
- Output: plain text by default, `--json` for machine use (one stable schema per command).
- Exit codes: `0` ok · `1` runtime error or a failed client · `2` invalid config or a refused precondition (such as root missing, or a subnet overlap) · `3` changes pending (only with `plan --detailed-exitcode`).
- `--offline` skips every Cloudflare read and write, marking that phase `skipped (offline)`. It is for the scaffold, tests, and boot.
- Locking: `apply` and boot block on the lock for up to a timeout (default 15 minutes, then exit `1`). The monitor never blocks: while the lock is held, it queues udev events in `/run/nile-lab/` and evaluates them again after the lock is released.

### Naming rule

Client names match `^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$`, because they flow into container names, compose projects, labels, DNS hostnames and Cloudflare names. Feature 3 validates it.

### Ownership contract (every later feature must follow it)

| Where | Marker | Notes |
|---|---|---|
| Docker containers, networks | labels `lab.nile.managed=true`, `lab.nile.client=<name>`, `lab.nile.spec-hash`, `lab.nile.runtime-hash`, `lab.nile.usb` | compose project name `nile-<client>`; shared networks named `nile-*` |
| Cloudflare tunnel | name `nile-lab-<server_name>` | the tool writes only to the tunnel matching this name; any other tunnel (including `nova`) is read only |
| Cloudflare DNS, Targets, Access apps | name or hostname prefix `nile-lab` (exact form fixed in feature 6) **plus** a marker: DNS record comment `managed by nile-lab`, and Targets and apps traceable to our tunnel | both prefix and marker are required; one alone is `foreign` |
| Access policies | the tool creates its own policies (prefix `nile-lab`), with include rules from config | it never edits or attaches to an existing policy, even one `nova` apps use |
| Authentik IdP in Cloudflare Access | none, **never written** | looked up by name, read only |

**Write allowlist (enforced in `adapters/cloudflare.py`, not only in the planner)**: every `PUT`, `PATCH` or `DELETE` must target an ID in the owned set observed during the same run, and `POST` may only create resources carrying the prefix and marker. Anything else raises before the request is sent. The API token is dedicated to this tool and scoped tightly (exact scopes in feature 6).
| Host files | `/etc/systemd/system/nile-lab-*`, `/etc/udev/rules.d/90-nile-lab-*.rules`, header `# managed by nile-lab` | the tool rewrites only files carrying the header |

### Locations on disk

| Path | Contents | Back up? |
|---|---|---|
| `/srv/nile-lab/lab.yaml` | the single config and secrets file, `0600 root:root`. Overridable with `--config` or `NILE_LAB_CONFIG` | **yes, the only file** |
| `/srv/nile-lab/clients/<name>/` | rendered `compose.yaml`, OEM and startup scripts (may contain secrets), `0700 root` | no, rebuilt from config |
| `/srv/nile-lab/storage/<name>/` | VM disks | no (exclude from backups); losing it means the VM reinstalls on next apply |
| `/opt/nile-lab/` | deployed code checkout and `.venv`; systemd runs `/opt/nile-lab/.venv/bin/nile-lab` | no, from git |

During development you can run `sudo uv run nile-lab ...` straight from this repo.

### Value sourcing

| Action | Value | Source |
|---|---|---|
| render client compose | dongle `hostbus` and `hostport` for QEMU `-device usb-host` | from the dongle's WiFi MAC in config through sysfs, or from the `lab.nile.usb` label when a running VM has claimed the dongle (see *Device identity*) |
| render client compose | macvlan parent interface name | from the wired port's MAC in config, resolved on every run |
| docker phase | `nile-mgmt` subnet and gateway | config (one lab wide subnet; the gateway defaults to the first address); overlap checked read only |
| docker phase | macvlan subnet, gateway, and DHCP vs static | config per wired network (schema in feature 3; dockur's `DHCP: "Y"` is the default) |
| render client compose | management IP | explicit per client in config, inside the `nile-mgmt` subnet |
| render client compose | image reference | config, defaulting to a pinned tag |
| delta check | `lab.nile.spec-hash`, `lab.nile.runtime-hash` | see *Change detection* |
| health | install window, port per OS | config default (for example 90 minutes); RDP 3389 for Windows, VNC port for macOS fixed in feature 9 |
| cloudflare phase | account ID, zone ID | account ID from config; zone ID looked up by zone name `nileglobalinc.com` from config |
| cloudflare phase | tunnel ID | looked up by name `nile-lab-<server_name>`, created when missing |
| cloudflared service | tunnel token | fetched from the API at apply, written to `/etc/nile-lab/tunnel.token` (`0600 root`); **not** stored in `lab.yaml` |
| Access policies | Authentik IdP ID | looked up by IdP name from config, read only |
| Access policies | include rules (groups, emails) | config. `nova` is a reference you read while designing feature 6, never read at runtime |
| Access app | public hostname | derived from client name plus base domain from config (exact pattern in feature 6) |
| every command | API token, guest passwords, WiFi keys | `lab.yaml`, typed `SecretStr` |

### Key invariants

- Only resources carrying the ownership marker are ever changed. Others are observed read only, at most.
- `plan` and `apply` with no config change emit only `noop` actions.
- One process mutates at a time: `apply`, the boot service, and monitor recovery actions take an exclusive `flock` on `/run/lock/nile-lab.lock` (see *CLI contract* for blocking rules).
- Boot never recreates a running VM because of a spec change (see *Change detection*).
- No secret value appears in stdout, stderr, journald, exception text, command arguments, or container environment variables where avoidable. Secrets reach containers and guests through `0600` files (an `env_file` or a file in the OEM folder) under `/srv/nile-lab/clients/` (`0700`).
- Only root runs Docker. No user is added to the `docker` group, because that group is the same as root and would expose rendered secrets through `docker inspect`.
- Secrets at rest are exactly: `lab.yaml` (`0600`), `/srv/nile-lab/clients/` (`0700`), and `/etc/nile-lab/tunnel.token` (`0600`). Guest side credentials (Windows user password, WiFi keys written into the VM) end up on VM disks. They are lab only credentials, and that exposure is accepted.
- Planner and renderer are pure; all I/O goes through `adapters/`.

### Testing on real systems

- This server is a dev server: integration tests may create and recreate VMs, networks, udev rules and units here.
- Cloudflare integration tests may create anything on `nileglobalinc.com` under a test prefix (`nile-lab-test-`), and teardown deletes **only** resources that the same test run created. Other tunnels (including `nova`), their config, and the Authentik IdP are never modified.

## Consequences

**Positive**:
- Delta, dry run, and reboot recovery share one tested code path.
- Backing up the lab means copying one file.
- The planner is pure, so most logic is tested in milliseconds without root or hardware.

**Negative / tradeoffs**:
- No state file means every run calls the Cloudflare API to observe, so it is slower and needs network for the cloud phase (boot avoids this with `--local-only`).
- Ownership still relies on discipline: a hand made Cloudflare resource with both the `nile-lab` prefix and our marker would be treated as ours. The write allowlist and dedicated token limit the damage.
- The dongle label fallback means a dongle swapped into the same physical port while a VM is running is trusted until the VM releases it.
- We maintain our own Cloudflare client (roughly a dozen endpoints) and track API changes ourselves.
- `restart: "no"` means a VM stays down if both the boot service and the monitor fail. The monitor's `Restart=always` is the safety net.
- `lab.yaml` sits next to large VM disks, so your backup job must target that one file (or exclude `storage/`).
- Recreating a Windows container keeps its disk, but dockur's OEM `install.bat` runs only during the first install, so changing a client's software list does not reach an already installed VM (feature 8 must decide how to handle that).

**Neutral**:
- Code is deployed to `/opt/nile-lab`, separate from the data root.
- Lint and format tooling is left to scope feature 2.

## Follow-up

- [ ] Feature 3 (config): fix the schema, including the per client management IP, dongle MAC and wired port MAC, the `nile-mgmt` subnet, macvlan network settings, pinned image references, install window, server name, base domain, Cloudflare account, the IdP name, and the policy include rules; pick the YAML library.
- [ ] Feature 9 and 6: name the fallback if browser VNC through Access doesn't work: dockur's built in web viewer (port 8006) published as an ordinary self hosted HTTP app behind Access.
- [ ] Feature 4 (bootstrap): define the install and upgrade path for `/opt/nile-lab` (how uv itself is installed, who runs `uv sync --locked`, how units are rendered again after an upgrade).
- [ ] Add a nightly integration test run (`host` and `cloudflare` markers) on this dev server once feature 2 sets up tooling.
- [ ] Feature 6 (Cloudflare): confirm the hostname pattern stays one level under `nileglobalinc.com` (Universal SSL covers `*.nileglobalinc.com` only, from my knowledge, so check this); set the exact `nile-lab` prefix; define least privilege API token scopes.
- [ ] Feature 9 (macOS): **risk**. `dockur/macos` documents no unattended first boot script mechanism, so setup likely runs over SSH after install. Browser rendered **VNC** for Access was not confirmed in the docs (browser RDP was). Verify both before designing.
- [ ] Feature 8 (delta): decide how a changed software list reaches an already installed VM.
- [ ] Feature 10 (monitoring): pick the udev event source (for example `pyudev` vs `udevadm monitor`) and the retry and backoff policy.
- [ ] Project is not a git repo yet; run `git init` before scaffolding so `/opt/nile-lab` can deploy from a checkout.
- [ ] `/audit` (feature 2) should capture this stack in root `AGENTS.md` (`/sync` keeps it current).
- [ ] Install the chosen Agent Skills once Node and `npx` are on the host (not installed today; found through web mirrors, so confirm each with `npx skills add <owner>/<repo> --list` first): `systemd-services` (`bagelhole/devops-security-agent-skills`), `cloudflare-zero-trust` (`bagelhole/devops-security-agent-skills`), `python-testing-patterns` (`wshobson/agents`), `docker-development-skill` (`netresearch/docker-development-skill`). Record each in root `AGENTS.md` `## Agent skills`, except `cloudflare-zero-trust`, which belongs in the Cloudflare adapter area's nested `AGENTS.md`.
- [ ] Connect the official Cloudflare MCP server (verify `github.com/cloudflare/mcp-server-cloudflare` first) with `claude mcp add`, ideally with a token that is read only for `nova`, before building feature 6. Record it on the `MCP servers:` line of `AGENTS.md`.
- [ ] Declined as unsafe (flagged by their security audits): `vm0-ai/vm0-skills` `cloudflare-tunnel`, and the `deploying-cloudflare-access-for-zero-trust` skills. Record them on the `Declined:` line.
