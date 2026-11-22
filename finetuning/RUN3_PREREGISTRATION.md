# Run 3 : critères d'acceptation fixés avant l'entraînement

Date de rédaction : 22 novembre 2026, **avant** l'entraînement du Run 3 et avant toute mesure du Run 3 sur le benchmark de tâches de génie logiciel.

## Ce qui est testé
Run 3 = recette du Run 1 (QLoRA, r = 16, learning rate 2e-4, 1 epoch, graine 42) sur un **mélange de tâches de génie logiciel** : génération de code, génération de tests unitaires, correction de bugs, refactoring, revue de sécurité, documentation (docstrings), explication de code, Dockerfile et GitHub Actions. Données : 9 383 exemples d'entraînement et 500 de validation (`prepare_data_run3.py`), empreintes SHA-256 :
- `train.jsonl` : `b2a8c933fed9a61eeb2dc1b5d8c06f0f1956d375f8a67fb8802624d7260b84f8`
- `val.jsonl` : `20db6fddd0051a72716dd19b7777b08b9b05e9d23a3d41e227e08261eb75661f`

C'est le troisième et dernier entraînement (limite fixée : 3 entraînements, tous rapportés).

## Hypothèse
Spécialiser le modèle sur des tâches de génie logiciel améliore ses résultats sur ces tâches (tests, correction de bugs), sans perte importante sur la génération de code.

## Critères (tous évalués en greedy, bf16, adaptateur fusionné, mêmes réglages que les autres évaluations)
- **C1, pas de régression en génération de code :** HumanEval 164 au moins **108/164** (marge de non-infériorité fixée à 5 points sous le modèle de base, 116/164).
- **C2, gain de spécialisation :** sur le benchmark de tâches de génie logiciel construit sur les 164 problèmes HumanEval, le Run 3 doit améliorer d'**au moins 5 points** le modèle de base, avec un intervalle de confiance bootstrap apparié à 95 % qui exclut 0, sur **au moins 2 des 3 mesures principales** :
  1. taux de correction de bugs (fonctions mutées, vérifiées par les tests officiels de HumanEval) ;
  2. taux de tests générés valides (tous les `assert` passent sur la solution correcte) ;
  3. score de mutation (tests valides qui détectent la mutation).
- **Décision :** Run 3 est accepté seulement si C1 et C2 sont satisfaits. Sinon il est rapporté comme non accepté.

## Mesures secondaires (décrites, pas d'effet sur la décision)
Couverture de lignes des tests générés ; respect des exigences et validité syntaxique pour 20 prompts Dockerfile et 20 prompts GitHub Actions écrits à la main ; docstring (le corps de la fonction reste identique et la docstring mentionne les paramètres) ; tokens de sortie ; détection de vulnérabilités sur V1 à V39 (notation aveugle, seulement si C1 et C2 sont satisfaits).

## Comparaisons
Modèle de base, Run 1, Run 2A et Run 3, avec le même code et les mêmes prompts. Aucun seuil ne sera modifié après la lecture des résultats.
