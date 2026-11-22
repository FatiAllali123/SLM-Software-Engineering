# Avancement --- LLMClient et backends de modèles

**Projet :** Efficient Small Language Models for Intelligent Software
Engineering, Testing and DevOps\
**Périmètre :** couche d'abstraction `LLMClient` et intégration de
plusieurs backends Qwen\
**État :** avancement intermédiaire --- backend LoRA en attente des
poids de l'adaptateur.

------------------------------------------------------------------------

## 1. Objectif de mon travail

Mettre en place une interface commune permettant d'utiliser plusieurs
modèles ou configurations de modèles sans modifier le code qui appelle
le LLM.

L'interface `LLMClient` reçoit une liste de messages et délègue la
génération au backend sélectionné.

Le format de retour commun est :

``` python
{
    "text": str,
    "tokens_in": int,
    "tokens_out": int,
    "latency_s": float
}
```

## 2. Architecture actuelle

``` text
llm/
├── __init__.py
├── client.py
└── backends/
    ├── __init__.py
    ├── base.py
    ├── stub.py
    ├── qwen_base.py
    └── qwen_nf4.py
```

-   `base.py` : définit la classe abstraite `BaseBackend`.
-   `stub.py` : fournit un backend de test sans chargement d'un vrai
    modèle.
-   `qwen_base.py` : charge Qwen2.5-Coder-1.5B-Instruct en BF16.
-   `qwen_nf4.py` : charge le même modèle avec une quantification 4 bits
    NF4.
-   `client.py` : expose l'interface commune `LLMClient`.

## 3. Travail réalisé

### 3.1 Interface commune et backend Stub

-   Création de `BaseBackend` avec une méthode `generate(messages)`.
-   Création de `LLMClient`.
-   Vérification de la validité de `messages` (type liste et liste non
    vide).
-   Implémentation de `StubBackend` pour tester le contrat sans charger
    de modèle.

### 3.2 Backend Qwen BF16

-   Chargement de `Qwen/Qwen2.5-Coder-1.5B-Instruct`.
-   Utilisation du format de conversation du tokenizer
    (`apply_chat_template`).
-   Génération de texte.
-   Mesure des tokens d'entrée, des tokens de sortie et de la latence.
-   Test effectué sur Kaggle avec GPU Tesla T4.

### 3.3 Backend Qwen NF4

-   Chargement du même modèle avec `BitsAndBytesConfig`.
-   Quantification 4 bits de type NF4.
-   Double quantification activée.
-   Type de calcul BF16.
-   Vérification du chargement en 4 bits et test de génération sur
    Kaggle T4.

### 3.4 Comparaison BF16 / NF4

Mesures relevées lors d'un essai sur le même prompt :

  Mesure                                     Qwen BF16     Qwen NF4
  --------------------------------------- ------------ ------------
  Mémoire GPU allouée après chargement      4054,37 MB   1110,09 MB
  Mémoire GPU réservée après chargement        4098 MB      1150 MB
  Pic de mémoire GPU allouée                4078,18 MB   1141,38 MB
  Tokens d'entrée                                   46           46
  Tokens de sortie                                 437          512
  Latence                                      15,40 s      25,33 s

Sur cet essai, NF4 réduit fortement la mémoire GPU utilisée. La
comparaison de latence doit cependant être interprétée avec prudence :
la génération NF4 a atteint la limite de 512 nouveaux tokens,
contrairement à BF16. Il s'agit d'une mesure ponctuelle, et non d'une
moyenne sur plusieurs essais.

## 4. Travail LoRA / QLoRA en cours

Le fine-tuning de l'adaptateur est réalisé par un autre membre de
l'équipe. Mon rôle est de préparer son intégration comme backend
supplémentaire, tout en conservant l'interface `LLMClient`.

### Informations reçues pour Run 1

Le fichier `adapter_config.json` transmis indique notamment :

  ------------------------------------------------------------------------------------
  Paramètre                           Valeur
  ----------------------------------- ------------------------------------------------
  Type PEFT                           `LORA`

  Modèle de base indiqué              `unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit`

  Rang `r`                            16

  `lora_alpha`                        16

  `lora_dropout`                      0

  `bias`                              `none`

  `task_type`                         `CAUSAL_LM`

  `inference_mode`                    `true`

  Modules ciblés                      `q_proj`, `k_proj`, `v_proj`, `o_proj`,
                                      `gate_proj`, `up_proj`, `down_proj`
  ------------------------------------------------------------------------------------

La configuration seule ne suffit pas pour utiliser l'adaptateur : les
poids entraînés sont également nécessaires, généralement dans
`adapter_model.safetensors` (ou parfois `adapter_model.bin`).

### Comparaison des rapports d'entraînement disponibles

Les rapports Run 1 et Run 2a indiquent que les deux entraînements
utilisent le même jeu de données et les mêmes paramètres principaux,
sauf le taux d'apprentissage :

  Paramètre                    Run 1    Run 2a
  ------------------------ --------- ---------
  Learning rate               0,0002    0,0001
  Rang LoRA                       16        16
  Epochs                           1         1
  Batch par appareil               2         2
  Gradient accumulation            8         8
  Nombre total de steps          375       375
  Validation loss finale     0,30602   0,30850
  Durée                       2168 s    2349 s
  Pic mémoire GPU            1,77 GB   1,77 GB

Run 1 présente une validation loss légèrement plus faible que Run 2a.
Cette différence ne suffit pas à déterminer définitivement le meilleur
adaptateur : une évaluation de la génération et des tâches de
programmation est encore nécessaire.

### État actuel

-   [x] Configuration `adapter_config.json` de Run 1 reçue et examinée.
-   [x] Rapports d'entraînement Run 1 et Run 2a examinés.
-   [ ] Récupérer les poids de l'adaptateur Run 1.
-   [ ] Vérifier la présence de tous les fichiers nécessaires à
    l'inférence.
-   [ ] Vérifier la compatibilité entre la base quantifiée utilisée à
    l'entraînement et la configuration d'inférence retenue.
-   [ ] Implémenter `llm/backends/qwen_lora.py`.
-   [ ] Tester le backend et vérifier le format de retour commun.
-   [ ] Comparer le modèle de base et le modèle fine-tuné sur des tâches
    identiques.

## 5. Prochaine étape : récupérer les poids LoRA

Le fichier `.safetensors` n'a pas besoin d'être ouvert manuellement.
C'est un fichier de poids destiné à être chargé par les bibliothèques
Python.

Demander au membre qui a effectué l'entraînement de fournir le dossier
complet de l'adaptateur, contenant au minimum :

``` text
run1/
├── adapter_config.json
└── adapter_model.safetensors
```

Si le fichier est trop volumineux pour être envoyé dans la conversation,
utiliser l'une des solutions suivantes :

1.  **Dépôt GitHub privé ou Hugging Face privé :** déposer le dossier de
    l'adaptateur et partager l'accès avec les personnes autorisées.
    Éviter de publier les poids sans accord de l'équipe.
2.  **Google Drive ou autre stockage partagé de l'équipe :** envoyer un
    lien avec les droits de téléchargement.
3.  **Archive ZIP :** compresser le dossier complet, sans supprimer ni
    renommer les fichiers.

Ne pas envoyer uniquement `adapter_config.json` : sans les poids, le
modèle ne peut pas appliquer les paramètres appris.

Une fois les fichiers récupérés, l'intégration pourra utiliser PEFT, par
exemple `PeftModel.from_pretrained(...)`, après avoir chargé une base
compatible. Le chemin et le type de chargement définitifs seront fixés
après vérification des fichiers et de l'environnement.

## 6. Tests et validation à terminer

-   [x] Tester le backend Stub.
-   [x] Tester le backend Qwen BF16.
-   [x] Tester le backend Qwen NF4.
-   [ ] Tester le backend Qwen LoRA.
-   [ ] Vérifier que tous les backends renvoient les quatre champs
    attendus.
-   [ ] Ajouter ou compléter les tests automatisés dans
    `tests/test_llm.py`.
-   [ ] Documenter les commandes d'installation et d'exécution.
-   [ ] Effectuer des mesures comparables sur plusieurs essais.

## 7. Conclusion de l'avancement

La couche d'abstraction `LLMClient` ainsi que les backends Stub, Qwen
BF16 et Qwen NF4 sont implémentés et testés. Une première comparaison
BF16/NF4 a été effectuée sur Kaggle T4.

La partie LoRA/QLoRA est en cours d'intégration. La configuration Run 1
et les rapports Run 1/Run 2a ont été examinés, mais les poids de
l'adaptateur ne sont pas encore disponibles. Le backend LoRA ne doit
donc pas être considéré comme terminé ou validé à ce stade.
