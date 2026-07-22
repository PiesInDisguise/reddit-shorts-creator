from dataclasses import dataclass
from pathlib import Path
from typing import List

import modal

MODAL_APP_NAME = "shortsbot-tts"
MODAL_CLASS_NAME = "TTSModel"


class TTSError(RuntimeError):
    pass


@dataclass
class Alignment:
    characters: List[str]
    start_times: List[float]
    end_times: List[float]


def _alignment_from_words(words: list) -> Alignment:
    """Expand word-level (text, start, end) entries into the character-level
    Alignment shape captions.words_from_alignment() expects -- every character
    in a word shares that word's start/end, with a single space token between
    words (its own timing is irrelevant since spaces are just split points)."""
    characters: List[str] = []
    start_times: List[float] = []
    end_times: List[float] = []

    for i, word in enumerate(words):
        text = word["word"]
        start = float(word["start"])
        end = float(word["end"])
        for ch in text:
            characters.append(ch)
            start_times.append(start)
            end_times.append(end)
        if i < len(words) - 1:
            characters.append(" ")
            start_times.append(end)
            end_times.append(end)

    return Alignment(characters=characters, start_times=start_times, end_times=end_times)


def synthesize(text: str, out_path: Path) -> Alignment:
    """Generate narration for text via the Chatterbox TTS Modal app (see
    modal_tts_app.py, deployed separately with `modal deploy modal_tts_app.py`)
    and return word-level timing (from its built-in Whisper forced alignment)
    expanded into the character-level Alignment shape."""
    if not text.strip():
        raise TTSError("Cannot synthesize empty text")

    try:
        model_cls = modal.Cls.from_name(MODAL_APP_NAME, MODAL_CLASS_NAME)
    except Exception as exc:
        raise TTSError(
            f"Could not find the '{MODAL_APP_NAME}' Modal app. Deploy it first with "
            f"`modal deploy modal_tts_app.py`. ({exc})"
        ) from exc

    try:
        result = model_cls().generate.remote(text)
    except Exception as exc:
        raise TTSError(f"Chatterbox TTS generation failed on Modal: {exc}") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(result["audio"])

    return _alignment_from_words(result["words"])
