from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    environment: str = 'production'
    database_url: str = 'postgresql+psycopg://medflow:medflow@postgres/medflow'
    auth_database_url: str = ''
    worker_database_url: str = ''
    redis_url: str = 'redis://redis:6379/0'
    public_origin: str = 'https://medflow.example.org'
    oidc_issuer: str = ''
    oidc_client_id: str = ''
    oidc_client_secret: str = ''
    session_secret: str = ''
    oidc_mfa_claim: str = 'mfa'
    integration_secret: str = ''
    integration_organization_id: str = ''
    transcription_endpoint: str = ''
    transcription_api_key: str = ''
    transcription_approved: bool = False
    summary_approved: bool = False
    summary_endpoint: str = ''
    summary_api_key: str = ''
    audio_bucket: str = ''
    audio_kms_key: str = ''
    audio_retention_days: int = 0
    presence_grace_seconds: int = 300
    presence_stale_seconds: int = 900
    event_max_age_days: int = 30
    max_upload_bytes: int = 25 * 1024 * 1024

@lru_cache
def settings():
    return Settings()
