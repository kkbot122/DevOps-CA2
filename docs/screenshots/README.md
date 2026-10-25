# Screenshot capture guidance

Use `NN-kebab-name.png` exactly as listed in [MANIFEST.md](MANIFEST.md). Capture full windows at 1280 px wide or larger with readable UI text. Hide the browser bookmarks bar and personal information; crop or mask credentials, tokens, email addresses, and unrelated notifications. Include the terminal command line in terminal evidence when it helps establish how the result was produced.

Do not fabricate, edit together, or relabel screenshots. If a UI is unavailable, leave the file missing and report why. `make screenshots-check` reports missing, small, and duplicate images; `make screenshots-check STRICT=1` fails when a MUST screenshot is missing.

## Current capture provenance

See [CURRENT-STATUS.md](../evidence/CURRENT-STATUS.md). Captures 17/18 and 21–24 are browser evidence reports of actual captured JSON/stdout; full originals are included. They are labeled as reports rather than terminal screenshots. Native terminal screenshots remain manual. A width of 1280 px is recommended; the automated minimum is 1000 px. Strict checks reject missing, corrupt, small or duplicated MUST evidence.
