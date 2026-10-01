from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = ""
    app_origin: str = "http://localhost:8000"
    oidc_issuer_url: str = "http://localhost:58080/realms/identityguardian"
    oidc_client_id: str = "identityguardian"
    secure_cookies: bool = False
    development: bool = True
    session_idle_seconds: int = 1800
    session_absolute_seconds: int = 28800
    read_limit_per_minute: int = 60
    write_limit_per_minute: int = 10

    @model_validator(mode="after")
    def secure_deployment(self):
        for value in (self.app_origin, self.oidc_issuer_url):
            parsed = urlparse(value)
            if parsed.scheme != "https":
                if not self.development or parsed.hostname not in {"localhost", "127.0.0.1"}:
                    raise ValueError("HTTP is restricted to loopback development")
        if not self.development and not self.secure_cookies:
            raise ValueError("Deployed mode requires Secure cookies")
        return self
