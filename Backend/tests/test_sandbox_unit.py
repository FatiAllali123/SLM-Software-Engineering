"""Tests du bac à sable QUI NE NÉCESSITENT PAS Docker.

Ils vérifient (1) la commande Docker construite, (2) la gestion du temps et de la taille de sortie
avec de simples programmes Python, (3) les erreurs quand Docker est absent.
Les tests avec un vrai conteneur sont dans test_sandbox_docker.py.
"""
import sys

import pytest

from Backend.app import sandbox
from Backend.app.config import Settings, get_settings
from Backend.app.errors import AppError


# ---------- 1. La commande docker run contient TOUTES les protections ----------
def _value_after(command, flag):
    return command[command.index(flag) + 1]


def test_command_has_all_protections():
    command = sandbox.build_command(Settings(), "slm-sbx-test")
    assert command[:2] == ["docker", "run"]
    assert "--rm" in command
    assert _value_after(command, "--network") == "none"
    assert _value_after(command, "--memory") == "256m"
    assert _value_after(command, "--memory-swap") == "256m"      # pas de swap
    assert _value_after(command, "--cpus") == "0.5"
    assert _value_after(command, "--pids-limit") == "64"
    assert "--read-only" in command
    assert _value_after(command, "--tmpfs") == "/tmp:rw,noexec,nosuid,size=16m"
    assert _value_after(command, "--cap-drop") == "ALL"
    assert _value_after(command, "--security-opt") == "no-new-privileges"
    assert _value_after(command, "--user") == "10001:10001"
    assert _value_after(command, "--pull") == "never"
    assert _value_after(command, "--name") == "slm-sbx-test"
    assert _value_after(command, "--label") == "slm-sandbox=1"


def test_command_never_shares_files_or_privileges():
    command = sandbox.build_command(Settings(), "x")
    forbidden = {"-v", "--volume", "--mount", "--privileged", "--network=host", "--pid", "--ipc",
                 "-e", "--env", "--env-file", "-p", "--publish", "--device"}
    assert not forbidden.intersection(command)
    assert "host" not in command


def test_command_ends_with_image_then_isolated_python_reading_stdin():
    settings = Settings()
    command = sandbox.build_command(settings, "x")
    assert command[-4:] == [settings.sandbox_image, "python", "-I", "-"]


def test_command_uses_limits_from_settings():
    settings = Settings(max_memory_mb=128, sandbox_cpus=1.0, sandbox_pids_limit=32, sandbox_tmpfs_mb=8)
    command = sandbox.build_command(settings, "x")
    assert _value_after(command, "--memory") == "128m"
    assert _value_after(command, "--cpus") == "1.0"
    assert _value_after(command, "--pids-limit") == "32"
    assert "size=8m" in _value_after(command, "--tmpfs")


# ---------- 2. Gestion du temps, de la sortie et de l'entrée ----------
class _Killed:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


def _run(code, stdin=b"", wall=10, cap=1_000_000):
    killed = _Killed()
    outcome = sandbox._execute([sys.executable, "-c", code], stdin, wall, cap, killed)
    return outcome, killed


def test_execute_sends_stdin_and_reads_stdout():
    outcome, killed = _run("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read().upper())", stdin=b"abc")
    assert outcome.stdout == b"ABC"
    assert outcome.returncode == 0
    assert not outcome.timed_out and not outcome.output_overflow
    assert killed.calls == 0


def test_execute_keeps_exit_code_and_stderr():
    outcome, _ = _run("import sys; sys.stderr.write('oups'); sys.exit(3)")
    assert outcome.returncode == 3
    assert outcome.stderr == b"oups"


def test_execute_stops_a_program_that_runs_too_long():
    outcome, killed = _run("import time; time.sleep(30)", wall=1)
    assert outcome.timed_out is True
    assert outcome.returncode is None
    assert killed.calls == 1
    assert outcome.duration_ms < 6000


def test_execute_stops_a_program_that_prints_too_much():
    code = "import sys\nwhile True:\n    sys.stdout.write('A' * 1000)\n    sys.stdout.flush()"
    outcome, killed = _run(code, wall=20, cap=10_000)
    assert outcome.output_overflow is True
    assert outcome.returncode is None
    assert len(outcome.stdout) <= 10_000          # jamais plus que la limite en mémoire
    assert killed.calls == 1
    assert outcome.duration_ms < 15000


def test_execute_survives_a_program_that_never_reads_its_input():
    outcome, _ = _run("pass", stdin=b"x" * 5_000_000)
    assert outcome.returncode == 0


def test_execute_missing_program_is_a_sandbox_error():
    with pytest.raises(AppError) as error:
        sandbox._execute(["programme-qui-nexiste-pas-xyz"], b"", 5, 1000, lambda: None)
    assert error.value.code == "SANDBOX_ERROR"


# ---------- 3. run_code : modes et erreurs ----------
def test_fake_mode_runs_nothing(monkeypatch):
    monkeypatch.setenv("SANDBOX_MODE", "fake")
    result = sandbox.run_code("raise SystemExit(7)", 5)
    assert result.exit_code == 0
    assert "fictive" in result.stdout


def test_unknown_mode_is_refused(monkeypatch):
    monkeypatch.setenv("SANDBOX_MODE", "local")     # il n'existe AUCUN mode "local"
    with pytest.raises(AppError) as error:
        sandbox.run_code("print(1)", 5)
    assert error.value.code == "SANDBOX_ERROR"


def test_default_mode_is_docker(monkeypatch):
    monkeypatch.delenv("SANDBOX_MODE", raising=False)
    assert get_settings().sandbox_mode == "docker"


def test_docker_missing_is_a_sandbox_error_never_a_local_run(monkeypatch, tmp_path):
    marker = tmp_path / "marqueur.txt"
    monkeypatch.setenv("SANDBOX_MODE", "docker")
    monkeypatch.setenv("DOCKER_BINARY", "docker-qui-nexiste-pas-xyz")
    code = f"open(r'{marker}', 'w').write('lance sur la machine')"
    with pytest.raises(AppError) as error:
        sandbox.run_code(code, 5)
    assert error.value.code == "SANDBOX_ERROR"
    assert not marker.exists()                        # le code n'a PAS été exécuté ailleurs


@pytest.mark.parametrize("text,expected", [
    ("docker: Error response from daemon: No such image: slm-sandbox:1.", True),
    ("error during connect: this error may indicate that the docker daemon is not running", True),
    ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", True),
    ("Traceback (most recent call last):\n  File \"<stdin>\", line 1", False),
    ("", False),
])
def test_docker_error_detection(text, expected):
    assert sandbox._looks_like_docker_error(text) is expected


def test_docker_ready_is_false_when_docker_is_missing(monkeypatch):
    monkeypatch.setenv("DOCKER_BINARY", "docker-qui-nexiste-pas-xyz")
    assert sandbox.docker_ready() is False
