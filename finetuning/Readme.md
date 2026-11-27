# Fine-tuning de Qwen2.5-Coder-1.5B-Instruct (QLoRA, Unsloth)

Partie « fine-tuning » du projet *Efficient Small Language Models for Intelligent Software Engineering, Testing and DevOps*.

**Statut : en cours.** Les résultats ci-dessous sont **mesurés** (fichiers dans `results/`). Les hypothèses et les expériences prévues sont signalées comme telles. Les cases marquées `[À COMPLÉTER]` attendent un résultat qui n'existe pas encore.

## 1. Question de recherche

**Q1 : le fine-tuning QLoRA de Qwen2.5-Coder-1.5B-Instruct sur des données d'instructions de code change-t-il ses résultats sur notre benchmark ?** Un résultat nul ou négatif est acceptable s'il est bien mesuré.

Choix de cadrage :
- un seul modèle fine-tuné (le plus petit, il tient sur le GPU T4 gratuit de Kaggle) ;
- méthode : Unsloth + QLoRA, comme dans le sujet ;
- évaluation avec **le même benchmark et les mêmes réglages** que le modèle de base (décodage greedy, mêmes jeux de test) ;
- les données d'entraînement ne doivent pas recouvrir HumanEval ni nos prompts.

## 2. Structure du dossier

```
finetuning/
├── README.md
├── prepare_data.py                     préparation des données du Run 1 (décontamination, split, format)
├── prepare_data_run3.py                mélange de tâches du Run 3 (6 sources, décontamination, secrets)
├── RUN3_PREREGISTRATION.md             critères du Run 3, écrits avant l'entraînement
├── RUN3_SCALING_PREREGISTRATION.md     critères de l'adaptateur réduit, écrits avant l'exécution
├── data/
│   ├── report.json                     rapport de décontamination
│   ├── removed_row_ids.json            lignes retirées
│   ├── SHA256SUMS.txt                  empreintes de train.jsonl et val.jsonl
│   ├── source_revisions.json           révisions figées du dataset et du modèle
│   └── secret_scan_report.json         scan de secrets
├── notebooks/
│   ├── dry_run.ipynb                   essai court (30 pas)
│   ├── train_run1.ipynb                entraînement Run 1
│   ├── eval_finetuned.ipynb            évaluation (variants : ft_bf16, base)
│   ├── eval_quant_finetuned.ipynb      quantization du modèle fine-tuné (fp16 / INT8 / nf4)
│   ├── eval_humaneval164.ipynb         HumanEval greedy sur les 164 problèmes (base et fine-tuné)
│   ├── train_run2a.ipynb, train_run3.ipynb
│   ├── eval_run2a.ipynb, eval_run3.ipynb
│   ├── eval_se_tasks.ipynb             benchmark automatique de tâches de génie logiciel
│   └── eval_run3_scaled.ipynb          adaptateur Run 3 à force réduite
├── configs/pip_freeze_finetune.txt     versions de l'environnement d'entraînement
├── results/
│   ├── dry_run_report.json
│   ├── run1_report.json
│   ├── run1/                           évaluation bf16 : fine-tuné et run de contrôle
│   │   ├── graded/                     résultats avec notes manuelles (aveugle)
│   │   └── blind_grading/              feuille de notation, notes brutes, clé
│   ├── quant_ft/                       évaluation quantizée du modèle fine-tuné
│   └── humaneval164/                   HumanEval complet, base et fine-tuné
└── tools/                              scripts de dé-aveuglement et de score, se_bench.py, rescore_se.py
```

Non versionnés : `train.jsonl` et `val.jsonl` (le script les régénère, les empreintes prouvent l'identité), l'adaptateur `adapter_run1` (environ 67 Mo, partagé hors GitHub) et les dossiers de checkpoints.

## 3. Données d'entraînement

| Élément | Valeur |
| --- | --- |
| Source | `ise-uiuc/Magicoder-OSS-Instruct-75K` (75 197 lignes, 9 langages) |
| Licence (fiche du dataset) | MIT. Les données ont été générées avec GPT-4 : les conditions d'OpenAI peuvent aussi s'appliquer (limite à signaler) |
| Sous-ensemble | lignes **Python** uniquement (38 284), car le benchmark est en Python |
| Révision figée | `5f839b1f368a76b161028bb9edff055db34022b2` |
| Taille finale | 6 000 exemples d'entraînement + 300 de validation, tirés avec la graine 42 |

**Décontamination** (voir `data/report.json`). On retire tout exemple qui recouvre les 164 problèmes HumanEval (énoncé, solution, tests), les prompts P1 à P15 ou les prompts de sécurité V1 à V9 :
- règle 1 : séquence de 10 tokens identique à un texte d'évaluation ;
- règle 2 : l'exemple définit une fonction du même nom qu'une fonction d'évaluation (noms de 5 caractères ou plus ; `__init__` et quelques noms génériques exclus).

| Mesure | Valeur |
| --- | --- |
| Retirés au total | 3 562 (n-gram 3 326, nom 361, les deux 125) |
| Conservés | 34 722 |
| Sensibilité de la règle 1 (exemples touchés à n = 8 / 10 / 13) | 11 841 / 3 326 / 1 335 |
| Écartés car trop longs (> 2 048 tokens) | 1 sur 6 301 examinés |
| Tokens par exemple d'entraînement | moyenne 523,5 ; médiane 508 ; max 1 698 |

Remarque : un échantillon de 8 fenêtres retirées par la règle 1 contenait des motifs de code génériques (littéraux de liste, signatures typées), pas des copies de solutions. La règle est volontairement conservatrice, et il reste largement assez de données.

**Format** : modèle de chat de Qwen. Le script vérifie que le texte d'entraînement commence par exactement le même préfixe que le prompt du benchmark, y compris la phrase système par défaut de Qwen.

**Empreintes** (SHA-256) :
- `train.jsonl` : `8b2d6e743b8f8a23b89d20f1cc0f97d823a522134fe291e5aab0655dc7df2b2a`
- `val.jsonl` : `01b59b3f8b4ad639993e20f566038d3942c3c55f291e5f4d4fbbff404e3cc116`

Le script ne **lit jamais** le code du dataset pour l'exécuter. Il ne fait que lire du texte.

## 4. Sécurité du pipeline d'entraînement

| Risque (sujet, section 3) | Ce qui a été fait | Limite |
| --- | --- | --- |
| Fuite de secrets dans les données | scan par expressions régulières et entropie sur les 6 300 exemples (`data/secret_scan_report.json`) | heuristique, peut manquer des secrets |
| Chaîne d'approvisionnement | révisions du dataset, de HumanEval et du modèle figées dans `data/source_revisions.json` ; empreinte SHA-256 de l'adaptateur ; format safetensors (pas de pickle) | on fait confiance au contenu du dataset public |
| Exécution de code généré | l'entraînement n'exécute rien ; l'évaluation exécute le code du modèle avec `utils/safe_exec.py`, **qui n'est pas un vrai bac à sable** | exécution dans la VM temporaire de Kaggle seulement |
| Régression de sécurité après fine-tuning | mesurée sur 9 prompts de sécurité (voir section 7) | jeu très petit |

Résultat du scan : aucune clé AWS, GitHub, Slack, Google, Stripe, de type OpenAI, ni bloc de clé privée. Un JWT trouvé est l'exemple public de jwt.io (`John Doe`). 157 chaînes de type e-mail, dont 133 sur `example.com`. Les 20 affectations de type « secret » ont été jugées factices par l'heuristique.

## 5. Entraînement

| Paramètre | Valeur |
| --- | --- |
| Méthode | QLoRA (base 4 bits nf4), Unsloth 2026.11.3, TRL 1.15.0 |
| LoRA | r = 16, alpha = 16, dropout 0, 7 modules de projection, 18 464 768 paramètres entraînables (1,18 %) |
| Optimisation | AdamW 8 bits, lr 2e-4 décroissant linéairement, 20 pas d'échauffement, graine 42 |
| Lot | 2 par appareil × 8 accumulations = 16 effectif |
| Durée | 1 epoch = 375 pas |
| Précision | fp16 (le T4 n'a pas de bf16 natif) |
| Perte | calculée sur la **réponse seulement** (vérifié : 299 tokens sur 608 pour un exemple) |

Résultats mesurés :
- **Essai court** (30 pas) : 6,0 s/pas, mémoire GPU maximale 1,75 Go, perte d'entraînement moyenne 0,352 (5 premiers pas) vers 0,278 (5 derniers).
- **Run 1** : 41,4 min (validations incluses), mémoire GPU maximale 1,77 Go.

| Pas | Perte de validation (300 exemples) |
| --- | --- |
| 0 | 0,3465 |
| 125 | 0,3136 |
| 250 | 0,3081 |
| 375 | 0,3060 |

Environ 80 % de la baisse a lieu pendant les 125 premiers pas. **Lecture prudente** : c'est la perte sur des données du même type que l'entraînement. Elle montre que le modèle s'adapte au style des données, pas qu'il est meilleur sur notre benchmark.

Environnement d'entraînement : Python 3.13.16, torch 2.11.0+cu130, transformers 5.17.0 (rétrogradé par l'installation d'Unsloth), peft 0.21.2, bitsandbytes 0.50.2 (liste complète : `configs/pip_freeze_finetune.txt`).

### 5.1 Run 2A : même recette, learning rate 1e-4

Hypothèse testée : un entraînement plus doux dérive moins du modèle d'origine. Un seul paramètre change (learning rate 2e-4 vers 1e-4) ; données, graine, empreintes et reste de la recette sont identiques. **Critères d'acceptation fixés avant les résultats :** (1) HumanEval 164 en greedy d'au moins 116/164 (pas de perte par rapport au modèle de base) ; (2) tokens de sortie moyens sur les 15 prompts d'au plus 85 % de ceux du modèle de base (229,6). Les prompts de sécurité ne sont notés que si les deux critères sont satisfaits. Au maximum 3 entraînements au total sont réalisés, tous rapportés.

| Mesure | Run 1 (2e-4) | Run 2A (1e-4) |
| --- | --- | --- |
| Perte de validation à la fin (300 exemples) | 0,3060 | 0,3085 |
| Durée d'entraînement (validations incluses) | 41,4 min | 36,2 min |
| Mémoire GPU maximale | 1,77 Go | 1,77 Go |
| HumanEval 164 greedy | 114/164 (69,5 %) | **110/164 (67,1 %)** |
| Tokens de sortie moyens, 15 prompts | 149,6 | 154,0 (−33 % par rapport à 229,6) |
| Tokens de sortie moyens, HumanEval | 183,6 | 181,4 (+10,5 % par rapport à 164,1) |

- Run 2A contre le modèle de base sur HumanEval 164 : 8 problèmes gagnés, 14 perdus, différence −3,7 points (intervalle bootstrap apparié à 95 % de −9,1 à +1,8), McNemar exact p = 0,29.
- Run 2A contre Run 1 : 3 gagnés, 7 perdus, différence −2,4 points (de −6,1 à +1,2), p = 0,34.
- **Verdict : critère 1 non satisfait (110 < 116), critère 2 satisfait (154,0 ≤ 195,2). Run 2A n'est pas accepté.** Les réponses de sécurité ont été générées mais ne sont pas notées, conformément à la règle fixée à l'avance.
- Aucune des différences entre base, Run 1 et Run 2A n'est statistiquement significative sur HumanEval, mais aucun des deux entraînements ne dépasse le modèle de base. Un learning rate plus bas ne change pas la conclusion.
- Empreinte de l'adaptateur Run 2A : `c047a5b40fc42fedac6fbff16b365e69a366536db76d16382319fac0b7917f92`.

### 5.2 Run 3 : mélange de tâches de génie logiciel

Même recette que le Run 1 (QLoRA, r = 16, learning rate 2e-4, 1 epoch, graine 42) sur un mélange de tâches couvrant celles du sujet. Critères d'acceptation écrits avant l'entraînement : `RUN3_PREREGISTRATION.md` (C1 : HumanEval 164 au moins 108/164 ; C2 : amélioration d'au moins 5 points sur au moins 2 de 3 mesures du benchmark de tâches ; les deux requis).

| Tâche | Source (licence lue sur la page du dataset) | Exemples d'entraînement |
| --- | --- | --- |
| Génération de code | Magicoder OSS-Instruct, Python (MIT) | 3 000 |
| Tests unitaires | `nvidia/OpenCodeInstruct`, tests validés par exécution (CC BY 4.0) | 1 900 |
| Correction de bugs, refactoring | `bigcode/commitpackft`, dépôts à licence permissive ; le message du commit sert d'instruction | 1 139 et 761 |
| Revue de sécurité | `CyberNative/Code_Vulnerability_Security_DPO` (Apache-2.0), données synthétiques, moitié vulnérable et moitié sûr | 336 et 347 |
| Documentation (docstrings) | construite à partir d'OpenCodeInstruct | 475 |
| Explication de code | construite à partir de réponses Magicoder | 475 |
| Dockerfile, GitHub Actions | `Helmcode/stack-v3-devops` (ODC-By d'après sa fiche), fichiers à licence permissive ; la spécification donnée au modèle est dérivée automatiquement du fichier | 475 et 475 |

Total : 9 383 exemples d'entraînement et 500 de validation, environ 4,16 millions de tokens. Décontamination contre HumanEval (164 problèmes), P1 à P15 et V1 à V39 : 54 % des candidats de tests d'OpenCodeInstruct (3 252 sur 6 000) et 509 candidats de docstrings sur 2 000 recouvraient nos textes d'évaluation et ont été retirés. Secrets retirés : 5 exemples de commits et 1 de DevOps. Empreintes : `train.jsonl` `b2a8c933fed9a61eeb2dc1b5d8c06f0f1956d375f8a67fb8802624d7260b84f8`, `val.jsonl` `20db6fddd0051a72716dd19b7777b08b9b05e9d23a3d41e227e08261eb75661f`. Les instructions DevOps sont synthétiques (dérivées du fichier lui-même) : le modèle apprend à passer d'une spécification à un fichier.

Résultats mesurés : 587 pas, 55,8 min, mémoire GPU maximale 1,76 Go, perte de validation 0,421 puis 0,294 (sur le jeu de validation mixte, non comparable aux autres runs). Empreinte de l'adaptateur : `5e945e408e60edf3ded0b4a5d31b3791f6f14bc46e6432e99519ac6a16e889ca`. **Verdict : non accepté** (C1 non satisfait : 102/164). Détails en sections 7.6 et 7.7.

Attribution : OpenCodeInstruct est sous licence CC BY 4.0 et stack-v3-devops sous ODC-By d'après leurs fiches ; ces sources doivent être citées.

## 6. Protocole d'évaluation

- **Même code que le benchmark du groupe** : cellules reprises de `benchmark_qwen` et `complement_gpu` ; seule la cellule de chargement du modèle change.
- Décodage greedy, 512 nouveaux tokens maximum ; pass@k avec échantillonnage (T = 0,6, top_p = 0,95, top_k = 50, n = 10, graine 42).
- **Modèle principal : bf16, adaptateur fusionné dans les poids** (même profil de vitesse que le modèle de base). L'adaptateur a été entraîné sur une base 4 bits puis appliqué à une base bf16, un léger décalage habituel dans QLoRA.
- **Run de contrôle** : le modèle de base passé dans le même notebook et le même environnement. Ses sorties sont **identiques mot pour mot** à celles de la mesure d'origine (20 HumanEval, 15 prompts, 9 prompts de sécurité, pass@k), donc les versions de bibliothèques n'ont pas changé la correction.
- La mesure de mémoire du modèle fine-tuné vient d'une **session neuve** (une première exécution avait une mémoire faussée par une erreur de chargement). Les sorties de la seconde exécution sont identiques à la première.
- **Notation manuelle aveugle** : réponses du modèle de base et du modèle fine-tuné mélangées et anonymisées, notées par un membre de l'équipe qui n'a pas entraîné le modèle, selon `benchmarking/grille_notation.md`. La clé n'est ouverte qu'après la notation.

## 7. Résultats mesurés

**Synthèse (état actuel, à relire à la fin du projet) :**
- **Correction : aucun changement mesurable.** Sur les 164 problèmes HumanEval, le modèle fine-tuné fait 114/164 contre 116/164 pour le modèle de base (différence −1,2 points, intervalle à 95 % de −7,3 à +4,9). Le gain apparent de +10 points sur les 20 premiers problèmes était dans le bruit.
- **Efficacité : dépend de la tâche.** Réponses 35 % plus courtes sur nos 15 prompts, mais 12 % plus longues sur HumanEval.
- **Sécurité : pas de différence confirmée.** Sur les 9 prompts d'origine (V1 à V9), le modèle fine-tuné détecte moins de vulnérabilités que le modèle de base, dans les quatre précisions ; sur 30 prompts supplémentaires (V10 à V39), les deux modèles sont faibles et équivalents. Sur les 21 prompts vulnérables réunis : 11 détections pour le modèle de base, 7 pour le fine-tuné, écart non significatif (p = 0,29). Voir section 7.5.
- **Quantization : se comporte comme pour le modèle de base.**
- **Run 2A (learning rate 1e-4, un seul changement) : non accepté.** HumanEval complet 110/164 contre 116/164 pour le modèle de base, donc un entraînement plus doux n'améliore pas la correction (section 5.1).
- **Run 3 (mélange de tâches de génie logiciel) : non accepté.** HumanEval complet 102/164 contre 116/164 (−8,5 points, p = 0,020 : perte significative). Sur le benchmark de tâches, son avantage apparent venait du format imposé ; quand le format est libre, le modèle de base écrit plus souvent des tests corrects (section 7.6).
- **Adaptateur du Run 3 à force réduite (coefficient 0,5) : non satisfaisant** selon les critères écrits avant (section 7.7).

### 7.1 Correction

**HumanEval complet, 164 problèmes, greedy** (`results/humaneval164/`, analyse avec `tools/compare_humaneval.py`) :

| Mesure | Base | Fine-tuné |
| --- | --- | --- |
| Problèmes réussis | 116/164 (70,7 %) | 114/164 (69,5 %) |
| Intervalle de confiance à 95 % (Wilson) | 63,4 à 77,2 | 62,1 à 76,0 |
| Gagnés (échec → réussite) / perdus (réussite → échec) | 12 gagnés, 14 perdus | |
| Test de McNemar exact (26 problèmes discordants) | p = 0,845 | |
| Différence (fine-tuné − base), bootstrap apparié à 95 % | −1,2 points (−7,3 à +4,9) | |
| 20 premiers problèmes / 144 autres | 16/20 et 100/144 | 18/20 et 96/144 |

Règle de décision fixée avant de voir les données : le gain est réel seulement si l'intervalle de la différence exclut 0 et si p < 0,05. **Ce n'est pas le cas** : on conclut à l'absence de différence mesurable (on ne peut pas non plus exclure une perte jusqu'à environ 7 points). Les 20 premiers problèmes (+2 pour le fine-tuné) étaient un sous-échantillon favorable ; sur les 144 autres le fine-tuné fait 4 problèmes de moins. Les échecs sont surtout des erreurs d'assertion pour les deux modèles (41 et 40) ; les autres types d'erreur diffèrent un peu (par exemple 5 TypeError contre 1) mais les effectifs sont trop faibles pour conclure. Pour les deux modèles, les 20 premiers problèmes reproduisent exactement les résultats des exécutions précédentes.

**Sous-ensemble de 20 problèmes et prompts maison :**

| Mesure | Base (contrôle) | Fine-tuné |
| --- | --- | --- |
| HumanEval greedy (20 problèmes) | 16/20 (80 %) | 18/20 (90 %) |
| pass@1 / pass@5 / pass@10 (échantillonnage, 20 problèmes) | 85,0 / 99,5 / 100,0 | 85,0 / 99,5 / 100,0 |
| Échantillons corrects sur 200 | 170 | 170 |
| P1 à P6, test automatique | 5/6 | 5/6 |

Sur ces 20 problèmes, le gain greedy vient de HumanEval/1 et /10, et l'échantillonnage ne montre aucun changement net (170 contre 170). **La correction ne change pas de façon mesurable.**

### 7.2 Coût et vitesse (15 prompts, T4)

| Mesure | Base (contrôle) | Fine-tuné |
| --- | --- | --- |
| Tokens de sortie moyens | 229,6 | 149,6 (−35 %) |
| Latence moyenne | 8,51 s | 5,91 s |
| Tokens/s | 26,9 | 25,2 |
| TTFT | 0,113 s | 0,122 s |
| Mémoire GPU maximale | 3,11 Go | 3,11 Go |
| Énergie par tâche, brute / nette (24 prompts) | 0,179 / 0,097 Wh | 0,111 / 0,053 Wh |

Sur ces 15 prompts (tâches variées : génération, bugs, explications, tests), la baisse de latence et d'énergie vient de réponses plus courtes, pas d'une génération plus rapide (les tokens/s ne montent pas).

**Cet effet ne se généralise pas à la complétion de code.** Sur les 164 problèmes HumanEval, le modèle fine-tuné produit en moyenne 183,6 tokens contre 164,1 pour le modèle de base (+11,8 %), avec une latence moyenne de 7,74 s contre 6,96 s ; la mémoire GPU maximale est la même (3,15 Go) et les tokens/s aussi (23,7 contre 23,4). Il produit une réponse plus longue sur 58 problèmes et plus courte sur 64. L'économie de tokens dépend donc du type de tâche : à ne pas présenter comme un gain général.

### 7.3 Notation manuelle aveugle

| Mesure | Base | Fine-tuné |
| --- | --- | --- |
| Détection de bugs P7 à P9 (précision / rappel / F1) | 0,67 / 1,00 / 0,80 | 0,67 / 1,00 / 0,80 |
| **Détection de vulnérabilités V1 à V9 (précision / rappel / F1)** | 0,75 / 1,00 / 0,857 | 0,75 / **0,50** / **0,60** |
| Qualité moyenne P10 à P15 (1 à 5) | 4,00 | 4,00 |
| Hallucinations | 0 sur 14 | 2 sur 13 (une des deux, R12, est en cours de vérification) |

**Résultat important : le modèle fine-tuné manque 3 vulnérabilités que le modèle de base détecte** (V2 clé d'API en dur, V4 injection de commandes, V5 désérialisation `pickle`), et fait mieux sur V7 (une fausse alerte en moins). Il n'y a que 6 prompts vulnérables : un test de signes exact donne p = 0,25, donc ce n'est **pas statistiquement significatif**, mais c'est une perte de moitié de la détection sur une tâche de sécurité. La cause est inconnue (hypothèse non testée : les données apprennent à écrire du code, pas à l'auditer).

Les notes de qualité de la notation humaine (moyenne 4,00 pour le modèle de base) diffèrent des notes provisoires préparées avec un assistant IA (3,33) : on retient les notes humaines.

### 7.4 Quantization du modèle fine-tuné (adaptateur fusionné en fp16, puis quantizé au chargement)

Mêmes 15 prompts et mêmes 20 problèmes HumanEval que l'expérience de quantization du modèle de base (réglages nf4 : double quantization, calcul fp16).

| Variante | Poids (Go) | Mémoire GPU max (Go) | Tokens/s | Tokens de sortie, base → fine-tuné | Latence (s), base → fine-tuné | HumanEval sur 20, base → fine-tuné |
| --- | --- | --- | --- | --- | --- | --- |
| bf16 | 3,09 | 3,12 → 3,11 | 25,9 → 25,2 | 229,6 → 149,6 | 8,87 → 5,91 | 16 → 18 |
| fp16 | 3,09 | 3,12 → 3,11 | 26,1 → 26,1 | 219,3 → 148,4 | 8,40 → 5,68 | 17 → 18 |
| INT8 | 1,78 | 1,81 → 1,81 | 6,6 → 6,6 | 231,9 → 144,1 | 35,16 → 21,77 | 17 → 17 |
| nf4 | 1,12 | 1,20 → 1,20 | 19,0 → 19,0 | 235,9 → 177,1 | 12,41 → 9,34 | 17 → 18 |

- La quantization réduit la mémoire de la même façon pour les deux modèles ; INT8 est la variante la plus lente.
- La réduction du nombre de tokens de sortie se maintient (−25 % à −38 %), moins en nf4.
- HumanEval du modèle fine-tuné varie d'au plus un problème entre les variantes (18, 18, 17, 18) ; l'avantage sur le modèle de base est de 0 à 2 problèmes selon la précision, **dans le bruit**.
- Le test automatique P1 à P6 donne 6/6 en nf4 : c'est un artefact du test de P5 (faux échec connu), pas une amélioration.
- Le test de mots-clés sur les prompts de sécurité est trop grossier (il compte V4 comme trouvé pour le bf16 alors que la notation humaine le classe manqué) : **ne pas le rapporter comme résultat de détection**.
- Détection de vulnérabilités (V1 à V9) du modèle de base et du fine-tuné sous quantization : voir section 7.5.
- Détection de bugs (P7 à P9) du fine-tuné quantizé : nf4 donne 0,50 / 0,50 / 0,50 (précision / rappel / F1) contre 0,67 / 1,00 / 0,80 pour bf16, fp16 et INT8 (notes du second correcteur, 3 prompts seulement) `[À COMPLÉTER : relire avec le groupe]`.

### 7.5 Sécurité : détection de vulnérabilités (notation humaine aveugle)

Deux jeux : les 9 prompts d'origine (6 vulnérables, 3 sûrs) et 30 prompts supplémentaires écrits par un membre de l'équipe (15 vulnérables V10 à V24, 15 sûrs V25 à V39, chaque snippet sûr étant la version corrigée d'un snippet vulnérable). Règle du second jeu : un faux type de faille compte comme manqué (FN) ; un faux type inventé sur un code sûr compte comme fausse alerte (FP). Notateurs : `[À COMPLÉTER : qui a noté quelle feuille]`. Sur 20 réponses notées par deux personnes, l'accord est de 19/20 (kappa de Cohen 0,93) ; sur les 18 réponses bf16 des 9 prompts d'origine, l'accord entre deux correcteurs est de 17/18 (le désaccord porte sur V6, une réponse qui se contredit).

**V1 à V9, une seule grille de notation, base contre fine-tuné :**

| Modèle | Variante | Précision | Rappel | F1 | TP / FP / FN / TN |
| --- | --- | --- | --- | --- | --- |
| base | bf16 | 0,75 | 1,00 | 0,857 | 6 / 2 / 0 / 1 |
| base | fp16 | 0,71 | 0,83 | 0,769 | 5 / 2 / 1 / 1 |
| base | INT8 | 0,78 | 1,00 | 0,875 | 7 / 2 / 0 / 0 |
| base | nf4 | 0,63 | 0,83 | 0,714 | 5 / 3 / 1 / 0 |
| fine-tuné | bf16 | 0,67 | 0,33 | 0,444 | 2 / 1 / 4 / 2 |
| fine-tuné | fp16 | 0,75 | 0,50 | 0,600 | 3 / 1 / 3 / 2 |
| fine-tuné | INT8 | 0,75 | 0,50 | 0,600 | 3 / 1 / 3 / 2 |
| fine-tuné | nf4 | 0,57 | 0,67 | 0,615 | 4 / 3 / 2 / 0 |

Le rappel du fine-tuné est inférieur à celui du modèle de base dans les quatre précisions. Pour le fine-tuné en bf16, le résultat dépend d'une réponse contradictoire (V6) : avec l'autre notation, le rappel serait de 0,50. Sur ces 9 prompts en bf16, le fine-tuné rate 4 vulnérabilités que le modèle de base trouve (V2, V4, V5, V6) et en gagne 1 sur les codes sûrs (V7) ; p = 0,375.

**Prompts supplémentaires V10 à V39 (bf16) :**

| Système | Précision | Rappel | F1 | Exactitude | TP / FP / FN / TN |
| --- | --- | --- | --- | --- | --- |
| base | 0,33 | 0,33 | 0,33 | 10/30 | 5 / 10 / 10 / 5 |
| fine-tuné | 0,39 | 0,33 | 0,36 | 12/30 | 5 / 8 / 10 / 7 |

Les deux modèles ne trouvent que 5 des 15 vulnérabilités et signalent à tort une faille sur la moitié environ des codes sûrs. Le fine-tuné fait mieux sur 5 prompts et moins bien sur 3 (test de McNemar exact, p = 0,73). Sur les 15 paires (vulnérable et son jumeau corrigé), les deux réponses sont justes pour 1 paire du modèle de base et 2 paires du fine-tuné.

**Ensemble des 39 prompts (bf16) :**
- Prompts vulnérables (21) : 11 détectés par le modèle de base, 7 par le fine-tuné ; fine-tuné meilleur sur 2, moins bon sur 6 (p = 0,29).
- Codes sûrs (18) : signalés à tort comme vulnérables par 12 réponses du modèle de base et 9 du fine-tuné.
- Toutes réponses justes ou fausses confondues : fine-tuné meilleur sur 6 prompts, moins bon sur 7 (p = 1,0).

**Lecture :** aucune différence statistiquement significative. Le signal initial (le fine-tuné perd des détections sur les failles classiques de V1 à V9) n'est pas reproduit sur les prompts supplémentaires, où les deux modèles sont proches du plancher. Un modèle de 1,5 milliard de paramètres n'est pas fiable pour cette tâche : ses réponses de sécurité doivent rester consultatives et être complétées par des outils d'analyse statique. Sur ces prompts, le fine-tuné produit des réponses plus courtes (177,5 tokens en moyenne contre 324,8, soit −45 %).

### 7.6 Benchmark automatique de tâches de génie logiciel (Run 3 contre modèle de base)

Benchmark construit sur les 164 problèmes HumanEval (`tools/se_bench.py`, notebook `eval_se_tasks.ipynb`), sans notation humaine : **correction de bugs** (un bug injecté, détecté par les tests officiels ; le modèle renvoie la fonction corrigée, jugée par ces tests ; 145 problèmes), **génération de tests** (validité, couverture de lignes, score de mutation), **docstrings** (82 problèmes), **Dockerfile et GitHub Actions** (20 spécifications chacun, jugées par analyse syntaxique et respect des exigences). Tous les modèles reçoivent exactement les mêmes prompts, en bf16, greedy. Le jeu de mutants est identique pour tous (empreinte `4ab436bd…`). Le code généré est exécuté dans un sous-processus avec limite de temps (ce n'est pas un bac à sable).

Résultats **corrigés** (voir le journal des corrections ci-dessous) :

| Mesure | Base | Run 3 | Différence (intervalle bootstrap apparié à 95 %) |
| --- | --- | --- | --- |
| Correction de bugs (145) | 43,4 % | 49,0 % | +5,5 (−3,4 à +15,2), non significatif |
| Tests valides, `assert` simples imposés par le prompt | 0,0 % | 28,7 % | +28,7 (+22,0 à +35,4) |
| Score de mutation, même format | 0,0 % | 28,3 % | +28,3 (+20,9 à +35,6) |
| Tests valides, `unittest` et `pytest` acceptés | 50,6 % | 28,7 % | −22,0 (−31,7 à −12,2) |
| Score de mutation, format libre | 45,3 % | 28,3 % | −17,0 (−27,1 à −6,9) |
| Couverture des tests valides, format libre | 98,9 % | 99,1 % | non testée |
| Docstring correcte (code inchangé, au moins 30 caractères) | 22,0 % | 40,2 % | non testée |
| Dockerfile valide / exigences respectées | 100 % / 93,5 % | 100 % / 96,9 % | non testée |
| GitHub Actions valide / exigences respectées | 100 % / 99,4 % | 100 % / 100 % | non testée |
| Tokens de sortie, correction de bugs / tests | 361,4 / 249,8 | 209,2 / 187,4 | non testée |


### 1. All Runs

| Run | Change vs Run 1 | Criterion Written Before Evaluating | Result | Decision |
|---|---|---|---|---|
| **Run 1** | Baseline: 6,000 examples, 1 epoch (375 steps), QLoRA r=16, lr 2e-4, seed 42 | None, exploratory first run | **HumanEval-164:** Base 116 (70.7%), fine-tuned 114 (69.5%), McNemar p = 0.845. **Tokens:** Base 229.6 on 15 prompts. **Security V10–V39:** Base 10/30, fine-tuned 12/30, p = 0.73. On V1–V9, recall is lower than base in all 4 precisions. | **Selected** as the fine-tuned model for the assistant (agreed 26 Nov), as the most defensible candidate. No measurable gain over base. |
| **Run 2A** | Learning rate 1e-4, otherwise identical to Run 1 | HumanEval-164 ≥ 116 **and** tokens ≤ 85% of base | **HumanEval-164:** 110 vs base 116. **Tokens:** 154.0 vs 229.6 (67% of base). Token criterion met, correctness criterion not met. | **Not accepted** |
| **Run 3** | Different training data (software-engineering task mix). Adapter SHA-256: `5e945e40…` (complete from manifest). | C1: HumanEval-164 ≥ 108. Other criteria: not specified. | **HumanEval-164:** 102/164 (62.2%) vs base 116, McNemar p = 0.020 (C1 fails). **Tokens:** 94.3 vs 229.6 (41% of base). **SE-Tasks:** Bugfix 43.4 vs 49.0 (difference CI: −3.4 to +15.2); lenient valid tests 50.6 vs 28.7; docstring 22.0 vs 40.2; strict valid tests and mutation score 0.0 vs 28.7 and 0.0 vs 28.3, respectively. Format effect: base model writes `unittest`. Security answers generated but not graded. | **Not accepted** |
| **Run 3 – Adapter scaled to alpha 0.5** | No new training: Run 3 adapter with scaling reduced to 0.5. | S1, S2, S3: thresholds not specified. | **HumanEval:** 110/164 (S1 pass). **Strict tests:** 17.7 (S2 pass). **Lenient tests:** 17.7 vs base 50.6 (S3 fails). | **Not accepted** |



**Lecture :**
- Le modèle de base écrit des tests `unittest` dans 150 réponses sur 164, alors que le prompt demandait des `assert` simples. Avec la règle stricte du prompt, il est donc à 0 % ; Run 3 suit le format (0 `unittest`, 164 réponses avec `assert`). Le critère C2 du pré-enregistrement (au moins 2 mesures principales améliorées de 5 points) était satisfait par ce **respect du format** : tests valides et score de mutation au format imposé.
- Quand on accepte aussi `unittest` et `pytest`, le modèle de base fait **mieux** que Run 3. Les tests de Run 3 sont faux sur la fonction correcte dans 112 cas sur 164. Il n'y a donc pas de preuve que Run 3 écrit de meilleurs tests.
- Run 3 n'est pas accepté de toute façon : le critère C1 (HumanEval au moins 108/164) échoue (102/164).

**Journal des corrections du scoreur** (erreurs de ma part, corrigées après la première évaluation ; les seuils n'ont pas changé) :
1. L'extracteur de blocs de code ne reconnaissait que certaines balises en minuscules : ```` ```Dockerfile ````, ```` ```docker ````, ```` ```Python ```` ou ```` ```YAML ```` n'étaient pas reconnus, et un Dockerfile parfait était jugé invalide. Premier résultat publié par erreur : Dockerfile du modèle de base valide à 0 %. Corrigé.
2. Le score de tests « strict » comptait comme valides des `assert` placés dans une fonction jamais appelée. Premier résultat : tests valides du modèle de base à 4,3 % ; corrigé : 0,0 %. Seuls comptent maintenant les `assert` exécutés au niveau du module.
3. Ajout d'un score de tests « indulgent » (secondaire) qui accepte `unittest` et `pytest` et ne compte que les assertions réellement exécutées.

### 7.7 Adaptateur du Run 3 à force réduite (sans nouvel entraînement)

Après le diagnostic du Run 3 (perte réelle de correction, pas un problème de format : 48 erreurs d'assertion sur 62 échecs, 164 réponses sur 164 avec un bloc de code, aucune tronquée), la mise à jour LoRA a été multipliée par 0,5 avant la fusion. Un seul coefficient a été fixé à l'avance (`RUN3_SCALING_PREREGISTRATION.md`) ; cette expérience est exploratoire et définie après avoir vu les résultats du Run 3.

| Critère (coefficient 0,5) | Résultat | Seuil | Verdict |
| --- | --- | --- | --- |
| S1 : HumanEval 164 | 110/164 (67,1 %) ; −3,7 points contre la base (−9,8 à +2,4), p = 0,33 | au moins 108 | satisfait |
| S2 : tests valides au format `assert`, contre la base | 17,7 % contre 0,0 % : +17,7 (+12,2 à +23,8) | au moins +10, intervalle exclut 0 | satisfait |
| S3 : tests valides, format libre, contre la base | 17,7 % contre 50,6 % : −32,9 (−41,5 à −24,4) | borne basse au-dessus de −10 | **non satisfait** |

**Verdict : l'adaptateur réduit n'est pas satisfaisant** (les trois critères étaient requis). Pour mémoire : coefficient 0 = modèle de base, 116/164 ; coefficient 0,5 : 110/164 ; coefficient 1 = Run 3 : 102/164. La correction baisse de façon régulière quand on augmente la force de l'adaptateur. Pour les tests générés à 0,5, 33 réponses sur 164 s'arrêtent à la limite de 512 tokens (3 pour Run 3, 11 pour la base) et 35 sont rejetées pour erreur de syntaxe : le modèle intermédiaire produit des listes d'`assert` qui ne se terminent pas. Cette observation n'est pas expliquée.

## 8. Limites

- Les prompts maison sont peu nombreux (15 + 9) : seules de grandes différences y sont visibles. HumanEval complet (164 problèmes) donne un intervalle d'environ ±6 points pour chaque modèle.
- Un seul entraînement, une seule graine. Un seul correcteur par réponse (sauf deux sous-ensembles notés deux fois), blindage imparfait (les réponses fine-tunées sont plus courtes). Si l'auteur des prompts supplémentaires a noté ses propres prompts, ce n'est pas un correcteur indépendant : `[À COMPLÉTER]`.
- Jeux de sécurité très petits (21 prompts vulnérables au total) et règle de notation stricte ; les deux modèles restent proches du hasard sur les prompts supplémentaires.
- Données générées par GPT-4 (voir licence), uniquement Python, en anglais, alors que nos prompts sont en français.
- Les mesures d'énergie et de coût sont des estimations (le GPU Kaggle est gratuit).
- `safe_exec.py` n'est pas un bac à sable.
- Le scan de secrets est une heuristique.

## 9. Hypothèses non testées et expériences prévues

Hypothèses (à ne pas citer comme des résultats) :
- les données d'entraînement enseignent surtout à écrire du code, ce qui expliquerait la baisse de détection de vulnérabilités ;
- le gain de correction restera dans le bruit à plus grande échelle.

Prévu, pas encore fait :
1. ~~HumanEval greedy sur les 164 problèmes~~ : fait (section 7.1).
2. ~~Détection de vulnérabilités sur 30 snippets supplémentaires~~ : fait (section 7.5).
3. Les trois entraînements permis sont utilisés (Run 1, Run 2A, Run 3). Un éventuel quatrième serait hors protocole et exploratoire (par exemple un mélange avec davantage de code vérifié par exécution) `[À DÉCIDER]`. Une variante PEFT différente (LoRA 16 bits) n'a pas été testée.
4. Un entraînement avec des exemples de revue de sécurité : non retenu, car le signal de sécurité n'est pas confirmé (section 7.5).
5. Test de régression de sécurité (refus, contournement) avec le membre en charge de la sécurité.

## 10. Reproduire

1. `prepare_data.py` dans un notebook Kaggle **sans GPU**, puis vérifier les deux empreintes (section 3).
2. `notebooks/train_run1.ipynb` sur un T4 (Internet activé) : installe `unsloth==2026.11.3 unsloth_zoo==2026.11.3 trl==1.15.0`, ré-exécute la préparation, vérifie les empreintes, entraîne.
3. `notebooks/eval_finetuned.ipynb` : `VARIANT = "ft_bf16"` (adaptateur ajouté comme entrée Kaggle), puis `VARIANT = "base"` pour le contrôle.
4. `notebooks/eval_quant_finetuned.ipynb` : fp16 / INT8 / nf4.
5. Notation : feuilles aveugles, puis scripts de `tools/`.

Empreinte de l'adaptateur évalué : `02ec15117c3bb9e0e84b5a0a7eec98f0bf1d14f438d6fa592d56a3cbe90ab9f3`.

Révisions figées : dataset Magicoder `5f839b1f368a76b161028bb9edff055db34022b2`, HumanEval `7dce6050a7d6d172f3cc5c32aa97f52fa1a2e544`, modèle Qwen2.5-Coder-1.5B-Instruct `2e1fd397ee46e1388853d2af2c993145b0f1098a`.
