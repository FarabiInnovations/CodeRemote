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


def test_recent_is_most_recent_first_without_duplicates(tmp_path):
    folders = []
    for name in "abcdefg":
        (tmp_path / name).mkdir()
        folders.append(str(tmp_path / name))
    for f in folders:
        settings.add_recent(f, tmp_path)
    settings.add_recent(folders[3], tmp_path)
    assert settings.recent(tmp_path) == [folders[3], folders[6], folders[5], folders[4], folders[2]]


def test_recent_skips_folders_that_no_longer_exist(tmp_path):
    (tmp_path / "keep").mkdir()
    settings.add_recent(str(tmp_path / "gone"), tmp_path)
    settings.add_recent(str(tmp_path / "keep"), tmp_path)
    assert settings.recent(tmp_path) == [str(tmp_path / "keep")]
