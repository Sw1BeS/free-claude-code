import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "nerd" / "migrate_env.py"


def load_migrate_env():
    spec = importlib.util.spec_from_file_location("migrate_env", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_env_file_strips_quotes_and_ignores_comments(tmp_path):
    module = load_migrate_env()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "",
                'OPENROUTER_API_KEY="sk-test"',
                "MODEL=anthropic/claude-sonnet-4",
                "invalid line",
                "EMPTY_VALUE=",
            ]
        )
        + "\n"
    )

    values = module.parse_env_file(env_file)

    assert values == {
        "OPENROUTER_API_KEY": "sk-test",
        "MODEL": "anthropic/claude-sonnet-4",
        "EMPTY_VALUE": "",
    }


def test_build_managed_env_copies_only_allowed_keys_and_sets_staged_port():
    module = load_migrate_env()
    legacy_values = {
        "OPENROUTER_API_KEY": "sk-openrouter",
        "DEEPSEEK_API_KEY": "sk-deepseek",
        "UNRELATED_SECRET": "do-not-copy",
        "PORT": "8082",
        "HOST": "0.0.0.0",
    }

    values = module.build_managed_env(legacy_values, existing_values={}, overwrite=True)

    assert values["OPENROUTER_API_KEY"] == "sk-openrouter"
    assert values["DEEPSEEK_API_KEY"] == "sk-deepseek"
    assert "UNRELATED_SECRET" not in values
    assert values["HOST"] == "127.0.0.1"
    assert values["PORT"] == "18082"


def test_build_managed_env_preserves_existing_without_overwrite():
    module = load_migrate_env()
    legacy_values = {
        "MODEL": "legacy-model",
        "PORT": "18082",
    }
    existing_values = {
        "MODEL": "existing-model",
        "PORT": "19000",
    }

    values = module.build_managed_env(
        legacy_values, existing_values=existing_values, overwrite=False
    )

    assert values["MODEL"] == "existing-model"
    assert values["PORT"] == "19000"


def test_render_env_quotes_values_without_leaking_to_stdout(capsys):
    module = load_migrate_env()

    rendered = module.render_env({"OPENROUTER_API_KEY": "sk-test"})
    captured = capsys.readouterr()

    assert rendered == 'OPENROUTER_API_KEY="sk-test"\n'
    assert captured.out == ""
    assert captured.err == ""
