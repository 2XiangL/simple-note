"""ImageResizer：双击图片后的 8 点缩放浮层。

无边框 Toplevel + 透明色（Windows -transparentcolor）：选框与 8 个手柄可见，
图片在编辑器中实时缩放并可见。角手柄锁纵横比，边手柄单方向；Enter 确认、Esc 取消。
"""

import tkinter as tk

HANDLE_SIZE = 8
MIN_SIZE = 16
_PAD = HANDLE_SIZE      # 画布四周留白，防止手柄被裁剪
_KEY = "#ff00ff"        # 透明键色

_ROLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


class ImageResizer:
    def __init__(self, editor, img_id, bbox):
        self.editor = editor
        self.img_id = img_id
        self.rel_x, self.rel_y, self.orig_w, self.orig_h = bbox
        w, h = editor.image_display_size(img_id) or (self.orig_w, self.orig_h)
        self.ratio = (w or 1) / (h or 1)
        self._anchor = (w, h)          # 拖拽起点尺寸（拖拽期间冻结）
        self._drag_role = None
        self._drag_start = None

        self.win = tk.Toplevel()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=_KEY)
        try:
            self.win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass  # 非 Windows 平台退化为不透明
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bd=0, bg=_KEY)
        self.canvas.pack(fill=tk.BOTH, expand=tk.YES)

        self._draw(w, h)
        self._place()
        self.canvas.focus_set()

        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Return>", lambda e: self._confirm())
        self.canvas.bind("<Escape>", lambda e: self._cancel())
        self.canvas.bind("<Delete>", lambda e: self._delete())
        self.canvas.bind("<BackSpace>", lambda e: self._delete())
        self._binds = []
        for seq in ("<Configure>", "<MouseWheel>", "<Up>", "<Down>", "<Prior>", "<Next>"):
            cbid = editor.bind(seq, self._on_editor_changed, add="+")
            self._binds.append((seq, cbid))
        self.canvas.bind("<FocusOut>", lambda e: self._confirm())

    def _live_size(self):
        return self.editor.image_display_size(self.img_id) or (self.orig_w, self.orig_h)

    def _draw(self, w, h):
        self.canvas.delete("all")
        self.win.geometry("%dx%d" % (w + 2 * _PAD, h + 2 * _PAD))
        self.canvas.create_rectangle(_PAD, _PAD, _PAD + w, _PAD + h, outline="#1a73e8", width=2)
        for role in _ROLES:
            cx, cy = self._handle_pos(role, w, h)
            hid = self.canvas.create_rectangle(
                _PAD + cx - HANDLE_SIZE, _PAD + cy - HANDLE_SIZE,
                _PAD + cx + HANDLE_SIZE, _PAD + cy + HANDLE_SIZE,
                fill="#1a73e8", outline="white",
            )
            self.canvas.tag_bind(hid, "<Button-1>", lambda e, r=role: self._on_handle_press(r, e))

    def _handle_pos(self, role, w, h):
        return {
            "nw": (0, 0), "n": (w / 2, 0), "ne": (w, 0),
            "e": (w, h / 2), "se": (w, h), "s": (w / 2, h),
            "sw": (0, h), "w": (0, h / 2),
        }[role]

    def _place(self):
        idx = self.editor._index_of_image(self.img_id)
        if idx is None:
            return
        bbox = self.editor.bbox(idx)
        if not bbox:
            return
        self.rel_x, self.rel_y, _, _ = bbox
        sx = self.editor.winfo_rootx() + self.rel_x - _PAD
        sy = self.editor.winfo_rooty() + self.rel_y - _PAD
        self.win.geometry("+%d+%d" % (sx, sy))

    def _on_handle_press(self, role, event):
        self._drag_role = role
        self._drag_start = (event.x_root, event.y_root)
        self._anchor = self._live_size()

    def _on_motion(self, event):
        if not self._drag_role or not self._drag_start:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        role = self._drag_role
        aw, ah = self._anchor
        if role == "e":
            w, h = aw + dx, ah
        elif role == "w":
            w, h = aw - dx, ah
        elif role == "s":
            w, h = aw, ah + dy
        elif role == "n":
            w, h = aw, ah - dy
        else:  # 角手柄锁纵横比
            w = aw - dx if role in ("nw", "sw") else aw + dx
            h = w / self.ratio
        w = max(MIN_SIZE, int(w))
        h = max(MIN_SIZE, int(h))
        self.editor.set_image_size(self.img_id, w, h)
        self._refresh()

    def _on_release(self, _event):
        self._drag_role = None
        self._drag_start = None

    def _refresh(self):
        w, h = self._live_size()
        self._draw(w, h)
        self._place()

    def _on_editor_changed(self, _event=None):
        if self._drag_role:
            return
        self._refresh()

    def _confirm(self):
        self.editor.end_resize()

    def _cancel(self):
        self.editor.set_image_size(self.img_id, int(self.orig_w), int(self.orig_h))
        self.editor.end_resize()

    def _delete(self):
        self.editor.delete_image(self.img_id)
        self.editor.end_resize()

    def destroy(self):
        for seq, cbid in self._binds:
            try:
                self.editor.unbind(seq, cbid)
            except Exception:
                pass
        self.win.destroy()
