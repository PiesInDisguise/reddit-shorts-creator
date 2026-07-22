import json
from pathlib import Path
from typing import List, Optional

VOICES_FILE = Path("voices.json")
DEFAULT_VOICES = ["TX3LPaxmHKxFdv7VOQHJ", "DfyC3OvvfERKzYGchkdL"]


def load_voices(path: Optional[Path] = None) -> List[str]:
    path = path or VOICES_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list) and data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    save_voices(DEFAULT_VOICES, path)
    return list(DEFAULT_VOICES)


def save_voices(voice_ids: List[str], path: Optional[Path] = None) -> None:
    path = path or VOICES_FILE
    path.write_text(json.dumps(voice_ids, indent=2))


def add_voice(voice_id: str, path: Optional[Path] = None) -> List[str]:
    voice_id = voice_id.strip()
    voices = load_voices(path)
    if voice_id and voice_id not in voices:
        voices.append(voice_id)
        save_voices(voices, path)
    return voices
