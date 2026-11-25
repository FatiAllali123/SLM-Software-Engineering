"""Bac à sable d'exécution du code (étape 4).

Le code est exécuté dans un conteneur Docker jetable :
  - aucun réseau, 256 Mo de mémoire (sans swap), 0,5 cœur, 64 processus au maximum ;
  - système de fichiers en lecture seule (sauf un petit /tmp sans exécution) ;
  - utilisateur sans droits (uid 10001), aucune "capability" Linux, pas d'élévation de privilèges ;
  - aucun dossier de l'ordinateur n'est partagé : le code arrive par l'entrée standard ;
  - aucune variable d'environnement de l'ordinateur n'est transmise ;
  - temps maximal : timeout_s (+ un court délai de démarrage), puis le conteneur est détruit ;
  - sortie limitée en taille : si le programme affiche trop, le conteneur est arrêté.

RÈGLE DE SÉCURITÉ : il n'existe AUCUN mode qui lance le code directement sur l'ordinateur.
Si Docker est absent ou éteint, on renvoie l'erreur SANDBOX_ERROR.

Le reste du backend ne connaît que run_code(code, timeout_s).
"""
import logging
import subprocess
import threading
import time
import uuid
from typing import Callable, List, NamedTuple, Optional

from .config import Settings, get_settings
from .errors import AppError
from .schemas import ExecuteResult

logger = logging.getLogger("backend")

CONTAINER_LABEL = "slm-sandbox=1"   # sert à retrouver d'éventuels conteneurs oubliés
SANDBOX_USER = "10001:10001"

_DOCKER_ERROR_MARKERS = (
    "docker:",
    "error during connect",
    "cannot connect to the docker daemon",
    "unable to find image",
    "no such image",
    "error response from daemon",
)


# ---------------------------------------------------------------------------
# Porte d'entrée utilisée par le reste du backend
# ---------------------------------------------------------------------------
def run_code(code: str, timeout_s: int) -> ExecuteResult:
    settings = get_settings()
    if settings.sandbox_mode == "fake":
        return _fake_result()
    if settings.sandbox_mode == "docker":
        return _run_in_docker(code, timeout_s, settings)
    raise AppError("SANDBOX_ERROR", "Mode de bac à sable inconnu.")


def _fake_result() -> ExecuteResult:
    """Réponse fictive : n'exécute rien (tests, ou SANDBOX_MODE=fake)."""
    return ExecuteResult(
        stdout="[exécution fictive : le code n'a pas été lancé]\n",
        stderr="",
        exit_code=0,
        timed_out=False,
        duration_ms=0,
    )


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
def build_command(settings: Settings, container_name: str) -> List[str]:
    """Construit la commande `docker run` avec TOUTES les protections."""
    memory = f"{settings.max_memory_mb}m"
    return [
        settings.docker_binary, "run",
        "--rm",                                   # détruit le conteneur à la fin
        "-i",                                     # le code arrive par l'entrée standard
        "--name", container_name,
        "--label", CONTAINER_LABEL,
        "--pull", "never",                        # n'utilise que l'image locale
        "--network", "none",                      # aucun réseau
        "--memory", memory,
        "--memory-swap", memory,                  # pas de swap : même valeur que la mémoire
        "--cpus", str(settings.sandbox_cpus),
        "--pids-limit", str(settings.sandbox_pids_limit),
        "--ulimit", "nofile=256:256",
        "--read-only",                            # système de fichiers en lecture seule
        "--tmpfs", f"/tmp:rw,noexec,nosuid,size={settings.sandbox_tmpfs_mb}m",
        "--cap-drop", "ALL",                      # aucune capacité Linux
        "--security-opt", "no-new-privileges",
        "--user", SANDBOX_USER,                   # jamais administrateur
        settings.sandbox_image,
        "python", "-I", "-",                      # mode isolé, code lu sur l'entrée standard
    ]


def _run_in_docker(code: str, timeout_s: int, settings: Settings) -> ExecuteResult:
    name = "slm-sbx-" + uuid.uuid4().hex[:12]
    command = build_command(settings, name)
    outcome = _execute(
        command,
        code.encode("utf-8"),
        wall_timeout_s=timeout_s + settings.sandbox_startup_grace_s,
        max_output_bytes=settings.sandbox_max_output_bytes,
        on_kill=lambda: _remove_container(settings, name),
    )
    stdout = outcome.stdout.decode("utf-8", errors="replace")
    stderr = outcome.stderr.decode("utf-8", errors="replace")

    # Code 125 = c'est Docker lui-même qui a échoué (et non le programme exécuté)
    if outcome.returncode == 125 and _looks_like_docker_error(stderr):
        logger.error("Docker a refusé de lancer le conteneur : %s", stderr[:500])
        raise AppError(
            "SANDBOX_ERROR",
            "Le bac à sable n'a pas pu démarrer (Docker est-il lancé et l'image construite ?).",
        )

    if outcome.output_overflow:
        stderr += "\n[sortie trop volumineuse : exécution arrêtée]\n"

    return ExecuteResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=outcome.returncode,       # None si le programme a été arrêté de force
        timed_out=outcome.timed_out,
        duration_ms=outcome.duration_ms,
    )


def _looks_like_docker_error(stderr: str) -> bool:
    head = stderr[:600].lower()
    return any(marker in head for marker in _DOCKER_ERROR_MARKERS)


def _remove_container(settings: Settings, name: str) -> None:
    """Détruit le conteneur par son nom. On réessaie : il peut ne pas être encore créé."""
    for _ in range(5):
        try:
            result = subprocess.run(
                [settings.docker_binary, "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if result.returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(0.4)
    logger.error("Impossible de détruire le conteneur %s", name)


def docker_ready(settings: Optional[Settings] = None) -> bool:
    """Vrai si Docker répond ET si l'image du bac à sable existe (utile pour les tests)."""
    settings = settings or get_settings()
    try:
        result = subprocess.run(
            [settings.docker_binary, "image", "inspect", settings.sandbox_image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Lancement d'un processus avec limite de temps et de sortie
# ---------------------------------------------------------------------------
class _Outcome(NamedTuple):
    stdout: bytes
    stderr: bytes
    returncode: Optional[int]    # None si le processus a été arrêté de force
    timed_out: bool
    output_overflow: bool
    duration_ms: int


def _execute(
    command: List[str],
    stdin_bytes: bytes,
    wall_timeout_s: float,
    max_output_bytes: int,
    on_kill: Callable[[], None],
) -> _Outcome:
    """Lance `command`, lui envoie stdin_bytes, lit sa sortie (taille limitée)
    et l'arrête si le temps est dépassé ou si elle affiche trop."""
    start = time.perf_counter()
    try:
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except OSError:
        logger.exception("Impossible de lancer la commande du bac à sable")
        raise AppError(
            "SANDBOX_ERROR",
            "Le bac à sable n'a pas pu démarrer (Docker est-il installé et lancé ?).",
        )

    overflow = threading.Event()
    out_chunks: List[bytes] = []
    err_chunks: List[bytes] = []
    workers = [
        threading.Thread(target=_feed, args=(proc.stdin, stdin_bytes), daemon=True),
        threading.Thread(target=_drain, args=(proc.stdout, max_output_bytes, out_chunks, overflow), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, max_output_bytes, err_chunks, overflow), daemon=True),
    ]
    for worker in workers:
        worker.start()

    timed_out = False
    deadline = start + wall_timeout_s
    while proc.poll() is None:
        if overflow.is_set():
            break
        if time.perf_counter() >= deadline:
            timed_out = True
            break
        time.sleep(0.02)

    killed = timed_out or overflow.is_set()
    if killed:
        try:
            on_kill()
        finally:
            _terminate(proc)
    else:
        proc.wait()

    for worker in workers:
        worker.join(timeout=2)

    return _Outcome(
        stdout=b"".join(out_chunks),
        stderr=b"".join(err_chunks),
        returncode=None if killed else proc.returncode,
        timed_out=timed_out,
        output_overflow=overflow.is_set(),
        duration_ms=int((time.perf_counter() - start) * 1000),
    )


def _feed(stream, data: bytes) -> None:
    """Envoie le code au processus puis ferme son entrée."""
    try:
        stream.write(data)
        stream.flush()
    except (OSError, ValueError):
        pass          # le processus s'est terminé sans lire tout le code
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _drain(stream, limit: int, chunks: List[bytes], overflow: threading.Event) -> None:
    """Lit la sortie, garde au plus `limit` octets, signale un dépassement."""
    total = 0
    try:
        while True:
            chunk = stream.read1(65536)
            if not chunk:
                break
            if total < limit:
                chunks.append(chunk[: limit - total])
            total += len(chunk)
            if total > limit:
                overflow.set()
    except (OSError, ValueError):
        pass


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.error("Le processus du bac à sable ne répond pas à l'arrêt")
