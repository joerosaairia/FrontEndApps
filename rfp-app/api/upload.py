"""POST /api/upload — Upload a file to Airia storage, return blob URL."""
import os, json
import requests as http_requests
from http.server import BaseHTTPRequestHandler

AIRIA_BASE    = os.environ.get("AIRIA_BASE", "https://demo.api.airia.ai")
AIRIA_API_KEY = os.environ.get("AIRIA_API_KEY", "")
HDR = {"X-API-Key": AIRIA_API_KEY, "User-Agent": "AiriaClient/1.0"}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            # Parse multipart form data manually
            if "multipart/form-data" not in content_type:
                self._json(400, {"error": "Expected multipart/form-data"})
                return

            boundary = content_type.split("boundary=")[1].strip()
            parts = body.split(f"--{boundary}".encode())

            file_bytes = None
            filename = "upload"
            file_content_type = "application/octet-stream"

            for part in parts:
                if b"Content-Disposition" not in part:
                    continue
                header_end = part.find(b"\r\n\r\n")
                if header_end == -1:
                    continue
                headers_raw = part[:header_end].decode("utf-8", errors="replace")
                if 'name="file"' in headers_raw:
                    file_bytes = part[header_end + 4:]
                    if file_bytes.endswith(b"\r\n"):
                        file_bytes = file_bytes[:-2]
                    # Extract filename
                    if 'filename="' in headers_raw:
                        fn_start = headers_raw.index('filename="') + 10
                        fn_end = headers_raw.index('"', fn_start)
                        filename = headers_raw[fn_start:fn_end]
                    # Extract content type
                    if "Content-Type:" in headers_raw:
                        ct_line = [l for l in headers_raw.split("\r\n") if "Content-Type:" in l]
                        if ct_line:
                            file_content_type = ct_line[0].split("Content-Type:")[1].strip()

            if file_bytes is None:
                self._json(400, {"error": "No file provided"})
                return

            resp = http_requests.post(
                f"{AIRIA_BASE}/v1/upload",
                files={"file": (filename, file_bytes, file_content_type)},
                headers=HDR,
                timeout=60,
            )
            resp.raise_for_status()
            url = resp.json().get("imageUrl", "")
            self._json(200, {"url": url, "filename": filename, "size": len(file_bytes)})

        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
