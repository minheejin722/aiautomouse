# Windows Desktop Automation MVP Architecture

## Goals
- Provide a deterministic automation engine driven by YAML or JSON macros.
- Prefer robust locators in this order: Browser DOM via CDP, Windows UI Automation, OCR, then template matching.
- Separate authoring from execution. LLMs help write macros, not run them.
- Support Windows 10 with per-monitor DPI awareness and multi-monitor coordinates.
- Record every run with logs, screenshots, and overlay/debug artifacts.

## Runtime Model
The system is split into five layers:

1. Bootstrap
   - Enables per-monitor DPI awareness before any UI capture or input injection.
   - Loads application settings and prepares artifact directories.
2. Engine
   - Parses macros into typed models and validates against schema `2.0`.
   - Evaluates deterministic step nodes, nested control flow, retry rules, and legacy compatibility wrappers.
   - Operates in either `dry-run` or `execute` mode while preserving runtime context.
3. Providers
   - Resolve targets into normalized `TargetMatch` objects.
   - Fixed priority: `browser_cdp`, `windows_uia`, `ocr`, `template_match`.
4. Platform
   - Wraps Win32 hotkeys, SendInput, window metadata, virtual desktop coordinates, and screen capture.
5. Runtime Services
   - Emergency stop, overlay, structured logging, and artifact persistence.
6. Desktop UI
   - PySide6 shell with `Snippets`, `Templates`, `Macros`, `Run / Logs`, and `Settings` tabs.
   - Uses repository/services layers to edit assets, launch runs, and control the hotkey service.

## Macro Execution Contract
Current schema version is `2.0`. The execution engine now supports typed step nodes such as:
- `focus_window`
- `find_text`
- `find_image`
- `click_ref`
- `click_xy`
- `click`
- `double_click_ref`
- `double_click`
- `right_click_ref`
- `right_click`
- `type_text`
- `paste_snippet`
- `press_keys`
- `wait_for_text`
- `wait_for_image`
- `verify_text`
- `verify_image`
- `verify_any`
- `verify_all`
- `if`
- `retry`
- `call_submacro`
- `abort`

Execution rules:
- Steps can carry inline or named retry policies.
- `find_*` and `wait_for_*` steps can save resolved matches into context refs.
- `verify_any` and `verify_all` evaluate structured condition trees.
- `if` and `retry` are control-flow steps that execute nested step lists.
- `call_submacro` executes reusable internal submacros or another macro file.
- The engine preserves context for refs, screenshots, clipboard state, active window info, retry counters, and step timing.
- Legacy `v1` macros are still accepted and migrated into internal compatibility steps at load time.

## Target Resolution
Every provider returns a `TargetMatch` in virtual desktop physical pixels:
- `provider_name`
- `rect`
- `confidence`
- `text`
- `metadata`

The resolver is deterministic and never reorders providers based on heuristics.

## Coordinates And DPI
- The standard coordinate system is virtual desktop physical pixels.
- Win32 input conversion to absolute coordinates happens only in the input layer.
- Screen capture also operates in the same coordinate system to avoid per-provider translation bugs.
- Per-monitor DPI awareness is enabled at process startup with `SetProcessDpiAwarenessContext` where available.

## Provider Notes
### Browser DOM
- Connect to `http://127.0.0.1:9222` using Playwright CDP.
- Locate by CSS selector, text, or page title filter.
- Convert DOM bounding boxes to screen coordinates using browser window metrics.

### Windows UI Automation
- Use `pywinauto` (`backend="uia"`) to find windows and descendants by title, automation id, class name, name, and control type.
- Prefer UIA for controls that expose reliable bounding rectangles or value patterns.

### Windows OCR
- Capture full screen or a region.
- Use a provider abstraction across Windows OCR (`winsdk`), Tesseract (`pytesseract`), and EasyOCR.
- Return the first matching text region above the requested confidence from the configured backend order.

### Template Matching
- Use OpenCV `matchTemplate` on grayscale captures.
- Supports both full screen and region-scoped search.

## Desktop UI MVP
- `Snippets` tab stores text snippets under `assets/snippets`.
- `Templates` tab imports files or captures a cropped region from the desktop into `assets/templates`.
- `Macros` tab edits raw JSON/YAML, validates against schema, and manages per-macro hotkeys.
- `Run / Logs` tab executes macros in dry-run or execute mode and reads artifacts from `artifacts/runs`.
- `Settings` tab edits CDP, OCR backend order, capture backend, overlay, and hotkey service state.

## Artifacts
Each run creates `artifacts/runs/<run_id>/`:
- `events.jsonl`
- `macro_resolved.json`
- `screenshots/`
- `overlay/`

Artifacts are produced in both dry-run and execute mode. Failure screenshots are captured automatically.
Overlay metadata is always written. The live topmost `tkinter` overlay window is enabled with `AIAUTOMOUSE_LIVE_OVERLAY=1`.

## Plugin Structure
- Providers conform to a shared `LocatorProvider` interface.
- Runtime services are injected into the runner so they can be replaced in tests.
- Optional dependencies are imported lazily so the CLI can still run if OCR, CDP, or template matching is unavailable.

## Schema Assets
- Runtime models live in `src/aiautomouse/engine/models.py`.
- The generated JSON Schema is stored at `schemas/macro.schema.json`.
