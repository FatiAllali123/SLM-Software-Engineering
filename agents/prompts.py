"""
Fichier centralisé pour tous les prompts utilisés par les agents.
Permet le versionnage et facilite les expériences d'ablation (Q3).
"""

# Version actuelle des prompts (à incrémenter à chaque modification)
PROMPT_VERSION = "v1.0"

# ============================================================
# Prompts pour l'agent d'Analyse
# ============================================================

ANALYSIS_PROMPT_TEMPLATE = """Voici une analyse statique du code Python :
- Fonctions trouvées : {functions_summary}
- Problèmes détectés par l'analyseur : {issues_count}

Fais une brève analyse sémantique de ce code pour compléter cette analyse.
"""

# ============================================================
# Prompts pour l'agent de Génération de Tests
# ============================================================

TEST_GENERATION_PROMPT_TEMPLATE = """Voici un squelette de tests pytest généré automatiquement pour ce code :
{skeleton}

Complète ce squelette en remplaçant les 'TODO' et les '0' par de vraies valeurs de test pour les fonctions {function_names}.
Renvoie UNIQUEMENT le code Python final, sans aucune explication textuelle.
"""

# ============================================================
# Prompts pour l'agent de Documentation
# ============================================================

DOCUMENTATION_PROMPT_TEMPLATE = """Voici un code Python. Les fonctions suivantes n'ont pas de docstring : {functions_without_docstring}.
Génère une docstring pertinente pour chacune de ces fonctions, au format Google Style (Args, Returns).
Voici le code :
{code}
"""

# ============================================================
# Prompts pour l'agent de Revue
# ============================================================

REVIEW_PROMPT_TEMPLATE = """Fais une revue de ce code Python :
{code}
"""