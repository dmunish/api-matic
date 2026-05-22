from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_mode: str = "sandbox"

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:5000/oauth/callback"
    google_token_file: str = "google_token.json"
    google_calendar_id: str = "primary"

    slack_webhook_url: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_test_number: str = ""

    hourly_rate: float = 150.0
    your_name: str = "Your Name"
    your_email: str = "you@example.com"
    demo_mode: bool = True

    @property
    def follow_up_delay_seconds(self) -> int:
        return 10 if self.demo_mode else 86_400


@lru_cache
def get_settings() -> Settings:
    return Settings()
