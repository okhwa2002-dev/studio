import shutil
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


def delete_tree(rel: str) -> None:
    """디렉토리를 하위까지 통째로 지운다. 없어도 조용히 통과한다(멱등).

    프로젝트 완전 삭제(정리 잡)가 쓴다. clear_dir로는 안 되는 이유: clear_dir은 한 단계의
    파일만 지우는데 실제 구조는 projects/{id}/{voice,captions,render}/ 로 한 단 더 깊고,
    render 아래에는 sources/ 가 또 있다.

    경로 검증은 resolve()에 맡긴다 — 루트 밖을 가리키면 ValueError다. rmtree는 되돌릴 수
    없으므로 이 가드가 특히 중요하다.

    ignore_errors=True인 이유: 파일 하나가 잠겨 있어도(Windows에서 재생 중인 mp4 등)
    나머지는 지우고 넘어간다. 남은 것은 다음 주기가 처리하며, 호출자는 커밋을 파일 삭제
    뒤에 두므로 덜 지워진 채로 행이 사라지는 일은 없다.
    """
    path = resolve(rel)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


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
