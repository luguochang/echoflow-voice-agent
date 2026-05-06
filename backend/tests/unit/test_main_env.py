import os

from backend.main import apply_server_overrides, load_project_environment


def test_load_project_environment_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "API_KEY=relay-key\nBASE_URL=https://relay.example.com/v1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)

    try:
        loaded = load_project_environment(tmp_path)

        assert loaded is True
        assert os.environ["API_KEY"] == "relay-key"
        assert os.environ["BASE_URL"] == "https://relay.example.com/v1"
    finally:
        os.environ.pop("API_KEY", None)
        os.environ.pop("BASE_URL", None)


def test_load_project_environment_preserves_existing_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("API_KEY", "existing-key")

    loaded = load_project_environment(tmp_path)

    assert loaded is True
    assert os.environ["API_KEY"] == "existing-key"


def test_apply_server_overrides_updates_websocket_config(monkeypatch):
    config = {
        "modules": {
            "protocols": {
                "config": {
                    "websocket": {
                        "host": "127.0.0.1",
                        "port": 8765,
                    }
                }
            }
        }
    }
    monkeypatch.setenv("ECHOFLOW_HOST", "0.0.0.0")
    monkeypatch.setenv("ECHOFLOW_PORT", "9000")

    apply_server_overrides(config)

    websocket = config["modules"]["protocols"]["config"]["websocket"]
    assert websocket["host"] == "0.0.0.0"
    assert websocket["port"] == 9000


def test_apply_server_overrides_rejects_invalid_port(monkeypatch):
    config = {
        "modules": {
            "protocols": {
                "config": {
                    "websocket": {
                        "host": "127.0.0.1",
                        "port": 8765,
                    }
                }
            }
        }
    }
    monkeypatch.setenv("ECHOFLOW_PORT", "70000")

    try:
        apply_server_overrides(config)
    except ValueError as exc:
        assert "ECHOFLOW_PORT" in str(exc)
    else:
        raise AssertionError("invalid ECHOFLOW_PORT should be rejected")
