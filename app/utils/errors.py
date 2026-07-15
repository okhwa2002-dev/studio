from dataclasses import dataclass


class AppError(Exception):
    """업무단(각 도메인 로직)이 status_code·code·message를 직접 지정해서 던지는 예외.

    에러 응답에 실릴 값은 이 예외를 던지는 쪽이 책임지고 채운다. DB 조회는 하지 않는다.
    """

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class Errors:
    """자주 쓰는 AppError를 미리 정의해 둔 헬퍼. 필요하면 AppError를 직접 던져도 된다."""

    @staticmethod
    def not_found(message: str = "리소스를 찾을 수 없습니다.") -> AppError:
        return AppError(404, "RESOURCE_NOT_FOUND", message)

    @staticmethod
    def bad_request(message: str = "잘못된 요청입니다.") -> AppError:
        return AppError(400, "BAD_REQUEST", message)

    @staticmethod
    def conflict(message: str = "이미 존재하는 리소스입니다.") -> AppError:
        return AppError(409, "CONFLICT", message)

    @staticmethod
    def forbidden(message: str = "접근 권한이 없습니다.") -> AppError:
        return AppError(403, "FORBIDDEN", message)

    @staticmethod
    def unauthorized(message: str = "인증이 필요합니다.") -> AppError:
        return AppError(401, "UNAUTHORIZED", message)

    @staticmethod
    def locked(message: str = "계정이 잠겼습니다. 관리자에게 문의하세요.") -> AppError:
        return AppError(423, "ACCOUNT_LOCKED", message)

    @staticmethod
    def invalid_id(message: str = "유효하지 않은 ID입니다.") -> AppError:
        return AppError(400, "INVALID_ID", message)


@dataclass(frozen=True)
class ResolvedError:
    code: str
    message: str
    status_code: int


# AppError가 아닌, 정말 예상 못한 예외가 발생했을 때만 쓰는 디폴트 에러.
# DB가 아니라 소스 코드에 고정된 값이다.
DEFAULT_ERROR = ResolvedError(
    code="UNKNOWN_ERROR",
    message="알 수 없는 오류가 발생했습니다.",
    status_code=500,
)
