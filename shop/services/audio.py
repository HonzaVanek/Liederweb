import subprocess
import tempfile
from pathlib import Path

from django.core.files import File


PREVIEW_DURATION_SECONDS = 30


class AudioProcessingError(Exception):
    pass


def _get_audio_duration(file_path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise AudioProcessingError(
            "Nepodařilo se zjistit délku MP3 pomocí ffprobe."
        ) from exc

    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise AudioProcessingError(
            "ffprobe vrátil neplatnou délku audio souboru."
        ) from exc


def generate_track_preview(track):
    if not track.full_audio:
        raise AudioProcessingError(
            "Stopa nemá nahranou plnou MP3."
        )

    full_audio_path = Path(track.full_audio.path)

    duration = _get_audio_duration(full_audio_path)

    preview_start = track.preview_start_seconds

    if preview_start >= duration:
        raise AudioProcessingError(
            "Začátek ukázky je až za koncem skladby."
        )

    track.duration_seconds = round(duration)

    preview_filename = (
        f"track-{track.pk}-preview.mp3"
    )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(preview_start),
                "-i",
                str(full_audio_path),
                "-t",
                str(PREVIEW_DURATION_SECONDS),
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "4",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Při regeneraci odstraníme staré preview.
        if track.preview_audio:
            track.preview_audio.delete(
                save=False,
            )

        with temp_path.open("rb") as preview_file:
            track.preview_audio.save(
                preview_filename,
                File(preview_file),
                save=False,
            )

        track.save(
            update_fields=[
                "duration_seconds",
                "preview_audio",
            ]
        )

    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise AudioProcessingError(
            "Nepodařilo se vytvořit 30sekundovou ukázku."
        ) from exc

    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()