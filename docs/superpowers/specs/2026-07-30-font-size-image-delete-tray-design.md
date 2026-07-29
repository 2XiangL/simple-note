# 字号行为 / 图片删除 / 托盘热键 设计文档

- **日期**：2026-07-30
- **状态**：已通过设计评审，待编写实现计划
- **范围**：三项独立增强，统一在一个 spec 中（彼此不依赖，可拆分实现）

## 1. 目标与范围

1. **字号行为修正**：无选区切换字号后，后续输入用新字号；选区切换只改选区。工具栏字号框像 Word 一样随光标位置自动刷新。
2. **图片删除**：双击图片进入缩放浮层后，按 Del 删除该图片。
3. **托盘 + 全局热键**：`Ctrl+Alt+N` 全局热键隐藏/显示主窗口；托盘左键切换、右键菜单含显示/隐藏与退出；点窗口 X 最小化到托盘。

## 2. 字号行为 + 字号框自动刷新

### 2.1 根因

`editor.py` 的 `_on_cursor_move`（绑定 `ButtonRelease-1` / `KeyRelease`）无条件执行 `self._current_style = self._style_at(before)`，把光标位置的样式整体覆盖回来。用户在工具栏无选区设的字号，在点击回编辑区时被清掉，导致输入仍用旧字号。

### 2.2 方案：待输入样式（pending）

`editor.py` 改动：

- `__init__` 增加 `self._pending = False`。
- `apply_style_to_selection` 无选区分支：`self._current_style = util.merge_style(...)` 后置 `self._pending = True`。
- `_on_cursor_move`：仅当 `not self._pending` 时才从光标位置重新采纳 `_current_style`；无论是否采纳，都通过新回调 `self._on_cursor_style(style)` 通知工具栏当前生效样式。
- `insert`（非 `_loading` 且 `_current_style` 非空分支）：套用样式后清 `self._pending = False`。下一次 `KeyRelease` 会自然重新采纳刚输入字符的样式（即刚被消耗的 pending 值）。
- 新增回调机制：`set_on_cursor_style(callback)` / `self._on_cursor_style = None`。

`toolbar.py` 改动：

- `set_editor` 时注册 `editor.set_on_cursor_style(self._refresh_size)`。
- `_refresh_size(style)`：把 `size_var` 设为 `str(style.get("size", 12))`。当字号框自身拥有焦点时跳过刷新，避免和用户输入打架。

### 2.3 行为时序（pending 粘到下一次输入）

1. 无选区选 20 → `_pending=True`，`_current_style={size:20}`，字号框显示 20。
2. 点进 12pt 文本 → `_on_cursor_move` 见 pending，不覆盖；字号框仍显示 20。
3. 输入"H" → `insert` 套 20pt，清 pending；随后 `KeyRelease` 重新采纳"H"=20pt。
4. 点进 14pt 文本 → 无 pending → 采纳 14pt，字号框显示 14。

### 2.4 作用域

- 自动刷新**仅字号框**（B/I/S 按钮不回显当前位置状态）。
- pending 机制对经过无选区 `apply_style_to_selection` 路径的所有样式 delta 生效（含 B/I/S），顺带修复潜在同类问题；但 B/I/S 按钮不做回显。
- 选区路径（`_apply_delta_range`）完全不变；pending 状态也**不**因"应用到选区"而被清除（pending 只由 typing 消耗、或由再次无选区设样式替换）。

### 2.5 测试（`tests/test_editor.py` 扩展）

- pending 在模拟光标移动后存活（构造无选区 set → 手动 `_on_cursor_move()` → 断言 `_current_style` 不变）。
- pending 被 `insert` 消耗（set → insert 一个字符 → 断言 `_pending is False`）。
- 选区路径不受影响（已有用例覆盖，保留）。
- cursor-style 回调收到正确 size（用真实 editor + 一个捕获回调的 list 断言）。

## 3. 图片删除（缩放浮层中按 Del）

### 3.1 方案

`editor.py` 新增：

```python
def delete_image(self, img_id):
    idx = self._index_of_image(img_id)
    if idx is None:
        return
    self.delete(idx)                 # 删除该索引处的单个字符（图片占一个字符位）
    self._images.pop(img_id, None)
    self._mark_dirty()
```

`image_resizer.py` 改动：

- `__init__` 的 canvas 绑定区追加 `self.canvas.bind("<Delete>", lambda e: self._delete())` 与 `<Backspace>` 同绑定。
- 新增 `_delete(self)`：`self.editor.delete_image(self.img_id)` → `self.editor.end_resize()`（end_resize 会 destroy 浮层并解绑 editor 上的临时绑定）。

### 3.2 边界

- 删除后浮层必须关闭（否则下一帧 `_place()` 找不到 bbox）。由 `end_resize()` 保证。
- Enter 确认 / Esc 取消语义不变。
- 图片从 `_images` 移除后，`to_document()` 的 `dump` 已找不到该 image 段，序列化自然不再包含——无需额外清理 styles/images 字典。

### 3.3 测试（`tests/test_editor.py` 扩展）

`test_delete_image_removes_from_text_and_registry`：插入一张图 → `delete_image(img_id)` → 断言 `img_id not in editor._images` 且 `dump` 结果中无 image 段。浮层 Del 绑定属 GUI 事件，不直接测。

## 4. 托盘 + 全局热键

### 4.1 架构

新增 `tray.py` 模块，封装 `TrayController`。`NoteApp` 持有一个实例。隔离系统级依赖（pystray/keyboard），便于在不调起真实托盘的情况下单测状态机。

### 4.2 线程模型（关键）

- `keyboard` 回调跑在 keyboard 库线程；`pystray` 菜单回调跑在 pystray 线程。
- **Tkinter 非线程安全**：两条外部线程的回调一律 `self._root.after(0, fn)` 派发回主线程执行，绝不直接碰 Tk。

### 4.3 `TrayController` API

```python
class TrayController:
    def __init__(self, root, on_quit):  # on_quit = 真正退出应用
        self._root = root
        self._on_quit = on_quit
        self._hidden = False
        self._icon = None        # pystray.Icon，start() 后赋值
        self._hotkey_unreg = None

    def start(self):
        # keyboard.add_hotkey('ctrl+alt+n', self._on_hotkey)，保存返回的卸载句柄
        # 构造 pystray.Icon（菜单：显示/隐藏、分隔、退出），icon.run(detach=True) 在守护线程

    def stop(self):
        # 卸载热键；icon.stop()（join 守护线程）

    # 仅主线程调用：
    def toggle_visibility(self):  # hide ↔ show 状态机
    def hide(self):
        # 调 active editor.end_resize() 关掉可能打开的缩放浮层；root.withdraw()
    def show(self):
        # root.deiconify() + lift() + focus_force()
```

外部线程回调（`_on_hotkey`、菜单项）只做 `self._root.after(0, self.toggle_visibility)` 或 `self._root.after(0, self._on_quit)`。

### 4.4 `app.py` 接线

- `NoteApp.__init__` 末尾：`self.tray = TrayController(self.root, on_quit=self._real_quit); self.tray.start()`。
- `WM_DELETE_WINDOW` 协议从 `on_exit` 改为 `self.tray.hide`（点 X = 最小化到托盘）。
- 新增 `_real_quit`：先 `self.tray.stop()`，再执行原 `on_exit` 主体（脏文档询问 + `root.destroy`）。原 `on_exit` 重命名为 `_real_quit` 的内核，保留所有现有逻辑。

### 4.5 托盘图标

不引入二进制资源。用 Pillow 程序化生成：64×64 圆角蓝底（与 image_resizer 选框同色 `#1a73e8`）+ 白色 "N"。`ImageFont.load_default()` 即可，小图标辨识度足够。

### 4.6 依赖

`pyproject.toml` 的 `dependencies` 追加 `pystray>=5.0` 与 `keyboard>=0.13`。`uv.lock` 由 `uv` 同步。

### 4.7 main.py

不变。`root.mainloop()` 在窗口 `withdraw` 后继续运行，符合托盘驻留语义。

### 4.8 测试（新 `tests/test_tray.py`）

可测部分（纯逻辑，无需托盘/显示）：用一个 stub `root`（带 Tk 兼容的 `after(ms, fn)`，测试里同步执行 fn）构造 `TrayController`，断言状态机：

- 初始 `_hidden is False`。
- `hide()` 后 `_hidden is True`，且 `root.withdraw` 被调度。
- `toggle_visibility()` 切换状态。
- `show()` 后 `_hidden is False`，且 `root.deiconify` 被调度。

`start()` 不在测试里调用（避免起真实托盘/热键）。真实 pystray/keyboard 集成列入手动验收清单。

## 5. 改动面汇总

- **改**：`editor.py`（pending + `delete_image` + cursor 回调）、`toolbar.py`（字号框刷新）、`image_resizer.py`（Del 绑定 + `_delete`）、`app.py`（托盘接线 + X 行为 + `_real_quit`）、`pyproject.toml`（2 个依赖）。
- **新**：`tray.py`、`tests/test_tray.py`。
- **扩**：`tests/test_editor.py`。
- **不动**：`main.py`、`util.py`、`notes_panel.py`、`snote.py`。

## 6. 手动验收清单

- 字号：无选区设字号 → 点别处 → 输入 = 新字号；选区设字号 → 仅选区变。
- 字号框：光标在不同字号文本间移动，框内数字随之刷新；正在编辑框时不被覆盖。
- 图片：双击进入缩放浮层 → 按 Del 图片消失且浮层关闭；序列化后重开无残留。
- 托盘：`Ctrl+Alt+N` 全局切换；点 X 最小化到托盘；托盘左键切换、右键"显示/隐藏"+"退出"；退出时脏文档仍会询问。
