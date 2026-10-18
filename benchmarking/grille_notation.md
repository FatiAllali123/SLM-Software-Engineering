# Grille de notation manuelle

À utiliser par les 4 membres de la même façon, pour que les notes soient comparables entre les modèles. Ce fichier est **commun** — ne le modifiez pas individuellement.

## Explication de code (P10, P11) et refactoring (P12, P13)

Notez de 1 à 5 :

| Note | Signification |
|---|---|
| 5 | Réponse correcte, claire et complète, rien à redire |
| 4 | Correcte mais incomplète ou mal formulée |
| 3 | Partiellement correcte (quelques éléments justes, d'autres faux ou absents) |
| 2 | Largement fausse mais en rapport avec la question |
| 1 | Hors sujet, incompréhensible ou totalement fausse |

## Détection de bugs (P7, P8, P9)

Notez avec une des 4 étiquettes suivantes (sert à calculer précision/rappel/F1) :

| À écrire dans `bug_label` | Étiquette | Cas |
|---|---|---|
| `TP` | Vrai positif | Il y a un vrai bug ET le modèle l'a trouvé correctement |
| `FP` | Faux positif | Il n'y a pas de bug (ou pas celui trouvé) MAIS le modèle en invente un |
| `FN` | Faux négatif | Il y a un vrai bug MAIS le modèle ne l'a pas trouvé |
| `TN` | Vrai négatif | Il n'y a pas de bug ET le modèle dit correctement qu'il n'y en a pas |

## Hallucination / erreur (toutes tâches de génération de code)

Pour chaque réponse contenant du code, cochez Oui/Non :
- Le code utilise-t-il une fonction, une librairie ou une syntaxe qui **n'existe pas** en Python ? → Oui = hallucination

## Comment remplir

Ajoutez ces notes manuelles comme colonnes supplémentaires dans votre fichier `results/benchmark_<modele>.csv`, en plus des colonnes automatiques (latence, tokens/s, etc.).
