# Tabber

Chrome extension + local Python backend that captures guitar audio from browser tabs and converts it to Guitar Pro tablature (.gp5 files).

## Architecture

```
Chrome Extension (MV3)          Local Python Backend (FastAPI)
┌─────────────────────┐         ┌──────────────────────────────┐
│ Popup UI            │         │ POST /transcribe/url         │
│  - URL mode button  │───────→│   yt-dlp download + transcribe│
│  - Record mode btn  │         │                              │
│                     │         │ POST /transcribe/audio       │
├─────────────────────┤         │   WebM upload + transcribe   │
│ Service Worker      │         │                              │
│  - tab info         │         │ GET /health                  │
│  - stream ID mgmt   │         ├──────────────────────────────┤
├─────────────────────┤         │ Transcription Engines:       │
│ Offscreen Document  │         │  1. Klangio API (primary)    │
│  - MediaRecorder    │         │  2. Basic Pitch + PyGuitarPro│
│  - audio capture    │         │     (open-source fallback)   │
└─────────────────────┘         └──────────────────────────────┘
```

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (or pip)
- ffmpeg (system install)
- Chrome browser

### Backend

```bash
cd backend
uv sync          # or: pip install .
uvicorn main:app --port 8765
```

### Configuration

Create `backend/.env` or set environment variables:

| Variable | Default | Description |
|---|---|---|
| `KLANGIO_API_KEY` | (empty) | API key for Klangio engine |
| `DEFAULT_ENGINE` | `klangio` | `klangio` or `opensource` |
| `PORT` | `8765` | Backend server port |

### Chrome Extension

1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked** → select the `extension/` directory

## Usage

1. Start the backend server
2. Navigate to a tab with guitar audio (e.g. a YouTube guitar video)
3. Click the Tabber extension icon
4. Choose an engine and either:
   - **Transcribe from URL** — sends the page URL to the backend (works with YouTube, etc.)
   - **Record Tab Audio** — captures live audio from the tab, then transcribes when stopped
5. A `.gp5` file downloads automatically, named after the tab title

## Transcription Engines

**Klangio** — Commercial API with high accuracy. Requires an API key from [klang.io](https://klang.io/api/).

**Open-source** — Uses [Basic Pitch](https://github.com/spotify/basic-pitch) for audio-to-MIDI detection, custom fret assignment, and [PyGuitarPro](https://github.com/Perlence/PyGuitarPro) for GP5 generation. No API key needed.
