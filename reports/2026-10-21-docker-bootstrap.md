# Docker repository and prerequisite automation — 2026-10-21

Implemented in `ansible/roles/host_prerequisites`, used by `prepare.yml --tags prerequisites`.

The role supports Debian 12/13 and Ubuntu 22.04/24.04/26.04 LTS on ARM64/AMD64. It creates a missing official Docker apt source with a dedicated signing key, verifies the expected primary fingerprint, refreshes package metadata when adding a repository or installing missing prerequisites, and installs missing packages. Requested packages that already exist are pinned to their installed version for that run, including Docker Engine/CLI, containerd and Buildx/Compose plugins. Fresh installs use current stable candidates; this is not a permanent version lock.

An existing matching `.list` or Deb822 `.sources` configuration is preserved. Duplicate or incompatible entries, signature-verification bypasses, invalid key paths/fingerprints, unsupported targets, conflicting distribution Docker/runtime packages and unmanaged Docker binaries are refused rather than replaced automatically. Full preparation accepts only the real apt root; repository-only fixtures use a private root and never install packages.

## Production verification

Preview, deployment and unchanged repeat each passed with `ok=20`, `changed=0`, `unreachable=0`, `failed=0`. The final preview after all guard changes passed with the same result.

Verified unchanged across deployment and repeat:

- All five installed Docker/runtime/plugin package versions.
- Docker daemon PID and all twelve managed container IDs.
- Existing `/etc/apt/sources.list.d/docker.list` and `/etc/apt/keyrings/docker.asc` contents, ownership and permissions.

All 18 production health checks passed afterwards.

## Isolated verification

Repository-only playbooks exercised fresh setup for Debian Trixie ARM64 and Ubuntu Noble AMD64 in temporary apt roots. For both, preview predicted changes without writing fixture files, creation passed (`changed=3`), and repeat passed (`changed=0`). Real official keys were downloaded over HTTPS and fingerprint-verified. Supplying an unexpected fingerprint failed without changing the created source/key files.

With isolated apt configuration, source files, state, logs and caches, package metadata refresh validated Docker's signed repository and found a `docker-ce` candidate with an empty installed-package database for both distributions/architectures. System apt update hooks were excluded and checked absent. No packages were installed by these fixtures. Temporary data was removed.

All 15 Ansible regression tests passed, covering repository parsing and preservation, duplicate/mismatch refusal, disabled sources, missing/symlinked keys, signature bypass, supported target guards, and existing Vault/SSH tests. Syntax and whitespace checks passed.

## Limits and remaining work

This does not establish a complete package installation or a working Docker daemon on a fresh machine. A genuinely separate-host installation and full service recovery remain untested. OS installation, initial SSH/sudo/account setup, repository checkout and application-data recovery remain separate steps. Outside monitoring remains deferred.

Usage and the staged fresh-host workflow: [Ansible operations](../ansible/README.md) and [remote preparation](../ansible/REMOTE_PROVISIONING.md).
