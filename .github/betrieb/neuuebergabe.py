# ruff: noqa: E501
"""Zeitplan-Job: uebergibt Issues nach Tages-/Laufgrenze automatisch neu an den Agenten.

Drei Faelle, alle nur bei AGENT_AUTO=on und ohne neue Rechte (Issues-Label per App-Token):
1. Tagesbudget: Ein Lauf von `issue-agent` brach am Guardrail `max-daily-ai-credits` ab (gh-aw schreibt dazu einen Kommentar
   "Daily Workflow AIC Guardrail Exceeded" in das offene `[aw]`-Issue). Faellt dieser Abbruch kurz nach dem letzten Setzen des
   Labels `agent` auf ein offenes Issue ohne offenen PR, wird das Label neu gesetzt. Der Abbruch kostet nichts; hoechstens
   MAX_VERSUCHE Wiederholungen je Issue, mindestens MIN_ABSTAND dazwischen (Marker im Issue). Laeuft gerade ein Agentenlauf, passiert nichts.
2. Retry: Das Gate hat einen PR wegen "Datei nicht im Auftrag" verworfen und im Issue den Marker gate-retry gesetzt (einmalig,
   dort begrenzt); das Label `agent` wird neu gesetzt (das Gate-Token hat kein Issues-Recht).
3. Laufgrenze: Issues mit Label `agent-kandidat`, die noch nicht uebergeben sind (z. B. wegen MAX_LAEUFE_24H), werden ueber
   agent_dispatch.py erneut geprueft; alle Dispatch-Grenzen gelten unveraendert (NEU_STILL=1 unterdrueckt den Ablehnungskommentar).
Es wird nur Issue-Metadaten gelesen, nie Issue-Text ausgefuehrt.
"""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

AGENT = "agent"
UEBERGEBEN = "agent-uebergeben"
KANDIDAT = "agent-kandidat"
MARKER = "<!-- neuuebergabe -->"
GATE_MARKER = "<!-- gate-retry -->"  # setzt das Gate einmalig, wenn es einen PR wegen "Datei nicht im Auftrag" verworfen hat
MAX_VERSUCHE = 5
MIN_ABSTAND = timedelta(minutes=55)
KORRELATION = timedelta(
    minutes=20
)  # Abbruch-Kommentar so kurz nach dem Label gehoert zu diesem Label
MAX_KANDIDATEN = 3
ABBRUCH_TEXT = "Daily Workflow AIC Guardrail Exceeded"
FEHLER_TITEL = re.compile(r"^\[aw\] .*(Issue umsetzen|issue-agent)", re.I)
CLOSES = re.compile(r"\b(?:closes|fixes|resolves)\s+#(\d+)", re.I)


def zeit(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def gh(*args, token=None):
    env = dict(os.environ, GH_TOKEN=token) if token else None
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, env=env).stdout


def seiten(pfad):
    """Alle Seiten einer Listen-Antwort als flache Liste."""
    teile = json.loads(gh("api", "--paginate", "--slurp", pfad))
    return [x for teil in teile for x in (teil if isinstance(teil, list) else [teil])]


def abbruchzeiten(fehler_issues, kommentare_von):
    """Zeitpunkte aller Guardrail-Abbrueche: Text der offenen [aw]-Issues und ihrer Kommentare."""
    zeiten = []
    for i in fehler_issues:
        if i.get("state") != "open" or not FEHLER_TITEL.match(i.get("title") or ""):
            continue
        if ABBRUCH_TEXT in (i.get("body") or ""):
            zeiten.append(zeit(i["created_at"]))
        zeiten += [
            zeit(c["created_at"])
            for c in kommentare_von(i)
            if ABBRUCH_TEXT in (c.get("body") or "")
        ]
    return zeiten


def letztes_label(ereignisse):
    """Zeitpunkt des letzten Setzens von Label `agent` (None, wenn nie)."""
    z = [
        zeit(e["created_at"])
        for e in ereignisse
        if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == AGENT
    ]
    return max(z) if z else None


def entscheide(issue, label_zeit, abbrueche, kommentare, offene_pr_nummern, jetzt):
    """(True, Grund) wenn das Label `agent` neu gesetzt werden darf, sonst (False, Grund)."""
    labels = {x["name"] for x in issue.get("labels", [])}
    if issue.get("state") != "open" or issue.get("pull_request"):
        return False, "kein offenes Issue"
    if AGENT not in labels:
        return False, "Label agent fehlt"
    if issue["number"] in offene_pr_nummern:
        return False, "offener PR vorhanden"
    if label_zeit is None:
        return False, "Zeitpunkt des Labels unbekannt"
    if any(
        label_zeit < zeit(c["created_at"])
        for c in kommentare
        if GATE_MARKER in (c.get("body") or "")
    ):
        return True, "Retry nach verworfenem PR (Datei nicht im Auftrag)"
    if not any(label_zeit <= a <= label_zeit + KORRELATION for a in abbrueche):
        return False, "kein Guardrail-Abbruch nach dem letzten Label"
    marker = sorted(zeit(c["created_at"]) for c in kommentare if MARKER in (c.get("body") or ""))
    if len(marker) >= MAX_VERSUCHE:
        return False, f"schon {len(marker)} automatische Wiederholungen"
    if marker and jetzt - marker[-1] < MIN_ABSTAND:
        return False, "letzte Wiederholung noch keine Stunde her"
    return True, f"Versuch {len(marker) + 1} von {MAX_VERSUCHE}"


def pr_ziele(prs):
    """Issue-Nummern, die offene PRs mit 'Closes #N' schliessen wuerden."""
    return {int(m.group(1)) for p in prs for m in CLOSES.finditer(p.get("body") or "")}


def laeuft_gerade(laeufe):
    return any(r.get("status") in ("queued", "in_progress", "waiting", "pending") for r in laeufe)


def main():
    repo = os.environ["GH_REPO"]
    if os.environ.get("AGENT_AUTO") != "on":
        print("Kill-Switch aus (AGENT_AUTO ist nicht on): nichts zu tun.")
        return 0
    jetzt = datetime.now(UTC)
    laeufe = json.loads(
        gh("api", f"repos/{repo}/actions/workflows/issue-agent.lock.yml/runs?per_page=20")
    )["workflow_runs"]
    if laeuft_gerade(laeufe):
        print("Ein Agentenlauf laeuft gerade: nichts zu tun.")
        return 0
    token = os.environ.get("APP_TOKEN", "")
    if not token:
        print("STOPP: App-Token fehlt, keine Neuuebergabe")
        return 1
    fehler = [
        i
        for i in seiten(f"repos/{repo}/issues?state=open&per_page=100")
        if not i.get("pull_request") and FEHLER_TITEL.match(i.get("title") or "")
    ]
    abbrueche = abbruchzeiten(
        fehler, lambda i: seiten(f"repos/{repo}/issues/{i['number']}/comments?per_page=100")
    )
    code = 0
    prs = seiten(f"repos/{repo}/pulls?state=open&per_page=100")
    offene = pr_ziele(prs)
    for issue in seiten(f"repos/{repo}/issues?state=open&labels={AGENT}&per_page=100"):
        if issue.get("pull_request"):
            continue
        nr = issue["number"]
        kommentare = seiten(f"repos/{repo}/issues/{nr}/comments?per_page=100")
        label_zeit = letztes_label(seiten(f"repos/{repo}/issues/{nr}/events?per_page=100"))
        ok, grund = entscheide(issue, label_zeit, abbrueche, kommentare, offene, jetzt)
        print(f"Issue {nr}: {'NEUUEBERGABE' if ok else 'nichts'} ({grund})")
        if not ok:
            continue
        gh(
            "issue",
            "comment",
            str(nr),
            "--repo",
            repo,
            "--body",
            f"{MARKER}\nAutomatische Neuuebergabe nach Abbruch am Tagesbudget ({grund}).",
        )
        gh("issue", "edit", str(nr), "--repo", repo, "--remove-label", AGENT)
        gh(
            "issue", "edit", str(nr), "--repo", repo, "--add-label", AGENT, token=token
        )  # nur das App-Token startet den Lauf
        break  # hoechstens ein Issue je Zeitplanlauf: der Tageszaehler entscheidet danach neu
    kandidaten = [
        i
        for i in seiten(f"repos/{repo}/issues?state=open&labels={KANDIDAT}&per_page=100")
        if not i.get("pull_request")
        and not ({x["name"] for x in i["labels"]} & {AGENT, UEBERGEBEN})
    ]
    for i in kandidaten[:MAX_KANDIDATEN]:
        skript = Path(__file__).resolve().parent / "agent_dispatch.py"
        r = subprocess.run(
            [sys.executable, str(skript), str(i["number"])],
            env=dict(os.environ, NEU_STILL="1"),
            capture_output=True,
            text=True,
        )
        print(r.stdout.strip() or r.stderr.strip()[-300:])
        code = max(code, 1 if r.returncode else 0)
    return code


if __name__ == "__main__":
    sys.exit(main())
