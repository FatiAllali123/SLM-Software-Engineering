# Adapter du Run 3 à force réduite : critères fixés avant l'exécution

Date de rédaction : 26 novembre 2026, avant toute mesure de cette expérience.

## Contexte (état connu, mesuré)
- Run 3 n'est **pas accepté** par la règle écrite avant son entraînement : HumanEval-164 = 102/164, sous le seuil de 108 (C1). La perte par rapport au modèle de base (116/164) est de −8,5 points, intervalle de −15,2 à −1,8, McNemar exact p = 0,020 : elle est significative. Les 62 échecs sont surtout des erreurs d'assertion (48), les 164 réponses contiennent un bloc de code et aucune n'est tronquée : ce n'est pas un problème de format.
- Sur le benchmark de tâches, après correction du scoreur : correction de bugs +5,5 points (intervalle de −3,4 à +15,2, non significatif) ; tests valides au format imposé (`assert` simples) 28,7 % contre 0,0 % pour le modèle de base, mais le modèle de base écrit des tests `unittest` dans 150 réponses sur 164. Si l'on accepte aussi `unittest` et `pytest`, le modèle de base fait **mieux** : 50,6 % de tests valides contre 28,7 % (−22,0 points, intervalle de −31,7 à −12,2).
- La décision d'acceptation du Run 3 (C1 et C2 requis) reste **inchangée** : non accepté.

## Nouvelle hypothèse (définie après avoir vu ces résultats)
Réduire la force de l'adaptateur (multiplier la mise à jour LoRA par un coefficient avant la fusion) peut conserver une partie du bénéfice de format tout en limitant la perte de correction. Aucun entraînement n'a lieu. Cette expérience est **exploratoire** et ne remplace pas la décision ci-dessus.

## Réglage principal fixé à l'avance
**Coefficient 0,5.** Un seul réglage est évalué pour la décision. Les coefficients 0,25 et 0,75 ne sont évalués, si on le décide, qu'à titre exploratoire et sont rapportés tous, sans être choisis d'après leurs résultats. HumanEval a déjà été lu plusieurs fois : cette mesure est une confirmation d'un réglage unique défini à l'avance, pas une sélection.

## Critères (coefficient 0,5, bf16, greedy, mêmes prompts et mêmes scoreurs que les autres évaluations)
- **S1, pas de perte de correction :** HumanEval-164 au moins **108/164**.
- **S2, bénéfice de format conservé :** taux de tests valides au format `assert` (scoreur strict corrigé) supérieur d'au moins 10 points à celui du modèle de base, avec un intervalle bootstrap apparié à 95 % qui exclut 0.
- **S3, pas de perte de qualité des tests quand le format est libre :** taux de tests valides en scoreur indulgent (unittest et pytest acceptés) : la borne basse de l'intervalle bootstrap apparié à 95 % de la différence avec le modèle de base est supérieure à **−10 points**.
- **Décision :** l'adaptateur réduit est considéré comme satisfaisant seulement si S1, S2 et S3 le sont tous. Sinon il est rapporté comme non satisfaisant. Aucun seuil ne sera modifié après la lecture des résultats.
