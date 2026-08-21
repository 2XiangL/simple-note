# 设计：待办清单与番茄钟联动

日期：2026-08-22
状态：待实现

为 Simple Note 增加全局待办清单：左侧面板改为双页签（笔记/待办），每条 todo 可设为「当前任务」，番茄钟可绑定当前任务运行——每完成一轮工作阶段，该任务累计番茄数 +1，通知文案带任务名。

## 需求决策（已与用户确认）

- **结合方式**：任务绑定番茄钟——todo 设为当前任务后，开始专注即针对它计时；每完成一轮工作阶段计数 +1；通知文案带任务名。不做达到番茄数自动勾选。
- **数据归属**：全局一份清单，存 `settings.json` 新增 `todos` 键（与提醒/番茄钟同层），不随笔记文件走。
- **UI**：左侧面板改 `ttk.Notebook` 双页签（「笔记」/「待办」），不新增窗口。
- **字段范围（YAGNI）**：每条 todo 仅 `text`/`done`/`pomo`/current 绑定 + 上移/下移排序。不做截止日期、优先级、标签、拖拽。

## 方案选型

- **方案 A（采用）**：新建 Tk-free 纯逻辑模块 `todo.py`（`TodoStore`）+ UI 模块 `todo_panel.py` + `reminder.py` 小改（任务名文案与计数信号），`app.py` 接线。与本仓库「纯逻辑模块（reminder/settings/lang）+ UI 组件 + app 胶水」的既有架构同构，核心逻辑可无显示器单测。
- 方案 B（否决）：把 todos 塞进 `ReminderScheduler`。单一状态源，但 reminder.py 职责翻倍（todo CRUD + 提醒 + 番茄钟混杂），UI 穿透 scheduler 做 CRUD，破坏单职责模块惯例。
- 方案 C（否决）：todo 状态直接放 `app.py`。代码最少，但核心逻辑无法无显示器单测，app.py 本就是最大文件，且 app 侧嗅探番茄钟阶段转移脆弱。

## 非目标（YAGNI）

- 不做截止日期/到期提醒、优先级、标签、分类
- 不做手动拖拽排序（只做上移/下移）
- 不做番茄钟运行态持久化（重启后 idle，现状不变）
- 不做达到目标番茄数自动完成任务
- 不修改 `.snote` 文件格式

## 数据模型与持久化（新模块 `todo.py`）

Tk-free 纯逻辑，模式对齐 `reminder.ReminderScheduler`。

**存储**：`settings.json` 新增 `todos` 键：

```json
{"items": [{"id": "a1b2c3d4", "text": "写周报", "done": false, "pomo": 2}],
 "current": "a1b2c3d4"}
```

`current` 为 null 时表示无当前任务。id 为 8 位 hex（`todo.py` 内自有 `_new_id`，同 `reminder._new_id` 的 uuid4 截取风格，不跨模块 import 私有函数）。

### `TodoStore` API

| API | 职责 |
|---|---|
| `load_dict(data)` | 深度清洗（同 `ReminderScheduler.load_dict` 惯例）：非 dict 输入安全；`items` 非 list 忽略；逐条清洗——非 dict 条目丢弃、`text` 非字符串或 strip 后为空丢弃、`done` 强制 bool、`pomo` clamp 到 0..9999、id 去重/缺 id 补发；`current` 指向不存在 id 时置 None。绝不抛 |
| `to_dict()` | 返回可 json 序列化的 `{"items": [...], "current": ...}` 深拷贝 |
| `list_items()` | 返回条目深拷贝列表（两段排序，见不变量） |
| `add(text)` | text 非空校验（ValueError），strip 后插入**未完成组末尾**，返回新条目 |
| `remove(tid)` | 删除条目；若删的是 current 则一并清空 |
| `toggle(tid)` | 翻转 done：置完成 → 沉到**已完成组末尾**并解除 current（若是）；取消完成 → 回**未完成组末尾** |
| `move(tid, delta)` | 段内上移（-1）/下移（+1），越界 no-op |
| `set_current(tid)` / `clear_current()` | 设置/清除当前任务（tid 不存在时 no-op） |
| `current_id()` | 返回当前任务 id 或 None |
| `add_pomo(n)` | 给 current 任务 `pomo += n`（clamp 9999），返回更新后条目；无 current 返回 None（计数丢弃） |

**排序不变量**：`items` 恒为 `[未完成…, 已完成…]` 两段，段内保持手动顺序；`add` 插入未完成组末尾，`toggle` 完成沉底/取消回到未完成组末尾。测试须直接断言此不变量。

## 调度器改动（`reminder.py` 小改）

- `start_pomodoro(now=None, task=None)`：`task` 为任务名 str 或 None，仅用于通知文案；存 `_pomo_task`
- `set_pomodoro_task(task)`：运行中更新文案任务名（用户换当前任务时 app 调用）；idle 时忽略。`stop_pomodoro()` 清空 `_pomo_task`
- `_tick_pomodoro`：追赶循环内累计**工作阶段完成数**（work→break 转换及最终轮 work→全部完成均计 1，break→work 不计）；pomodoro 事件 dict 新增 `"work_completed": n`。休眠追赶跨多轮时 `work_completed` 为累计值，与现有「追赶合并只报最后一条消息」语义互补——计数不丢、通知不刷屏
- 有任务名时文案变化（例：`t("第 %d 轮工作结束（%s），休息 %d 分钟。")`、完成消息带任务名），全部经 `t()` 且 en 译文补进 `EN_TRANSLATIONS`
- `notify.format_events` 只读 `title`/`message`，事件新键完全兼容（已核实）
- 番茄钟运行态（含任务绑定）不持久化，与现状一致

## UI（新模块 `todo_panel.py`）

**布局改造（`app.py`）**：`PanedWindow` 第一个 pane 从 `NotesPanel` 换成 `ttk.Notebook`，两页签：「笔记」（原 `NotesPanel` 原样嵌入）+「待办」（`TodoPanel`）。右侧编辑区、minsize/width 不变。

**`TodoPanel(ttk.Frame)`**——同 `NotesPanel` 的「视图 + 回调」模式，数据在 app 侧：

- 顶部：`ttk.Entry` + 「添加」按钮（空文本提示不添加）
- 中部：`ttk.Treeview`——`#0` 列显示状态符（`☐`/`☑`，当前任务 `▶` 前缀），文本列 `任务文本 (🍅×n)`（`pomo>0` 时）
- 底部：「开始专注/停止专注」按钮——按钮为纯开关语义：番茄钟运行中（无论有无绑定）显示「停止专注」，点击即 `stop_pomodoro()`；idle 时显示「开始专注」，点击绑定当前任务启动，无 current 时提示先选择任务
- 交互：双击行 = 切换完成；右键菜单 = 设为/取消当前任务、切换完成、上移、下移、删除
- 对 app 接口：`set_items(items, current_id, running)` 全量重绘；构造注入回调 `on_add(text)` / `on_toggle(tid)` / `on_remove(tid)` / `on_move(tid, delta)` / `on_set_current(tid)`（tid 为 None 表示取消）/ `on_toggle_focus()`
- 文案一律 `t()`，新 UI 文案同步补 en 译文（`test_en_dict_covers_all_t_callsites` 强制）

## app 接线与数据流（`app.py`）

- `__init__`：`self.todos = TodoStore()` + `load_dict(settings.get("todos"))`；左 pane 换 Notebook
- `_tick`：事件里若有 `kind=="pomodoro"` 且 `work_completed>0` → `todos.add_pomo(n)`；返回非 None 则 persist + `todo_panel.set_items(...)` 刷新。放进现有 try 块，`finally` 重排 `after` 的异常安全结构不动（AGENTS.md 红线）
- current 任务变化统一走 `_on_current_changed()`：`scheduler.set_pomodoro_task(label or None)` + persist + 面板刷新。触发点：`set_current`/`clear_current`、toggle 连带清除、remove 连带清除
- 「开始专注」= `scheduler.start_pomodoro(datetime.now(), task=当前任务名)` + `_refresh_title()`；「提醒」菜单「开始番茄钟」保持无绑定（`task=None`），两个入口并存
- 持久化时机：todo CRUD 即时 persist（同 reminder `on_change` 模式）；`add_pomo` 在 tick 内 persist（同 oneshot fired 模式）
- `_persist()`：增加 `self.settings["todos"] = self.todos.to_dict()`

## `settings.py` 改动

- `default_settings()` 增加 `"todos": {"items": [], "current": None}`
- `load_settings` 键白名单 `("sound", "pomodoro", "reminders")` 增加 `"todos"`（浅读 dict 形值，深度清洗在 `TodoStore.load_dict`——与 reminders 分工惯例一致）

## 边界语义（明确化）

- **运行中删除/完成 current 任务**：番茄钟继续跑（不中断），`_on_current_changed` 把 scheduler 任务名清为 None，后续轮计数丢弃、文案回落无任务名
- **运行中切换 current**：后续完成轮计入新任务。「当前任务」语义 = 下一个完成轮记在哪
- **休眠追赶**：一次 tick `work_completed=n` 整体累加到 current
- **老配置升级**：`settings.json` 无 `todos` 键 → 空清单
- **持久化失败**：沿用 `settings.save_settings` 的 stderr 警告不抛语义

## 测试策略

| 测试文件 | 显示器 | 覆盖 |
|---|---|---|
| `tests/test_todo.py`（新） | 无需 | 清洗（坏条目/去重/pomo clamp/悬空 current/非 dict 输入）、CRUD、两段排序不变量（完成沉底/取消回未完成组末尾/add 插入位置）、current 生命周期（remove/toggle 连带清除）、`add_pomo`（无 current 丢弃/clamp） |
| `tests/test_reminder.py`（增） | 无需 | `task` 文案（有/无任务名）、`work_completed` 计数（单轮/追赶多轮/最终轮收官）、`set_pomodoro_task`（运行中生效/idle 忽略）、stop 清空任务名 |
| `tests/test_settings.py`（增） | 无需 | `todos` 键默认值/往返/白名单透传 |
| `tests/test_app.py`（增） | 多数无需 | Notebook 接线、tick 计数回写 + persist、开始专注路径、current 变化联动 scheduler、运行中删除 current 不中断番茄钟 |
| `tests/test_todo_panel.py`（新） | 需要 | 行渲染（状态符/🍅计数/▶）、双击/右键菜单/回调派发、开始专注按钮态与无 current 提示 |
| `tests/test_lang.py` | 无需 | 完整性扫描自动覆盖新 `t()` 调用点 |

收尾更新 `AGENTS.md`：`todo.py`/`todo_panel.py` 架构条目、headless 测试清单（`test_todo` 加入无显示器名单、`test_todo_panel` 加入需显示器名单）、`settings.json` `todos` 键说明、两页签布局说明。
