import os
import sys

import pytest

from coderemote import folders


def make_tree(root):
    (root / "alpha").mkdir()
    (root / "Beta" / ".git").mkdir(parents=True)          # normal clone
    (root / "worktree").mkdir()
    (root / "worktree" / ".git").write_text("gitdir: /x")  # worktree/submodule: .git is a file
    (root / ".hidden").mkdir()
    (root / "notes.txt").write_text("a file, not a folder")
    return root


def names(listing):
    return [e["name"] for e in listing["entries"]]


def test_lists_only_folders_sorted_case_insensitively(tmp_path):
    listing = folders.list_folder(str(make_tree(tmp_path)))
    assert names(listing) == ["alpha", "Beta", "worktree"]
    assert listing["path"] == str(tmp_path.resolve())
    assert listing["parent"] == str(tmp_path.resolve().parent)


def test_marks_git_repos_including_dot_git_files(tmp_path):
    listing = folders.list_folder(str(make_tree(tmp_path)))
    git = {e["name"]: e["git"] for e in listing["entries"]}
    assert git == {"alpha": False, "Beta": True, "worktree": True}


def test_hidden_folders_only_when_asked(tmp_path):
    make_tree(tmp_path)
    assert ".hidden" not in names(folders.list_folder(str(tmp_path)))
    assert ".hidden" in names(folders.list_folder(str(tmp_path), show_hidden=True))


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_broken_symlink_is_skipped(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "dangling").symlink_to(tmp_path / "missing")
    assert names(folders.list_folder(str(tmp_path))) == ["real"]


@pytest.mark.skipif(sys.platform != "linux", reason="needs a filesystem that accepts non-UTF-8 names")
def test_non_utf8_names_are_skipped(tmp_path):
    os.mkdir(os.fsencode(tmp_path) + b"/bad\xff")
    (tmp_path / "good").mkdir()
    assert names(folders.list_folder(str(tmp_path))) == ["good"]


def test_root_has_no_parent():
    anchor = os.path.abspath(os.sep)
    assert folders.list_folder(anchor)["parent"] is None


def test_errors(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    with pytest.raises(folders.NotFound):
        folders.list_folder(str(tmp_path / "nope"))
    with pytest.raises(folders.NotAFolder):
        folders.list_folder(str(tmp_path / "file.txt"))
    with pytest.raises(folders.FolderError):
        folders.list_folder("relative/path")


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="root ignores permissions")
def test_unreadable_folder_is_no_access(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        with pytest.raises(folders.NoAccess):
            folders.list_folder(str(locked))
    finally:
        locked.chmod(0o755)


def test_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "proj").mkdir()
    assert names(folders.list_folder("~")) == ["proj"]


def repos(parent, n):
    for i in range(n):
        (parent / f"repo{i}" / ".git").mkdir(parents=True)


def test_guess_picks_candidate_with_most_repos(tmp_path):
    repos(tmp_path / "code", 1)
    repos(tmp_path / "projects", 3)
    assert folders.guess_projects_root(tmp_path) == tmp_path / "projects"


def test_guess_falls_back_to_home(tmp_path):
    (tmp_path / "projects").mkdir()  # exists but holds no repos
    repos(tmp_path / "elsewhere", 2)  # not a known name
    assert folders.guess_projects_root(tmp_path) == tmp_path
