# Task Plan

- [x] Create project metadata, docs, config, and sample macros/assets
- [x] Implement macro models, loader, runtime context, actions, conditions, resolver, and runner
- [x] Implement Win32 bootstrap, input, hotkeys, windows helpers, and screen capture
- [x] Implement browser CDP, UIA, OCR, and template matching providers
- [x] Implement overlay, structured logging, artifact persistence, app bootstrap, and CLI/service commands
- [x] Add unit and integration tests
- [x] Run tests and document review results

## Review
- `python -m pytest -q` -> `10 passed, 4 skipped`
- `aiautomouse doctor` executed successfully and reported provider availability against the current machine
- `aiautomouse run <temp v2 smoke macro> --mode dry-run` executed successfully end-to-end
- `python -c "from aiautomouse.engine.loader import load_macro; ..."` confirmed the new structured sample macro loads as schema `2.0`
- `schemas/macro.schema.json` was regenerated from the Pydantic model layer
- `python -m compileall src tests` passed after the PySide6 desktop UI and service layer were added
- Live `tkinter` overlay window is implemented as an opt-in path via `AIAUTOMOUSE_LIVE_OVERLAY=1`; artifact overlay metadata is always written
- Legacy `v1` macros are migrated into internal compatibility steps at load time
- `python -m pip install PySide6 pywinauto easyocr pytesseract` completed successfully on this machine
- `easyocr` initially failed to import because `scikit-image 0.20.0` was ABI-incompatible with `numpy 2.2.6`; `python -m pip install --upgrade --force-reinstall scikit-image` resolved it
- `python -c "import PySide6, pywinauto, easyocr, pytesseract"` passed after the dependency fix
- `python -c "from aiautomouse.gui.app import launch_gui; print(...)"` and a `MainWindow` construction smoke test both passed
- `aiautomouse doctor` now reports `windows_uia`, `ocr`, and `template_match` providers as available on this machine
- Native Tesseract OCR was installed with `winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements`
- `config/app.yaml` now pins `ocr.tesseract_cmd` to `C:\Program Files\Tesseract-OCR\tesseract.exe`, so the app does not depend on session `PATH` refresh timing
- User `PATH` was updated to include `C:\Program Files\Tesseract-OCR` for future terminal sessions
- `python -c "import pytesseract; ...; print(pytesseract.get_tesseract_version())"` returned `5.4.0.20240606`
- `TesseractOcrBackend.is_available()` now checks for the actual executable instead of only the Python wrapper import

## Current Task

- [x] Design a shared OCR result model and matching/selection pipeline
- [x] Extend screen capture and runtime context for OCR capture metadata, last-known-area lookup, and debug state
- [x] Rebuild the OCR provider abstraction over Windows OCR, Tesseract, and EasyOCR with caching, rate limiting, anchors, and fallback hooks
- [x] Wire the new OCR query options into macro models, targeting, conditions, and runner behavior
- [x] Add unit tests for normalization, matching, selection, caching, rate limiting, and fallback behavior
- [x] Run tests and document review results for the OCR abstraction changes

## OCR Review

- Added a shared OCR result model with `text`, `normalized_text`, `bbox`, `line_id`, `confidence`, `provider`, and `screenshot_id`
- Screen capture now exposes `CaptureFrame` metadata and supports full-screen, monitor, region, and window capture selection
- OCR matching now supports whitespace collapse, casefold-based normalization, `exact` / `contains` / `regex` / `fuzzy` search modes, anchor-relative ranking, and last-known-area prioritization
- OCR provider caching is implemented for recognized lines and matched selections, and backend calls are throttled with a rate limiter
- OCR debug overlays now persist recognized text bounding boxes in artifacts and can render them live when `AIAUTOMOUSE_LIVE_OVERLAY=1`
- Text-target builders now support image-matching fallback by attaching an optional template locator to OCR-driven targets
- `python -m compileall src tests` passed after the OCR abstraction changes
- `python -m pytest -q tests/unit/test_ocr_provider.py` -> `6 passed`
- `python -m pytest -q` -> `16 passed, 4 skipped`
- `aiautomouse doctor` still reports the OCR provider as available on this machine
- `python - <<...>>` schema probe confirmed `FindTextStep` remains present in the generated JSON schema

## Current Task

- [x] Extend template resource and locator models to support template metadata, search hints, and click offsets without breaking existing macros
- [x] Implement an OpenCV image matching pipeline with grayscale/color/mask support, multi-scale search, NMS, duplicate filtering, region-first planning, and last-known-region priority
- [x] Add frame differencing, recent-success caching, multi-monitor/DPI-aware search planning, and structured debug artifacts/logging
- [x] Integrate chosen template click offsets and metadata into runtime target resolution/actions
- [x] Add unit tests for metadata loading, search prioritization, candidate filtering, caching, differencing, and coordinate behavior
- [x] Run verification, regenerate schema artifacts, and document review results

## Image Matching Review

- Template resources now support inline metadata objects and sidecar `.template.json|yaml` files, including `name`, `notes`, `threshold`, `preferred_theme`, `preferred_dpi`, `language_hint`, `search_region_hint`, `click_offset`, `use_grayscale`, and `use_mask`
- `TemplateLocatorSpec` and image-related macro steps/conditions now accept search overrides such as monitor targeting, search-region hints, multi-scale search, and last-known-region padding without breaking existing string-based template definitions
- The template-matching provider was rebuilt around an OpenCV pipeline with grayscale/color handling, optional mask matching, DPI-informed scale planning, multi-scale search, duplicate filtering, non-maximum suppression, and best-first region planning
- Search order now prioritizes recent successful areas, explicit regions, metadata region hints, window regions, monitor regions, and only then full-screen fallback
- Frame differencing now skips redundant re-searches on unchanged captures, and recent successful coordinates are cached in runtime context for subsequent steps
- Debug artifacts now include per-search JSON payloads and heatmap images under the run debug directory, and structured logs capture selected matches, reused frames, and failure reasons
- Template click offsets now flow through `TargetMatch.metadata` and are honored by click resolution when no step-specific offset overrides them
- `python -m compileall src tests` had already passed before this change set and the updated modules compiled cleanly under the test run
- `python -m pytest -q tests/unit/test_template_match.py` -> `6 passed`
- `python -m pytest -q` -> `22 passed, 4 skipped`
- `python -c "from aiautomouse.engine.schema import write_macro_json_schema; ..."` regenerated `schemas/macro.schema.json`
- `aiautomouse doctor` still reports `template_match: true` on this machine

## Current Task

- [x] Extend browser-related settings and macro schema to express Playwright-first locators, page opening, waits, and file uploads without breaking existing macros
- [x] Implement a dedicated Playwright browser adapter layer that owns session/page/locator actions and keeps desktop fallback outside the Playwright boundary
- [x] Integrate browser targets and browser-capable actions into the shared macro engine while preserving resolver order and desktop fallback behavior
- [x] Add unit tests for DOM locator resolution, browser-vs-desktop action routing, file upload behavior, and fallback behavior
- [x] Run verification, regenerate schema artifacts, and document review results

## Browser Adapter Review

- Added a dedicated `PlaywrightBrowserAdapter` layer under `src/aiautomouse/browser/` so Playwright session/page/locator logic is isolated from desktop providers and Win32 input code
- `DomLocatorSpec` now supports Playwright-first DOM strategies including role, name, text, css, selector, xpath, placeholder, label, test id, page filters, wait state, enabled/stable waits, network-idle waits, and page/context selection
- Added `open_page` and `upload_files` macro steps, plus browser settings for CDP URL, launch-on-demand, channel, headless mode, and Playwright timeouts
- Browser-target `TargetMatch` objects now carry DOM locator metadata and page identity so `click_ref`, `type_text`, `paste_snippet`, and `press_keys` can execute through Playwright instead of desktop input when appropriate
- `open_page` dry-run now seeds a synthetic browser page context so browser macros can continue through plan-only validation without launching a real browser window
- Resolver order remains `browser_cdp -> windows_uia -> windows_ocr -> template_match`; browser misses fall through to desktop providers without mixing OCR/image logic into Playwright code
- File upload now prefers direct `<input type="file">` assignment and falls back to Playwright file chooser handling only when needed
- Browser errors are emitted through structured logs and persisted into run debug artifacts, including best-effort browser screenshots on failures
- `config/app.yaml` now exposes browser launch settings, and `tests/integration/test_browser_cdp_macro.py` was updated to exercise the new browser-first path when desktop integration is explicitly enabled
- `python -m compileall src tests` passed
- `python -m pytest -q tests/unit/test_browser_adapter.py` -> `6 passed`
- `python -m pytest -q` -> `28 passed, 4 skipped`
- `python -c "from aiautomouse.engine.schema import write_macro_json_schema; ..."` regenerated `schemas/macro.schema.json`
- `python -m pip install playwright` and `python -m playwright install chromium` completed successfully on this machine
- `python -m aiautomouse.cli doctor` now reports `browser_cdp: true`

## Current Task

- [x] Add an authoring-only natural-language-to-macro conversion layer with deterministic parsing, validation, ambiguity reporting, fallback suggestions, and adapter recommendation output
- [x] Integrate the converter into services, CLI, and the Macros UI without introducing runtime LLM dependencies
- [x] Add unit tests for Korean prompt conversion, resource checklist generation, ambiguity handling, and CLI output
- [x] Run verification and document review results

## Authoring Review

- Added a dedicated `authoring` layer that converts natural-language descriptions into validated schema `2.0` macro JSON without changing the deterministic runtime engine
- The converter is rule-based and workspace-aware, so it emits ambiguity warnings, suggested fallback strategies, required snippet/template checklist items, and a browser/UIA/OCR/image adapter recommendation
- `MacroAuthoringService` exposes the flow to both the CLI and the PySide6 `Macros` tab, while runtime execution continues to load and run only structured JSON
- Added `aiautomouse author` for text or file-based prompt conversion, with optional macro JSON output writing
- The `Macros` tab now supports `Generate From Text` and shows diagnostics for ambiguous steps, missing resources, and recommended fallback strategies
- Fixed a Korean particle parsing bug in image-template detection so template identifiers do not capture trailing `을/를`
- `python -m py_compile src/aiautomouse/authoring/converter.py` passed
- `python -m pytest -q tests/unit/test_authoring.py` -> `3 passed`
- `python -m compileall src tests` passed
- `python -m pytest -q` -> `31 passed, 4 skipped`
- `python -m aiautomouse.cli author --text "창 제목에 Chrome이 포함된 창을 활성화하고, 화면에서 '업로드' 텍스트를 찾고 클릭한 뒤, snippet prompt_01을 붙여넣고 Enter를 눌러."` produced a validated macro JSON report with warnings, fallback suggestions, resource checklist output, and a `browser` adapter recommendation

## Current Task

- [x] Harden runtime diagnostics and artifact capture for before/after screenshots, failure summaries, active window snapshots, OCR dumps, and replay-friendly logs
- [x] Add crash-safe shutdown, portable logging defaults, and JSON settings persistence support without breaking existing YAML settings
- [x] Expand sample assets and macro pack, and add PyInstaller packaging assets/documentation
- [x] Add unit tests plus integration tests with mock desktop targets for diagnostics and persistence behavior
- [x] Run verification and document review results

## Operations Review

- Added atomic file writes for settings and structured artifact JSON so partial writes are less likely during crashes or forced termination
- Settings now support both YAML and JSON persistence, auto-create missing settings files, and expose portable `logs/` plus diagnostics configuration
- Runtime runs now emit `summary.json`, step before/after screenshots, per-step snapshot JSON, failed step ids, active window snapshots, and replay-friendly ordered `events.jsonl`
- OCR provider runs now dump raw backend output under `debug/ocr/`, while image matching keeps heatmaps and candidate dumps under `debug/template_match/`
- GUI and application shutdown paths now stop hotkeys, trigger emergency-stop tokens, and close capture/browser resources more safely
- GUI run history now surfaces failed step ids directly in the `Run / Logs` table
- Added a portable macro pack manifest, extra sample snippets, extra sample templates, a JSON sample config, and PyInstaller packaging assets under `packaging/`
- `python -m pytest -q tests/unit/test_settings_persistence.py tests/unit/test_workspace.py tests/unit/test_ocr_provider.py tests/integration/test_mock_desktop_targets.py` -> `12 passed`
- `python -m compileall src tests` passed
- `python -c "from pathlib import Path; compile(Path('packaging/aiautomouse.spec').read_text(...), ...)"` confirmed the PyInstaller spec parses successfully
- `python -m pytest -q` -> `35 passed, 4 skipped`
- `python -m aiautomouse.cli doctor` reports portable log paths plus all four providers as available on this machine
- `pyinstaller --version` -> `6.12.0`
- `pyinstaller --noconfirm --clean packaging/aiautomouse.spec` completed successfully and produced `dist/aiautomouse/`
- `dist\aiautomouse\aiautomouse.exe doctor` executed successfully against the frozen build

## Current Task

- [x] Trace the PyInstaller `easyocr/torch` warning path and separate build-noise causes from actual runtime-risk causes
- [x] Add a local PyInstaller torch hook override that excludes optional testing, Pallas/JAX, ONNX, and distributed paths not needed by EasyOCR at runtime
- [x] Add tests for the local packaging hook behavior and rebuild the frozen app to verify the warnings are gone
- [x] Re-run source and frozen verification and document the findings

## Packaging Warning Review

- Root cause: the upstream PyInstaller `hook-torch.py` used `collect_submodules("torch")`, which recursed into `torch.testing._internal.inductor_utils`; that module imports `torch.utils._pallas`, which probes JAX and triggered `jaxlib.mosaic.gpu` / `jax_cuda12_plugin` noise during the build
- This was a build-time analysis problem, not a proven runtime bug in the app itself; the main impact was log noise, slower builds, and risk of dragging in irrelevant optional subtrees
- Added a local override hook at `packaging/hooks/hook-torch.py` and wired it through `packaging/aiautomouse.spec`
- The local hook now filters out optional `torch.testing`, `torch.utils._pallas`, `torch._inductor`, `torch.onnx`, and `torch.distributed` areas, and explicitly excludes `jax`, `jaxlib`, `jax_cuda12_plugin`, `onnx`, `onnxruntime`, and `onnxscript`
- Added `tests/unit/test_packaging_hooks.py` to lock the filter behavior
- `python -m pytest -q tests/unit/test_packaging_hooks.py` -> `1 passed`
- `pyinstaller --noconfirm --clean packaging/aiautomouse.spec` now completes without the previous `jaxlib.mosaic.gpu` / `jax_cuda12_plugin` console warnings
- `python -m pytest -q` -> `36 passed, 4 skipped`
- `dist\aiautomouse\aiautomouse.exe doctor` still succeeds after the hook change, so the packaging cleanup did not break the frozen build
- Residual `jax` mentions in `build\aiautomouse\warn-aiautomouse.txt` now come from SciPy's optional array-API compatibility probing, not from the EasyOCR/Torch path that was under investigation
