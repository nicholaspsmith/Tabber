import re
import shutil
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from audio.download import convert_webm_to_wav, download_audio
from audio.separate import is_demucs_available
from config import settings
from transcribe.klangio import transcribe_klangio
from transcribe.opensource import transcribe_opensource

app = FastAPI(title="Tabber", description="Guitar audio to tablature")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def sanitize_title(title: str) -> str:
    return re.sub(r"[^\w\-.]", "_", title).strip("_") or "untitled"


async def run_engine(engine: str, audio_path: Path, title: str) -> bytes:
    if engine == "klangio":
        return await transcribe_klangio(audio_path, title)
    elif engine == "opensource":
        return await transcribe_opensource(audio_path, title)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")


class TranscribeURLRequest(BaseModel):
    url: str
    title: str
    engine: str | None = None


@app.get("/health")
async def health():
    engines = ["opensource"]
    if settings.klangio_api_key:
        engines.insert(0, "klangio")
    return {"status": "ok", "engines": engines, "demucs": is_demucs_available()}


@app.post("/transcribe/url")
async def transcribe_url(req: TranscribeURLRequest):
    engine = req.engine or settings.default_engine
    safe_title = sanitize_title(req.title)
    wav_path = None

    try:
        wav_path = download_audio(req.url)
        gp5_bytes = await run_engine(engine, wav_path, req.title)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if wav_path and wav_path.parent.exists():
            shutil.rmtree(wav_path.parent, ignore_errors=True)

    return Response(
        content=gp5_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.gp5"'},
    )


@app.post("/transcribe/audio")
async def transcribe_audio(
    audio: UploadFile = File(...),
    title: str = Form(...),
    engine: str | None = Form(None),
):
    engine = engine or settings.default_engine
    safe_title = sanitize_title(title)
    tmp_dir = Path(tempfile.mkdtemp(prefix="tabber_"))

    try:
        # Save uploaded file
        webm_path = tmp_dir / f"upload{Path(audio.filename or '.webm').suffix}"
        with open(webm_path, "wb") as f:
            f.write(await audio.read())

        # Convert to WAV
        wav_path = convert_webm_to_wav(webm_path)

        gp5_bytes = await run_engine(engine, wav_path, title)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return Response(
        content=gp5_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.gp5"'},
    )


def run():
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)


if __name__ == "__main__":
    run()
