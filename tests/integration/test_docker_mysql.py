from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "build" / "docker-compose.mysql.yml"


def docker_info(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "info"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def docker_environment() -> tuple[dict[str, str], str]:
    env = dict(os.environ)
    if docker_info(env).returncode == 0:
        return env, "127.0.0.1"
    if shutil.which("minikube") is None:
        return env, "127.0.0.1"

    docker_env = subprocess.run(
        ["minikube", "docker-env", "--shell", "sh"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if docker_env.returncode != 0:
        return env, "127.0.0.1"
    for line in docker_env.stdout.splitlines():
        line = line.strip()
        if line.startswith("export "):
            key, _separator, raw_value = line.removeprefix("export ").partition("=")
            env[key] = raw_value.strip().strip('"').strip("'")
        elif line.startswith("unset "):
            env.pop(line.removeprefix("unset ").strip(), None)

    minikube_ip = subprocess.run(
        ["minikube", "ip"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    host = minikube_ip.stdout.strip() if minikube_ip.returncode == 0 else "127.0.0.1"
    return env, host


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@unittest.skipUnless(os.environ.get("RUN_DOCKER_INTEGRATION") == "1", "Docker integration tests are opt-in")
class DockerMySQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is not available")
        docker_env, docker_host = docker_environment()
        docker_status = docker_info(docker_env)
        if docker_status.returncode != 0 and os.environ.get("CI") != "true":
            raise unittest.SkipTest(f"docker daemon is not available: {docker_status.stdout.strip()}")
        if docker_status.returncode != 0:
            raise AssertionError(f"docker daemon is not available:\n\n{docker_status.stdout}")
        cls.project_name = f"budget-it-{os.getpid()}"
        cls.port = free_port()
        cls.base_url = f"http://{docker_host}:{cls.port}"
        cls.env = {
            **docker_env,
            "BUDGET_HTTP_PORT": str(cls.port),
            "BUDGET_MYSQL_ROOT_PASSWORD": "integration-root-password",
            "BUDGET_MYSQL_PASSWORD": "integration-budget-password",
            "BUDGET_MYSQL_DATABASE": "budget_integration",
            "BUDGET_MYSQL_USER": "budget",
            "BUDGET_MYSQL_CREATE_DATABASE": "1",
        }
        cls.compose("up", "-d", "--build")
        cls.wait_for_http("/login", expected_status={200})

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "project_name"):
            cls.compose("down", "-v", "--remove-orphans", check=False)

    @classmethod
    def compose(cls, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["docker", "compose", "-p", cls.project_name, "-f", str(COMPOSE_FILE), *args],
            cwd=ROOT,
            env=cls.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if check and result.returncode != 0:
            raise AssertionError(f"docker compose {' '.join(args)} failed with code {result.returncode}\n\n{result.stdout}")
        return result

    @classmethod
    def wait_for_http(cls, path: str, expected_status: set[int], timeout: int = 180) -> None:
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            try:
                with urlopen(f"{cls.base_url}{path}", timeout=5) as response:
                    if response.status in expected_status:
                        return
                    last_error = f"HTTP {response.status}"
            except HTTPError as error:
                if error.code in expected_status:
                    return
                last_error = f"HTTP {error.code}"
            except (ConnectionResetError, TimeoutError, OSError, URLError) as error:
                last_error = str(error)
            time.sleep(2)
        logs = cls.compose("logs", "--no-color", check=False).stdout
        raise AssertionError(f"{path} did not become ready: {last_error}\n\n{logs}")

    def fetch(self, path: str) -> tuple[int, str]:
        with urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return response.status, response.read().decode("utf-8", errors="replace")

    def test_login_page_is_served_by_docker_app_with_mysql(self) -> None:
        status, body = self.fetch("/login")
        self.assertEqual(status, 200)
        self.assertIn("Personal Finance", body)

    def test_static_asset_is_served_from_docker_app(self) -> None:
        status, body = self.fetch("/static/js/core.js")
        self.assertEqual(status, 200)
        self.assertIn("function budgetConfig", body)
