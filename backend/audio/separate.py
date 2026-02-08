"""Stem separation using Demucs (via centrifugue's venv)."""

import subprocess
from pathlib import Path

# Path to centrifugue's Demucs virtual environment
DEMUCS_VENV = Path.home() / "Code" / "centrifugue" / "venv-demucs"
DEMUCS_PYTHON = DEMUCS_VENV / "bin" / "python"


def is_demucs_available() -> bool:
    return DEMUCS_PYTHON.is_file()


def separate_stems(audio_path: Path, output_dir: Path) -> dict[str, Path]:
    """Run Demucs on audio to produce separated stems.

    Uses the fast htdemucs model with WAV output for quality.

    Returns dict mapping stem name -> path, e.g.:
        {"vocals": ..., "drums": ..., "bass": ..., "other": ...}
    """
    if not is_demucs_available():
        raise RuntimeError(
            f"Demucs not found at {DEMUCS_PYTHON}. "
            "Install centrifugue or set up a Demucs venv."
        )

    cmd = [
        str(DEMUCS_PYTHON), "-m", "demucs",
        str(audio_path),
        "-n", "htdemucs",
        "-o", str(output_dir),
        "--two-stems=other",  # Only separate into other + rest (faster)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Demucs failed: {result.stderr.strip()}")

    # Find the output stems directory
    stems_dir = output_dir / "htdemucs" / audio_path.stem
    if not stems_dir.exists():
        # Search for any directory with wav/mp3 files
        for d in output_dir.rglob("*"):
            if d.is_dir() and (list(d.glob("*.wav")) or list(d.glob("*.mp3"))):
                stems_dir = d
                break
        else:
            raise RuntimeError(f"No stems found in {output_dir}")

    stems = {}
    for stem_file in stems_dir.iterdir():
        if stem_file.suffix in (".wav", ".mp3"):
            stems[stem_file.stem] = stem_file

    if not stems:
        raise RuntimeError(f"No audio files found in {stems_dir}")

    return stems
