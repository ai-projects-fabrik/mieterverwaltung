"""Tests fuer die Pfad- und Kostenregeln des Auto-Merge (rein, ohne Netzwerk)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auto_merge as am  # noqa: E402


def datei(name, patch="@@ -1 +1 @@\n-alt\n+neu", **extra):
    return {"filename": name, "patch": patch, **extra}


def test_normale_aenderung_ist_ok():
    ok, gruende = am.klassifiziere([datei("src/projekt/x.py"), datei("tests/test_x.py")])
    assert ok
    assert gruende == []
    assert am.klassifiziere([])[0]


@pytest.mark.parametrize(
    "pfad",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/auto-merge.yml",
        ".github/betrieb/backlog.py",
        "tests/akzeptanz/test_felder.py",
        "backlog/ziele.json",
        "ziel-entwurf.json",
        "ruleset-main.json",
        "config/allowlist.json",
        "CODEOWNERS",
        "hooks/pre-commit",
        ".claude/settings.json",
        ".mcp.json",
        "settings.local.json",
        "AGENTS.md",
        "CLAUDE.md",
    ],
)
def test_geschuetzte_pfade_gehen_zum_betreiber(pfad):
    ok, gruende = am.klassifiziere([datei("src/projekt/x.py"), datei(pfad)])
    assert not ok
    assert any(pfad in g for g in gruende)


def test_umbenennung_aus_geschuetztem_pfad_zaehlt():
    ok, _ = am.klassifiziere([datei("docs/x.md", previous_filename=".github/workflows/ci.yml")])
    assert not ok


@pytest.mark.parametrize(
    "zeile",
    [
        "+max-ai-credits: 12",
        "-max-daily-ai-credits: 40",
        "+  GH_AW_MAX_DAILY_AI_CREDITS: 80",
        '+"max_usd": 2',
        "+budget = 5",
        "+max_runden = 9",
    ],
)
def test_kostenbremsen_in_geaenderten_zeilen(zeile):
    ok, gruende = am.klassifiziere([datei("src/projekt/x.py", patch=f"@@ -1 +1 @@\n{zeile}")])
    assert not ok
    assert any("Kostenbremse" in g for g in gruende)


def test_kosten_in_unveraenderten_zeilen_und_kopfzeilen_zaehlen_nicht():
    patch = "--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n max-ai-credits: 12\n-alt\n+neu"
    assert am.klassifiziere([datei("src/projekt/x.py", patch=patch)])[0]


def test_nicht_lesbarer_patch_geht_zum_betreiber():
    ok, gruende = am.klassifiziere([{"filename": "src/projekt/gross.py"}])
    assert not ok
    assert "Patch nicht lesbar" in gruende[0]


def test_gruende_sind_eindeutig_und_sortiert():
    ok, gruende = am.klassifiziere([datei("tests/akzeptanz/a.py"), datei("tests/akzeptanz/a.py")])
    assert not ok
    assert gruende == sorted(set(gruende))
    assert len(gruende) == 1


def test_workflow_hat_kein_if_am_job():
    """Ein uebersprungener Job ergibt eine Suite 'skipped': agent-gate wird dort nicht gewertet."""
    import yaml

    wf = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "workflows" / "auto-merge.yml").read_text(
            encoding="utf-8"
        )
    )
    assert all("if" not in job for job in wf["jobs"].values())
