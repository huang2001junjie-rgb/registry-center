from enum import Enum
from typing import Any, Optional, Dict


class AuthFailureReason(Enum):
    """认证失败原因枚举"""
    INVALID_CREDENTIALS = "Invalid credentials"


class AuthenticationError(Exception):
    """认证失败异常"""

    def __init__(self, reason: AuthFailureReason, detail: str = None):
        self.reason = reason
        self.detail = detail
        super().__init__(self.detail)


class Principal:
    """认证成功后的用户身份信息主体"""

    def __init__(self, client_ip: str):
        self.client_ip = client_ip


def authenticate(client_ip: str, request: Any, context: Optional[Dict[str, Any]] = None) -> Principal:
    try:
        return Principal(client_ip=client_ip)
    except Exception as e:
        raise AuthenticationError(AuthFailureReason.INVALID_CREDENTIALS, "认证失败") from e
