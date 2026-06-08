#!/bin/sh
set -eu

WORKFLOW=".github/workflows/docker-image.yml"
EVENT_FILE="${TMPDIR:-/tmp}/budget-github-release-event.json"
ACT_IMAGE="${ACT_IMAGE:-catthehacker/ubuntu:act-latest}"
PUSH=0

usage() {
    cat <<'EOF'
Usage: scripts/run-github-workflow-local.sh [--push]

Run the GitHub Actions Docker workflow locally with act.

Default mode is safe: it simulates a push to main, so the workflow validates
tests and Docker build setup without logging in to Docker Hub or publishing.

Options:
  --push    Provide Docker Hub secrets from DOCKERHUB_USERNAME and
            DOCKERHUB_TOKEN, simulating a push to release and allowing the
            workflow to publish the image.

Requirements:
  - act
  - Docker access; on this project, Minikube Docker is used automatically when
    minikube is available.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --push)
            PUSH=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if ! command -v act >/dev/null 2>&1; then
    echo "act is required. Install it with: brew install act" >&2
    exit 1
fi

if command -v minikube >/dev/null 2>&1; then
    if MINIKUBE_DOCKER_ENV="$(minikube docker-env 2>/dev/null)"; then
        eval "$MINIKUBE_DOCKER_ENV"
    else
        echo "Minikube Docker environment is not available; using the current Docker environment." >&2
    fi
fi

if [ "$PUSH" -eq 1 ]; then
    EVENT_REF="refs/heads/release"
else
    EVENT_REF="refs/heads/main"
fi

cat > "$EVENT_FILE" <<EOF
{
  "ref": "${EVENT_REF}",
  "repository": {
    "default_branch": "main"
  }
}
EOF

set -- act push \
    -W "$WORKFLOW" \
    -e "$EVENT_FILE" \
    --container-architecture linux/amd64 \
    -P "ubuntu-latest=${ACT_IMAGE}"

if [ "$PUSH" -eq 1 ]; then
    : "${DOCKERHUB_USERNAME:?DOCKERHUB_USERNAME is required with --push}"
    : "${DOCKERHUB_TOKEN:?DOCKERHUB_TOKEN is required with --push}"
    set -- "$@" \
        -s "DOCKERHUB_USERNAME=${DOCKERHUB_USERNAME}" \
        -s "DOCKERHUB_TOKEN=${DOCKERHUB_TOKEN}"
else
    echo "Running in safe mode on refs/heads/main without Docker Hub secrets."
    echo "Use --push with DOCKERHUB_USERNAME and DOCKERHUB_TOKEN to publish."
fi

exec "$@"
