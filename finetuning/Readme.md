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
├── prepare_data.py                     préparation des données (décontamination, split, format)
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
│   └── eval_quant_finetuned.ipynb      quantization du modèle fine-tuné (fp16 / INT8 / nf4)
├── configs/pip_freeze_finetune.txt     versions de l'environnement d'entraînement
├── results/
│   ├── dry_run_report.json
│   ├── run1_report.json
│   ├── run1/                           évaluation bf16 : fine-tuné et run de contrôle
│   │   ├── graded/                     résultats avec notes manuelles (aveugle)
│   │   └── blind_grading/              feuille de notation, notes brutes, clé
│   └── quant_ft/                       évaluation quantizée du modèle fine-tuné
└── tools/                              scripts de dé-aveuglement et de score
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

## 6. Protocole d'évaluation

- **Même code que le benchmark du groupe** : cellules reprises de `benchmark_qwen` et `complement_gpu` ; seule la cellule de chargement du modèle change.
- Décodage greedy, 512 nouveaux tokens maximum ; pass@k avec échantillonnage (T = 0,6, top_p = 0,95, top_k = 50, n = 10, graine 42).
- **Modèle principal : bf16, adaptateur fusionné dans les poids** (même profil de vitesse que le modèle de base). L'adaptateur a été entraîné sur une base 4 bits puis appliqué à une base bf16, un léger décalage habituel dans QLoRA.
- **Run de contrôle** : le modèle de base passé dans le même notebook et le même environnement. Ses sorties sont **identiques mot pour mot** à celles de la mesure d'origine (20 HumanEval, 15 prompts, 9 prompts de sécurité, pass@k), donc les versions de bibliothèques n'ont pas changé la correction.
- La mesure de mémoire du modèle fine-tuné vient d'une **session neuve** (une première exécution avait une mémoire faussée par une erreur de chargement). Les sorties de la seconde exécution sont identiques à la première.
- **Notation manuelle aveugle** : réponses du modèle de base et du modèle fine-tuné mélangées et anonymisées, notées par un membre de l'équipe qui n'a pas entraîné le modèle, selon `benchmarking/grille_notation.md`. La clé n'est ouverte qu'après la notation.

## 7. Résultats mesurés

### 7.1 Correction

| Mesure | Base (contrôle) | Fine-tuné |
| --- | --- | --- |
| HumanEval greedy (20 problèmes) | 16/20 (80 %) | 18/20 (90 %) |
| pass@1 / pass@5 / pass@10 (échantillonnage) | 85,0 / 99,5 / 100,0 | 85,0 / 99,5 / 100,0 |
| Échantillons corrects sur 200 | 170 | 170 |
| P1 à P6, test automatique | 5/6 | 5/6 |

Le gain greedy vient de deux problèmes (HumanEval/1 et /10, de échec à réussite), sans régression. L'échantillonnage ne montre **aucun changement net** (170 contre 170). Avec 20 problèmes, un problème vaut 5 points : **la correction ne change pas de façon mesurable**.

### 7.2 Coût et vitesse (15 prompts, T4)

| Mesure | Base (contrôle) | Fine-tuné |
| --- | --- | --- |
| Tokens de sortie moyens | 229,6 | 149,6 (−35 %) |
| Latence moyenne | 8,51 s | 5,91 s |
| Tokens/s | 26,9 | 25,2 |
| TTFT | 0,113 s | 0,122 s |
| Mémoire GPU maximale | 3,11 Go | 3,11 Go |
| Énergie par tâche, brute / nette (24 prompts) | 0,179 / 0,097 Wh | 0,111 / 0,053 Wh |

La baisse de latence et d'énergie vient de réponses plus courtes, pas d'une génération plus rapide (les tokens/s ne montent pas). **C'est l'effet le plus net du fine-tuning.**

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
- Notation humaine de ces réponses quantizées (détection de bugs et de vulnérabilités) : `[À COMPLÉTER]` (feuille 2 en cours de notation).
- Détection de vulnérabilités du modèle de base sous quantization : `[À COMPLÉTER]` (run de contrôle sécurité en cours).

## 8. Limites

- Seulement 20 problèmes HumanEval et 15 + 9 prompts maison : seules de grandes différences sont visibles.
- Un seul entraînement, une seule graine. Un seul correcteur par réponse, blindage imparfait (les réponses fine-tunées sont plus courtes).
- Données générées par GPT-4 (voir licence), uniquement Python, en anglais, alors que nos prompts sont en français.
- Les mesures d'énergie et de coût sont des estimations (le GPU Kaggle est gratuit).
- `safe_exec.py` n'est pas un bac à sable.
- Le scan de secrets est une heuristique.

## 9. Hypothèses non testées et expériences prévues

Hypothèses (à ne pas citer comme des résultats) :
- les données d'entraînement enseignent surtout à écrire du code, ce qui expliquerait la baisse de détection de vulnérabilités ;
- le gain de correction restera dans le bruit à plus grande échelle.

Prévu, pas encore fait :
1. HumanEval greedy sur les 164 problèmes, pour le modèle de base et le fine-tuné.
2. Détection de vulnérabilités sur 20 à 30 snippets supplémentaires (équilibrés), pour tester si la baisse est réelle.
3. Une seconde variante PEFT (par exemple LoRA 16 bits) pour comparer avec QLoRA.
4. Selon le résultat de 2 : un entraînement avec des exemples de revue de sécurité.
5. Test de régression de sécurité (refus, contournement) avec le membre en charge de la sécurité.

## 10. Reproduire

1. `prepare_data.py` dans un notebook Kaggle **sans GPU**, puis vérifier les deux empreintes (section 3).
2. `notebooks/train_run1.ipynb` sur un T4 (Internet activé) : installe `unsloth==2026.11.3 unsloth_zoo==2026.11.3 trl==1.15.0`, ré-exécute la préparation, vérifie les empreintes, entraîne.
3. `notebooks/eval_finetuned.ipynb` : `VARIANT = "ft_bf16"` (adaptateur ajouté comme entrée Kaggle), puis `VARIANT = "base"` pour le contrôle.
4. `notebooks/eval_quant_finetuned.ipynb` : fp16 / INT8 / nf4.
5. Notation : feuilles aveugles, puis scripts de `tools/`.

Empreinte de l'adaptateur évalué : `02ec15117c3bb9e0e84b5a0a7eec98f0bf1d14f438d6fa592d56a3cbe90ab9f3`.

Révisions figées : dataset Magicoder `5f839b1f368a76b161028bb9edff055db34022b2`, HumanEval `7dce6050a7d6d172f3cc5c32aa97f52fa1a2e544`, modèle Qwen2.5-Coder-1.5B-Instruct `2e1fd397ee46e1388853d2af2c993145b0f1098a`.