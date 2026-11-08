# ruff: noqa: E501
"""Tests der automatischen Agenten-Uebergabe (.github/betrieb/agent_dispatch.py): Eignung und harte Grenzen."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "agent_dispatch", Path(__file__).resolve().parent.parent / "agent_dispatch.py"
)
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)

BODY = (
    "**Datei:** nur `src/projekt/preis.py` und `tests/test_preis.py`. **Abhaengigkeiten:** keine\n"
    "**Akzeptanztest:** `tests/akzeptanz/test_preis.py` (gemergt in PR #9).\n"
)


def issue(**kw):
    i = {
        "state": "open",
        "labels": [{"name": "agent-kandidat"}],
        "author_association": "OWNER",
        "body": BODY,
    }
    i.update(kw)
    return i


def pruefe(i=None, auto="on", akz=frozenset({"test_preis.py"}), laeufe=0, prs=0):
    return ad.entscheide(i or issue(), auto, set(akz), laeufe, prs)


def test_geeignetes_issue_wird_uebergeben():
    ok, grund = pruefe()
    assert ok and "preis" in grund


def test_kill_switch_aus_oder_fehlt():
    assert not pruefe(auto="off")[0]
    assert not pruefe(auto="")[0]


def test_ohne_kandidaten_label_nichts():
    assert not pruefe(issue(labels=[]))[0]


def test_keine_wiederholung():
    assert not pruefe(issue(labels=[{"name": "agent-kandidat"}, {"name": "agent-uebergeben"}]))[0]
    assert not pruefe(issue(labels=[{"name": "agent-kandidat"}, {"name": "agent"}]))[0]


def test_fremder_autor_geschlossenes_issue_und_pr():
    assert not pruefe(issue(author_association="NONE"))[0]
    assert not pruefe(issue(state="closed"))[0]
    assert not pruefe(issue(pull_request={"url": "x"}))[0]


def test_zuschnitt_muss_genau_ein_modul_und_test_sein():
    zu_viel = BODY.replace("`tests/test_preis.py`", "`tests/test_preis.py` und `src/projekt/x.py`")
    assert not pruefe(issue(body=zu_viel))[0]
    fremd = BODY.replace("`src/projekt/preis.py`", "`deploy/preis.py`")
    assert not pruefe(issue(body=fremd))[0]
    anderer_test = BODY.replace("`tests/test_preis.py`", "`tests/test_anders.py`")
    assert not pruefe(issue(body=anderer_test))[0]
    assert not pruefe(issue(body="irgendein Text"))[0]


def test_pfad_tricks_werden_abgelehnt():
    assert not pruefe(issue(body=BODY.replace("src/projekt/preis.py", "src/../.github/preis.py")))[
        0
    ]
    mit_punkten = BODY.replace("`tests/test_preis.py`", "`tests/../test_preis.py`")
    assert not pruefe(issue(body=mit_punkten))[0]


def test_akzeptanztest_pflicht_spec_first():
    assert not pruefe(akz=frozenset())[0]
    ohne_feld = BODY.replace("`tests/akzeptanz/test_preis.py`", "`tests/akzeptanz/test_andere.py`")
    assert not pruefe(issue(body=ohne_feld))[0]


def test_limits_laeufe_und_offene_prs():
    assert ad.MAX_LAEUFE_24H == 30 and ad.MAX_PARALLEL == 5 and ad.MAX_PARALLEL_SPITZE == 2
    assert pruefe(laeufe=14)[0]
    assert not pruefe(laeufe=15)[0]
    assert pruefe(prs=4)[0]
    assert not pruefe(prs=5)[0]


def test_parallele_issues_nur_mit_getrennten_dateien():
    belegt = {"src/projekt/anderes.py", "tests/test_anderes.py"}
    assert ad.entscheide(issue(), "on", {"test_preis.py"}, 0, 2, belegt)[0]
    gleich = {"src/projekt/preis.py"}
    ok, grund = ad.entscheide(issue(), "on", {"test_preis.py"}, 0, 1, gleich)
    assert not ok and "belegt" in grund


def test_zu_langer_text():
    assert not pruefe(issue(body=BODY + "x" * 7000))[0]


def test_zaehlung_ignoriert_uebersprungene_und_alte_laeufe():
    from datetime import UTC, datetime

    jetzt = datetime(2026, 10, 24, 12, tzinfo=UTC)
    laeufe = [
        {"conclusion": "skipped", "created_at": "2026-10-24T11:00:00Z"},
        {"conclusion": "success", "created_at": "2026-10-24T10:00:00Z"},
        {"conclusion": "failure", "created_at": "2026-10-24T09:00:00Z"},
        {"conclusion": "success", "created_at": "2026-10-23T11:59:00Z"},
    ]
    assert ad.zaehle_laeufe(laeufe, jetzt) == 2


def test_zaehlung_ignoriert_laeufe_ohne_agentenjob():
    from datetime import UTC, datetime

    jetzt = datetime(2026, 10, 24, 12, tzinfo=UTC)
    laeufe = [
        {"id": 1, "conclusion": "success", "created_at": "2026-10-24T10:00:00Z"},
        {"id": 2, "conclusion": "success", "created_at": "2026-10-24T09:00:00Z"},
    ]
    assert ad.zaehle_laeufe(laeufe, jetzt, lambda r: r["id"] == 2) == 1


def test_backlog_vertrauen_nur_bei_bot_und_wortgleichem_text():
    ziel = {"id": "z1", "freigegeben": True, "text": BODY}
    text = ad.rendere_ziel(ziel)
    bot = {"user": {"login": "github-actions[bot]"}, "body": text, "author_association": "NONE"}
    assert ad.vertraut_backlog(bot, [ziel])
    assert not ad.vertraut_backlog({**bot, "user": {"login": "fremd"}}, [ziel])
    assert not ad.vertraut_backlog({**bot, "body": text + "x"}, [ziel])
    assert not ad.vertraut_backlog(bot, [{**ziel, "freigegeben": False}])
    assert not ad.vertraut_backlog(bot, [])
    assert not ad.vertraut_backlog(bot, None)


def test_backlog_issue_wird_ohne_eigentuemer_assoziation_uebergeben():
    ziel = {"id": "preis", "freigegeben": True, "text": BODY}
    i = issue(
        author_association="NONE",
        user={"login": "github-actions[bot]"},
        body=ad.rendere_ziel(ziel),
    )
    ok, _ = ad.entscheide(i, "on", {"test_preis.py"}, 0, 0, ziele=[ziel])
    assert ok
    ok, grund = ad.entscheide(i, "on", {"test_preis.py"}, 0, 0, ziele=[])
    assert not ok and "Autor" in grund
