from __future__ import annotations

import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import sys
import types
from dataclasses import dataclass
from typing import Any

LEGACY_CHAT_VERTEXAI_MODULE = "langchain_community.chat_models.vertexai"
LEGACY_LLMS_MODULE = "langchain_community.llms"
EXPECTED_RAGAS_VERSION = "0.4.3"


class UnavailableChatVertexAI:
    """Compatibility placeholder; Vertex AI is not available."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Vertex AI is unavailable in the offline RAGAS compatibility shim.")


class UnavailableVertexAI:
    """Compatibility placeholder; Vertex AI is not available."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Vertex AI is unavailable in the offline RAGAS compatibility shim.")


@dataclass(frozen=True)
class RagasApi:
    EvaluationDataset: type
    SingleTurnSample: type
    Faithfulness: type
    ContextPrecision: type
    llm_factory: object
    ragas_version: str
    compatibility_shim_applied: bool


def install_vertexai_legacy_import_shim() -> bool:
    """Install a narrow import shim for RAGAS 0.4.3's optional legacy Vertex AI imports."""
    loaded_module = sys.modules.get(LEGACY_CHAT_VERTEXAI_MODULE)
    if loaded_module is not None:
        return getattr(loaded_module, "ChatVertexAI", None) is UnavailableChatVertexAI

    try:
        if importlib.util.find_spec(LEGACY_CHAT_VERTEXAI_MODULE) is not None:
            return False
    except ModuleNotFoundError as exc:
        if exc.name in (LEGACY_CHAT_VERTEXAI_MODULE, "langchain_community"):
            pass
        else:
            raise

    compatibility_module = types.ModuleType(LEGACY_CHAT_VERTEXAI_MODULE)
    compatibility_module.ChatVertexAI = UnavailableChatVertexAI
    compatibility_module.__doc__ = "Compatibility module for RAGAS 0.4.3 offline imports."
    compatibility_module.__spec__ = importlib.machinery.ModuleSpec(LEGACY_CHAT_VERTEXAI_MODULE, loader=None)
    sys.modules[LEGACY_CHAT_VERTEXAI_MODULE] = compatibility_module

    llms_module = importlib.import_module(LEGACY_LLMS_MODULE)
    if "VertexAI" not in vars(llms_module):
        setattr(llms_module, "VertexAI", UnavailableVertexAI)

    return True


def import_ragas_api() -> RagasApi:
    compatibility_shim_applied = install_vertexai_legacy_import_shim()

    ragas_version = importlib.metadata.version("ragas")
    if ragas_version != EXPECTED_RAGAS_VERSION:
        raise RuntimeError(f"Expected ragas {EXPECTED_RAGAS_VERSION}, found {ragas_version}")

    from ragas import EvaluationDataset
    from ragas.dataset_schema import SingleTurnSample
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecision, Faithfulness

    return RagasApi(
        EvaluationDataset=EvaluationDataset,
        SingleTurnSample=SingleTurnSample,
        Faithfulness=Faithfulness,
        ContextPrecision=ContextPrecision,
        llm_factory=llm_factory,
        ragas_version=ragas_version,
        compatibility_shim_applied=compatibility_shim_applied,
    )
