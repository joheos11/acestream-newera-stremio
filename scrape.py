#!/usr/bin/env python3
"""
Scraper para ACEStream NEW ERA
============================== 
Extrae eventos y canales del HTML de la web y genera archivos JSON.
Se ejecuta cada 12h via GitHub Actions.

Uso:
    python scrape.py
"""

import json
import re
import time
import hashlib
import urllib.request
import urllib.error
import sys
from datetime import datetime, timezone

# ============================================================================
# CONFIG
# ============================================================================
WEB_URL = "https://k2k4r8lm8tkmuxbc8lkmq1in3v0oya1p6pe9o5bu0hu30br5ko08k2gb.ipns.dweb.link/"

# ============================================================================
# SCRAPING
# ============================================================================

def fetch_html(url: str) -> str:
    """Descarga la página con reintentos."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"Intento {attempt+1} fallido: {e}", file=sys.stderr)
            time.sleep(5)
    raise Exception(f"No se pudo descargar {url} tras 3 intentos")


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


def guess_channel_genre(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ['dazn']): return 'DAZN'
    if any(w in n for w in ['m+ ', 'movistar', 'plus ']): return 'Movistar+'
    if any(w in n for w in ['eurosport']): return 'EuroSport'
    if any(w in n for w in ['liga', 'champions', 'laliga', 'hyper', 'futf', 'copa del',
                              'gol play', 'gol tv', 'teledeporte', '1rfef', 'primera feder', 'segunda']): return 'Fútbol'
    if any(w in n for w in ['f1', 'formula', 'motor', 'motogp', 'rally', 'golf', 'tenis', 'tennis']): return 'Motor'
    if any(w in n for w in ['sky sports', 'bt sport', 'premier sport', 'elev', 'sport tv',
                              'ziggo', 'rtl', 'polsat', 'setanta', 'viasat', 'match',
                              'nhl', 'fox sports', 'espn']): return 'Internacional'
    if any(w in n for w in ['bein']): return 'beIN'
    if any(w in n for w in ['nba', 'basket']): return 'Baloncesto'
    if any(w in n for w in ['ufc', 'box', 'fight', 'mma']): return 'Combate'
    if any(w in n for w in ['la 1', 'la 2', 'cuatro', 'telecinco', 'disney', 'nick',
                              'calle 13', 'comedy']): return 'Generalista'
    if any(w in n for w in ['canal ', 'm. deportes']): return 'Deportes'
    return 'Otros'


def extract_events(html: str) -> list[dict]:
    """Extrae eventos con acestream IDs."""
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

        ace_ids = re.findall(
            r"window\.openAcestream\('([a-f0-9]{40})'\)",
            detail_map.get(event_id, "")
        )
        if not ace_ids:
            continue

        match_name = re.sub(r'<[^>]+>', '', match_raw).strip()
        match_name = re.sub(r'[-_]+', ' ', match_name)

        events.append({
            "event_id": event_id,
            "time": time_str,
            "match_name": match_name or competition,
            "competition": competition,
            "genre": guess_genre(competition),
            "acestream_ids": ace_ids,
        })

    return events


def extract_channels(html: str) -> list[dict]:
    """Extrae canales de data:text/plain URLs embebidas en el HTML."""
    channels = []

    # Buscar data:text/plain URLs (versión actual de la web)
    data_urls = re.findall(r'data:text/plain;charset=utf-8,([^\"\']+)', html)

    # Encontrar la que contiene listaplana
    for encoded in data_urls:
        decoded = urllib.parse.unquote(encoded)
        lines = [l.strip() for l in decoded.split('\n') if l.strip()]
        hashes = [l for l in lines if re.match(r'^[a-f0-9]{40}$', l)]
        if hashes:
            # Esta es la lista plana
            current_name = ''
            current_source = ''
            for line in lines:
                if '-->' in line:
                    parts = line.split('-->')
                    current_name = parts[0].strip()
                    current_source = parts[1].strip()
                elif re.match(r'^[a-f0-9]{40}$', line):
                    channels.append({
                        "name": current_name,
                        "source": current_source,
                        "acestream_id": line,
                        "genre": guess_channel_genre(current_name),
                    })
            break

    # Fallback: buscar en fileContents embebido (versión antigua)
    if not channels:
        listaplana_match = re.search(
            r"'listaplana\.txt':\s*`([^`]+)`",
            html, re.DOTALL
        )
        if listaplana_match:
            lp_text = listaplana_match.group(1)
            current_name = ''
            current_source = ''
            for line in lp_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if '-->' in line:
                    parts = line.split('-->')
                    current_name = parts[0].strip()
                    current_source = parts[1].strip()
                elif re.match(r'^[a-f0-9]{40}$', line):
                    channels.append({
                        "name": current_name,
                        "source": current_source,
                        "acestream_id": line,
                        "genre": guess_channel_genre(current_name),
                    })

    return channels


# ============================================================================
# MAIN
# ============================================================================

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando scrape...")
    ts = datetime.now(timezone.utc).isoformat()

    # Fetch HTML
    print(f"📡 Descargando {WEB_URL}...")
    html = fetch_html(WEB_URL)
    print(f"   HTML descargado: {len(html):,} bytes")

    # Extract
    print("🔍 Extrayendo eventos...")
    events = extract_events(html)
    print(f"   → {len(events)} eventos encontrados")

    print("📺 Extrayendo canales...")
    channels = extract_channels(html)
    print(f"   → {len(channels)} canales encontrados")

    # Group channels by genre
    genres = {}
    for ch in channels:
        g = ch['genre']
        if g not in genres:
            genres[g] = []
        genres[g].append(ch)

    # Save events
    events_data = {
        "_meta": {
            "updated": ts,
            "source": WEB_URL,
            "count": len(events),
        },
        "events": events,
    }
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(events_data, f, ensure_ascii=False, indent=2)
    print(f"💾 events.json guardado: {len(events)} eventos")

    # Save channels
    channels_data = {
        "_meta": {
            "updated": ts,
            "source": WEB_URL,
            "count": len(channels),
        },
        "channels": channels,
        "genres": genres,
    }
    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(channels_data, f, ensure_ascii=False, indent=2)
    print(f"💾 channels.json guardado: {len(channels)} canales")

    print(f"✅ Scrape completado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
