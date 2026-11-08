import pytest

from projekt.objekttabelle import (
    SPALTEN,
    neue_id,
    objekte_aus_zeilen,
    zeilen_aus_formular,
)


def test_spalten_sind_die_sichtbaren_formularspalten():
    assert SPALTEN == (
        ("bezeichnung", "Bezeichnung"),
        ("miete_netto", "Miete netto (CHF)"),
        ("nebenkosten", "Nebenkosten (CHF)"),
        ("kaution", "Kaution (CHF)"),
    )


@pytest.mark.parametrize(
    ("bezeichnung", "erwartet"),
    [
        ("Musterweg 1, Zürich", "musterweg-1-zuerich"),
        ("Grüne Straße", "gruene-strasse"),
        ("Haus_Ä", "haus-ae"),
        ("  A   B  ", "a-b"),
        ("§§§", "objekt"),
        ("", "objekt"),
        ("x" * 100, "x" * 36),
    ],
)
def test_neue_id_transliteriert_und_begrenzt(bezeichnung, erwartet):
    assert neue_id(bezeichnung, []) == erwartet


def test_neue_id_weicht_kollisionen_aus():
    assert neue_id("Haus A", ["haus-a"]) == "haus-a-2"
    assert neue_id("Haus A", ["haus-a", "haus-a-2"]) == "haus-a-3"
    assert neue_id("§§§", ["objekt", "objekt-2"]) == "objekt-3"


def test_neue_id_bleibt_bei_kollision_hoechstens_vierzig_zeichen():
    basis = "a" * 36
    vorhanden = [basis, f"{basis}-2", f"{basis}-3"]
    ergebnis = neue_id("a" * 100, vorhanden)
    assert ergebnis == f"{basis}-4"
    assert len(ergebnis) <= 40


def test_neue_id_prueft_typ_und_nutzt_jede_iterierbare():
    with pytest.raises(ValueError, match="Bezeichnung"):
        neue_id(5, [])
    assert neue_id("Haus", (name for name in ["haus"])) == "haus-2"


def test_zeilen_aus_formular_sortiert_und_trimmt():
    form = {
        "zeile_999_bezeichnung": " Ende ",
        "zeile_0_bezeichnung": " Start ",
        "zeile_10_miete_netto": " 1'000 ",
        "zeile_10_id": " zehn ",
        "zeile_1000_bezeichnung": "zu gross",
        "zeile_3_unbekannt": "ignorieren",
        "zeile_x_bezeichnung": "ignorieren",
        "drive_ordner": "G:",
    }
    assert zeilen_aus_formular(form) == [
        {"bezeichnung": "Start"},
        {"miete_netto": "1'000", "id": "zehn"},
        {"bezeichnung": "Ende"},
    ]


def test_zeilen_aus_formular_behaelt_leere_werte_und_prueft_typ():
    assert zeilen_aus_formular({"zeile_1_bezeichnung": "  "}) == [{"bezeichnung": ""}]
    with pytest.raises(ValueError, match="form"):
        zeilen_aus_formular(["zeile_1_bezeichnung", "Haus"])
    with pytest.raises(ValueError, match="zeile_1_bezeichnung"):
        zeilen_aus_formular({"zeile_1_bezeichnung": 5})


def test_neue_zeile_bekommt_normalisierte_id_und_betraege():
    assert objekte_aus_zeilen(
        [
            {
                "bezeichnung": " Haus A ",
                "miete_netto": "1250.5",
                "nebenkosten": 0,
                "kaution": "CHF 3000",
            }
        ],
        [],
    ) == [
        {
            "id": "haus-a",
            "bezeichnung": "Haus A",
            "miete_netto": "1'250.50",
            "nebenkosten": "0.00",
            "kaution": "3'000.00",
        }
    ]


def test_bestehende_id_bleibt_bei_umbenennung():
    bestehend = [{"id": "weg-1", "bezeichnung": "Musterweg 1"}]
    assert objekte_aus_zeilen(
        [{"id": "weg-1", "bezeichnung": "Musterweg 1a", "kaution": "100"}], bestehend
    ) == [{"id": "weg-1", "bezeichnung": "Musterweg 1a", "kaution": "100.00"}]


def test_unbekannte_id_wird_durch_neue_id_ersetzt():
    bestehend = [{"id": "haus", "bezeichnung": "Haus"}]
    assert objekte_aus_zeilen([{"id": "frei-erfunden", "bezeichnung": "Haus"}], bestehend) == [
        {"id": "haus-2", "bezeichnung": "Haus"}
    ]


def test_doppelte_bestehende_id_wird_nur_einmal_vergeben():
    bestehend = [{"id": "a", "bezeichnung": "A"}]
    assert objekte_aus_zeilen(
        [
            {"id": "a", "bezeichnung": "A"},
            {"id": " a ", "bezeichnung": "A neu"},
        ],
        bestehend,
    ) == [
        {"id": "a", "bezeichnung": "A"},
        {"id": "a-neu", "bezeichnung": "A neu"},
    ]


def test_zeilen_ohne_sichtbaren_wert_entfernen_objekte():
    bestehend = [
        {"id": "a", "bezeichnung": "A"},
        {"id": "b", "bezeichnung": "B"},
    ]
    zeilen = [
        {"id": "a", "bezeichnung": "A"},
        {"id": "b"},
        {"bezeichnung": "   ", "miete_netto": ""},
        {"unbekannt": "x"},
        {},
    ]
    assert objekte_aus_zeilen(zeilen, bestehend) == [{"id": "a", "bezeichnung": "A"}]
    assert objekte_aus_zeilen([], bestehend) == []


def test_gleiche_bezeichnung_bekommt_fortlaufende_ids_und_sortiert():
    ergebnis = objekte_aus_zeilen(
        [{"bezeichnung": "Zebra"}, {"bezeichnung": "Haus"}, {"bezeichnung": "Haus"}], []
    )
    assert [objekt["id"] for objekt in ergebnis] == ["haus", "haus-2", "zebra"]


def test_fehlende_bezeichnung_und_ungueltige_betraege_nennen_zeile():
    with pytest.raises(ValueError, match=r"Zeile 1.*Bezeichnung"):
        objekte_aus_zeilen([{"miete_netto": "100"}], [])
    with pytest.raises(ValueError, match=r"Zeile 2.*Miete netto \(CHF\)"):
        objekte_aus_zeilen([{"bezeichnung": "A"}, {"bezeichnung": "B", "miete_netto": "viel"}], [])
    with pytest.raises(ValueError, match=r"Zeile 1.*Nebenkosten \(CHF\)"):
        objekte_aus_zeilen([{"bezeichnung": "A", "nebenkosten": "-1"}], [])
    with pytest.raises(ValueError, match=r"Zeile 1.*Kaution \(CHF\)"):
        objekte_aus_zeilen([{"bezeichnung": "A", "kaution": 1.5}], [])


def test_zeilen_und_bestehend_werden_geprueft():
    with pytest.raises(ValueError, match="zeilen"):
        objekte_aus_zeilen("keine Liste", [])
    with pytest.raises(ValueError, match="Zeile 2"):
        objekte_aus_zeilen([{"bezeichnung": "A"}, "keine Zeile"], [])
    with pytest.raises(ValueError, match="bestehend"):
        objekte_aus_zeilen([], "keine Liste")


def test_eingaben_werden_nicht_veraendert():
    bestehend = [{"id": "a", "bezeichnung": "A"}]
    zeilen = [{"id": "a", "bezeichnung": "A", "kaution": "10"}]
    kopie_bestehend = [dict(eintrag) for eintrag in bestehend]
    kopie_zeilen = [dict(eintrag) for eintrag in zeilen]
    objekte_aus_zeilen(zeilen, bestehend)
    assert bestehend == kopie_bestehend
    assert zeilen == kopie_zeilen
