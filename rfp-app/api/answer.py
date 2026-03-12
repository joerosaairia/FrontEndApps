"""POST /api/answer — Answer a single RFP question via sub-pipeline."""
import os, json, re
import requests as http_requests
from http.server import BaseHTTPRequestHandler

AIRIA_BASE        = os.environ.get("AIRIA_BASE", "https://demo.api.airia.ai")
AIRIA_API_KEY     = os.environ.get("AIRIA_API_KEY", "")
ANSWERER_PIPELINE = os.environ.get("ANSWERER_PIPELINE", "52f71380-5c5a-46df-abb5-542971af8bb3")

HDR_JSON = {
    "X-API-Key": AIRIA_API_KEY,
    "User-Agent": "AiriaClient/1.0",
    "Content-Type": "application/json",
}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
            question = body.get("question", "")
            context = body.get("context", "").strip()

            if not question:
                self._json(400, {"error": "No question provided"})
                return

            prompt = question
            if context:
                prompt = f"{question}\n\nAdditional context from the user:\n{context}"

            resp = http_requests.post(
                f"{AIRIA_BASE}/v1/PipelineExecution/{ANSWERER_PIPELINE}",
                json={"userInput": prompt},
                headers=HDR_JSON,
                timeout=120,
            )
            resp.raise_for_status()
            result_text = resp.json().get("result", "")

            # Parse JSON response (may be wrapped in ```json fences)
            cleaned = re.sub(r'^```json\s*', '', result_text.strip())
            cleaned = re.sub(r'\s*```$', '', cleaned)
            try:
                parsed = json.loads(cleaned)
            except Exception:
                parsed = {"answer": result_text, "sources": [], "confidence": "UNKNOWN", "key_points": []}

            self._json(200, parsed)

        except Exception as e:
            self._json(200, {"error": str(e), "answer": f"Error: {str(e)}", "confidence": "ERROR", "sources": [], "key_points": []})

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
