# Lessons Learned

- When runtime verification is blocked only by missing Python packages, install them immediately and re-run the verification instead of stopping at a dependency note.
- Distinguish between a Python wrapper being installed and the underlying native tool being present. `pytesseract` importing successfully does not mean `tesseract.exe` is installed.
- For OCR/image stacks on Windows, verify imports after installation because binary ABI mismatches such as `numpy` vs `scikit-image` are common and need explicit repair.
- For Playwright-based features, verify both the Python package import and the browser runtime installation. `playwright` importing is not enough; `python -m playwright install chromium` may still be required before `doctor` can report the browser provider as usable.
- When claiming a PyInstaller build is acceptable, inspect the build log for noisy optional-import paths from large dependencies like `torch` and fix them with local hook filtering instead of treating the warnings as harmless by default.
