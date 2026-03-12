"""GET /api/health — Health check."""
import os, json
from http.server import BaseHTTPRequestHandler

PARSER_PIPELINE   = os.environ.get("PARSER_PIPELINE", "a6ee7f8a-4b8f-4dc1-9f47-2a793e482935")
ANSWERER_PIPELINE = os.environ.get("ANSWERER_PIPELINE", "52f71380-5c5a-46df-abb5-542971af8bb3")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "parser": PARSER_PIPELINE,
            "answerer": ANSWERER_PIPELINE,
        }).encode())
