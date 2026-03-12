#!/usr/bin/env python3
"""
Billing Compliance App — Backend Proxy
Thin Flask server that proxies Airia API calls so the API key stays server-side.

Two workflows:
  1. Load Guidelines:  Upload client guidelines doc → extract rules → store in memory
  2. Evaluate Invoice:  Upload invoice → evaluate against stored rules → return XLSX report

Endpoints:
  POST /api/upload            — Upload a file to Airia storage, return blob URL
  POST /api/load-guidelines   — Execute Guidelines Extractor pipeline
  POST /api/evaluate          — Execute Billing Evaluator pipeline
  GET  /api/clients           — List clients with loaded guidelines (from memory)
  GET  /api/health            — Health check
  GET  /                      — Serve the frontend
"""

import os, json, re, traceback, requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Config (set these as Vercel environment variables) ────────────────
AIRIA_BASE = os.environ.get("AIRIA_BASE", "https://demo.api.airia.ai")
AIRIA_API_KEY = os.environ.get("AIRIA_API_KEY", "")
GUIDELINES_PIPELINE = os.environ.get("GUIDELINES_PIPELINE", "")
EVALUATOR_PIPELINE = os.environ.get("EVALUATOR_PIPELINE", "")
MEMORY_ID = os.environ.get("MEMORY_ID", "")

HDR = {"X-API-Key": AIRIA_API_KEY, "User-Agent": "AiriaClient/1.0"}
HDR_JSON = {**HDR, "Content-Type": "application/json"}


# ── Helpers ───────────────────────────────────────────────────────────
def airia_upload(file_bytes, filename, content_type):
    """Upload file to Airia storage, return blob URL."""
    resp = requests.post(
        f"{AIRIA_BASE}/v1/upload",
        files={"file": (filename, file_bytes, content_type)},
        headers=HDR,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("imageUrl", "")


def airia_execute_multipart(pipeline_id, user_input, file_url, timeout=600):
    """Execute a multipart pipeline with file URL + message."""
    payload = {"userInput": user_input}
    resp = requests.post(
        f"{AIRIA_BASE}/v1/PipelineExecution/Multipart/{pipeline_id}",
        json=payload,
        headers=HDR_JSON,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("result", "")


def airia_execute(pipeline_id, user_input, timeout=600):
    """Execute a pipeline and return the result string."""
    resp = requests.post(
        f"{AIRIA_BASE}/v1/PipelineExecution/{pipeline_id}",
        json={"userInput": user_input},
        headers=HDR_JSON,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("result", "")


def get_memory_store():
    """Read the shared memory block to get the list of loaded clients."""
    try:
        resp = requests.get(
            f"{AIRIA_BASE}/v1/MemoryBlock/{MEMORY_ID}",
            headers=HDR_JSON,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Memory value is a JSON string containing the client map
        value = data.get("value", "") or data.get("activeVersion", {}).get("value", "") or ""
        if not value:
            return {}
        store = json.loads(value)
        if isinstance(store, dict):
            return store
        return {}
    except Exception:
        return {}


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "guidelines_pipeline": GUIDELINES_PIPELINE,
        "evaluator_pipeline": EVALUATOR_PIPELINE,
    })


@app.route("/api/upload", methods=["POST"])
def upload():
    """Upload a file to Airia storage."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        f = request.files["file"]
        file_bytes = f.read()
        url = airia_upload(file_bytes, f.filename, f.content_type)
        return jsonify({"url": url, "filename": f.filename, "size": len(file_bytes)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clients", methods=["GET"])
def list_clients():
    """Return list of clients with loaded guidelines."""
    try:
        store = get_memory_store()
        clients = []
        for key, val in store.items():
            if isinstance(val, dict):
                clients.append({
                    "key": key,
                    "name": val.get("client_name", key),
                    "rule_count": val.get("rule_count", len(val.get("rules", []))),
                    "last_updated": val.get("last_updated", ""),
                })
        return jsonify({"clients": clients})
    except Exception as e:
        return jsonify({"error": str(e), "clients": []}), 200


@app.route("/api/load-guidelines", methods=["POST"])
def load_guidelines():
    """Upload guidelines file + client name → execute Guidelines Extractor pipeline."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        f = request.files["file"]
        client_name = request.form.get("client_name", "").strip()
        if not client_name:
            return jsonify({"error": "Client name is required"}), 400

        file_bytes = f.read()

        # Upload file to Airia storage first
        file_url = airia_upload(file_bytes, f.filename, f.content_type)

        # Execute the Guidelines Extractor pipeline
        # The pipeline expects: file URL as multipart + client name as message
        user_input = f"{client_name}\n\nFile URL: {file_url}"
        result = airia_execute(GUIDELINES_PIPELINE, user_input, timeout=600)

        # Parse the result to check for errors
        if "ERROR" in result.upper() and len(result) < 500:
            return jsonify({"error": result}), 500

        return jsonify({"result": result, "client_name": client_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/evaluate", methods=["POST"])
def evaluate():
    """Upload invoice file + client name → execute Billing Evaluator pipeline."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        f = request.files["file"]
        client_name = request.form.get("client_name", "").strip()
        if not client_name:
            return jsonify({"error": "Client name is required"}), 400

        file_bytes = f.read()

        # Upload file to Airia storage first
        file_url = airia_upload(file_bytes, f.filename, f.content_type)

        # Execute the Billing Evaluator pipeline
        user_input = f"{client_name}\n\nFile URL: {file_url}"
        result = airia_execute(EVALUATOR_PIPELINE, user_input, timeout=600)

        # Parse the result — it contains a markdown summary with an XLSX download link
        if "ERROR" in result[:200].upper():
            return jsonify({"error": result}), 500

        # Extract the XLSX download link from the result
        dl_match = re.search(r'\[(?:Download|download)[^\]]*\]\((https?://[^\)]+)\)', result)
        xlsx_url = dl_match.group(1) if dl_match else None

        # Also try to find a direct URL pattern
        if not xlsx_url:
            url_match = re.search(r'(https?://[^\s\)]+\.xlsx[^\s\)]*)', result, re.IGNORECASE)
            if url_match:
                xlsx_url = url_match.group(1)

        # Try to find any blob URL if no xlsx-specific match
        if not xlsx_url:
            url_match = re.search(r'(https?://[^\s\)]+(?:blob|upload|storage)[^\s\)]*)', result, re.IGNORECASE)
            if url_match:
                xlsx_url = url_match.group(1)

        return jsonify({
            "result": result,
            "xlsx_url": xlsx_url,
            "client_name": client_name,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Vercel entry point — the `app` variable is picked up automatically
