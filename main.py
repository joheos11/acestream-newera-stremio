"""
ACEStream NEW ERA — Stremio Addon
Serve datos estáticos para máxima compatibilidad con Vercel serverless.
"""

import json
import os

# Rutas absolutas a los datos embebidos
_BASE = os.path.dirname(os.path.abspath(__file__))

def _load(path: str):
    with open(os.path.join(_BASE, path), "r", encoding="utf-8") as f:
        return json.load(f)

_MANIFEST = _load("manifest.json")
_CATALOG = _load("catalog.json")
_STREAMS = _load("streams.json")


# ============================================================================
# FLASK (mínimo, solo sirve archivos estáticos)
# ============================================================================
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.after_request
def cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/manifest.json")
def serve_manifest():
    return jsonify(_MANIFEST)


@app.route("/catalog.json")
def serve_catalog():
    """Catálogo plano con los 241 canales."""
    return jsonify(_CATALOG)


@app.route("/catalog/tv/canales")
@app.route("/catalog/tv/canales.json")
def serve_catalog_tv():
    """Ruta que espera Stremio para el catálogo de tv."""
    return jsonify(_CATALOG)


@app.route("/meta/tv/<stremio_id>.json")
def serve_meta(stremio_id: str):
    """Info de un canal individual (la necesita Stremio para la pantalla de detalle)."""
    ch = _STREAMS.get(stremio_id)
    if ch:
        return jsonify({
            "meta": {
                "id": stremio_id,
                "type": "tv",
                "name": ch["name"],
            }
        })
    return jsonify({"meta": None})


@app.route("/stream/tv/<stremio_id>.json")
def serve_stream(stremio_id: str):
    ch = _STREAMS.get(stremio_id)
    if ch:
        return jsonify({
            "streams": [{
                "title": f"🔴 {ch['name']}",
                "url": f"acestream://{ch['acestream_id']}",
                "behaviorHints": {"notWebReady": True},
            }]
        })
    return jsonify({"streams": []})


@app.route("/")
def index():
    return jsonify({
        "name": "ACEStream NEW ERA",
        "channels": len(_CATALOG.get("metas", [])),
        "manifest": "/manifest.json",
    })


# ============================================================================
# VERCEL
# ============================================================================
def handler(event, context):
    return app(event, context)


if __name__ == "__main__":
    print(f"🚀 ACEStream NEW ERA → {len(_CATALOG.get('metas', []))} canales")
    app.run(host="0.0.0.0", port=7000, debug=False)
