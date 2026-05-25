from typing import Any

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles


class NoStoreStaticFiles(StaticFiles):
    def __init__(self, *args: Any, studio_build: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._studio_build = studio_build

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        requested_path = (path or "").replace("\\", "/").lstrip("/")
        if requested_path in {"", "."} or requested_path.endswith("/"):
            requested_path = "index.html"
        if requested_path in {"app.js", "style.css", "index.html"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["ETag"] = f'"xtts-studio-{self._studio_build}-{requested_path}"'
            response.headers["X-XTTS-Studio-Build"] = self._studio_build
        return response
