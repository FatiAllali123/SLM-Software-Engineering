
import pytest

from models.factory import get_llm_client
from models.llm_client import StubLLMClient


def test_factory_stub():
    client = get_llm_client()

    assert isinstance(client, StubLLMClient)


def test_factory_unknown_backend():
    with pytest.raises(ValueError):
        get_llm_client(backend_type="unknown")


def test_factory_stub_with_extra_parameters():
    with pytest.raises(ValueError):
        get_llm_client(
            backend_type="stub",
            precision="fp16"
        )
