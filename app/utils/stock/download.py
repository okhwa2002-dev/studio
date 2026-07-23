import httpx

from app.utils import storage
from app.utils.stock.base import StockTooLarge

_CHUNK_MESSAGE = "소재가 상한을 넘었습니다"


async def download(url: str, rel: str, max_bytes: int, timeout_sec: int, transport=None) -> int:
    """url을 저장소 rel 경로로 스트리밍 저장하고 쓴 바이트 수를 돌려준다.

    상한을 넘으면 즉시 StockTooLarge. 어떤 실패든 부분 파일을 지우고 예외를 올린다 —
    반쪽짜리 파일이 남으면 ffmpeg가 원인 불명으로 죽는다. 이 후보를 건너뛰고
    다음 후보로 갈지는 호출자(StockRender)가 정한다.
    """
    path = storage.resolve(rel)   # 저장소 밖 경로는 여기서 ValueError
    path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec, follow_redirects=True, transport=transport
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with path.open("wb") as out:
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if written > max_bytes:
                            raise StockTooLarge(f"{_CHUNK_MESSAGE}({max_bytes} bytes): {url}")
                        out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return written
