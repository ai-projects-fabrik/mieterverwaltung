"""Google-Anmeldung fuer installierte Apps ohne Netzwerkzugriff.

Das Modul prueft die von Google heruntergeladene Client-Datei, baut die
Anmelde- und Token-Anfragen nach OAuth 2.0 mit PKCE und verwaltet die lokale
Token-Datei. Den eigentlichen HTTP-Transport und den Loopback-Server baut
``googlehttp.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

SCOPE = "https://www.googleapis.com/auth/drive.readonly"

_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_CLIENT_DATEI = "google-client.json"
_TOKEN_DATEI = "google-token.json"
_LOOPBACK_PRAEFIXE = ("http://127.0.0.1:", "http://localhost:")


def _text(wert: object, feld: str) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
    text = wert.strip()
    if not text:
        raise ValueError(f"Feld '{feld}' darf nicht leer sein")
    return text


def _https_adresse(wert: object, feld: str) -> str:
    text = _text(wert, feld)
    if not text.startswith("https://"):
        raise ValueError(f"Feld '{feld}' muss mit https:// beginnen")
    return text


def _als_pfad(wert: str | Path, feld: str) -> Path:
    try:
        return Path(wert)
    except TypeError as fehler:
        raise ValueError(f"Feld '{feld}' muss ein Dateipfad sein") from fehler


def _home_pfad(home: str | Path | None) -> Path:
    if home is None:
        return Path.home()
    return _als_pfad(home, "home")


def _anmelde_werte(client: object) -> tuple[str, str]:
    if not isinstance(client, dict):
        raise ValueError("client muss ein dict mit den Google-Zugangsdaten sein")
    return _text(client.get("client_id"), "client_id"), _https_adresse(
        client.get("auth_uri"), "auth_uri"
    )


def _token_ziel(client: object) -> tuple[str, str, str]:
    if not isinstance(client, dict):
        raise ValueError("client muss ein dict mit den Google-Zugangsdaten sein")
    return (
        _text(client.get("client_id"), "client_id"),
        _text(client.get("client_secret"), "client_secret"),
        _https_adresse(client.get("token_uri"), "token_uri"),
    )


def _redirect_uri(redirect_uri: object) -> str:
    text = _text(redirect_uri, "redirect_uri")
    if not text.startswith(_LOOPBACK_PRAEFIXE):
        raise ValueError(
            "Feld 'redirect_uri' muss mit http://127.0.0.1: oder http://localhost: beginnen"
        )
    return text


def lade_client(text: str) -> dict[str, str]:
    """Liest die Google-Client-Datei und liefert die benoetigten Zugangsdaten.

    Erwartet den Inhalt einer OAuth-Client-Datei vom Typ *Desktop-App* mit dem
    Bereich ``installed``. Fehlende oder ungueltige Felder sowie kein JSON
    loesen einen ValueError mit dem Feldnamen aus.
    """

    if not isinstance(text, str):
        raise ValueError("Client-Datei muss als Text uebergeben werden")
    try:
        daten = json.loads(text)
    except json.JSONDecodeError as fehler:
        raise ValueError(f"Client-Datei enthaelt kein gueltiges JSON: {fehler.msg}") from fehler

    if not isinstance(daten, dict):
        raise ValueError("Client-Datei muss ein JSON-Objekt mit dem Bereich 'installed' sein")
    installiert = daten.get("installed")
    if not isinstance(installiert, dict):
        raise ValueError("Client-Datei enthaelt keinen Bereich 'installed'")

    client_id = _text(installiert.get("client_id"), "client_id")
    client_secret = _text(installiert.get("client_secret"), "client_secret")
    auth_uri = _https_adresse(installiert.get("auth_uri", _AUTH_URI), "auth_uri")
    token_uri = _https_adresse(installiert.get("token_uri", _TOKEN_URI), "token_uri")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": auth_uri,
        "token_uri": token_uri,
    }


def neues_pkce(zufall: bytes) -> tuple[str, str]:
    """Baut aus Zufallsbytes einen PKCE-Verifier und dessen S256-Challenge.

    ``zufall`` muss mindestens 32 Bytes enthalten. Beide Rueckgabewerte sind
    base64url-kodiert und enthalten kein Auffuellzeichen ``=``.
    """

    if not isinstance(zufall, bytes):
        raise ValueError("Feld 'zufall' muss als bytes uebergeben werden")
    if len(zufall) < 32:
        raise ValueError("Feld 'zufall' muss mindestens 32 Bytes enthalten")

    verifier = base64.urlsafe_b64encode(zufall).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def anmelde_url(client: dict, redirect_uri: str, state: str, challenge: str) -> str:
    """Baut die Google-Anmeldeadresse fuer den Loopback-Flow mit PKCE.

    Der Redirect muss auf ``127.0.0.1`` oder ``localhost`` zeigen. Ungueltige
    Zugangsdaten, ein leerer ``state`` oder eine fehlende Challenge loesen
    einen ValueError aus.
    """

    client_id, auth_uri = _anmelde_werte(client)
    redirect = _redirect_uri(redirect_uri)
    state_text = _text(state, "state")
    challenge_text = _text(challenge, "code_challenge")
    parameter = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPE,
        "state": state_text,
        "code_challenge": challenge_text,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    teile = urlsplit(auth_uri)
    vorhanden = parse_qsl(teile.query, keep_blank_values=True)
    query = urlencode([*vorhanden, *parameter.items()])
    return urlunsplit((teile.scheme, teile.netloc, teile.path, query, teile.fragment))


def code_aus_redirect(abfrage: str, state: str) -> str:
    """Liest den Autorisierungscode aus der Redirect-Abfrage.

    Ein Fehler von Google, ein anderer oder fehlender ``state`` sowie ein
    fehlender Code loesen einen ValueError mit klarer Meldung aus.
    """

    if not isinstance(abfrage, str):
        raise ValueError("Redirect-Abfrage muss als Text uebergeben werden")
    state_text = _text(state, "state")
    werte = parse_qs(abfrage.lstrip("?"), keep_blank_values=True)

    if "error" in werte:
        fehler = werte["error"][0].strip() or "unbekannt"
        beschreibung = werte.get("error_description", [""])[0]
        zusatz = f": {beschreibung}" if isinstance(beschreibung, str) and beschreibung else ""
        raise ValueError(f"Google-Anmeldung wurde abgelehnt ({fehler}){zusatz}")

    zurueck = werte.get("state", [])
    if not zurueck or zurueck[0] != state_text:
        raise ValueError("Feld 'state' fehlt oder passt nicht zur Anmeldung")

    codes = werte.get("code", [])
    if not codes or not codes[0].strip():
        raise ValueError("Feld 'code' fehlt in der Redirect-Abfrage")
    return codes[0]


def token_anfrage_code(
    client: dict, code: str, verifier: str, redirect_uri: str
) -> tuple[str, bytes]:
    """Baut die Token-Anfrage zum Tauschen des Autorisierungscodes.

    Liefert die Token-Adresse und den formular-kodierten Anfragekoerper als
    bytes. Fehlende Werte loesen einen ValueError mit dem Feldnamen aus.
    """

    client_id, client_secret, token_uri = _token_ziel(client)
    code_text = _text(code, "code")
    verifier_text = _text(verifier, "code_verifier")
    redirect = _redirect_uri(redirect_uri)
    parameter = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code_text,
        "code_verifier": verifier_text,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }
    return token_uri, urlencode(parameter).encode("utf-8")


def token_anfrage_refresh(client: dict, refresh_token: str) -> tuple[str, bytes]:
    """Baut die Token-Anfrage zum Erneuern eines abgelaufenen Tokens.

    Liefert die Token-Adresse und den formular-kodierten Anfragekoerper als
    bytes. Ein leerer Refresh-Token loest einen ValueError aus.
    """

    client_id, client_secret, token_uri = _token_ziel(client)
    refresh = _text(refresh_token, "refresh_token")
    parameter = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }
    return token_uri, urlencode(parameter).encode("utf-8")


def token_aus_antwort(antwort: bytes, jetzt: float, alt: dict | None = None) -> dict:
    """Prueft eine Token-Antwort und liefert Access-Token, Refresh-Token und Ablauf.

    ``expires_in`` wird mit der aktuellen Zeit zu ``ablauf`` addiert; fehlt
    der Wert, gelten 3600 Sekunden. Fehlt ``refresh_token`` in der Antwort,
    wird er aus ``alt`` uebernommen. Fehler von Google und ungueltige Werte
    loesen einen ValueError mit Feldnamen aus.
    """

    if not isinstance(antwort, (bytes, bytearray)):
        raise ValueError("Token-Antwort muss als bytes uebergeben werden")
    try:
        daten = json.loads(bytes(antwort).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as fehler:
        raise ValueError("Token-Antwort enthaelt kein gueltiges JSON") from fehler
    if not isinstance(daten, dict):
        raise ValueError("Token-Antwort muss ein JSON-Objekt sein")

    if "error" in daten:
        fehler = daten["error"]
        beschreibung = daten.get("error_description")
        text = str(fehler) if isinstance(fehler, str) and fehler else "unbekannt"
        zusatz = f": {beschreibung}" if isinstance(beschreibung, str) and beschreibung else ""
        raise ValueError(f"Google-Token-Anfrage fehlgeschlagen ({text}){zusatz}")

    access_token = _text(daten.get("access_token"), "access_token")
    if "expires_in" in daten:
        expires_in = daten["expires_in"]
        if (
            isinstance(expires_in, bool)
            or not isinstance(expires_in, (int, float))
            or expires_in <= 0
        ):
            raise ValueError("Feld 'expires_in' muss eine positive Zahl sein")
    else:
        expires_in = 3600

    if "refresh_token" in daten:
        refresh_token = _text(daten["refresh_token"], "refresh_token")
    else:
        if not isinstance(alt, dict):
            raise ValueError("Feld 'refresh_token' fehlt und ist auch nicht gespeichert")
        refresh_token = _text(alt.get("refresh_token"), "refresh_token")

    if isinstance(jetzt, bool) or not isinstance(jetzt, (int, float)):
        raise ValueError("Feld 'jetzt' muss eine Zahl sein")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "ablauf": jetzt + expires_in,
    }


def token_gueltig(token: object, jetzt: float, puffer: float = 60) -> bool:
    """Sagt, ob ein Access-Token noch laenger als ``puffer`` Sekunden gilt.

    Ungueltige Token-Objekte und fehlende Werte ergeben ``False`` statt eines
    Fehlers. Der Puffer verhindert, dass ein Token waehrend einer Anfrage
    ablaeuft.
    """

    if not isinstance(token, dict):
        return False
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        return False
    ablauf = token.get("ablauf")
    if isinstance(ablauf, bool) or not isinstance(ablauf, (int, float)):
        return False
    if isinstance(jetzt, bool) or not isinstance(jetzt, (int, float)):
        return False
    if isinstance(puffer, bool) or not isinstance(puffer, (int, float)):
        return False
    return ablauf > jetzt + puffer


def client_pfad(home: str | Path | None = None) -> Path:
    """Liefert den festen Pfad der Google-Client-Datei im Benutzerordner.

    Das Ergebnis ist ``<home>/.mieterverwaltung/google-client.json``. Ohne
    ``home`` wird der Benutzerordner verwendet; es wird nichts angelegt.
    """

    return _home_pfad(home) / ".mieterverwaltung" / _CLIENT_DATEI


def lade_client_datei(pfad: str | Path) -> dict[str, str]:
    """Liest die Google-Client-Datei am angegebenen Pfad.

    Eine fehlende oder nicht lesbare Datei loest einen ValueError aus, der den
    Dateinamen ``google-client.json`` und den Pfad nennt. Inhaltliche Fehler
    werden von :func:`lade_client` gemeldet.
    """

    datei = _als_pfad(pfad, "pfad")
    try:
        text = datei.read_text(encoding="utf-8")
    except FileNotFoundError as fehler:
        raise ValueError(f"Client-Datei '{_CLIENT_DATEI}' fehlt: '{datei}'") from fehler
    except (OSError, UnicodeError) as fehler:
        raise ValueError(
            f"Client-Datei '{_CLIENT_DATEI}' unter '{datei}' konnte nicht gelesen werden: {fehler}"
        ) from fehler
    return lade_client(text)


def token_pfad(home: str | Path | None = None) -> Path:
    """Liefert den festen Pfad der Google-Token-Datei im Benutzerordner.

    Das Ergebnis ist ``<home>/.mieterverwaltung/google-token.json``. Ohne
    ``home`` wird der Benutzerordner verwendet; es wird nichts angelegt.
    """

    return _home_pfad(home) / ".mieterverwaltung" / _TOKEN_DATEI


def lade_token(pfad: str | Path) -> dict:
    """Liest die lokale Token-Datei; fehlende oder unbrauchbare Dateien ergeben ``{}``.

    Als brauchbar gilt ein JSON-Objekt mit einem nicht leeren ``refresh_token``.
    Lesefehler, ungueltiges JSON und falsche Strukturen werden bewusst nicht
    als Fehler nach aussen gegeben, damit die App eine neue Anmeldung starten
    kann.
    """

    datei = _als_pfad(pfad, "pfad")
    try:
        text = datei.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    try:
        daten = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(daten, dict):
        return {}
    refresh_token = daten.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        return {}
    return daten


def speichere_token(pfad: str | Path, token: dict) -> None:
    """Prueft und schreibt die Token-Datei atomar als UTF-8-JSON.

    Der Token muss ein dict mit nicht leerem ``refresh_token`` sein. Fehlende
    Ordner werden angelegt. Bei einem Fehler bleibt eine vorhandene Datei
    unveraendert und es bleiben keine Temp-Dateien zurueck.
    """

    ziel = _als_pfad(pfad, "pfad")
    if not isinstance(token, dict):
        raise ValueError("Feld 'refresh_token' fehlt: Token muss ein dict sein")
    refresh_token = token.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise ValueError("Feld 'refresh_token' fehlt oder ist leer")

    try:
        inhalt = (json.dumps(token, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
            "utf-8"
        )
    except (TypeError, ValueError, UnicodeError) as fehler:
        raise ValueError("Token konnte nicht als JSON serialisiert werden") from fehler

    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        raise ValueError(f"Ordner fuer Token-Datei '{ziel.parent}' ist nicht nutzbar") from fehler

    temp_pfad: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=ziel.parent,
            prefix=f".{ziel.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_pfad = Path(temp.name)
            temp.write(inhalt)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_pfad, ziel)
        temp_pfad = None
    except OSError as fehler:
        raise ValueError(f"Token-Datei '{ziel}' konnte nicht geschrieben werden") from fehler
    finally:
        if temp_pfad is not None:
            try:
                temp_pfad.unlink(missing_ok=True)
            except OSError:
                pass
