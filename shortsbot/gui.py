import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from config import ConfigError, Settings

from . import reddit_pipeline, video_utils, youtube_pipeline


class PipelineTab(ttk.Frame):
    """Shared scaffolding for a tab that runs a long pipeline in a background
    thread and streams status lines + progress updates back into the UI."""

    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self._log_queue = queue.Queue()
        self._progress_queue = queue.Queue()
        self._last_output_path = None
        self._last_progress_fraction = 0.0
        self.after(150, self._drain_queues)

    def _drain_queues(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass

        try:
            while True:
                stage, fraction = self._progress_queue.get_nowait()
                self.progress_bar["value"] = fraction * 100
                self.status_label.configure(text=stage)
        except queue.Empty:
            pass

        self.after(150, self._drain_queues)

    def log(self, message: str):
        self._log_queue.put(message)

    def report_progress(self, stage: str, fraction: float):
        self._last_progress_fraction = fraction
        self._progress_queue.put((stage, fraction))

    def build_log_box(self, parent):
        box = tk.Text(parent, height=10, width=70, state="disabled", wrap="word")
        box.grid(sticky="nsew")
        return box

    def build_progress_widgets(self, parent):
        frame = ttk.Frame(parent)
        self.progress_bar = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x")
        self.status_label = ttk.Label(frame, text="Idle")
        self.status_label.pack(anchor="w", pady=(2, 0))
        return frame

    def reset_progress(self):
        self._last_progress_fraction = 0.0
        self.progress_bar["value"] = 0
        self.status_label.configure(text="Starting...")

    def run_in_thread(self, target, on_done=None):
        self.reset_progress()

        def wrapper():
            try:
                result = target()
                self.log(f"Done: {result}")
                self._last_output_path = Path(result)
                if on_done:
                    on_done(result)
            except (ConfigError, FileNotFoundError, ValueError, RuntimeError) as exc:
                self.log(f"Error: {exc}")
                self.report_progress("Failed", self._last_progress_fraction)
                messagebox.showerror("Error", str(exc))
            except Exception as exc:  # unexpected failure, still surface it
                self.log(f"Unexpected error: {exc!r}")
                self.report_progress("Failed", self._last_progress_fraction)
                messagebox.showerror("Unexpected error", str(exc))

        threading.Thread(target=wrapper, daemon=True).start()

    def open_output_folder(self):
        if self._last_output_path and self._last_output_path.exists():
            subprocess.run(["explorer", "/select,", str(self._last_output_path)])
        else:
            messagebox.showinfo("No output yet", "Run a job first.")


class YouTubeTab(PipelineTab):
    def __init__(self, parent, settings: Settings):
        super().__init__(parent)
        self.settings = settings
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="YouTube URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", padx=6)

        ttk.Label(self, text="Mode:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.mode_var = tk.StringVar(value="random")
        mode_frame = ttk.Frame(self)
        mode_frame.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(
            mode_frame, text="Random 60s", variable=self.mode_var, value="random",
            command=self._toggle_manual_fields,
        ).pack(side="left")
        ttk.Radiobutton(
            mode_frame, text="Manual start/end", variable=self.mode_var, value="manual",
            command=self._toggle_manual_fields,
        ).pack(side="left", padx=(10, 0))

        ttk.Label(self, text="Start:").grid(row=2, column=0, sticky="w")
        self.start_var = tk.StringVar()
        self.start_entry = ttk.Entry(self, textvariable=self.start_var, state="disabled")
        self.start_entry.grid(row=2, column=1, sticky="ew", padx=6)

        ttk.Label(self, text="End:").grid(row=3, column=0, sticky="w")
        self.end_var = tk.StringVar()
        self.end_entry = ttk.Entry(self, textvariable=self.end_var, state="disabled")
        self.end_entry.grid(row=3, column=1, sticky="ew", padx=6)

        ttk.Label(
            self, text="Saves into background_clips/ (used as Reddit-mode filler footage)."
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        button_row = ttk.Frame(self)
        button_row.grid(row=5, column=0, columnspan=2, pady=10, sticky="w")
        ttk.Button(button_row, text="Run", command=self._run).pack(side="left")
        ttk.Button(
            button_row, text="Open background clips folder", command=self.open_output_folder
        ).pack(side="left", padx=(8, 0))

        progress_frame = self.build_progress_widgets(self)
        progress_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 8))

        ttk.Label(self, text="Log:").grid(row=7, column=0, sticky="w")
        self.log_box = self.build_log_box(self)
        self.log_box.grid(row=8, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(8, weight=1)

    def _toggle_manual_fields(self):
        state = "normal" if self.mode_var.get() == "manual" else "disabled"
        self.start_entry.configure(state=state)
        self.end_entry.configure(state=state)

    def _run(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a YouTube URL first.")
            return

        mode = self.mode_var.get()
        try:
            start = video_utils.parse_timestamp(self.start_var.get()) if self.start_var.get() else None
            end = video_utils.parse_timestamp(self.end_var.get()) if self.end_var.get() else None
        except ValueError:
            messagebox.showwarning("Bad timestamp", "Start/End must be seconds or MM:SS / HH:MM:SS.")
            return

        clips_dir = self.settings.background_clips_dir
        clips_dir.mkdir(parents=True, exist_ok=True)
        out_path = clips_dir / f"clip_{int(time.time())}.mp4"

        self.log(f"Starting youtube job: {url} (mode={mode})")
        self.run_in_thread(
            lambda: youtube_pipeline.run(
                url, mode=mode, start=start, end=end, out_path=out_path,
                progress_cb=self.report_progress,
            )
        )


class RedditTab(PipelineTab):
    def __init__(self, parent, settings: Settings):
        super().__init__(parent)
        self.settings = settings
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Reddit thread URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", padx=6)

        button_row = ttk.Frame(self)
        button_row.grid(row=1, column=0, columnspan=2, pady=10, sticky="w")
        ttk.Button(button_row, text="Run", command=self._run).pack(side="left")
        ttk.Button(button_row, text="Open output folder", command=self.open_output_folder).pack(
            side="left", padx=(8, 0)
        )

        progress_frame = self.build_progress_widgets(self)
        progress_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 8))

        ttk.Label(self, text="Log:").grid(row=3, column=0, sticky="w")
        self.log_box = self.build_log_box(self)
        self.log_box.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(4, weight=1)

    def _run(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a Reddit thread URL first.")
            return

        self.log(f"Starting reddit job: {url}")
        self.run_in_thread(
            lambda: reddit_pipeline.run(url, self.settings, progress_cb=self.report_progress)
        )


def launch():
    settings = Settings.load()

    root = tk.Tk()
    root.title("Shorts Creator")
    root.geometry("640x520")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=8)

    youtube_tab = YouTubeTab(notebook, settings)
    reddit_tab = RedditTab(notebook, settings)
    notebook.add(youtube_tab, text="YouTube")
    notebook.add(reddit_tab, text="Reddit")

    root.mainloop()


if __name__ == "__main__":
    launch()
