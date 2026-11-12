
import json
import time
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from llm.backends.base import BaseBackend


class QwenBaseBackend(BaseBackend):

    def __init__(self, config_path=None):

        if config_path is None:
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / "benchmarking" / "config.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.model_name = config["models"]["qwen"]
        self.generation_params = config["generation_params"]
        self.precision = config["precision"]

        if not torch.cuda.is_available():
            raise RuntimeError("Aucun GPU CUDA disponible.")

        if self.precision != "bf16":
            raise ValueError("La precision attendue est BF16.")

        if not torch.cuda.is_bf16_supported():
            raise RuntimeError("BF16 non supporte par PyTorch.")

        print("Chargement du tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name
        )

        print("Chargement du modele Qwen en BF16...")

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            device_map={"": 0}
        )

        self.model.eval()

        print("Qwen charge avec succes.")

    def generate(self, messages: list[dict]) -> dict:

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
