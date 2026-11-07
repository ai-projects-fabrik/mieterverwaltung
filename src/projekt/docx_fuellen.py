"""Platzhalter in Word-Vorlagen finden und ersetzen.

Die Vorlage bleibt in ihrem Aufbau unveraendert. Nur ``word/document.xml`` wird
verarbeitet; alle anderen Dateien im DOCX-Paket werden byte-gleich uebernommen.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib

_DOKUMENT = "word/document.xml"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_PLATZHALTER = re.compile(r"\{\{([a-z_]+)\}\}")


def _lese_paket(docx: bytes) -> tuple[list[tuple[zipfile.ZipInfo, bytes]], bytes]:
    if not isinstance(docx, bytes):
        raise ValueError("docx muss als bytes uebergeben werden")

    try:
        with zipfile.ZipFile(io.BytesIO(docx)) as paket:
            eintraege = [(info, paket.read(info)) for info in paket.infolist()]
            kommentar = paket.comment
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        ValueError,
        zlib.error,
    ) as fehler:
        raise ValueError("docx ist kein gueltiges ZIP-Paket") from fehler

    if not any(info.filename == _DOKUMENT for info, _ in eintraege):
        raise ValueError("docx enthaelt keine Datei word/document.xml")

    return eintraege, kommentar


def _dokument_bytes(eintraege: list[tuple[zipfile.ZipInfo, bytes]]) -> bytes:
    for info, daten in eintraege:
        if info.filename == _DOKUMENT:
            return daten
    raise ValueError("docx enthaelt keine Datei word/document.xml")


def _parse_dokument(roh: bytes) -> tuple[ET.Element, dict[str, str]]:
    namensraeume: dict[str, str] = {}
    try:
        for _, (praefix, uri) in ET.iterparse(io.BytesIO(roh), events=("start-ns",)):
            if praefix:
                namensraeume[praefix] = uri
        wurzel = ET.fromstring(roh)
    except (ET.ParseError, ValueError) as fehler:
        raise ValueError("docx enthaelt ungueltiges XML in word/document.xml") from fehler
    if wurzel.tag != f"{{{_W}}}document":
        raise ValueError("docx enthaelt kein gueltiges word/document.xml")
    return wurzel, namensraeume


def _werte_pruefen(werte: dict[str, str]) -> None:
    if not isinstance(werte, dict):
        raise ValueError("werte muss ein dict sein")
    for feld, wert in werte.items():
        if not isinstance(feld, str):
            raise ValueError("Feldname muss als Text uebergeben werden")
        if not isinstance(wert, str):
            raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")


def _text_knoten(absatz: ET.Element) -> list[ET.Element]:
    return list(absatz.iter(f"{{{_W}}}t"))


def _absatz_text(absatz: ET.Element) -> str:
    return "".join(knoten.text or "" for knoten in _text_knoten(absatz))


def _setze_text(knoten: ET.Element, text: str) -> None:
    knoten.text = text or None
    if text and (text[0].isspace() or text[-1].isspace()):
        knoten.set(_XML_SPACE, "preserve")
    else:
        knoten.attrib.pop(_XML_SPACE, None)


def _ersetze_absatz(absatz: ET.Element, werte: dict[str, str]) -> None:
    knoten = _text_knoten(absatz)
    if not knoten:
        return

    gesamt = "".join(knoten_text.text or "" for knoten_text in knoten)
    if _PLATZHALTER.search(gesamt) is None:
        return

    ersetzt = _PLATZHALTER.sub(
        lambda treffer: werte.get(treffer.group(1), treffer.group(0)), gesamt
    )
    _setze_text(knoten[0], ersetzt)
    for weiterer in knoten[1:]:
        _setze_text(weiterer, "")


def _gebrauchte_namensraeume(wurzel: ET.Element) -> set[str]:
    gebraucht: set[str] = set()
    for element in wurzel.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            gebraucht.add(element.tag[1 : element.tag.index("}")])
        for name in element.attrib:
            if name.startswith("{"):
                gebraucht.add(name[1 : name.index("}")])
    return gebraucht


def _serialisiere(wurzel: ET.Element, namensraeume: dict[str, str]) -> bytes:
    for praefix, uri in namensraeume.items():
        if praefix == "xml":
            continue
        try:
            ET.register_namespace(praefix, uri)
        except ValueError:
            pass

    gebraucht = _gebrauchte_namensraeume(wurzel)
    for praefix, uri in namensraeume.items():
        if praefix == "xml" or uri in gebraucht:
            continue
        wurzel.set(f"xmlns:{praefix}" if praefix else "xmlns", uri)

    try:
        return ET.tostring(wurzel, encoding="utf-8", xml_declaration=True)
    except ValueError as fehler:
        raise ValueError("docx enthaelt ungueltige XML-Zeichen") from fehler


def platzhalter(docx: bytes) -> list[str]:
    """Liefert die in der DOCX-Vorlage vorkommenden Platzhalter sortiert und eindeutig."""

    eintraege, _ = _lese_paket(docx)
    wurzel, _ = _parse_dokument(_dokument_bytes(eintraege))
    namen = {
        treffer
        for absatz in wurzel.iter(f"{{{_W}}}p")
        for treffer in _PLATZHALTER.findall(_absatz_text(absatz))
    }
    return sorted(namen)


def fuelle(docx: bytes, werte: dict[str, str]) -> bytes:
    """Ersetzt Platzhalter in der DOCX-Vorlage und liefert das neue DOCX als bytes.

    Platzhalter duerfen in Word ueber mehrere Text-Runs verteilt sein. Fehlende
    Werte bleiben als Platzhalter stehen, damit der Mensch sie vor dem Versand
    pruefen kann.
    """

    _werte_pruefen(werte)
    eintraege, kommentar = _lese_paket(docx)
    wurzel, namensraeume = _parse_dokument(_dokument_bytes(eintraege))

    for absatz in wurzel.iter(f"{{{_W}}}p"):
        _ersetze_absatz(absatz, werte)

    neues_dokument = _serialisiere(wurzel, namensraeume)
    puffer = io.BytesIO()
    try:
        with zipfile.ZipFile(puffer, "w") as paket:
            paket.comment = kommentar
            for info, daten in eintraege:
                paket.writestr(info, neues_dokument if info.filename == _DOKUMENT else daten)
    except (OSError, ValueError, zlib.error) as fehler:
        raise ValueError("docx konnte nicht neu geschrieben werden") from fehler
    return puffer.getvalue()
