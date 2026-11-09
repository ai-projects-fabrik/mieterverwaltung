"""Lokaler HTTP-Server um die socketfreie Weboberflaeche aus :mod:`projekt.webapp_einfach`."""

from __future__ import annotations

import argparse
import sys
import tempfile
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import NoReturn

from projekt.einstellungen import einstellungen_pfad
from projekt.webapp_einfach import antwort

_MAX_KOERPER = 1024 * 1024
_HTML_TYP = "text/html; charset=utf-8"
_ERLAUBTE_METHODEN = ("GET", "POST")
_FEHLER_405 = b"<h1>Fehler</h1><p>Methode nicht erlaubt</p>"


class _Eingabefehler(Exception):
    """Fehler in den Kommandozeilenargumenten."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _Eingabefehler(message)


class _Handler(BaseHTTPRequestHandler):
    """Reicht Anfragen an :func:`projekt.webapp_einfach.antwort` weiter."""

    def __init__(self, *args: object, kontext: dict, **kwargs: object) -> None:
        self._kontext = kontext
        super().__init__(*args, **kwargs)

    def _sende(self, status: int, kopf: dict[str, str], koerper: bytes) -> None:
        self.send_response(status)
        for name, wert in kopf.items():
            if str(name).lower() != "content-length":
                self.send_header(str(name), str(wert))
        self.send_header("Content-Length", str(len(koerper)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def _nicht_erlaubt(self) -> None:
        self.close_connection = True
        self._sende(
            405,
            {"Content-Type": _HTML_TYP, "Allow": ", ".join(_ERLAUBTE_METHODEN)},
            _FEHLER_405,
        )

    def _koerper_lesen(self) -> bytes:
        roh = self.headers.get("Content-Length")
        if roh is None:
            return b""

        text = str(roh).strip()
        if not text.isascii() or not text.isdigit():
            raise ValueError("Feld 'Content-Length' ist ungueltig")
        laenge = int(text)

        lesen = min(laenge, _MAX_KOERPER + 1)
        if laenge > _MAX_KOERPER:
            self.close_connection = True
        try:
            return self.rfile.read(lesen) if lesen else b""
        except OSError as fehler:
            raise ValueError("Anfragekoerper konnte nicht gelesen werden") from fehler

    def _beantworte_anfrage(self, methode: str) -> None:
        if methode not in _ERLAUBTE_METHODEN:
            self._nicht_erlaubt()
            return

        try:
            koerper = self._koerper_lesen()
        except ValueError:
            self.close_connection = True
            self._sende(
                400,
                {"Content-Type": _HTML_TYP},
                b"<h1>Fehler</h1><p>Anfrage ungueltig</p>",
            )
            return

        status, kopf, antwort_koerper = antwort(
            methode,
            self.path,
            dict(self.headers.items()),
            koerper,
            self._kontext,
        )
        self._sende(status, kopf, antwort_koerper)

    def do_GET(self) -> None:
        self._beantworte_anfrage("GET")

    def do_POST(self) -> None:
        self._beantworte_anfrage("POST")

    def do_HEAD(self) -> None:
        self._nicht_erlaubt()

    def do_PUT(self) -> None:
        self._nicht_erlaubt()

    def do_PATCH(self) -> None:
        self._nicht_erlaubt()

    def do_DELETE(self) -> None:
        self._nicht_erlaubt()

    def do_OPTIONS(self) -> None:
        self._nicht_erlaubt()

    def do_CONNECT(self) -> None:
        self._nicht_erlaubt()

    def do_TRACE(self) -> None:
        self._nicht_erlaubt()

    def __getattr__(self, name: str) -> object:
        if name.startswith("do_"):
            return self._nicht_erlaubt
        raise AttributeError(name)

    def log_message(self, format: str, *args: object) -> None:
        """Unterdrueckt die Standard-Logausgabe des lokalen Servers."""


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="projekt.webserver", allow_abbrev=False)
    parser.add_argument("--port", type=int, default=8765, help="Port der lokalen Oberflaeche")
    parser.add_argument(
        "--einstellungen",
        default=einstellungen_pfad(),
        help="Pfad zur Einstellungsdatei",
    )
    parser.add_argument(
        "--selbsttest", action="store_true", help="Eingebauten Selbsttest ausfuehren"
    )
    return parser


def _selbsttest() -> None:
    with tempfile.TemporaryDirectory() as ordner:
        kontext = {"einstellungen_datei": Path(ordner) / "einstellungen.json"}
        status, _, koerper = antwort("GET", "/settings", {}, b"", kontext)

    if status != 200:
        raise ValueError("Selbsttest: GET /settings liefert nicht Status 200")
    if not isinstance(koerper, bytes) or b"<form" not in koerper:
        raise ValueError("Selbsttest: GET /settings enthaelt kein Formular")


def starte(kontext: dict, host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    """Bindet den lokalen HTTP-Server an Loopback, ohne ihn zu starten.

    ``host`` darf nur ``127.0.0.1`` oder ``localhost`` sein. ``port`` muss
    zwischen 0 und 65535 liegen; 0 waehlt einen freien Port.
    """

    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Feld 'host' muss '127.0.0.1' oder 'localhost' sein")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Feld 'port' muss zwischen 0 und 65535 liegen")
    return HTTPServer(("127.0.0.1", port), partial(_Handler, kontext=kontext))


def main(argv: list[str] | None = None) -> int:
    """Startet den lokalen Webserver oder fuehrt den Selbsttest aus."""

    try:
        args = _parser().parse_args(argv)
    except _Eingabefehler as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 2
    except SystemExit as fehler:
        return fehler.code if isinstance(fehler.code, int) else 1

    if not 0 <= args.port <= 65535:
        print("Fehler: Feld 'port' muss zwischen 0 und 65535 liegen", file=sys.stderr)
        return 2

    if args.selbsttest:
        try:
            _selbsttest()
        except Exception as fehler:
            print(f"Selbsttest fehlgeschlagen: {fehler}", file=sys.stderr)
            return 1
        print("Selbsttest OK")
        return 0

    kontext = {"einstellungen_datei": Path(args.einstellungen)}
    try:
        server = starte(kontext, host="127.0.0.1", port=args.port)
    except (OSError, ValueError) as fehler:
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
