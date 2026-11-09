"""Anfragen und Antworten der Google Drive API ohne Netzwerk."""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

GOOGLE_DOC = "application/vnd.google-apps.document"
WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
STICHWORTE: tuple[str, ...] = ("vertrag", "protokoll")

_FILES_URL = "https://www.googleapis.com/drive/v3/files"


def _stichworte_pruefen(stichworte: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(stichworte, tuple):
        raise ValueError("Feld 'stichworte' muss als tuple uebergeben werden")

    geprueft: list[str] = []
    for stichwort in stichworte:
        if not isinstance(stichwort, str):
            raise ValueError("Feld 'stichworte' darf nur Text enthalten")
        wert = stichwort.strip()
        if wert:
            geprueft.append(wert.casefold())
    return tuple(geprueft)


def passt(name: str, stichworte: tuple[str, ...] = STICHWORTE) -> bool:
    """Prueft, ob der Name ein Stichwort als Teilwort enthaelt.

    Gross- und Kleinschreibung werden ueber ``casefold`` ignoriert. Leere
    Stichworte zaehlen nicht; ohne wirksame Stichworte passt jeder Name. Ein
    Name, der kein Text ist, und ungueltige Stichworte loesen einen ValueError
    mit dem Feldnamen aus.
    """

    if not isinstance(name, str):
        raise ValueError("Feld 'name' muss als Text uebergeben werden")

    gesucht = _stichworte_pruefen(stichworte)
    if not gesucht:
        return True

    klein = name.casefold()
    return any(stichwort in klein for stichwort in gesucht)


def liste_anfrage(seitentoken: str = "") -> str:
    """Baut die Drive-API-Adresse fuer die naechste Dateiliste.

    Abgefragt werden nicht geloeschte Google Docs und Word-Dateien, eigene und
    geteilte Dateien. Der Name wird bewusst nicht in ``q`` gefiltert, weil die
    Drive-Suche dort nur Wortanfaenge findet. Ein nicht leerer Seitentoken wird
    als ``pageToken`` angehaengt; ein Wert, der kein Text ist, loest einen
    ValueError aus.
    """

    if not isinstance(seitentoken, str):
        raise ValueError("Feld 'seitentoken' muss als Text uebergeben werden")

    parameter = {
        "q": f"trashed=false and (mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')",
        "fields": "nextPageToken,files(id,name,mimeType,ownedByMe)",
        "pageSize": "1000",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if seitentoken:
        parameter["pageToken"] = seitentoken
    return f"{_FILES_URL}?{urlencode(parameter)}"


def _fehlermeldung(fehler: object) -> str:
    if isinstance(fehler, dict):
        meldung = fehler.get("message")
        if isinstance(meldung, str) and meldung.strip():
            return meldung
    elif isinstance(fehler, str) and fehler.strip():
        return fehler
    return "Unbekannter Fehler der Google Drive API"


def auswerte_liste(
    antwort: bytes,
    stichworte: tuple[str, ...] = STICHWORTE,
) -> tuple[list[dict], str]:
    """Wertet eine Dateiliste der Drive-API aus.

    Liefert die passenden Dateien als ``{"id", "name", "mime", "eigene"}``,
    sortiert nach Name ohne Beachtung der Gross-/Kleinschreibung und danach
    nach id, sowie den naechsten Seitentoken (leer am Ende). Unbrauchbare
    Eintraege werden uebergangen. Ungueltiges JSON, eine Antwort, die kein
    JSON-Objekt ist, oder ein Fehlerobjekt der API loesen einen ValueError aus.
    """

    if not isinstance(antwort, bytes):
        raise ValueError("Feld 'antwort' muss als bytes uebergeben werden")
    gesucht = _stichworte_pruefen(stichworte)

    try:
        daten = json.loads(antwort)
    except (json.JSONDecodeError, UnicodeDecodeError) as fehler:
        raise ValueError("Feld 'antwort' enthaelt kein gueltiges JSON") from fehler
    if not isinstance(daten, dict):
        raise ValueError("Feld 'antwort' ist kein JSON-Objekt")

    if "error" in daten:
        raise ValueError(f"Feld 'error': Google Drive meldet: {_fehlermeldung(daten['error'])}")

    dateien = daten.get("files", [])
    if dateien is None:
        dateien = []
    if not isinstance(dateien, list):
        raise ValueError("Feld 'files' muss eine Liste sein")

    seite = daten.get("nextPageToken", "")
    if seite is None:
        seite = ""
    if not isinstance(seite, str):
        raise ValueError("Feld 'nextPageToken' muss als Text uebergeben werden")

    treffer: list[dict] = []
    for eintrag in dateien:
        if not isinstance(eintrag, dict):
            continue
        kennung = eintrag.get("id")
        name = eintrag.get("name")
        mime = eintrag.get("mimeType")
        if not isinstance(kennung, str) or not kennung.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        if mime not in (GOOGLE_DOC, WORD):
            continue
        if not passt(name, gesucht):
            continue
        treffer.append(
            {
                "id": kennung,
                "name": name,
                "mime": mime,
                "eigene": eintrag.get("ownedByMe") is True,
            }
        )

    treffer.sort(key=lambda datei: (datei["name"].casefold(), datei["id"]))
    return treffer, seite


def abruf_anfrage(datei: dict) -> str:
    """Baut die Drive-API-Adresse zum Herunterladen einer Vorlage.

    Google Docs werden als Word-Datei exportiert, Word-Dateien direkt
    abgerufen. Die Datei-id wird vollstaendig URL-kodiert. Eine fehlende oder
    ungueltige id beziehungsweise ein nicht unterstuetzter MIME-Typ loesen
    einen ValueError mit dem Feldnamen aus.
    """

    if not isinstance(datei, dict):
        raise ValueError("Feld 'id' fehlt; die Datei muss als dict uebergeben werden")

    kennung = datei.get("id")
    if not isinstance(kennung, str) or not kennung.strip():
        raise ValueError("Feld 'id' muss als nicht leerer Text uebergeben werden")

    mime = datei.get("mime")
    if mime == GOOGLE_DOC:
        parameter = urlencode({"mimeType": WORD})
        return f"{_FILES_URL}/{quote(kennung, safe='')}/export?{parameter}"
    if mime == WORD:
        parameter = urlencode({"alt": "media", "supportsAllDrives": "true"})
        return f"{_FILES_URL}/{quote(kennung, safe='')}?{parameter}"
    raise ValueError("Feld 'mime' muss ein Google Doc oder eine Word-Datei bezeichnen")
