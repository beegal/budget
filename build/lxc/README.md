# Proxmox LXC Template

This directory contains the files used to build a native Proxmox CT template for Personal Finance.

The build starts from the official Proxmox Debian 12 standard template and adds:

- MariaDB server inside the container.
- Personal Finance installed in `/opt/personal-finance/app`.
- A Python virtual environment with application dependencies.
- A `personal-finance-firstboot.service` unit that generates secrets, creates the MariaDB database/user and initializes the schema on first boot.
- A `personal-finance.service` unit that runs Uvicorn on port `8000`.

No database password or authentication secret is stored in the template. First boot writes generated values to:

```text
/etc/personal-finance/personal-finance.env
```

After first boot, browse to:

```text
http://<container-ip>:8000
```

The current known-good release asset is:

```text
https://github.com/beegal/budget/releases/download/v0.1.5/personal-finance-debian12-mariadb-amd64-v0.1.5.tar.zst
```

Build the same version locally from the repository root:

```bash
VERSION=v0.1.5 build/lxc/build-template.sh
```
