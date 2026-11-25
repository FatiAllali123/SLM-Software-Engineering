# État d'avancement : Piste 4 (Agents)

**Auteur :** Ikrame Houzane (D)
**Date :** 25 novembre 2026
**Branche :** `feature/agents-langgraph`
**Statut :** ✅ Terminé pour la Phase 1, en attente d'intégration avec le backend et le modèle réel

## 1. Ce qui est fait et sécurisé

L'architecture de la Piste 4 est complète et testée. Le code est push sur la branche `feature/agents-langgraph`.

### Architecture du Pipeline
- **Point d'entrée** : `app/agents/pipeline.py` contient la fonction `run_pipeline(task, code, language, mode, llm)`.
- **Conformité** : Respecte à 100 % le contrat d'API v1.0 (sections 10 et 11) défini par la Piste 3 (C).
- **Format de sortie** : Renvoie un dictionnaire avec les clés `result`, `metrics` et `trace`, prêt à être encapsulé dans le `ok_envelope` du backend.
- **Gestion des erreurs** : Lève une exception `AgentInvalidInputError` (code `INVALID_INPUT`) si le code fourni est invalide, permettant au backend de renvoyer une erreur 400 propre.

### Les Agents (Basés sur le module `ast` et le LLM)
- **Analyse (`analysis.py`)** : Utilise `ast` pour extraire les fonctions et détecter les erreurs de syntaxe. Le texte du modèle est ensuite intégré au résultat.
- **Génération de tests (`test_generation.py`)** : Génère un squelette de fichier `pytest` valide basé sur les fonctions détectées et le texte du modèle.
- **Revue (`review.py`)** : Détecte les mauvaises pratiques (utilisation de `print`, fonctions sans docstring, `except` nus) et renvoie un verdict honnête (`approve` ou `request_changes`).
- **Modes** : Le paramètre `mode` gère l'exécution en `single_agent` (1 appel) ou `multi_agent` (3 appels successifs via le graphe LangGraph).

### Qualité et Tests
- **12 tests unitaires** passent au vert (`app/agents/test_agents.py` et `test_pipeline.py`), incluant un test spécifique pour l'exception `AgentInvalidInputError`.
- **Test de compatibilité** : Le pipeline a été testé avec une copie exacte du `TaskRequest` de la Piste 3. La sortie s'insère parfaitement dans son schéma de validation.
- **Corrections d'architecture (retour de relecture)** : 
  - Le pipeline passe désormais une chaîne de caractères (`str`) au client LLM (et non plus une liste), ce qui est 100 % compatible avec le contrat de Fati et le futur client de Salma.
  - Le mode `multi_agent` utilise le **vrai graphe LangGraph** (`run_multi_agent`) qui exécute les 3 agents à la suite.
  - Le texte généré par le modèle est bien récupéré et intégré dans le résultat final (il n'est plus jeté).

### Évaluation Q3
- Le script `app/agents/evaluate_q3.py` et le dataset `app/agents/q3_dataset.json` (10 tâches variées) sont prêts. Le script génère un fichier JSON comparant le mode Single-Agent et Multi-Agent (temps, tokens, appels).
- **Note importante** : Les chiffres actuels sont des simulations basées sur le stub. L'évaluation réelle (avec le vrai modèle de Salma) mesurera le coût réel en tokens et en latence, ainsi que la qualité des résultats.

## 2. Ce qui reste à faire

### Dépendances externes
- **En attente de C (Backend)** : Dès que la route `POST /analyze` est finalisée et push, faire l'intégration réelle en lançant le serveur FastAPI (`uvicorn`) et en testant le flux complet.
- **En attente de B (Modèle)** : Dès que le `RealLLMClient` est prêt, remplacer le `LLMClientStub` par le vrai client. Relancer les 12 tests et le script Q3 pour obtenir les métriques réelles (latence, tokens).

### Travaux en cours
- **Documentation** : Préparation de la section "Agents" pour le rapport final (README).
- **Préparation du test d'intégration** : Script de test avec `curl` prêt à être exécuté dès validation des routes.

## 3. Instructions pour les autres membres

- **Fati (C)** : Tu peux utiliser `run_pipeline` directement. Les métriques `input_tokens` et `output_tokens` sont déjà calculées par le modèle (ou le stub). Le champ `model` et `precision` doivent être ajoutés par ton backend à partir du client LLM. L'exception `AgentInvalidInputError` peut être attrapée pour renvoyer une 400.
- **Salma (B)** : L'interface `LLMClient` (section 9 du contrat) est définie dans `app/agents/llm_protocol.py`. Ton `RealLLMClient` doit implémenter la méthode `generate(prompt, max_new_tokens, temperature)` et renvoyer un objet `LLMResponse`.