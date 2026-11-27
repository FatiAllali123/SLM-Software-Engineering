import json
import os
from datetime import datetime
from .prompts import PROMPT_VERSION

class AgentLogger:
    """Système de logging professionnel pour tracer les étapes des agents (LLMOps)."""
    
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "agent_traces.jsonl")

    def log_step(self, agent_name: str, step: str, details: dict):
        """Écrit une ligne de log au format JSONL."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt_version": PROMPT_VERSION,
            "agent": agent_name,
            "step": step,
            "details": details
        }
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

logger = AgentLogger()