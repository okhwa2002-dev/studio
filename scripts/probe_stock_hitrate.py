"""한국어 on_screen이 스톡에서 실제로 얼마나 잡히는지 재는 일회성 조사 스크립트.

테스트가 아니다 — 결과는 판정이 아니라 자료이며, 스펙 리스크 3에 기록한다.
실행: uv run python scripts/probe_stock_hitrate.py
"""

import asyncio

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pexels import PexelsSource
from app.utils.stock.pixabay import PixabaySource

# 실제 대본에 나올 법한 on_screen들 — 구체명사부터 추상 문구까지 섞는다
QUERIES = [
    "서울 야경",       # 구체 장소
    "아침 루틴",       # 일상 개념
    "복리 계산",       # 추상 개념
    "출근길",          # 일상 장면
    "하루 5분이면 충분",  # 자막용 문구 (검색어로는 최악)
    "abstract background",  # 최후 폴백
]


async def main() -> None:
    settings = get_settings()
    sources = []
    if settings.pexels_api_key:
        sources.append(PexelsSource())
    if settings.pixabay_api_key:
        sources.append(PixabaySource())
    if not sources:
        print("PEXELS_API_KEY / PIXABAY_API_KEY 가 없습니다.")
        return

    for query in QUERIES:
        row = []
        for source in sources:
            for kind in (VIDEO, PHOTO):
                try:
                    count = len(await source.search(query, kind))
                except Exception as exc:
                    row.append(f"{source.name}/{kind}=ERR({type(exc).__name__})")
                    continue
                row.append(f"{source.name}/{kind}={count}")
        print(f"{query!r:28} " + "  ".join(row))


if __name__ == "__main__":
    asyncio.run(main())
