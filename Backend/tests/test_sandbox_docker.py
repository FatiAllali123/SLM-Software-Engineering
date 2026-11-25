"""Tests du bac à sable AVEC un vrai conteneur Docker (code malveillant simulé).

Ils sont sautés automatiquement si Docker n'est pas lancé ou si l'image n'existe pas.
Construire l'image une fois :  docker build -t slm-sandbox:1 Backend/sandbox_image
Chaque test correspond à une ligne du tableau "menace -> protection -> test -> résultat" du rapport.
"""
import subprocess
import time

import pytest

from Backend.app import sandbox
from Backend.app.config import get_settings

pytestmark = pytest.mark.skipif(
    not sandbox.docker_ready(),
    reason="Docker n'est pas lancé ou l'image slm-sandbox:1 n'existe pas",
)


@pytest.fixture(autouse=True)
def real_docker_mode(monkeypatch):
    monkeypatch.setenv("SANDBOX_MODE", "docker")


def run(code, timeout_s=10):
    return sandbox.run_code(code, timeout_s)


def leftover_containers():
    settings = get_settings()
    out = subprocess.run(
        [settings.docker_binary, "ps", "-aq", "--filter", "label=slm-sandbox=1"],
        capture_output=True, text=True, timeout=20,
    )
    return out.stdout.split()


# ---------- Fonctionnement normal ----------
def test_normal_program():
    result = run("print('bonjour')")
    assert result.stdout == "bonjour\n"
    assert result.exit_code == 0
    assert result.timed_out is False


def test_exit_code_is_kept():
    assert run("import sys; sys.exit(3)").exit_code == 3


def test_python_error_goes_to_stderr():
    result = run("print(1/0)")
    assert result.exit_code == 1
    assert "ZeroDivisionError" in result.stderr


def test_syntax_error_goes_to_stderr():
    result = run("def (:")
    assert result.exit_code == 1
    assert "SyntaxError" in result.stderr


# ---------- Menaces ----------
def test_threat_infinite_loop_is_stopped_and_container_destroyed():
    result = run("while True:\n    pass", timeout_s=2)
    assert result.timed_out is True
    assert result.exit_code is None
    for _ in range(25):                      # le conteneur doit avoir disparu
        if not leftover_containers():
            break
        time.sleep(0.4)
    assert leftover_containers() == []


def test_threat_network_is_blocked():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=3)\n"
        "    print('RESEAU OUVERT')\n"
        "except OSError:\n"
        "    print('BLOCKED')\n"
    )
    assert run(code).stdout.strip() == "BLOCKED"


def test_threat_filesystem_is_read_only_except_tmp():
    code = (
        "try:\n"
        "    open('/essai.txt', 'w').write('x')\n"
        "    print('ECRITURE POSSIBLE')\n"
        "except OSError:\n"
        "    print('BLOCKED')\n"
        "open('/tmp/ok.txt', 'w').write('x')\n"
        "print('TMP_OK')\n"
    )
    assert run(code).stdout.split() == ["BLOCKED", "TMP_OK"]


def test_threat_memory_bomb_is_killed():
    code = "data = []\nwhile True:\n    data.append(b'x' * 10_000_000)"
    result = run(code, timeout_s=8)
    assert result.timed_out is False
    assert result.exit_code == 137            # tué par manque de mémoire (limite 256 Mo)


def test_threat_fork_bomb_is_limited():
    code = (
        "import os, time\n"
        "children = 0\n"
        "try:\n"
        "    for _ in range(300):\n"
        "        pid = os.fork()\n"
        "        if pid == 0:\n"
        "            time.sleep(4)\n"
        "            os._exit(0)\n"
        "        children += 1\n"
        "    print('NO_LIMIT', children)\n"
        "except OSError:\n"
        "    print('LIMITED', children)\n"
    )
    out = run(code, timeout_s=8).stdout.split()
    assert out[0] == "LIMITED"
    assert int(out[1]) < 70


def test_threat_runs_as_non_administrator():
    result = run("import os; print(os.getuid(), os.geteuid())")
    assert result.stdout.split() == ["10001", "10001"]


def test_threat_host_files_are_not_visible():
    code = (
        "paths = [r'C:\\Users', '/host_mnt', '/mnt/c', '/Users']\n"
        "import os\n"
        "print('VISIBLE' if any(os.path.exists(p) for p in paths) else 'BLOCKED')\n"
    )
    assert run(code).stdout.strip() == "BLOCKED"


def test_threat_host_environment_variables_are_not_leaked(monkeypatch):
    monkeypatch.setenv("SECRET_TEST_VAR", "do-not-leak-123")
    result = run("import os; print(os.environ.get('SECRET_TEST_VAR', 'ABSENT'))")
    assert result.stdout.strip() == "ABSENT"
    assert "do-not-leak-123" not in result.stdout + result.stderr


def test_threat_output_flood_is_cut():
    code = "import sys\nwhile True:\n    sys.stdout.write('A' * 1000)"
    result = run(code, timeout_s=8)
    assert result.exit_code is None
    assert len(result.stdout) <= get_settings().sandbox_max_output_bytes


# ---------- Branchement dans l'API ----------
def test_api_execute_really_runs_the_code():
    from fastapi.testclient import TestClient
    from Backend.app.main import app

    response = TestClient(app).post("/execute", json={"code": "print(2 + 2)", "timeout_s": 5})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["result"]["stdout"] == "4\n"
    assert body["metrics"] is None


def test_api_execute_masks_secrets_in_the_output():
    from fastapi.testclient import TestClient
    from Backend.app.main import app

    code = "print(\"API_KEY = 'abcd1234efgh5678'\")"
    body = TestClient(app).post("/execute", json={"code": code, "timeout_s": 5}).json()
    assert body["status"] == "ok"
    assert "abcd1234efgh5678" not in body["result"]["stdout"]
    assert "[SECRET_MASQUÉ]" in body["result"]["stdout"]
