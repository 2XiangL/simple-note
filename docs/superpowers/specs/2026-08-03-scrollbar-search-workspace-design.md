# 设计：纵向滚动条 + 查找（Ctrl+F）+ 打开工作区

日期：2026-08-03
状态：已确认，待实现

为 Simple Note 增加三项功能：

1. 编辑框纵向滚动条
2. 查找功能（Ctrl+F，仅当前笔记，浮动对话框）
3. 打开工作区（选择目录，递归加载其中所有 `.snote`）

## 非目标（YAGNI）

- 不做查找替换（仅查找）
- 不做跨文档搜索（仅当前活动笔记）
- 不记忆工作区目录、不在启动时自动重载
- 不做后台线程/进度条加载（Tkinter 非线程安全，同步批量即可）
- 打开工作区不关闭已打开文档，只追加

## 功能 1：编辑框纵向滚动条

采用**每文档容器 frame** 方案：editor 与其专属滚动条同属一个容器，随文档生命周期整体 pack/forget/destroy。

### 结构

`NoteApp._make_doc`（app.py:198）改为：

- 创建容器 `frame = tk.Frame(self.editor_host)`
- `editor = RichTextEditor(frame)`（原来直接以 `editor_host` 为父）
- `sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=editor.yview)`
- `editor.configure(yscrollcommand=sb.set)`
- 布局：`editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)`，`sb.pack(side=tk.RIGHT, fill=tk.Y)`（写法沿用 notes_panel.py:18-20）

### 联动改动

- `NoteDocument`（app.py:23）增加 `frame` 字段
- `switch_to`（app.py:296）：pack/forget 的对象由 `doc.editor` 改为 `doc.frame`
- `close_doc`（app.py:284）：`doc.editor.end_resize()` 后改为 `doc.frame.destroy()`，一次销毁 editor + 滚动条
- `_make_doc` 载入失败路径（app.py:206-208）：先 `editor.destroy()` 再 `frame.destroy()`，保住现有孤儿控件守卫及其测试（`test_make_doc_destroys_editor_when_from_document_fails` 断言 editor 的 destroy 被调用）
- app.py 补 `from tkinter import ttk`

### 测试

`tests/test_app.py` 新增一个 `tk_root` 用例：`_make_doc` 产出的 editor 与 scrollbar 互绑（editor 的 `yscrollcommand` 与 scrollbar 的 `command` 均已设置且指向对方），且二者同属一个 frame。

## 功能 2：查找（Ctrl+F）

### 新模块 `search_dialog.py`

`SearchDialog(tk.Toplevel)`，非模态，沿用 `ReminderDialog` 的单例复用模式（app 持引用；重开时若 `winfo_exists()` 则 `lift()` + 聚焦输入框，否则新建——同 `_open_reminder_dialog`，app.py:179-185）。

界面（简体中文）：

- 搜索输入框
- 「上一个」「下一个」按钮
- 「区分大小写」复选框
- 状态标签：`3/12` 形式的匹配位置，或 `无匹配`

行为：

- `Enter` = 下一个，`Shift+Enter` = 上一个，`Esc` = 关闭
- 输入框内容变化时即时重算高亮与计数
- 空 pattern：清除高亮、状态复位，不报错
- 构造参数 `editor_provider`：app 传入一个返回当前活动 editor 的回调（`lambda: self.active.editor`）。对话框每次操作时通过它取 editor，天然跟上文档切换/关闭，无需 app 手动同步引用

### `RichTextEditor` 新增方法

文本操作留在 editor 内（现有职责划分）：

- 参数约定：`case=True` 表示区分大小写（对应 Tk `search` 的 `nocase=not case`）
- `find_matches(pattern, case) -> list[(start, end)]`：用 `tk.Text.search` 从 `1.0` 循环至 `tk.END` 收集全部匹配
- `search_next(pattern, case)` / `search_prev(pattern, case)`：next 从当前选区末尾 `sel.last`（无选区则 `insert`）起向后搜，prev 从 `sel.first`（无选区则 `insert`）起向前搜——避免对当前命中原地重复命中；环绕到文档尾/头继续；命中后移动光标、`tag_add("sel", start, end)`、`see(start)`；返回 `(当前序号, 总数)`，无匹配返回 `None`
- `clear_search_highlight()`：移除查找高亮 tag
- 高亮 tag：`search_all`（浅色底）覆盖全部匹配，`search_cur`（深色底）覆盖当前匹配；二者只设 `background`（不与样式 tag 的 font/foreground/overstrike 冲突），创建后 `tag_raise` 到最上层
- `find_matches` / `search_next` / `search_prev` 负责刷新上述高亮

### app.py 布线

- 新增「编辑」菜单，置于「文件」与「查看」之间，含「查找...」命令，accelerator `Ctrl+F`
- `root.bind("<Control-f>", ...)` 打开查找对话框
- `_open_search_dialog()`：单例复用逻辑（同上）

### 测试

- `tests/test_editor.py`（`tk_root`）：`find_matches` 计数、区分大小写开关、`search_next`/`search_prev` 环绕、`clear_search_highlight` 清除
- 新文件 `tests/test_search_dialog.py`（`tk_root`，需显示器）：对话框创建、`Enter` 推进到下一匹配、状态标签计数正确

## 功能 3：打开工作区

### 菜单/快捷键

文件菜单「打开」之后加「打开工作区...」命令，绑定 `<Control-Shift-O>`。

### app.py 改动

从 `open_doc`（app.py:224-242）抽出两个助手，两条打开路径共用：

- `_find_open_doc(path) -> doc | None`：normcase/realpath 判重（跳过 `doc.path is None` 的未保存文档），命中返回已打开的 doc
- `_load_path(path) -> doc`：`snote.load_document` + `_make_doc`，失败抛异常（由调用方弹框/收集）。`open_doc` 原来「加载失败」与「解析失败」两段弹框随之合并为一条「打开失败」弹框（现有测试不断言消息文案，行为等价）

`open_doc` 改为调用这两个助手，外部行为不变（现有 `test_open_doc_*` 应全绿）。

`open_workspace()` 流程：

1. `filedialog.askdirectory(title="打开工作区")`；取消则返回
2. `files = sorted(Path(d).rglob("*.snote"), key=lambda p: os.path.normcase(str(p)))` — 递归所有子目录，大小写不敏感的稳定排序
3. 逐文件处理，不中断：
   - `_find_open_doc` 命中 → 计入「跳过（重复）」
   - 否则 `_load_path` 成功 → 先 `doc.dirty = False` 再 `add_doc(doc)`（顺序同 open_doc，避免列表标题闪现 `*` 前缀），计入「已加载」
   - 异常 → 计入「失败」（文件名 + 原因）
4. 结果反馈：
   - 目录下无 `.snote` → `messagebox.showinfo` 提示
   - 有失败 → `messagebox.showwarning`：「已加载 X 个，跳过重复 Y 个，失败 Z 个」+ 失败文件清单（最多列 10 条，超出以「…等 N 个」收尾）
   - 全部成功且至少加载一个 → 静默（笔记已出现在左侧面板）

已打开文档不关闭；最终活动文档为最后一个成功载入的（`add_doc` 既有行为）。

### 测试

`tests/test_app.py` 新增（沿用 `NoteApp.__new__` + monkeypatch 模式，无显示器可跑）：

- 递归发现嵌套子目录中的 `.snote`（用真实 `snote.save_document` 在 `tmp_path` 造文件树）
- 已打开路径被跳过、不重复加载
- 单个坏文件不阻断其余加载，且进入失败清单

## 文档

实现完成后同步更新 `AGENTS.md`：新模块 `search_dialog.py`、`RichTextEditor` 查找方法、每文档 frame 容器、工作区入口与助手函数。

## 约定提醒

- 新增 UI 字符串与 docstring 一律简体中文（仓库约定）
- 无 lint/typecheck；验证手段为 `uv run pytest`，注意 headless 下 `tk_root` 用例静默跳过，核对 skipped 数
