from typing import Any


def dep(deps: dict[str, Any], name: str) -> Any:
    return deps[name]
