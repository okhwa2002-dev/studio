"""새 변경 엔드포인트를 추가하고 감사 기록을 잊는 것을 막는다.

기록을 강요하는 테스트가 아니다 — 어느 쪽 집합에 넣을지 **결정하도록** 강요하는
테스트다. "안 남기기로 했다"(_EXEMPT)도 정당한 답이고, 그 판단이 코드에 남는다.

단위는 경로가 아니라 **(메서드, 경로) 쌍**이다. 경로만 보면 이미 목록에 있는 경로에
메서드를 하나 더하는 변경(예: 제목 수정용 PATCH /api/projects/{project_id})이 조용히
통과한다 — 그 경로는 DELETE 때문에 이미 분류돼 있기 때문이다.
"""

from app.main import app

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 감사 로그를 남기는 (메서드, 경로). 경로는 FastAPI 라우트의 경로 템플릿 그대로다.
_AUDITED = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/change-password"),
    ("POST", "/api/admin/users/{user_id}/approve"),
    ("POST", "/api/admin/users/{user_id}/reject"),
    ("POST", "/api/admin/users/{user_id}/unlock"),
    ("POST", "/api/admin/users/{user_id}/reset-password"),
    ("POST", "/api/admin/users/{user_id}/reset-failures"),
    ("POST", "/api/admin/notices"),
    ("PATCH", "/api/admin/notices/{notice_id}"),
    ("DELETE", "/api/admin/notices/{notice_id}"),
    ("POST", "/api/admin/faqs"),
    ("PATCH", "/api/admin/faqs/{faq_id}"),
    ("DELETE", "/api/admin/faqs/{faq_id}"),
    ("PUT", "/api/admin/system/settings"),
    ("POST", "/api/projects"),
    ("DELETE", "/api/projects/{project_id}"),
    ("PUT", "/api/projects/{project_id}/stages/script"),
    ("POST", "/api/projects/{project_id}/stages/{name}/run"),
    ("POST", "/api/projects/{project_id}/stages/{name}/approve"),
    ("POST", "/api/projects/{project_id}/stages/{name}/regenerate"),
}

# 일부러 남기지 않는 (메서드, 경로)와 그 이유.
_EXEMPT = {
    # 사용자가 공지 목록을 열 때마다 발생한다. 감사 가치는 없고 건수로는 다른 모든
    # 행위의 합을 넘겨 관리자 화면을 읽을 수 없게 만든다.
    ("POST", "/api/notices/{notice_id}/read"),
    # 토큰 자동 갱신도 같은 이유다. 단 그 안의 재사용 감지(탈취 신호)는
    # TOKEN_REUSE_DETECTED로 반드시 기록한다.
    ("POST", "/api/auth/refresh"),
}


def _get_write_endpoints():
    """OpenAPI 스키마에서 모든 변경 엔드포인트를 (메서드, 경로) 쌍으로 추출한다.

    include_router로 등록된 라우터는 app.routes에 경로 정보가 노출되지 않으므로,
    OpenAPI 스키마를 사용한다.

    한계: `include_in_schema=False`로 등록된 라우트는 OpenAPI에 들어가지 않으므로 이
    방식으로 보이지 않는다(현재 저장소에는 그런 라우트가 0건이다).
    """
    openapi_schema = app.openapi()
    endpoints = set()

    if openapi_schema and "paths" in openapi_schema:
        for path_str, path_obj in openapi_schema["paths"].items():
            for method in path_obj.keys():
                if method.upper() in _WRITE_METHODS:
                    endpoints.add((method.upper(), path_str))

    return endpoints


def _fmt(endpoints) -> list[str]:
    return [f"{method} {path}" for method, path in sorted(endpoints)]


def test_every_write_endpoint_is_classified():
    endpoints = _get_write_endpoints()
    unclassified = endpoints - _AUDITED - _EXEMPT
    assert not unclassified, (
        "감사 기록 여부가 정해지지 않은 변경 엔드포인트가 있습니다. "
        f"기록하면 _AUDITED에, 안 하면 이유와 함께 _EXEMPT에 넣으세요: {_fmt(unclassified)}"
    )


def test_classification_has_no_stale_entries():
    """지워진 엔드포인트가 집합에 남아 있으면, 다음 사람이 아직 있다고 믿게 된다."""
    endpoints = _get_write_endpoints()
    stale = (_AUDITED | _EXEMPT) - endpoints
    assert not stale, f"존재하지 않는 엔드포인트가 분류 집합에 남아 있습니다: {_fmt(stale)}"
