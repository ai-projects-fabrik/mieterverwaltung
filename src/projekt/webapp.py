"""Routing und Formularverarbeitung der lokalen Weboberflaeche ohne Socket."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import parse_qsl

from projekt.ablage import liste_vorlagen
from projekt.auftraege import erstelle_protokoll, erstelle_vertrag
from projekt.einstellungen import (
    EINSTELLUNGEN_FELDER,
    lade_einstellungen,
    normalisiere_einstellungen,
    ordner,
    speichere_einstellungen,
)
from projekt.objekte import entferne_objekt, lade_objekte, setze_objekt, speichere_objekte
from projekt.seiten import (
    ergebnis,
    formular_mietvertrag,
    formular_protokoll,
    formular_settings,
    rahmen,
)

_HTML_TYP = "text/html; charset=utf-8"
_MAX_KOERPER = 1024 * 1024
_ORTE = ("lokal", "drive")
_NEU_FELDER = ("id", "bezeichnung", "miete_netto", "nebenkosten", "kaution")
_SETTINGS_HINWEIS = (
    "Keine Einstellungen gesetzt. Bitte zuerst im Tab Settings die Ordner "
    "konfigurieren, insbesondere vorlagen_lokal."
)


class _ZuGross(Exception):
    """Der Anfragekoerper ueberschreitet die erlaubte Groesse."""


def _kopfwert(kopf: object, name: str) -> str:
    if not isinstance(kopf, dict):
        return ""
    for schluessel, wert in kopf.items():
        if str(schluessel).lower() == name.lower():
            return str(wert)
    return ""


def _einstellungen_datei(kontext: object) -> Path:
    if not isinstance(kontext, dict):
        raise ValueError("kontext muss ein dict sein")
    datei = kontext.get("einstellungen_datei")
    if not isinstance(datei, (str, Path)) or not str(datei).strip():
        raise ValueError("Feld 'einstellungen_datei' ist nicht gesetzt")
    return Path(datei)


def _lese_einstellungen(kontext: object) -> dict[str, str]:
    try:
        return lade_einstellungen(_einstellungen_datei(kontext))
    except (OSError, TypeError, ValueError):
        return {}


def _lese_objekte(einstellungen: dict[str, str]) -> list[dict[str, str]]:
    datei = einstellungen.get("objekte_datei")
    if not isinstance(datei, str) or not datei.strip():
        return []
    try:
        return lade_objekte(datei.strip())
    except (OSError, TypeError, ValueError):
        return []


def _lese_vorlagen(einstellungen: dict[str, str]) -> dict[str, list[str]]:
    ergebnis_: dict[str, list[str]] = {}
    for ort in _ORTE:
        try:
            ergebnis_[ort] = liste_vorlagen(ordner(einstellungen, "vorlagen", ort))
        except (OSError, TypeError, ValueError):
            ergebnis_[ort] = []
    return ergebnis_


def _html(status: int, inhalt: str) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": _HTML_TYP}, inhalt.encode("utf-8")


def _fehler(status: int, meldung: str) -> tuple[int, dict[str, str], bytes]:
    return _html(status, f"<h1>Fehler</h1><p>{escape(meldung)}</p>")


def _formular(kopf: object, koerper: object) -> dict[str, str]:
    if not isinstance(koerper, bytes):
        raise ValueError("Anfragekoerper muss als bytes uebergeben werden")
    if len(koerper) > _MAX_KOERPER:
        raise _ZuGross

    content_type = _kopfwert(kopf, "Content-Type")
    haupttyp = content_type.split(";", 1)[0].strip().lower()
    if haupttyp != "application/x-www-form-urlencoded":
        raise ValueError("Content-Type muss application/x-www-form-urlencoded sein")

    try:
        text = koerper.decode("utf-8")
        paare = parse_qsl(
            text,
            keep_blank_values=True,
            encoding="utf-8",
            errors="strict",
            strict_parsing=False,
        )
    except (UnicodeDecodeError, ValueError) as fehler:
        raise ValueError("Formulardaten sind kein gueltiges UTF-8") from fehler

    daten: dict[str, str] = {}
    for name, wert in paare:
        daten.setdefault(name, wert)
    return daten


def _seite(aktiv: str, inhalt: str) -> tuple[int, dict[str, str], bytes]:
    return _html(200, rahmen(aktiv, inhalt))


def _get_seite(kontext: object, pfad: str) -> tuple[int, dict[str, str], bytes]:
    einstellungen = _lese_einstellungen(kontext)
    objekte = _lese_objekte(einstellungen)
    vorlagen = _lese_vorlagen(einstellungen)
    if pfad == "/mietvertrag":
        return _seite("mietvertrag", formular_mietvertrag(objekte, vorlagen))
    if pfad == "/protokoll":
        return _seite("protokoll", formular_protokoll(objekte, vorlagen))
    return _seite("settings", formular_settings(einstellungen, objekte))


def _auftrag_seite(
    aktiv: str,
    form: dict[str, str],
    kontext: object,
    *,
    protokoll: bool,
) -> tuple[int, dict[str, str], bytes]:
    einstellungen = _lese_einstellungen(kontext)
    try:
        if not einstellungen:
            raise ValueError(_SETTINGS_HINWEIS)
        erstellen = erstelle_protokoll if protokoll else erstelle_vertrag
        auftrag = erstellen(form, {"einstellungen": einstellungen})
    except (TypeError, ValueError) as fehler:
        meldung = str(fehler) or _SETTINGS_HINWEIS
        objekte = _lese_objekte(einstellungen)
        vorlagen = _lese_vorlagen(einstellungen)
        if protokoll:
            inhalt = formular_protokoll(objekte, vorlagen, form, meldung)
        else:
            inhalt = formular_mietvertrag(objekte, vorlagen, form, meldung)
        return _html(400, rahmen(aktiv, inhalt))

    dateien = list(auftrag["dateien"])
    if auftrag["pdf_auftrag"] is not None:
        dateien.append(auftrag["pdf_auftrag"])
    text = "Dateien angelegt" if protokoll else auftrag["bericht"]
    titel = "Uebergabeprotokoll erstellt" if protokoll else "Mietvertrag erstellt"
    inhalt = ergebnis(titel, text, dateien, auftrag["hinweis"])
    return _html(200, rahmen(aktiv, inhalt))


def _settings_werte(form: dict[str, str]) -> dict[str, str]:
    return {
        feld: form[feld]
        for feld in EINSTELLUNGEN_FELDER
        if feld in form and isinstance(form[feld], str)
    }


def _settings_seite(
    einstellungen: dict[str, str],
    objekte: list[dict[str, str]],
    meldung: str = "",
    status: int = 200,
) -> tuple[int, dict[str, str], bytes]:
    return _html(status, rahmen("settings", formular_settings(einstellungen, objekte, meldung)))


def _dateiinhalt(pfad: str) -> bytes | None:
    try:
        return Path(pfad).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as fehler:
        raise ValueError(f"Objektdatei '{pfad}' konnte nicht gelesen werden") from fehler


def _objektdatei_zuruecksetzen(pfad: str, inhalt: bytes | None) -> None:
    try:
        if inhalt is None:
            Path(pfad).unlink(missing_ok=True)
        else:
            Path(pfad).write_bytes(inhalt)
    except OSError:
        pass


def _settings_speichern(form: dict[str, str], kontext: object) -> tuple[int, dict[str, str], bytes]:
    rohe_einstellungen = _settings_werte(form)
    aktuelle_einstellungen = _lese_einstellungen(kontext)
    objekte: list[dict[str, str]] | None = None
    objekte_vorher: bytes | None = None
    objekte_geschrieben = False

    try:
        neue_einstellungen = normalisiere_einstellungen(rohe_einstellungen)
        neu = {
            feld: form.get(f"neu_{feld}", "").strip()
            for feld in _NEU_FELDER
            if form.get(f"neu_{feld}", "").strip()
        }
        entfernen = form.get("entfernen", "").strip()
        objekte_datei = neue_einstellungen.get("objekte_datei")

        if neu or entfernen:
            if not objekte_datei:
                raise ValueError("Feld 'objekte_datei' ist nicht gesetzt")
            objekte = lade_objekte(objekte_datei)
            if neu:
                objekte = setze_objekt(objekte, neu)
            if entfernen:
                objekte = entferne_objekt(objekte, entfernen)

        if objekte is not None and objekte_datei is not None:
            objekte_vorher = _dateiinhalt(objekte_datei)
            speichere_objekte(objekte_datei, objekte)
            objekte_geschrieben = True
        speichere_einstellungen(_einstellungen_datei(kontext), neue_einstellungen)
    except (TypeError, ValueError) as fehler:
        if objekte_geschrieben and objekte_datei is not None:
            _objektdatei_zuruecksetzen(objekte_datei, objekte_vorher)
        anzeige_objekte = _lese_objekte(aktuelle_einstellungen)
        return _settings_seite(
            rohe_einstellungen,
            anzeige_objekte,
            str(fehler) or "Einstellungen konnten nicht gespeichert werden",
            400,
        )

    if objekte is None:
        objekte = _lese_objekte(neue_einstellungen)
    return _settings_seite(neue_einstellungen, objekte, "Gespeichert")


def _beantworte(
    methode: str,
    pfad: str,
    kopf: object,
    koerper: object,
    kontext: object,
) -> tuple[int, dict[str, str], bytes]:
    if not isinstance(methode, str) or not isinstance(pfad, str):
        return _fehler(400, "Anfrage ist ungueltig")

    methode = methode.upper()
    pfad = pfad.split("?", 1)[0]

    if pfad == "/":
        if methode != "GET":
            return _fehler(405, "Methode nicht erlaubt")
        return 302, {"Location": "/mietvertrag"}, b""

    if pfad in ("/mietvertrag", "/protokoll", "/settings"):
        if methode == "GET":
            return _get_seite(kontext, pfad)
        if methode != "POST":
            return _fehler(405, "Methode nicht erlaubt")
        form = _formular(kopf, koerper)
        if pfad == "/settings":
            return _settings_speichern(form, kontext)
        return _auftrag_seite(
            pfad.removeprefix("/"),
            form,
            kontext,
            protokoll=pfad == "/protokoll",
        )

    return _fehler(404, "Seite nicht gefunden")


def antwort(
    methode: str,
    pfad: str,
    kopf: dict[str, str],
    koerper: bytes,
    kontext: dict,
) -> tuple[int, dict[str, str], bytes]:
    """Beantwortet eine Oberflaechen-Anfrage ohne Socket.

    Die Funktion liest Einstellungen und Objekte bei jeder Anfrage neu. Sie
    liefert Status, HTTP-Kopf und HTML-Koerper und erzeugt bei ungueltigen
    Eingaben eine 400-Antwort statt einer Ausnahme oder eines Status 500.
    """

    try:
        return _beantworte(methode, pfad, kopf, koerper, kontext)
    except _ZuGross:
        return _fehler(413, "Anfrage ist zu gross")
    except (OSError, TypeError, ValueError) as fehler:
        return _fehler(400, str(fehler) or "Anfrage ist ungueltig")
    except Exception:
        return _fehler(400, "Anfrage konnte nicht verarbeitet werden")
