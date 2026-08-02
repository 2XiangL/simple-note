"""ReminderDialog：提醒管理对话框（非模态 Toplevel）。"""

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import notify


def _valid_hhmm(hour, minute):
    return 0 <= hour <= 23 and 0 <= minute <= 59


class ReminderDialog(tk.Toplevel):
    def __init__(self, master, scheduler, sound_cfg, on_change):
        super().__init__(master)
        self.title("提醒管理")
        self._scheduler = scheduler
        self._on_change = on_change
        self._sound_cfg = dict(sound_cfg) if isinstance(sound_cfg, dict) else {"mode": "system", "path": ""}
        self._build_pomodoro()
        self._build_list()
        self._build_add()
        self._build_sound()
        self.refresh_list()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 番茄钟 ----
    def _build_pomodoro(self):
        frame = ttk.LabelFrame(self, text="番茄钟")
        frame.pack(fill=tk.X, padx=6, pady=4)
        cfg = self._scheduler.pomodoro_config()
        self._work_var = tk.IntVar(value=cfg["work_min"])
        self._break_var = tk.IntVar(value=cfg["break_min"])
        self._rounds_var = tk.IntVar(value=cfg["rounds"])
        ttk.Label(frame, text="工作(分)").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=1, to=180, width=4, textvariable=self._work_var).pack(side=tk.LEFT)
        ttk.Label(frame, text="休息(分)").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=1, to=180, width=4, textvariable=self._break_var).pack(side=tk.LEFT)
        ttk.Label(frame, text="轮数").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=1, to=12, width=4, textvariable=self._rounds_var).pack(side=tk.LEFT)
        self._pomo_btn = ttk.Button(frame, text="开始", width=6, command=self._on_pomo_toggle)
        self._pomo_btn.pack(side=tk.LEFT, padx=6)
        self._pomo_status = ttk.Label(frame, text="")
        self._pomo_status.pack(side=tk.LEFT, padx=4)

    def _apply_pomodoro_cfg(self):
        try:
            cfg = {
                "work_min": self._work_var.get(),
                "break_min": self._break_var.get(),
                "rounds": self._rounds_var.get(),
            }
        except tk.TclError:
            return
        self._scheduler.update_pomodoro(cfg)

    def _on_pomo_toggle(self):
        self._apply_pomodoro_cfg()
        if self._scheduler.pomodoro_phase() == "idle":
            self._scheduler.start_pomodoro()
        else:
            self._scheduler.stop_pomodoro()
        self.refresh_status()
        self._on_change()

    def refresh_status(self):
        running = self._scheduler.pomodoro_phase() != "idle"
        self._pomo_btn.configure(text="停止" if running else "开始")
        rem = self._scheduler.pomodoro_remaining()
        self._pomo_status.configure(text=("%s %s %s" % rem) if rem else "")

    # ---- 列表 ----
    def _build_list(self):
        frame = ttk.LabelFrame(self, text="提醒列表")
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self._tree = ttk.Treeview(frame, columns=("type", "label", "when"), show="headings", height=6)
        self._tree.heading("type", text="类型")
        self._tree.heading("label", text="内容")
        self._tree.heading("when", text="时间")
        self._tree.column("type", width=60)
        self._tree.column("label", width=140)
        self._tree.column("when", width=140)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Button(frame, text="删除选中", command=self._on_delete).pack(side=tk.RIGHT, padx=4)

    def refresh_list(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        oneshot, daily = self._scheduler.list_reminders()
        for e in oneshot:
            self._tree.insert("", tk.END, iid=e["id"], values=("一次性", e["label"], e["when"].replace("T", " ")))
        for e in daily:
            self._tree.insert("", tk.END, iid=e["id"], values=("每日", e["label"], "每天 %02d:%02d" % (e["hour"], e["minute"])))
        self.refresh_status()

    def _on_delete(self):
        sel = self._tree.selection()
        if not sel:
            return
        for rid in sel:
            self._scheduler.remove(rid)
        self.refresh_list()
        self._on_change()

    # ---- 新增 ----
    def _build_add(self):
        frame = ttk.LabelFrame(self, text="新增提醒（每日忽略日期）")
        frame.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(frame, text="内容").pack(side=tk.LEFT, padx=2)
        self._label_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._label_var, width=12).pack(side=tk.LEFT)
        self._type_var = tk.StringVar(value="daily")
        ttk.Radiobutton(frame, text="每日", value="daily", variable=self._type_var).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(frame, text="一次性", value="oneshot", variable=self._type_var).pack(side=tk.LEFT, padx=4)
        self._date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Label(frame, text="日期").pack(side=tk.LEFT, padx=2)
        ttk.Entry(frame, textvariable=self._date_var, width=10).pack(side=tk.LEFT)
        self._hour_var = tk.IntVar(value=datetime.now().hour)
        self._minute_var = tk.IntVar(value=0)
        ttk.Label(frame, text="时").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=0, to=23, width=3, textvariable=self._hour_var).pack(side=tk.LEFT)
        ttk.Label(frame, text="分").pack(side=tk.LEFT, padx=2)
        ttk.Spinbox(frame, from_=0, to=59, width=3, textvariable=self._minute_var).pack(side=tk.LEFT)
        ttk.Button(frame, text="添加", command=self._on_add).pack(side=tk.LEFT, padx=6)

    def _on_add(self):
        label = self._label_var.get().strip()
        if not label:
            messagebox.showwarning("新增提醒", "请填写内容。", parent=self)
            return
        try:
            hour = self._hour_var.get()
            minute = self._minute_var.get()
        except tk.TclError:
            messagebox.showwarning("新增提醒", "时间格式不正确。", parent=self)
            return
        if not _valid_hhmm(hour, minute):
            messagebox.showwarning("新增提醒", "时间超出范围（时 0–23，分 0–59）。", parent=self)
            return
        if self._type_var.get() == "daily":
            self._scheduler.add_daily(label, hour, minute)
        else:
            try:
                when = datetime.strptime("%s %02d:%02d" % (self._date_var.get().strip(), hour, minute), "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showwarning("新增提醒", "日期格式应为 YYYY-MM-DD。", parent=self)
                return
            self._scheduler.add_oneshot(label, when)
        self._label_var.set("")
        self.refresh_list()
        self._on_change()

    # ---- 提示音 ----
    def _build_sound(self):
        frame = ttk.LabelFrame(self, text="提示音")
        frame.pack(fill=tk.X, padx=6, pady=4)
        self._sound_mode_var = tk.StringVar(value=self._sound_cfg.get("mode", "system"))
        ttk.Radiobutton(frame, text="系统提示音", value="system", variable=self._sound_mode_var, command=self._on_sound_change).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(frame, text="自定义音频", value="custom", variable=self._sound_mode_var, command=self._on_sound_change).pack(side=tk.LEFT, padx=4)
        self._sound_path_var = tk.StringVar(value=self._sound_cfg.get("path", ""))
        ttk.Entry(frame, textvariable=self._sound_path_var, width=24).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame, text="浏览...", width=6, command=self._on_browse).pack(side=tk.LEFT)
        ttk.Button(frame, text="试听", width=4, command=self._on_preview).pack(side=tk.LEFT, padx=4)

    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="选择音频文件", filetypes=[("Wave 音频", "*.wav"), ("所有文件", "*.*")], parent=self
        )
        if path:
            self._sound_path_var.set(path)
            self._sound_mode_var.set("custom")
            self._on_sound_change()

    def _on_preview(self):
        notify.notify(self, "试听", "提示音试听", self.sound_config())

    def _on_sound_change(self):
        self._sound_cfg = self.sound_config()
        self._on_change()

    def sound_config(self):
        return {"mode": self._sound_mode_var.get(), "path": self._sound_path_var.get().strip()}

    def _on_close(self):
        self._on_change()
        self.destroy()
