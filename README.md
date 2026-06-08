# Personal Finance

Personal Finance is a local web application for managing budgets by periods, accounts and labels.

The project intentionally stays simple: FastAPI, server-rendered Jinja templates, vanilla JavaScript/CSS, and a SQLAlchemy Core database layer that can use SQLite, MySQL or a full SQLAlchemy database URL.

## Features

- Create and browse budget periods.
- Manage accounts, transaction labels and a monthly budget template.
- Enter transactions account by account.
- Edit table rows inline with `Enter` to confirm and `Esc` to cancel.
- Reorder accounts and transactions by drag and drop.
- View balances, income, expenses, transfers and per-label summaries.
- View a global multi-period summary.
- Instantiate scheduled budget entries into real account transactions.
- Import CSV/TSV transactions into an account.
- Filter transactions by period, account and label.
- Export/import one user's data from the UI.
- Export/import the full database from the CLI.
- Run with multiple users isolated by `user_id`.

## Project Stats

Approximate workspace stats, excluding local databases and temporary files:

- 164 application files.
- About 15,365 lines.
- 28 Python files, about 5,915 lines.
- 105 HTML/Jinja templates, about 3,730 lines.
- 5 JavaScript files, about 2,137 lines.
- 1 main CSS file, about 2,027 lines.
- 4 locale YAML files: `fr`, `en`, `de`, `nl`.
- 25 FastAPI routes.
- 10 local SVG icons.

## Data

The default SQLite database is:

```text
data/budget.sqlite3
```

It is not tracked by Git. On first startup, the application creates the schema only. Initial user data is created on the user's first authenticated request from:

```text
initial-data.yaml
```

The initial seed is tracked in `profile_seeded` with the key `initial-data`. This table is not a user preference table; it records one-shot bootstrap jobs so default data is not recreated if a user later deletes all their data.

Active tables:

- `users`
- `user_profiles`
- `profile_seeded`
- `period`
- `accounts`
- `transaction_labels`
- `transactions`
- `account_balances`
- `monthly_budget`
- `budget_schedule`

Business tables are scoped by `user_id`, and endpoints must always filter reads and writes by the authenticated user.

## Run Locally

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Equivalent Uvicorn command:

```bash
uvicorn app:application --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Tests

Python unit tests use `unittest`:

```bash
python3 -m unittest discover -s tests -v
```

Current tests cover date parsing and display, language preference detection, translation fallback, user profile defaults and SQLAlchemy database URL handling.

Docker/MySQL integration tests are opt-in because they build and run containers:

```bash
RUN_DOCKER_INTEGRATION=1 python3 -m unittest tests.integration.test_docker_mysql -v
```

The integration smoke test builds the application image, starts MySQL with Docker Compose, waits for the real HTTP application, verifies `/login`, verifies a static JavaScript asset, then removes the containers and volumes.
If Docker is not running locally, the integration test tries Minikube's Docker environment, equivalent to `eval "$(minikube docker-env)"`, and uses `minikube ip` for HTTP checks. If neither Docker nor Minikube is available locally, the test is skipped. In GitHub Actions it is executed with `RUN_DOCKER_INTEGRATION=1` and is expected to pass.

## Configuration

`config.yaml` declares supported UI languages and their default profile values:

```yaml
languages:
  - id: en
    label: English
    icon: GB
    locale: en_US.UTF-8
    date-format: mm/dd/yy
```

The supported date formats are:

- `jj/mm/yy`
- `mm/jj/yy`
- `yy-mm-jj`

The UI language is chosen from the long-lived `budget_language` cookie. On a first visit, the fallback comes from the browser `Accept-Language` header. Changing the UI language later does not rewrite an existing user's date or number preferences.

## Database Configuration

The application uses SQLAlchemy Core for business data connections and schema creation.

Simple SQLite configuration:

```bash
BUDGET_DB_BACKEND=sqlite
BUDGET_SQLITE_PATH=data/budget.sqlite3
```

Simple MySQL configuration:

```bash
BUDGET_DB_BACKEND=mysql
BUDGET_MYSQL_HOST=127.0.0.1
BUDGET_MYSQL_PORT=3306
BUDGET_MYSQL_DATABASE=budget
BUDGET_MYSQL_USER=budget
BUDGET_MYSQL_PASSWORD=...
```

Full SQLAlchemy URL configuration:

```bash
BUDGET_DATABASE_URL=sqlite:////path/to/budget.sqlite3 python3 app.py
BUDGET_DATABASE_URL=mysql+pymysql://budget:pass@127.0.0.1:3306/budget python3 app.py
```

`BUDGET_DATABASE_URL` takes precedence over `BUDGET_DB_BACKEND`. FastAPI Users reuses the same configuration and automatically switches to async drivers where needed, such as `sqlite+aiosqlite` or `mysql+aiomysql`.

Authentication settings:

```bash
BUDGET_AUTH_SECRET=change-me
BUDGET_AUTH_COOKIE_MAX_AGE=2592000
BUDGET_AUTH_COOKIE_SECURE=0
BUDGET_AUTH_LIFETIME=2592000
```

In production, `BUDGET_AUTH_SECRET` must be long and private. Set `BUDGET_AUTH_COOKIE_SECURE=1` behind HTTPS. If no auth secret is configured, the application generates a non-predictable secret at startup, which is safer than a hardcoded default but invalidates existing sessions on restart.

To create a MySQL database and user with the CLI:

```bash
BUDGET_DB_BACKEND=mysql \
BUDGET_MYSQL_ROOT_USER=root \
BUDGET_MYSQL_ROOT_PASSWORD=... \
BUDGET_MYSQL_DATABASE=budget \
BUDGET_MYSQL_USER=budget \
BUDGET_MYSQL_PASSWORD=... \
python3 budget_cli.py --db-backend mysql db create
```

MySQL databases are created with `CHARACTER SET utf8mb4 COLLATE utf8mb4_bin`. Tables inherit the database defaults. The schema does not force a table engine and lets MySQL use its default engine, normally InnoDB.

## UX Conventions

- `Enter` confirms inline edits.
- `Esc` cancels inline edits.
- `V` confirms, `X` cancels, `+` adds.
- Disabled actions remain visible and explain the reason in a tooltip.
- Empty multi-period or multi-account filters mean all values.
- Period/account dropdown filters refresh when the dropdown closes.
- Labels are grouped by the part before `-`, for example `Insurance - AG` is grouped under `Insurance`.
- Positive amounts are green, negative amounts are red and unknown values are grey.
- Open-ended period end dates are displayed as `current` in the active UI language.

## Main Pages

- `/`: period list and period creation.
- `/parameters`: accounts, labels, monthly budget, user export/import.
- `/period/<id>`: one period with summary, budget tab and visible accounts.
- `/period/<id>/import?account=<id>`: CSV/TSV import for an account.
- `/transactions`: global transaction view with filters and totals.
- `/summary`: global multi-period summary.
- `/profile`: user language and display preferences.
- `/admin`: admin-only user management.

## CSV Import

Expected columns:

```text
Date,Label,Amount,Comment
```

The import screen supports:

- `jj/mm/yy`
- `mm/jj/yy`
- `yy-mm-jj`
- CSV or TSV
- optional header row
- two-digit or four-digit years

Imported dates must be valid. Transactions outside the current period are imported but flagged as inconsistent where relevant.

## CLI

The CLI uses Typer and Rich.

Create an empty database:

```bash
python3 budget_cli.py db create
```

Use another SQLite file:

```bash
python3 budget_cli.py --db /tmp/budget-test.sqlite3 db create
python3 budget_cli.py --db /tmp/budget-test.sqlite3 users create user@example.com
```

Use a SQLAlchemy URL:

```bash
python3 budget_cli.py --database-url sqlite:////tmp/budget-test.sqlite3 db create
python3 budget_cli.py --database-url mysql+pymysql://budget:pass@127.0.0.1:3306/budget users list
```

User administration:

```bash
python3 budget_cli.py users list
python3 budget_cli.py users create user@example.com --password Password123!
python3 budget_cli.py users set-password user@example.com --password NewPassword123!
python3 budget_cli.py users enable user@example.com
python3 budget_cli.py users disable user@example.com
python3 budget_cli.py users make-admin user@example.com
python3 budget_cli.py users revoke-admin user@example.com
```

Full export/import:

```bash
python3 budget_cli.py export full backup-budget.xlsx
python3 budget_cli.py db create
python3 budget_cli.py import full backup-budget.xlsx
```

User export/import:

```bash
python3 budget_cli.py export user user@example.com budget-user.xlsx
python3 budget_cli.py import user user@example.com budget-user.xlsx
```

Full exports include `users`, `user_profiles`, `profile_seeded` and all business tables. User exports contain only one user's business data and are remapped to the target user on import.

## Docker

Build locally:

```bash
docker build -f build/Dockerfile -t beegal/budget:local .
```

With Minikube Docker:

```bash
eval "$(minikube docker-env)" && docker build -f build/Dockerfile -t beegal/budget:local .
```

Run:

```bash
docker run --rm -p 8000:8000 -v "$(pwd)/data:/app/data" beegal/budget:local
```

The container listens on port `8000` and uses `/app/data` for the default SQLite database.

### Docker With Managed MySQL

```bash
BUDGET_MYSQL_ROOT_PASSWORD=... \
BUDGET_MYSQL_PASSWORD=... \
docker compose -f build/docker-compose.mysql.yml up --build
```

Volumes:

- `budget-mysql-data`: MySQL data at `/var/lib/mysql`.
- `budget-db-config`: connection information at `/app/config/db.env`.
- `budget-app-data`: local app data.

### Docker With External MySQL

```bash
BUDGET_MYSQL_HOST=mysql.example.local \
BUDGET_MYSQL_DATABASE=budget \
BUDGET_MYSQL_USER=budget \
BUDGET_MYSQL_PASSWORD=... \
docker compose -f build/docker-compose.external-mysql.yml up --build
```

## Proxmox LXC Template

The project can build a native Proxmox CT template without Docker. The build starts from the official Proxmox Debian 12 standard template and adds Personal Finance plus MariaDB inside the container.

Template contents:

- Personal Finance installed in `/opt/personal-finance/app`.
- MariaDB installed locally in the CT.
- Application data directory at `/opt/personal-finance/data`.
- Runtime configuration at `/etc/personal-finance/personal-finance.env`.
- `personal-finance-firstboot.service` to generate secrets, create the MariaDB database/user and initialize the schema.
- `personal-finance.service` to run Uvicorn on port `8000`.

No password or auth secret is baked into the template. First boot generates them and stores them in `/etc/personal-finance/personal-finance.env`.

Build locally on a Debian/Ubuntu host:

```bash
sudo apt-get update
sudo apt-get install -y zstd
VERSION=v0.1.1 build/lxc/build-template.sh
```

The output is:

```text
dist/personal-finance-debian12-mariadb-amd64-v0.1.1.tar.zst
```

Install on Proxmox by downloading the release asset into the CT template cache:

```bash
wget -O /var/lib/vz/template/cache/personal-finance-debian12-mariadb-amd64-v0.1.1.tar.zst \
  https://github.com/beegal/budget/releases/download/v0.1.1/personal-finance-debian12-mariadb-amd64-v0.1.1.tar.zst
```

Create the CT:

```bash
pct create 120 local:vztmpl/personal-finance-debian12-mariadb-amd64-v0.1.1.tar.zst \
  --hostname personal-finance \
  --cores 1 \
  --memory 1024 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --start 1
```

After the first boot, browse to:

```text
http://<container-ip>:8000
```

In the Proxmox UI, the same `.tar.zst` can be downloaded through `Storage > CT Templates > Download from URL`, then selected when creating a CT.

## GitHub Actions

`.github/workflows/docker-image.yml` runs tests and Docker builds on pushes to `main`, pushes to `release`, pull requests and manual dispatches.

The workflow:

1. Checks out the repository.
2. Installs Python dependencies.
3. Runs Python unit tests.
4. Runs the Docker/MySQL integration smoke test.
5. Builds the Docker image.
6. Pushes the Docker image only when the ref is `refs/heads/release`.

Published image:

```text
beegal/budget:latest
beegal/budget:release-<github-run-number>
```

Required secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

`.github/workflows/lxc-template.yml` builds the native Proxmox LXC template. Manual runs upload the template as an artifact. Pushing a `v*` tag also creates or updates a GitHub Release and attaches the `.tar.zst` CT template.

### Run The GitHub Workflow Locally

The helper script uses the same workflow file through `act`:

```bash
brew install act
scripts/run-github-workflow-local.sh
```

By default the script simulates a push to `main`, so it validates tests and Docker setup without logging in to Docker Hub or publishing. It automatically applies Minikube's Docker environment when `minikube` is available.

To run the full workflow and allow the Docker push:

```bash
DOCKERHUB_USERNAME=... \
DOCKERHUB_TOKEN=... \
scripts/run-github-workflow-local.sh --push
```

`--push` simulates a push to `release`, so the workflow publishes both `latest` and the automatic `release-<github-run-number>` tag.

## Repository Layout

```text
.
├── app.py
├── auth.py
├── backend_messages.py
├── budget_cli.py
├── config.py
├── config.yaml
├── database.py
├── build/
│   ├── Dockerfile
│   └── lxc/
├── initial-data.yaml
├── i18n.py
├── user_preferences.py
├── web_helpers.py
├── components/
├── endpoints/
├── locales/
├── scripts/
├── static/
│   ├── app.js
│   ├── icons/
│   ├── js/
│   └── style.css
├── templates/
│   ├── de/
│   ├── en/
│   ├── fr/
│   └── nl/
└── tests/
```

`static/app.js` is only a compatibility pointer. Active frontend code lives in `static/js/`.
