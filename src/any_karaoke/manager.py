"""Any Karaoke manager: the window for building and managing a karaoke library.

Extraction runs on a worker thread and talks to the UI through a queue. Tk is not thread
safe, so the worker never touches a widget: it only puts messages on self.messages, and
the UI drains them from a root.after poll.
"""

import argparse
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

from any_karaoke.assets import icon_path
from any_karaoke.extractor import (
    ExtractionCancelled,
    ProgressReporter,
    WhisperModels,
    extract_a_new_mp3_file,
    load_separator,
    song_file_for,
)
from any_karaoke.game_config import (
    MP3_BITRATE,
    OUTPUT_AUDIO_FORMAT,
    WHISPER_MODEL,
    WHISPER_MODEL_CHOICES,
)
from any_karaoke.lyrics_edit import apply_corrected_lyrics, describe_timing, read_editable_lyrics
from any_karaoke.processes import launch_module
from any_karaoke.song_files import AK_EXTENSION, is_song, read_lyrics_alignment, song_display_name

PLAYER_MODULE = "any_karaoke.main"
POLL_INTERVAL_MS = 100
MAX_LOG_LINES = 2000
HEADER_LOGO_SIZE = 42

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
class ManagerWindow:
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
        # tree item id -> lyrics the user pasted for that song, used instead of the lookup
        self.pasted_lyrics = {}

        root.title("Any Karaoke Manager")
        root.geometry("900x720")
        root.minsize(760, 600)
        # Held on the instance, otherwise Tk lets the image be collected and shows nothing
        self.icon_image = apply_window_icon(root)

        self.output_var = tk.StringVar(value=output_folder or os.path.join(os.getcwd(), "karaoke_tracks"))
        self.model_var = tk.StringVar(value=WHISPER_MODEL)
        self.format_var = tk.StringVar(value=self._label_for_format(OUTPUT_AUDIO_FORMAT))
        self.skip_var = tk.BooleanVar(value=True)
        self.stage_var = tk.StringVar(value="idle")
        self.position_var = tk.StringVar(value="")

        self._build_header(root)
        self._build_settings(root)
        self._build_queue(root)
        self._build_progress(root)
        self._build_actions(root)
        self._build_log(root)

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_id = self.root.after(POLL_INTERVAL_MS, self._drain_messages)

    # --- layout
    def _build_header(self, root):
        frame = ttk.Frame(root, padding=(8, 8, 8, 0))
        frame.pack(fill="x")

        self.header_image = load_logo_image(HEADER_LOGO_SIZE)
        if self.header_image is not None:
            ttk.Label(frame, image=self.header_image).pack(side="left", padx=(0, 10))

        ttk.Label(frame, text="Any Karaoke", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(frame, text="build your karaoke library", foreground="#666").pack(side="left", padx=(10, 0))

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

        columns = ("song", "lyrics", "status")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("song", text="Song")
        self.tree.heading("lyrics", text="Lyrics")
        self.tree.heading("status", text="Status")
        self.tree.column("song", width=440, anchor="w")
        self.tree.column("lyrics", width=90, anchor="w")
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
        ttk.Button(buttons, text="Paste lyrics", command=self._paste_lyrics).pack(side="left", padx=(18, 0))
        ttk.Button(buttons, text="Edit lyrics", command=self._edit_lyrics).pack(side="left", padx=6)

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
            item_id = self.tree.insert("", "end", values=(os.path.basename(path), "", STATUS_QUEUED))
            self.sources[item_id] = path

    def _remove_selected(self):
        if self._busy():
            return
        for item_id in self.tree.selection():
            self.tree.delete(item_id)
            self.sources.pop(item_id, None)
            self.results.pop(item_id, None)
            self.pasted_lyrics.pop(item_id, None)

    def _clear_queue(self):
        if self._busy():
            return
        for item_id in list(self.sources):
            self.tree.delete(item_id)
        self.sources.clear()
        self.results.clear()
        self.pasted_lyrics.clear()

    def _paste_lyrics(self):
        """Attach hand written lyrics to the selected song, used instead of the lookup."""
        if self._busy():
            return

        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Nothing selected", "Select a song in the queue first.")
            return

        item_id = selection[0]
        song_name = self.tree.set(item_id, "song")
        result = ask_for_lyrics(self.root, song_name, self.pasted_lyrics.get(item_id, ""))

        if result is None:  # cancelled
            return

        if result.strip():
            self.pasted_lyrics[item_id] = result
            self._append_log(f"pasted lyrics attached to {song_name} ({len(result.splitlines())} lines)")
        else:
            self.pasted_lyrics.pop(item_id, None)
            self._append_log(f"pasted lyrics cleared for {song_name}, the internet lookup will be used")

        self._set_lyrics_marker(item_id)

    def edit_lyrics_for(self, song_path):
        """Open the editor on a finished song."""
        if not is_song(song_path):
            messagebox.showerror("Not a song", f"'{song_path}' is not an Any Karaoke file.")
            return None
        return LyricsEditor(self.root, song_path)

    def _edit_lyrics(self):
        """Edit the selected finished song, or ask for a .ak when nothing is queued."""
        if self._busy():
            return

        song_path = self._selected_song(quiet=True) or filedialog.askopenfilename(
            title="Choose a song to edit",
            filetypes=[("Any Karaoke song", f"*{AK_EXTENSION}"), ("All files", "*.*")],
        )
        if song_path:
            self.edit_lyrics_for(song_path)

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
            self.tree.set(item_id, "status", status)

    def _set_lyrics_marker(self, item_id):
        if self.tree.exists(item_id):
            self.tree.set(item_id, "lyrics", "custom" if self.pasted_lyrics.get(item_id) else "")

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
            args=(
                jobs,
                output_folder,
                self.model_var.get(),
                self.audio_format,
                self.skip_var.get(),
                # A snapshot, so the worker never reads UI state while it is being edited
                dict(self.pasted_lyrics),
            ),
            daemon=True,
        )
        self.worker.start()

    def _run_queue(self, jobs, output_folder, whisper_model, audio_format, skip_existing, pasted_lyrics=None):
        """Worker thread. Only communicates through self.messages."""
        writer = QueueWriter(self.messages)
        models = WhisperModels(whisper_model)
        separator = None
        pasted_lyrics = pasted_lyrics or {}

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
                        existing = song_file_for(mp3_path, output_folder)
                        if is_song(existing):
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
                            lyrics_text=pasted_lyrics.get(item_id),
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
    def _selected_song(self, quiet=False):
        """The finished song for the selected row, or None. quiet skips the complaints."""
        selection = self.tree.selection()
        if not selection:
            if not quiet:
                messagebox.showinfo("Nothing selected", "Select a song in the queue first.")
            return None

        item_id = selection[0]
        folder = self.results.get(item_id)
        if not folder:
            # Not extracted in this session, but it may already exist on disk
            source = self.sources.get(item_id)
            if source:
                candidate = song_file_for(source, self.output_var.get())
                if is_song(candidate):
                    folder = candidate

        if not folder:
            if not quiet:
                messagebox.showinfo("Not extracted yet", "That song has no extracted file yet.")
            return None

        return folder

    def _play_selected(self):
        folder = self._selected_song()
        if not folder:
            return
        self._append_log(f"launching player for {folder}")
        launch_module(PLAYER_MODULE, folder)

    def _open_folder(self):
        folder = self._selected_song()
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


class LyricsEditor:
    """Correct the lyrics of an extracted song and redo their timings.

    Saving re-matches, which is instant. Re-align force-aligns the corrected words against
    the vocals for exact timings, which takes seconds and needs the extract extra, so it
    runs on a worker thread rather than freezing the window behind a model download.
    """

    def __init__(self, parent, song_path):
        self.song_path = song_path
        self.messages = queue.Queue()
        self.worker = None
        self._poll_id = None
        self.saved = False

        self.window = tk.Toplevel(parent)
        self.window.title(f"Lyrics: {song_display_name(song_path)}")
        self.window.geometry("680x600")
        self.window.transient(parent)

        ttk.Label(
            self.window,
            text="One line per lyric line, blank lines between verses.\n"
            "Save re-matches the timings. Re-align listens to the vocals for exact ones.",
            padding=8,
            justify="left",
        ).pack(fill="x")

        self.text_box = ScrolledText(self.window, wrap="word", undo=True)
        self.text_box.pack(fill="both", expand=True, padx=8)
        self.text_box.insert("1.0", read_editable_lyrics(song_path))
        self.text_box.focus_set()

        self.status = tk.StringVar(value=describe_timing((read_lyrics_alignment(song_path) or {}).get("timing")))
        ttk.Label(self.window, textvariable=self.status, padding=(8, 6)).pack(fill="x")

        buttons = ttk.Frame(self.window, padding=8)
        buttons.pack(fill="x")
        self.save_button = ttk.Button(buttons, text="Save", command=self._save)
        self.save_button.pack(side="right")
        self.realign_button = ttk.Button(buttons, text="Save and re-align", command=self._save_and_realign)
        self.realign_button.pack(side="right", padx=6)
        ttk.Button(buttons, text="Close", command=self.close).pack(side="left")

        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_id = self.window.after(POLL_INTERVAL_MS, self._drain)

    @property
    def lyrics(self):
        return self.text_box.get("1.0", "end-1c")

    # --- actions
    def _save(self):
        self._run(realign=False)

    def _save_and_realign(self):
        self._run(realign=True)

    def _run(self, realign):
        if self.worker and self.worker.is_alive():
            return

        if not self.lyrics.strip():
            messagebox.showinfo("No lyrics", "Type some lyrics before saving.")
            return

        self._set_busy(True)
        self.status.set("aligning against the vocals, this can take a while the first time" if realign else "saving")
        self.worker = threading.Thread(target=self._work, args=(self.lyrics, realign), daemon=True)
        self.worker.start()

    def _work(self, text, realign):
        """Worker thread. Only communicates through self.messages."""
        try:
            summary = apply_corrected_lyrics(self.song_path, text, realign=realign)
            self.messages.put(("done", describe_timing(summary)))
        except Exception as error:
            self.messages.put(("failed", f"{type(error).__name__}: {error}"))

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.save_button.configure(state=state)
        self.realign_button.configure(state=state)

    # --- UI thread
    def _drain(self):
        if self._poll_id is None:
            return

        try:
            while True:
                kind, payload = self.messages.get_nowait()
                self._set_busy(False)
                if kind == "done":
                    self.saved = True
                    self.status.set(f"saved: {payload}")
                else:
                    self.status.set(payload)
                    messagebox.showerror("Could not save", payload)
        except queue.Empty:
            pass

        if self._poll_id is not None:
            self._poll_id = self.window.after(POLL_INTERVAL_MS, self._drain)

    def close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel("Busy", "Alignment is still running. Close anyway?"):
                return

        if self._poll_id is not None:
            try:
                self.window.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None

        self.window.destroy()


def load_logo_image(size=None):
    """A Tk image of the logo, optionally shrunk by an integer factor. None if missing.

    Tk's PhotoImage only subsamples by whole numbers, so the requested size is met as
    closely as that allows rather than exactly.
    """
    path = icon_path()
    if not path:
        return None

    try:
        image = tk.PhotoImage(file=path)
    except tk.TclError:
        return None

    if size:
        factor = max(1, round(image.height() / size))
        if factor > 1:
            image = image.subsample(factor, factor)

    return image


def apply_window_icon(window):
    """Set the window and taskbar icon. Returns the image, which must be kept alive."""
    image = load_logo_image()
    if image is None:
        return None

    try:
        window.iconphoto(True, image)
    except tk.TclError:
        return None

    return image


def ask_for_lyrics(parent, song_name, initial=""):
    """Modal text box for pasting lyrics. Returns the text, or None when cancelled.

    An empty result means the user cleared them, which is different from cancelling.
    """
    dialog = tk.Toplevel(parent)
    dialog.title(f"Lyrics for {song_name}")
    dialog.geometry("620x520")
    dialog.transient(parent)

    ttk.Label(
        dialog,
        text="Paste the lyrics, one line per line. Blank lines separate verses.\n"
        "Leave empty to fall back to the internet lookup.",
        padding=8,
        justify="left",
    ).pack(fill="x")

    text_box = ScrolledText(dialog, wrap="word", undo=True)
    text_box.pack(fill="both", expand=True, padx=8)
    text_box.insert("1.0", initial)
    text_box.focus_set()

    answer = {"value": None}

    def save():
        answer["value"] = text_box.get("1.0", "end-1c")
        dialog.destroy()

    def clear():
        text_box.delete("1.0", "end")

    buttons = ttk.Frame(dialog, padding=8)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Save", command=save).pack(side="right")
    ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=6)
    ttk.Button(buttons, text="Clear", command=clear).pack(side="left")

    dialog.grab_set()
    parent.wait_window(dialog)

    return answer["value"]


def open_in_file_manager(path):
    """Reveal a song in the platform file manager.

    A song is a single .ak file, so the containing folder is opened with the file
    selected rather than trying to open the song itself.
    """
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build and manage an Any Karaoke library.")
    parser.add_argument("--edit", metavar="SONG", help="open the lyrics editor on a .ak file")
    parser.add_argument("--output", metavar="FOLDER", help="folder new songs are extracted into")
    args = parser.parse_args(argv)

    root = tk.Tk()
    try:
        # Nicer default widget look on Windows
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass

    window = ManagerWindow(root, output_folder=args.output)
    if args.edit:
        window.edit_lyrics_for(args.edit)
    root.mainloop()


if __name__ == "__main__":
    main()
