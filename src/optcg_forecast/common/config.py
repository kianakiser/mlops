"""Configuration, loaded from the environment.

Everything secret arrives as an environment variable — from `.env` locally (gitignored) and
from GitHub Actions secrets in CI. Nothing secret is ever read from a committed file.

Settings are validated at import of `load_settings()` rather than at first use, so a missing
variable fails the pipeline immediately with a clear message instead of surfacing as a
confusing auth error deep inside a client library.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]


class ConfigError(RuntimeError):
    """A required setting is missing or malformed."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Required environment variable {name!r} is not set. "
            f"Copy .env.example to .env and fill it in, or add {name} to your "
            f"GitHub Actions secrets."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for all three pipelines."""

    # data source
    source_api_base_url: str
    source_api_key: str

    # feature store
    hopsworks_api_key: str
    hopsworks_project: str

    # tracking / registry
    mlflow_tracking_uri: str
    mlflow_experiment_name: str

    # cloud
    gcp_project_id: str = ""
    gcp_region: str = "europe-west6"
    gcs_bucket: str = ""

    # runtime
    log_level: str = "INFO"

    # the model alias the inference pipeline loads; moving this alias in the registry
    # promotes a new model with no code change and no redeploy
    model_name: str = "optcg_forecast"
    model_alias: str = "champion"

    _loaded_from: str = field(default="environment", compare=False)

    @property
    def model_uri(self) -> str:
        """The registry URI the inference pipeline resolves at load time."""
        return f"models:/{self.model_name}@{self.model_alias}"


def load_settings(*, dotenv_path: Path | None = None, require_cloud: bool = False) -> Settings:
    """Read settings from the environment, loading `.env` first if present.

    Args:
        dotenv_path: explicit `.env` to load; defaults to the repository root.
        require_cloud: also demand the GCP settings. Off by default so the feature and
            training pipelines can run locally without cloud credentials.
    """
    path = dotenv_path or (REPO_ROOT / ".env")
    if path.exists():
        load_dotenv(path, override=False)

    settings = Settings(
        source_api_base_url=_require("SOURCE_API_BASE_URL"),
        source_api_key=_require("SOURCE_API_KEY"),
        hopsworks_api_key=_require("HOPSWORKS_API_KEY"),
        hopsworks_project=_require("HOPSWORKS_PROJECT"),
        mlflow_tracking_uri=_optional("MLFLOW_TRACKING_URI", "http://localhost:5001"),
        mlflow_experiment_name=_optional("MLFLOW_EXPERIMENT_NAME", "optcg_forecast"),
        gcp_project_id=_require("GCP_PROJECT_ID") if require_cloud else _optional("GCP_PROJECT_ID"),
        gcp_region=_optional("GCP_REGION", "europe-west6"),
        gcs_bucket=_require("GCS_BUCKET") if require_cloud else _optional("GCS_BUCKET"),
        log_level=_optional("LOG_LEVEL", "INFO"),
        _loaded_from=str(path) if path.exists() else "environment",
    )
    return settings


def redacted(settings: Settings) -> dict[str, str]:
    """A dict of the settings safe to log — secrets masked.

    Use this in pipeline start-up logs. Never log a Settings object directly.
    """
    secretish = ("key", "secret", "token", "password")
    out: dict[str, str] = {}
    for name, value in vars(settings).items():
        if name.startswith("_"):
            continue
        if isinstance(value, str) and any(s in name.lower() for s in secretish) and value:
            out[name] = f"***{value[-4:]}" if len(value) > 4 else "***"
        else:
            out[name] = str(value)
    return out
