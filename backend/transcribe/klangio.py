import asyncio
from pathlib import Path

import httpx

from config import settings

BASE_URL = "https://api.klang.io"
POLL_INTERVAL = 3  # seconds
MAX_POLL_TIME = 300  # 5 minutes


async def transcribe_klangio(audio_path: Path, title: str) -> bytes:
    """Submit audio to Klangio API and return GP5 file bytes."""
    if not settings.klangio_api_key:
        raise RuntimeError("KLANGIO_API_KEY not configured")

    headers = {"kl-api-key": settings.klangio_api_key}

    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=60) as client:
        # 1. Submit transcription job
        with open(audio_path, "rb") as f:
            resp = await client.post(
                "/transcription",
                params={"model": "guitar", "outputs": ["gp5"]},
                files={"file": (audio_path.name, f, "audio/wav")},
                data={"title": title[:120]},
            )
        resp.raise_for_status()
        job = resp.json()
        job_id = job["job_id"]

        # 2. Poll for completion
        elapsed = 0
        while elapsed < MAX_POLL_TIME:
            status_resp = await client.get(f"/job/{job_id}/status")
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data["status"]

            if status == "COMPLETED":
                break
            elif status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                error = status_data.get("error", "Unknown error")
                raise RuntimeError(f"Klangio job {status}: {error}")

            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        else:
            raise RuntimeError(f"Klangio job timed out after {MAX_POLL_TIME}s")

        # 3. Download GP5 result
        gp5_resp = await client.get(f"/job/{job_id}/gp5")
        gp5_resp.raise_for_status()
        return gp5_resp.content
