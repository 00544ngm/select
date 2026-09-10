from __future__ import annotations

import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings
except ModuleNotFoundError:
    from pydantic import BaseModel as BaseSettings


def _load_env_file(filepath=".env"):
    path = Path(filepath)
    if not path.exists():
        return {}
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def _coerce_value(value, target_type):
    if target_type is bool:
        return value.lower() in {"1", "true", "yes", "on"}
    if target_type is int:
        return int(value)
    return value


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 16384
    openai_temperature: float = 0.3

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    cattoken_api_key: str = ""
    cattoken_base_url: str = "https://www.cattoken.vip/v1"
    cattoken_model: str = "gpt-5.4"

    headless: bool = True
    browser_ws_endpoint: str | None = None
    proxy: str | None = None
    captcha_wait_enabled: bool = True
    captcha_wait_timeout_seconds: int = 600
    captcha_check_interval_seconds: int = 5
    timeout_ms: int = 30000
    max_retries: int = 3
    log_level: str = "INFO"

    def __init__(self, **data):
        env_values = _load_env_file()
        fields = type(self).model_fields
        for name, field in fields.items():
            env_name = name.upper()
            raw_value = os.environ.get(env_name, env_values.get(env_name))
            if raw_value is None or name in data:
                continue
            annotation = getattr(field, "annotation", str)
            data[name] = _coerce_value(raw_value, annotation)
        super().__init__(**data)
