
import pytest

from models.llm_client import (
    LLMResponse,
    StubLLMClient,
    RealLLMClient
)

from llm.backends.stub import StubBackend


def test_stub_llm_client():
    client = StubLLMClient()

    response = client.generate("Explique Python")

    assert isinstance(response, LLMResponse)
    assert response.model == "stub"
    assert response.precision == "none"
    assert response.text.startswith("[STUB]")
    assert response.input_tokens > 0


def test_real_llm_client_with_stub_backend():
    client = RealLLMClient(StubBackend())

    response = client.generate("Explique Python")

    assert isinstance(response, LLMResponse)
    assert response.text.startswith("[STUB]")
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.model == "stub"
    assert response.precision == "none"


def test_empty_prompt():
    client = StubLLMClient()

    with pytest.raises(ValueError):
        client.generate("")


def test_invalid_prompt_type():
    client = StubLLMClient()

    with pytest.raises(TypeError):
        client.generate(123)


def test_invalid_max_new_tokens():
    client = StubLLMClient()

    with pytest.raises(ValueError):
        client.generate("Test", max_new_tokens=0)


def test_invalid_temperature():
    client = StubLLMClient()

    with pytest.raises(ValueError):
        client.generate("Test", temperature=3)


def test_real_client_without_backend():
    with pytest.raises(ValueError):
        RealLLMClient(None)
