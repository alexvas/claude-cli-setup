#!/usr/bin/env python3
"""Generate ~/.pi/agent/models.json from /etc/inf-splitter/inf-splitter.toml.

Creates a single ``inf-splitter`` provider that proxies all models from TOML
sections that declare ``endpoint_openai``.  The proxy address is taken from the
``HOST_GATEWAY_IP`` and ``PROXY_PORT`` environment variables.
"""

import json
import os
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def main() -> None:
    toml_path = (
        sys.argv[1] if len(sys.argv) > 1 else "/etc/inf-splitter/inf-splitter.toml"
    )
    out_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.expanduser("~/.pi/agent/models.json")
    )

    host_ip = os.environ.get("HOST_GATEWAY_IP", "127.0.0.1")
    proxy_port = os.environ.get("PROXY_PORT", "3000")

    with open(toml_path, "rb") as fh:
        config = tomllib.load(fh)

    models: list[dict[str, str]] = []

    for _name, section in config.items():
        if not isinstance(section, dict):
            continue
        if "endpoint_openai" not in section:
            continue

        models_raw = section["models"]
        ids: list[str] = (
            [models_raw] if isinstance(models_raw, str) else list(models_raw)
        )
        for mid in ids:
            if mid != "default":
                models.append({"id": mid})

    provider = {
        "baseUrl": f"http://{host_ip}:{proxy_port}",
        "api": "openai-completions",
        "apiKey": "inf-splitter",
        "models": models,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump({"providers": {"inf-splitter": provider}}, fh, indent=2)
        fh.write("\n")

    ids = [m["id"] for m in models]
    print(
        f"Written {len(models)} model(s) from {toml_path} to {out_path}: {', '.join(ids)}"
    )


if __name__ == "__main__":
    main()
