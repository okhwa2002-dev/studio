from app.utils.errors import DEFAULT_ERROR, AppError, Errors, ResolvedError


def test_app_error_carries_status_code_code_and_message():
    exc = AppError(404, "AUTH_INVALID", "인증 실패")
    assert exc.status_code == 404
    assert exc.code == "AUTH_INVALID"
    assert exc.message == "인증 실패"


def test_default_error_is_a_fixed_source_constant():
    # 디폴트 에러는 DB가 아니라 소스 코드에 고정된 값이어야 한다.
    assert DEFAULT_ERROR == ResolvedError(
        code="UNKNOWN_ERROR",
        message="알 수 없는 오류가 발생했습니다.",
        status_code=500,
    )


def test_errors_not_found_uses_default_message_and_status():
    exc = Errors.not_found()
    assert exc.status_code == 404
    assert exc.code == "RESOURCE_NOT_FOUND"
    assert exc.message == "리소스를 찾을 수 없습니다."


def test_errors_bad_request_accepts_custom_message():
    exc = Errors.bad_request("이름은 필수입니다.")
    assert exc.status_code == 400
    assert exc.code == "BAD_REQUEST"
    assert exc.message == "이름은 필수입니다."


def test_errors_conflict_defaults():
    exc = Errors.conflict()
    assert exc.status_code == 409
    assert exc.code == "CONFLICT"


def test_errors_forbidden_defaults():
    exc = Errors.forbidden()
    assert exc.status_code == 403
    assert exc.code == "FORBIDDEN"


def test_errors_unauthorized_defaults():
    exc = Errors.unauthorized()
    assert exc.status_code == 401
    assert exc.code == "UNAUTHORIZED"


def test_errors_invalid_id_defaults():
    exc = Errors.invalid_id()
    assert exc.status_code == 400
    assert exc.code == "INVALID_ID"
