# ------------------------------------------------------------------
# Local override for PyInstaller's upstream torch hook.
#
# Goal:
# - keep the runtime-safe torch packaging behavior that EasyOCR needs
# - avoid recursing into torch testing/pallas paths that import optional JAX
#   helpers and spam Windows builds with irrelevant warnings
# ------------------------------------------------------------------

import os

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    get_package_paths,
    is_module_satisfies,
    logger,
)


def _include_torch_hiddenimport(name: str) -> bool:
    excluded_prefixes = (
        "torch.distributed",
        "torch.onnx",
        "torch.testing",
        "torch.utils._pallas",
        "torch._inductor",
        "torch._inductor.codegen.pallas",
        "torch._inductor.runtime.runtime_utils",
        "torch._higher_order_ops.triton_kernel_wrap",
        "torch._inductor.kernel.vendored_templates.cutedsl_grouped_gemm",
    )
    return not name.startswith(excluded_prefixes)


if is_module_satisfies("PyInstaller >= 6.0"):
    from PyInstaller.compat import is_linux, is_win
    from PyInstaller.utils.hooks import PY_DYLIB_PATTERNS

    module_collection_mode = "pyz+py"
    warn_on_missing_hiddenimports = False
    excludedimports = [
        "jax",
        "jaxlib",
        "jax_cuda12_plugin",
        "onnx",
        "onnxruntime",
        "onnxscript",
        "triton",
    ]

    datas = collect_data_files(
        "torch",
        excludes=[
            "**/*.h",
            "**/*.hpp",
            "**/*.cuh",
            "**/*.lib",
            "**/*.cpp",
            "**/*.pyi",
            "**/*.cmake",
        ],
    )
    hiddenimports = collect_submodules("torch", filter=_include_torch_hiddenimport, on_error="warn once")
    binaries = collect_dynamic_libs(
        "torch",
        search_patterns=PY_DYLIB_PATTERNS + ["*.so.*"],
    )

    if is_linux:
        def _infer_nvidia_hiddenimports():
            import packaging.requirements
            from _pyinstaller_hooks_contrib.compat import importlib_metadata
            from _pyinstaller_hooks_contrib.utils import nvidia_cuda as cudautils

            dist = importlib_metadata.distribution("torch")
            requirements = [packaging.requirements.Requirement(req) for req in dist.requires or []]
            requirements = [req.name for req in requirements if req.marker is None or req.marker.evaluate()]
            return cudautils.infer_hiddenimports_from_requirements(requirements)

        try:
            nvidia_hiddenimports = _infer_nvidia_hiddenimports()
        except Exception:
            logger.warning("hook-torch: failed to infer NVIDIA CUDA hidden imports!", exc_info=True)
            nvidia_hiddenimports = []
        logger.info("hook-torch: inferred hidden imports for CUDA libraries: %r", nvidia_hiddenimports)
        hiddenimports += nvidia_hiddenimports
        bindepend_symlink_suppression = ["**/torch/lib/*.so*"]

    if is_win:
        def _collect_mkl_dlls():
            import packaging.requirements
            from _pyinstaller_hooks_contrib.compat import importlib_metadata

            dist = importlib_metadata.distribution("torch")
            requirements = [packaging.requirements.Requirement(req) for req in dist.requires or []]
            requirements = [req.name for req in requirements if req.marker is None or req.marker.evaluate()]
            if "mkl" not in requirements:
                logger.info("hook-torch: this torch build does not depend on MKL...")
                return []

            try:
                dist = importlib_metadata.distribution("mkl")
            except importlib_metadata.PackageNotFoundError:
                return []
            requirements = [packaging.requirements.Requirement(req) for req in dist.requires or []]
            requirements = [req.name for req in requirements if req.marker is None or req.marker.evaluate()]
            requirements = ["mkl"] + requirements

            mkl_binaries = []
            logger.info("hook-torch: collecting DLLs from MKL and its dependencies: %r", requirements)
            for requirement in requirements:
                try:
                    dist = importlib_metadata.distribution(requirement)
                except importlib_metadata.PackageNotFoundError:
                    continue

                for dist_file in dist.files:
                    if not dist_file.match("../../Library/bin/*.dll"):
                        continue
                    dll_file = dist.locate_file(dist_file).resolve()
                    mkl_binaries.append((str(dll_file), "."))

            logger.info(
                "hook-torch: found MKL DLLs: %r",
                sorted([os.path.basename(src_name) for src_name, dest_name in mkl_binaries]),
            )
            return mkl_binaries

        try:
            mkl_binaries = _collect_mkl_dlls()
        except Exception:
            logger.warning("hook-torch: failed to collect MKL DLLs!", exc_info=True)
            mkl_binaries = []
        binaries += mkl_binaries
else:
    datas = [(get_package_paths("torch")[1], "torch")]

if is_module_satisfies("torch >= 2.0.0"):
    import sys

    new_limit = 5000
    if sys.getrecursionlimit() < new_limit:
        logger.info("hook-torch: raising recursion limit to %d", new_limit)
        sys.setrecursionlimit(new_limit)
