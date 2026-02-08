"""Map MIDI pitches to guitar string/fret pairs minimizing hand movement."""

from dataclasses import dataclass

# Standard guitar tuning: string number (1=high E) -> open string MIDI pitch
STANDARD_TUNING = {
    1: 64,  # E4
    2: 59,  # B3
    3: 55,  # G3
    4: 50,  # D3
    5: 45,  # A2
    6: 40,  # E2
}

MAX_FRET = 22


@dataclass
class FretPosition:
    string: int  # 1-6
    fret: int    # 0-22


def get_possible_positions(midi_pitch: int) -> list[FretPosition]:
    """Return all valid (string, fret) pairs for a MIDI pitch."""
    positions = []
    for string_num, open_pitch in STANDARD_TUNING.items():
        fret = midi_pitch - open_pitch
        if 0 <= fret <= MAX_FRET:
            positions.append(FretPosition(string=string_num, fret=fret))
    return positions


def assign_frets(
    note_events: list[tuple[float, float, int, float]],
) -> list[tuple[float, float, FretPosition, float]]:
    """Assign string/fret positions to note events using a greedy approach.

    Args:
        note_events: List of (onset, offset, midi_pitch, amplitude) tuples.

    Returns:
        List of (onset, offset, FretPosition, amplitude) tuples.
    """
    if not note_events:
        return []

    result = []
    last_fret = 5  # Start around a comfortable mid-range position

    # Sort by onset time
    sorted_events = sorted(note_events, key=lambda e: (e[0], e[2]))

    for onset, offset, pitch, amp in sorted_events:
        positions = get_possible_positions(pitch)
        if not positions:
            # Pitch out of guitar range — skip
            continue

        # Pick position closest to last used fret (minimize hand movement)
        best = min(positions, key=lambda p: abs(p.fret - last_fret))
        if best.fret > 0:
            last_fret = best.fret

        result.append((onset, offset, best, amp))

    return result
