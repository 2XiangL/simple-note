# AGENTS.md

Compact context for OpenCode sessions working on Simple Note.

## Commands

Simple Note is a Tkinter desktop app managed with **uv** (see `uv.lock`).

- Run the app: `uv run python main.py`
- Run tests: `uv run pytest`
- Run a single test: `uv run pytest tests/test_util.py::test_merge_style_overwrites_and_sets`

`pyproject.toml` sets `tool.pytest.ini_options.pythonpath = ["."]`, so modules at the repo root (`app`, `editor`, `snote`, `util`, ...) are imported directly — there is no package directory.

There is **no lint, formatter, or typecheck** configured. Do not assume ruff/mypy/black; do not invent a lint step.

## Environment gotchas

- Requires **Python 3.14** (`.python-version`, `pyproject.toml`). Let `uv` resolve it.
- Runtime deps are **Pillow** and **pystray** (see `pyproject.toml`). `main.py` probes for Pillow at startup and warns if missing; `pystray` is imported lazily inside `tray.py` so a missing/broken tray never crashes startup.
- Tests instantiate real Tk widgets. The `tk_root` fixture (see `tests/conftest.py`) calls `pytest.skip(...)` when no display is available — on a headless session most of `tests/test_editor.py` silently skips. Always check the "skipped" count, not just pass/fail. `test_util`, `test_snote`, `test_settings`, and `test_tray` are headless-safe (no real Tk — `test_tray` drives a `_FakeRoot`); only `test_editor` needs a display.
- `image_resizer.py` uses the Windows-only `-transparentcolor` attribute and falls back to an opaque overlay on other platforms (caught `tk.TclError`). Don't "fix" that try/except.

## Architecture

Entry point is `main.py` → `app.NoteApp` (main window, menus, multi-document coordination). Data flow:

- `editor.py` — `RichTextEditor(tk.Text)`. Rich text via **one composite style tag per character** (`s1`, `s2`, ...). Applying a style delta merges it with the char's current style and may mint a new tag; a char never carries two style tags. Tests in `tests/test_editor.py` enforce this invariant — preserve it when editing style logic. **Every typed/inserted char carries a tag, including base-size text** (a tag whose style dict is `{}`); this is what lets the widget base font track `_current_style` (see below) without polluting untagged text. `to_document` filters base-style tags out of the serialized form (compact + backward compatible), and `from_document` re-applies a base tag to any untagged text on load — so the on-disk format still represents base text as "no tag" while the in-memory model always tags it.
  - **Typed text bypasses the Python `insert()` override.** Tk's default `<KeyPress>` class binding calls the Tcl-level C `insert` directly, so `RichTextEditor.insert` only catches *programmatic* inserts. To style typed chars *before redraw* (no font-size flash), `_on_key_press` records the cursor on `<KeyPress>`, the Text class binding inserts the bare char, then a **late** `<KeyPress>` handler `_stamp_typed_range` (registered via a per-instance bindtag appended after `"Text"` in `bindtags`) stamps `_current_style` onto the just-typed range within the same event. `_on_cursor_move` (on `<KeyRelease>`/`<ButtonRelease-1>`) only derives the continuation `_current_style` and notifies the toolbar. A no-selection toolbar change sets `_pending` so the style survives cursor moves until consumed by typing; after a **selection-based** format apply, `_current_style` is reset to the surrounding style with the applied attributes removed (so typing after a selection bold/italic/strike/color is not sticky) and `_pending` is set to protect it. Tests that call `ed.insert(...)` directly do NOT model typed input — simulate the real path with `ed._on_key_press(...)` → `ed.tk.call(ed._w, "insert", "insert", ch)` → `ed._stamp_typed_range()` (→ `ed._on_cursor_move()` to model KeyRelease).
  - **Widget base font tracks `_current_style`** via `_sync_widget_font` (called wherever `_current_style` changes). Tk sizes the insertion cursor on an *empty* line from the widget base font, not from any tag — so the widget font must match `_current_style` for the cursor (and IME preedit) to match the current size after Enter. This is only safe because all body text is tagged (above); changing the widget font reflows only empty lines, not tagged content. Reconfigure is guarded by `_widget_font` so it's a no-op when the size hasn't changed.
- `snote.py` — the `.snote` self-contained file format. A zip with `content.json` (document dict: `version`, `format`, `styles`, `ops`, `images`) plus `images/<id>.png` entries. `load_document` raises `ValueError` on bad zip / missing `content.json` / wrong `format`, but **tolerates missing image blobs** (returns without them; editor renders a placeholder).
- `util.py` — pure style helpers (`merge_style`, `style_to_font`, `style_to_tag_config`) and clipboard image grab. No Tk state; safe to unit-test directly.
- `toolbar.py`, `notes_panel.py`, `image_resizer.py` — UI components wired up by `NoteApp`.
- `imefont.py` — Windows-only IME composition-font sync. `RichTextEditor._sync_ime_font` calls `imefont.set_composition_font` whenever `_current_style` changes (cursor move / style apply / doc load / `<FocusIn>`) so the Chinese-IME preedit/candidate window matches the surrounding font instead of the widget base font. No-op on non-Windows. The visual result can't be unit-tested headlessly — it needs a real Windows IME session.
- `tray.py` — `TrayController`: pystray tray icon + global hotkey Ctrl+Alt+N (Windows-only, via Win32 `RegisterHotKey` pumped on its own thread). **Tkinter is not thread-safe**: the hotkey-listener thread and pystray menu callbacks must NEVER call Tk directly — they only `_marshal` (enqueue); the main thread drains the queue via `root.after` polling (`_poll`/`_drain`). Tray/hotkey failures are caught and never block app startup (a busy hotkey only prints a warning). Preserve this queue+poll pattern when editing tray logic.
- `settings.py` — pure-function read/write of app prefs (line-spacing level), no Tk dep, at `~/.simple-note/settings.json`. `load_settings`/`save_settings` are **fault-tolerant and never raise** (missing/corrupt/wrong-type/unknown-level all fall back to defaults, warning to stderr). Preset map `LINE_SPACING_PRESETS` (紧凑=0 / 标准=4 / 宽松=8 px) is applied via the `app.NoteApp` view menu → `editor.set_line_spacing(px)` and persisted.

Images are stored **losslessly**: the original `PIL.Image` source is kept in memory and re-encoded at original resolution on save; only the on-screen display is resized. Do not save the resized photo in place of the source.

## Conventions

- UI strings and code docstrings are written in **Simplified Chinese**. Match this when adding user-facing text or docstrings.
- `_apply_delta_range` / `insert` / `to_document` / `from_document` form the serialization boundary; `to_document()` then `from_document()` must round-trip equal (see `test_roundtrip_*`). Keep them in sync.
- `.opencode/` is OpenCode tooling, not part of the application.
