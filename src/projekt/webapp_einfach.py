"""Routing und Formularverarbeitung der vereinfachten Oberflaeche ohne Socket."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import parse_qsl

from projekt.ablage import liste_vorlagen
from projekt.auftraege import erstelle_protokoll, erstelle_vertrag, protokoll_werte
from projekt.auswahl import auswahl_pfad, lade_auswahl, speichere_auswahl
from projekt.einstellungen import lade_einstellungen, ordner, speichere_einstellungen
from projekt.objekte import lade_objekte, speichere_objekte
from projekt.objekttabelle import objekte_aus_zeilen, zeilen_aus_formular
from projekt.pfade import (
    drive_ordner,
    einstellungen_aus_ordnern,
    erkenne_drive,
    lege_ordner_an,
    lokaler_ordner,
    standard_lokal,
)
from projekt.seiten import ergebnis
from projekt.seiten_einfach import (
    formular_objekttabelle,
    formular_ordner,
    formular_uebergabe,
    formular_vertrag,
    rahmen_einfach,
)
from projekt.vorauswahl import merke, vorauswahl

_HTML_TYP = "text/html; charset=utf-8"
_MAX_KOERPER = 1024 * 1024
_ORTE = ("lokal", "drive")
_SEITEN = ("/mietvertrag", "/protokoll", "/objekte", "/settings")


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
        raise ValueError("Feld 'einstellungen_datei' ist nicht gesetzt")
    datei = kontext.get("einstellungen_datei")
    if not isinstance(datei, (str, Path)) or not str(datei).strip():
        raise ValueError("Feld 'einstellungen_datei' ist nicht gesetzt")
    return Path(datei)


def _home(kontext: object) -> str | Path | None:
    if not isinstance(kontext, dict):
        return None
    home = kontext.get("home")
    return home if isinstance(home, (str, Path)) else None


def _drive_kandidaten(kontext: object) -> tuple[str, ...] | None:
    if not isinstance(kontext, dict):
        return None
    kandidaten = kontext.get("drive_kandidaten")
    if isinstance(kandidaten, (list, tuple)):
        return tuple(kandidaten)
    return None


def _standard_einstellungen(kontext: object) -> dict[str, str]:
    return einstellungen_aus_ordnern(
        erkenne_drive(_drive_kandidaten(kontext)),
        standard_lokal(_home(kontext)),
    )


def _lese_einstellungen(kontext: object) -> dict[str, str]:
    datei = _einstellungen_datei(kontext)
    try:
        gespeichert = lade_einstellungen(datei)
    except (OSError, TypeError, ValueError):
        gespeichert = {}
    if gespeichert:
        return gespeichert
    return _standard_einstellungen(kontext)


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


def _vorlagen_hinweise(einstellungen: dict[str, str], vorlagen: dict[str, list[str]]) -> list[str]:
    """Hinweise fuer Vorlagen-Ordner ohne .docx, bei .gdoc-Dateien mit Speichertipp."""

    hinweise: list[str] = []
    gdoc = False
    for ort in _ORTE:
        if vorlagen.get(ort):
            continue
        try:
            pfad = Path(ordner(einstellungen, "vorlagen", ort))
        except (OSError, TypeError, ValueError):
            continue
        hinweise.append(f"Keine Vorlage (.docx) gefunden in {pfad}")
        try:
            gdoc = gdoc or any(
                p.name.casefold().endswith((".gdoc", ".gsheet")) for p in pfad.iterdir()
            )
        except OSError:
            pass
    if gdoc:
        hinweise.append(
            "Google-Docs-Dateien bitte als .docx speichern (Datei > Herunterladen > Microsoft Word)"
        )
    return hinweise


def _google(kontext: object):
    """Die Google-Quelle aus dem Kontext (Schluessel ``google``) oder ``None``."""

    quelle = kontext.get("google") if isinstance(kontext, dict) else None
    return quelle if hasattr(quelle, "vorlagen") else None


def _mit_google(kontext: object, vorlagen: dict, hinweise: list[str]) -> list[dict]:
    """Traegt Google-Vorlagen in ``vorlagen`` ein, haengt Hinweise an, liefert die Dateien."""

    quelle = _google(kontext)
    if quelle is None:
        return []
    dateien, meldungen = quelle.vorlagen()
    hinweise.extend(meldungen)
    if dateien:
        vorlagen["google"] = dateien
    return dateien


def _google_vorwahl(werte: dict, letzte: dict, art: str, dateien: list[dict]) -> dict:
    """Waehlt eine Google-Vorlage vor, wenn zuletzt benutzt oder sonst keine vorhanden."""

    ids = {f"google:{datei['id']}" for datei in dateien}
    gemerkt = letzte.get(f"{art}_vorlage")
    if gemerkt in ids:
        return {**werte, "vorlage": gemerkt}
    if not werte.get("vorlage") and dateien:
        stichwort = "vertrag" if art == "vertrag" else "protokoll"
        passende = [d for d in dateien if stichwort in d["name"].casefold()] or dateien
        return {**werte, "vorlage": f"google:{passende[0]['id']}"}
    return werte


def _google_block(kontext: object) -> str:
    quelle = _google(kontext)
    if quelle is None:
        return ""
    return (
        "<h2>Google</h2>"
        f"<p>{escape(quelle.status())}</p>"
        '<form method="post" action="/google"><p>'
        '<button type="submit">Mit Google verbinden</button></p></form>'
    )


def _html(status: int, inhalt: str) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": _HTML_TYP}, inhalt.encode("utf-8")


def _fehler(
    status: int,
    meldung: str,
    aktiv: str = "mietvertrag",
) -> tuple[int, dict[str, str], bytes]:
    inhalt = f"<h1>Fehler</h1><p>{escape(meldung)}</p>"
    return _html(status, rahmen_einfach(aktiv, inhalt))


def _seite(aktiv: str, inhalt: str) -> tuple[int, dict[str, str], bytes]:
    return _html(200, rahmen_einfach(aktiv, inhalt))


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


def _get_seite(kontext: object, pfad: str) -> tuple[int, dict[str, str], bytes]:
    einstellungen = _lese_einstellungen(kontext)
    objekte = _lese_objekte(einstellungen)
    vorlagen = _lese_vorlagen(einstellungen)
    hinweise = _vorlagen_hinweise(einstellungen, vorlagen)
    home = _home(kontext)
    google = _mit_google(kontext, vorlagen, hinweise)

    if pfad == "/mietvertrag":
        letzte = lade_auswahl(auswahl_pfad(einstellungen, home))
        werte = _google_vorwahl(
            vorauswahl("vertrag", objekte, vorlagen, letzte), letzte, "vertrag", google
        )
        return _seite("mietvertrag", formular_vertrag(objekte, vorlagen, werte, "", hinweise))
    if pfad == "/protokoll":
        letzte = lade_auswahl(auswahl_pfad(einstellungen, home))
        werte = _google_vorwahl(
            vorauswahl("protokoll", objekte, vorlagen, letzte), letzte, "protokoll", google
        )
        return _seite("protokoll", formular_uebergabe(objekte, vorlagen, werte, "", hinweise))
    if pfad == "/objekte":
        return _seite("objekte", formular_objekttabelle(objekte))

    return _settings_seite(
        drive_ordner(einstellungen, _drive_kandidaten(kontext)),
        lokaler_ordner(einstellungen, home),
        kontext=kontext,
    )


def _auftrag_seite(
    aktiv: str,
    form: dict[str, str],
    kontext: object,
    *,
    protokoll: bool,
) -> tuple[int, dict[str, str], bytes]:
    einstellungen = _lese_einstellungen(kontext)
    objekte = _lese_objekte(einstellungen)
    vorlagen = _lese_vorlagen(einstellungen)
    hinweise = _vorlagen_hinweise(einstellungen, vorlagen)
    _mit_google(kontext, vorlagen, hinweise)

    try:
        erstellen = erstelle_protokoll if protokoll else erstelle_vertrag
        auftrags_kontext: dict = {"einstellungen": einstellungen}
        vorlage = form.get("vorlage", "")
        if isinstance(vorlage, str) and vorlage.strip().startswith("google:"):
            quelle = _google(kontext)
            if quelle is None:
                raise ValueError("Feld 'vorlage': Google ist nicht aktiviert")
            auftrags_kontext["vorlage_bytes"] = quelle.hole(vorlage.strip().removeprefix("google:"))
        auftrag = erstellen(form, auftrags_kontext)
    except (OSError, TypeError, ValueError) as fehler:
        meldung = str(fehler) or "Auftrag konnte nicht erstellt werden"
        if protokoll:
            inhalt = formular_uebergabe(objekte, vorlagen, form, meldung, hinweise)
        else:
            inhalt = formular_vertrag(objekte, vorlagen, form, meldung, hinweise)
        return _html(400, rahmen_einfach(aktiv, inhalt))

    dateien = list(auftrag.get("dateien", []))
    pdf_auftrag = auftrag.get("pdf_auftrag")
    if pdf_auftrag is not None:
        dateien.append(pdf_auftrag)
    if protokoll:
        text = "Dateien angelegt"
        try:
            werte = protokoll_werte(form, auftrags_kontext)
        except (OSError, TypeError, ValueError):
            werte = None
    else:
        text = auftrag.get("bericht", "")
        if text == "keine Aenderungen":
            text = ""
        werte = auftrag.get("werte")
    titel = "Uebergabeprotokoll erstellt" if protokoll else "Mietvertrag erstellt"
    inhalt = ergebnis(titel, text, dateien, auftrag.get("hinweis", ""), werte=werte)

    try:
        speichere_auswahl(
            auswahl_pfad(einstellungen, _home(kontext)),
            merke("protokoll" if protokoll else "vertrag", form),
        )
    except Exception:
        pass

    return _html(200, rahmen_einfach(aktiv, inhalt))


def _settings_seite(
    drive: str,
    lokal: str,
    meldung: str = "",
    status: int = 200,
    kontext: object = None,
) -> tuple[int, dict[str, str], bytes]:
    inhalt = formular_ordner(drive, lokal, meldung) + _google_block(kontext)
    return _html(status, rahmen_einfach("settings", inhalt))


def _settings_speichern(form: dict[str, str], kontext: object) -> tuple[int, dict[str, str], bytes]:
    datei = _einstellungen_datei(kontext)
    drive = form.get("drive_ordner", "")
    lokal = form.get("lokaler_ordner", "")

    try:
        neue_einstellungen = einstellungen_aus_ordnern(drive, lokal)
        speichere_einstellungen(datei, neue_einstellungen)
    except (OSError, TypeError, ValueError) as fehler:
        meldung = str(fehler) or "Einstellungen konnten nicht gespeichert werden"
        return _settings_seite(drive, lokal, meldung, 400, kontext)

    try:
        lege_ordner_an(neue_einstellungen)
    except ValueError as fehler:
        meldung = f"Gespeichert. Hinweis: {fehler}"
    else:
        meldung = "Gespeichert"

    return _settings_seite(
        neue_einstellungen.get("drive_wurzel", drive),
        lokaler_ordner(neue_einstellungen, _home(kontext)),
        meldung,
        kontext=kontext,
    )


def _objekte_speichern(form: dict[str, str], kontext: object) -> tuple[int, dict[str, str], bytes]:
    einstellungen = _lese_einstellungen(kontext)
    objekte_datei = einstellungen.get("objekte_datei")
    zeilen: list[dict[str, str]] = []

    try:
        zeilen = zeilen_aus_formular(form)
        if not isinstance(objekte_datei, str) or not objekte_datei.strip():
            raise ValueError("Feld 'objekte_datei' ist nicht gesetzt")
        bestehende = lade_objekte(objekte_datei.strip())
        objekte = objekte_aus_zeilen(zeilen, bestehende)
        speichere_objekte(objekte_datei.strip(), objekte)
    except (OSError, TypeError, ValueError) as fehler:
        meldung = str(fehler) or "Objekte konnten nicht gespeichert werden"
        return _html(400, rahmen_einfach("objekte", formular_objekttabelle(zeilen, meldung)))

    return _html(200, rahmen_einfach("objekte", formular_objekttabelle(objekte, "Gespeichert")))


def _beantworte(
    methode: str,
    pfad: str,
    kopf: object,
    koerper: object,
    kontext: object,
) -> tuple[int, dict[str, str], bytes]:
    if not isinstance(methode, str) or not isinstance(pfad, str):
        return _fehler(400, "Anfrage ist ungueltig")

    _einstellungen_datei(kontext)
    methode = methode.upper()
    pfad = pfad.split("?", 1)[0]

    if pfad == "/":
        if methode != "GET":
            return _fehler(405, "Methode nicht erlaubt")
        return 302, {"Location": "/mietvertrag"}, b""

    if pfad == "/google":
        quelle = _google(kontext)
        if methode != "POST" or quelle is None:
            return _fehler(405 if quelle is not None else 404, "Seite nicht gefunden")
        meldung = quelle.verbinden()
        einstellungen = _lese_einstellungen(kontext)
        return _settings_seite(
            drive_ordner(einstellungen, _drive_kandidaten(kontext)),
            lokaler_ordner(einstellungen, _home(kontext)),
            meldung,
            kontext=kontext,
        )

    if pfad in _SEITEN:
        if methode == "GET":
            return _get_seite(kontext, pfad)
        if methode != "POST":
            return _fehler(405, "Methode nicht erlaubt", pfad.removeprefix("/"))
        form = _formular(kopf, koerper)
        if pfad == "/settings":
            return _settings_speichern(form, kontext)
        if pfad == "/objekte":
            return _objekte_speichern(form, kontext)
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
    """Beantwortet eine Anfrage der vereinfachten Oberflaeche ohne Socket.

    Die Funktion liest Einstellungen, Objekte und Vorlagen bei jeder Anfrage
    neu. Fehlt die Einstellungsdatei, gelten die aus Drive- und lokalem
    Standardordner abgeleiteten Werte, ohne etwas anzulegen. Ungueltige
    Eingaben ergeben eine 4xx-Antwort statt einer Ausnahme oder eines 5xx.
    """

    try:
        return _beantworte(methode, pfad, kopf, koerper, kontext)
    except _ZuGross:
        return _fehler(413, "Anfrage ist zu gross")
    except (OSError, TypeError, ValueError) as fehler:
        return _fehler(400, str(fehler) or "Anfrage ist ungueltig")
    except Exception:
        return _fehler(400, "Anfrage konnte nicht verarbeitet werden")
