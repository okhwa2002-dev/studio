from pathlib import Path

from app.utils import storage


def test_resolve_is_under_storage_root(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    p = storage.resolve("projects/1/voice/voice.mp3")
    assert p == tmp_path / "projects/1/voice/voice.mp3"


def test_write_bytes_creates_parents_and_returns_size(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    size = storage.write_bytes("projects/7/voice/voice.mp3", b"hello")
    assert size == 5
    assert (tmp_path / "projects/7/voice/voice.mp3").read_bytes() == b"hello"


def test_delete_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("a/b.mp3", b"x")
    storage.delete("a/b.mp3")
    assert not (tmp_path / "a/b.mp3").exists()
    storage.delete("a/b.mp3")  # 두 번째 호출도 예외 없이 통과해야 한다


def test_resolve_rejects_escaping_path(monkeypatch, tmp_path):
    # 상위 경로 탈출(../)은 거부한다 — 경로가 외부 입력에서 올 수 있다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    import pytest

    with pytest.raises(ValueError):
        storage.resolve("../secrets.txt")


def test_clear_dir_removes_files_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("projects/3/render/sources/scene1.mp4", b"a")
    storage.write_bytes("projects/3/render/sources/scene2.jpg", b"b")

    storage.clear_dir("projects/3/render/sources")
    assert list((tmp_path / "projects/3/render/sources").iterdir()) == []

    storage.clear_dir("projects/3/render/sources")          # 두 번째도 통과
    storage.clear_dir("projects/3/render/does-not-exist")   # 없는 디렉토리도 통과


def test_clear_dir_leaves_sibling_files(monkeypatch, tmp_path):
    # 소재만 지우고 같은 단계의 render.mp4는 건드리지 않아야 한다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    storage.write_bytes("projects/3/render/render.mp4", b"keep")
    storage.write_bytes("projects/3/render/sources/scene1.mp4", b"drop")

    storage.clear_dir("projects/3/render/sources")
    assert (tmp_path / "projects/3/render/render.mp4").read_bytes() == b"keep"
