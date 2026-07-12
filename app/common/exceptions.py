class AppException(Exception):
    """비즈니스 로직에서 의도적으로 발생시키는 예외.

    핸들러가 status_code/message를 그대로 ApiResponse로 변환한다.
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)
