import base64
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
MIN_API_SPEED = 0.7
MAX_API_SPEED = 1.2


class TTSError(RuntimeError):
    pass


@dataclass
class Alignment:
    characters: List[str]
    start_times: List[float]
    end_times: List[float]


@dataclass
class NarrationResult:
    audio_path: Path
    alignment: Alignment
    duration: float  # actual decoded audio duration (source of truth), set by caller


def synthesize(
    text: str,
    voice_id: str,
    api_key: str,
    out_path: Path,
    speed: float = 1.0,
    model_id: str = "eleven_multilingual_v2",
) -> Alignment:
    if not text.strip():
        raise TTSError("Cannot synthesize empty text")

    speed = max(MIN_API_SPEED, min(MAX_API_SPEED, speed))

    url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}/with-timestamps"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"speed": speed},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs TTS request failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    audio_bytes = base64.b64decode(data["audio_base64"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio_bytes)

    alignment_data = data["alignment"]
    return Alignment(
        characters=alignment_data["characters"],
        start_times=alignment_data["character_start_times_seconds"],
        end_times=alignment_data["character_end_times_seconds"],
    )
