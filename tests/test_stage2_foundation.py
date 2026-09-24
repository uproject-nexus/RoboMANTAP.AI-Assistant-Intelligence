from config.constants import option_count_for_jenjang, option_labels_for_jenjang
from config.settings import AppSettings
from infrastructure.ai.json_utils import loads_json
from infrastructure.database.connection import DBWrapper
from utils.math import clean_math_string
from utils.text import clean_json_text


def test_existing_madrasah_option_policy_is_preserved():
    assert option_labels_for_jenjang("MTs") == ("A", "B", "C", "D")
    assert option_labels_for_jenjang("MA") == ("A", "B", "C", "D", "E")
    assert option_count_for_jenjang("MA") == 5


def test_foundation_config_has_no_runtime_side_effects():
    settings = AppSettings()
    assert settings.stream_hint_max_tokens == 9000
    assert settings.stream_solution_max_tokens == 9000


def test_json_and_math_utilities():
    assert clean_json_text("```json\n{\"ok\": true}\n```") == '{"ok": true}'
    assert loads_json("```json\n{\"ok\": true}\n```")["ok"] is True
    assert "∘" in clean_math_string(r"f(x) = x^2 \circ g(x)")
    assert "∘" in clean_math_string(r"f(x) = x^2 \circl g(x)")


def test_database_wrapper_is_defined_without_connecting():
    assert DBWrapper.__name__ == "DBWrapper"
