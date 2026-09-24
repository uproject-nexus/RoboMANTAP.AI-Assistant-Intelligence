from infrastructure.ai import option_labels_for_jenjang, normalize_custom_timer_config
from infrastructure.database.connection import DBWrapper

def test_option_policy():
    assert option_labels_for_jenjang("MTs") == ("A","B","C","D")
    assert option_labels_for_jenjang("MA") == ("A","B","C","D","E")

def test_timer_normalization():
    cfg=normalize_custom_timer_config({"timer_h":2,"timer_m":5,"timer_s":4})
    assert cfg["timer_seconds"] == 7504
    assert (cfg["timer_h"],cfg["timer_m"],cfg["timer_s"]) == (2,5,4)

def test_db_boundary():
    assert hasattr(DBWrapper, "query")
