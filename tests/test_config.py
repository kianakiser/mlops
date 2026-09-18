"""Tests for configuration loading."""

from __future__ import annotations

import pytest

from mlops_project.common.config import ConfigError, Settings, load_settings, redacted

REQUIRED = {
    "SOURCE_API_BASE_URL": "https://api.example.com",
    "SOURCE_API_KEY": "dummy-value-for-tests",
    "HOPSWORKS_API_KEY": "dummy-value-for-tests",
    "HOPSWORKS_PROJECT": "demo",
}


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in [
        *REQUIRED,
        "MLFLOW_TRACKING_URI",
        "MLFLOW_EXPERIMENT_NAME",
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "GCS_BUCKET",
        "LOG_LEVEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    return tmp_path / "absent.env"


def test_loads_when_all_required_present(clean_env, monkeypatch):
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    settings = load_settings(dotenv_path=clean_env)
    assert settings.hopsworks_project == "demo"
    assert settings.gcp_region == "europe-west6"  # default applied


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_missing_required_variable_names_itself(clean_env, monkeypatch, missing):
    for key, value in REQUIRED.items():
        if key != missing:
            monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError) as excinfo:
        load_settings(dotenv_path=clean_env)
    assert missing in str(excinfo.value)


def test_cloud_settings_optional_unless_requested(clean_env, monkeypatch):
    for key, value in REQUIRED.items():
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
        mlflow_tracking_uri="u",
        mlflow_experiment_name="e",
        model_name="demo",
        model_alias="champion",
    )
    assert settings.model_uri == "models:/demo@champion"


def test_redacted_masks_secrets_but_keeps_config():
    settings = Settings(
        source_api_base_url="https://api.example.com",
        source_api_key="dummy-unredacted-aaa",
        hopsworks_api_key="dummy-unredacted-bbb",
        hopsworks_project="demo",
        mlflow_tracking_uri="http://localhost:5001",
        mlflow_experiment_name="exp",
    )
    out = redacted(settings)
    assert "dummy-unredacted-aaa" not in str(out)
    assert "dummy-unredacted-bbb" not in str(out)
    assert out["source_api_key"].startswith("***")
    assert out["source_api_base_url"] == "https://api.example.com"  # non-secret survives
    assert out["hopsworks_project"] == "demo"
