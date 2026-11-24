"""Configuration centrale du backend.

Toutes les valeurs modifiables (limites, outils autorisés...) sont ICI.
Pour changer une limite, on modifie seulement ce fichier.
Les valeurs par défaut viennent de docs/api_contract.md (section 8).
"""
import os
from dataclasses import dataclass

API_VERSION = "1.0"


@dataclass(frozen=True)
class Settings:
    # Limites (à confirmer avec D)
    max_code_bytes: int = 50 * 1024      # 50 Ko de code reçu au maximum
    max_exec_seconds: int = 10           # temps maximal d'exécution (et valeur par défaut)
    max_memory_mb: int = 256             # mémoire maximale du bac à sable
    max_output_chars: int = 10_000       # sortie d'exécution tronquée à ce nombre

    # Valeurs acceptées
    supported_languages: tuple = ("python",)
    allowed_tools: tuple = (
        "analyze_code",
        "generate_tests",
        "review_code",
        "execute_code",
    )

    # Choix du modèle : "stub" (faux modèle) ou "real" (vrai modèle)
    llm_backend: str = "stub"

    # Où chercher le code de B et de D (adaptateurs).
    # Si B ou D changent le nom de leur fichier, on change seulement ces deux lignes.
    llm_module: str = "models.llm_client"      # doit contenir get_llm_client()
    pipeline_module: str = "agents.pipeline"   # doit contenir run_pipeline()

    # Fichier du journal d'audit (SQLite)
    audit_db_path: str = "Backend/data/audit.db"


def get_settings() -> Settings:
    """Construit les réglages en lisant les variables d'environnement."""
    return Settings(
        llm_backend=os.getenv("LLM_BACKEND", "stub"),
        llm_module=os.getenv("LLM_MODULE", "models.llm_client"),
        pipeline_module=os.getenv("PIPELINE_MODULE", "agents.pipeline"),
        audit_db_path=os.getenv("AUDIT_DB_PATH", "Backend/data/audit.db"),
    )
