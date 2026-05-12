import base64
import json
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request


def xai_access_error_hint(detail: str) -> str:
    lowered = str(detail or "").lower()
    if any(token in lowered for token in ("model", "not found", "does not exist", "not exist", "permission", "access", "unauthorized", "forbidden")):
        return " Проверьте модель и доступ аккаунта xAI: укажите доступную модель в настройках Grok, например grok-2-image-1212, или модель, выданную вашей учётной записи/API."
    return ""


def xai_json_request(
    base_url: str,
    endpoint: str,
    api_key: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
    operation_label: str = "xAI request",
) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{base_url.rstrip('/')}{endpoint}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"{operation_label} failed with HTTP {exc.code}: {detail}{xai_access_error_hint(detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{operation_label} failed: {exc.reason}") from exc
    return json.loads(response_body) if response_body else {}


def download_http_file(url: str, out_path: Path, *, timeout: float = 180.0, empty_label: str = "Downloaded URL") -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "XTTS-Studio/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data:
        raise RuntimeError(f"{empty_label} returned an empty body")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)


def extract_xai_image_url(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0] if isinstance(data[0], dict) else {}
        if first.get("url"):
            return str(first.get("url") or "")
        if first.get("b64_json"):
            return "data:image/png;base64," + str(first.get("b64_json") or "")
    image = response.get("image") if isinstance(response.get("image"), dict) else {}
    return str(image.get("url") or response.get("url") or "")


def save_xai_image_url(image_url: str, out: Path) -> None:
    if image_url.startswith("data:image/"):
        _header, encoded = image_url.split(",", 1)
        out.write_bytes(base64.b64decode(encoded))
        return
    download_http_file(image_url, out, timeout=180.0, empty_label="Downloaded xAI image URL")
