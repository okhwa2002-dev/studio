"""새 변경 엔드포인트를 추가하고 감사 기록을 잊는 것을 막는다.

기록을 강요하는 테스트가 아니다 — 어느 쪽 집합에 넣을지 **결정하도록** 강요하는
테스트다. "안 남기기로 했다"(_EXEMPT)도 정당한 답이고, 그 판단이 코드에 남는다.
"""

from app.main import app

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 감사 로그를 남기는 경로. 값은 FastAPI 라우트의 경로 템플릿 그대로다.
_AUDITED = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/change-password",
    "/api/admin/users/{user_id}/approve",
    "/api/admin/users/{user_id}/reject",
    "/api/admin/users/{user_id}/unlock",
    "/api/admin/users/{user_id}/reset-password",
    "/api/admin/users/{user_id}/reset-failures",
    "/api/admin/notices",
    "/api/admin/notices/{notice_id}",
    "/api/admin/faqs",
    "/api/admin/faqs/{faq_id}",
    "/api/admin/system/settings",
    "/api/projects",
    "/api/projects/{project_id}",
    "/api/projects/{project_id}/stages/script",
    "/api/projects/{project_id}/stages/{name}/run",
    "/api/projects/{project_id}/stages/{name}/approve",
    "/api/projects/{project_id}/stages/{name}/regenerate",
}

# 일부러 남기지 않는 경로와 그 이유.
_EXEMPT = {
    # 사용자가 공지 목록을 열 때마다 발생한다. 감사 가치는 없고 건수로는 다른 모든
    # 행위의 합을 넘겨 관리자 화면을 읽을 수 없게 만든다.
    "/api/notices/{notice_id}/read",
    # 토큰 자동 갱신도 같은 이유다. 단 그 안의 재사용 감지(탈취 신호)는
    # TOKEN_REUSE_DETECTED로 반드시 기록한다.
    "/api/auth/refresh",
}


def _get_write_endpoints():
    """OpenAPI 스키마에서 모든 변경 엔드포인트를 추출한다.

    include_router로 등록된 라우터는 app.routes에 경로 정보가 노출되지 않으므로,
    OpenAPI 스키마를 사용한다.
    """
    openapi_schema = app.openapi()
    paths = set()

    if openapi_schema and "paths" in openapi_schema:
        for path_str, path_obj in openapi_schema["paths"].items():
            for method in path_obj.keys():
                if method.upper() in _WRITE_METHODS:
                    paths.add(path_str)

    return paths


def test_every_write_endpoint_is_classified():
    paths = _get_write_endpoints()
    unclassified = paths - _AUDITED - _EXEMPT
    assert not unclassified, (
        "감사 기록 여부가 정해지지 않은 변경 엔드포인트가 있습니다. "
        f"기록하면 _AUDITED에, 안 하면 이유와 함께 _EXEMPT에 넣으세요: {sorted(unclassified)}"
    )


def test_classification_has_no_stale_entries():
    """지워진 경로가 집합에 남아 있으면, 다음 사람이 그 경로가 아직 있다고 믿게 된다."""
    paths = _get_write_endpoints()
    stale = (_AUDITED | _EXEMPT) - paths
    assert not stale, f"존재하지 않는 경로가 분류 집합에 남아 있습니다: {sorted(stale)}"
