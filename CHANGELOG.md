# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- First scaffold of the `nile-lab` command line tool (Python 3.13, installed with `uv sync --locked`). The stack and architecture are recorded in spec 0001.
- `nile-lab validate` checks your lab config file and lists every bad field, without ever printing secret values.
- `nile-lab plan` reads the host and Docker, compares them with your config, and prints what it would change, grouped by phase (host, docker, clients, cloudflare). It only reads and never changes anything. Use `--offline` to skip Cloudflare, `--json` for machine readable output, and `--detailed-exitcode` to exit `3` when changes are pending.
- Ownership safety: the plan only acts on resources that `nile-lab` created. Anything else it finds is reported as foreign and left alone.
- Clear exit codes: `0` ok, `1` runtime error (for example Docker not responding, reported in one line), `2` invalid config or refused precondition (not run as root, subnet overlap, or host routes that could not be read, so the overlap check never passes silently), `3` changes pending.
- A sample config in `examples/lab.sample.yaml` (placeholder secrets only) and a unit test suite that runs without root, KVM, or network.
