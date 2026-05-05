"""
Stremio Addon para ACEStream NEW ERA
======================================
Scrapes la web de NEW ERA y sirve eventos + canales de Acestream para Stremio.
Incluye: Agenda de eventos en vivo + Lista de canales permanente.
"""

import json
import re
import time
import hashlib
import os
from datetime import datetime
from typing import Optional

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
WEB_URL = "https://k2k4r8lm8tkmuxbc8lkmq1in3v0oya1p6pe9o5bu0hu30br5ko08k2gb.ipns.dweb.link/"
CACHE_TTL = 300  # 5 min

# ============================================================================
# CANALES (embebidos para evitar scraping extra)
# ============================================================================
_CHANNELS_DATA: Optional[dict] = None


def load_channels() -> dict:
    global _CHANNELS_DATA
    if _CHANNELS_DATA is None:
        path = os.path.join(os.path.dirname(__file__), "channels.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _CHANNELS_DATA = json.load(f)
        else:
            _CHANNELS_DATA = {"channels": [], "genres": {}, "count": 0}
    return _CHANNELS_DATA


# ============================================================================
# SCRAPING
# ============================================================================

def fetch_html(url: str) -> str:
    """Descarga la página de la web de NEW ERA."""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def extract_events(html: str) -> list[dict]:
    """Extrae eventos + acestream IDs del HTML."""
    events = []

    # Map: event_id -> detail_html
    detail_map = {}
    for eid, detail_html in re.findall(
        r'<tr class="event-detail" data-event-id="([^"]+)">(.*?)</tr>',
        html, re.DOTALL
    ):
        detail_map[eid] = detail_html

    # Competencias
    comp_map = {}
    for eid, comp in re.findall(
        r'<tr class="event-row" data-event-id="([^"]+)">.*?class="competition-name">([^<]+)</span>',
        html, re.DOTALL
    ):
        comp_map[eid] = comp.strip()

    # Eventos principales
    for event_id, row_html in re.findall(
        r'<tr class="event-row" data-event-id="([^"]+)">(.*?)</tr>',
        html, re.DOTALL
    ):
        parts = event_id.split("-", 1)
        if len(parts) < 2:
            continue

        time_str = parts[0]
        match_raw = parts[1]
        competition = comp_map.get(event_id, "")

        # Acestream IDs
        ace_ids = re.findall(
            r"window\.openAcestream\('([a-f0-9]{40})'\)",
            detail_map.get(event_id, "")
        )
        if not ace_ids:
            continue

        genre = guess_genre(competition)
        match_name = re.sub(r'<[^>]+>', '', match_raw).strip()
        match_name = re.sub(r'[-_]+', ' ', match_name)

        events.append({
            "event_id": event_id,
            "time": time_str,
            "match_name": match_name or competition,
            "competition": competition,
            "genre": genre,
            "acestream_ids": ace_ids,
        })

    return events


def guess_genre(comp: str) -> str:
    c = comp.lower()
    if any(w in c for w in ["liga", "copa", "champions", "europa", "mundia", "futf", "la liga",
                             "hypermotion", "primera feder", "rfef", "bundesliga", "serie a",
                             "premier", "copa del rey", "uefa", "laliga", "fifa", "eurocop"]):
        return "futbol"
    if any(w in c for w in ["nba", "euroliga", "liga endesa", "acb", "balonc", "basket"]):
        return "baloncesto"
    if any(w in c for w in ["tenis", "wta", "atp", "masters", "miami", "roland"]):
        return "tenis"
    if any(w in c for w in ["f1", "formula", "fórmula"]):
        return "f1"
    if any(w in c for w in ["motogp", "moto", "motocross", "superbike", "moto2", "moto3"]):
        return "motogp"
    if any(w in c for w in ["ufc", "boxeo", "mma", "wwe"]):
        return "ufs"
    if any(w in c for w in ["nhl", "nfl", "hockey"]):
        return "deportes"
    return "otros"


# ============================================================================
# STREMO METAS / STREAMS
# ============================================================================

def event_to_meta(event: dict) -> dict:
    """Convierte evento → item de catálogo Stremio."""
    eid = event["event_id"]
    safe = hashlib.md5(eid.encode()).hexdigest()[:12]
    sid = f"acestream_{safe}"

    return {
        "id": sid,
        "type": "tv",
        "name": f"{event['match_name']} ({event['competition']})",
        "poster": "https://i.imgur.com/AcestreamPoster.png",
        "posterShape": "landscape",
        "genres": [event["genre"].title(), "Deportes", event["competition"]],
        "description": (
            f"🕐 {event['time']} | {event['competition']}\n"
            f"{event['match_name']}\n\n"
            f"🔴 Acestream | {len(event['acestream_ids'])} opciones disponibles"
        ),
        "runtime": "LIVE",
        "infoLinks": [],
    }


def channel_to_meta(channel: dict) -> dict:
    """Convierte canal → item de catálogo Stremio (type=channel)."""
    cid = hashlib.md5(channel["acestream_id"].encode()).hexdigest()[:12]
    sid = f"senal_{cid}"

    return {
        "id": sid,
        "type": "tv",
        "name": channel["name"],
        "poster": "https://i.imgur.com/ChannelIcon.png",
        "posterShape": "square",
        "genres": [channel["genre"], "Canales"],
        "description": (
            f"📡 {channel['name']}\n"
            f"Fuente: {channel['source']}\n"
            f"🔴 ID: {channel['acestream_id']}"
        ),
        "runtime": "LIVE",
        "infoLinks": [],
    }


def make_streams(event_or_channel) -> list[dict]:
    """Genera streams Stremio desde acestream IDs."""
    ids = event_or_channel.get("acestream_ids", [event_or_channel.get("acestream_id", "")])
    if not ids or not ids[0]:
        return []
    streams = []
    for i, ace_id in enumerate(ids):
        streams.append({
            "title": f"Acestream Opción {i+1}/{len(ids)}",
            "url": f"acestream://{ace_id}",
            "behaviorHints": {"notWebReady": True},
        })
    return streams


# ============================================================================
# CACHÉ
# ============================================================================
_cache: Optional[list[dict]] = None
_cache_at: float = 0


def get_events(force=False) -> list[dict]:
    global _cache, _cache_at
    if force or _cache is None or (time.time() - _cache_at) > CACHE_TTL:
        try:
            html = fetch_html(WEB_URL)
            _cache = extract_events(html)
            _cache_at = time.time()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Eventos cacheados: {len(_cache)}")
        except Exception as e:
            print(f"Error fetching events: {e}")
            if _cache is None:
                _cache = []
    return _cache


# ============================================================================
# WEB SERVER (Flask, compatible con Vercel)
# ============================================================================
from flask import Flask, jsonify, request

app = Flask(__name__)

_MANIFEST = None


def load_manifest():
    global _MANIFEST
    if _MANIFEST is None:
        with open("manifest.json", "r", encoding="utf-8") as f:
            _MANIFEST = json.load(f)


@app.route("/")
def index():
    return jsonify({
        "name": "ACEStream NEW ERA - Stremio Addon",
        "version": "1.0.0",
        "description": "Eventos deportivos + Canales via Acestream - NEW ERA",
        "manifest": "/manifest.json",
        "catalogs": [
            "/catalog/movie/acestream-futbol",
            "/catalog/channel/acestream-canales",
        ],
        "stats": {
            "eventos": len(get_events()),
            "canales": load_channels().get("count", 0),
        }
    })


@app.route("/manifest.json")
def manifest():
    load_manifest()
    return jsonify(_MANIFEST)


@app.route("/catalog/<type_>/<catalog_id>")
def catalog(type_: str, catalog_id: str):
    search_q = request.args.get("search", "").lower()
    genre_q = request.args.get("genre", "")

    # Canales
    if catalog_id == "acestream-canales":
        ch_data = load_channels()
        channels = ch_data.get("channels", [])

        if search_q:
            channels = [c for c in channels if search_q in c["name"].lower()]
        if genre_q:
            channels = [c for c in channels if c["genre"] == genre_q]

        metas = [channel_to_meta(c) for c in channels[:500]]
        return jsonify({"metas": metas})

    # Eventos por defecto (movie type)
    events = get_events()
    if search_q:
        events = [e for e in events
                  if search_q in e["match_name"].lower()
                  or search_q in e["competition"].lower()]
    if genre_q:
        events = [e for e in events if e["genre"] == genre_q]

    metas = [event_to_meta(e) for e in events[:200]]
    return jsonify({"metas": metas})


@app.route("/stream/tv/<stremio_id>.json")
def stream(type_: str, stremio_id: str):
    # Intentar como evento
    events = get_events()
    for e in events:
        safe = hashlib.md5(e["event_id"].encode()).hexdigest()[:12]
        if f"acestream_{safe}" == stremio_id:
            streams = make_streams(e)
            return jsonify({"streams": streams})

    # Intentar como canal
    ch_data = load_channels()
    for c in ch_data.get("channels", []):
        safe = hashlib.md5(c["acestream_id"].encode()).hexdigest()[:12]
        if f"senal_{safe}" == stremio_id:
            streams = make_streams(c)
            return jsonify({"streams": streams})

    return jsonify({"streams": []})


@app.route("/events.json")
def events_raw():
    """Endpoint raw con todos los eventos."""
    return jsonify({"events": get_events(), "count": len(get_events())})


@app.route("/channels.json")
def channels_raw():
    """Endpoint raw con todos los canales."""
    return jsonify(load_channels())


# ============================================================================
# VERCEL SERVERLESS
# ============================================================================
def handler(event, context):
    return app(event, context)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    ch = load_channels()
    print(f"🚀 ACEStream NEW ERA Stremio Addon → http://0.0.0.0:{port}")
    print(f"   Eventos: {len(get_events())}")
    print(f"   Canales: {ch.get('count', 0)}")
    print(f"   Manifest: http://0.0.0.0:{port}/manifest.json")
    app.run(host="0.0.0.0", port=port, debug=False)
