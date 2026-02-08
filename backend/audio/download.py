import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _find_ytdlp() -> str:
    """Find yt-dlp binary, preferring the one in the current venv."""
    venv_bin = Path(sys.executable).parent / "yt-dlp"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("yt-dlp")
    if found:
        return found
    raise RuntimeError("yt-dlp not found")


def download_audio(url: str) -> Path:
    """Download audio from a URL as WAV using yt-dlp.

    Returns the path to the downloaded WAV file in a temp directory.
    Caller is responsible for cleanup.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="tabber_"))
    output_template = str(tmp_dir / "audio.%(ext)s")

    cmd = [
        _find_ytdlp(),
        "--extract-audio",
        "--audio-format", "wav",
        "--output", output_template,
        "--no-playlist",
        "--extractor-args", "youtube:player_client=web",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()}")

    wav_path = tmp_dir / "audio.wav"
    if not wav_path.exists():
        # yt-dlp may have named it differently; find any wav
        wavs = list(tmp_dir.glob("*.wav"))
        if not wavs:
            raise RuntimeError(f"No WAV file produced. yt-dlp output: {result.stderr.strip()}")
        wav_path = wavs[0]

    return wav_path


def convert_webm_to_wav(webm_path: Path) -> Path:
    """Convert a WebM audio file to WAV using ffmpeg.

    Returns the path to the WAV file (same directory, different extension).
    """
    wav_path = webm_path.with_suffix(".wav")

    cmd = [
        "ffmpeg",
        "-i", str(webm_path),
        "-ar", "44100",
        "-ac", "1",
        "-y",
        str(wav_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.strip()}")

    return wav_path
