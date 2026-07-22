import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from config import ConfigError, Settings

from . import reddit_client, reddit_pipeline, uploaded_videos, video_utils, voices, youtube_pipeline
from .range_slider import RangeSlider
from .upload.youtube_upload import YouTubeUploader


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
                if isinstance(result, (list, tuple)):
                    self.log(f"Done: wrote {len(result)} file(s)")
                    self._last_output_path = Path(result[-1]) if result else None
                else:
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

        ttk.Separator(self, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(10, 6)
        )

        ttk.Label(self, text="Giga Sample: cut multiple background clips from one video").grid(
            row=7, column=0, columnspan=2, sticky="w"
        )

        giga_top_row = ttk.Frame(self)
        giga_top_row.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.load_info_button = ttk.Button(
            giga_top_row, text="Load Info", command=self._load_giga_info
        )
        self.load_info_button.pack(side="left")
        self.giga_status_var = tk.StringVar(value="No video loaded")
        ttk.Label(giga_top_row, textvariable=self.giga_status_var).pack(side="left", padx=(8, 0))

        self._giga_duration = 0.0
        self._giga_title = ""
        self.range_slider = RangeSlider(self, width=480, height=50)
        self.range_slider.grid(row=9, column=0, columnspan=2, sticky="w", pady=(6, 0))

        giga_bottom_row = ttk.Frame(self)
        giga_bottom_row.grid(row=10, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(giga_bottom_row, text="Clips:").pack(side="left")
        self.giga_count_var = tk.IntVar(value=5)
        ttk.Spinbox(
            giga_bottom_row, from_=1, to=50, textvariable=self.giga_count_var, width=5
        ).pack(side="left", padx=(4, 10))
        ttk.Button(giga_bottom_row, text="Giga Sample", command=self._run_giga_sample).pack(
            side="left"
        )

        progress_frame = self.build_progress_widgets(self)
        progress_frame.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 8))

        ttk.Label(self, text="Log:").grid(row=12, column=0, sticky="w")
        self.log_box = self.build_log_box(self)
        self.log_box.grid(row=13, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(13, weight=1)

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

        self.log(f"Starting youtube job: {url} (mode={mode})")
        self.run_in_thread(
            lambda: youtube_pipeline.run(
                url, mode=mode, start=start, end=end,
                out_dir=self.settings.background_clips_dir,
                progress_cb=self.report_progress,
            )
        )

    def _load_giga_info(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a YouTube URL first.")
            return
        self.load_info_button.configure(state="disabled")
        self.giga_status_var.set("Loading...")
        self.log(f"Fetching info for {url}")

        def worker():
            try:
                info = youtube_pipeline.fetch_info(url)
            except Exception as exc:
                self.after(0, lambda: self._on_giga_info_error(exc))
            else:
                self.after(0, lambda: self._on_giga_info_loaded(info))

        threading.Thread(target=worker, daemon=True).start()

    def _on_giga_info_loaded(self, info):
        self.load_info_button.configure(state="normal")
        self._giga_duration = info["duration"]
        self._giga_title = info["title"]
        self.giga_status_var.set(
            f"{info['title']} ({video_utils.format_timestamp(info['duration'])})"
        )
        self.range_slider.set_duration(info["duration"])
        self.log(f"Loaded info: {info['title']} ({info['duration']:.1f}s)")

    def _on_giga_info_error(self, exc):
        self.load_info_button.configure(state="normal")
        self.giga_status_var.set("No video loaded")
        self.log(f"Error loading info: {exc}")
        messagebox.showerror("Error", str(exc))

    def _run_giga_sample(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a YouTube URL first.")
            return
        if self._giga_duration <= 0:
            messagebox.showwarning("Load info first", "Click Load Info before Giga Sample.")
            return

        count = self.giga_count_var.get()
        start, end = self.range_slider.get_range()

        self.log(
            f"Starting giga-sample job: {url} (count={count}, range={start:.1f}-{end:.1f})"
        )
        self.run_in_thread(
            lambda: youtube_pipeline.run_giga_sample(
                url, count=count, start=start, end=end,
                out_dir=self.settings.background_clips_dir,
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

        ttk.Label(self, text="Voice:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        voice_frame = ttk.Frame(self)
        voice_frame.grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        voice_frame.columnconfigure(0, weight=1)
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(voice_frame, textvariable=self.voice_var)
        self.voice_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(voice_frame, text="+ Add", command=self._add_voice).grid(
            row=0, column=1, padx=(6, 0)
        )
        self._refresh_voices()

        button_row = ttk.Frame(self)
        button_row.grid(row=2, column=0, columnspan=2, pady=10, sticky="w")
        ttk.Button(button_row, text="Run", command=self._run).pack(side="left")
        ttk.Button(button_row, text="Open output folder", command=self.open_output_folder).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(
            button_row, text="Create with Upload", command=self._run_with_upload
        ).pack(side="left", padx=(8, 0))

        progress_frame = self.build_progress_widgets(self)
        progress_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 8))

        ttk.Label(self, text="Log:").grid(row=4, column=0, sticky="w")
        self.log_box = self.build_log_box(self)
        self.log_box.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self.rowconfigure(5, weight=1)

    def _refresh_voices(self):
        voice_list = voices.load_voices()
        self.voice_combo["values"] = voice_list
        if voice_list and not self.voice_var.get():
            self.voice_var.set(voice_list[0])

    def _add_voice(self):
        new_id = self.voice_var.get().strip()
        if not new_id:
            messagebox.showwarning(
                "No voice ID", "Type a voice ID into the field, then click + Add."
            )
            return
        updated = voices.add_voice(new_id)
        self.voice_combo["values"] = updated
        self.log(f"Added voice: {new_id}")

    def _run(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a Reddit thread URL first.")
            return

        voice_id = self.voice_var.get().strip() or None
        self.log(f"Starting reddit job: {url} (voice={voice_id or 'default'})")
        self.run_in_thread(
            lambda: reddit_pipeline.run(
                url, self.settings, voice_id=voice_id, progress_cb=self.report_progress
            )
        )

    def _run_with_upload(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a Reddit thread URL first.")
            return
        if not self.settings.enable_upload:
            messagebox.showwarning(
                "Upload not enabled", "Set ENABLE_UPLOAD=true in .env to use Create with Upload."
            )
            return

        voice_id = self.voice_var.get().strip() or None
        self.log(f"Starting reddit job with upload: {url} (voice={voice_id or 'default'})")

        def job():
            icon_cache_dir = Path("cache") / "subreddit_icons"
            self.report_progress("Fetching Reddit post", 0.0)
            post = reddit_client.fetch_post(url, self.settings.apify_api_token, icon_cache_dir)
            out_path = reddit_pipeline.render_post(
                post, self.settings, voice_id=voice_id, progress_cb=self.report_progress
            )
            self.log(f"Rendered {out_path}, uploading to YouTube...")
            uploader = YouTubeUploader(
                self.settings.youtube_client_secrets_file, self.settings.youtube_token_file
            )
            result = uploader.upload(
                out_path,
                title=post.title,
                description=reddit_pipeline.build_hashtags(post.subreddit),
                privacy="public",
            )
            self.log(f"Uploaded to {result.platform}: {result.url}")
            uploaded_videos.record_upload(
                out_path.name, result.platform, result.video_id, result.url
            )
            return out_path

        self.run_in_thread(job)


class LibraryTab(ttk.Frame):
    """Browse and delete previously generated shorts in output/."""

    def __init__(self, parent, settings: Settings):
        super().__init__(parent, padding=12)
        self.settings = settings
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top_row = ttk.Frame(self)
        top_row.grid(row=0, column=0, sticky="ew")
        ttk.Button(top_row, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(
            top_row, text="Open in folder", command=self._open_selected_in_folder
        ).pack(side="left", padx=(8, 0))
        ttk.Button(top_row, text="Play", command=self._play_selected).pack(
            side="left", padx=(8, 0)
        )
        self.delete_button = ttk.Button(top_row, text="Delete", command=self._delete_selected)
        self.delete_button.pack(side="left", padx=(8, 0))

        list_frame = ttk.Frame(self)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(list_frame, selectmode="extended")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        self._paths = []
        self.refresh()

    def refresh(self):
        out_dir = Path("output")
        paths = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if out_dir.exists() else []
        self._paths = paths
        self.listbox.delete(0, "end")
        for p in paths:
            size_mb = p.stat().st_size / (1024 * 1024)
            self.listbox.insert("end", f"{p.name}  ({size_mb:.1f} MB)")

    def _selected_paths(self):
        return [self._paths[i] for i in self.listbox.curselection()]

    def _open_selected_in_folder(self):
        selected = self._selected_paths()
        if not selected:
            messagebox.showinfo("No selection", "Select a short first.")
            return
        subprocess.run(["explorer", "/select,", str(selected[0])])

    def _play_selected(self):
        selected = self._selected_paths()
        if not selected:
            messagebox.showinfo("No selection", "Select a short first.")
            return
        os.startfile(str(selected[0]))

    def _delete_selected(self):
        selected = self._selected_paths()
        if not selected:
            messagebox.showinfo("No selection", "Select a short first.")
            return

        infos = [(p, uploaded_videos.get_upload_info(p.name)) for p in selected]
        youtube_count = sum(1 for _, info in infos if info and info.get("platform") == "youtube")
        names = "\n".join(p.name for p in selected)
        warning = (
            f"\n\n{youtube_count} of these will also be deleted from YouTube."
            if youtube_count
            else ""
        )
        if not messagebox.askyesno(
            "Delete shorts?", f"Permanently delete {len(selected)} file(s)?{warning}\n\n{names}"
        ):
            return

        self.delete_button.configure(state="disabled")

        def worker():
            errors = []
            for path, info in infos:
                if info and info.get("platform") == "youtube":
                    try:
                        uploader = YouTubeUploader(
                            self.settings.youtube_client_secrets_file,
                            self.settings.youtube_token_file,
                        )
                        uploader.delete(info["video_id"])
                        uploaded_videos.remove_upload(path.name)
                    except Exception as exc:
                        errors.append(f"{path.name}: failed to delete from YouTube ({exc})")
                        continue
                try:
                    path.unlink()
                except OSError as exc:
                    errors.append(f"{path.name}: failed to delete file ({exc})")
            self.after(0, lambda: self._on_delete_done(errors))

        threading.Thread(target=worker, daemon=True).start()

    def _on_delete_done(self, errors):
        self.delete_button.configure(state="normal")
        self.refresh()
        if errors:
            messagebox.showerror("Some deletions failed", "\n".join(errors))


def launch():
    settings = Settings.load()

    root = tk.Tk()
    root.title("Shorts Creator")
    root.geometry("640x520")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=8)

    youtube_tab = YouTubeTab(notebook, settings)
    reddit_tab = RedditTab(notebook, settings)
    library_tab = LibraryTab(notebook, settings)
    notebook.add(youtube_tab, text="YouTube")
    notebook.add(reddit_tab, text="Reddit")
    notebook.add(library_tab, text="Library")

    root.mainloop()


if __name__ == "__main__":
    launch()
