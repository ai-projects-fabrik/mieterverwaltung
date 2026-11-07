"""Aenderungen aus dem Text einer Mieter-Anfrage lesen."""

from __future__ import annotations

from projekt.felder import FELDER, normalisiere


def aenderungen_aus_text(text: str) -> dict[str, str]:
    """Liest Zeilen der Form ``Feld: Wert`` und liefert die normalisierten Felder.

    Zeilen mit unbekannten Feldnamen und zitierter Text werden ignoriert. Wird
    ein Feld mehrfach mit unterschiedlichen normalisierten Werten genannt, ist
    die Eingabe widerspruechlich und loest einen ValueError mit Feldnamen aus.
    """

    if not isinstance(text, str):
        raise ValueError("Anfrage muss als Text uebergeben werden")

    ergebnis: dict[str, str] = {}
    for zeile in text.splitlines():
        if zeile.lstrip().startswith(">"):
            continue
        if ":" not in zeile:
            continue

        schluessel, wert = zeile.split(":", 1)
        feld = schluessel.strip().lower().replace(" ", "_")
        if feld not in FELDER:
            continue

        normalisiert = normalisiere({feld: wert.strip()})[feld]
        if feld in ergebnis and ergebnis[feld] != normalisiert:
            raise ValueError(f"Feld '{feld}' wird mit verschiedenen Werten genannt")
        ergebnis[feld] = normalisiert

    return ergebnis
