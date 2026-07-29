"""ImageResizer：双击图片后的 8 点缩放浮层。"""

import tkinter as tk

HANDLE_SIZE = 8
MIN_SIZE = 16

# 手柄角色（顺时针）
_ROLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


class ImageResizer:
    def __init__(self, editor, img_id, bbox):
        self.editor = editor
        self.img_id = img_id
        self.x, self.y, self.orig_w, self.orig_h = bbox
        w, h = editor.image_display_size(img_id)
        self.ratio = (w or 1) / (h or 1)
        self.start_w, self.start_h = w, h
        self._drag_role = None
        self._drag_start = None

        self.canvas = tk.Canvas(editor, highlightthickness=0, bd=0)
        self.canvas.configure(bg="")
        self._draw()
        self._place()

        self.canvas.focus_set()
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Return>", lambda e: self._confirm())
        self.canvas.bind("<Escape>", lambda e: self._cancel())
        editor.bind("<Configure>", self._on_editor_changed, add="+")

    # ---- 绘制 ----
    def _draw(self):
        self.canvas.delete("all")
        w, h = self.start_w, self.start_h
        self.canvas.configure(width=w, height=h)
        self.canvas.create_rectangle(1, 1, w - 1, h - 1, outline="#1a73e8", width=2, tags="border")
        self._handles = {}
        for role in _ROLES:
            cx, cy = self._handle_pos(role, w, h)
            hid = self.canvas.create_rectangle(
                cx - HANDLE_SIZE, cy - HANDLE_SIZE, cx + HANDLE_SIZE, cy + HANDLE_SIZE,
                fill="#1a73e8", outline="white", tags=("handle", role),
            )
            self.canvas.tag_bind(hid, "<Button-1>", lambda e, r=role: self._on_handle_press(r, e))
            self._handles[role] = hid

    def _handle_pos(self, role, w, h):
        positions = {
            "nw": (0, 0), "n": (w / 2, 0), "ne": (w, 0),
            "e": (w, h / 2), "se": (w, h), "s": (w / 2, h),
            "sw": (0, h), "w": (0, h / 2),
        }
        return positions[role]

    def _place(self):
        self.canvas.place(x=self.x, y=self.y)

    # ---- 拖拽 ----
    def _on_handle_press(self, role, event):
        self._drag_role = role
        self._drag_start = (event.x_root, event.y_root)
        self.start_w, self.start_h = self.editor.image_display_size(self.img_id)

    def _on_motion(self, event):
        if not self._drag_role or not self._drag_start:
            return
        dx = event.x_root - self._drag_start[0]
        dy = event.y_root - self._drag_start[1]
        role = self._drag_role
        w, h = self.start_w, self.start_h
        if role == "e":
            w = self.start_w + dx
        elif role == "w":
            w = self.start_w - dx
        elif role == "s":
            h = self.start_h + dy
        elif role == "n":
            h = self.start_h - dy
        else:  # 角手柄：锁纵横比
            if role in ("nw", "sw"):
                w = self.start_w - dx
            else:
                w = self.start_w + dx
            h = w / self.ratio
        w = max(MIN_SIZE, int(w))
        h = max(MIN_SIZE, int(h))
        self.editor.set_image_size(self.img_id, w, h)
        self._reposition()

    def _on_release(self, _event):
        self._drag_role = None
        self._drag_start = None

    def _reposition(self):
        idx = self.editor._index_of_image(self.img_id)
        if idx is None:
            return
        bbox = self.editor.bbox(idx)
        if not bbox:
            return
        self.x, self.y, _, _ = bbox
        self.start_w, self.start_h = self.editor.image_display_size(self.img_id)
        self._draw()
        self._place()

    def _on_editor_changed(self, _event=None):
        if self._drag_role:
            return
        self._reposition()

    # ---- 结束 ----
    def _confirm(self):
        self.editor.end_resize()

    def _cancel(self):
        self.editor.set_image_size(self.img_id, int(self.orig_w), int(self.orig_h))
        self.editor.end_resize()

    def destroy(self):
        try:
            self.editor.unbind("<Configure>")
        except Exception:
            pass
        self.canvas.destroy()
