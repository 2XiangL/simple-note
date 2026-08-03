# 设计：单实例应用

日期：2026-08-03
状态：已确认，待实现

为 Simple Note 增加单实例保护：再次启动时不再多开，而是把已运行的窗口激活（含从托盘/最小化恢复）并置前，第二个进程随后静默退出。仅 Windows 生效，其他平台不限制多开。

现状痛点：多开时全局热键 Ctrl+Alt+N 注册冲突（tray.py:221 已有"热键被占用，通常是上一个实例仍驻留托盘"的告警），托盘出现多个同图标，设置/提醒各自为政。

## 方案选型

- **方案 A（采用）**：Win32 命名互斥体检测 + `RegisterWindowMessage` 广播 + 第一实例隐藏顶层窗口监听。检测原子无竞态；进程崩溃/退出后 OS 自动释放互斥体，无残留；不依赖窗口标题（标题在番茄钟时动态变化）；激活走 app 自身的 `tray.show()`，托盘 `_hidden` 状态机保持同步。
- 方案 B（否决）：互斥体 + EnumWindows 找 `TkTopLevel` 窗口直接 `SetForegroundWindow`。依赖 Tk 类名与标题前缀（脆），且绕过 tray 状态机直接动窗口，从托盘恢复后 `_hidden` 错乱、热键显隐行为出错。
- 方案 C（否决）：`~/.simple-note/` 锁文件 + PID。崩溃残留、原子性、PID 存活检查边缘情况多，且已确定仅 Windows。

## 非目标（YAGNI）

- 不做文件关联/双击 `.snote` 传参打开（广播通道将来可扩展 WM_COPYDATA，现在不做）
- 不做跨平台锁文件兜底（非 Windows 平台单实例不生效，不阻断启动）
- 不做"是否允许多开"的设置项

## 新模块 `singleinstance.py`

Tk-free、Windows 优先，风格对齐 `tray.py`/`imefont.py`：非 Windows 或 Win32 失败一律优雅降级，绝不阻断启动。

命名常量：

- 互斥体名 `SimpleNote.SingleInstance`（默认会话级 Local 命名空间，多用户/多桌面会话各自独立）
- 注册消息名 `SimpleNote.Activate`
- 窗口类名 `SimpleNoteSingleInstanceWnd`

### API

| API | 职责 |
|---|---|
| `acquire(name=MUTEX_NAME)` | `CreateMutexW(None, FALSE, name)`。首实例返回互斥体句柄（须持有至进程退出）；`GetLastError() == ERROR_ALREADY_EXISTS` 返回 `None`；非 Windows 或 API 异常 → stderr 警告并返回哨兵值放行（fail-open：宁可偶尔多开，不可启动失败） |
| `release(handle)` | `CloseHandle`（退出与测试用；哨兵值为 no-op） |
| `activate_existing(timeout_ms=2000, msg_name=ACTIVATE_MSG_NAME)` | `RegisterWindowMessageW(msg_name)` 后 `SendMessageTimeoutW(HWND_BROADCAST, msg, 0, 0, SMTO_NORMAL\|SMTO_ABORTIFHUNG, timeout_ms)`；尽力而为返回 bool，任何失败静默返回 False。`msg_name` 为测试缝隙（默认值不变），测试用唯一名避免惊动开发机上运行中的真实实例 |
| `set_activation_handler(fn)` | 注册模块级窗口激活回调（可传 None 重置），由 `NoteApp` 就绪时调用；监听线程触发时经此回调封送回主线程 |
| `SingleInstanceListener(threading.Thread)` | 守护线程：隐藏**顶层**窗口 + GetMessageW 消息泵；收到注册消息调用 `on_activate`（仍在监听线程内）。构造参数 `on_activate`（可省略，省略时默认分派到 `set_activation_handler` 注册的模块级回调），可选 `msg_name=ACTIVATE_MSG_NAME`（同上测试缝隙） |

关键点：监听窗口必须是普通隐藏顶层窗口——message-only 窗口（HWND_MESSAGE）收不到 `HWND_BROADCAST` 广播。

### `SingleInstanceListener` 细节

复刻 `_HotkeyListener`（tray.py:40）的既有模式：

- `run()`：`RegisterWindowMessageW` → 注册窗口类（wndproc 为 `WINFUNCTYPE`，**引用保存在实例属性上防 GC**）→ `CreateWindowExW` 隐藏顶层窗口 → GetMessageW 循环；`msg.message == 注册消息 id` 时调用 `_handle_message` → `on_activate()`；`finally` 里 `DestroyWindow` + `UnregisterClass`（在创建窗口的线程内销毁）
- `stop()`：`PostThreadMessageW(thread_id, WM_QUIT)` 打断 GetMessage（同热键监听的 stop）
- 窗口创建/注册失败 → stderr 警告后线程退出（退化为"第二实例静默退出但无法激活"，应用本身不受影响）
- `_handle_message(msg_id)` 为纯分派逻辑（注册消息 id → 触发回调；其他 → 忽略），可脱离 Win32 单测

## `main.py` 改造

单实例检查放在**最前面**，早于 Pillow 探测与 `tk.Tk()`——第二实例不创建任何 Tk 对象：

```python
def main():
    guard = singleinstance.acquire()
    if guard is None:            # 已有实例在运行
        singleinstance.activate_existing()
        return                   # 静默退出
    ... 原有 Pillow 探测 / Tk 启动 ...
```

`guard` 句柄存模块级全局（如 `main._GUARD`），进程存活期间不关闭；OS 在进程退出/崩溃时自动释放互斥体。

## 激活链路（第一实例）

线程模型复刻热键监听：**监听线程只入队、绝不碰 Tk**；主线程消费。

**监听线程在 `main.py` 中启动，早于一切 Tk 创建**（acquire 成功紧接启动）——消除启动竞态：若第二实例在首个实例的 Tk 初始化窗口（约 0.5-2s）内启动，广播仍会被监听线程收到。此时窗口激活回调可能尚未注册，激活为 no-op——窗口本来也未显示，无感知影响。

封送复用 `TrayController` 已有的 `_calls` 队列 + `root.after(50ms)` 轮询 `_drain`。`TrayController` 增加一行公开入口：

```python
def enqueue(self, fn):
    """供外部线程入队（内部 _marshal 的公开别名）。"""
    self._calls.put(fn)
```

激活回调经**模块级注册**接线（避免 main.py 持有 app 引用）：

- `main.py`：`_LISTENER = SingleInstanceListener()`（省略 on_activate，默认分派到模块级回调）+ `.start()`；`mainloop()` 返回后 `_LISTENER.stop()`
- `app.NoteApp.__init__`（`self.tray.start()` 之后）：`singleinstance.set_activation_handler(lambda: self.tray.enqueue(self.tray.show))`
- `_real_quit` 不再负责 stop 监听线程（已移至 main.py 的 mainloop 退出路径）

`tray.show()` 已含 `_hidden=False` + `deiconify` + `lift` + `focus_force`：托盘隐藏、最小化、普通可见三种状态都能恢复并置前，且 `_hidden` 状态机同步。窗口本来就可见时 `show()` 等价于 lift+focus，行为正确。

时序：第二实例广播后立即退出；第一实例监听线程收到消息 → 默认分派 → 模块级回调（enqueue）→ 主线程下一次 50ms 轮询消费 → 窗口置前。主线程卡在模态框时激活延迟到模态框关闭，可接受。

## 错误处理

对齐 tray 的"绝不阻断启动"惯例：

- `acquire()` 遇非 `ERROR_ALREADY_EXISTS` 的 Win32 异常 → stderr 警告 + 放行启动
- `activate_existing()` 任何失败 → 静默返回 False，第二实例照样退出（最坏：点了没反应，不弹错）
- 监听线程创建窗口/注册类失败 → 警告后退出，应用正常运行
- 监听线程消息处理异常捕获，绝不让消息泵线程裸死

## 测试

全部无显示器可跑（不碰真实 Tk），风格对齐 `tests/test_tray.py`。互斥体/消息名在测试中带 `os.getpid()` 唯一化，避免与开发机上运行中的真实实例互扰（真实实例持有同名互斥体、监听同名广播）：

| 测试 | 手段 |
|---|---|
| `acquire`/`release` 语义 | 同进程内二次 `CreateMutexW` 同名必得 `ERROR_ALREADY_EXISTS`：首实例→句柄、二次→None、`release` 后可再 acquire。真实 Win32 调用，`skipif(sys.platform != "win32")` |
| 广播→监听闭环（集成） | 起真实 `SingleInstanceListener`（回调记录到列表）→ 调 `activate_existing()` → 轮询等待回调触发。纯 Win32，不碰 Tk |
| wndproc 分派逻辑 | 直接调 `_handle_message(msg_id)`：注册消息 id → 触发回调；其他消息 → 不触发 |
| `main()` 分流 | monkeypatch `acquire` 返回 None → 断言 `activate_existing` 被调且未创建 Tk；返回哨兵 → 断言照常进入启动流程（monkeypatch 掉 `tk.Tk`/`NoteApp`） |
| `TrayController.enqueue` | 复用 `_FakeRoot`：入队 → `_drain` → 回调执行 |

## 文档同步

- `AGENTS.md` Architecture 增加 `singleinstance.py` 条目（互斥体+广播+监听线程；监听线程绝不碰 Tk 的封送规则）

## 兼容性

- 不新增依赖（纯 ctypes）；`SimpleNote.spec` 无需改动
- 非 Windows：`acquire` 放行、`activate_existing` no-op、监听线程不启动，行为与现状一致
