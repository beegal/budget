#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

VERSION="${VERSION:-${GITHUB_REF_NAME:-local}}"
ARCH="${ARCH:-amd64}"
SUITE="${SUITE:-bookworm}"
MIRROR="${MIRROR:-http://deb.debian.org/debian}"
BUILD_DIR="${BUILD_DIR:-${REPO_ROOT}/dist/lxc-build}"
DIST_DIR="${DIST_DIR:-${REPO_ROOT}/dist}"
ROOTFS="${BUILD_DIR}/rootfs"
TEMPLATE_NAME="personal-finance-debian12-mariadb-${ARCH}-${VERSION}.tar.zst"
TEMPLATE_PATH="${DIST_DIR}/${TEMPLATE_NAME}"

need_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

run_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

need_command debootstrap
need_command tar
need_command zstd

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "Building Debian ${SUITE} rootfs in ${ROOTFS}"
run_root debootstrap --arch="$ARCH" --variant=minbase "$SUITE" "$ROOTFS" "$MIRROR"

echo "Preparing apt policy for image build"
run_root install -m 755 /dev/null "$ROOTFS/usr/sbin/policy-rc.d"
run_root sh -c "printf '#!/bin/sh\nexit 101\n' > '$ROOTFS/usr/sbin/policy-rc.d'"

echo "Installing base packages"
run_root chroot "$ROOTFS" /bin/sh -lc "
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        locales \
        mariadb-server \
        python3 \
        python3-pip \
        python3-venv \
        systemd \
        systemd-sysv
    apt-get clean
"

echo "Configuring locale"
run_root sh -c "printf 'en_US.UTF-8 UTF-8\nfr_FR.UTF-8 UTF-8\n' > '$ROOTFS/etc/locale.gen'"
run_root chroot "$ROOTFS" /bin/sh -lc "locale-gen"
run_root sh -c "printf 'LANG=en_US.UTF-8\n' > '$ROOTFS/etc/default/locale'"

echo "Creating application user and directories"
run_root chroot "$ROOTFS" /bin/sh -lc "
    useradd --system --home-dir /opt/personal-finance --shell /usr/sbin/nologin personal-finance
    mkdir -p /opt/personal-finance/app /opt/personal-finance/data /etc/personal-finance /usr/local/sbin
"

echo "Copying application files"
tar \
    --exclude='.git' \
    --exclude='.github' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='*.swp' \
    --exclude='.*.swp' \
    --exclude='data' \
    --exclude='dist' \
    --exclude='build' \
    --exclude='tests' \
    --exclude='Personnal-Budget*.xls' \
    --exclude='Personnal-Budget*.xlsx' \
    --exclude='budget.db' \
    --exclude='codex-context.md' \
    -C "$REPO_ROOT" -cf - . | run_root tar -C "$ROOTFS/opt/personal-finance/app" -xf -

echo "Installing application dependencies"
run_root chroot "$ROOTFS" /bin/sh -lc "
    cd /opt/personal-finance/app
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/pip install --no-cache-dir -r requirements.txt
"

echo "Installing systemd units and firstboot script"
run_root install -m 755 "$SCRIPT_DIR/personal-finance-firstboot" "$ROOTFS/usr/local/sbin/personal-finance-firstboot"
run_root install -m 644 "$SCRIPT_DIR/personal-finance-firstboot.service" "$ROOTFS/etc/systemd/system/personal-finance-firstboot.service"
run_root install -m 644 "$SCRIPT_DIR/personal-finance.service" "$ROOTFS/etc/systemd/system/personal-finance.service"
run_root mkdir -p "$ROOTFS/etc/systemd/system/multi-user.target.wants"
run_root ln -sf /lib/systemd/system/mariadb.service "$ROOTFS/etc/systemd/system/multi-user.target.wants/mariadb.service"
run_root ln -sf /etc/systemd/system/personal-finance-firstboot.service "$ROOTFS/etc/systemd/system/multi-user.target.wants/personal-finance-firstboot.service"
run_root ln -sf /etc/systemd/system/personal-finance.service "$ROOTFS/etc/systemd/system/multi-user.target.wants/personal-finance.service"

echo "Setting permissions"
run_root chroot "$ROOTFS" /bin/sh -lc "
    chown -R root:root /opt/personal-finance/app
    chown -R personal-finance:personal-finance /opt/personal-finance/data
    chmod 750 /etc/personal-finance
"

echo "Cleaning rootfs"
run_root rm -f "$ROOTFS/usr/sbin/policy-rc.d"
run_root chroot "$ROOTFS" /bin/sh -lc "
    rm -rf /tmp/* /var/tmp/* /var/lib/apt/lists/*
    : > /etc/machine-id
    rm -f /var/lib/dbus/machine-id
    find /opt/personal-finance/app -type d -name __pycache__ -prune -exec rm -rf {} +
    find /opt/personal-finance/app -type f -name '*.pyc' -delete
"

echo "Creating Proxmox CT template: ${TEMPLATE_PATH}"
run_root tar --numeric-owner -C "$ROOTFS" -cf - . | zstd -19 -T0 -o "$TEMPLATE_PATH"
run_root chown "$(id -u):$(id -g)" "$TEMPLATE_PATH" 2>/dev/null || true

echo "$TEMPLATE_PATH"
