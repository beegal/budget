# Proxmox LXC Template

This directory contains the files used to build a native Proxmox CT template for Personal Finance.

The template includes:

- Debian 12 root filesystem.
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
