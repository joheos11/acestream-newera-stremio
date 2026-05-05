"""
Stremio Addon para ACEStream NEW ERA
======================================
Scrapes la web y sirve eventos + streams de Acestream para Stremio.

Uso local:
    pip install flask
    python main.py

Deploy en Vercel (serverless):
    $ vercel

Deploy en Railway/Render:
    $ pip install -r requirements.txt
    $ python main.py
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

        # Competencia
        competition = comp_map.get(event_id, "")

        # Acestream IDs
        ace_ids = re.findall(
            r"window\.openAcestream\('([a-f0-9]{40})'\)",
            detail_map.get(event_id, "")
        )
        if not ace_ids:
            continue

        genre = guess_genre(competition)

        # Limpiar nombre
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
        "type": "movie",
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


def make_streams(event: dict) -> list[dict]:
    """Genera streams Stremio desde acestream IDs."""
    streams = []
    for i, ace_id in enumerate(event["acestream_ids"]):
        streams.append({
            "title": f"Acestream Opción {i+1}/{len(event['acestream_ids'])}",
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
        html = fetch_html(WEB_URL)
        _cache = extract_events(html)
        _cache_at = time.time()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Eventos cacheados: {len(_cache)}")
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
        "description": "Eventos deportivos via Acestream - NEW ERA",
        "manifest": "/manifest.json",
        "catalogs": "/catalog/movie/acestream-futbol",
        "live_events": "/events.json",
    })


@app.route("/manifest.json")
def manifest():
    load_manifest()
    return jsonify(_MANIFEST)


@app.route("/catalog/<type_>/<catalog_id>")
def catalog(type_: str, catalog_id: str):
    search_q = request.args.get("search", "").lower()
    genre_q = request.args.get("genre", "")

    events = get_events()

    if search_q:
        events = [e for e in events
                  if search_q in e["match_name"].lower()
                  or search_q in e["competition"].lower()]
    if genre_q:
        events = [e for e in events if e["genre"] == genre_q]

    metas = [event_to_meta(e) for e in events[:200]]
    return jsonify({"metas": metas})


@app.route("/stream/<type_>/<stremio_id>.json")
def stream(type_: str, stremio_id: str):
    events = get_events()
    target = stremio_id.replace(f"acestream_", "")

    for e in events:
        safe = hashlib.md5(e["event_id"].encode()).hexdigest()[:12]
        if safe == target:
            streams = make_streams(e)
            return jsonify({"streams": streams})

    return jsonify({"streams": []})


@app.route("/events.json")
def events_raw():
    """Endpoint raw con todos los eventos (útil para Kodi)."""
    return jsonify({"events": get_events(), "count": len(get_events())})


# ============================================================================
# VERCEL SERVERLESS
# ============================================================================
def handler(event, context):
    return app(event, context)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7000))
    print(f"🚀 ACEStream NEW ERA Stremio Addon → http://0.0.0.0:{port}")
    print(f"   Manifest: http://0.0.0.0:{port}/manifest.json")
    print(f"   Catálogo: http://0.0.0.0:{port}/catalog/movie/acestream-futbol")
    app.run(host="0.0.0.0", port=port, debug=False)
