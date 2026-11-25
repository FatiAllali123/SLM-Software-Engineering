
import contextlib
import json
import time
from pathlib import Path

from llm.backends.base import BaseBackend


REQUIRED_ADAPTER_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
)

BASE = "base"


class QwenLoRABackend(BaseBackend):
    """
    Backend Qwen2.5-Coder-1.5B avec quantification NF4
    et prise en charge de plusieurs adaptateurs LoRA.

    Modes disponibles :
        - base : modèle sans adaptateur LoRA.
        - run1 : modèle avec le premier adaptateur.
        - run2a : modèle avec le deuxième adaptateur.
    """

    def __init__(
        self,
        adapters,
        active=None,
        config_path=None,
        precision="fp16",
        base_model=None,
    ):

        # =========================================================
        # 1. Validation des paramètres
        # =========================================================

        if precision not in ("fp16", "bf16"):
            raise ValueError(
                "Précision non supportée. Choisir 'fp16' ou 'bf16'."
            )

        self.precision = precision

        self.adapters = self._validate_adapters(adapters)

        if active is None:
            active = next(iter(self.adapters))

        self._check_name(active)
        self.active = active

        # =========================================================
        # 2. Imports différés
        # =========================================================

        import torch

        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        try:
            import peft
        except ImportError as e:
            raise ImportError(
                "Le paquet 'peft' est requis : pip install peft"
            ) from e

        self.torch = torch

        # =========================================================
        # 3. Chargement de la configuration du projet
        # =========================================================

        if config_path is None:
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / "benchmarking" / "config.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.generation_params = config["generation_params"]

        self.base_model_name = self._resolve_base_model(
            base_model,
            config["models"]["qwen"],
        )

        # =========================================================
        # 4. Vérification du GPU et de la précision
        # =========================================================

        if not torch.cuda.is_available():
            raise RuntimeError("Aucun GPU CUDA disponible.")

        if precision == "bf16" and not torch.cuda.is_bf16_supported():
            raise RuntimeError("BF16 non supporté par ce GPU.")

        torch_dtype = (
            torch.bfloat16
            if precision == "bf16"
            else torch.float16
        )

        # Vérifier la correspondance entre le modèle entraîné
        # et le modèle de base qui sera chargé.

        for name, info in self.adapter_info.items():

            trained_on = info.get("base_model_name_or_path")

            if trained_on and trained_on != self.base_model_name:
                print(
                    f"[attention] L'adaptateur '{name}' a été entraîné "
                    f"sur '{trained_on}' mais est chargé sur "
                    f"'{self.base_model_name}'."
                )

        # =========================================================
        # 5. Chargement du tokenizer
        # =========================================================

        print("Chargement du tokenizer...")

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.base_model_name
        )

        # =========================================================
        # 6. Configuration de la quantification NF4
        # =========================================================

        print(
            f"Chargement de Qwen en NF4 "
            f"(calcul {precision.upper()})..."
        )

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch_dtype,
        )

        base = AutoModelForCausalLM.from_pretrained(
            self.base_model_name,
            quantization_config=bnb_config,
            dtype=torch_dtype,
            device_map={"": 0},
        )

        # =========================================================
        # 7. Chargement des adaptateurs LoRA
        # =========================================================

        print(
            f"Attachement des adaptateurs : {list(self.adapters)}..."
        )

        self.model = self._attach_adapters(base)

        self.set_adapter(self.active)

        self.model.eval()

        print(
            "Qwen + LoRA chargés avec succès. "
            f"Adaptateur actif : {self.active}"
        )

    # =============================================================
    # Validation des adaptateurs
    # =============================================================

    def _validate_adapters(self, adapters):

        if not isinstance(adapters, dict) or not adapters:
            raise ValueError(
                "adapters doit être un dictionnaire "
                "{nom: chemin} non vide."
            )

        validated = {}
        self.adapter_info = {}

        for name, path in adapters.items():

            if not isinstance(name, str) or not name:
                raise ValueError(
                    "Chaque adaptateur doit avoir un nom non vide."
                )

            if name == BASE:
                raise ValueError(
                    f"'{BASE}' est un nom réservé au modèle de base."
                )

            path = Path(path)

            if not path.is_dir():
                raise FileNotFoundError(
                    f"Dossier de l'adaptateur introuvable : {path}"
                )

            for fname in REQUIRED_ADAPTER_FILES:

                if not (path / fname).is_file():
                    raise FileNotFoundError(
                        f"Fichier '{fname}' manquant dans {path}"
                    )

            with open(
                path / "adapter_config.json",
                "r",
                encoding="utf-8",
            ) as f:

                self.adapter_info[name] = json.load(f)

            validated[name] = path

        return validated

    # =============================================================
    # Détermination du modèle de base
    # =============================================================

    def _resolve_base_model(self, base_model, default_name):

        if base_model:
            return base_model

        declared = {
            info.get("base_model_name_or_path")
            for info in self.adapter_info.values()
        } - {None}

        if len(declared) > 1:
            raise ValueError(
                "Les adaptateurs ne déclarent pas le même modèle de base."
            )

        return declared.pop() if declared else default_name

    # =============================================================
    # Vérification du nom de l'adaptateur
    # =============================================================

    def _check_name(self, name):

        if name != BASE and name not in self.adapters:
            raise ValueError(
                f"Adaptateur inconnu : '{name}'. "
                f"Choix disponibles : {[BASE] + list(self.adapters)}"
            )

    # =============================================================
    # Attachement des adaptateurs au modèle
    # =============================================================

    def _attach_adapters(self, base_model):

        from peft import PeftModel

        names = list(self.adapters)

        # Charger le premier adaptateur avec le modèle de base.

        model = PeftModel.from_pretrained(
            base_model,
            str(self.adapters[names[0]]),
            adapter_name=names[0],
        )

        # Ajouter les autres adaptateurs au même modèle.

        for name in names[1:]:

            model.load_adapter(
                str(self.adapters[name]),
                adapter_name=name,
            )

        return model

    # =============================================================
    # Changer l'adaptateur actif
    # =============================================================

    def set_adapter(self, name):

        self._check_name(name)

        if name != BASE:
            self.model.set_adapter(name)

        self.active = name

    # =============================================================
    # Génération de texte
    # =============================================================

    def generate(self, messages: list[dict]) -> dict:

        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )

        inputs = {
            key: value.to(self.model.device)
            for key, value in inputs.items()
        }

        tokens_in = inputs["input_ids"].shape[1]

        # Désactiver temporairement LoRA pour le mode base.

        adapter_off = (
            self.model.disable_adapter()
            if self.active == BASE
            else contextlib.nullcontext()
        )

        # Mesurer précisément le temps de génération sur GPU.

        self.torch.cuda.synchronize()

        start = time.perf_counter()

        with adapter_off, self.torch.inference_mode():

            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.generation_params["max_new_tokens"],
                do_sample=self.generation_params["do_sample"],
            )

        self.torch.cuda.synchronize()

        latency_s = time.perf_counter() - start

        # Extraire uniquement les nouveaux tokens générés.

        generated_ids = outputs[0][tokens_in:]

        text = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
        )

        return {
            "text": text,
            "tokens_in": int(tokens_in),
            "tokens_out": int(generated_ids.shape[0]),
            "latency_s": float(latency_s),
        }
