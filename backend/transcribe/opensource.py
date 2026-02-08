"""Open-source transcription: Demucs separation → Basic Pitch → fret assignment → PyGuitarPro GP5."""

import logging
import tempfile
from io import BytesIO
from pathlib import Path

import guitarpro
import librosa
import numpy as np

from audio.separate import is_demucs_available, separate_stems
from transcribe.fret_assign import STANDARD_TUNING, assign_frets

log = logging.getLogger(__name__)

# Duration value constants (fractions of a whole note)
DURATION_VALUES = [1, 2, 4, 8, 16, 32, 64]
QUARTER_TIME = 960  # pyguitarpro quarter note time unit

# Basic Pitch parameters tuned for guitar in a full mix (drums, distortion).
# Lower thresholds catch chord tones that distortion harmonics obscure.
# Frequency limits exclude drum hits and non-guitar content.
ONSET_THRESHOLD = 0.3
FRAME_THRESHOLD = 0.15
MIN_NOTE_LENGTH_MS = 80
MIN_FREQUENCY_HZ = 75.0   # Just below E2 (~82 Hz)
MAX_FREQUENCY_HZ = 1400.0  # Above guitar's practical range

# Minimum amplitude to keep a note (filters ghost/phantom detections)
MIN_AMPLITUDE = 0.12


def _estimate_tempo(audio_path: str) -> tuple[float, np.ndarray]:
    """Estimate tempo using librosa beat tracking.

    Returns (tempo_bpm, beat_times_seconds).
    """
    y, sr = librosa.load(audio_path, sr=22050)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    if hasattr(tempo, "__len__"):
        tempo = float(tempo[0])
    else:
        tempo = float(tempo)

    # Refine tempo from actual beat intervals if we have enough beats
    if len(beat_times) > 4:
        intervals = np.diff(beat_times)
        median_interval = float(np.median(intervals))
        if median_interval > 0:
            tempo = 60.0 / median_interval

    return round(tempo), beat_times


def _closest_duration(seconds: float, tempo: float) -> int:
    """Find the closest standard note duration value for a given time span."""
    beats = seconds * tempo / 60.0  # Duration in quarter-note beats
    if beats <= 0:
        return 16  # Default to sixteenth

    ideal_value = 4.0 / beats
    return min(DURATION_VALUES, key=lambda v: abs(v - ideal_value))


def _quantize_to_grid(time_s: float, tempo: float) -> float:
    """Quantize a time value to the nearest sixteenth-note grid."""
    beat_duration = 60.0 / tempo
    sixteenth = beat_duration / 4
    return round(time_s / sixteenth) * sixteenth


async def transcribe_opensource(audio_path: Path, title: str) -> bytes:
    """Transcribe audio to GP5 using Demucs + Basic Pitch + PyGuitarPro."""
    from basic_pitch.inference import predict

    # 1. Estimate tempo from the full mix (drums give best beat tracking)
    tempo, beat_times = _estimate_tempo(str(audio_path))
    log.info("Estimated tempo: %d BPM", tempo)

    # 2. Separate stems with Demucs to isolate guitar ("other" stem)
    pitch_audio = audio_path  # fallback: use original if no Demucs
    stems_dir = None

    if is_demucs_available():
        log.info("Running Demucs stem separation...")
        stems_dir = Path(tempfile.mkdtemp(prefix="tabber_stems_"))
        try:
            stems = separate_stems(audio_path, stems_dir)
            if "other" in stems:
                pitch_audio = stems["other"]
                log.info("Using isolated 'other' stem for pitch detection")
            else:
                log.warning("No 'other' stem found, using full mix")
        except RuntimeError as e:
            log.warning("Demucs separation failed (%s), using full mix", e)
    else:
        log.warning("Demucs not available, transcribing from full mix")

    # 3. Run Basic Pitch on the isolated stem
    _model_output, _midi_data, note_events = predict(
        str(pitch_audio),
        onset_threshold=ONSET_THRESHOLD,
        frame_threshold=FRAME_THRESHOLD,
        minimum_note_length=MIN_NOTE_LENGTH_MS,
        minimum_frequency=MIN_FREQUENCY_HZ,
        maximum_frequency=MAX_FREQUENCY_HZ,
    )

    # Clean up stems temp dir
    if stems_dir:
        import shutil
        shutil.rmtree(stems_dir, ignore_errors=True)

    if not note_events:
        raise RuntimeError("No notes detected in the audio")

    # Filter out low-confidence detections
    cleaned_events = [
        (onset, offset, int(pitch), float(amp))
        for onset, offset, pitch, amp, *_ in note_events
        if float(amp) >= MIN_AMPLITUDE
    ]

    if not cleaned_events:
        raise RuntimeError("No confident notes detected in the audio")

    # 3. Assign frets
    fretted = assign_frets(cleaned_events)
    if not fretted:
        raise RuntimeError("No notes in guitar range detected")

    # 4. Quantize and group into measures (4/4 time)
    beat_duration = 60.0 / tempo
    measure_duration = beat_duration * 4  # 4/4 time

    # Group notes by measure
    measures_notes: dict[int, list] = {}
    for onset, offset, pos, amp in fretted:
        q_onset = _quantize_to_grid(onset, tempo)
        measure_idx = int(q_onset / measure_duration)
        if measure_idx not in measures_notes:
            measures_notes[measure_idx] = []
        measures_notes[measure_idx].append((q_onset, offset, pos, amp))

    if not measures_notes:
        raise RuntimeError("Failed to assign notes to measures")

    num_measures = max(measures_notes.keys()) + 1

    # 5. Build GP5 song
    song = guitarpro.models.Song()
    song.title = title
    song.tempo = int(tempo)

    # Set up guitar strings (standard tuning)
    strings = [
        guitarpro.models.GuitarString(number=s, value=v)
        for s, v in sorted(STANDARD_TUNING.items())
    ]

    # Create track
    track = song.tracks[0]
    track.name = "Guitar"
    track.strings = strings
    track.channel.instrument = 25  # Steel string acoustic guitar

    # Create measure headers for the song
    song.measureHeaders.clear()
    for i in range(num_measures):
        header = guitarpro.models.MeasureHeader()
        header.number = i + 1
        header.start = QUARTER_TIME + i * QUARTER_TIME * 4
        header.timeSignature = guitarpro.models.TimeSignature(
            numerator=4,
            denominator=guitarpro.models.Duration(value=4),
        )
        song.measureHeaders.append(header)

    # Create measures on the track
    track.measures.clear()
    for i, header in enumerate(song.measureHeaders):
        measure = guitarpro.models.Measure(track, header)
        voice = measure.voices[0]

        notes_in_measure = measures_notes.get(i, [])
        if not notes_in_measure:
            # Rest measure — add a single whole rest beat
            beat = guitarpro.models.Beat(voice, duration=guitarpro.models.Duration(value=1))
            beat.status = guitarpro.models.BeatStatus.rest
            voice.beats.append(beat)
        else:
            # Sort by onset time
            notes_in_measure.sort(key=lambda n: n[0])

            # Group simultaneous notes into chords
            chord_groups: list[list] = []
            current_group = [notes_in_measure[0]]
            for n in notes_in_measure[1:]:
                # Notes within a 32nd note of each other are a chord
                if abs(n[0] - current_group[0][0]) < (beat_duration / 8):
                    current_group.append(n)
                else:
                    chord_groups.append(current_group)
                    current_group = [n]
            chord_groups.append(current_group)

            for gi, group in enumerate(chord_groups):
                # Determine duration: use gap to next group, or note length
                onset = group[0][0]
                if gi + 1 < len(chord_groups):
                    next_onset = chord_groups[gi + 1][0][0]
                    dur_seconds = next_onset - onset
                else:
                    # Last group in measure: use note's own duration
                    offset = group[0][1]
                    dur_seconds = offset - onset

                dur_seconds = max(dur_seconds, beat_duration / 4)
                dur_value = _closest_duration(dur_seconds, tempo)
                duration = guitarpro.models.Duration(value=dur_value)

                beat = guitarpro.models.Beat(voice, duration=duration)
                beat.status = guitarpro.models.BeatStatus.normal

                # Track which strings are used in this beat to avoid duplicates
                used_strings = set()
                for _onset, _offset, pos, amp in group:
                    if pos.string in used_strings:
                        continue
                    used_strings.add(pos.string)

                    velocity = min(127, max(1, int(amp * 127)))
                    note = guitarpro.models.Note(beat)
                    note.value = pos.fret
                    note.string = pos.string
                    note.velocity = velocity
                    note.type = guitarpro.models.NoteType.normal
                    beat.notes.append(note)

                voice.beats.append(beat)

        track.measures.append(measure)

    # 6. Write to bytes
    buf = BytesIO()
    guitarpro.write(song, buf, version=(5, 1, 0))
    return buf.getvalue()
