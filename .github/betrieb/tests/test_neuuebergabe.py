# ruff: noqa: E501
"""Tests der Zeitplan-Neuuebergabe (.github/betrieb/neuuebergabe.py)."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "neuuebergabe", Path(__file__).resolve().parent.parent / "neuuebergabe.py"
)
nu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nu)

T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
JETZT = T0 + timedelta(hours=3)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def issue(**kw):
    i = {"number": 43, "state": "open", "labels": [{"name": "agent"}, {"name": "agent-uebergeben"}]}
    i.update(kw)
    return i


def test_neuuebergabe_nach_abbruch():
    ok, grund = nu.entscheide(issue(), T0, [T0 + timedelta(minutes=2)], [], set(), JETZT)
    assert ok and "1 von" in grund


def test_kein_abbruch_nach_dem_label():
    assert not nu.entscheide(issue(), T0, [T0 - timedelta(minutes=5)], [], set(), JETZT)[0]
    assert not nu.entscheide(issue(), T0, [T0 + timedelta(hours=2)], [], set(), JETZT)[0]


def test_offener_pr_oder_kein_label_oder_geschlossen():
    ab = [T0 + timedelta(minutes=1)]
    assert not nu.entscheide(issue(), T0, ab, [], {43}, JETZT)[0]
    assert not nu.entscheide(issue(labels=[]), T0, ab, [], set(), JETZT)[0]
    assert not nu.entscheide(issue(state="closed"), T0, ab, [], set(), JETZT)[0]
    assert not nu.entscheide(issue(pull_request={"url": "x"}), T0, ab, [], set(), JETZT)[0]
    assert not nu.entscheide(issue(), None, ab, [], set(), JETZT)[0]


def test_versuchsgrenze_und_abstand():
    ab = [T0 + timedelta(minutes=1)]
    spaet = [{"created_at": iso(T0 - timedelta(hours=h)), "body": nu.MARKER} for h in range(1, 6)]
    assert "5 automatische" in nu.entscheide(issue(), T0, ab, spaet, set(), JETZT)[1]
    jung = [{"created_at": iso(JETZT - timedelta(minutes=10)), "body": nu.MARKER}]
    assert not nu.entscheide(issue(), T0, ab, jung, set(), JETZT)[0]
    alt = [{"created_at": iso(JETZT - timedelta(hours=2)), "body": nu.MARKER}]
    assert nu.entscheide(issue(), T0, ab, alt, set(), JETZT)[0]


def test_abbruchzeiten_nur_offene_aw_issues():
    aw = {
        "state": "open",
        "title": "[aw] Issue umsetzen exceeded daily AI credits budget",
        "created_at": iso(T0),
        "body": nu.ABBRUCH_TEXT,
    }
    zu = dict(aw, state="closed")
    fremd = dict(aw, title="Anderes Issue")
    kommentar = {"created_at": iso(T0 + timedelta(hours=1)), "body": f"x {nu.ABBRUCH_TEXT}"}
    egal = {"created_at": iso(T0 + timedelta(hours=2)), "body": "anderer Fehler"}
    z = nu.abbruchzeiten([aw, zu, fremd], lambda i: [kommentar, egal])
    assert z == [T0, T0 + timedelta(hours=1)]


def test_letztes_label():
    ev = [
        {"event": "labeled", "created_at": iso(T0), "label": {"name": "agent"}},
        {
            "event": "labeled",
            "created_at": iso(T0 + timedelta(hours=1)),
            "label": {"name": "agent"},
        },
        {
            "event": "labeled",
            "created_at": iso(T0 + timedelta(hours=2)),
            "label": {"name": "andere"},
        },
        {
            "event": "unlabeled",
            "created_at": iso(T0 + timedelta(hours=3)),
            "label": {"name": "agent"},
        },
    ]
    assert nu.letztes_label(ev) == T0 + timedelta(hours=1)
    assert nu.letztes_label([]) is None


def test_pr_ziele_und_laufstatus():
    assert nu.pr_ziele([{"body": "Closes #12 und fixes #7"}, {"body": None}]) == {12, 7}
    assert nu.laeuft_gerade([{"status": "completed"}, {"status": "in_progress"}])
    assert not nu.laeuft_gerade([{"status": "completed"}])


def test_retry_nach_verworfenem_pr_braucht_gate_marker_nach_dem_label():
    ohne_abbruch = []
    spaeter = [{"created_at": iso(T0 + timedelta(minutes=5)), "body": nu.GATE_MARKER}]
    frueher = [{"created_at": iso(T0 - timedelta(minutes=5)), "body": nu.GATE_MARKER}]
    ok, grund = nu.entscheide(issue(), T0, ohne_abbruch, spaeter, set(), JETZT)
    assert ok and "Retry" in grund
    assert not nu.entscheide(issue(), T0, ohne_abbruch, frueher, set(), JETZT)[0]
    assert not nu.entscheide(issue(), T0, ohne_abbruch, spaeter, {43}, JETZT)[0]


def pr_haengt(**kw):
    p = {
        "state": "open",
        "draft": False,
        "user": {"type": "Bot"},
        "mergeable_state": "blocked",
        "updated_at": iso(T0),
        "head": {"sha": "abc"},
    }
    p.update(kw)
    return p


GRUEN = [{"name": "test", "conclusion": "success"}, {"name": "agent-gate", "conclusion": "success"}]


def test_haengender_agenten_pr_wird_erkannt():
    assert nu.haengt(pr_haengt(), GRUEN, [], JETZT)


def test_kein_anstoss_wenn_etwas_anderes_blockiert_oder_zu_frisch():
    assert not nu.haengt(pr_haengt(mergeable_state="clean"), GRUEN, [], JETZT)
    assert not nu.haengt(pr_haengt(updated_at=iso(JETZT - timedelta(minutes=5))), GRUEN, [], JETZT)
    assert not nu.haengt(pr_haengt(draft=True), GRUEN, [], JETZT)
    assert not nu.haengt(pr_haengt(user={"type": "User"}), GRUEN, [], JETZT)
    assert not nu.haengt(pr_haengt(state="closed"), GRUEN, [], JETZT)
    assert not nu.haengt(pr_haengt(), GRUEN[:1], [], JETZT)
    assert not nu.haengt(
        pr_haengt(), [GRUEN[0], {"name": "agent-gate", "conclusion": "failure"}], [], JETZT
    )


def test_pr_ohne_check_runs_wird_nach_20_minuten_angestossen():
    assert nu.haengt(pr_haengt(mergeable_state="unknown"), [], [], JETZT)
    assert not nu.haengt(
        pr_haengt(mergeable_state="unknown", updated_at=iso(JETZT - timedelta(minutes=5))),
        [],
        [],
        JETZT,
    )
    assert not nu.haengt(pr_haengt(draft=True), [], [], JETZT)
    assert not nu.haengt(pr_haengt(user={"type": "User"}), [], [], JETZT)
    marke = [{"body": "<!-- neustoss:abc -->"}]
    assert not nu.haengt(pr_haengt(), [], marke, JETZT)
    assert nu.haengt(pr_haengt(head={"sha": "neu"}), [], marke, JETZT)


def test_anstoss_nur_einmal_je_commit():
    marke = [{"body": "<!-- neustoss:abc -->\nProtokoll"}]
    assert not nu.haengt(pr_haengt(), GRUEN, marke, JETZT)
    assert nu.haengt(pr_haengt(head={"sha": "neu"}), GRUEN, marke, JETZT)
