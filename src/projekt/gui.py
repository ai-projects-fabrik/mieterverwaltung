"""Lokale Web-Oberflaeche zum Ausfuellen einer Mietvertragsvorlage."""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import threading
import uuid
import zipfile
from email.parser import BytesParser
from email.policy import default as _EMAIL_POLICY
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import NoReturn

from projekt.anfrage import aenderungen_aus_text
from projekt.bericht import bericht
from projekt.docx_fuellen import fuelle, platzhalter
from projekt.felder import FELDER, normalisiere

_MAX_KOERPER = 5 * 1024 * 1024
_HTML_TYP = "text/html; charset=utf-8"
_DOCX_TYP = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_TOKEN = re.compile(r"[0-9a-f]{32}")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_vertraege: dict[str, bytes] = {}
_vertraege_sperre = threading.Lock()


class _GuiFehler(Exception):
    """Fehler, dessen Text als Klartext in der HTML-Antwort erscheint."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _GuiFehler(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="projekt.gui", allow_abbrev=False)
    parser.add_argument("--port", type=int, default=8765, help="Port der lokalen Oberflaeche")
    parser.add_argument(
        "--selbsttest", action="store_true", help="Eingebauten Selbsttest ausfuehren"
    )
    return parser


def _seite(titel: str, inhalt: str) -> bytes:
    dokument = (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        f"<title>{html.escape(titel)}</title></head><body>"
        f"<h1>{html.escape(titel)}</h1>{inhalt}</body></html>"
    )
    return dokument.encode("utf-8")


def _html_antwort(status: int, inhalt: str) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": _HTML_TYP}, _seite("Mietvertrag", inhalt)


def _fehler(status: int, nachricht: str) -> tuple[int, dict[str, str], bytes]:
    return _html_antwort(status, f"<p>{html.escape(nachricht)}</p>")


def _kopfwert(kopf: dict[str, str], name: str) -> str:
    for schluessel, wert in kopf.items():
        if str(schluessel).lower() == name.lower():
            return str(wert)
    return ""


def _formular() -> bytes:
    felder = "".join(
        f'<p><label for="{feld}">{feld}</label><input id="{feld}" name="{feld}" type="text"></p>'
        for feld in FELDER
    )
    inhalt = (
        '<form method="post" action="/erstellen" enctype="multipart/form-data">'
        '<p><label for="vorlage">Vorlage (.docx)</label>'
        '<input id="vorlage" name="vorlage" type="file" accept=".docx" required></p>'
        '<p><label for="daten">Bestand (JSON, optional)</label>'
        '<input id="daten" name="daten" type="file" accept=".json,application/json"></p>'
        f"{felder}"
        '<p><label for="anfrage">Anfrage</label>'
        '<textarea id="anfrage" name="anfrage" rows="8"></textarea></p>'
        '<p><button type="submit">Vertrag erstellen</button></p></form>'
    )
    return _html_antwort(200, inhalt)[2]


def _multipart_teile(kopf: dict[str, str], koerper: bytes) -> dict[str, tuple[bool, bytes]]:
    if not isinstance(koerper, bytes):
        raise _GuiFehler("Anfragekoerper muss als bytes uebergeben werden")

    content_type = _kopfwert(kopf, "Content-Type")
    haupttyp = content_type.split(";", 1)[0].strip().lower()
    if haupttyp != "multipart/form-data":
        raise _GuiFehler("Content-Type muss multipart/form-data sein")
    if "\r" in content_type or "\n" in content_type:
        raise _GuiFehler("Content-Type ist ungueltig")

    try:
        roh = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin-1") + koerper
        )
        nachricht = BytesParser(policy=_EMAIL_POLICY).parsebytes(roh)
    except (UnicodeEncodeError, ValueError) as fehler:
        raise _GuiFehler("Multipart-Anfrage ist ungueltig") from fehler

    if not nachricht.is_multipart() or nachricht.defects:
        raise _GuiFehler("Multipart-Anfrage ist ungueltig")

    teile: dict[str, tuple[bool, bytes]] = {}
    for teil in nachricht.iter_parts():
        if teil.defects or teil.get_content_disposition() != "form-data":
            raise _GuiFehler("Multipart-Anfrage ist ungueltig")
        name = teil.get_param("name", header="content-disposition")
        if not isinstance(name, str) or not name:
            raise _GuiFehler("Multipart-Anfrage enthaelt ein Feld ohne Namen")
        inhalt = teil.get_payload(decode=True)
        if not isinstance(inhalt, bytes):
            raise _GuiFehler("Multipart-Anfrage ist ungueltig")
        teile[name] = (teil.get_filename() is not None, inhalt)
    return teile


def _datei(teile: dict[str, tuple[bool, bytes]], feld: str, pflicht: bool) -> bytes | None:
    if feld not in teile:
        if pflicht:
            raise _GuiFehler(f"Feld '{feld}' fehlt")
        return None
    ist_datei, inhalt = teile[feld]
    if not ist_datei:
        raise _GuiFehler(f"Feld '{feld}' muss als Datei uebergeben werden")
    return inhalt


def _textfeld(teile: dict[str, tuple[bool, bytes]], feld: str) -> str:
    if feld not in teile:
        return ""
    ist_datei, inhalt = teile[feld]
    if ist_datei:
        raise _GuiFehler(f"Feld '{feld}' muss als Text uebergeben werden")
    try:
        return inhalt.decode("utf-8")
    except UnicodeDecodeError as fehler:
        raise _GuiFehler(f"Feld '{feld}' ist nicht UTF-8-kodiert") from fehler


def _bestand(teile: dict[str, tuple[bool, bytes]]) -> dict:
    roh = _datei(teile, "daten", pflicht=False)
    if roh is None:
        return {}
    try:
        daten = json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as fehler:
        raise _GuiFehler("Feld 'daten' enthaelt kein gueltiges JSON") from fehler
    return daten


def _vertrag_erstellen(kopf: dict[str, str], koerper: bytes) -> tuple[int, dict[str, str], bytes]:
    if len(koerper) > _MAX_KOERPER:
        return _fehler(413, "Anfrage ist zu gross")

    teile = _multipart_teile(kopf, koerper)
    vorlage = _datei(teile, "vorlage", pflicht=True)
    if vorlage is None:
        raise _GuiFehler("Feld 'vorlage' fehlt")

    roh_bestand = _bestand(teile)
    if not isinstance(roh_bestand, dict):
        raise _GuiFehler("Feld 'daten' muss ein JSON-Objekt enthalten")

    for feld in FELDER:
        wert = _textfeld(teile, feld)
        if wert.strip():
            roh_bestand[feld] = wert

    alt = normalisiere(roh_bestand)
    anfrage = _textfeld(teile, "anfrage")
    neu = dict(alt)
    if anfrage.strip():
        neu.update(aenderungen_aus_text(anfrage))

    try:
        vorhandene_platzhalter = platzhalter(vorlage)
    except ValueError as fehler:
        raise _GuiFehler(f"Feld 'vorlage': {fehler}") from fehler
    fehlende = [name for name in vorhandene_platzhalter if name not in neu]
    if fehlende:
        raise _GuiFehler("Platzhalter ohne Wert: " + ", ".join(fehlende))

    try:
        vertrag = fuelle(vorlage, neu)
    except ValueError as fehler:
        raise _GuiFehler(f"Feld 'vorlage': {fehler}") from fehler

    token = uuid.uuid4().hex
    with _vertraege_sperre:
        _vertraege[token] = vertrag

    inhalt = (
        "<h2>Aenderungsbericht</h2>"
        f"<pre>{html.escape(bericht(alt, neu))}</pre>"
        f'<p><a href="/download/{token}">Vertrag herunterladen</a></p>'
    )
    return _html_antwort(200, inhalt)


def _download(pfad: str, methode: str) -> tuple[int, dict[str, str], bytes] | None:
    if not pfad.startswith("/download/"):
        return None
    token = pfad.removeprefix("/download/")
    if _TOKEN.fullmatch(token) is None:
        return _fehler(404, "Download nicht gefunden")
    if methode != "GET":
        return _fehler(405, "Methode nicht erlaubt")

    with _vertraege_sperre:
        vertrag = _vertraege.get(token)
    if vertrag is None:
        return _fehler(404, "Download nicht gefunden")
    return (
        200,
        {"Content-Type": _DOCX_TYP, "Content-Disposition": 'attachment; filename="vertrag.docx"'},
        vertrag,
    )


def _beantworte(
    methode: str, pfad: str, kopf: dict[str, str], koerper: bytes
) -> tuple[int, dict[str, str], bytes]:
    methode = methode.upper()
    pfad = pfad.split("?", 1)[0]

    if pfad == "/":
        if methode != "GET":
            return _fehler(405, "Methode nicht erlaubt")
        return 200, {"Content-Type": _HTML_TYP}, _formular()

    if pfad == "/erstellen":
        if methode != "POST":
            return _fehler(405, "Methode nicht erlaubt")
        return _vertrag_erstellen(kopf, koerper)

    download = _download(pfad, methode)
    if download is not None:
        return download
    return _fehler(404, "Seite nicht gefunden")


def antwort(
    methode: str, pfad: str, kopf: dict[str, str], koerper: bytes
) -> tuple[int, dict[str, str], bytes]:
    """Beantwortet eine HTTP-Anfrage ohne Socket und liefert Status, Kopf und Koerper.

    Die Funktion speichert erzeugte Vertraege nur im Prozessspeicher. Fehler bei
    der Verarbeitung werden als HTML-Antwort mit Status 400 ausgegeben; es wird
    nie ein interner Serverfehler 500 erzeugt.
    """

    try:
        return _beantworte(methode, pfad, kopf, koerper)
    except _GuiFehler as fehler:
        return _fehler(400, str(fehler))
    except (ValueError, TypeError) as fehler:
        return _fehler(400, str(fehler) or "Anfrage ist ungueltig")
    except Exception:
        return _fehler(400, "Anfrage konnte nicht verarbeitet werden")


class _Handler(BaseHTTPRequestHandler):
    """HTTP-Handler, der alle Anfragen an :func:`antwort` weiterreicht."""

    def _sende(self, status: int, kopf: dict[str, str], koerper: bytes) -> None:
        self.send_response(status)
        for name, wert in kopf.items():
            if name.lower() != "content-length":
                self.send_header(name, wert)
        self.send_header("Content-Length", str(len(koerper)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def _beantworte_anfrage(self, methode: str) -> None:
        try:
            laenge = int(self.headers.get("Content-Length", "0") or "0")
            if laenge < 0:
                raise ValueError("negative Laenge")
            if laenge > _MAX_KOERPER:
                self.close_connection = True
                self._sende(*_fehler(413, "Anfrage ist zu gross"))
                return
            koerper = self.rfile.read(laenge) if laenge else b""
            self._sende(*antwort(methode, self.path, dict(self.headers.items()), koerper))
        except (OSError, ValueError):
            self._sende(*_fehler(400, "Anfrage konnte nicht gelesen werden"))

    def do_GET(self) -> None:
        self._beantworte_anfrage("GET")

    def do_HEAD(self) -> None:
        self._beantworte_anfrage("HEAD")

    def do_POST(self) -> None:
        self._beantworte_anfrage("POST")

    def do_PUT(self) -> None:
        self._beantworte_anfrage("PUT")

    def do_PATCH(self) -> None:
        self._beantworte_anfrage("PATCH")

    def do_DELETE(self) -> None:
        self._beantworte_anfrage("DELETE")

    def do_OPTIONS(self) -> None:
        self._beantworte_anfrage("OPTIONS")

    def log_message(self, format: str, *args: object) -> None:
        """Unterdrueckt die Standard-Logausgabe des lokalen Servers."""


def starte(host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    """Bindet den lokalen HTTP-Server an Loopback, ohne ihn zu starten."""

    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Host muss 127.0.0.1 oder localhost sein")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Port muss zwischen 0 und 65535 liegen")
    return HTTPServer(("127.0.0.1", port), _Handler)


def _multipart_koerper(
    felder: dict[str, str], dateien: dict[str, tuple[str, bytes]]
) -> tuple[dict[str, str], bytes]:
    grenze = "----mvgui-selbsttest"
    teile: list[bytes] = []
    for name, wert in felder.items():
        teile.append(
            (
                f'--{grenze}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{wert}\r\n'
            ).encode()
        )
    for name, (dateiname, inhalt) in dateien.items():
        teile.append(
            (
                f'--{grenze}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{dateiname}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + inhalt
            + b"\r\n"
        )
    teile.append(f"--{grenze}--\r\n".encode())
    return {"Content-Type": f"multipart/form-data; boundary={grenze}"}, b"".join(teile)


def _mini_vorlage() -> bytes:
    xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W}"><w:body>'
        "<w:p><w:r><w:t>Mieter: {{mieter_name}}</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Miete: {{miete_netto}}</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", xml)
    return puffer.getvalue()


def _selbsttest() -> None:
    status, _, _ = antwort("GET", "/", {}, b"")
    if status != 200:
        raise ValueError("Selbsttest: Startseite ist nicht erreichbar")

    kopf, koerper = _multipart_koerper(
        {"mieter_name": "Selbsttest", "miete_netto": "1000"},
        {"vorlage": ("selbsttest.docx", _mini_vorlage())},
    )
    status, _, seite = antwort("POST", "/erstellen", kopf, koerper)
    if status != 200:
        raise ValueError("Selbsttest: Vertrag konnte nicht erstellt werden")
    treffer = re.search(rb"/download/([0-9a-f]{32})", seite)
    if treffer is None:
        raise ValueError("Selbsttest: Download-Link fehlt")

    status, _, vertrag = antwort("GET", f"/download/{treffer.group(1).decode()}", {}, b"")
    if status != 200 or platzhalter(vertrag):
        raise ValueError("Selbsttest: Vertrag ist unvollstaendig")


def main(argv: list[str] | None = None) -> int:
    """Startet die lokale Web-Oberflaeche oder fuehrt den Selbsttest aus."""

    try:
        args = _parser().parse_args(argv)
    except _GuiFehler as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 2
    except SystemExit as fehler:
        return fehler.code if isinstance(fehler.code, int) else 1

    if not 0 <= args.port <= 65535:
        print("Fehler: Port muss zwischen 0 und 65535 liegen", file=sys.stderr)
        return 2

    if args.selbsttest:
        try:
            _selbsttest()
        except Exception as fehler:
            print(f"Selbsttest fehlgeschlagen: {fehler}", file=sys.stderr)
            return 1
        print("Selbsttest OK")
        return 0

    try:
        server = starte(port=args.port)
    except OSError as fehler:
        print(f"Fehler: Server konnte nicht gestartet werden: {fehler}", file=sys.stderr)
        return 1

    print(f"Lokale Oberflaeche: http://127.0.0.1:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
