"""
Execution isolee du code genere par les modeles.

ATTENTION : ce n'est PAS un vrai sandbox. Le code tourne dans un processus
separe avec un timeout (protege des boucles infinies et des crashs), mais il
garde les memes droits que le notebook (fichiers, reseau). Dans le rapport,
ecrire "execution isolee avec timeout", pas "sandbox".

COMMUN aux 4 membres.
"""
import multiprocessing
import queue as queue_module


def _run(code: str, test_code: str, q):
    try:
        namespace = {}
        exec(code, namespace)
        exec(test_code, namespace)
        q.put(("pass", None))
    except BaseException as e:  # inclut SystemExit, AssertionError...
        q.put(("fail", f"{type(e).__name__}: {e}"))


def run_tests(code: str, test_code: str, timeout: int = 5):
    """Retourne (status, error) avec status dans {"pass", "fail", "timeout"}."""
    q = multiprocessing.Queue()
    process = multiprocessing.Process(target=_run, args=(code, test_code, q))
    process.start()
    process.join(timeout)

    if process.is_alive():
        process.terminate()
        process.join()
        return "timeout", f"Depassement du delai de {timeout}s"

    try:
        return q.get(timeout=2)
    except queue_module.Empty:
        return "fail", "Aucun resultat renvoye (le processus a probablement plante)"
