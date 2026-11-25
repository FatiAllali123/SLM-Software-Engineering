# Avancement — LLMClient et backends de modèles

**Projet :** Efficient Small Language Models for Intelligent Software Engineering, Testing and DevOps  
**Périmètre :** Couche d'abstraction `LLMClient`, intégration des backends Qwen et adaptation de l'interface destinée aux agents.  
**État :** Backends Stub, Qwen BF16, Qwen NF4 et Qwen LoRA implémentés et testés. `RealLLMClient` est prêt pour l'intégration avec le pipeline d'agents.

---

## 1. Objectif de mon travail

L'objectif est de mettre en place une interface commune permettant d'utiliser plusieurs modèles ou configurations de modèles sans modifier le code qui appelle le LLM.

Le projet repose sur deux niveaux d'abstraction :

1. **`LLMClient`** : interface interne qui reçoit une liste de messages et délègue la génération au backend sélectionné.
2. **`RealLLMClient`** : adaptateur qui expose une interface simple destinée aux agents du projet et retourne un objet `LLMResponse`.

Le format de retour de l'interface interne `LLMClient` est :

```python
{
    "text": str,
    "tokens_in": int,
    "tokens_out": int,
    "latency_s": float
}
```

L'interface destinée aux agents retourne un objet `LLMResponse` contenant :

```python
LLMResponse(
    text: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    model: str,
    precision: str
)
```

---

## 2. Architecture du projet

L'architecture actuelle est organisée de la manière suivante :

```text
SLM-Software-Engineering/
│
├── benchmarking/
│   └── config.json
│
├── llm/
│   ├── __init__.py
│   ├── client.py
│   └── backends/
│       ├── __init__.py
│       ├── base.py
│       ├── stub.py
│       ├── qwen_base.py
│       ├── qwen_nf4.py
│       └── qwen_lora.py
│
├── models/
│   ├── __init__.py
│   ├── llm_client.py
│   └── factory.py
│
└── tests/
    ├── test_llm.py
    ├── test_stub.py
    ├── test_models_llm_client.py
    └── test_factory.py
```

### Rôle des principaux fichiers

| Fichier | Fonctionnement |
|---|---|
| `llm/backends/base.py` | Définit la classe abstraite `BaseBackend`. |
| `llm/backends/stub.py` | Fournit un backend de test sans charger de véritable modèle. |
| `llm/backends/qwen_base.py` | Charge Qwen2.5-Coder-1.5B-Instruct en BF16. |
| `llm/backends/qwen_nf4.py` | Charge le modèle avec une quantification 4 bits NF4. |
| `llm/backends/qwen_lora.py` | Charge le modèle Qwen quantifié et ses adaptateurs LoRA. |
| `llm/client.py` | Expose l'interface interne commune `LLMClient`. |
| `models/llm_client.py` | Définit `LLMResponse`, `LLMClient`, `StubLLMClient` et `RealLLMClient`. |
| `models/factory.py` | Permet de sélectionner et d'instancier le client et le backend souhaités. |

---

## 3. Travail réalisé

### 3.1 Interface commune et backend Stub

- Création de `BaseBackend` avec une méthode `generate(messages)`.
- Création de l'interface interne `LLMClient`.
- Vérification de la validité de `messages` (type liste et liste non vide).
- Implémentation de `StubBackend` pour tester le contrat sans charger de véritable modèle.
- Vérification du format de retour commun.

### 3.2 Backend Qwen BF16

- Chargement de `Qwen/Qwen2.5-Coder-1.5B-Instruct`.
- Utilisation du format de conversation du tokenizer avec `apply_chat_template`.
- Génération de texte.
- Mesure des tokens d'entrée, des tokens de sortie et de la latence.
- Test effectué sur Kaggle avec GPU Tesla T4.

### 3.3 Backend Qwen NF4

- Chargement du même modèle avec `BitsAndBytesConfig`.
- Quantification 4 bits de type NF4.
- Activation de la double quantification.
- Configuration du type de calcul BF16.
- Vérification du chargement en 4 bits et test de génération sur Kaggle T4.

### 3.4 Comparaison BF16 / NF4

Mesures relevées lors d'un essai sur le même prompt :

| Mesure | Qwen BF16 | Qwen NF4 |
|---|---:|---:|
| Mémoire GPU allouée après chargement | 4054,37 MB | 1110,09 MB |
| Mémoire GPU réservée après chargement | 4098 MB | 1150 MB |
| Pic de mémoire GPU allouée | 4078,18 MB | 1141,38 MB |
| Tokens d'entrée | 46 | 46 |
| Tokens de sortie | 437 | 512 |
| Latence | 15,40 s | 25,33 s |

Sur cet essai, NF4 réduit fortement la mémoire GPU utilisée. La comparaison de latence doit cependant être interprétée avec prudence : la génération NF4 a atteint la limite de 512 nouveaux tokens, contrairement à BF16.

Il s'agit d'une mesure ponctuelle et non d'une moyenne sur plusieurs essais.

---

## 4. Intégration du backend Qwen LoRA

Le fine-tuning des adaptateurs a été réalisé par un autre membre de l'équipe. Mon travail consiste à intégrer ces adaptateurs comme configurations supplémentaires du modèle Qwen, tout en conservant l'architecture commune du projet.

### 4.1 Adaptateurs disponibles

Deux adaptateurs ont été récupérés et intégrés :

- `run1`
- `run2a`

Leurs configurations indiquent notamment :

| Paramètre | Valeur |
|---|---|
| Type PEFT | `LORA` |
| Modèle de base | `unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit` |
| Rang `r` | 16 |
| `lora_alpha` | 16 |
| `lora_dropout` | 0 |
| `bias` | `none` |
| `task_type` | `CAUSAL_LM` |
| `inference_mode` | `true` |
| Modules ciblés | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |

Chaque adaptateur contient notamment :

```text
adapter_run1/
├── adapter_config.json
├── adapter_model.safetensors
└── ...
```

Le même principe de structure est utilisé pour `adapter_run2a`.

### 4.2 Comparaison des rapports d'entraînement

Les rapports Run 1 et Run 2a indiquent que les deux entraînements utilisent le même jeu de données et les mêmes paramètres principaux, sauf le taux d'apprentissage.

| Paramètre | Run 1 | Run 2a |
|---|---:|---:|
| Learning rate | 0,0002 | 0,0001 |
| Rang LoRA | 16 | 16 |
| Epochs | 1 | 1 |
| Batch par appareil | 2 | 2 |
| Gradient accumulation | 8 | 8 |
| Nombre total de steps | 375 | 375 |
| Validation loss finale | 0,30602 | 0,30850 |
| Durée | 2168 s | 2349 s |
| Pic mémoire GPU | 1,77 GB | 1,77 GB |

Run 1 présente une validation loss légèrement plus faible que Run 2a. Cette différence ne suffit toutefois pas à déterminer définitivement le meilleur adaptateur. Une évaluation sur des tâches de programmation reste nécessaire.

### 4.3 Implémentation de `qwen_lora.py`

Le fichier `llm/backends/qwen_lora.py` a été implémenté pour gérer les adaptateurs LoRA.

Les principales fonctionnalités sont :

- Lecture et vérification des configurations des adaptateurs.
- Identification du modèle de base utilisé pendant le fine-tuning.
- Chargement du tokenizer.
- Chargement du modèle Qwen quantifié en 4 bits NF4.
- Chargement des adaptateurs avec PEFT.
- Gestion de plusieurs adaptateurs dans un même modèle.
- Changement de l'adaptateur actif avec `set_adapter()`.
- Possibilité d'utiliser les adaptateurs `run1` et `run2a`.
- Génération de texte avec retour des métriques.

Le changement d'adaptateur se fait ainsi :

```python
llm.backend.set_adapter("run1")

response = llm.generate(
    "Write a Python function that checks whether a number is prime.",
    max_new_tokens=256,
    temperature=0.0
)
```

Pour utiliser le deuxième adaptateur :

```python
llm.backend.set_adapter("run2a")
```

### 4.4 Tests de génération sur Kaggle

Le backend LoRA a été chargé et testé sur Kaggle avec un GPU Tesla T4.

Les deux adaptateurs ont été testés avec le même prompt :

> Write a Python function that checks whether a number is prime.

Les deux générations ont produit une implémentation correcte de la fonction `is_prime`.

Exemple de génération obtenue :

```python
def is_prime(n):
    if n <= 1:
        return False

    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False

    return True
```

Résultats observés lors des essais :

| Mesure | Run 1 | Run 2a |
|---|---:|---:|
| Modèle de base | Qwen2.5-Coder-1.5B-Instruct | Qwen2.5-Coder-1.5B-Instruct |
| Tokens d'entrée | 41 | — |
| Tokens de sortie | 189 | — |
| Latence | 19,675 s | 19,512 s |
| Génération correcte | Oui | Oui |

Les latences correspondent à des essais individuels. Elles ne permettent pas de conclure qu'un adaptateur est plus rapide que l'autre.

**Configuration utilisée :**

- Plateforme : Kaggle.
- GPU : Tesla T4.
- Modèle : `unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit`.
- Adaptateurs : `run1` et `run2a`.
- Précision configurée dans le backend : FP16.

Le checkpoint étant déjà quantifié, Transformers affiche un avertissement concernant la configuration de quantification fournie. Il faut distinguer la précision configurée dans le backend de la configuration effective de calcul interne de BitsAndBytes.

---

## 5. Adaptateur `RealLLMClient` pour les agents

Après l'implémentation des backends, une deuxième interface a été ajoutée pour permettre aux agents d'utiliser le modèle sans dépendre directement de son implémentation interne.

Le fichier concerné est :

```text
models/llm_client.py
```

### 5.1 Contrat demandé

L'interface attendue par le pipeline d'agents est :

```python
class LLMClient:
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0
    ) -> LLMResponse:
        ...
```

L'objet `LLMResponse` est une dataclass contenant :

```python
@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    precision: str
```

### 5.2 Implémentation de `RealLLMClient`

La classe `RealLLMClient` joue le rôle d'adaptateur entre les agents et l'interface interne `LLMClient`.

Elle permet notamment de :

- Recevoir un prompt sous forme de chaîne de caractères.
- Valider les paramètres de génération.
- Construire le message destiné au backend.
- Appeler l'interface interne `LLMClient`.
- Récupérer le texte généré et les métriques.
- Retourner un objet `LLMResponse` conforme au contrat demandé.

Les agents peuvent ainsi utiliser directement :

```python
response = llm.generate(
    prompt="Write a Python function that checks whether a number is prime.",
    max_new_tokens=512,
    temperature=0.0
)

print(response.text)
print(response.input_tokens)
print(response.output_tokens)
print(response.latency_ms)
print(response.model)
print(response.precision)
```

Ils n'ont pas besoin de connaître les détails du backend utilisé.

### 5.3 Vérification de l'interface

L'interface `RealLLMClient` a été testée sur Kaggle avec les deux adaptateurs.

Les tests ont confirmé :

- La génération de texte avec `run1`.
- La génération de texte avec `run2a`.
- Le changement d'adaptateur actif.
- La récupération du texte généré.
- La transmission des métriques.
- Le retour d'un objet `LLMResponse`.

Le nom du modèle retourné correspond au modèle de base réellement chargé :

```text
unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit
```

La précision retournée correspond à la valeur configurée dans le backend : `fp16`.

---

## 6. Factory et sélection des backends

Le fichier `models/factory.py` permet de sélectionner le client à utiliser selon le backend souhaité.

Les backends pris en charge sont :

- `stub`
- `qwen_base`
- `qwen_nf4`
- `qwen_lora`

Exemple d'utilisation avec le backend LoRA :

```python
from models.factory import get_llm_client

llm = get_llm_client(
    backend_type="qwen_lora",
    adapters={
        "run1": "/path/to/adapter_run1",
        "run2a": "/path/to/adapter_run2a"
    },
    active="run1",
    precision="fp16"
)

response = llm.generate(
    prompt="Write a Python function that checks whether a number is prime.",
    max_new_tokens=512,
    temperature=0.0
)

print(response.text)
```

Cette organisation permet de changer de backend sans modifier la manière dont les agents appellent le LLM.

---

## 7. Tests et validation

### État des vérifications

- [x] Créer et tester `BaseBackend`.
- [x] Implémenter et tester `StubBackend`.
- [x] Implémenter et tester `LLMClient`.
- [x] Implémenter et tester le backend Qwen BF16.
- [x] Implémenter et tester le backend Qwen NF4.
- [x] Effectuer une première comparaison BF16 / NF4.
- [x] Récupérer les poids des adaptateurs Run 1 et Run 2a.
- [x] Implémenter `llm/backends/qwen_lora.py`.
- [x] Charger les deux adaptateurs avec PEFT.
- [x] Tester la génération avec Run 1 et Run 2a sur Kaggle.
- [x] Implémenter `RealLLMClient`.
- [x] Vérifier la conformité de `RealLLMClient` avec le contrat d'API.
- [x] Tester `RealLLMClient` avec les deux adaptateurs.
- [x] Pousser les modifications sur GitHub.
- [ ] Vérifier l'intégration de `RealLLMClient` dans le pipeline d'agents.
- [ ] Effectuer l'évaluation Q3 : Single-Agent vs Multi-Agent.
- [ ] Effectuer des mesures comparables sur plusieurs essais pour les différents modèles et configurations.

### Commande pour exécuter les tests

```bash
python -m pytest tests/ -v
```

---

## 8. État GitHub

Les modifications concernant l'implémentation de `RealLLMClient` ont été poussées sur la branche :

```text
feature/llm-client
```

Dernier commit :

```text
f1af381 Fix model name in real LLM client
```

La branche contient notamment l'implémentation de l'adaptateur `RealLLMClient` et les corrections associées.

---

## 9. Conclusion de l'avancement

La couche d'abstraction `LLMClient` est implémentée et permet d'utiliser plusieurs configurations de modèles à travers une interface commune.

Les backends Stub, Qwen BF16, Qwen NF4 et Qwen LoRA ont été développés et testés. Les deux adaptateurs LoRA, Run 1 et Run 2a, ont été chargés avec succès et utilisés pour effectuer des générations sur Kaggle avec un GPU Tesla T4.

Une comparaison initiale entre Qwen BF16 et Qwen NF4 a également été réalisée afin d'observer les différences de consommation mémoire et de latence.

Enfin, l'adaptateur `RealLLMClient` a été implémenté dans `models/llm_client.py`. Il respecte le contrat d'API attendu par le pipeline d'agents et retourne un objet `LLMResponse` contenant le texte généré, les métriques et les informations du modèle.

**La partie implémentation du client et des backends est donc terminée.** La prochaine étape consiste à intégrer `RealLLMClient` dans le pipeline d'agents, puis à participer à l'évaluation Q3 comparant l'approche Single-Agent à l'approche Multi-Agent.