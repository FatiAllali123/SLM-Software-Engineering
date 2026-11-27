"""Verifie que les tests generes par les agents (format pytest) peuvent etre lances dans le bac a sable."""
import pytest

from Backend.app import sandbox

pytestmark = pytest.mark.skipif(
    not sandbox.docker_ready(),
    reason="Docker n'est pas lance ou l'image du bac a sable n'existe pas",
)


@pytest.fixture(autouse=True)
def real_docker_mode(monkeypatch):
    monkeypatch.setenv("SANDBOX_MODE", "docker")


def build_runner(source: str, tests: str) -> str:
    """Code a envoyer a /execute : ecrit le module et ses tests dans /tmp, puis lance pytest."""
    return (
        "import pathlib, sys\n"
        f"pathlib.Path('/tmp/module_under_test.py').write_text({source!r})\n"
        f"pathlib.Path('/tmp/test_generated.py').write_text({tests!r})\n"
        "import pytest\n"
        "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '/tmp/test_generated.py']))\n"
    )


GOOD_SOURCE = "def add(a, b):\n    return a + b\n"
BAD_SOURCE = "def add(a, b):\n    return a - b\n"
TESTS = "from module_under_test import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


def test_pytest_is_installed_in_the_sandbox():
    result = sandbox.run_code("import pytest; print(pytest.__version__)", 10)
    assert result.exit_code == 0
    assert result.stdout.strip() == "8.3.4"


def test_generated_tests_that_pass_are_reported_as_passed():
    result = sandbox.run_code(build_runner(GOOD_SOURCE, TESTS), 15)
    assert result.exit_code == 0
    assert "1 passed" in result.stdout


def test_generated_tests_that_fail_are_reported_as_failed():
    result = sandbox.run_code(build_runner(BAD_SOURCE, TESTS), 15)
    assert result.exit_code == 1
    assert "1 failed" in result.stdout