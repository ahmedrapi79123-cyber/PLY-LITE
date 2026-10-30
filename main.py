"""PLY Lite - a minimal, folder-based music player."""
from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from metadata import image_from_bytes, read_metadata
from player import AudioPlayer

APP_NAME = "PLY Lite"
SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac", ".opus", ".m4a", ".aac",
}
BACKGROUND = "#F1F1F4"
PANEL = "#FAFAFB"
DARK = "#202333"
MUTED = "#8990A5"
PURPLE = "#7354E8"
TRACK = "#E3E4EA"


def format_time(seconds: float) -> str:
    value = max(0, int(seconds))
    return f"{value // 60:02d}:{value % 60:02d}"


def songs_in_same_folder(filepath: Path) -> list[Path]:
    """Return supported audio files directly inside filepath's folder only."""
    folder = filepath.parent
    songs = [
        item.resolve()
        for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    songs.sort(key=lambda item: item.name.casefold())
    selected = filepath.resolve()
    if selected not in songs:
        songs.append(selected)
        songs.sort(key=lambda item: item.name.casefold())
    return songs


class PLYLiteApp:
    def __init__(self, root: tk.Tk, initial_file: Path | None = None):
        self.root = root
        self.player = AudioPlayer()
        self.tracks: list[Path] = []
        self.current_index = -1
        self.duration = 0.0
        self.dragging_seek = False
        self.cover_source = None
        self.cover_photo = None
        self.cover_item = None
        self._warning_after_id = None

        self.root.title(APP_NAME)
        self.root.geometry("1040x620")
        self.root.minsize(820, 500)
        self.root.configure(bg=BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Control-o>", lambda _event: self.open_dialog())
        self.root.bind("<space>", lambda _event: self.toggle_playback())
        self.root.bind("<Left>", lambda _event: self.previous_track())
        self.root.bind("<Right>", lambda _event: self.next_track())

        self._build_interface()
        self.root.after(250, self._update_playback)

        if initial_file:
            self.root.after(150, lambda: self.open_path(initial_file))
        elif not self.player.available:
            self._warning_after_id = self.root.after(300, self._show_gstreamer_error)

    def _build_interface(self):
        self.shell = tk.Frame(
            self.root,
            bg=PANEL,
            highlightbackground="#D9DBE3",
            highlightthickness=1,
        )
        self.shell.pack(fill="both", expand=True, padx=22, pady=22)
        self.shell.grid_columnconfigure(0, weight=54, minsize=390)
        self.shell.grid_columnconfigure(1, weight=46, minsize=300)
        self.shell.grid_rowconfigure(0, weight=1)

        self.left = tk.Frame(self.shell, bg=PANEL)
        self.left.grid(row=0, column=0, sticky="nsew")
        self.left.grid_columnconfigure(0, weight=1)
        self.left.grid_rowconfigure(1, weight=1)

        self.cover_canvas = tk.Canvas(
            self.shell, bg="#110D22", bd=0, highlightthickness=0
        )
        self.cover_canvas.grid(row=0, column=1, sticky="nsew", padx=(0, 5), pady=5)
        self.cover_canvas.bind("<Configure>", self._draw_cover)

        self._build_header()
        self._build_player_controls()
        self._load_default_cover()

    def _build_header(self):
        header = tk.Frame(self.left, bg=PANEL)
        header.pack(fill="x", padx=28, pady=(24, 0))

        menu = tk.Button(
            header, text="☰", command=self._show_menu,
            font=("DejaVu Sans", 17), fg=MUTED, bg=PANEL,
            activeforeground=PURPLE, activebackground=PANEL,
            relief="flat", bd=0, cursor="hand2", padx=5,
        )
        menu.pack(side="left")

        brand = tk.Frame(header, bg=PANEL)
        brand.pack(side="left", padx=(17, 0))
        tk.Label(
            brand, text="PLY", font=("DejaVu Sans", 17, "bold"),
            fg=DARK, bg=PANEL,
        ).pack(side="left")
        tk.Label(
            brand, text="Lite", font=("DejaVu Sans", 17),
            fg=PURPLE, bg=PANEL,
        ).pack(side="left")

    def _build_player_controls(self):
        center = tk.Frame(self.left, bg=PANEL)
        center.pack(fill="both", expand=True, padx=42, pady=(18, 34))

        info = tk.Frame(center, bg=PANEL)
        info.pack(fill="both", expand=True)

        self.title_label = tk.Label(
            info, text="Open a song to start listening",
            font=("DejaVu Sans", 23, "bold"), fg=DARK,
            bg=PANEL, wraplength=440, justify="center",
        )
        self.title_label.pack(expand=True, pady=(65, 6))

        self.artist_label = tk.Label(
            info, text="PLY Lite", font=("DejaVu Sans", 14),
            fg=MUTED, bg=PANEL,
        )
        self.artist_label.pack(pady=(0, 40))

        progress = tk.Frame(center, bg=PANEL)
        progress.pack(fill="x", pady=(0, 0))
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "PLY.Horizontal.TScale",
            background=PANEL,
            troughcolor=TRACK,
            sliderthickness=13,
            borderwidth=0,
        )
        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_scale = ttk.Scale(
            progress, from_=0, to=100, orient="horizontal",
            variable=self.seek_var, command=self._on_seek,
            style="PLY.Horizontal.TScale",
        )
        self.seek_scale.pack(fill="x")
        self.seek_scale.bind("<ButtonPress-1>", self._seek_started)
        self.seek_scale.bind("<ButtonRelease-1>", self._seek_finished)

        times = tk.Frame(progress, bg=PANEL)
        times.pack(fill="x", pady=(7, 0))
        self.elapsed_label = tk.Label(
            times, text="00:00", font=("DejaVu Sans", 10),
            fg=MUTED, bg=PANEL,
        )
        self.elapsed_label.pack(side="left")
        self.total_label = tk.Label(
            times, text="00:00", font=("DejaVu Sans", 10),
            fg=MUTED, bg=PANEL,
        )
        self.total_label.pack(side="right")

        controls = tk.Frame(center, bg=PANEL)
        controls.pack(fill="x", pady=(30, 0))
        controls.grid_columnconfigure((0, 1, 2), weight=1)

        self.previous_button = self._control_button(controls, "|◀", self.previous_track)
        self.previous_button.grid(row=0, column=0)

        self.play_canvas = tk.Canvas(
            controls, width=88, height=88, bg=PANEL,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.play_canvas.grid(row=0, column=1)
        self.play_canvas.create_oval(
            7, 7, 81, 81, outline=PURPLE, width=2, tags="play_button"
        )
        self.play_glyph = self.play_canvas.create_text(
            44, 44, text="▶", fill=PURPLE,
            font=("DejaVu Sans", 24, "bold"), tags="play_button",
        )
        self.play_canvas.bind("<Button-1>", lambda _event: self.toggle_playback())
        self.next_button = self._control_button(controls, "▶|", self.next_track)
        self.next_button.grid(row=0, column=2)

    @staticmethod
    def _control_button(parent, text, command):
        return tk.Button(
            parent, text=text, command=command,
            font=("DejaVu Sans", 20, "bold"), fg=PURPLE,
            bg=PANEL, activeforeground=PURPLE, activebackground=PANEL,
            relief="flat", bd=0, cursor="hand2", padx=8, pady=8,
        )

    def _show_menu(self):
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Open song…", accelerator="Ctrl+O", command=self.open_dialog)
        menu.add_separator()
        menu.add_command(label="Quit", command=self.close)
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def open_dialog(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Open an audio file",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.ogg *.flac *.opus *.m4a *.aac"),
                ("All files", "*"),
            ],
        )
        if filename:
            self.open_path(Path(filename))

    def open_path(self, filepath: Path):
        path = Path(filepath).expanduser()
        if not path.is_file():
            messagebox.showerror(APP_NAME, "The selected audio file could not be found.")
            return
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            messagebox.showerror(APP_NAME, "This audio format is not supported by PLY Lite.")
            return

        try:
            new_tracks = songs_in_same_folder(path)
            new_index = new_tracks.index(path.resolve())
            self.player.play(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open this song:\n{exc}")
            return

        self.tracks = new_tracks
        self.current_index = new_index
        self._show_track(path)

    def _show_track(self, filepath: Path):
        details = read_metadata(filepath)
        self.title_label.configure(text=details["title"])
        self.artist_label.configure(text=details["artist"])
        self.root.title(f"{details['title']} — {APP_NAME}")
        self.duration = 0.0
        self.seek_var.set(0.0)
        self.elapsed_label.configure(text="00:00")
        self.total_label.configure(text="00:00")
        self._set_play_icon(playing=True)

        self.cover_source = image_from_bytes(details.get("cover_bytes"))
        if self.cover_source is None:
            self._load_default_cover()
        else:
            self._draw_cover()

    def _load_default_cover(self):
        from PIL import Image

        default_path = Path(__file__).parent / "assets" / "default_cover.png"
        try:
            self.cover_source = Image.open(default_path).convert("RGB")
        except Exception:
            self.cover_source = Image.new("RGB", (700, 700), "#17102B")
        self._draw_cover()

    def _draw_cover(self, _event=None):
        if self.cover_source is None:
            return
        width = max(1, self.cover_canvas.winfo_width())
        height = max(1, self.cover_canvas.winfo_height())
        try:
            from PIL import Image, ImageTk, ImageOps

            image = ImageOps.fit(
                self.cover_source,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            self.cover_photo = ImageTk.PhotoImage(image)
            self.cover_canvas.delete("cover")
            self.cover_canvas.create_image(
                width // 2, height // 2, image=self.cover_photo,
                anchor="center", tags="cover",
            )
        except Exception:
            self.cover_canvas.configure(bg="#17102B")

    def toggle_playback(self):
        if not self.tracks or self.current_index < 0:
            self.open_dialog()
            return
        try:
            if self.player.state == "playing":
                self.player.pause()
                self._set_play_icon(playing=False)
            elif self.player.state == "paused":
                self.player.resume()
                self._set_play_icon(playing=True)
            else:
                self.player.play(self.tracks[self.current_index])
                self._set_play_icon(playing=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Playback error:\n{exc}")

    def _set_play_icon(self, playing: bool):
        self.play_canvas.itemconfigure(self.play_glyph, text="Ⅱ" if playing else "▶")

    def previous_track(self):
        if not self.tracks:
            return
        index = (self.current_index - 1) % len(self.tracks)
        self._play_index(index)

    def next_track(self, automatic: bool = False):
        if not self.tracks:
            return
        if automatic and self.current_index >= len(self.tracks) - 1:
            self._set_play_icon(playing=False)
            self.seek_var.set(0.0)
            self.elapsed_label.configure(text="00:00")
            return
        index = (self.current_index + 1) % len(self.tracks)
        self._play_index(index)

    def _play_index(self, index: int):
        filepath = self.tracks[index]
        try:
            self.player.play(filepath)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not play {filepath.name}:\n{exc}")
            return
        self.current_index = index
        self._show_track(filepath)

    def _seek_started(self, _event):
        self.dragging_seek = True

    def _seek_finished(self, _event):
        self.dragging_seek = False
        self.player.seek(self.seek_var.get())

    def _on_seek(self, value):
        if self.dragging_seek:
            self.elapsed_label.configure(text=format_time(float(value)))

    def _update_playback(self):
        event = self.player.poll()
        if event == "eos":
            self.next_track(automatic=True)
        elif isinstance(event, tuple) and event[0] == "error":
            self._set_play_icon(playing=False)
            messagebox.showerror(APP_NAME, f"Playback error:\n{event[1]}")

        if self.player.state != "stopped":
            position, duration = self.player.get_position_duration()
            if duration > 0:
                self.duration = duration
                self.seek_scale.configure(to=duration)
                if not self.dragging_seek:
                    self.seek_var.set(min(position, duration))
                    self.elapsed_label.configure(text=format_time(position))
                self.total_label.configure(text=format_time(duration))
        self.root.after(250, self._update_playback)

    def _show_gstreamer_error(self):
        self._warning_after_id = None
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        messagebox.showwarning(
            APP_NAME,
            "Audio playback needs GStreamer.\n\n"
            "Install python3-gi and python3-gst-1.0, then reopen PLY Lite.\n\n"
            f"Details: {self.player.error}",
        )

    def close(self):
        if self._warning_after_id is not None:
            try:
                self.root.after_cancel(self._warning_after_id)
            except tk.TclError:
                pass
            self._warning_after_id = None
        self.player.close()
        self.root.destroy()


def main():
    initial_file = None
    for argument in sys.argv[1:]:
        candidate = Path(argument).expanduser()
        if candidate.is_file():
            initial_file = candidate
            break

    root = tk.Tk()
    PLYLiteApp(root, initial_file=initial_file)
    root.mainloop()


if __name__ == "__main__":
    main()
