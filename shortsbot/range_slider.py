import tkinter as tk
from tkinter import ttk

from . import video_utils


class RangeSlider(ttk.Frame):
    """Custom dual-handle range slider (Tkinter has no built-in equivalent).
    Drag either handle to adjust the selected [start, end] range; defaults to
    the full [0, duration] span whenever a new duration is set."""

    def __init__(self, parent, width: int = 480, height: int = 50, on_change=None):
        super().__init__(parent)
        self._width = width
        self._height = height
        self._margin = 14
        self._handle_radius = 7
        self._min_gap = 1.0
        self._on_change = on_change
        self._duration = 0.0
        self._start = 0.0
        self._end = 0.0
        self._dragging = None  # None | "start" | "end"

        self.canvas = tk.Canvas(self, width=width, height=height, highlightthickness=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self._redraw()

    def set_duration(self, seconds: float) -> None:
        self._duration = max(seconds, 0.001)
        self._start = 0.0
        self._end = self._duration
        self._redraw()
        if self._on_change:
            self._on_change(self._start, self._end)

    def get_range(self) -> tuple:
        return self._start, self._end

    # -- internal --

    def _track_span(self):
        return self._margin, self._width - self._margin

    def _frac_to_x(self, frac):
        left, right = self._track_span()
        return left + frac * (right - left)

    def _x_to_seconds(self, x):
        left, right = self._track_span()
        span = max(right - left, 1)
        frac = (x - left) / span
        frac = min(1.0, max(0.0, frac))
        return frac * self._duration

    def _on_press(self, event):
        if self._duration <= 0:
            return
        start_x = self._frac_to_x(self._start / self._duration)
        end_x = self._frac_to_x(self._end / self._duration)
        self._dragging = "start" if abs(event.x - start_x) <= abs(event.x - end_x) else "end"
        self._on_drag(event)

    def _on_drag(self, event):
        if self._dragging is None or self._duration <= 0:
            return
        seconds = self._x_to_seconds(event.x)
        if self._dragging == "start":
            self._start = max(0.0, min(seconds, self._end - self._min_gap))
        else:
            self._end = min(self._duration, max(seconds, self._start + self._min_gap))
        self._redraw()
        if self._on_change:
            self._on_change(self._start, self._end)

    def _on_release(self, event):
        self._dragging = None

    def _redraw(self):
        self.canvas.delete("all")
        left, right = self._track_span()
        mid_y = self._height // 2
        self.canvas.create_line(left, mid_y, right, mid_y, fill="#999", width=3)

        if self._duration <= 0:
            self.canvas.create_text(
                self._width // 2, mid_y, text="Load Info to enable", fill="#999"
            )
            return

        start_x = self._frac_to_x(self._start / self._duration)
        end_x = self._frac_to_x(self._end / self._duration)
        self.canvas.create_line(start_x, mid_y, end_x, mid_y, fill="#3a7bd5", width=3)
        r = self._handle_radius
        for x in (start_x, end_x):
            self.canvas.create_oval(x - r, mid_y - r, x + r, mid_y + r, fill="#3a7bd5", outline="")
        self.canvas.create_text(
            start_x, mid_y - r - 10, text=video_utils.format_timestamp(self._start)
        )
        self.canvas.create_text(
            end_x, mid_y - r - 10, text=video_utils.format_timestamp(self._end)
        )
