"""Small GStreamer playback wrapper for PLY Lite."""
from pathlib import Path


class AudioPlayer:
    """Play one local audio file and expose basic playback controls."""

    def __init__(self):
        self.available = False
        self.error = None
        self.state = "stopped"
        self.pipeline = None
        self.bus = None
        self._gst = None

        try:
            import gi

            gi.require_version("Gst", "1.0")
            from gi.repository import Gst

            Gst.init(None)
            self._gst = Gst
            self.pipeline = Gst.ElementFactory.make("playbin", "ply-lite-player")
            if self.pipeline is None:
                raise RuntimeError("GStreamer could not create the playbin element.")
            self.bus = self.pipeline.get_bus()
            self.available = True
        except Exception as exc:  # Keep the GUI launchable so it can show a useful error.
            self.error = str(exc)

    def play(self, filepath: Path) -> None:
        if not self.available:
            raise RuntimeError(
                "GStreamer is not available. Install python3-gi and python3-gst-1.0."
            )

        path = Path(filepath).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)

        self.pipeline.set_state(self._gst.State.NULL)
        self.pipeline.set_property("uri", path.as_uri())
        result = self.pipeline.set_state(self._gst.State.PLAYING)
        if result == self._gst.StateChangeReturn.FAILURE:
            self.pipeline.set_state(self._gst.State.NULL)
            raise RuntimeError(f"GStreamer could not play: {path.name}")
        self.state = "playing"

    def pause(self) -> None:
        if self.available and self.state == "playing":
            self.pipeline.set_state(self._gst.State.PAUSED)
            self.state = "paused"

    def resume(self) -> None:
        if self.available and self.state == "paused":
            self.pipeline.set_state(self._gst.State.PLAYING)
            self.state = "playing"

    def stop(self) -> None:
        if self.available:
            self.pipeline.set_state(self._gst.State.NULL)
        self.state = "stopped"

    def seek(self, seconds: float) -> None:
        if not self.available or self.state == "stopped":
            return
        target = max(0.0, float(seconds))
        self.pipeline.seek_simple(
            self._gst.Format.TIME,
            self._gst.SeekFlags.FLUSH | self._gst.SeekFlags.KEY_UNIT,
            int(target * self._gst.SECOND),
        )

    def get_position_duration(self) -> tuple[float, float]:
        if not self.available or self.state == "stopped":
            return 0.0, 0.0

        position_ok, position = self.pipeline.query_position(self._gst.Format.TIME)
        duration_ok, duration = self.pipeline.query_duration(self._gst.Format.TIME)
        current = position / self._gst.SECOND if position_ok else 0.0
        total = duration / self._gst.SECOND if duration_ok else 0.0
        return current, total

    def poll(self):
        """Return None, 'eos', or ('error', message) without blocking the GUI."""
        if not self.available or self.bus is None:
            return None

        message_types = self._gst.MessageType.EOS | self._gst.MessageType.ERROR
        while True:
            message = self.bus.pop_filtered(message_types)
            if message is None:
                return None
            if message.type == self._gst.MessageType.EOS:
                self.state = "stopped"
                self.pipeline.set_state(self._gst.State.NULL)
                return "eos"
            if message.type == self._gst.MessageType.ERROR:
                error, debug = message.parse_error()
                self.state = "stopped"
                self.pipeline.set_state(self._gst.State.NULL)
                detail = str(error)
                if debug:
                    detail = f"{detail}\n{debug}"
                return "error", detail

    def close(self) -> None:
        self.stop()
