# 全局行间距 设计文档

- **日期**：2026-07-30
- **状态**：已通过设计评审，待编写实现计划
- **范围**：新增一项小功能——可调整全局行间距，应用级偏好，跨会话保留

## 1. 目标与范围

1. **全局行间距**：提供一个视图级设置，调整编辑器所有行的行间距，对所有已打开文档即时生效。
2. **应用级偏好**：行间距是应用偏好（所有文档共享、跨会话保留），不属于任何单篇笔记。新增应用偏好持久化机制（`settings.py`）。
3. **预设档位**：以菜单单选（紧凑 / 标准 / 宽松）暴露，不提供连续数值输入。
4. **序列化零影响**：行间距不进入 `.snote` 文档格式，`to_document()` / `from_document()` 与现有 round-trip 不变式完全不动。

非目标（YAGNI）：连续数值/滑块、每文档独立行间距、行间距随文档保存、主题或其他偏好设置（但 `settings.py` 结构应便于将来扩展）。

## 2. 方案选择

采用**方案 A：新增 `settings.py` 纯模块 + 编辑器 widget 级 spacing**。

行间距在 Tk `tk.Text` 中天然是 widget 级布局设置（`spacing1` / `spacing2` / `spacing3`）。本应用的复合样式标签（每字符一个 `sN` 标签）从不携带 spacing，因此 widget 级配置必然全局生效，无标签优先级冲突。应用级偏好值得一个独立、无 Tk 依赖、可直接单测的 `settings.py`。

已否决：
- 方案 B（设置 IO 内联进 `app.py`）：把文件 IO 混进 UI 类，难单测，将来加偏好会膨胀。
- 方案 C（存进 `.snote` 文档）：与应用级偏好目标冲突。

## 3. 架构与数据流

```
settings.py (新增，纯函数，无 Tk 依赖)
  - 常量：DEFAULT_LINE_SPACING / 预设映射 / PRESET_ORDER
  - px_for_level(name) -> int
  - default_settings() -> dict
  - load_settings(path=None) -> dict
  - save_settings(settings, path=None)
  - 默认路径: Path.home() / ".simple-note" / "settings.json"

editor.py
  + set_line_spacing(px)  -> self.configure(spacing1=px, spacing2=px, spacing3=0)

app.py (NoteApp)
  - 启动加载 settings 一次；缓存当前档位
  - 新增"查看"菜单，radiobutton 单选三档
  - _make_doc() 建编辑器后即套用当前行间距
  - 切换档位 -> 套用到所有已开文档 + 写盘 + 更新菜单勾选
```

关键不变量：行间距是**视图设置**，不参与文档序列化。`from_document()` 重载文档时行间距保持当前值不变（视图设置不应被文档内容覆盖）。

## 4. 预设档位

每档映射到一个整数像素值，套为 `spacing1 = spacing2 = 值, spacing3 = 0`（每条可视行上方加 N px；段落首行与折行续行一致，段落之间也一致）：

| 档位 | 像素 | 说明 |
|------|------|------|
| 紧凑 | 0 | 无额外间距 |
| 标准 | 4 | 轻微透气，**默认档位** |
| 宽松 | 8 | 明显宽松 |

存储格式（UTF-8 JSON，`Path.home() / ".simple-note" / "settings.json"`）：

```json
{"version": 1, "line_spacing": "标准"}
```

## 5. 模块设计

### 5.1 `settings.py`（纯，无 Tk）

```python
DEFAULT_LINE_SPACING = "标准"
SETTINGS_VERSION = 1

# 档位 -> 像素；ordered 映射，PRESET_ORDER 决定菜单顺序
LINE_SPACING_PRESETS = {"紧凑": 0, "标准": 4, "宽松": 8}
PRESET_ORDER = ["紧凑", "标准", "宽松"]

def default_settings():
    return {"version": SETTINGS_VERSION, "line_spacing": DEFAULT_LINE_SPACING}

def px_for_level(name):
    # 未知值回退到默认档
    return LINE_SPACING_PRESETS.get(name, LINE_SPACING_PRESETS[DEFAULT_LINE_SPACING])

def settings_path():
    return Path.home() / ".simple-note" / "settings.json"

def load_settings(path=None): ...      # 缺失/损坏/类型错 -> default_settings()
def save_settings(settings, path=None): ...  # OSError -> 警告，不抛
```

`path` 参数供测试用 `tmp_path` 注入。`load_settings` 返回的 dict 总是与默认值合并完整（即总是含 `version` 与合法 `line_spacing`）。

### 5.2 `editor.py` 改动

新增一个方法，纯 widget 级配置：

```python
def set_line_spacing(self, px):
    """设置全局行间距（widget 级 spacing1/2/3）。"""
    self.configure(spacing1=px, spacing2=px, spacing3=0)
```

不新增实例状态；不进 `to_document()` / `from_document()`。

### 5.3 `app.py` 改动

`__init__` 最开头（**在 `self._build_menu()` 之前**，因为菜单引用 `_ls_var`；也在创建任何编辑器之前）：

```python
self.settings = settings.load_settings()
self._line_spacing = self.settings.get("line_spacing", settings.DEFAULT_LINE_SPACING)
self._ls_var = tk.StringVar(value=self._line_spacing)
```

随后原有 `self._build_menu()` 即可在构建"查看"菜单时绑定 `self._ls_var`。

`_build_menu` 新增"查看"菜单（最终菜单栏：`文件` / `查看` / `关于`）：

```python
view_menu = tk.Menu(menubar, tearoff=0)
for name in settings.PRESET_ORDER:
    view_menu.add_radiobutton(label=name, value=name,
                              variable=self._ls_var, command=self._on_line_spacing)
menubar.add_cascade(label="查看", menu=view_menu)
```

回调与建文档套用：

```python
def _on_line_spacing(self):
    level = self._ls_var.get()
    self._line_spacing = level
    px = settings.px_for_level(level)
    for doc in self.docs:
        doc.editor.set_line_spacing(px)
    self.settings["line_spacing"] = level
    settings.save_settings(self.settings)

def _make_doc(self, ...):
    editor = RichTextEditor(self.editor_host)
    editor.set_line_spacing(settings.px_for_level(self._line_spacing))  # 建完即套用
    ...
```

## 6. 错误处理

静默容错，绝不崩 UI：

- `load_settings`：读取/解析失败（`OSError` / 非 JSON）→ 返回 `default_settings()` 并向 `stderr` 打一行警告；文件缺失 / 非 dict / 未知档位等校验性回退**静默**返回默认值（首次运行不应告警）。
- `save_settings`：`OSError` → 向 `stderr` 警告，不弹窗、不阻塞（设置仍临时生效于本次运行，仅不落盘）。
- `px_for_level` 收到未知值 → 静默回退默认档像素值。

## 7. 测试

沿用现有约定，纯函数优先：

- 新增 `tests/test_settings.py`（无 Tk，必跑）：
  - `default_settings()` 含默认档与版本；`px_for_level` 三档映射正确、未知值回退默认档。
  - 文件缺失 → 默认；损坏 JSON → 默认；正常 JSON → 读出。
  - save → load 往返相等；`path` 参数支持 `tmp_path`。
- `tests/test_editor.py`：`set_line_spacing(px)` 后 `spacing1/spacing2/spacing3` 配置正确（依赖显示，headless 下随 `tk_root` fixture 跳过，留意 skipped 计数）。
- 不新增 app 级菜单 UI 测试（菜单交互成本高、收益低，YAGNI）。

不触碰序列化边界 → `test_snote.py`、现有 `test_roundtrip_*` 一律不受影响。

## 8. 兼容性

- 现有 `.snote` 文件无需迁移：行间距不在文档内。
- 首次运行无设置文件 → 默认档"标准 (4px)"，所有笔记看起来比当前（0px）略松一点点（已与产品确认可接受）。
- `settings.py` 结构预留 `version` 字段，便于将来扩展偏好。
