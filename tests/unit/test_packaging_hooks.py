from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_hook_module():
    hook_path = Path("packaging/hooks/hook-torch.py").resolve()
    spec = importlib.util.spec_from_file_location("aiautomouse_hook_torch", hook_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_local_torch_hook_excludes_pallas_and_testing_paths():
    module = _load_hook_module()

    assert module._include_torch_hiddenimport("torch.nn.functional") is True
    assert module._include_torch_hiddenimport("torch.testing._internal.inductor_utils") is False
    assert module._include_torch_hiddenimport("torch.utils._pallas") is False
    assert module._include_torch_hiddenimport("torch._inductor.codegen.pallas") is False
    assert module._include_torch_hiddenimport("torch.distributed.elastic") is False
    assert module._include_torch_hiddenimport("torch.onnx._internal.exporter") is False
