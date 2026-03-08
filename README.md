# AIAutoMouse

Windows 10 oriented desktop automation toolkit for VS Code + Codex workflows. Runtime execution is deterministic: macros are validated JSON or YAML, provider order is fixed, and no LLM calls happen during execution.

## Capabilities
- Deterministic YAML or JSON macros
- Authoring-only natural-language to validated macro JSON conversion
- Browser-first target resolution: DOM / Playwright, then Windows UIA, then OCR, then template matching
- Dry-run and execute modes
- Global hotkey service plus emergency stop hotkey
- Structured logs, before/after screenshots, step diagnostics, OCR dumps, image-match dumps, and replay-friendly JSONL events
- PySide6 desktop UI with `Snippets`, `Templates`, `Macros`, `Run / Logs`, and `Settings`
- Portable packaging support through PyInstaller

## Architecture
- `Authoring`: natural-language descriptions can be converted into validated macro JSON, but the runtime only persists and executes structured macro files.
- `MacroEngine`: deterministic step runner with retry policies, step timing, failure summaries, and explicit provider ordering.
- `Target resolution`: Browser DOM / Playwright first, then Windows UI Automation, then OCR, then OpenCV template matching.
- `Runtime context`: keeps found regions, screenshots, clipboard state, active window info, retry counters, OCR/image caches, and step timing data.
- `Artifacts`: each run writes `events.jsonl`, `summary.json`, `screenshots/`, `debug/steps/`, `debug/ocr/`, `debug/template_match/`, and overlay snapshots.
- `Persistence`: settings can be stored as YAML or JSON. Portable deployments should prefer [config/app.json](/c:/coding/aiautomouse/config/app.json).

## Quick Start
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
playwright install chromium
aiautomouse doctor
aiautomouse gui
```

To enable browser DOM automation against an existing browser session:

```powershell
msedge.exe --remote-debugging-port=9222
```

## Commands
- `aiautomouse gui`
- `aiautomouse author --text "<natural language>" [--output generated.json]`
- `aiautomouse run <macro> --mode execute|dry-run`
- `aiautomouse serve --hotkeys config/hotkeys.yaml`
- `aiautomouse doctor`

To enable the live `tkinter` overlay window in addition to overlay artifacts:

```powershell
$env:AIAUTOMOUSE_LIVE_OVERLAY = "1"
```

## Emergency Stop
- Default emergency stop hotkey: `Ctrl+Alt+Pause`
- The same hotkey works for direct runs and the background hotkey service.
- This binding is configurable in Settings and in the settings file.

## Project Layout
- `architecture.md`: system architecture, macro schema, provider order, DPI behavior, and runtime details
- `config/`: runtime settings, including [app.yaml](/c:/coding/aiautomouse/config/app.yaml), [app.json](/c:/coding/aiautomouse/config/app.json), and hotkey bindings
- `macros/samples/`: runnable sample macros
- `macros/packs/portable_demo/`: sample macro pack manifest and notes for portable builds
- `schemas/macro.schema.json`: generated JSON Schema for the current macro format
- `assets/`: snippets and image templates
- `src/aiautomouse/`: application code
- `tests/`: unit and integration coverage

## Macro Schema
- Current schema version: `2.0`
- Backward compatibility: legacy `v1` `precondition/action/postcondition/rollback/fallback` macros are migrated into internal compatibility steps at load time
- Reusable flow features: `variables`, `anchors`, `regions`, `retry_policies`, `submacros`, `if`, `retry`, `verify_any`, `verify_all`
- Runtime step coverage includes `focus_window`, `find_text`, `find_image`, `click`, `double_click`, `right_click`, `type_text`, `paste_snippet`, `press_keys`, `wait_for_text`, `wait_for_image`, `verify_text`, `verify_image`, `retry`, and `abort`

Recommended sample macros:
- `macros/samples/focus_and_paste.json`
- `macros/samples/image_click_retry.json`
- `macros/samples/conditional_submit.json`
- `macros/samples/upload_and_submit.json`

## UI Tabs
- `Snippets`: create, edit, and delete text snippets
- `Templates`: import image templates or capture them from screen selection
- `Macros`: edit JSON or YAML macros, validate against schema, generate from text, and register or unregister hotkeys
- `Run / Logs`: execute macros in dry-run or execute mode, inspect recent runs, replay logs, failure step ids, and screenshots
- `Settings`: configure CDP, OCR backend order, capture backend, overlay, diagnostics, hotkey service, and run history limits

## Authoring
```powershell
aiautomouse author --text "창 제목에 Chrome이 포함된 창을 활성화하고, 화면에서 '업로드' 텍스트를 찾고 클릭한 뒤, snippet prompt_01을 붙여넣고 Enter를 눌러."
```

The `author` command only runs during macro authoring. It emits:
- validated macro JSON
- ambiguous step warnings
- suggested fallback strategies
- required snippet or template checklist items
- a browser / UIA / OCR / image adapter recommendation

Runtime execution still stores and runs only structured JSON without any LLM calls.

## Packaging
Portable packaging uses PyInstaller:

```powershell
python -m pip install -r requirements.txt
python -m pip install PyInstaller
playwright install chromium
pyinstaller --noconfirm --clean packaging/aiautomouse.spec
```

Helper script:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build_portable.ps1
```

Portable builds should keep these folders next to the executable:
- `config/`
- `assets/`
- `macros/`
- `schemas/`
- `logs/`

## Diagnostics And Logs
- Run artifacts default to `logs/runs/<run_id>/`
- `events.jsonl`: replay-friendly structured log with ordered event sequence numbers
- `summary.json`: macro status, failed step id, active window snapshot, step timings, and replay log path
- `screenshots/`: before, after, and failure screenshots
- `debug/steps/`: per-step snapshots with phase, attempt, references, and active window data
- `debug/ocr/`: raw OCR backend output dumps and chosen OCR result
- `debug/template_match/`: image-match heatmaps, chosen bbox, top-N candidates, and failure reasons

## Limitations
- Windows 10 is the primary target. Other operating systems are not supported.
- Browser automation is Chromium-family only.
- OCR quality depends on font rendering, scaling, language packs, and backend availability.
- Template matching is sensitive to DPI, theme, and animation; region scoping and fresh templates matter.
- Some native file dialogs and protected UI surfaces may require OCR or image fallbacks.

## Troubleshooting
- `doctor` reports a provider as unavailable:
  install the missing dependency, then run `aiautomouse doctor` again.
- Browser macros do not resolve DOM locators:
  start Edge or Chrome with `--remote-debugging-port=9222`, or allow Playwright launch-on-demand.
- Tesseract OCR is unavailable:
  confirm `ocr.tesseract_cmd` points to `tesseract.exe` and the executable exists.
- Runs fail with the wrong target selected:
  tighten the macro with `region`, `anchor_text`, `window`, or `search_region_hint`.
- A run stops unexpectedly:
  inspect `logs/runs/<run_id>/summary.json`, `events.jsonl`, `debug/ocr/`, and `debug/template_match/`.
- Portable builds start but assets are missing:
  verify the PyInstaller build includes `config/`, `assets/`, `macros/`, and `schemas/`.

## DPI Tips
- The app initializes per-monitor-v2 DPI awareness on startup.
- Capture templates on the same monitor scale where they will be matched.
- Prefer region searches over full-screen searches on mixed-DPI multi-monitor setups.
- If clicks drift on one monitor only, recreate the template at that monitor's DPI.
- OCR and template fallback become more stable when searches are anchored to previously found regions.
