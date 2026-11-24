
import json
import time
from pathlib import Path

from llm.backends.base import BaseBackend


class QwenBaseBackend(BaseBackend):

    def __init__(self, config_path=None, precision=None):

        # Imports différés
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        if config_path is None:
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / "benchmarking" / "config.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.model_name = config["models"]["qwen"]
        self.generation_params = config["generation_params"]
        # Utiliser la précision fournie ou celle du fichier de configuration
        self.precision = precision if precision is not None else config["precision"]

        if not torch.cuda.is_available():
            raise RuntimeError("Aucun GPU CUDA disponible.")

        # Choisir le type numérique selon la précision
        if self.precision == "bf16":
            if not torch.cuda.is_bf16_supported():
                raise RuntimeError("BF16 non supporte par PyTorch.")

            torch_dtype = torch.bfloat16

        elif self.precision == "fp16":
            torch_dtype = torch.float16

        else:
            raise ValueError(
                "Précision non supportée. Choisir 'bf16' ou 'fp16'."
            )

        print("Chargement du tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name
        )

        print(f"Chargement du modele Qwen en {self.precision.upper()}...")

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            dtype=torch_dtype,
            device_map={"": 0}
            
        )

        self.model.eval()

        print("Qwen charge avec succes.")

    def generate(self, messages: list[dict]) -> dict:

        # Import différé pour la génération
        import torch

        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True
        )

        inputs = {
            key: value.to(self.model.device)
            for key, value in inputs.items()
        }

        tokens_in = inputs["input_ids"].shape[1]

        torch.cuda.synchronize()
        start = time.perf_counter()

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.generation_params["max_new_tokens"],
                do_sample=self.generation_params["do_sample"]
            )

        torch.cuda.synchronize()
        latency_s = time.perf_counter() - start

        generated_ids = outputs[0][tokens_in:]

        response = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True
        )

        return {
            "text": response,
            "tokens_in": int(tokens_in),
            "tokens_out": int(generated_ids.shape[0]),
            "latency_s": float(latency_s)
        }
