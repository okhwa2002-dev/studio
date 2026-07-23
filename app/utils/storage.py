from pathlib import Path

from app.config import get_settings


def _root() -> Path:
    """STORAGE_PATH 루트. 테스트는 이 함수를 monkeypatch해 tmp_path로 바꾼다."""
    return Path(get_settings().storage_path).resolve()


def resolve(rel: str) -> Path:
    """저장소 루트 기준 상대 경로를 절대 경로로. 루트 밖으로 나가는 경로는 거부한다."""
    root = _root()
    path = (root / rel).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"저장소 밖 경로입니다: {rel}")
    return path


def write_bytes(rel: str, data: bytes) -> int:
    """부모 디렉토리를 만들고 파일을 쓴 뒤 바이트 크기를 돌려준다."""
    path = resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def delete(rel: str) -> None:
    """파일을 지운다. 이미 없어도 조용히 통과한다(멱등)."""
    resolve(rel).unlink(missing_ok=True)


def clear_dir(rel: str) -> None:
    """디렉토리 안의 파일을 모두 지운다. 없어도 조용히 통과한다(멱등).

    stock 렌더러가 재실행될 때 이전 소재를 남기지 않기 위한 것. 소재는 asset으로
    기록하지 않아 _replace_assets가 지워주지 않으므로 provider가 직접 비운다.
    하위 디렉토리는 건드리지 않는다 — 소재는 평평하게 저장된다.
    """
    path = resolve(rel)
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
