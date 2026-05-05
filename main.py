"""
ACEStream NEW ERA — Stremio Addon (simplificado)
Un catálogo plano con 241 canales únicos + streams Acestream.
"""

import json
import hashlib
import os

# ============================================================================
# CANALES ÚNICOS (cargados desde channels.json embebido)
# ============================================================================
_CHANNELS = None

def get_channels():
    global _CHANNELS
    if _CHANNELS is None:
        path = os.path.join(os.path.dirname(__file__), "channels.json")
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Deduplicar por (name, genre) — primer occurrence wins
        seen = {}
        unique = []
        for ch in raw.get("channels", []):
            key = (ch["name"], ch["genre"])
            if key not in seen:
                seen[key] = True
                unique.append(ch)
        _CHANNELS = unique
    return _CHANNELS


def acestream_to_stremio_id(acestream_id: str) -> str:
    """Convierte un acestream ID → ID de Stremio (estables, sin hash del nombre)."""
    h = hashlib.md5(acestream_id.encode()).hexdigest()[:12]
    return f"acestream_{h}"


def make_meta(channel: dict) -> dict:
    """Convierte canal → meta de Stremio (versión mínima)."""
    sid = acestream_to_stremio_id(channel["acestream_id"])
    return {
        "id": sid,
        "type": "tv",
        "name": channel["name"],
    }


def make_streams(channel: dict) -> list[dict]:
    """Genera la respuesta de streams para un canal."""
    ace_id = channel["acestream_id"]
    return [{
        "title": f"🔴 {channel['name']}",
        "url": f"acestream://{ace_id}",
        "behaviorHints": {"notWebReady": True},
    }]


# ============================================================================
# FLASK SERVER
# ============================================================================
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.after_request
def cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


_MANIFEST = None


def load_manifest():
    global _MANIFEST
    if _MANIFEST is None:
        with open("manifest.json", "r", encoding="utf-8") as f:
            _MANIFEST = json.load(f)


@app.route("/manifest.json")
def manifest():
    load_manifest()
    return jsonify(_MANIFEST)


@app.route("/")
def index():
    chs = get_channels()
    return jsonify({
        "name": "ACEStream NEW ERA",
        "channels": len(chs),
        "manifest": "/manifest.json",
    })


@app.route("/catalog/tv/canales")
def catalog_canales():
    channels = get_channels()

    # Solo búsqueda
    search = request.args.get("search", "").lower()
    if search:
        channels = [c for c in channels if search in c["name"].lower()]

    # Soportar paginación de Stremio
    try:
        limit = int(request.args.get("limit", 200))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        limit, offset = 200, 0

    channels = channels[offset:offset + limit]

    metas = [make_meta(c) for c in channels]
    return jsonify({"metas": metas})


@app.route("/stream/tv/<stremio_id>.json")
def stream_tv(stremio_id: str):
    """Dado un ID de Stremio, devuelve el stream acestream."""
    channels = get_channels()

    for ch in channels:
        sid = acestream_to_stremio_id(ch["acestream_id"])
        if sid == stremio_id:
            return jsonify({"streams": make_streams(ch)})

    return jsonify({"streams": []})


# ============================================================================
# VERCEL
# ============================================================================
def handler(event, context):
    return app(event, context)


if __name__ == "__main__":
    chs = get_channels()
    print(f"🚀 ACEStream NEW ERA → {len(chs)} canales únicos")
    app.run(host="0.0.0.0", port=7000, debug=False)
