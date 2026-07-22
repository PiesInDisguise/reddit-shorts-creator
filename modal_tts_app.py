"""Modal app: Chatterbox TTS generation + faster-whisper forced alignment,
running on a cloud GPU. Deploy with:

    modal deploy modal_tts_app.py

shortsbot.tts_client looks this app/function up by name at runtime via
modal.Function.from_name(...), so it must stay deployed for the reddit
pipeline to work.
"""

import modal

APP_NAME = "shortsbot-tts"
CLASS_NAME = "TTSModel"

app = modal.App(APP_NAME)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", "torchaudio", index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("chatterbox-tts", "faster-whisper")
)


@app.cls(gpu="T4", image=image, timeout=600, scaledown_window=120)
class TTSModel:
    @modal.enter()
    def load(self):
        import torch
        from chatterbox.tts import ChatterboxTTS
        from faster_whisper import WhisperModel

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tts_model = ChatterboxTTS.from_pretrained(device=self.device)
        self.whisper_model = WhisperModel(
            "base.en",
            device=self.device,
            compute_type="float16" if self.device == "cuda" else "int8",
        )

    @modal.method()
    def generate(self, text: str) -> dict:
        import tempfile
        from pathlib import Path

        import torchaudio as ta

        wav = self.tts_model.generate(text)

        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "out.wav"
            ta.save(str(wav_path), wav, self.tts_model.sr)
            audio_bytes = wav_path.read_bytes()

            segments, _ = self.whisper_model.transcribe(str(wav_path), word_timestamps=True)
            words = [
                {"word": str(w.word).strip(), "start": float(w.start), "end": float(w.end)}
                for seg in segments
                for w in (seg.words or [])
                if str(w.word).strip()
            ]

        return {"audio": audio_bytes, "words": words}
