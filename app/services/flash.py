from urllib.parse import quote

from fastapi.responses import RedirectResponse
from starlette.responses import Response

COOKIE_NAME = "stg_flash"


def set_flash(response: Response, kind: str, message: str) -> Response:
    response.set_cookie(
        key=COOKIE_NAME,
        value=f"{quote(kind)}|{quote(message)}",
        max_age=120,
        samesite="lax",
        httponly=False,
    )
    return response


def redirect_with_flash(url: str, kind: str, message: str, status_code: int = 303) -> RedirectResponse:
    return set_flash(RedirectResponse(url=url, status_code=status_code), kind, message)
