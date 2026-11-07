"""Kommandozeile zum Fuellen einer Mietvertragsvorlage."""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import NoReturn

from projekt.anfrage import aenderungen_aus_text
from projekt.bericht import bericht
from projekt.docx_fuellen import fuelle, platzhalter
from projekt.felder import normalisiere

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class _CliFehler(Exception):
    """Fehler, dessen Text direkt auf stderr ausgegeben wird."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliFehler(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="projekt.cli", allow_abbrev=False)
    parser.add_argument("--vorlage", help="Pfad zur DOCX-Vorlage")
    parser.add_argument("--daten", help="Pfad zur JSON-Datei mit dem Bestand")
    parser.add_argument("--anfrage", help="Optionaler Pfad zur Anfrage als UTF-8-Text")
    parser.add_argument("--ausgabe", help="Pfad fuer den neuen Vertrag")
    parser.add_argument(
        "--selbsttest", action="store_true", help="Eingebauten Selbsttest ausfuehren"
    )
    return parser


def _lies_bytes(pfad: Path, bezeichnung: str) -> bytes:
    try:
        return pfad.read_bytes()
    except OSError as fehler:
        raise _CliFehler(
            f"{bezeichnung} '{pfad}' konnte nicht gelesen werden: {fehler}"
        ) from fehler


def _lies_text(pfad: Path, bezeichnung: str) -> str:
    roh = _lies_bytes(pfad, bezeichnung)
    try:
        return roh.decode("utf-8")
    except UnicodeDecodeError as fehler:
        raise _CliFehler(f"{bezeichnung} '{pfad}' ist nicht UTF-8-kodiert") from fehler


def _lies_bestand(pfad: Path) -> dict[str, str]:
    text = _lies_text(pfad, "Datendatei")
    try:
        daten = json.loads(text)
    except json.JSONDecodeError as fehler:
        raise _CliFehler(f"Datendatei '{pfad}' enthaelt kein gueltiges JSON: {fehler}") from fehler
    return normalisiere(daten)


def _lies_aenderungen(pfad: Path) -> dict[str, str]:
    return aenderungen_aus_text(_lies_text(pfad, "Anfragedatei"))


def _schreibe_ausgabe(pfad: Path, daten: bytes) -> None:
    try:
        datei = pfad.open("xb")
    except FileExistsError as fehler:
        raise _CliFehler(f"Ausgabedatei '{pfad}' existiert bereits") from fehler
    except OSError as fehler:
        raise _CliFehler(
            f"Ausgabedatei '{pfad}' konnte nicht angelegt werden: {fehler}"
        ) from fehler

    try:
        with datei:
            datei.write(daten)
    except OSError as fehler:
        try:
            pfad.unlink()
        except OSError:
            pass
        raise _CliFehler(
            f"Ausgabedatei '{pfad}' konnte nicht geschrieben werden: {fehler}"
        ) from fehler


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
    vorlage = _mini_vorlage()
    alt = normalisiere({"mieter_name": "Selbsttest", "miete_netto": 1000})
    neu = {**alt, **aenderungen_aus_text("Miete netto: 1'200.00")}

    if "miete_netto" not in bericht(alt, neu):
        raise ValueError("Selbsttest: Aenderungsbericht ist unvollstaendig")
    ergebnis = fuelle(vorlage, neu)
    if platzhalter(ergebnis):
        raise ValueError("Selbsttest: Platzhalter blieben stehen")


def main(argv: list[str] | None = None) -> int:
    """Fuehrt die Vertragserstellung aus und liefert den Prozess-Rueckgabewert."""

    try:
        args = _parser().parse_args(argv)
    except _CliFehler as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 2
    except SystemExit as fehler:
        return fehler.code if isinstance(fehler.code, int) else 1

    if args.selbsttest:
        try:
            _selbsttest()
        except Exception as fehler:
            print(f"Selbsttest fehlgeschlagen: {fehler}", file=sys.stderr)
            return 1
        print("Selbsttest OK")
        return 0

    fehlende_optionen = [
        option
        for option in ("--vorlage", "--daten", "--ausgabe")
        if getattr(args, option.removeprefix("--")) is None
    ]
    if fehlende_optionen:
        print(f"Fehlende Option(en): {', '.join(fehlende_optionen)}", file=sys.stderr)
        return 2

    try:
        ausgabe = Path(args.ausgabe)
        if ausgabe.exists():
            raise _CliFehler(f"Ausgabedatei '{ausgabe}' existiert bereits")

        alt = _lies_bestand(Path(args.daten))
        neu = dict(alt)
        if args.anfrage is not None:
            neu.update(_lies_aenderungen(Path(args.anfrage)))

        aenderungsbericht = bericht(alt, neu)
        vorlage = _lies_bytes(Path(args.vorlage), "Vorlage")
        fehlende_platzhalter = [name for name in platzhalter(vorlage) if name not in neu]
        if fehlende_platzhalter:
            raise _CliFehler("Platzhalter ohne Wert: " + ", ".join(fehlende_platzhalter))

        _schreibe_ausgabe(ausgabe, fuelle(vorlage, neu))
    except (_CliFehler, ValueError, OSError) as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1

    print(aenderungsbericht)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
