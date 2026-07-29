# Simple Note —— 轻量化本地便签工具 设计文档

- **日期**：2026-07-30
- **状态**：已通过设计评审，待编写实现计划
- **核心原则**：尽最大可能轻量化

## 1. 目标与范围

一个纯本地、单文件的轻量便签工具，具备：

1. 富文本编辑：颜色、字号、加粗、斜体、删除线（仿 Word，先选中再应用，实时生效）。
2. 剪贴板图片粘贴：`Ctrl+V` 内联插入文本流；双击图片后拖动 8 个手柄缩放（仿 Word）。
3. 多文档：左侧笔记栏列出已打开的多个笔记，可点击切换，右键菜单含保存/另存为/关闭。
4. 自包含文件：保存为单个 `.snote` 文件（含文本 + 图片 + 样式，类似 docx 的自包含思路）。

**明确不做（YAGNI）**：浮动/绝对定位图片、真正的 .docx 互通、自动保存、工作区会话恢复、网络/同步、GUI 自动化测试框架。

## 2. 总体方案

- **GUI 框架**：Tkinter（Python 标准库），GUI 零三方依赖。
- **依赖**：仅 `Pillow`（剪贴板取图 + 平滑重采样）。在 `pyproject.toml` 中声明。
- **图片定位模型**：内联式（随文字流），在光标处插入，不做浮动定位。
- **多文档模型**：每个笔记 = 一个独立 `.snote` 文件；左侧笔记栏列出当前打开的文件；新建打开空白笔记，打开加载文件入列表，关闭移出列表。

> 选型依据：备选 PyQt6（依赖巨大，违背轻量）与 pywebview（依赖 WebView 运行时、打包复杂）。Tkinter 唯一满足"尽最大可能轻量化"。代价是 8 点缩放浮层需自实现，工作量可控。

## 3. 模块结构

每个文件单一职责，便于隔离理解与测试：

```
simple-note/
├── main.py            # 入口：创建 NoteApp 并 mainloop
├── app.py             # NoteApp：主窗口、菜单栏、菜单动作(新建/打开/保存/另存/退出/关于)、多文档协调
├── toolbar.py         # FormatToolbar：颜色/字号/加粗/斜体/删除线 按钮与触发
├── notes_panel.py     # NotesPanel：左侧打开笔记列表、切换、右键菜单(保存/另存/关闭)
├── editor.py          # RichTextEditor(tk.Text)：富文本样式模型 + 序列化/反序列化 + 剪贴板粘贴入口
├── image_resizer.py   # ImageResizer：图片双击后的 8 点缩放浮层
├── snote.py           # save_snote()/load_snote()：.snote(zip+JSON) 读写
└── util.py            # get_clipboard_image() 等 Pillow 辅助 + 样式纯函数
```

> `NoteDocument`（持有编辑器实例 + 文件路径 + dirty 标记 + images 字典的数据模型类）定义在 `app.py` 中，与多文档协调逻辑同处，不单独开文件。

## 4. 富文本样式模型：复合标签 (composite tags)

### 4.1 背景与问题

Tkinter 的一个已知坑：不同 tag 的 `font` 属性**不会合并**，高优先级 tag 会整个覆盖字体。因此「加粗 + 20 号字」若拆成两个独立 tag 会互相冲突，无法同时生效。

### 4.2 方案

每种**唯一样式组合**对应一个复合标签，标签内携带完整 font 描述：

- 复合标签以内部计数 id 命名（如 `s1`、`s2`）。
- 每个 `sN` 通过 `tag_configure` 设置完整字体：`font=(family, size, "bold italic")` + `overstrike=`（删除线）+ `foreground=`（颜色）。
- 支持的样式属性：`bold`、`italic`、`strike`、`size`、`fg`（颜色，`#RRGGBB`）。
- 字体 family 为**应用级全局默认**（取 Tkinter 默认字体族），不随标签序列化；因此 `.snote` 的 `styles` 中不含 family 字段，重开后按全局默认渲染。

### 4.3 不变量

每个字符恰好归属**一个**复合样式标签。由此：

- 读某处当前样式 = `tag_names(index)` 取该复合标签 → 查样式映射。
- 应用「选中 → 改字号/加粗等」：遍历选区每字符，读当前样式 → 合并 delta → 取/建复合标签 → 移除选区旧标签 → 应用新标签。
- 新输入文本：继承光标前一个字符的复合标签（仿 Word 行为）。

### 4.4 纯函数化

「读样式 / 合并样式 delta / 生成或解析复合标签」抽成 `util.py` 中的纯函数，便于单测。

## 5. `.snote` 文件格式（zip + JSON）

### 5.1 包结构

zip 压缩包内：

```
content.json
images/<img_id>.png      # 每张图存为单独文件（避免 base64 膨胀，体积可读）
```

### 5.2 content.json 结构

```json
{
  "version": 1,
  "format": "snote",
  "styles": {
    "s1": {"bold": true, "size": 20},
    "s2": {"fg": "#ff0000", "italic": true}
  },
  "ops": [
    {"k": "tagon",  "name": "s1"},
    {"k": "text",   "text": "Hello"},
    {"k": "tagoff", "name": "s1"},
    {"k": "text",   "text": "\n"},
    {"k": "image",  "id": "img1"}
  ],
  "images": {
    "img1": {"file": "images/img1.png", "width": 300, "height": 200}
  }
}
```

- `ops` 直接由 `tk.Text.dump()` 生成（天然产出 `tagon/tagoff/text/image` 流），加载时按序回放。
- `styles` 为运行时复合标签名 → 样式字典的映射。
- `images` 为图片 id → 显示尺寸 + zip 内相对路径。
- 序列化/反序列化为纯逻辑（输入 dict/Text dump、输出 dict），便于单测与往返(round-trip)测试。

### 5.3 版本与兼容

- `version` 字段用于后续兼容；当前固定为 `1`。
- 加载时校验 `format == "snote"`，否则视为非本格式文件并报错。

## 6. 主窗口布局

```
┌─────────────────────────────────────────────────┐
│ 文件(新建 打开 保存 另存为 ─ 退出)    关于(关于) │  ← 菜单栏 (tk.Menu)
├─────────────────────────────────────────────────┤
│ [A 颜色] [字号: 12 ▾] [B] [I] [S]               │  ← 工具栏 (FormatToolbar, ttk)
├──────────┬──────────────────────────────────────┤
│ 笔记栏   │                                      │
│ • 笔记1  │                                      │
│ • 笔记2* │     文本编辑框                        │  ← PanedWindow(horizontal)
│   (右键: │     (RichTextEditor)                  │     左:NotesPanel(Listbox)
│    保存/ │                                      │     中:当前笔记的编辑器
│    另存/ │                                      │
│    关闭) │                                      │
└──────────┴──────────────────────────────────────┘
```

### 6.1 多文档协调

- 每个打开的笔记 = 一个 `NoteDocument`（持有自己的 `RichTextEditor` 实例 + 文件路径 + dirty 标记）。
- 切换：点左侧条目 → `pack_forget()` 当前编辑器 → 显示选中笔记的编辑器（各笔记状态独立保留）。标题 `*` 前缀表示未保存。
- 菜单动作：作用于当前激活的笔记。

## 7. 工具栏交互（仿 Word：先选中文本再点按钮）

| 控件 | 类型 | 行为 |
|------|------|------|
| 颜色 | 按钮 → `colorchooser` | 选中后给选区设 `fg`；无选中则设后续输入色 |
| 字号 | `ttk.Combobox`（8–72，可输入） | 选中后实时调整选区字号 |
| 加粗/斜体/删除线 | `ttk.Button` 切换 | 对选区切换该属性 |

所有操作统一走「读当前样式 → 合并 delta → 复合标签」这套纯函数。

## 8. 图片：粘贴与内联插入

1. `Ctrl+V` → `util.get_clipboard_image()`（PIL `ImageGrab.grabclipboard()`）。
2. 剪贴板无图则忽略；有图则：按编辑区可视宽度等比缩放（避免超大图撑爆界面）→ Pillow 缩放 → 生成 `PhotoImage` → `editor.image_create(cursor_index)` 内联插入。
3. 每张图分配 `img_id`；源 `PIL.Image` 与当前显示尺寸存入 `NoteDocument.images`，供缩放重采样与序列化复用。

## 9. 图片 8 点缩放（核心交互，仿 Word）

### 9.1 触发

双击图片进入缩放模式。

### 9.2 浮层（ImageResizer）

- 用 `Canvas` 通过 `.place()` 覆盖在编辑区上。
- 由 `text.bbox(image_index)` 得到图片屏幕矩形 → 画选框 + 8 个手柄（4 角 + 4 边中点）。
- 浮层存活期间监听编辑区 `<Configure>` 与滚动事件，实时重定位。

### 9.3 拖动

- **角手柄**：锁定纵横比等比缩放（Word 默认行为）。
- **边手柄**：单方向缩放（不锁比）。
- 拖动时用 Pillow 对**源图**重采样到新尺寸 → `text.image_configure(idx, image=new)` 实时刷新显示。

### 9.4 结束

- `Enter` 或点空白处：确认新尺寸，移除浮层，尺寸写回 `NoteDocument.images[img_id]`。
- `Esc`：取消本次缩放，恢复进入时尺寸，移除浮层。

### 9.5 设计要点

缩放只改「显示尺寸」，源图始终保留，保证反复缩放不失真，且保存/重新打开后尺寸一致。

## 10. 错误处理与边界情况

| 场景 | 处理 |
|------|------|
| 打开：文件不存在/损坏/非 .snote | `messagebox.showerror`，不加入笔记栏 |
| 打开：zip 缺图片/字段 | 缺图用占位符图标 + 警告日志；缺字段跳过 |
| 保存：路径无写权限 | `messagebox.showerror`，保持 dirty |
| 关闭/退出：存在 dirty 笔记 | 弹窗询问「保存/不保存/取消」逐个处理 |
| 剪贴板无图 | 静默忽略（不报错） |
| 粘贴图过大 | 按编辑区可视宽度等比缩放（设上限） |
| Pillow 未安装 | 启动时检测，`messagebox` 提示「图片功能需 Pillow」 |
| 切走笔记时处于缩放模式 | 切换前自动取消浮层 |
| 序列化：空笔记 | 产出合法空 ops，可正常往返 |

### 10.1 dirty 追踪

编辑器修改回调置 `dirty=True`，标题前缀 `*`；保存后清零。退出时遍历所有 dirty 文档逐一提示。

## 11. 测试策略

GUI 事件难单测，故把可测逻辑抽离成纯函数 / 纯 IO，分层测试。

### 11.1 单元测试（`tests/`，pytest）

- `util.py` 样式纯函数：合并样式 delta、生成复合标签名、解析标签名 → 样式。
- `snote.py` 序列化：`dict → save → load → dict` 往返一致（含图、含复合样式）。
- `snote.py` 边界：空文档、损坏 zip、缺图占位。

### 11.2 手工验收清单（作为交付验收依据）

1. 新建 → 输入 → 加粗/斜体/删除线/颜色/字号 实时生效。
2. 选中已有文本改样式正确合并。
3. 截图 → `Ctrl+V` 内联插入；双击 8 点缩放（角锁比 / 边自由）；`Esc` 取消、`Enter` 确认。
4. 保存为 `.snote` → 关闭 → 重新打开，文本/样式/图片/尺寸完全还原。
5. 多笔记切换、右键保存/另存/关闭、退出时 dirty 提示。

> 不引入 GUI 自动化框架（如 pytest-qt），保持轻量；以纯逻辑单测 + 手工验收清单覆盖。

## 12. 依赖与运行

- Python ≥ 3.14（沿用项目 `.python-version`）。
- 依赖：`Pillow`（在 `pyproject.toml` 的 `dependencies` 声明）。
- 运行：`uv run python main.py`（或 `uv run main.py`）。
