from dataclasses import dataclass

import httpx

VIDEO = "video"
PHOTO = "photo"

DEFAULT_TIMEOUT_SEC = 15.0


async def get_json(url: str, params: dict, headers: dict, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict:
    """소스별 HTTP GET+JSON 파싱. Pexels/Pixabay 등 어느 소스든 로직이 동일해 여기 둔다.

    timeout_sec를 매개변수로 둔 이유: 이후 지연 특성이 다른 소스가 추가돼도
    이 함수를 다시 포크하지 않고 값만 다르게 넘기면 되도록 하기 위해서다.
    """
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


class StockTooLarge(Exception):
    """소재가 STOCK_MAX_BYTES를 넘었다. 이 후보만 건너뛰라는 신호."""


@dataclass(frozen=True)
class Clip:
    """소스 중립 스톡 소재 1건. 어느 API에서 왔든 이 모양으로 통일한다."""

    source: str            # "pexels" | "pixabay"
    kind: str              # VIDEO | PHOTO
    id: str                # 소스 내 고유 id
    url: str               # 내려받을 실제 파일 URL
    page_url: str          # 출처 표기용 소스 페이지 링크
    author: str            # 작가명 (없으면 "")
    width: int
    height: int
    duration_sec: float | None = None   # 이미지는 None

    @property
    def key(self) -> tuple[str, str]:
        """씬 간 중복 배제 키. 소스가 달라도 id가 겹칠 수 있어 소스명을 함께 쓴다."""
        return (self.source, self.id)
