from pathlib import Path

from . import ffmpeg_utils

WHOOSH_ASSET_PATH = Path("assets") / "sfx" / "whoosh.wav"


def ensure_whoosh_sound(asset_path: Path = WHOOSH_ASSET_PATH) -> Path:
    """Return a short synthesized "whoosh" sound effect, generating and caching
    it on first use. Self-contained (band-passed noise with an amplitude
    envelope) -- no external sound asset needed."""
    if asset_path.exists():
        return asset_path

    asset_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_utils.run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=pink:amplitude=1:duration=0.45:sample_rate=44100",
            "-af",
            "highpass=f=300,lowpass=f=7000,afade=t=in:d=0.04,afade=t=out:st=0.28:d=0.17",
            str(asset_path),
        ]
    )
    return asset_path
