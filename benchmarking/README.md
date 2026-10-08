# Benchmarking des 4 SLM

Comparaison de **Qwen2.5-Coder-1.5B-Instruct**, **Phi-4-mini-instruct**, **Gemma-3-4B-it** et **SmolLM3-3B** sur des tâches de génie logiciel (génération de code, complétion, détection de bugs, explication, refactoring, génération de tests) et sur un sous-ensemble de HumanEval.

## Structure

```
benchmarking/
├── README.md
├── requirements.txt              [COMMUN]
├── .gitignore                    [COMMUN]
├── prompts.json                  [COMMUN] 15 prompts maison
├── config.json                   [COMMUN] paramètres de génération, modèles
├── humaneval_subset.json         [COMMUN] 20 problèmes HumanEval
├── grille_notation.md            [COMMUN] barème des notes manuelles
├── merge_results.py              [COMMUN] fusion finale
├── utils/
│   ├── safe_exec.py              [COMMUN] exécution isolée avec timeout
│   └── extract.py                [COMMUN] extraction du code de la réponse
├── notebooks/
│   ├── benchmark_template.ipynb  [COMMUN] modèle de départ
│   └── benchmark_<modele>.ipynb  [INDIVIDUEL] votre copie
├── results/
│   ├── benchmark_<modele>.csv    [INDIVIDUEL] 15 prompts
│   └── humaneval_<modele>.json   [INDIVIDUEL] score + détail HumanEval
├── environnement_<modele>.md     [INDIVIDUEL] généré par le notebook
└── (générés par merge_results.py)
    comparatif_final.csv, resume_final.csv,
    comparatif_humaneval.csv, detail_humaneval.csv
```

## Ce qui est identique pour les 4 membres

Modèle d'exécution : Google Colab, GPU T4, FP16. Génération greedy (`do_sample=False`), `max_new_tokens=512`, batch size 1, mêmes prompts, même extraction du code, même timeout (5 s), même chat template propre à chaque modèle (via `apply_chat_template`). Seule différence autorisée : le modèle (et `/no_think` pour SmolLM3, défini dans `config.json`).

**Personne ne modifie un fichier [COMMUN] sans l'accord du groupe.**

## Comment lancer (une personne = un modèle)

1. Colab : `Exécution > Modifier le type d'exécution > T4 GPU`.
2. Ouvrez `notebooks/benchmark_template.ipynb`, faites-en une copie nommée `benchmark_<modele>.ipynb`.
3. Cellule 1 : mettez l'URL de votre dépôt. Cellule du modèle : `MODEL_KEY = "qwen"`, `"phi"`, `"gemma"` ou `"smollm"`.
4. Gemma uniquement : acceptez les conditions du modèle sur Hugging Face, puis décommentez la cellule `login` (ne poussez jamais votre token sur GitHub).
5. `Exécution > Tout exécuter`.
6. Téléchargez les fichiers créés (`results/...`, `environnement_...md`) et ajoutez-les au dépôt (**uniquement les vôtres**).
7. Remplissez les colonnes manuelles de `results/benchmark_<modele>.csv` (voir ci-dessous).

## Colonnes de `benchmark_<modele>.csv`

| Colonne | Contenu |
|---|---|
| `id`, `task`, `prompt`, `response` | prompt et réponse brute du modèle |
| `gpu` | nom du GPU |
| `ttft_s` | temps pour générer le 1er token (s) |
| `latency_s` | temps total de génération (s) |
| `tokens_per_sec` | vitesse de génération |
| `input_tokens`, `output_tokens` | nombre de tokens |
| `gpu_memory_go` | pic de mémoire GPU (Go) |
| `auto_status` | `pass` / `fail` / `timeout` (P1-P4 : tests exécutés ; P5-P6 : réponse attendue présente) ; vide pour les autres tâches |
| `auto_error` | détail de l'erreur |
| `bug_label` | **manuel**, P7-P9 : `TP`, `FP`, `FN` ou `TN` |
| `note_qualite` | **manuel**, P10-P13 : note de 1 à 5 (voir `grille_notation.md`) |
| `hallucination` | **manuel**, réponses avec code : `oui` ou `non` |

Les tests générés (P14-P15) sont à noter à la main avec `note_qualite` (1 à 5).

## Fichier `humaneval_<modele>.json`

Champs communs : `model`, `gpu`, `precision`, `dataset`, `n_problems`, `n_pass`, `pass@1` (en %), `details` (une entrée par problème : statut, erreur, TTFT, latence, tokens/s, mémoire, réponse).

## Fusion finale (une seule personne)

Quand les 8 fichiers de `results/` existent et que les notes manuelles sont remplies :

```
python merge_results.py
```

## Limites à mentionner dans le rapport

- **HumanEval** : seulement 20 problèmes (les 20 premiers, pas un tirage aléatoire). Un problème = 5 points de pass@1 : les écarts sont peu significatifs et ne sont pas directement comparables aux scores publiés sur les 164 problèmes.
- **Détection de bugs** : seulement 3 prompts (précision/rappel/F1 indicatifs).
- **Exécution du code** : isolée avec timeout, mais ce n'est pas un sandbox (le code garde les droits du notebook).
- **Notes manuelles** : subjectives, même si cadrées par la grille.
- Les mesures de vitesse dépendent du GPU Colab attribué : vérifiez `gpu` dans les résultats.
