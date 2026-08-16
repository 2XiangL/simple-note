# AGENTS.md

Compact context for OpenCode sessions working on Simple Note.

## Commands

Simple Note is a Tkinter desktop app managed with **uv** (see `uv.lock`).

- Run the app: `uv run python main.py`
- Run tests: `uv run pytest`
- Run a single test: `uv run pytest tests/test_util.py::test_merge_style_overwrites_and_sets`
- Package a Windows exe: `pyinstaller SimpleNote.spec` → `dist/SimpleNote.exe` (windowed, no console). `pyinstaller` is **not** a declared dependency — install it separately. `build/` and `dist/` are gitignored build artifacts; never edit them.

`pyproject.toml` sets `tool.pytest.ini_options.pythonpath = ["."]`, so modules at the repo root (`app`, `editor`, `snote`, `util`, ...) are imported directly — there is no package directory.

There is **no lint, formatter, or typecheck** configured. Do not assume ruff/mypy/black; do not invent a lint step.

## Environment gotchas

- Requires **Python 3.14** (`.python-version`, `pyproject.toml`). Let `uv` resolve it.
- Runtime deps are **Pillow** and **pystray** (see `pyproject.toml`). `main.py` probes for Pillow at startup and warns then **exits** if missing; `pystray` is imported lazily inside `tray.py` so a missing/broken tray never crashes startup.
- Tests instantiate real Tk widgets. Any test taking the `tk_root` fixture (see `tests/conftest.py`) silently `pytest.skip(...)`s when no display is available — on a headless session whole files skip. Always check the "skipped" count, not just pass/fail. Fully headless-safe (no real Tk): `test_util`, `test_snote`, `test_settings`, `test_notify`, `test_reminder`, `test_tray`, `test_main`, `test_singleinstance` (`test_tray` drives a `_FakeRoot`; `test_reminder`/`test_notify` are pure logic with an injected clock; `test_main`/`test_singleinstance` monkeypatch Tk/Win32 entirely). `test_app` is mostly headless but has several `tk_root` tests (container wiring, search-dialog lifecycle); `test_imefont` has one `tk_root` test. `test_editor`, `test_notes_panel`, `test_reminder_dialog`, and `test_search_dialog` need a display.
- `image_resizer.py` uses the Windows-only `-transparentcolor` attribute and falls back to an opaque overlay on other platforms (caught `tk.TclError`). Don't "fix" that try/except.
- Even on the dev machine (with a display), `tk.Tk()` intermittently fails mid-suite with "Can't find a usable tk.tcl", so 1–2 random `tk_root` tests skip per run and the victim changes each run. A lone skip is not a real failure nor headlessness — rerun the affected test file to confirm.

## Architecture

Entry point is `main.py` → `app.NoteApp` (main window, menus, multi-document coordination). 每个文档的 editor 与纵向滚动条同装在一个每文档容器 `tk.Frame`（`NoteDocument.frame`）里，`switch_to`/`close_doc` 以 frame 为单位 pack/destroy。Data flow:

- `editor.py` — `RichTextEditor(tk.Text)`. Rich text via **one composite style tag per character** (`s1`, `s2`, ...). Applying a style delta merges it with the char's current style and may mint a new tag; a char never carries two style tags. Tests in `tests/test_editor.py` enforce this invariant — preserve it when editing style logic. **Every typed/inserted char carries a tag, including base-size text** (a tag whose style dict is `{}`); this is what lets the widget base font track `_current_style` (see below) without polluting untagged text. `to_document` filters base-style tags out of the serialized form (compact + backward compatible), and `from_document` re-applies a base tag to any untagged text on load — so the on-disk format still represents base text as "no tag" while the in-memory model always tags it.
  - **Typed text bypasses the Python `insert()` override.** Tk's default `<KeyPress>` class binding calls the Tcl-level C `insert` directly, so `RichTextEditor.insert` only catches *programmatic* inserts. To style typed chars *before redraw* (no font-size flash), `_on_key_press` records the cursor on `<KeyPress>`, the Text class binding inserts the bare char, then a **late** `<KeyPress>` handler `_stamp_typed_range` (registered via a per-instance bindtag appended after `"Text"` in `bindtags`) stamps `_current_style` onto the just-typed range within the same event. `_on_cursor_move` (on `<KeyRelease>`/`<ButtonRelease-1>`) only derives the continuation `_current_style` and notifies the toolbar. A no-selection toolbar change sets `_pending` so the style survives cursor moves until consumed by typing; after a **selection-based** format apply, `_current_style` is reset to the surrounding style with the applied attributes removed (so typing after a selection bold/italic/strike/color is not sticky) and `_pending` is set to protect it. Tests that call `ed.insert(...)` directly do NOT model typed input — simulate the real path with `ed._on_key_press(...)` → `ed.tk.call(ed._w, "insert", "insert", ch)` → `ed._stamp_typed_range()` (→ `ed._on_cursor_move()` to model KeyRelease). `<<Paste>>` goes through the same late handler: `_on_paste` grabs image clipboards (returns `"break"`) or else records `_type_start`（有选区取 `sel.first`）for `_stamp_typed_range` to tag — keep paste in mind when touching the stamp path.
  - **Widget base font tracks `_current_style`** via `_sync_widget_font` (called wherever `_current_style` changes). Tk sizes the insertion cursor on an *empty* line from the widget base font, not from any tag — so the widget font must match `_current_style` for the cursor (and IME preedit) to match the current size after Enter. This is only safe because all body text is tagged (above); changing the widget font reflows only empty lines, not tagged content. Reconfigure is guarded by `_widget_font` so it's a no-op when the size hasn't changed. 查找原语 `find_matches`/`search_next`/`search_prev`/`highlight_search`/`clear_search_highlight` 只用两个底纹 tag（`search_all`/`search_cur`，仅设 background），不触碰样式 tag；next/prev 分别从 `sel.last`/`sel.first` 起搜并环绕，避免原地重复命中。
- `app.open_workspace` — 「打开工作区」：`askdirectory` + `Path.rglob("*.snote")` 递归批量载入，复用 `_find_open_doc`（判重跳过）/`_load_path`（load + _make_doc）两个助手（`open_doc` 同源）；坏文件收集进失败汇总弹框，不阻断其余加载。全程主线程同步，勿引入后台线程。
- `snote.py` — the `.snote` self-contained file format. A zip with `content.json` (document dict: `version`, `format`, `styles`, `ops`, `images`) plus `images/<id>.png` entries. `load_document` raises `ValueError` on bad zip / missing `content.json` / wrong `format`, but **tolerates missing image blobs** (returns without them; editor renders a placeholder).
- `util.py` — pure style helpers (`merge_style`, `style_to_font`, `style_to_tag_config`) and clipboard image grab. No Tk state; safe to unit-test directly.
- `lang.py` — Tk-free 界面语言模块：`detect_system_language()`（Windows 用 `GetUserDefaultUILanguage` LCID 主语言 ID==0x04 判中文，非 Windows/失败回退 locale，英文兜底）+ `set_language`/`get_language`/`t(key)`。**中文原文即 key**：zh 模式原样返回，en 查 `EN_TRANSLATIONS`，缺 key 回退中文。`main.py` 启动最开头锁定语言；`tests/test_lang.py::test_en_dict_covers_all_t_callsites` 扫描全仓库 `t("...")` 调用点保证无漏译——新 UI 文案必须 `t("中文")` 调用并在 `EN_TRANSLATIONS` 补 en 译文。`settings.json` 持久化键（紧凑/标准/宽松）保持中文内部键，仅显示层翻译。
- `toolbar.py`, `notes_panel.py`, `image_resizer.py` — UI components wired up by `NoteApp`.
- `imefont.py` — Windows-only IME composition-font sync. `RichTextEditor._sync_ime_font` calls `imefont.set_composition_font` whenever `_current_style` changes (cursor move / style apply / doc load / `<FocusIn>`) so the Chinese-IME preedit/candidate window matches the surrounding font instead of the widget base font. No-op on non-Windows. The visual result can't be unit-tested headlessly — it needs a real Windows IME session.
- `tray.py` — `TrayController`: pystray tray icon + global hotkey Ctrl+Alt+N (Windows-only, via Win32 `RegisterHotKey` pumped on its own thread). **Tkinter is not thread-safe**: the hotkey-listener thread and pystray menu callbacks must NEVER call Tk directly — they only `_marshal` (enqueue); the main thread drains the queue via `root.after` polling (`_poll`/`_drain`). Tray/hotkey failures are caught and never block app startup (a busy hotkey only prints a warning). Preserve this queue+poll pattern when editing tray logic.
- `singleinstance.py` — 单实例守卫（仅 Windows，fail-open）：`acquire()` 占用命名互斥体（已占用返回 None = 第二实例）；`activate_existing()` 广播 `SimpleNote.Activate` 注册消息；`SingleInstanceListener` 是隐藏**顶层**窗口（message-only 窗口收不到广播）+ GetMessageW 泵的守护线程，`on_activate` 可省略（默认分派到 `set_activation_handler` 注册的模块级回调）。`main.py` 在**任何 Tk 创建之前**分流第二实例（广播后静默退出），且 acquire 成功后**立即启动监听线程**（消除启动竞态）；`NoteApp.__init__` 用 `singleinstance.set_activation_handler(lambda: self.tray.enqueue(self.tray.show))` 接线，激活广播经 tray 队列封送恢复并置前窗口；`mainloop()` 返回后 `stop_single_instance_listener()`。监听线程绝不碰 Tk、只入队（同 tray 热键规则）。已知残余：启动窗口内（监听已起、回调未注册）的激活广播为 no-op。测试用带 pid 的唯一互斥体/消息名，避免与开发机上运行中的真实实例互扰。
- `settings.py` — pure-function read/write of app prefs (line-spacing level), no Tk dep, at `~/.simple-note/settings.json`. `load_settings`/`save_settings` are **fault-tolerant and never raise** (missing/corrupt/wrong-type/unknown-level all fall back to defaults, warning to stderr). Preset map `LINE_SPACING_PRESETS` (紧凑=0 / 标准=4 / 宽松=8 px) is applied via the `app.NoteApp` view menu → `editor.set_line_spacing(px)` and persisted.
- `reminder.py` — Tk-free 提醒调度引擎（番茄钟状态机 + 一次性/每日提醒），时钟经 `now_fn` 注入故可无显示器单测。由 `app.NoteApp` 用 `root.after(1000, _tick)` 每秒在主线程驱动；`tick(now)` 返回到期事件。番茄钟追赶（休眠唤醒）会静默推进、每次 tick 只发一条通知。每日提醒用 `_last_tick < occ <= now` 检测跨过；`arm(now)` 在启动时设定基准，使启动前已过的每日提醒不补发。
- `notify.py` — 通知胶水：`resolve_sound(cfg)` 纯函数（custom .wav 存在则自定义，否则系统蜂鸣）+ `notify(root, title, msg, sound_cfg)`（唤回窗口→winsound 播音→模态 `messagebox`）。自定义音频仅 Windows/.wav（`winsound.PlaySound`），任何失败回退 `root.bell()`，绝不阻断弹框。
- `reminder_dialog.py` — 非模态管理对话框 `ReminderDialog(tk.Toplevel)`：番茄钟启停/参数、提醒列表增删、提示音配置（`sound_config()` 取回）。经 `on_change` 回调触发 app 持久化。
- `search_dialog.py` — 非模态查找对话框 `SearchDialog(tk.Toplevel)`：构造参数 `editor_provider` 是返回活动 editor 的回调（由 `app.NoteApp._open_search_dialog` 传入），天然跟随文档切换/关闭；文本操作全部委托 editor 查找方法，对话框本身不碰 tk.Text。

Images are stored **losslessly**: the original `PIL.Image` source is kept in memory and re-encoded at original resolution on save; only the on-screen display is resized. Do not save the resized photo in place of the source.

## Conventions

- UI 文案一律经 `lang.t("中文原文")` 取用，en 译文只加进 `lang.EN_TRANSLATIONS`（见 `test_en_dict_covers_all_t_callsites`）；docstring 与 stderr 开发者警告仍写简体中文。行距单选 `label=t(name)` 但 `value` 保持内部中文键。
- `_apply_delta_range` / `insert` / `to_document` / `from_document` form the serialization boundary; `to_document()` then `from_document()` must round-trip equal (see `test_roundtrip_*`). Keep them in sync.
- `.opencode/` is OpenCode tooling, not part of the application.
- `docs/superpowers/` holds dated design specs/plans from past feature work — background context only; code and tests are the source of truth.
- 提醒数据持久化在 `settings.json` 的 `sound`/`pomodoro`/`reminders` 键；`settings.py` 只做容错读写（保留 dict 形值），深度清洗在 `reminder.ReminderScheduler.load_dict`。
- 提醒/番茄钟全程跑在 Tk 主线程（`root.after`），切勿引入后台线程；`app._tick` 必须异常安全且无论如何都重新 `after`，否则提醒会静默停摆。
