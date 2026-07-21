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
    reddit_user_agent: str
    reddit_client_id: str
    reddit_client_secret: str
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
            reddit_user_agent=os.environ.get("REDDIT_USER_AGENT", ""),
            reddit_client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
            reddit_client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
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

    def require_reddit_user_agent(self) -> None:
        if not self.reddit_user_agent or "<your_reddit_username>" in self.reddit_user_agent:
            raise ConfigError(
                "REDDIT_USER_AGENT is not set (or still the placeholder). Reddit requires "
                "a descriptive User-Agent on every request. Set REDDIT_USER_AGENT in your "
                ".env file, e.g. 'shortsbot/0.1 by u/yourname'."
            )

    def require_reddit_oauth(self) -> None:
        if not self.reddit_client_id or not self.reddit_client_secret:
            raise ConfigError(
                "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are not set. Reddit blocks anonymous "
                "JSON scraping from most networks now, so this tool authenticates via "
                "Reddit's OAuth API. Create a free 'script' app at "
                "https://www.reddit.com/prefs/apps and put its client id/secret in .env."
            )

    def require_upload_enabled(self) -> None:
        if not self.enable_upload:
            raise ConfigError(
                "ENABLE_UPLOAD is false. Set ENABLE_UPLOAD=true in your .env file "
                "to allow the upload command to run."
            )
