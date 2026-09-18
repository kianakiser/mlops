"""Tests for configuration loading."""

from __future__ import annotations

import pytest

from optcg_forecast.common.config import ConfigError, Settings, load_settings, redacted

# Nothing is required by default any more: the ingest half of the feature pipeline talks to a
# keyless public API, so demanding credentials would make a scheduled run fail for no reason.
# Each pipeline opts in to what it actually needs.
OPTIONAL_ENV = {
    "SOURCE_API_BASE_URL": "https://api.example.com",
    "SOURCE_API_KEY": "dummy-value-for-tests",
    "HOPSWORKS_API_KEY": "dummy-value-for-tests",
    "HOPSWORKS_PROJECT": "demo",
}


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in [
        *OPTIONAL_ENV,
        "WANDB_API_KEY",
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "GCS_BUCKET",
        "LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    return tmp_path / "absent.env"


def test_loads_with_a_completely_empty_environment(clean_env):
    """A scheduled ingest run must work with no secrets at all."""
    settings = load_settings(dotenv_path=clean_env)
    assert settings.source_api_base_url == "https://play.limitlesstcg.com/api"
    assert settings.source_api_key == ""
    assert settings.gcp_region == "europe-west6"


def test_environment_overrides_the_defaults(clean_env, monkeypatch):
    for key, value in OPTIONAL_ENV.items():
        monkeypatch.setenv(key, value)
    settings = load_settings(dotenv_path=clean_env)
    assert settings.hopsworks_project == "demo"
    assert settings.source_api_base_url == "https://api.example.com"


@pytest.mark.parametrize("missing", ["HOPSWORKS_API_KEY", "HOPSWORKS_PROJECT"])
def test_feature_store_settings_are_demanded_only_when_asked_for(clean_env, monkeypatch, missing):
    for key, value in OPTIONAL_ENV.items():
        if key != missing:
            monkeypatch.setenv(key, value)

    load_settings(dotenv_path=clean_env)  # fine without it

    with pytest.raises(ConfigError) as excinfo:
        load_settings(dotenv_path=clean_env, require_feature_store=True)
    assert missing in str(excinfo.value)


def test_cloud_settings_optional_unless_requested(clean_env, monkeypatch):
    for key, value in OPTIONAL_ENV.items():
        monkeypatch.setenv(key, value)
    load_settings(dotenv_path=clean_env)  # fine without cloud vars
    with pytest.raises(ConfigError):
        load_settings(dotenv_path=clean_env, require_cloud=True)


def test_model_uri_uses_alias_not_version():
    settings = Settings(
        source_api_base_url="u",
        source_api_key="k",
        hopsworks_api_key="k",
        hopsworks_project="p",
        model_name="demo",
        model_alias="champion",
    )
    assert settings.model_uri == "demo@champion"


def test_redacted_masks_secrets_but_keeps_config():
    settings = Settings(
        source_api_base_url="https://api.example.com",
        source_api_key="dummy-unredacted-aaa",
        hopsworks_api_key="dummy-unredacted-bbb",
        hopsworks_project="demo",
    )
    out = redacted(settings)
    assert "dummy-unredacted-aaa" not in str(out)
    assert "dummy-unredacted-bbb" not in str(out)
    assert out["source_api_key"].startswith("***")
    assert out["source_api_base_url"] == "https://api.example.com"  # non-secret survives
    assert out["hopsworks_project"] == "demo"
