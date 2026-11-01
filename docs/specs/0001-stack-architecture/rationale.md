# 0001. Rationale: Python declarative reconciler for the Nile client VM lab

Decision record for [index.md](index.md). `/develop` does not need this file.

## Context

This server (Ubuntu 26.04, 64 cores, 121 GB RAM, KVM) must host a lab of Windows and macOS client VMs for internal demos. Each VM is reachable in the browser over RDP or VNC through Cloudflare Access, behind the externally hosted Authentik login. Windows VMs get one of 11 identical USB WiFi dongles (TP-Link Archer T3U) passed through, and macOS VMs get a macvlan link on a spare wired port (macvlan: a virtual network card with its own MAC on a physical port). Every VM has a second, management interface. The VMs run as KVM in Docker using the `dockur` images, following the `docker-clients` reference without Traefik.

The forces that shape the stack (from `docs/brief.md` and the scope):
- **One file to back up** that holds all config and secrets.
- **Delta runs**: adding a client and rerunning must touch only the new client and leave running VMs and apps alone. A dry run must show changes first.
- **Reboot recovery** with no human involvement, even though USB bus numbers can change across reboots, and identical dongles can only be told apart by MAC or physical port.
- **Hard safety boundary in Cloudflare**: the tool may add anything on `nileglobalinc.com`, may delete only what it created, and must never change the `nova` tunnel, other tunnels, or the Authentik IdP.
- **Monitoring and recovery** of VMs and dongles.
- One operator, one server, no team scale or multi host needs. This server is a dev server where real integration testing is allowed.

The request says "a script", but these needs (delta, dry run, recovery, safety boundary) describe a small reconciling tool rather than a set of scripts. Without a deliberate structure, each need would become its own ad hoc code path and drift apart.

## Options considered

Full stacks compared, not individual tools.

### Option 1: Python declarative reconciler, generated compose per client, systemd and udev

A single Python CLI computes a plan from desired versus observed state and applies it through thin adapters (Docker CLI, sysfs and systemd, a small httpx Cloudflare client). Ownership is marked by labels and prefixes, with no state file.

**Pros**: one code path for delta, dry run, and recovery; a pure planner is easy to test; strong YAML, validation and HTTP libraries; one backup file.
**Cons**: more up front design than scripts; a Python runtime to manage (uv); every run reads live Cloudflare state.

### Option 2: Bash imperative scripts with docker compose and curl

Ordered scripts (`bootstrap.sh`, `add-client.sh`, `publish.sh`), each guarded by existence checks, using `jq` for API JSON.

**Pros**: no runtime to install; closest to the commands you'd type by hand; fast to start.
**Cons**: nested config validation, JSON diffing against Cloudflare, and dry run are fragile in Bash; delta and recovery logic spread across scripts and drift; hard to unit test.

### Option 3: Ansible for the host plus OpenTofu or Terraform for Cloudflare

Idempotent Ansible roles for the host and containers, with the Cloudflare provider for tunnels, DNS and Access.

**Pros**: mature idempotency; Terraform gives a real plan and apply for Cloudflare.
**Cons**: two tools and two languages; Terraform state is a second file to back up (which breaks the single file requirement) or needs a remote backend; dongle MAC to USB address resolution and monitoring still need custom code; Ansible's dry run is weak for shell steps.

### Option 4: Go single binary reconciler

The same reconciler design as Option 1, compiled to one static binary.

**Pros**: no runtime on the host; strong typing; good Docker and HTTP libraries.
**Cons**: slower iteration and a build step for a one server lab; fewer quick templating and YAML conveniences; the strengths (distribution, performance) do not matter on a single host.

## Rationale

The delta, dry run and reboot requirements are all the same operation, "make reality match the config", seen from different angles. A declarative reconciler implements that once (Option 1 or 4). Scripts (Option 2) would implement it three times, inconsistently. Between Python and Go, nothing here rewards Go's strengths: there's one host and a low call volume, and fast iteration matters more. Option 3 gets a good Cloudflare plan from Terraform, but at the cost of a state file, which directly violates the single backup file requirement. It would also still leave the hardest local problems (telling identical dongles apart, monitoring) as custom code.

Not storing state follows from the same backup requirement. Ownership labels and prefixes also make the Cloudflare safety boundary something the planner enforces mechanically: an unmarked resource can never appear in an action. A thin httpx client was chosen over the official SDK because the resources we need (browser rendered RDP, Targets) are newer API surface. The SDK's coverage of them was not confirmed, and it had a breaking major release (v5) in April 2026. Generated compose per client (rather than one shared project) keeps each client's delta isolated and stays readable when you debug by hand. A systemd boot service that looks up each dongle again before starting any container answers the USB renumbering problem that Docker restart policies cannot.

Small calls I made on your behalf (pick, then runner up):
- **Python 3.13 managed by uv**, runner up the system `python3`. Sources disagree on whether Ubuntu 26.04 ships 3.13 or 3.14, and pinning removes the question.
- **Code in `/opt/nile-lab`**, runner up running in place from the home directory checkout. systemd units shouldn't depend on a user's home directory.
- **Boot runs `--local-only`**, runner up a full apply at boot. Cloudflare config persists remotely and cloudflared reconnects on its own, so boot never depends on API reachability.
- **No deletes in this pass**: orphans are reported, matching the deferred *Remove or change a client* scope item.
- **An exclusive `flock`** across apply, boot and monitor, runner up a PID file. A lock is released automatically if the process crashes.
- **Explicit management IP per client in config**, runner up an IP derived from the client's index. Cloudflare Targets reference IPs, so they must stay stable when clients are reordered.

## Landscape check (2026-10-31)

One capped web check, run before the stack questions:
- `cloudflare` Python SDK 5.9.0 (Oct 2026); v5.0.0 (Apr 2026) was a breaking major. Coverage of tunnels, Access apps and Targets was not confirmed.
- Browser rendered RDP: a self hosted app with a public hostname, the browser rendering setting set to RDP, a Target (hostname plus IP), a tunnel CIDR route, and a proxied DNS record. Policies allow Allow or Block only. Browser VNC appears in the setting's text but has no setup doc that I found.
- `dockur/windows` and `dockur/macos`: USB examples use `-device usb-host,vendorid=..,productid=..` with `/dev/bus/usb`; macvlan uses `DHCP: "Y"` plus `/dev/vhost-net` and a device cgroup rule; the host cannot reach a macvlan container IP directly. Windows runs `/oem/install.bat` at the end of install. macOS has no documented first boot script hook.
- uv 0.13.6, Typer 0.27.3, Click 8.5.0 (PyPI, Oct 2026).

## References

**Project sources**:
- `docs/brief.md` (the original request)
- `docs/scope/scope.md`, feature 1 and the server facts in its header
- The `docker-clients` reference repo named in the request (not yet read; its compose patterns are taken up in feature 5)

**Practices & standards**:
- Declarative reconciliation (desired state versus observed state, as in Kubernetes controllers and Terraform plan and apply)
- Ownership labelling for safe shared environments
- Functional core, imperative shell (pure planner, I/O in adapters)
- Least privilege for API tokens

**Links** (web verified during the landscape check):
- Cloudflare browser rendered RDP: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/use-cases/rdp/rdp-browser/
- Cloudflare Python SDK v5.0.0 changelog: https://developers.cloudflare.com/changelog/post/2026-04-30-cloudflare-python-v500/
- `cloudflare` on PyPI: https://pypi.org/project/cloudflare/
- dockur/windows: https://github.com/dockur/windows
- dockur/macos: https://github.com/dockur/macos
- uv on PyPI: https://pypi.org/project/uv/
- Typer on PyPI: https://pypi.org/project/typer/
