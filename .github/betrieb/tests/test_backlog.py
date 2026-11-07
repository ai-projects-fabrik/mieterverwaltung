# ruff: noqa: E501
"""Tests des Backlog-Managers (.github/betrieb/backlog.py): Auswahl, Abhaengigkeiten, Limits und Kontrollen."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

MONITOR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MONITOR))
spec = importlib.util.spec_from_file_location("backlog", MONITOR / "backlog.py")
bl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bl)
ad = bl.ad

JETZT = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def text(datei):
    return f"**Datei:** nur `src/projekt/{datei}.py` und `tests/test_{datei}.py`. **Abhaengigkeiten:** keine\n"


def ziel(zid, datei, deps=(), frei=True):
    return {
        "id": zid,
        "titel": zid,
        "text": text(datei),
        "abhaengig_von": list(deps),
        "freigegeben": frei,
    }


def issue(nr, z, state="open", grund=None, alter_h=1, bot="github-actions[bot]"):
    return {
        "number": nr,
        "state": state,
        "state_reason": grund,
        "user": {"login": bot},
        "body": ad.rendere_ziel(z),
        "created_at": (JETZT - timedelta(hours=alter_h)).isoformat(),
    }


def ids(erg):
    return [z["id"] for z in erg[0]]


def test_freies_ziel_wird_gewaehlt():
    assert ids(bl.waehle([ziel("a", "a")], [], 0, JETZT)) == ["a"]


def test_nicht_freigegebenes_ziel_nie():
    assert ids(bl.waehle([ziel("a", "a", frei=False)], [], 0, JETZT)) == []


def test_ziel_mit_issue_nicht_doppelt():
    z = ziel("a", "a")
    assert ids(bl.waehle([z], [issue(1, z)], 0, JETZT)) == []
    assert ids(bl.waehle([z], [issue(1, z, "closed", "completed")], 0, JETZT)) == []


def test_abgebrochene_abhaengigkeit_blockiert():
    a, b = ziel("a", "a"), ziel("b", "b", deps=["a"])
    assert ids(bl.waehle([a, b], [issue(1, a, "closed", "not_planned")], 0, JETZT)) == []


def test_gemeinsame_datei_wird_nicht_gleichzeitig_vergeben():
    a, b = ziel("a", "x"), ziel("b", "x")
    assert ids(bl.waehle([a, b], [], 0, JETZT)) == ["a"]
    assert ids(bl.waehle([b], [issue(1, a)], 0, JETZT)) == []


def test_hoechstens_zwei_neue_je_lauf_und_parallelgrenze():
    zs = [ziel(c, c) for c in "abcd"]
    assert len(bl.waehle(zs, [], 0, JETZT)[0]) == bl.MAX_NEU_PRO_LAUF
    assert (
        len(bl.waehle(zs, [issue(i, ziel(f"v{i}", f"v{i}")) for i in range(1, 5)], 0, JETZT)[0])
        == 1
    )
    voll = [issue(i, ziel(f"v{i}", f"v{i}")) for i in range(1, 6)]
    assert bl.waehle(zs, voll, 0, JETZT)[0] == []


def test_tageslimit_der_laeufe():
    zs = [ziel("a", "a"), ziel("b", "b")]
    assert len(bl.waehle(zs, [], ad.MAX_LAEUFE_24H - 1, JETZT)[0]) == 1
    assert bl.waehle(zs, [], ad.MAX_LAEUFE_24H, JETZT)[0] == []


def test_zwei_abgebrochene_ziele_pausieren():
    x, y = ziel("x", "x"), ziel("y", "y")
    iss = [issue(1, x, "closed", "not_planned"), issue(2, y, "closed", "not_planned")]
    erg = bl.waehle([ziel("a", "a")], iss, 0, JETZT)
    assert erg[0] == [] and "Pause" in erg[1]


def test_stau_pausiert():
    x, y = ziel("x", "x"), ziel("y", "y")
    iss = [issue(1, x, alter_h=30), issue(2, y, alter_h=40)]
    erg = bl.waehle([ziel("a", "a")], iss, 0, JETZT)
    assert erg[0] == [] and "Pause" in erg[1]
    assert len(bl.waehle([ziel("a", "a")], [issue(1, x, alter_h=30)], 0, JETZT)[0]) == 1


def test_fremdes_issue_mit_marker_zaehlt_nicht():
    z = ziel("a", "a")
    fremd = ziel("a", "andere")  # gleiche Ziel-ID, aber nicht vom Manager angelegt
    assert ids(bl.waehle([z], [issue(1, fremd, bot="angreifer")], 0, JETZT)) == ["a"]


SPITZE = datetime(2026, 10, 26, 7, 0, tzinfo=UTC)  # Montag 07:00 UTC
WOCHENENDE = datetime(2026, 10, 24, 7, 0, tzinfo=UTC)  # Samstag 07:00 UTC


def test_tarifzeiten_utc():
    spitze = [
        (0, 1, 0),
        (1, 1, 1),
        (3, 59, 1),
        (4, 0, 0),
        (5, 59, 0),
        (6, 0, 1),
        (9, 59, 1),
        (10, 0, 0),
        (23, 0, 0),
    ]
    for stunde, minute, erwartet in spitze:
        assert ad.ist_spitze(datetime(2026, 10, 26, stunde, minute, tzinfo=UTC)) == bool(erwartet)
    assert not ad.ist_spitze(WOCHENENDE)
    assert not ad.ist_spitze(datetime(2026, 10, 25, 2, 0, tzinfo=UTC))  # Sonntag
    # lokale Zeitzone zaehlt nicht: 08:00 in Zuerich (UTC+2) ist 06:00 UTC = Spitze
    zuerich = timezone(timedelta(hours=2))
    assert ad.ist_spitze(datetime(2026, 10, 26, 8, 0, tzinfo=zuerich))


def test_parallelitaet_nach_tarifzeit():
    assert ad.parallel_grenze(SPITZE) == 2
    assert ad.parallel_grenze(SPITZE, dringend=True) == 5
    assert ad.parallel_grenze(JETZT) == 5 and ad.parallel_grenze(WOCHENENDE) == 5


def test_spitzenzeit_normale_ziele_warten_dringende_nicht():
    normal = ziel("n", "n")
    eilig = dict(ziel("e", "e"), dringend=True)
    assert bl.waehle([normal], [], 0, SPITZE)[0] == []
    assert ids(bl.waehle([normal, eilig], [], 0, SPITZE)) == ["e"]
    assert ids(bl.waehle([normal], [], 0, JETZT)) == ["n"]  # guenstige Zeit: sofort


def test_dispatcher_spitze_zwei_parallel():
    assert ad.pruefe_grenzen(["x"], 0, 1, set(), ad.parallel_grenze(SPITZE)) is None
    assert ad.pruefe_grenzen(["x"], 0, 2, set(), ad.parallel_grenze(SPITZE))
    assert ad.pruefe_grenzen(["x"], 0, 2, set(), ad.parallel_grenze(SPITZE, True)) is None
