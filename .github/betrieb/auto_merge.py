# ruff: noqa: E501
"""Auto-Merge bei gruener CI (Betreiber-Anweisung LS-20261108-042, Variante A).

Laeuft aus `.github/workflows/auto-merge.yml` fuer offene, nicht als Entwurf markierte PRs gegen den Standard-Branch.
Es wird nie Code aus dem PR ausgefuehrt oder ausgecheckt; gelesen werden nur die Dateiliste und die Patches ueber die API.

Aendert ein PR etwas an Workflows (`.github/`), Gate-/Akzeptanzkriterien, Zielliste, Rechten/Allowlists/Hooks/Settings
oder Kostenbremsen, bekommt er das Label `needs-operator` und bleibt beim Betreiber (ein schon aktivierter Auto-Merge
wird zurueckgenommen). Sonst wird `gh pr merge --auto --squash` gesetzt; gemergt wird erst, wenn alle Pflichtchecks
des Rulesets (`test`, `agent-gate`) gruen sind. Traegt ein PR schon das Label, wird nichts aktiviert.
"""

import json
import os
import re
import subprocess
import sys

LABEL = "needs-operator"

# Pfade, die der Betreiber selbst freigibt (Regex, gegen den Pfad im PR).
GESCHUETZTE_PFADE = [
    (r"^\.github/", "Workflows und Betrieb (.github/)"),
    (r"^tests/akzeptanz/", "Akzeptanzkriterien (tests/akzeptanz)"),
    (r"^backlog/", "Zielliste/Gate-Konfiguration (backlog/)"),
    (r"(^|/)ziel-entwurf\.json$", "Ziel-Konfiguration"),
    (r"(^|/)ruleset[^/]*\.json$", "Ruleset/Branch-Schutz"),
    (r"(^|/)allowlist[^/]*\.json$", "Allowlist"),
    (r"(^|/)CODEOWNERS$", "CODEOWNERS"),
    (r"(^|/)hooks/", "Hooks"),
    (r"(^|/)\.claude/", "Claude-Konfiguration (.claude/)"),
    (r"(^|/)\.mcp\.json$", "MCP-Konfiguration"),
    (r"(^|/)settings[^/]*\.json$", "Settings (settings*.json)"),
    (r"(^|/)(AGENTS|CLAUDE)(\.local)?\.md$", "Agenten-Anweisungen"),
]
# Kostenbremsen: Schluesselwoerter in geaenderten Zeilen (egal in welcher Datei).
KOSTEN = re.compile(
    r"max[-_]ai[-_]credits|max[-_]daily[-_]ai[-_]credits|max[-_]usd|max[-_]runden|\bbudget",
    re.I,
)


def klassifiziere(dateien):
    """Gibt (ok, gruende) zurueck. `dateien` ist die Liste der PR-Dateien der GitHub-API
    (Felder `filename`, optional `previous_filename`, `patch`). Rein, ohne Netzwerkzugriff."""
    gruende = []
    for d in dateien:
        pfade = [d.get("filename", "")]
        if d.get("previous_filename"):
            pfade.append(d["previous_filename"])
        for pfad in pfade:
            for muster, name in GESCHUETZTE_PFADE:
                if re.search(muster, pfad):
                    gruende.append(f"{pfad}: {name}")
        patch = d.get("patch")
        if patch is None:
            gruende.append(f"{d.get('filename', '')}: Patch nicht lesbar (zu gross oder binaer)")
            continue
        for zeile in patch.splitlines():
            if zeile[:1] in "+-" and zeile[:3] not in ("+++", "---") and KOSTEN.search(zeile):
                gruende.append(f"{d.get('filename', '')}: Kostenbremse/Budget geaendert")
                break
    return (not gruende), sorted(set(gruende))


def gh(*args, token=None):
    """Fuehrt gh aus (optional mit anderem Token) und gibt stdout zurueck."""
    env = dict(os.environ, GH_TOKEN=token) if token else None
    cmd = ["gh", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=env).stdout


def main():
    repo = os.environ["REPO"]
    nr = os.environ["PR_NUMBER"]
    sha = os.environ["HEAD_SHA"]
    token = os.environ.get("MERGE_TOKEN") or None
    pr = json.loads(gh("api", f"repos/{repo}/pulls/{nr}"))
    standard = json.loads(gh("api", f"repos/{repo}"))["default_branch"]
    if pr["state"] != "open" or pr.get("draft"):
        print("Entwurf oder nicht offen: nichts zu tun.")
        return 0
    if pr["base"]["ref"] != standard or (pr["head"].get("repo") or {}).get("full_name") != repo:
        print("Fork-PR oder nicht gegen den Standard-Branch: nichts zu tun.")
        return 0
    if pr["head"]["sha"] != sha:
        print("HEAD hat sich geaendert; der neue Lauf prueft erneut.")
        return 0
    if token is None:
        print("Kein App-Token (AGENT_APP_ID/AGENT_APP_KEY): kein Auto-Merge.")
        return 0
    labels = {label["name"] for label in pr.get("labels", [])}
    seiten = json.loads(
        gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{nr}/files?per_page=100")
    )
    dateien = [d for seite in seiten for d in seite]
    ok, gruende = klassifiziere(dateien)
    if not ok:
        print(f"{LABEL}: " + "; ".join(gruende))
        gh("label", "create", LABEL, "--repo", repo, "--force", "--color", "d93f0b", token=token)
        gh("pr", "edit", nr, "--repo", repo, "--add-label", LABEL, token=token)
        if pr.get("auto_merge"):
            gh("pr", "merge", nr, "--repo", repo, "--disable-auto", token=token)
            print("Auto-Merge zurueckgenommen.")
        return 0
    if LABEL in labels:
        print(f"Label {LABEL} gesetzt: bleibt beim Betreiber.")
        return 0
    gh(
        "pr",
        "merge",
        nr,
        "--repo",
        repo,
        "--auto",
        "--squash",
        "--match-head-commit",
        sha,
        token=token,
    )
    print("Auto-Merge aktiviert (merged bei gruenen Pflichtchecks).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
