"""Read basic audio tags and embedded cover art for PLY Lite."""
import base64
from io import BytesIO
from pathlib import Path


def read_metadata(filepath: Path) -> dict:
    path = Path(filepath)
    result = {
        "title": path.stem,
        "artist": "Unknown Artist",
        "cover_bytes": None,
    }

    try:
        import mutagen

        easy_audio = mutagen.File(path, easy=True)
        if easy_audio is not None and easy_audio.tags:
            title = easy_audio.tags.get("title")
            artist = easy_audio.tags.get("artist")
            if title:
                result["title"] = str(title[0])
            if artist:
                result["artist"] = str(artist[0])

        audio = mutagen.File(path)
        tags = getattr(audio, "tags", None)
        if audio is None or tags is None:
            return result

        # MP3 / ID3 cover art.
        if hasattr(tags, "getall"):
            pictures = tags.getall("APIC")
            if pictures:
                result["cover_bytes"] = pictures[0].data
                return result

        # FLAC cover art.
        pictures = getattr(audio, "pictures", None)
        if pictures:
            result["cover_bytes"] = pictures[0].data
            return result

        # Ogg Vorbis / Opus cover art (FLAC picture block or base64 image).
        if hasattr(tags, "get"):
            for field in ("metadata_block_picture", "coverart"):
                encoded_items = tags.get(field) or []
                if isinstance(encoded_items, str):
                    encoded_items = [encoded_items]
                for encoded in encoded_items:
                    try:
                        picture_data = base64.b64decode(encoded)
                        if field == "metadata_block_picture":
                            from mutagen.flac import Picture
                            picture_data = Picture(picture_data).data
                        if picture_data:
                            result["cover_bytes"] = picture_data
                            return result
                    except Exception:
                        continue

        # MP4 / M4A cover art.
        covers = tags.get("covr") if hasattr(tags, "get") else None
        if covers:
            result["cover_bytes"] = bytes(covers[0])
    except Exception:
        # Missing or malformed tags must not stop playback.
        pass

    return result


def image_from_bytes(data: bytes):
    """Return a Pillow image from cover bytes, or None for invalid data."""
    if not data:
        return None
    try:
        from PIL import Image

        image = Image.open(BytesIO(data))
        image.load()
        return image.convert("RGB")
    except Exception:
        return None
