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

# Poster genérico para todos los canales
_POSTER = "https://i.imgur.com/AcestreamIcon.png"
_BACKGROUND = "https://i.imgur.com/AcestreamBg.png"


# ============================================================================
# FLASK (mínimo, solo sirve archivos estáticos)
# ============================================================================
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.after_request
def cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Origin, Referer"
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
    """Info de un canal individual con campos completos para Stremio."""
    ch = _STREAMS.get(stremio_id)
    if ch:
        # Devolver el objeto meta directamente, no envuelto en "meta"
        meta = {
            "id": stremio_id,
            "type": "tv",
            "name": ch.get("name", stremio_id),
            "poster": _POSTER,
            "background": _BACKGROUND,
            "genre": [ch.get("genre", "TV")],
            "posterShape": "square",
        }
        return jsonify(meta)
    # Si no se encuentra, devolver un meta vacío que Stremio pueda ignorar
    return jsonify({"id": stremio_id, "type": "tv", "name": stremio_id, "poster": _POSTER})


@app.route("/stream/tv/<stremio_id>.json")
def serve_stream(stremio_id: str):
    """Stream del canal — acestream:// con notWebReady=True para Acestream."""
    ch = _STREAMS.get(stremio_id)
    if ch:
        return jsonify({
            "streams": [{
                "title": f"🔴 {ch.get('name', stremio_id)}",
                "url": f"acestream://{ch['acestream_id']}",
                "behaviorHints": {
                    "notWebReady": True,
                    "hasChromecastSupport": False,
                    "hasDrmSources": False,
                },
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


@app.route("/addons.json")
def serve_addons():
    """Endpoint de descubrimiento."""
    return jsonify({
        "addons": [{
            "transport": "stremio-addon",
            "manifest": _MANIFEST,
        }]
    })


# ============================================================================
# VERCEL
# ============================================================================
def handler(event, context):
    return app(event, context)


if __name__ == "__main__":
    print(f"🚀 ACEStream NEW ERA → {len(_CATALOG.get('metas', []))} canales")
    app.run(host="0.0.0.0", port=7000, debug=False)
