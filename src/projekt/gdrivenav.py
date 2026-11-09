"""Anfragen und Antworten fuer die Navigation in Google Drive ohne Netzwerk."""

from __future__ import annotations

import json
from urllib.parse import urlencode

from projekt.gdrive import GOOGLE_DOC, WORD

WURZEL = "root"
GETEILT = "geteilt"
ORDNER = "application/vnd.google-apps.folder"

_ABOUT_URL = "https://www.googleapis.com/drive/v3/about"
_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_ID_ZEICHEN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def _kennung(wert: object, feld: str) -> str:
    if not isinstance(wert, str) or not 1 <= len(wert) <= 200:
        raise ValueError(f"Feld '{feld}' muss eine Drive-id mit 1 bis 200 Zeichen sein")
    if any(zeichen not in _ID_ZEICHEN for zeichen in wert):
        raise ValueError(f"Feld '{feld}' darf nur A-Z, a-z, 0-9, _ und - enthalten")
    return wert


def _fehlermeldung(fehler: object) -> str:
    if isinstance(fehler, dict):
        meldung = fehler.get("message")
        if isinstance(meldung, str) and meldung.strip():
            return meldung
    elif isinstance(fehler, str) and fehler.strip():
        return fehler
    return "Unbekannter Fehler der Google Drive API"


def _antwort(antwort: object) -> dict:
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


def _datei(eintrag: object) -> dict | None:
    if not isinstance(eintrag, dict):
        return None
    kennung = eintrag.get("id")
    name = eintrag.get("name")
    mime = eintrag.get("mimeType")
    if not isinstance(kennung, str) or not 1 <= len(kennung) <= 200:
        return None
    if any(zeichen not in _ID_ZEICHEN for zeichen in kennung):
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    if mime not in (GOOGLE_DOC, WORD):
        return None
    return {"id": kennung, "name": name, "mime": mime, "eigene": eintrag.get("ownedByMe") is True}


def konto_anfrage() -> str:
    """Baut die Drive-API-Adresse fuer das angemeldete Google-Konto."""

    return f"{_ABOUT_URL}?fields=user(displayName,emailAddress)"


def auswerte_konto(antwort: bytes) -> str:
    """Liefert die E-Mail-Adresse oder ersatzweise den Anzeigenamen des Kontos.

    Eine fehlende Kontoinformation sowie ungueltiges JSON loesen einen
    ValueError mit dem Feldnamen aus. Ein Fehlerobjekt der API wird mit der
    Google-Meldung weitergereicht.
    """

    daten = _antwort(antwort)
    konto = daten.get("user")
    if not isinstance(konto, dict):
        raise ValueError("Feld 'Konto': Google-Antwort enthaelt kein Konto")
    for feld in ("emailAddress", "displayName"):
        wert = konto.get(feld)
        if isinstance(wert, str) and wert.strip():
            return wert.strip()
    raise ValueError("Feld 'Konto': Google-Antwort enthaelt weder E-Mail noch Anzeigename")


def datei_anfrage(kennung: str) -> str:
    """Baut die Drive-API-Adresse fuer die Metadaten einer einzelnen Datei."""

    geprueft = _kennung(kennung, "id")
    parameter = urlencode({"fields": "id,name,mimeType,ownedByMe", "supportsAllDrives": "true"})
    return f"{_FILES_URL}/{geprueft}?{parameter}"


def auswerte_datei(antwort: bytes) -> dict:
    """Wertet die Metadaten einer Google-Docs- oder Word-Datei aus.

    Liefert ``{"id", "name", "mime", "eigene"}``. Andere Dateitypen und
    unbrauchbare Antworten loesen einen ValueError mit dem Feldnamen aus.
    """

    eintrag = _antwort(antwort)
    kennung = eintrag.get("id")
    if (
        not isinstance(kennung, str)
        or not 1 <= len(kennung) <= 200
        or any(zeichen not in _ID_ZEICHEN for zeichen in kennung)
    ):
        raise ValueError("Feld 'antwort': Datei enthaelt keine gueltige id")
    name = eintrag.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Feld 'antwort': Datei enthaelt keinen gueltigen Namen")
    mime = eintrag.get("mimeType")
    if mime not in (GOOGLE_DOC, WORD):
        raise ValueError("Feld 'antwort': Datei ist kein Google Docs- oder Word-Dokument")
    return {"id": kennung, "name": name, "mime": mime, "eigene": eintrag.get("ownedByMe") is True}


def ordner_anfrage(ordner_id: str = WURZEL, seitentoken: str = "") -> str:
    """Baut die Drive-API-Adresse fuer den Inhalt eines Ordners.

    ``GETEILT`` fragt die mit dem Konto geteilten Dateien ab. Fuer alle anderen
    Ordner-ids gilt eine strenge Zeichenpruefung, damit keine Einschleusung in
    die Drive-Abfrage ``q`` moeglich ist.
    """

    if not isinstance(seitentoken, str):
        raise ValueError("Feld 'seitentoken' muss als Text uebergeben werden")

    typen = f"(mimeType='{ORDNER}' or mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')"
    if ordner_id == GETEILT:
        q = f"sharedWithMe=true and trashed=false and {typen}"
    else:
        geprueft = _kennung(ordner_id, "ordner_id")
        q = f"'{geprueft}' in parents and trashed=false and {typen}"

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
    """Wertet den Inhalt eines Drive-Ordners aus.

    Liefert Unterordner, Google-Docs-/Word-Dateien und den naechsten
    Seitentoken. Beide Listen sind nach Name ohne Beachtung der
    Gross-/Kleinschreibung und danach nach id sortiert; unbrauchbare Eintraege
    und andere Dateitypen entfallen.
    """

    daten = _antwort(antwort)
    eintraege = daten.get("files", [])
    if eintraege is None:
        eintraege = []
    if not isinstance(eintraege, list):
        raise ValueError("Feld 'files' muss eine Liste sein")

    weiter = daten.get("nextPageToken", "")
    if weiter is None:
        weiter = ""
    if not isinstance(weiter, str):
        raise ValueError("Feld 'nextPageToken' muss als Text uebergeben werden")

    ordner: list[dict] = []
    dateien: list[dict] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        if eintrag.get("mimeType") == ORDNER:
            kennung = eintrag.get("id")
            name = eintrag.get("name")
            if not isinstance(kennung, str) or not 1 <= len(kennung) <= 200:
                continue
            if any(zeichen not in _ID_ZEICHEN for zeichen in kennung):
                continue
            if not isinstance(name, str) or not name.strip():
                continue
            ordner.append({"id": kennung, "name": name})
            continue
        datei = _datei(eintrag)
        if datei is not None:
            dateien.append(datei)

    ordner.sort(key=lambda eintrag: (eintrag["name"].casefold(), eintrag["id"]))
    dateien.sort(key=lambda eintrag: (eintrag["name"].casefold(), eintrag["id"]))
    return ordner, dateien, weiter


def suche_in(eintraege: list[dict], text: str) -> list[dict]:
    """Filtert Eintraege nach einem Textstueck im Namen ohne Gross-/Kleinschreibung.

    Der Suchtext wird getrimmt. Ein leerer Suchtext behaelt alle Eintraege.
    """

    if not isinstance(eintraege, list):
        raise ValueError("Feld 'eintraege' muss eine Liste sein")
    if not isinstance(text, str):
        raise ValueError("Feld 'text' muss als Text uebergeben werden")

    gesucht = text.strip().casefold()
    if not gesucht:
        return list(eintraege)
    return [
        eintrag
        for eintrag in eintraege
        if isinstance(eintrag, dict)
        and isinstance(eintrag.get("name"), str)
        and gesucht in eintrag["name"].casefold()
    ]
