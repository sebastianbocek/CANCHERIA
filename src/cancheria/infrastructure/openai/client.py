from __future__ import annotations
from cancheria.config.settings import AppSettings

def create_client():
    from openai import OpenAI
    settings=AppSettings.from_env()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key)
