"""In-memory UploadThing double that mirrors the behaviour verified against the live API:
prepareUpload → signed ingest URL; multipart PUT with field ``file``; 413 when the body
exceeds the declared size; reads by customId at ``{appId}.ufs.sh/f/{customId}`` (404 if
absent); deleteFiles by customIds; listFiles; 401 for a wrong API key."""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any

import httpx

API_KEY = "sk_test_fake_key"
APP_ID = "fakeapp123"
TOKEN = base64.b64encode(json.dumps({"apiKey": API_KEY, "appId": APP_ID, "regions": ["sea1"]}).encode()).decode()


class FakeUploadThing:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}  # customId -> bytes
        self.pending: dict[str, dict[str, Any]] = {}  # ingest key -> {customId, size}
        self.fail_next: list[int] = []  # status codes to return for the next API/ingest calls
        self.calls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{request.method} {url.host}{url.path}")
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), json={"error": "injected"})
        if url.host == "api.uploadthing.com":
            if request.headers.get("x-uploadthing-api-key") != API_KEY:
                return httpx.Response(401, json={"error": "Invalid API key"})
            body = json.loads(request.content or b"{}")
            if url.path == "/v7/prepareUpload":
                key = uuid.uuid4().hex
                self.pending[key] = {"customId": body.get("customId") or key, "size": body["fileSize"], "acl": body.get("acl")}
                return httpx.Response(200, json={"key": key, "url": f"https://sea1.ingest.uploadthing.com/{key}?signature=x"})
            if url.path == "/v6/deleteFiles":
                ids = body.get("customIds", [])
                count = sum(1 for i in ids if self.files.pop(i, None) is not None)
                return httpx.Response(200, json={"success": True, "deletedCount": count})
            if url.path == "/v6/listFiles":
                return httpx.Response(200, json={"hasMore": False, "files": [{"customId": k} for k in self.files]})
            return httpx.Response(404, json={"error": "unknown endpoint"})
        if url.host.endswith("ingest.uploadthing.com") and request.method == "PUT":
            key = url.path.strip("/")
            meta = self.pending.get(key)
            if meta is None:
                return httpx.Response(404, json={"error": "unknown upload"})
            ctype = request.headers.get("content-type", "")
            if not ctype.startswith("multipart/form-data"):
                return httpx.Response(415, json={"error": "Unsupported Media Type"})
            data = _multipart_file(request.content, ctype)
            if len(data) > meta["size"]:
                return httpx.Response(413, json={"error": "Upload too large"})
            self.files[meta["customId"]] = data
            return httpx.Response(200, json={"ufsUrl": f"https://{APP_ID}.ufs.sh/f/{key}", "fileHash": "x"})
        if url.host == f"{APP_ID}.ufs.sh" and request.method == "GET":
            cid = url.path.removeprefix("/f/")
            if cid not in self.files:
                return httpx.Response(404)
            return httpx.Response(200, content=self.files[cid])
        return httpx.Response(404)


def _multipart_file(body: bytes, content_type: str) -> bytes:
    boundary = re.search(r"boundary=([^;]+)", content_type).group(1).encode()  # type: ignore[union-attr]
    for part in body.split(b"--" + boundary):
        if b'name="file"' in part:
            _, _, payload = part.partition(b"\r\n\r\n")
            return payload.removesuffix(b"\r\n")
    raise AssertionError("no file field")
