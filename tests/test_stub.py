
from llm import LLMClient
from llm.backends import StubBackend

# Initialiser le backend
backend = StubBackend()

# Créer le client
client = LLMClient(backend)

# Préparer les messages
messages = [
    {
        "role": "system",
        "content": "Tu es un assistant spécialisé en programmation."
    },
    {
        "role": "user",
        "content": "Explique une boucle for en Python."
    }
]

# Générer la réponse
result = client.generate(messages)

print("Réponse :", result["text"])
print("Tokens entrée :", result["tokens_in"])
print("Tokens sortie :", result["tokens_out"])
print("Latence :", result["latency_s"])
