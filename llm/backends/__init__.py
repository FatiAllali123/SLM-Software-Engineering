
from .base import BaseBackend
from .stub import StubBackend

def __getattr__(name):
    if name == "QwenBaseBackend":
        from .qwen_base import QwenBaseBackend
        return QwenBaseBackend

    if name == "QwenNF4Backend":
        from .qwen_nf4 import QwenNF4Backend
        return QwenNF4Backend

    if name == "QwenLoRABackend":
        from .qwen_lora import QwenLoRABackend
        return QwenLoRABackend

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
