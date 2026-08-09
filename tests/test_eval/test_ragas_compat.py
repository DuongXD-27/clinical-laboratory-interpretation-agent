from __future__ import annotations

import builtins
import os
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest

from eval import ragas_compat
from eval.ragas_compat import import_ragas_api, install_vertexai_legacy_import_shim

FORBIDDEN_KEYS = {"OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "ANTHROPIC_API_KEY"}


def test_compat_01_fresh_process_import():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "from eval.ragas_compat import import_ragas_api; a=import_ragas_api(); print(a.ragas_version)",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "0.4.3"


def test_compat_02_version():
    assert import_ragas_api().ragas_version == "0.4.3"


def test_compat_03_required_classes_are_classes():
    api = import_ragas_api()

    assert isinstance(api.SingleTurnSample, type)
    assert isinstance(api.EvaluationDataset, type)
    assert isinstance(api.Faithfulness, type)
    assert isinstance(api.ContextPrecision, type)


def test_compat_04_shim_idempotence_and_real_module_preservation(monkeypatch):
    assert install_vertexai_legacy_import_shim() is True
    assert install_vertexai_legacy_import_shim() is True

    class RealChatVertexAI:
        pass

    real_module = types.ModuleType(ragas_compat.LEGACY_CHAT_VERTEXAI_MODULE)
    real_module.ChatVertexAI = RealChatVertexAI
    monkeypatch.setitem(sys.modules, ragas_compat.LEGACY_CHAT_VERTEXAI_MODULE, real_module)

    assert install_vertexai_legacy_import_shim() is False
    assert sys.modules[ragas_compat.LEGACY_CHAT_VERTEXAI_MODULE].ChatVertexAI is RealChatVertexAI


def test_compat_05_unrelated_import_error_not_swallowed(monkeypatch):
    def raise_unrelated(name):
        raise ModuleNotFoundError("unrelated import failure")

    monkeypatch.delitem(sys.modules, ragas_compat.LEGACY_CHAT_VERTEXAI_MODULE, raising=False)
    monkeypatch.setattr(ragas_compat.importlib.util, "find_spec", raise_unrelated)

    with pytest.raises(ModuleNotFoundError, match="unrelated import failure"):
        install_vertexai_legacy_import_shim()


def test_compat_06_no_site_packages_file_patching(monkeypatch):
    site_packages = str(Path(sys.executable).parents[1] / "Lib" / "site-packages").casefold()
    opened_for_write: list[str] = []
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        path = str(file).casefold()
        if site_packages in path and any(flag in mode for flag in ("w", "a", "+", "x")):
            opened_for_write.append(str(file))
            raise AssertionError(f"site-packages write attempted: {file}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    install_vertexai_legacy_import_shim()

    assert opened_for_write == []


def test_compat_07_no_environment_key_access(monkeypatch):
    class GuardedEnviron(dict):
        def __getitem__(self, key):
            if key in FORBIDDEN_KEYS:
                raise AssertionError(f"forbidden key read: {key}")
            return super().__getitem__(key)

        def get(self, key, default=None):
            if key in FORBIDDEN_KEYS:
                raise AssertionError(f"forbidden key read: {key}")
            return super().get(key, default)

    monkeypatch.setattr(os, "environ", GuardedEnviron(os.environ))

    install_vertexai_legacy_import_shim()


def test_compat_08_no_network_call(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    import_ragas_api()


def test_compat_09_dataset_construction_after_bootstrap():
    api = import_ragas_api()
    sample = api.SingleTurnSample(
        user_input="Câu hỏi mẫu",
        response="Câu trả lời mẫu",
        reference="Tham chiếu mẫu",
        retrieved_contexts=["Ngữ cảnh mẫu"],
    )
    dataset = api.EvaluationDataset(samples=[sample])

    assert len(dataset.samples) == 1


def test_compat_10_vertex_placeholders_unavailable():
    install_vertexai_legacy_import_shim()

    with pytest.raises(RuntimeError, match="Vertex AI is unavailable"):
        ragas_compat.UnavailableChatVertexAI()
    with pytest.raises(RuntimeError, match="Vertex AI is unavailable"):
        ragas_compat.UnavailableVertexAI()
