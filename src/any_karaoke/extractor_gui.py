"""Tkinter front end for the extractor.

Extraction runs on a worker thread and talks to the UI through a queue. Tk is not thread
safe, so the worker never touches a widget: it only puts messages on self.messages, and
the UI drains them from a root.after poll.
"""

import os
import queue
import subprocess
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from any_karaoke.extractor import (
    ExtractionCancelled,
    ProgressReporter,
    WhisperModels,
    extract_a_new_mp3_file,
    load_separator,
    song_folder_for,
)
from any_karaoke.game_config import (
    MP3_BITRATE,
    OUTPUT_AUDIO_FORMAT,
    WHISPER_MODEL,
    WHISPER_MODEL_CHOICES,
)
from any_karaoke.song_files import is_karaoke_folder

POLL_INTERVAL_MS = 100
MAX_LOG_LINES = 2000

FORMAT_LABELS = {f"mp3 ({MP3_BITRATE}kbps)": "mp3", "wav (lossless)": "wav"}

STATUS_QUEUED = "queued"
STATUS_SKIPPED = "skipped"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"


# ================================================
# Worker side plumbing
# ================================================
class GuiReporter(ProgressReporter):
    """Sends extraction progress to the UI queue instead of stdout."""

    def __init__(self, messages, cancel_event, item_id):
        self.messages = messages
        self.cancel_event = cancel_event
        self.item_id = item_id

    def stage(self, name):
        self.messages.put(("stage", self.item_id, name))

    def percent(self, value):
        self.messages.put(("percent", self.item_id, value))

    def log(self, message):
        self.messages.put(("log", str(message)))

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise ExtractionCancelled("cancelled by user")


class QueueWriter:
    """File-like object funnelling worker stdout and stderr into the log pane.

    Carriage returns are collapsed so tqdm style progress bars show as a single
    updating line rather than thousands of log entries.
    """

    def __init__(self, messages):
        self.messages = messages
        self._buffer = ""

    def write(self, text):
        self._buffer += text
        while True:
            index = min((i for i in (self._buffer.find("\n"), self._buffer.find("\r")) if i >= 0), default=-1)
            if index < 0:
                break
            line, self._buffer = self._buffer[:index], self._buffer[index + 1 :]
            if line.strip():
                self.messages.put(("log", line.rstrip()))
        return len(text)

    def flush(self):
        if self._buffer.strip():
            self.messages.put(("log", self._buffer.rstrip()))
        self._buffer = ""


# ================================================
# The window
# ================================================
class ExtractorWindow:
    def __init__(self, root, output_folder=None):
        self.root = root
        self.messages = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self._poll_id = None
        self._closing = False
        # tree item id -> source mp3 path, and the folder it produced
        self.sources = {}
        self.results = {}

        root.title("Any Karaoke Extractor")
        root.geometry("900x680")
        root.minsize(760, 560)

        self.output_var = tk.StringVar(value=output_folder or os.path.join(os.getcwd(), "karaoke_tracks"))
        self.model_var = tk.StringVar(value=WHISPER_MODEL)
        self.format_var = tk.StringVar(value=self._label_for_format(OUTPUT_AUDIO_FORMAT))
        self.skip_var = tk.BooleanVar(value=True)
        self.stage_var = tk.StringVar(value="idle")
        self.position_var = tk.StringVar(value="")

        self._build_settings(root)
        self._build_queue(root)
        self._build_progress(root)
        self._build_actions(root)
        self._build_log(root)

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_id = self.root.after(POLL_INTERVAL_MS, self._drain_messages)

    # --- layout
    def _build_settings(self, root):
        frame = ttk.LabelFrame(root, text="Settings", padding=8)
        frame.pack(fill="x", padx=8, pady=(8, 4))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Output folder").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(frame, textvariable=self.output_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(frame, text="Browse", command=self._choose_output).grid(row=0, column=2, padx=(6, 0))

        options = ttk.Frame(frame)
        options.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(options, text="Model").pack(side="left")
        ttk.Combobox(
            options,
            textvariable=self.model_var,
            values=list(WHISPER_MODEL_CHOICES),
            state="readonly",
            width=10,
        ).pack(side="left", padx=(4, 14))

        ttk.Label(options, text="Format").pack(side="left")
        ttk.Combobox(
            options,
            textvariable=self.format_var,
            values=list(FORMAT_LABELS),
            state="readonly",
            width=14,
        ).pack(side="left", padx=(4, 14))

        ttk.Checkbutton(
            options,
            text="Skip songs already extracted",
            variable=self.skip_var,
        ).pack(side="left")

    def _build_queue(self, root):
        frame = ttk.LabelFrame(root, text="Queue", padding=8)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        columns = ("song", "status")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("song", text="Song")
        self.tree.heading("status", text="Status")
        self.tree.column("song", width=520, anchor="w")
        self.tree.column("status", width=220, anchor="w")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", padx=8)
        ttk.Button(buttons, text="Add mp3s", command=self._add_files).pack(side="left")
        ttk.Button(buttons, text="Remove selected", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear", command=self._clear_queue).pack(side="left")

    def _build_progress(self, root):
        frame = ttk.Frame(root, padding=(8, 8))
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, textvariable=self.stage_var, width=22).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(frame, textvariable=self.position_var, width=14).grid(row=0, column=2, sticky="e")

    def _build_actions(self, root):
        frame = ttk.Frame(root, padding=(8, 0))
        frame.pack(fill="x")

        self.start_button = ttk.Button(frame, text="Start", command=self._start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(frame, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=6)

        ttk.Button(frame, text="Open folder", command=self._open_folder).pack(side="right")
        ttk.Button(frame, text="Play selected", command=self._play_selected).pack(side="right", padx=6)

    def _build_log(self, root):
        frame = ttk.LabelFrame(root, text="Log", padding=8)
        frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.log = ScrolledText(frame, height=10, wrap="none", state="disabled")
        self.log.pack(fill="both", expand=True)

    # --- settings helpers
    @staticmethod
    def _label_for_format(audio_format):
        for label, value in FORMAT_LABELS.items():
            if value == audio_format:
                return label
        return next(iter(FORMAT_LABELS))

    @property
    def audio_format(self):
        return FORMAT_LABELS.get(self.format_var.get(), OUTPUT_AUDIO_FORMAT)

    # --- queue management
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose audio files",
            filetypes=[("Audio files", "*.mp3 *.wav *.flac *.m4a *.ogg"), ("All files", "*.*")],
        )
        already = set(self.sources.values())
        for path in paths:
            if path in already:
                continue
            item_id = self.tree.insert("", "end", values=(os.path.basename(path), STATUS_QUEUED))
            self.sources[item_id] = path

    def _remove_selected(self):
        if self._busy():
            return
        for item_id in self.tree.selection():
            self.tree.delete(item_id)
            self.sources.pop(item_id, None)
            self.results.pop(item_id, None)

    def _clear_queue(self):
        if self._busy():
            return
        for item_id in list(self.sources):
            self.tree.delete(item_id)
        self.sources.clear()
        self.results.clear()

    def _choose_output(self):
        chosen = filedialog.askdirectory(title="Choose output folder")
        if chosen:
            self.output_var.set(chosen)

    def _busy(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "Wait for the current run to finish, or press Cancel.")
            return True
        return False

    def _set_status(self, item_id, status):
        if self.tree.exists(item_id):
            song = self.tree.set(item_id, "song")
            self.tree.item(item_id, values=(song, status))

    # --- running
    def _start(self):
        if self._busy():
            return

        jobs = [(item_id, path) for item_id, path in self.sources.items() if self.tree.exists(item_id)]
        if not jobs:
            messagebox.showinfo("Nothing to do", "Add at least one audio file to the queue.")
            return

        output_folder = self.output_var.get().strip()
        if not output_folder:
            messagebox.showerror("No output folder", "Choose a folder for the extracted songs.")
            return

        try:
            os.makedirs(output_folder, exist_ok=True)
        except OSError as error:
            messagebox.showerror("Bad output folder", str(error))
            return

        for item_id, _ in jobs:
            self._set_status(item_id, STATUS_QUEUED)

        self.cancel_event.clear()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.configure(value=0)

        self.worker = threading.Thread(
            target=self._run_queue,
            args=(jobs, output_folder, self.model_var.get(), self.audio_format, self.skip_var.get()),
            daemon=True,
        )
        self.worker.start()

    def _run_queue(self, jobs, output_folder, whisper_model, audio_format, skip_existing):
        """Worker thread. Only communicates through self.messages."""
        writer = QueueWriter(self.messages)
        models = WhisperModels(whisper_model)
        separator = None

        try:
            # Model downloads and library warnings go to stdout/stderr; show them in the log
            with redirect_stdout(writer), redirect_stderr(writer):
                for position, (item_id, mp3_path) in enumerate(jobs, start=1):
                    if self.cancel_event.is_set():
                        self.messages.put(("status", item_id, STATUS_CANCELLED))
                        continue

                    self.messages.put(("position", position, len(jobs)))
                    reporter = GuiReporter(self.messages, self.cancel_event, item_id)

                    if skip_existing:
                        existing = song_folder_for(mp3_path, output_folder)
                        if is_karaoke_folder(existing):
                            self.messages.put(("log", f"skipping {os.path.basename(mp3_path)}, already extracted"))
                            self.messages.put(("done", item_id, existing, STATUS_SKIPPED))
                            continue

                    try:
                        if separator is None:
                            separator = load_separator(progress=reporter)

                        song_folder = extract_a_new_mp3_file(
                            mp3_path,
                            output_folder,
                            whisper_model=whisper_model,
                            audio_format=audio_format,
                            progress=reporter,
                            models=models,
                            separator=separator,
                        )
                        self.messages.put(("done", item_id, song_folder, STATUS_DONE))
                    except ExtractionCancelled:
                        self.messages.put(("status", item_id, STATUS_CANCELLED))
                        break
                    except Exception as error:
                        self.messages.put(("log", traceback.format_exc()))
                        self.messages.put(("status", item_id, f"{STATUS_FAILED}: {error}"))
                writer.flush()
        finally:
            models.free()
            self.messages.put(("finished",))

    def _cancel(self):
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.stage_var.set("cancelling")
            self._append_log("cancel requested, finishing the current step")

    # --- UI updates, main thread only
    def _drain_messages(self):
        if self._closing:
            return

        try:
            while True:
                message = self.messages.get_nowait()
                self._handle_message(message)
        except queue.Empty:
            pass
        finally:
            # Reschedule only while the window is alive, otherwise Tk reports the pending
            # callback as an invalid command once the root is destroyed
            if not self._closing:
                self._poll_id = self.root.after(POLL_INTERVAL_MS, self._drain_messages)

    def _handle_message(self, message):
        kind = message[0]

        if kind == "log":
            self._append_log(message[1])
        elif kind == "stage":
            _, item_id, name = message
            self.stage_var.set(name)
            self.progress.configure(value=0)
            self._set_status(item_id, name)
        elif kind == "percent":
            _, item_id, value = message
            self.progress.configure(value=value)
            self._set_status(item_id, f"{self.stage_var.get()} {value:.0f}%")
        elif kind == "position":
            _, position, total = message
            self.position_var.set(f"song {position} of {total}")
        elif kind == "status":
            self._set_status(message[1], message[2])
        elif kind == "done":
            _, item_id, folder, status = message
            self.results[item_id] = folder
            self._set_status(item_id, status)
        elif kind == "finished":
            self._on_finished()

    def _on_finished(self):
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.stage_var.set("idle")
        self.position_var.set("")
        self.progress.configure(value=0)

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")

        # Keep the pane bounded so a long batch cannot grow it without limit
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.log.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")

        self.log.see("end")
        self.log.configure(state="disabled")

    # --- finished song actions
    def _selected_folder(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Nothing selected", "Select a song in the queue first.")
            return None

        item_id = selection[0]
        folder = self.results.get(item_id)
        if not folder:
            # Not extracted in this session, but it may already exist on disk
            source = self.sources.get(item_id)
            if source:
                candidate = song_folder_for(source, self.output_var.get())
                if is_karaoke_folder(candidate):
                    folder = candidate

        if not folder:
            messagebox.showinfo("Not extracted yet", "That song has no extracted folder yet.")
            return None

        return folder

    def _play_selected(self):
        folder = self._selected_folder()
        if not folder:
            return
        self._append_log(f"launching player for {folder}")
        subprocess.Popen([sys.executable, "-m", "any_karaoke.main", folder])

    def _open_folder(self):
        folder = self._selected_folder()
        if not folder:
            return
        open_in_file_manager(folder)

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel("Quit", "Extraction is running. Cancel it and quit?"):
                return
            self.cancel_event.set()

        self.shutdown()
        self.root.destroy()

    def shutdown(self):
        """Stop the message poll so no callback fires after the root is destroyed."""
        self._closing = True
        if self._poll_id is not None:
            try:
                self.root.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None


def open_in_file_manager(path):
    """Reveal a folder in the platform file manager."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def main():
    root = tk.Tk()
    try:
        # Nicer default widget look on Windows
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass

    ExtractorWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
