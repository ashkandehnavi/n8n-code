#!/usr/bin/env python3
"""Upload n8n/coding-agent.workflow.json onto n8n.denox.ir workflow LkpwmWAnSXuBzQ8q."""
from __future__ import annotations

import json
import os
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF_FILE = ROOT / "n8n" / "coding-agent.workflow.json"
WF_ID = "LkpwmWAnSXuBzQ8q"
BASE = "https://n8n.denox.ir"

# Cookie file is created by the operator script; never commit it.
COOKIE_FILE = Path(os.environ.get("N8N_COOKIE_FILE", os.path.expandvars(r"%TEMP%\n8n-cookie.txt")))


def req(method: str, path: str, cookie: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Cookie": cookie,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(r, context=ctx, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> None:
    cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()
    local = json.loads(WF_FILE.read_text(encoding="utf-8"))
    current = req("GET", f"/rest/workflows/{WF_ID}", cookie)["data"]

    payload = {
        "id": WF_ID,
        "name": local.get("name", current.get("name", "final exam")),
        "nodes": local["nodes"],
        "connections": local["connections"],
        "settings": local.get("settings") or current.get("settings") or {},
        "staticData": current.get("staticData"),
        "meta": local.get("meta") or current.get("meta"),
        "pinData": {},
        "versionId": current["versionId"],
    }
    updated = req("PATCH", f"/rest/workflows/{WF_ID}", cookie, payload)
    print("updated", updated.get("data", {}).get("id"), "version", updated.get("data", {}).get("versionId"))

    # n8n 2.x publish
    try:
        pub = req("POST", f"/rest/workflows/{WF_ID}/publish", cookie, {"versionId": updated["data"]["versionId"]})
        print("published", pub.get("data", {}).get("activeVersionId") or pub.get("data", {}).get("versionId"))
    except Exception as exc:
        print("publish skipped/failed:", exc)
        try:
            act = req(
                "POST",
                f"/rest/workflows/{WF_ID}/activate",
                cookie,
                {"versionId": updated["data"]["versionId"]},
            )
            print("activate", act.get("data", {}).get("active") or act.get("data", {}).get("id"))
        except Exception as exc2:
            print("activate failed:", exc2)


if __name__ == "__main__":
    main()
