import time
from typing import List, Dict

class LLMClientStub:
    def generate(self, messages: List[Dict[str, str]]) -> Dict:
        """Simule un appel LLM pour que tu puisses coder les agents sans GPU."""
        start_time = time.time()
        
        # Simulation d'un temps de génération (ex: 0.5s)
        time.sleep(0.5) 
        
        # On récupère le dernier message utilisateur pour faire semblant de répondre
        prompt = messages[-1]["content"]
        
        # Fausse réponse basée sur le prompt (pour que ce soit réaliste)
        response_text = f"Stub analysis for: {prompt[:30]}...\nResult: Looks good."
        
        latency = time.time() - start_time
        
        return {
            "text": response_text,
            "tokens_in": len(prompt.split()), # estimation grossière
            "tokens_out": len(response_text.split()),
            "latency_s": round(latency, 3)
        }