# État d'avancement : Piste 4 (Agents)

**Auteur :** Ikrame Houzane (D)
**Date :** 22 novembre 2026
**Branche :** `feature/agents-langgraph`
**Statut :** ✅ Terminé pour la Phase 1, en attente d'intégration

## 1. Ce qui est fait et sécurisé

L'architecture de la Piste 4 est complète et testée. Le code est push sur la branche `feature/agents-langgraph`.

### Architecture du Pipeline
- **Point d'entrée** : `app/agents/pipeline.py` contient la fonction `run_pipeline(task, code, language, mode, llm)`.
- **Conformité** : Respecte à 100 % le contrat d'API v1.0 (sections 10 et 11) défini par la Piste 3 (C).
- **Format de sortie** : Renvoie un dictionnaire avec les clés `result`, `metrics` et `trace`, prêt à être encapsulé dans le `ok_envelope` du backend.

### Les Agents (sans IA pour l'instant)
- **Analyse (`analysis.py`)** : Utilise le module natif Python `ast` pour extraire les fonctions et détecter les erreurs de syntaxe.
- **Génération de tests (`test_generation.py`)** : Génère un squelette de fichier `pytest` valide basé sur les fonctions détectées.
- **Revue (`review.py`)** : Détecte les mauvaises pratiques (utilisation de `print`, fonctions sans docstring, `except` nus).
- **Modes** : Le paramètre `mode` gère l'exécution en `single_agent` (1 appel) ou `multi_agent` (3 appels successifs).

### Tests et Validation
- **11 tests unitaires** passent au vert (`app/agents/test_agents.py` et `test_pipeline.py`).
- **Test de compatibilité** : Le pipeline a été testé avec une copie exacte du `TaskRequest` de la Piste 3. La sortie s'insère parfaitement dans son schéma de validation.
- **Évaluation Q3** : Le script `app/agents/evaluate_q3.py` est prêt. Il génère un fichier JSON de résultats comparant le mode Single-Agent et Multi-Agent (temps, tokens, appels).

## 2. Ce qui reste à faire

### Dépendances externes
- **En attente de C (Backend)** : Dès que la route `POST /analyze` est finalisée et push, faire l'intégration réelle en lançant le serveur FastAPI (`uvicorn`) et en testant le flux complet.
- **En attente de B (Modèle)** : Dès que le `RealLLMClient` est prêt, remplacer le `LLMClientStub` par le vrai client. Relancer les 11 tests et le script Q3 pour obtenir les métriques réelles (latence, tokens).

### Travaux en cours
- **Documentation** : Préparation de la section "Agents" pour le rapport final (README).
- **Préparation du test d'intégration du 25 novembre** : Script de test avec `curl` prêt à être exécuté dès validation des routes.

## 3. Instructions pour les autres membres

- **Fati (C)** : Tu peux utiliser `run_pipeline` directement. Les métriques `input_tokens` et `output_tokens` sont déjà calculées par le modèle (ou le stub). Le champ `model` et `precision` doivent être ajoutés par ton backend à partir du client LLM.
- **Salma (B)** : L'interface `LLMClient` (section 9 du contrat) est définie dans `app/agents/llm_protocol.py`. Ton `RealLLMClient` doit implémenter la méthode `generate(prompt, max_new_tokens, temperature)` et renvoyer un objet `LLMResponse`.