import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    elevenlabs_api_key: str
    elevenlabs_default_voice_id: str
    apify_api_token: str
    background_clips_dir: Path
    impact_font_path: Path
    enable_upload: bool
    youtube_client_secrets_file: Path
    youtube_token_file: Path

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_default_voice_id=os.environ.get(
                "ELEVENLABS_DEFAULT_VOICE_ID", "AHc7z8dzjrGlVbbQ8enm"
            ),
            apify_api_token=os.environ.get("APIFY_API_TOKEN", ""),
            background_clips_dir=Path(
                os.environ.get("BACKGROUND_CLIPS_DIR", "./background_clips")
            ),
            impact_font_path=Path(
                os.environ.get("IMPACT_FONT_PATH", r"C:\Windows\Fonts\impact.ttf")
            ),
            enable_upload=os.environ.get("ENABLE_UPLOAD", "false").strip().lower()
            == "true",
            youtube_client_secrets_file=Path(
                os.environ.get(
                    "YOUTUBE_CLIENT_SECRETS_FILE",
                    "./.secrets/youtube_client_secret.json",
                )
            ),
            youtube_token_file=Path(
                os.environ.get("YOUTUBE_TOKEN_FILE", "./.secrets/youtube_token.json")
            ),
        )

    def require_elevenlabs(self) -> None:
        if not self.elevenlabs_api_key:
            raise ConfigError(
                "ELEVENLABS_API_KEY is not set. Add it to your .env file "
                "(copy .env.example to .env and fill it in)."
            )

    def require_apify(self) -> None:
        if not self.apify_api_token:
            raise ConfigError(
                "APIFY_API_TOKEN is not set. Add it to your .env file. Get one from "
                "https://console.apify.com/settings/integrations."
            )

    def require_upload_enabled(self) -> None:
        if not self.enable_upload:
            raise ConfigError(
                "ENABLE_UPLOAD is false. Set ENABLE_UPLOAD=true in your .env file "
                "to allow the upload command to run."
            )
