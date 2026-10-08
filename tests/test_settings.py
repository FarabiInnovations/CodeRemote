from coderemote import settings


def test_missing_file_is_empty(tmp_path):
    assert settings.load(tmp_path) == {}


def test_save_merges_and_round_trips(tmp_path):
    settings.save({"a": 1}, tmp_path)
    settings.save({"b": 2}, tmp_path)
    assert settings.load(tmp_path) == {"a": 1, "b": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]  # no temp files left


def test_corrupt_file_is_treated_as_empty(tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    assert settings.load(tmp_path) == {}
