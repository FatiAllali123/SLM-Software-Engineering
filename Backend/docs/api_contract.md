# Contrat d'API du backend (v1.0)

> **Statut : proposé, en attente du « OK » de B et D.**
> **Responsable du document : Fati (rôle C, backend et sécurité).**
> Toute modification passe par une pull request qui modifie ce fichier, avec une ligne ajoutée au [journal des changements](#12-journal-des-changements).

## 1. Pourquoi ce document

Le backend (FastAPI) est le point central : l'interface React, les agents et le modèle s'y branchent.
Ce contrat fixe **ce que chacun doit offrir et recevoir**, pour que A, B, C et D avancent en parallèle sans se bloquer.

| Rôle | Dossier | Ce qu'il doit respecter dans ce contrat |
|---|---|---|
| **C** (backend et sécurité) | `backend/` | Sections 3 à 8 : portes, formats JSON, erreurs, sécurité |
| **B** (service du modèle et évaluation) | `models/` | Section 9 : `LLMClient` |
| **D** (agents) | `agents/` | Section 10 : `run_pipeline` et section 11 : `mode` |
| **A** (fine-tuning) | `finetuning/` | Fournit le modèle fine-tuné que B branche derrière `LLMClient` |

## 2. Schéma général

```
Client (futur écran React, ou page /docs de FastAPI)
        │  requête JSON
        ▼
backend/  (C)  ── filtre de secrets ── validation ── journal d'audit
        │
        ├── /analyze, /generate-tests, /review
        │        └── agents.run_pipeline(...)            (D)
        │                  └── LLMClient.generate(...)   (B)  ──►  modèle (stub ou réel)
        │
        └── /execute  ──►  bac à sable (sandbox)         (C)
```

## 3. Les portes (endpoints)

| Méthode | Chemin | Rôle | Passe par les agents ? |
|---|---|---|---|
| `GET` | `/health` | Vérifier que le serveur répond | Non |
| `POST` | `/analyze` | Analyser du code (bugs, qualité, vulnérabilités) | Oui |
| `POST` | `/generate-tests` | Générer des tests unitaires | Oui |
| `POST` | `/review` | Faire une revue de code | Oui |
| `POST` | `/execute` | Exécuter du code dans le bac à sable | Non |

## 4. Format de la requête

Pour `/analyze`, `/generate-tests`, `/review` :

```json
{
  "code": "def add(a, b):\n    return a + b",
  "language": "python",
  "mode": "single_agent"
}
```

| Champ | Type | Obligatoire | Valeurs | Défaut |
|---|---|---|---|---|
| `code` | texte | oui | Code source à traiter, taille maximale : voir section 8 | |
| `language` | texte | non | `python` (seule valeur acceptée en v1) | `python` |
| `mode` | texte | non | `single_agent` ou `multi_agent` | `single_agent` |

Pour `/execute` :

```json
{
  "code": "print('bonjour')",
  "language": "python",
  "timeout_s": 5
}
```

| Champ | Type | Obligatoire | Valeurs | Défaut |
|---|---|---|---|---|
| `code` | texte | oui | Code à exécuter | |
| `language` | texte | non | `python` | `python` |
| `timeout_s` | nombre | non | De 1 jusqu'au maximum de la section 8 | 10 |

Le champ `mode` est ignoré par `/execute` et `/health`.

## 5. Format de la réponse (enveloppe commune)

**Toutes** les portes (sauf `/health`) répondent avec la même enveloppe, succès comme erreur :

```json
{
  "request_id": "a1b2c3d4e5f6",
  "status": "ok",
  "task": "analyze",
  "result": {
    "issues": [
      {"line": 2, "severity": "low", "message": "Pas de docstring"}
    ],
    "summary": "1 problème mineur"
  },
  "metrics": {
    "model": "qwen2.5-coder-1.5b",
    "precision": "fp16",
    "input_tokens": 120,
    "output_tokens": 45,
    "latency_ms": 830,
    "llm_calls": 1,
    "mode": "single_agent"
  },
  "error": null
}
```

| Champ | Contenu |
|---|---|
| `request_id` | Identifiant unique de la requête (généré par le backend). Le même identifiant est écrit dans le journal d'audit. |
| `status` | `ok`, `error`, `blocked` (refusé par une règle de sécurité) ou `needs_approval` (réservé pour plus tard : validation humaine). |
| `task` | `analyze`, `generate_tests`, `review` ou `execute`. |
| `result` | Contenu selon la porte (section 5.1). `null` si `status` n'est pas `ok`. |
| `metrics` | Mesures utilisées par l'évaluation et le LLMOps. `null` pour `/execute`. |
| `error` | `null` si tout va bien, sinon `{"code": "...", "message": "..."}` (section 6). |

### 5.1 Contenu de `result` selon la porte

**`/analyze`**
```json
{
  "issues": [
    {"line": 2, "severity": "low", "category": "quality", "message": "Pas de docstring"}
  ],
  "summary": "1 problème mineur"
}
```
- `severity` : `low`, `medium` ou `high`.
- `category` : `bug`, `vulnerability`, `quality` ou `style`.
- `line` : numéro de ligne (à partir de 1) ou `null` si non applicable.
- `issues` peut être une liste vide (aucun problème trouvé).

**`/generate-tests`**
```json
{
  "tests": "def test_add():\n    assert add(1, 2) == 3\n",
  "test_count": 1,
  "summary": "1 test généré"
}
```
- `tests` : code Python des tests, en texte.

**`/review`**
```json
{
  "findings": [
    {"line": 1, "severity": "low", "message": "Nom de fonction peu explicite"}
  ],
  "verdict": "approve_with_comments",
  "summary": "Code correct, quelques remarques"
}
```
- `verdict` : `approve`, `approve_with_comments` ou `request_changes`.

**`/execute`**
```json
{
  "stdout": "bonjour\n",
  "stderr": "",
  "exit_code": 0,
  "timed_out": false,
  "duration_ms": 120
}
```
- Un dépassement de temps n'est **pas une erreur du serveur** : la réponse est `status: "ok"` avec `timed_out: true`.
- `stdout` et `stderr` sont tronqués à 10 000 caractères et passent par le filtre de secrets.

### 5.2 Réponse de `GET /health`

```json
{"status": "ok", "version": "1.0", "llm_backend": "stub"}
```
`llm_backend` vaut `stub` ou `real`.

## 6. Erreurs

Une erreur renvoie la même enveloppe avec `status: "error"` (ou `"blocked"`), `result: null` et un objet `error` :

```json
{
  "request_id": "a1b2c3d4e5f6",
  "status": "error",
  "task": "analyze",
  "result": null,
  "metrics": null,
  "error": {"code": "CODE_TOO_LARGE", "message": "Le code dépasse 50 Ko."}
}
```

| Code d'erreur | Statut HTTP | Sens |
|---|---|---|
| `INVALID_INPUT` | 400 | Requête mal formée (champ manquant, mauvais type, `mode` inconnu) |
| `UNSUPPORTED_LANGUAGE` | 400 | Langage autre que `python` |
| `CODE_TOO_LARGE` | 413 | Code plus grand que la limite |
| `TOOL_NOT_ALLOWED` | 403 | Un agent a demandé un outil absent de la liste blanche (`status: "blocked"`) |
| `SANDBOX_ERROR` | 500 | Le bac à sable n'a pas pu démarrer ou a échoué |
| `MODEL_ERROR` | 502 | `LLMClient` a échoué ou n'a pas répondu |
| `INTERNAL_ERROR` | 500 | Erreur inattendue |

Règles :
- Le backend ne renvoie **jamais** une trace d'erreur Python brute à l'utilisateur.
- Les secrets détectés dans le code sont **masqués** (`[SECRET_MASQUÉ]`), la requête n'est pas refusée pour autant. Le journal d'audit note qu'un secret a été masqué.

## 7. Règles de sécurité appliquées par le backend

1. **Filtre de secrets** : appliqué au code reçu **avant** tout envoi au modèle ou aux agents, et à toute réponse **avant** son envoi au client.
2. **Validation des entrées** : taille, langage, format JSON, valeurs de `mode`.
3. **Exécution isolée** : tout code exécuté (y compris celui produit par les agents) passe par le bac à sable, jamais dans le processus du serveur.
4. **Liste blanche d'outils** : un agent ne peut appeler que les outils de la section 8.
5. **Moindres droits** : lecture seule par défaut. Aucune écriture de fichier, commande système ou `git push` sans validation humaine (prévu en phase 2, `status: "needs_approval"`).
6. **Journal d'audit** : une ligne dans SQLite pour chaque appel, même refusé (identifiant, date, acteur, action, empreinte du code, décision, raison, durée). Le code complet n'est pas stocké, seulement son empreinte.

## 8. Limites et configuration par défaut

> **À confirmer avec D.** Ces valeurs sont dans `backend/app/config.py`, donc faciles à changer.

| Paramètre | Valeur par défaut |
|---|---|
| Taille maximale du code reçu | 50 Ko |
| Temps maximal d'exécution | 10 secondes |
| Mémoire maximale du bac à sable | 256 Mo |
| Réseau dans le bac à sable | Aucun |
| Outils autorisés pour les agents | `analyze_code`, `generate_tests`, `review_code`, `execute_code` |
| Choix du modèle | Variable d'environnement `LLM_BACKEND` : `stub` (défaut) ou `real` |

## 9. `LLMClient` (à implémenter par B)

Le backend et les agents n'appellent **jamais** le modèle directement : ils passent par `LLMClient`. Ainsi, on peut remplacer le faux modèle par le vrai (de base, fine-tuné, fp16 ou nf4) sans toucher au reste.

**Emplacement proposé :** `models/llm_client.py`

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str            # texte généré
    input_tokens: int    # nombre de tokens du prompt
    output_tokens: int   # nombre de tokens générés
    latency_ms: int      # durée totale de l'appel
    model: str           # ex. "qwen2.5-coder-1.5b" ou "stub"
    precision: str       # ex. "fp16", "nf4" ou "none" pour le stub


class LLMClient(Protocol):
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> LLMResponse:
        ...
```

Règles :
- `generate` renvoie toujours un `LLMResponse` rempli. En cas d'échec, elle **lève une exception** que le backend transforme en `MODEL_ERROR`.
- `temperature=0.0` doit donner un résultat reproductible autant que possible (important pour l'évaluation).
- Deux implémentations sont attendues :
  - `StubLLMClient` : renvoie une réponse **fixe et instantanée** (`model="stub"`, `precision="none"`, tokens estimés par le nombre de mots). Sert au développement et aux tests, sans GPU.
  - `RealLLMClient` : charge le vrai modèle (de base ou avec adaptateur) et renvoie les vraies mesures.
- Une fonction `get_llm_client()` choisit l'implémentation selon `LLM_BACKEND`.

## 10. `run_pipeline` (à implémenter par D)

Le backend appelle les agents par une **simple fonction Python importée** (pas de service séparé).

**Emplacement proposé :** `agents/pipeline.py`

```python
def run_pipeline(
    task: str,       # "analyze", "generate_tests" ou "review"
    code: str,       # code déjà filtré par le backend
    language: str,   # "python"
    mode: str,       # "single_agent" ou "multi_agent"
    llm: "LLMClient",
) -> dict:
    ...
```

La fonction renvoie un dictionnaire :

```python
{
    "result": { ... },   # contenu exact de la section 5.1 selon "task"
    "metrics": {
        "input_tokens": 120,    # somme de tous les appels au modèle
        "output_tokens": 45,    # somme de tous les appels au modèle
        "latency_ms": 830,      # durée totale
        "llm_calls": 1          # nombre d'appels à llm.generate
    },
    "trace": [
        {"agent": "analysis", "step": "analyze", "input_tokens": 120,
         "output_tokens": 45, "latency_ms": 830}
    ]
}
```

Règles :
- `result` respecte **exactement** les champs de la section 5.1. Le backend valide ce format et renvoie `INTERNAL_ERROR` s'il est faux.
- `trace` liste les étapes des agents (une ligne par agent et par étape). Elle sert au journal d'audit et au LLMOps.
- Les agents utilisent **uniquement** `llm.generate` pour parler au modèle, et **uniquement** les outils de la liste blanche (section 8). Demander un outil interdit doit lever une exception `ToolNotAllowedError`, que le backend transforme en `TOOL_NOT_ALLOWED`.
- Tout code à exécuter passe par la fonction d'exécution isolée du backend, jamais par `exec`, `eval` ou `subprocess` dans le code des agents.
- Le backend ajoute lui-même `model`, `precision` et `mode` dans le champ `metrics` de l'enveloppe.

## 11. Le champ `mode` : un agent ou plusieurs

| Valeur | Comportement attendu |
|---|---|
| `single_agent` (défaut) | Un seul agent fait toute la tâche, en un ou quelques appels au modèle |
| `multi_agent` | Le pipeline LangGraph complet : analyse, tests, puis revue, avec plusieurs agents |

Ce champ permet de comparer les deux configurations sur **le même jeu de tâches** (question de recherche Q3) : taux de réussite, tokens consommés et latence. Il est donc **disponible dès la première version**, même si `multi_agent` n'est pas encore complet (dans ce cas, D peut le faire se comporter comme `single_agent` en attendant).

## 12. Journal des changements

| Version | Date | Changement | Auteur |
|---|---|---|---|
| 1.0 | 18/11/2026 | Première version proposée | C |

## 13. Validation

| Personne | Rôle | OK (date) |
|---|---|---|
| B | `LLMClient` | |
| D | `run_pipeline`, `mode`, limites et liste blanche | |
| A | Pour information | |
