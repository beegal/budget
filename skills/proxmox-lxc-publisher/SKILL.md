---
name: proxmox-lxc-publisher
description: Use when building, releasing, installing, or validating native Proxmox LXC CT templates for an application, especially Debian-based templates with an app service, local MariaDB, firstboot initialization, GitHub Release assets, and Proxmox pct installation checks.
metadata:
  short-description: Publish and validate Proxmox LXC templates
---

# Proxmox LXC Publisher

Use this skill to publish an application as a native Proxmox LXC CT template.

The expected output is a `.tar.zst` template that Proxmox can install through `pct create` or the Proxmox UI.

## Scope

This skill covers:

- Building a Debian-based Proxmox CT template.
- Embedding an application and systemd services.
- Installing MariaDB inside the CT when requested.
- Using a firstboot service for secrets, database creation and schema initialization.
- Publishing the template as a GitHub Release asset.
- Testing the template on a real Proxmox host.

This skill does not document private reverse proxy, DNS or certificate infrastructure. Treat those as environment-specific deployment steps.

## Required Repository Shape

Prefer these paths unless the project already has established alternatives:

```text
build/lxc/build-template.sh
build/lxc/<app-name>-firstboot
build/lxc/<app-name>.service
build/lxc/<app-name>-firstboot.service
.github/workflows/lxc-template.yml
```

## Template Design

Use an official Proxmox Debian standard template as the base. Do not build from a generic rootfs if Proxmox compatibility matters.

Recommended base behavior:

- Default to the latest official Debian 12 standard template from `download.proxmox.com`.
- Allow pinning with `PROXMOX_TEMPLATE_VERSION`.
- Allow full override with `PROXMOX_TEMPLATE_URL`.
- Preserve the Proxmox-compatible `/etc/network/interfaces` layout from the base template.

Install into conventional paths:

```text
/opt/<app-name>/app
/opt/<app-name>/data
/etc/<app-name>/<app-name>.env
/etc/systemd/system/<app-name>.service
/etc/systemd/system/<app-name>-firstboot.service
```

Do not bake secrets into the template.

## Firstboot Rules

Firstboot should be idempotent and safe to rerun.

It should:

- Generate database root/application passwords if missing.
- Generate the application auth/session secret if missing.
- Write secrets to `/etc/<app-name>/<app-name>.env` with restrictive permissions.
- Start or wait for MariaDB when MariaDB is inside the CT.
- Create the application database and user.
- Initialize the schema.
- Disable itself after success.

It should not:

- Delete existing data.
- Rotate existing secrets automatically.
- Require network access.

## Build Checklist

Before releasing:

```bash
sh -n build/lxc/build-template.sh
sh -n build/lxc/<app-name>-firstboot
```

If the build script runs apt inside a chroot, make sure it handles common local-builder issues:

- Temporarily copy a working `/etc/resolv.conf` into the chroot for DNS.
- Create basic device nodes before apt if needed: `/dev/null`, `/dev/zero`, `/dev/random`, `/dev/urandom`, `/dev/tty`.
- Restore or clean up temporary files after the build.

Build locally on Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y zstd
VERSION=vX.Y.Z build/lxc/build-template.sh
```

Expected output:

```text
dist/<app-name>-debian12-mariadb-amd64-vX.Y.Z.tar.zst
```

## GitHub Release Workflow

Use a workflow that:

- Builds on manual dispatch.
- Builds on pushed `v*` tags.
- Uploads the template as an artifact for manual runs.
- Creates or updates a GitHub Release for `v*` tags.
- Attaches the `.tar.zst` template asset to the release.

Before tagging, confirm the worktree:

```bash
git status --short
git log --oneline -5
```

Release sequence:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
gh run list --workflow lxc-template.yml --limit 5
gh release view vX.Y.Z
```

## Proxmox Install Test

Download the release asset on the Proxmox host:

```bash
wget -O /var/lib/vz/template/cache/<template-name>.tar.zst \
  https://github.com/<owner>/<repo>/releases/download/vX.Y.Z/<template-name>.tar.zst
```

Create a CT:

```bash
pct create <ctid> local:vztmpl/<template-name>.tar.zst \
  --hostname <app-name> \
  --cores 1 \
  --memory 1024 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --start 1
```

If the Proxmox UI is preferred, upload or download the `.tar.zst` into `Storage > CT Templates`, then create a CT from that template.

## Validation Commands

Inside the CT:

```bash
systemctl status <app-name>-firstboot
systemctl status mariadb
systemctl status <app-name>
curl -I http://127.0.0.1:8000/login
```

Expected result:

- Firstboot is `active (exited)` or disabled after success.
- MariaDB is active when bundled in the CT.
- The application service is active.
- The login endpoint returns HTTP 200 or another expected application response.

From another host on the same network:

```bash
curl -I http://<ct-ip>:8000/login
```

## Troubleshooting

If Proxmox CT creation fails with missing network files, the template probably did not preserve the Proxmox base template network layout. Rebase the build on the official Proxmox Debian standard template.

If apt fails in chroot with DNS errors, copy a valid resolver into the chroot during the build and restore it afterward.

If apt or package scripts fail with `/dev/null` or `/dev/tty` errors, create the basic device nodes before installing packages.

If firstboot succeeds but the application is unreachable, check:

```bash
journalctl -u <app-name>-firstboot --no-pager
journalctl -u <app-name> --no-pager
ss -ltnp
```

If the app works inside the CT but not externally, keep the template unchanged and debug routing, firewall, bridge, DNS or reverse proxy outside this skill.
