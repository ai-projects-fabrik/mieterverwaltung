"""Google-Zugriff der App: HTTP, Anmeldung per Loopback, Vorlagen listen und abrufen.

Dieses Modul ist der einzige Ort mit Netzwerkzugriff auf Google (von Menschen gebaut und gemergt).
Die Logik steckt in :mod:`projekt.googleauth` und :mod:`projekt.gdrive`; alle Netzwerkaufrufe laufen
ueber den austauschbaren ``transport``, damit Tests ohne Netz auskommen.
"""

from __future__ import annotations

import http.server
import secrets
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

from projekt.gdrive import STICHWORTE, abruf_anfrage, auswerte_liste, liste_anfrage
from projekt.googleauth import (
    anmelde_url,
    client_pfad,
    code_aus_redirect,
    lade_client_datei,
    lade_token,
    neues_pkce,
    speichere_token,
    token_anfrage_code,
    token_anfrage_refresh,
    token_aus_antwort,
    token_gueltig,
    token_pfad,
)

Transport = Callable[[str, dict[str, str], bytes | None], tuple[int, bytes]]

_ZEITLIMIT = 30
_ANMELDE_WARTEZEIT = 180
_MAX_SEITEN = 20
_FERTIG = (
    "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
    "<title>Mietverwaltung</title></head><body><h1>Fertig</h1>"
    "<p>Die Mietverwaltung ist mit Google verbunden. "
    "Dieses Fenster kann geschlossen werden.</p></body></html>"
)


def senden(
    url: str, kopf: dict[str, str] | None = None, daten: bytes | None = None
) -> tuple[int, bytes]:
    """Sendet GET (ohne ``daten``) oder POST; liefert (Status, Koerper), auch bei Fehlerstatus."""

    if not url.startswith("https://"):
        raise ValueError("Google-Adressen muessen mit https:// beginnen")
    anfrage = urllib.request.Request(url, data=daten, headers=kopf or {})
    try:
        with urllib.request.urlopen(anfrage, timeout=_ZEITLIMIT) as antwort:
            return antwort.status, antwort.read()
    except urllib.error.HTTPError as fehler:
        return fehler.code, fehler.read()
    except (urllib.error.URLError, TimeoutError, OSError) as fehler:
        raise ValueError(f"Google nicht erreichbar: {fehler}") from fehler


def _formular_senden(transport: Transport, url: str, koerper: bytes) -> bytes:
    _, antwort = transport(url, {"Content-Type": "application/x-www-form-urlencoded"}, koerper)
    return antwort


def anmelden(
    client: dict,
    *,
    transport: Transport = senden,
    oeffne: Callable[[str], object] = webbrowser.open,
    jetzt: Callable[[], float] = time.time,
    zufall: Callable[[int], bytes] = secrets.token_bytes,
    wartezeit: float = _ANMELDE_WARTEZEIT,
) -> dict:
    """Meldet einmal im Browser an (Loopback, PKCE) und liefert das neue Token.

    Der lokale Server hoert nur auf 127.0.0.1, nimmt genau eine Antwort mit ``code`` oder ``error``
    entgegen und schliesst danach. ``oeffne`` bekommt die Anmelde-Adresse (Standard: Browser).
    """

    ergebnis: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            abfrage = self.path.partition("?")[2]
            if "code=" not in abfrage and "error=" not in abfrage:
                self.send_response(404)
                self.end_headers()
                return
            ergebnis["abfrage"] = abfrage
            self._antworte(200, _FERTIG)

        def _antworte(self, status: int, seite: str) -> None:
            koerper = seite.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(koerper)))
            self.end_headers()
            self.wfile.write(koerper)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 0.5
    try:
        redirect = f"http://127.0.0.1:{server.server_address[1]}/"
        verifier, challenge = neues_pkce(zufall(32))
        state = secrets.token_urlsafe(16)
        oeffne(anmelde_url(client, redirect, state, challenge))
        ende = time.monotonic() + wartezeit
        while "abfrage" not in ergebnis and time.monotonic() < ende:
            server.handle_request()
    finally:
        server.server_close()
    if "abfrage" not in ergebnis:
        raise ValueError("Anmeldung bei Google nicht rechtzeitig abgeschlossen")
    code = code_aus_redirect(ergebnis["abfrage"], state)
    url, koerper = token_anfrage_code(client, code, verifier, redirect)
    return token_aus_antwort(_formular_senden(transport, url, koerper), jetzt())


def zugriffstoken(
    client: dict,
    token_datei: Path,
    *,
    transport: Transport = senden,
    jetzt: Callable[[], float] = time.time,
) -> str:
    """Liefert ein gueltiges Zugriffstoken (erneuert es); ohne Anmeldung ``ValueError``."""

    token = lade_token(token_datei)
    if token_gueltig(token, jetzt()):
        return token["access_token"]
    if not token:
        raise ValueError("Google ist noch nicht verbunden")
    url, koerper = token_anfrage_refresh(client, token["refresh_token"])
    neu = token_aus_antwort(_formular_senden(transport, url, koerper), jetzt(), token)
    speichere_token(token_datei, neu)
    return neu["access_token"]


def _bearer(zugriff: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {zugriff}"}


def liste_vorlagen_google(
    zugriff: str,
    *,
    stichworte: tuple[str, ...] = STICHWORTE,
    transport: Transport = senden,
) -> list[dict]:
    """Listet passende Google Docs und Word-Dateien (eigene und freigegebene)."""

    gefunden: list[dict] = []
    seite = ""
    for _ in range(_MAX_SEITEN):
        status, antwort = transport(liste_anfrage(seite), _bearer(zugriff), None)
        treffer, seite = auswerte_liste(antwort, stichworte)
        if status != 200:
            raise ValueError(f"Google Drive antwortet mit Status {status}")
        gefunden.extend(treffer)
        if not seite:
            break
    gefunden.sort(key=lambda d: (d["name"].casefold(), d["id"]))
    return gefunden


def hole_vorlage(zugriff: str, datei: dict, *, transport: Transport = senden) -> bytes:
    """Holt die Vorlage als .docx in den Arbeitsspeicher (Google Docs per Export)."""

    status, daten = transport(abruf_anfrage(datei), _bearer(zugriff), None)
    if status != 200:
        raise ValueError(
            f"Vorlage '{datei.get('name', '')}' nicht abrufbar (Google-Status {status})"
        )
    if not daten.startswith(b"PK"):
        raise ValueError(f"Vorlage '{datei.get('name', '')}' ist keine gueltige .docx-Datei")
    return daten


class GoogleQuelle:
    """Vorlagenquelle Google fuer die Oberflaeche (Liste, Abruf, Anmeldung, kurzer Cache)."""

    def __init__(
        self,
        home: str | Path | None = None,
        *,
        transport: Transport = senden,
        oeffne: Callable[[str], object] = webbrowser.open,
        jetzt: Callable[[], float] = time.time,
        stichworte: tuple[str, ...] = STICHWORTE,
        cache_sekunden: float = 60,
        im_hintergrund: bool = True,
        wartezeit: float = _ANMELDE_WARTEZEIT,
    ) -> None:
        self._home = home
        self._transport = transport
        self._oeffne = oeffne
        self._jetzt = jetzt
        self._stichworte = stichworte
        self._cache_sekunden = cache_sekunden
        self._im_hintergrund = im_hintergrund
        self._wartezeit = wartezeit
        self._sperre = threading.Lock()
        self._cache: tuple[float, list[dict]] | None = None
        self._anmeldung: threading.Thread | None = None
        self._anmelde_fehler = ""

    def _angemeldet(self) -> bool:
        return bool(lade_token(token_pfad(self._home)))

    def _anmelde_lauf(self, client: dict) -> None:
        try:
            token = anmelden(
                client,
                transport=self._transport,
                oeffne=self._oeffne,
                jetzt=self._jetzt,
                wartezeit=self._wartezeit,
            )
            speichere_token(token_pfad(self._home), token)
            self._anmelde_fehler = ""
        except (OSError, ValueError) as fehler:
            nicht_fertig = "nicht rechtzeitig" in str(fehler)
            self._anmelde_fehler = (
                "Anmeldung abgebrochen - erneut versuchen" if nicht_fertig else str(fehler)
            )

    def verbinden(self) -> str:
        """Startet die Anmeldung im Browser (nicht blockierend) und liefert eine Meldung."""

        try:
            client = lade_client_datei(client_pfad(self._home))
        except ValueError as fehler:
            return str(fehler)
        with self._sperre:
            if self._anmeldung is not None and self._anmeldung.is_alive():
                return "Die Anmeldung im Browser laeuft bereits."
            self._anmelde_fehler = ""
            if self._im_hintergrund:
                self._anmeldung = threading.Thread(
                    target=self._anmelde_lauf, args=(client,), daemon=True
                )
                self._anmeldung.start()
            else:
                self._anmelde_lauf(client)
        if self._anmelde_fehler:
            return self._anmelde_fehler
        return (
            "Anmeldung im Browser gestartet. Bitte dort zustimmen und danach die Seite neu laden."
        )

    def status(self) -> str:
        """Kurzer Text zum Verbindungsstand fuer die Einstellungen."""

        if not client_pfad(self._home).is_file():
            return f"Google-Zugangsdatei fehlt: {client_pfad(self._home)}"
        if self._anmeldung is not None and self._anmeldung.is_alive():
            return "Anmeldung im Browser laeuft."
        if self._angemeldet():
            return "Mit Google verbunden."
        return "Nicht mit Google verbunden."

    def vorlagen(self) -> tuple[list[dict], list[str]]:
        """Liefert (Dateien, Hinweise); Fehler und fehlende Anmeldung werden zu Hinweisen."""

        try:
            client = lade_client_datei(client_pfad(self._home))
        except ValueError as fehler:
            return [], [
                f"{fehler}. Datei von Google (OAuth-Client Desktop-App) dort ablegen, "
                "siehe docs/google-einrichtung.md."
            ]
        if not self._angemeldet():
            laeuft = self._anmeldung is not None and self._anmeldung.is_alive()
            if laeuft:
                hinweis = (
                    "Google-Anmeldung im Browser laeuft. Bitte dort zustimmen, dann neu laden."
                )
            elif self._anmelde_fehler:
                hinweis = f"{self._anmelde_fehler} (Einstellungen > Mit Google verbinden)"
            else:
                hinweis = "Nicht mit Google verbunden (Einstellungen > Mit Google verbinden)."
            return [], [hinweis]
        jetzt = self._jetzt()
        if self._cache is not None and jetzt - self._cache[0] < self._cache_sekunden:
            return self._cache[1], []
        try:
            zugriff = zugriffstoken(
                client, token_pfad(self._home), transport=self._transport, jetzt=self._jetzt
            )
            dateien = liste_vorlagen_google(
                zugriff, stichworte=self._stichworte, transport=self._transport
            )
        except (OSError, ValueError) as fehler:
            return [], [f"Google-Vorlagen nicht verfuegbar: {fehler}"]
        self._cache = (jetzt, dateien)
        if not dateien:
            return [], [
                "Keine passende Vorlage (Name mit Vertrag oder Protokoll) in Google Drive gefunden."
            ]
        return dateien, []

    def hole(self, kennung: str) -> bytes:
        """Holt die Vorlage mit dieser Datei-id als .docx (nur Dateien aus der Vorlagenliste)."""

        dateien, hinweise = self.vorlagen()
        datei = next((d for d in dateien if d["id"] == kennung), None)
        if datei is None:
            raise ValueError(hinweise[0] if hinweise else "Google-Vorlage nicht gefunden")
        client = lade_client_datei(client_pfad(self._home))
        zugriff = zugriffstoken(
            client, token_pfad(self._home), transport=self._transport, jetzt=self._jetzt
        )
        return hole_vorlage(zugriff, datei, transport=self._transport)
