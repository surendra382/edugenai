from backend.app.core.config import Settings


def test_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite:///./data/app.db"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.backend_url == "http://127.0.0.1:8000"


def test_settings_loads_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=sqlite:///./data/test.db\n"
        "API_HOST=0.0.0.0\n"
        "API_PORT=9000\n"
        "BACKEND_URL=http://0.0.0.0:9000\n"
    )

    settings = Settings(_env_file=str(env_file))

    assert settings.database_url == "sqlite:///./data/test.db"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9000
    assert settings.backend_url == "http://0.0.0.0:9000"
