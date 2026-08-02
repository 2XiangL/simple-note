# 定时任务提醒功能 · 设计文档

- 日期：2026-08-02
- 状态：已评审，待编写实现计划
- 调度架构：方案 A（`root.after` 单线程调度器）

## 1. 目标与需求

为 Simple Note 增加定时提醒能力，包含两类触发方式：

1. **番茄钟倒计时**：可配置工作时长、休息时长、轮数，自动循环，每次阶段切换时提醒；运行时在窗口标题栏实时显示倒计时。
2. **固定时间提醒**：
   - 一次性：指定日期+时间（如今天 20:00），触发后自动移除。
   - 每日重复：指定 HH:MM（如每天 08:00），每天触发。

**已确认的关键决策：**

| 维度 | 决策 |
| --- | --- |
| 通知方式 | 模态对话框（`messagebox`）+ 提示音（系统蜂鸣或自定义 .wav，可配置）；隐藏到托盘时先唤回窗口再弹框 |
| 番茄钟形态 | 可配置（工作/休息时长、轮数），自动循环，阶段切换提醒 |
| 固定时间类型 | 一次性 + 每日重复 |
| 持久化 | 全部持久化到 `settings.json`（每日提醒、未触发的一次性、番茄钟时长偏好、提示音配置） |
| 管理入口 | 菜单栏「提醒」菜单 → 管理对话框（增删改提醒、启停番茄钟） |
| 实时显示 | 番茄钟运行时在窗口标题栏显示倒计时 |
| 调度架构 | 方案 A：Tk-free 纯逻辑引擎 + `root.after` 每秒驱动，主线程单线程，无新依赖 |

## 2. 架构与模块分解

遵循现有"纯逻辑模块 + UI 组件模块"分层（同 `settings.py`/`util.py` 纯逻辑、`toolbar.py`/`notes_panel.py` UI 组件）。

### 新增模块

- **`reminder.py`** — Tk-free 调度引擎 + 数据模型（纯逻辑，可无显示器单测，同 `settings.py`）。
  - `ReminderScheduler(now_fn=datetime.now)`：时钟可注入（测试用假时钟）。
  - 职责：番茄钟状态机（启停/阶段/轮次/剩余时间）、一次性与每日提醒的增删查、`tick(now) -> 到期事件列表`、`to_dict()/load_dict()` 持久化往返、载入时数据清洗。
- **`notify.py`** — 通知助手（薄 UI 胶水）：`notify(root, title, message, sound_cfg)` + 纯函数 `resolve_sound(sound_cfg)`。
- **`reminder_dialog.py`** — 管理对话框 `ReminderDialog(tk.Toplevel)`（UI 组件，同 `toolbar.py`），中文界面，非模态。

### 改动模块

- **`app.py`** — 接线：菜单栏加「提醒」菜单；创建 `ReminderScheduler` 并在启动时载入持久化状态；`root.after(1000, self._tick)` 每秒驱动；到期事件交给 `notify`；刷新标题栏倒计时；状态变化时保存。
- **`settings.py`** — 扩展以持久化 `sound`/`pomodoro`/`reminders` 新键，保持容错（详见 §4）。

## 3. 数据模型与持久化

数据模型用纯 dict，便于 JSON 往返。

### 番茄钟配置（持久化的是配置，运行态不持久化）

```python
{"work_min": 25, "break_min": 5, "rounds": 4}   # 默认值
```

### 一次性提醒（触发后 fired=True 随即移除）

```python
{"id": "a1b2c3d4", "label": "开会", "when": "2026-08-02T20:00:00", "fired": False}
```

### 每日提醒（本地时间 HH:MM）

```python
{"id": "e5f6a7b8", "label": "喝水", "hour": 8, "minute": 0}
```

`id` 用 `uuid4().hex[:8]`，保证删除/去重有稳定标识。

### 提示音配置（应用偏好，由 settings.py 拥有）

```python
{"mode": "system", "path": ""}   # 默认值
```
- `mode`：`"system"`（系统蜂鸣）或 `"custom"`（自定义音频）。
- `path`：自定义音频文件路径（.wav），仅 `mode == "custom"` 时使用。

### settings.json 布局（现有键下新增三个键）

```json
{
  "version": 1,
  "line_spacing": "标准",
  "sound": {"mode": "system", "path": ""},
  "pomodoro": {"work_min": 25, "break_min": 5, "rounds": 4},
  "reminders": {"oneshot": [ ... ], "daily": [ ... ]}
}
```

### 职责划分

- **`settings.py`** 只负责文件读写 + 保留新键：`load_settings` 扩展为在键存在且大致类型正确（dict）时原样保留 `sound`/`pomodoro`/`reminders`，否则填默认；保持"绝不抛"。**无需 bump version**——旧文件只是缺这些键，缺则默认，向后兼容。
- **`reminder.py`** 负责模式校验：`ReminderScheduler.load_dict(pomodoro, reminders)` 做完整清洗（整数强转、丢弃残缺条目）。数据模型知识留在 `reminder.py`，文件 IO 留在 `settings.py`，单向依赖、无环。

### 明确边界

番茄钟**运行状态**（当前阶段/轮次/结束时刻）不持久化——重启后需重新启动；持久化的只有时长/轮数偏好。

## 4. 调度引擎与数据流

### ReminderScheduler 内部状态

- 持久化：`_pomodoro_cfg`、`_oneshot` 列表、`_daily` 列表。
- 会话级（不持久化）：番茄钟运行态 `_pomo_phase`（idle/work/break）、`_pomo_round`、`_pomo_phase_end`；以及 `_last_tick`（上次 tick 时刻，用于检测"跨过"）。
- 公开方法：`arm(now)`（启动时调用一次，设 `_last_tick = now`，这是"每日不补发启动前已过时刻"性质的来源）、`start_pomodoro(now)`、`stop_pomodoro()`、`tick(now)`、`pomodoro_remaining(now)`、`add_oneshot(...)`、`add_daily(...)`、`remove(id)`、`update_pomodoro(cfg)`、`to_dict()`、`load_dict(pomodoro, reminders)`。

### 番茄钟状态机

- `start_pomodoro(now)`：phase=work、round=1、phase_end = now + work_min。
- `stop_pomodoro()`：phase=idle、phase_end=None。
- 每次 tick 若 `now >= phase_end`：
  - work → break：发"工作结束，休息 X 分钟"，phase_end = now + break_min。
  - break → work 且 round+1：发"休息结束，开始第 N 轮"，phase_end = now + work_min。
  - 最后一轮 work 结束：发"番茄钟完成"，phase=idle。
- **追赶合并**：若 `now` 远超 `phase_end`（如休眠唤醒），用 `while now >= phase_end` 静默推进到当前应有阶段，**每次 tick 只发一条**代表最终状态的通知，避免弹框连发。

### 三类到期检测（`tick(now) -> events`）

1. **一次性**：`now >= when` 且未 fired → 标记 fired 并移出列表，产生事件。
2. **每日**：算出今日时刻 `occ = now.replace(hour=r.hour, minute=r.minute, second=0, microsecond=0)`；当 `_last_tick < occ <= now` 触发（触发后 `_last_tick` 前移，不会重复）。
3. **番茄钟**：如上状态机。
- tick 末尾 `_last_tick = now`。

### 错过提醒的策略

- **一次性**：应用关闭期间错过的，下次启动后第一次 tick 立即补发一次（`now >= when` 自然成立）。
- **每日**：启动时 `arm(now)` 令 `_last_tick = now`，因此**今天启动前已过的每日提醒不补发**（避免晚上 9 点开机却弹"早上 8 点提醒"）；应用运行中电脑休眠、唤醒后已过点的，会补发一次且不重复。
- **番茄钟**：休眠错过多个阶段时按"追赶合并"只发一条。

### 标题栏倒计时

- `pomodoro_remaining(now)`：idle 返回 None；否则返回 `("工作中"/"休息中", "MM:SS", "第N/共M轮")`。
- `app.py` 每次 tick 设 `root.title("Simple Note — 工作中 18:32（第1/4轮）")`，idle 时还原为 `"Simple Note"`。
- 窗口标题当前未被文档名占用（文档名显示在左侧面板），无冲突。

### app.py 数据流

- 启动：`settings.load_settings()` → `scheduler.load_dict(data.get("pomodoro"), data.get("reminders"))` → `self._sound_cfg = data.get("sound")`（缺则默认）→ `scheduler.arm(now)` → `root.after(1000, self._tick)`。
- `_tick`：取 `now` → `events = scheduler.tick(now)` → 逐个 `notify(root, title, msg, self._sound_cfg)` → 按 `pomodoro_remaining` 刷新标题 → 若状态有持久性变化（如一次性被消费）则保存 → 重新 `after`。
- 保存时机：对话框内增删改、番茄钟配置变更、一次性被消费、退出时，统一经 `_persist()` 写回 settings.json。

## 5. 通知、管理对话框与菜单接线

### notify.py（薄 UI 胶水）

`notify(root, title, message, sound_cfg)`：

1. `root.deiconify()` + `root.lift()` + `root.focus_force()` —— 从托盘唤回并抢到前台（否则模态框可能压在后面）。
2. 播放提示音（经纯函数 `resolve_sound(sound_cfg)` 决策）：
   - 自定义：`winsound.PlaySound(path, SND_FILENAME | SND_ASYNC)` 播放 .wav（Windows，零新依赖）；文件缺失/播放失败 → 回退系统蜂鸣。
   - 系统蜂鸣：`winsound.MessageBeep(...)`；异常 → 回退 `root.bell()`。
3. `messagebox.showinfo(title, message)`（模态，须手动关闭）。

`resolve_sound(sound_cfg) -> ("custom", path) | ("system", None)` 为纯函数：`mode == "custom"` 且 `path` 非空且文件存在 → `("custom", path)`，否则 `("system", None)`。这是 notify 中唯一可无显示器单测的部分；实际播音（winsound）与模态框靠手动/集成验证。

### reminder_dialog.py — ReminderDialog(tk.Toplevel)，非模态

关键：**非模态**，不能阻塞记笔记，用户要能边记边看标题栏倒计时。

构造：`ReminderDialog(master, scheduler, sound_cfg, on_change)`，直接读写 scheduler 与提示音配置，任何变更后调 `on_change`（由 app.py 触发持久化 + 标题刷新）；提示音当前值经 `sound_config() -> {"mode","path"}` 取回。四个 LabelFrame：

- **番茄钟**：工作时长/休息时长/轮数 三个 Spinbox（预填当前配置）+「开始/停止」按钮 + 运行状态标签。
- **提醒列表**：Treeview，列 [类型, 内容, 时间]（一次性显示 `一次性/开会/2026-08-02 20:00`，每日显示 `每日/喝水/每天 08:00`）+「删除选中」按钮。
- **新增提醒**：内容 Entry + 类型 Radiobutton（一次性/每日）。
  - 一次性：日期 Entry（默认今天，`YYYY-MM-DD`）+ 时/分 Spinbox；解析失败弹提示。
  - 每日：时(0–23)/分(0–59) Spinbox。
  - 「添加」按钮。
- **提示音**：Radiobutton「系统提示音」/「自定义音频」；选自定义时显示路径 Entry +「浏览...」（`filedialog.askopenfilename`，过滤 `*.wav`）+「试听」按钮。变更经 `on_change` 持久化（写入 settings 的 `sound` 键，app.py 同步更新 `self._sound_cfg`）。

### app.py 菜单接线

- 菜单栏新增「提醒」级联（置于"查看"与"关于"之间）：
  - 「管理提醒...」→ 打开 `ReminderDialog`（**单例**：已打开则 lift，不重复创建）。
  - 「开始番茄钟」/「停止番茄钟」→ 用当前配置快速启停（便利项）。
- 持有 `self._reminder_dlg` 引用以维持单例。

## 6. 错误处理

- **核心不变量：tick 链绝不能死。** 若 `_tick` 抛异常，下一次 `root.after` 就不会排上，所有提醒会静默停摆。因此 `app._tick` 用 try/except 包住主体（异常写 stderr），**无论成败都重新 `after`**；`scheduler.tick` 内部对每条提醒单独保护，一条坏数据不能拖垮整个循环。（类比 tray 的"失败绝不阻断"规则。）
- **持久化**（settings.py）：保持"绝不抛"。`pomodoro`/`reminders` 缺失/损坏 → 默认/空；整体 JSON 损坏 → 全默认；仅向 stderr 警告。
- **载入清洗**（`load_dict`）：时长/轮数强转为正整数（越界则按字段回退默认）；丢弃残缺提醒条目（缺键、类型错、hour/minute 越界、`when` 不可解析）。
- **对话框输入校验**：时 0–23、分 0–59、轮数≥1、时长≥1；一次性日期时间解析失败弹提示、不添加。番茄钟配置夹到合理范围（如工作/休息 1–180 分钟、轮数 1–12）。
- **notify**：`winsound` 失败回退 `root.bell()`；唤回窗口动作包 try/except，确保不阻止弹框。
- **自定义音频**：文件缺失/格式不支持/播放异常 → 静默回退系统蜂鸣，绝不让播音失败阻断弹框；非 Windows 平台无 `winsound`，自定义音频同样回退 `root.bell()`。

## 7. 测试策略

遵循仓库惯例：纯逻辑模块无显示器单测，Tk 控件经 `tk_root` fixture 在无显示器时跳过。

- **`tests/test_reminder.py`**（无显示器可跑，同 test_settings/test_util）：注入假时钟、手动 `tick(now)`，完全确定性。覆盖：
  - 番茄钟状态机全流程与完成；
  - 追赶合并（时钟猛跳只发一条且阶段正确）；
  - 一次性到点触发/移除/不重复/启动补发；
  - 每日跨过触发/不重复/启动不补发已过时刻/休眠唤醒补发一次；
  - `pomodoro_remaining`；
  - `to_dict`/`load_dict` 往返 + 坏数据清洗绝不抛。
- **`tests/test_settings.py`**（扩展，无显示器）：新旧键（含 `sound`）往返、缺键默认、坏提醒数据回退、旧文件（仅 line_spacing）向后兼容。
- **`tests/test_reminder_dialog.py`**（需显示器，无显示器跳过）：轻量冒烟——构造对话框、经 scheduler 增/删提醒反映到列表。
- **`tests/test_notify.py`**（无显示器）：纯函数 `resolve_sound` 的分支（system / custom+文件存在 / custom+文件缺失或路径空 → 回退 system）。
- **notify 播音与模态框**：winsound/messagebox 无法无显示器单测，靠手动验证。
- 实现阶段对 `reminder.py` 走 TDD（先写失败测试再实现）。

## 8. 范围边界（非目标 / YAGNI）

- 不支持每周（按星期几）重复——仅一次性 + 每日。
- 不支持番茄钟运行态跨重启恢复——重启后需重新启动。
- 不支持提醒的暂停/贪睡（snooze）。
- 不引入第三方调度库（APScheduler/schedule）或日期控件。

## 9. 对现有文件的影响与注意事项

- **`settings.py` 的白名单坑**：现有 `load_settings` 只白名单 `line_spacing`、会丢弃其它键，必须扩展为往返 `sound`/`pomodoro`/`reminders`，否则提醒数据存了也会被读丢。
- **自定义音频的格式/平台约束**：经 `winsound.PlaySound` 播放，仅支持 .wav、仅 Windows（与本项目 Windows 取向一致，零新依赖）；其它平台/格式回退系统蜂鸣。不引入 pygame/playsound 等音频依赖。
- **窗口标题**：当前仅初始化时设为 `"Simple Note"`，文档名显示在左侧面板而非标题栏，故标题栏可安全用于番茄钟倒计时。
- **`AGENTS.md` 更新**：实现后把 `test_reminder` 加入"无显示器可跑"集合、`test_reminder_dialog` 加入"需显示器"集合，并补充 `reminder.py`/`notify.py`/`reminder_dialog.py` 的架构说明。
- **线程安全**：本功能全程跑在 Tk 主线程（`root.after`），不涉及 `tray.py` 的跨线程封送；切勿为此引入后台线程。
