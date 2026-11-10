"""Navigation in Google Drive ohne Netzwerk.

Das Modul baut die Anfragen fuer Konto, einzelne Dateien und Ordnerinhalte der
Drive API und wertet deren Antworten aus. Den HTTP-Transport uebernimmt
``googlehttp.py``; hier kommt kein Netzwerkzugriff vor.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from projekt.gdrive import GOOGLE_DOC, WORD

WURZEL = "root"
GETEILT = "geteilt"
ORDNER = "application/vnd.google-apps.folder"

_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_ABOUT_URL = "https://www.googleapis.com/drive/v3/about"
_ID_MUSTER = re.compile(r"[A-Za-z0-9_-]{1,200}")
_DATEITYPEN = (GOOGLE_DOC, WORD)


def _kennung_pruefen(wert: object, feld: str) -> str:
    if not isinstance(wert, str) or _ID_MUSTER.fullmatch(wert) is None:
        raise ValueError(
            f"Feld '{feld}' muss eine Drive-Kennung aus A-Za-z0-9_- (1 bis 200 Zeichen) sein"
        )
    return wert


def _fehlermeldung(fehler: object) -> str:
    if isinstance(fehler, dict):
        meldung = fehler.get("message")
        if isinstance(meldung, str) and meldung.strip():
            return meldung
    elif isinstance(fehler, str) and fehler.strip():
        return fehler
    return "Unbekannter Fehler der Google Drive API"


def _lade_json(antwort: bytes) -> dict:
    if not isinstance(antwort, bytes):
        raise ValueError("Feld 'antwort' muss als bytes uebergeben werden")
    try:
        daten = json.loads(antwort)
    except (json.JSONDecodeError, UnicodeDecodeError) as fehler:
        raise ValueError("Feld 'antwort' enthaelt kein gueltiges JSON") from fehler
    if not isinstance(daten, dict):
        raise ValueError("Feld 'antwort' ist kein JSON-Objekt")
    if "error" in daten:
        raise ValueError(f"Feld 'error': Google Drive meldet: {_fehlermeldung(daten['error'])}")
    return daten


def konto_anfrage() -> str:
    """Baut die Drive-API-Adresse fuer das angemeldete Konto."""

    return f"{_ABOUT_URL}?fields=user(displayName,emailAddress)"


def auswerte_konto(antwort: bytes) -> str:
    """Liefert die E-Mail-Adresse des Kontos, sonst den getrimmten Anzeigenamen.

    Fehlt beides, ist die Antwort kein JSON-Objekt oder meldet die API einen
    Fehler, entsteht ein ValueError mit dem Feldnamen.
    """

    daten = _lade_json(antwort)
    benutzer = daten.get("user")
    if not isinstance(benutzer, dict):
        raise ValueError("Feld 'Konto' enthaelt weder E-Mail-Adresse noch Anzeigename")

    email = benutzer.get("emailAddress")
    if isinstance(email, str) and email.strip():
        return email.strip()

    name = benutzer.get("displayName")
    if isinstance(name, str) and name.strip():
        return name.strip()
    raise ValueError("Feld 'Konto' enthaelt weder E-Mail-Adresse noch Anzeigename")


def datei_anfrage(kennung: str) -> str:
    """Baut die Drive-API-Adresse fuer eine einzelne Datei.

    Die Kennung wird gegen das Drive-Id-Muster geprueft, damit keine fremden
    Zeichen in die Abfrage gelangen koennen.
    """

    datei_id = _kennung_pruefen(kennung, "id")
    parameter = {
        "fields": "id,name,mimeType,ownedByMe",
        "supportsAllDrives": "true",
    }
    return f"{_FILES_URL}/{datei_id}?{urlencode(parameter)}"


def _datei_aus_eintrag(eintrag: dict) -> dict | None:
    kennung = eintrag.get("id")
    name = eintrag.get("name")
    mime = eintrag.get("mimeType")
    if not isinstance(kennung, str) or _ID_MUSTER.fullmatch(kennung) is None:
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    if mime not in _DATEITYPEN:
        return None
    return {
        "id": kennung,
        "name": name,
        "mime": mime,
        "eigene": eintrag.get("ownedByMe") is True,
    }


def auswerte_datei(antwort: bytes) -> dict:
    """Wertet eine einzelne Datei der Drive-API aus.

    Liefert ``{"id", "name", "mime", "eigene"}``. Nur Google Docs und
    Word-Dateien sind zulaessig.
    """

    daten = _lade_json(antwort)
    datei = _datei_aus_eintrag(daten)
    if datei is not None:
        return datei

    kennung = daten.get("id")
    if not isinstance(kennung, str) or _ID_MUSTER.fullmatch(kennung) is None:
        raise ValueError("Feld 'id': ungueltige Datei ohne gueltige Drive-Kennung")
    name = daten.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Feld 'name' der Datei darf nicht leer sein")
    raise ValueError("Feld 'mimeType': nur Google Docs und Word-Dateien sind zulaessig")


def _dateitypen_filter() -> str:
    return f"(mimeType='{ORDNER}' or mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')"


def ordner_anfrage(ordner_id: str = WURZEL, seitentoken: str = "") -> str:
    """Baut die Drive-API-Adresse fuer den Inhalt eines Ordners.

    ``GETEILT`` fragt die mit dem Konto geteilten Dateien ab. Ein nicht leerer
    Seitentoken wird als ``pageToken`` angehaengt.
    """

    kennung = _kennung_pruefen(ordner_id, "ordner_id")
    if not isinstance(seitentoken, str):
        raise ValueError("Feld 'seitentoken' muss als Text uebergeben werden")

    typen = _dateitypen_filter()
    if kennung == GETEILT:
        q = f"sharedWithMe=true and trashed=false and {typen}"
    else:
        q = f"'{kennung}' in parents and trashed=false and {typen}"

    parameter = {
        "q": q,
        "fields": "nextPageToken,files(id,name,mimeType,ownedByMe)",
        "pageSize": "200",
        "orderBy": "folder,name",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if seitentoken:
        parameter["pageToken"] = seitentoken
    return f"{_FILES_URL}?{urlencode(parameter)}"


def auswerte_ordner(antwort: bytes) -> tuple[list[dict], list[dict], str]:
    """Trennt eine Ordnerantwort in Unterordner, Dateien und Seitentoken.

    Unterordner enthalten ``id`` und ``name``; Dateien haben die Form aus
    :func:`auswerte_datei`. Beide Listen sind nach Name (ohne Beachtung der
    Gross-/Kleinschreibung) und danach nach id sortiert. Unbrauchbare Eintraege
    und andere Dateitypen entfallen.
    """

    daten = _lade_json(antwort)

    dateien_roh = daten.get("files", [])
    if dateien_roh is None:
        dateien_roh = []
    if not isinstance(dateien_roh, list):
        raise ValueError("Feld 'files' muss eine Liste sein")

    seite = daten.get("nextPageToken", "")
    if seite is None:
        seite = ""
    if not isinstance(seite, str):
        raise ValueError("Feld 'nextPageToken' muss als Text uebergeben werden")

    ordner: list[dict] = []
    dateien: list[dict] = []
    for eintrag in dateien_roh:
        if not isinstance(eintrag, dict):
            continue
        kennung = eintrag.get("id")
        name = eintrag.get("name")
        mime = eintrag.get("mimeType")
        if not isinstance(kennung, str) or _ID_MUSTER.fullmatch(kennung) is None:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        if mime == ORDNER:
            ordner.append({"id": kennung, "name": name})
        elif mime in _DATEITYPEN:
            dateien.append(
                {
                    "id": kennung,
                    "name": name,
                    "mime": mime,
                    "eigene": eintrag.get("ownedByMe") is True,
                }
            )

    ordner.sort(key=lambda eintrag: (eintrag["name"].casefold(), eintrag["id"]))
    dateien.sort(key=lambda eintrag: (eintrag["name"].casefold(), eintrag["id"]))
    return ordner, dateien, seite


def suche_in(eintraege: list[dict], text: str) -> list[dict]:
    """Filtert Eintraege nach einem Namensteil ohne Gross-/Kleinschreibung.

    Der Suchtext wird getrimmt. Ein leerer Text behaelt alle Eintraege.
    Eintraege ohne Textnamen werden uebergangen.
    """

    if not isinstance(eintraege, list):
        raise ValueError("Feld 'eintraege' muss eine Liste sein")
    if not isinstance(text, str):
        raise ValueError("Feld 'text' muss als Text uebergeben werden")

    gesucht = text.strip().casefold()
    if not gesucht:
        return list(eintraege)

    treffer: list[dict] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        name = eintrag.get("name")
        if isinstance(name, str) and gesucht in name.casefold():
            treffer.append(eintrag)
    return treffer
