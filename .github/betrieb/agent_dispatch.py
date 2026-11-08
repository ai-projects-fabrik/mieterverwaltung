# ruff: noqa: E501
"""Uebergibt ein geeignetes, risikoarmes Issue automatisch an den Agenten (Label `agent`).

Ausloeser: Label `agent-kandidat` auf einem Issue. Der Agent startet nur, wenn ALLE Bedingungen erfuellt sind:
Kill-Switch an (Variable AGENT_AUTO=on), Autor ist Repo-Eigentuemer/-Mitglied, Issue offen, noch nie uebergeben
(Label `agent-uebergeben`), Zuschnitt laut ISSUE-VORLAGE (genau ein neues Modul `src/...py` + `tests/test_<modul>.py`,
Akzeptanztest `tests/akzeptanz/test_<modul>.py` liegt auf dem Standard-Branch), hoechstens 15 Agentenlaeufe in 24 h,
hoechstens 5 Issues gleichzeitig in Arbeit (2 in der DeepSeek-Spitzenzeit, ausser Label `dringend`), keine gemeinsamen Dateien. Kosten: die Grenzen des kompilierten
Workflows (siehe README, Kostenbremsen) gelten zusaetzlich. Es wird nur der Issue-Text gelesen (als Daten) und nie ausgefuehrt.
"""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta

KANDIDAT = "agent-kandidat"
UEBERGEBEN = "agent-uebergeben"
AGENT = "agent"
MAX_LAEUFE_24H = 30  # temporaer verdoppelt (Betreiber 08.11.), passend zu 80 AIC
MAX_PARALLEL = 5  # ausserhalb der Spitzenzeit und fuer Issues mit Label `dringend`
MAX_PARALLEL_SPITZE = 2
DRINGEND = "dringend"
# DeepSeek-Tarif (offizielle Preisseite): Spitzenzeit Mo-Fr 01:00-04:00 und 06:00-10:00 UTC, sonst halber Preis. Chinesische
# Feiertage sind ganztaegig guenstig; eine Liste liegt nicht vor, deshalb zaehlen sie hier als Spitze (nur Verzoegerung, kein Mehrpreis).
SPITZE_UTC = ((1, 4), (6, 10))


def ist_spitze(jetzt):
    """True in der teuren Tarifzeit (Mo-Fr, UTC)."""
    jetzt = jetzt.astimezone(UTC)
    return jetzt.weekday() < 5 and any(a <= jetzt.hour < b for a, b in SPITZE_UTC)


def parallel_grenze(jetzt, dringend=False):
    """Gleichzeitige Agenten: 5 ausserhalb der Spitzenzeit (und immer bei dringend), 2 in der Spitzenzeit."""
    return MAX_PARALLEL_SPITZE if ist_spitze(jetzt) and not dringend else MAX_PARALLEL


MAX_BODY = 6000
AUTOREN = {"OWNER", "MEMBER", "COLLABORATOR"}
SRC = re.compile(r"^src/[a-z][a-z0-9_]*/([a-z][a-z0-9_]*)\.py$")
TEST = re.compile(r"^tests/test_([a-z][a-z0-9_]*)\.py$")
AKZ = re.compile(r"^tests/akzeptanz/test_([a-z][a-z0-9_]*)\.py$")
BACKLOG_BOT = "github-actions[bot]"
ZIEL_MARKER = re.compile(r"\A<!-- ziel:([a-z0-9][a-z0-9-]*) -->\n")


def gh(*args, token=None):
    """Fuehrt gh aus (optional mit anderem Token) und gibt stdout zurueck."""
    env = dict(os.environ, GH_TOKEN=token) if token else None
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, env=env).stdout


def felder(body):
    """Liest **Datei:** und **Akzeptanztest:** aus dem Issue-Text; gibt (Pfade, Akzeptanzpfade) zurueck."""
    datei = re.search(r"\*\*Datei:\*\*([^\n]*)", body)
    akz = re.search(r"\*\*Akzeptanztest:\*\*([^\n]*)", body)
    pfade = re.findall(r"`([^`]+)`", datei.group(1)) if datei else []
    akzp = re.findall(r"`([^`]+)`", akz.group(1)) if akz else []
    return pfade, akzp


def rendere_ziel(ziel):
    """Issue-Text eines freigegebenen Ziels (Marker plus Text); Quelle ist backlog/ziele.json auf dem Standard-Branch."""
    return f"<!-- ziel:{ziel['id']} -->\n{ziel['text']}"


def vertraut_backlog(issue, ziele):
    """True, wenn das Issue vom Backlog-Manager stammt: Autor ist der Actions-Bot und der Text ist WORTGLEICH der des
    freigegebenen Ziels auf dem Standard-Branch. Ein fremdes oder veraendertes Issue erbt so nie Eigentuemer-Vertrauen."""
    body = issue.get("body") or ""
    m = ZIEL_MARKER.match(body)
    if not m or (issue.get("user") or {}).get("login") != BACKLOG_BOT:
        return False
    return any(
        z.get("id") == m.group(1) and z.get("freigegeben") is True and rendere_ziel(z) == body
        for z in ziele or []
    )


def pruefe_grenzen(pfade, laeufe_24h, in_arbeit, belegte_pfade, max_parallel=MAX_PARALLEL):
    """Durchsatzgrenzen: Tageslimit, hoechstens max_parallel Issues gleichzeitig, keine gemeinsamen Dateien."""
    if laeufe_24h >= MAX_LAEUFE_24H:
        return f"Limit: {laeufe_24h} Agentenlaeufe in 24 h"
    if in_arbeit >= max_parallel:
        return f"{in_arbeit} Issues schon in Arbeit (Limit {max_parallel} parallel)"
    gemeinsam = sorted(set(pfade) & set(belegte_pfade))
    if gemeinsam:
        return f"Datei schon von einem Issue in Arbeit belegt: {gemeinsam[0]}"
    return None


def entscheide(
    issue,
    auto,
    akzeptanz,
    laeufe_24h,
    offene_agent_prs,
    belegte_pfade=frozenset(),
    ziele=None,
    max_parallel=MAX_PARALLEL,
):
    """Gibt (True, Grund) zurueck, wenn das Issue uebergeben werden darf, sonst (False, Grund)."""
    labels = {label["name"] for label in issue.get("labels", [])}
    if auto != "on":
        return False, "Kill-Switch aus (Variable AGENT_AUTO ist nicht on)"
    if issue.get("state") != "open" or issue.get("pull_request"):
        return False, "kein offenes Issue"
    if KANDIDAT not in labels:
        return False, f"Label {KANDIDAT} fehlt"
    if UEBERGEBEN in labels or AGENT in labels:
        return False, "schon uebergeben (keine Wiederholung ohne Mensch)"
    if issue.get("author_association") not in AUTOREN and not vertraut_backlog(issue, ziele):
        return False, "Autor ist kein Eigentuemer/Mitglied"
    body = issue.get("body") or ""
    if len(body) > MAX_BODY:
        return False, "Issue-Text zu lang"
    pfade, akzp = felder(body)
    src = [m for p in pfade if (m := SRC.match(p))]
    tst = [m for p in pfade if (m := TEST.match(p))]
    if len(pfade) != 2 or len(src) != 1 or len(tst) != 1 or src[0].group(1) != tst[0].group(1):
        return (
            False,
            "Zuschnitt: genau ein neues Modul src/<paket>/<modul>.py plus tests/test_<modul>.py",
        )
    modul = src[0].group(1)
    if len(akzp) != 1 or not (m := AKZ.match(akzp[0])) or m.group(1) != modul:
        return False, "Akzeptanztest laut Vorlage fehlt oder passt nicht zum Modul"
    if f"test_{modul}.py" not in akzeptanz:
        return False, "Akzeptanztest liegt nicht auf dem Standard-Branch (spec-first)"
    grenze = pruefe_grenzen(pfade, laeufe_24h, offene_agent_prs, belegte_pfade, max_parallel)
    if grenze:
        return False, grenze
    return True, f"Modul {modul}"


def zaehle_laeufe(laeufe, jetzt, hat_agentenjob=lambda lauf: True):
    """Zaehlt echte Agentenlaeufe der letzten 24 h.

    Uebersprungene Laeufe (andere Labels) und Laeufe, die vor dem Agentenjob stoppten (z. B. Berechtigungspruefung),
    kosten nichts und zaehlen nicht.
    """
    grenze = jetzt - timedelta(hours=24)
    return sum(
        1
        for r in laeufe
        if r.get("conclusion") != "skipped"
        and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) > grenze
        and hat_agentenjob(r)
    )


def laeufe_24h_api(repo):
    """Echte Agentenlaeufe der letzten 24 h laut Actions-Verlauf von issue-agent."""
    laeufe = json.loads(
        gh("api", f"repos/{repo}/actions/workflows/issue-agent.lock.yml/runs?per_page=50")
    )["workflow_runs"]

    def hat_agentenjob(lauf):
        jobs = json.loads(gh("api", f"repos/{repo}/actions/runs/{lauf['id']}/jobs"))["jobs"]
        return any(j["name"] == "agent" and j["conclusion"] != "skipped" for j in jobs)

    return zaehle_laeufe(laeufe, datetime.now(UTC), hat_agentenjob)


def lade_ziele(repo, standard):
    """Freigegebene Ziele (backlog/ziele.json auf dem Standard-Branch); bei jedem Fehler leer (kein Vertrauen)."""
    try:
        roh = gh(
            "api",
            f"repos/{repo}/contents/backlog/ziele.json?ref={standard}",
            "-H",
            "Accept: application/vnd.github.raw+json",
        )
        ziele = json.loads(roh)
        return ziele if isinstance(ziele, list) else []
    except (subprocess.CalledProcessError, ValueError):
        return []


def main(argv):
    nr = argv[1]
    repo = os.environ["GH_REPO"]
    issue = json.loads(gh("api", f"repos/{repo}/issues/{nr}"))
    standard = json.loads(gh("api", f"repos/{repo}"))["default_branch"]
    try:
        akzeptanz = {
            e["name"]
            for e in json.loads(gh("api", f"repos/{repo}/contents/tests/akzeptanz?ref={standard}"))
        }
    except (subprocess.CalledProcessError, ValueError, KeyError):
        akzeptanz = set()
    ziele = lade_ziele(repo, standard)
    laeufe_24h = laeufe_24h_api(repo)
    prs = json.loads(gh("api", f"repos/{repo}/pulls?state=open&per_page=50"))
    offene = sum(
        1 for p in prs if any(label["name"] == "agent-pr" for label in p.get("labels", []))
    )
    # In Arbeit = offene Issues mit Label agent-uebergeben (Lauf oder PR laeuft) und deren Dateien.
    arbeit = [
        i
        for i in json.loads(
            gh("api", f"repos/{repo}/issues?state=open&labels={UEBERGEBEN}&per_page=50")
        )
        if str(i["number"]) != str(nr) and not i.get("pull_request")
    ]
    belegt = {p for i in arbeit for p in felder(i.get("body") or "")[0]}
    ok, grund = entscheide(
        issue,
        os.environ.get("AGENT_AUTO", ""),
        akzeptanz,
        laeufe_24h,
        max(offene, len(arbeit)),
        belegt,
        ziele,
        parallel_grenze(
            datetime.now(UTC), DRINGEND in {label["name"] for label in issue.get("labels", [])}
        ),
    )
    print(f"Issue {nr}: {'UEBERGABE' if ok else 'keine Uebergabe'} ({grund})")
    if not ok:
        gh(
            "issue",
            "comment",
            nr,
            "--repo",
            repo,
            "--body",
            f"Keine automatische Uebergabe an den Agenten: {grund}.",
        )
        return 0
    token = os.environ.get("APP_TOKEN", "")
    if not token:
        print("STOPP: App-Token fehlt, keine Uebergabe")
        return 1
    gh("label", "create", UEBERGEBEN, "--repo", repo, "--force", "--color", "5319e7")
    gh("issue", "edit", nr, "--repo", repo, "--add-label", f"{UEBERGEBEN},{AGENT}", token=token)
    gh(
        "issue",
        "comment",
        nr,
        "--repo",
        repo,
        "--body",
        f"Automatisch an den Agenten uebergeben ({grund}; Tarif: {'Spitze' if ist_spitze(datetime.now(UTC)) else 'guenstig'}). Limits: hoechstens {MAX_LAEUFE_24H} Laeufe in 24 h, "
        f"hoechstens {MAX_PARALLEL} parallel ({MAX_PARALLEL_SPITZE} in der Spitzenzeit), keine Wiederholung ohne Mensch, Kostenbremse des Workflows (siehe README).",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
