# ruff: noqa: E501
"""Mutationsprobe (manuell, ca. 10 Minuten, nicht in der CI).

Jede absichtlich kaputte Gate-Variante muss die Gate-Tests rot machen.
Aufruf vom Repo-Wurzelverzeichnis: python .github/gate-tests/mutationsprobe.py .
"""

import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

repo = sys.argv[1]
gate = open(os.path.join(repo, ".github", "workflows", "agent-gate.yml"), encoding="utf-8").read()
test = os.path.join(repo, ".github", "gate-tests", "test_gate.py")
DISPATCH = 'print("CI auf main ausgeloest." if rc == 0 else "CI auf main NICHT ausgeloest.")'

MIN_MUTANTEN = 40
# (alt, neu): ersetzt das ERSTE Vorkommen
MUTANTEN = {
    "Akzeptanz-Sperre entfernt": (
        "if p.lower().startswith(GESCHUETZT) or PLUGIN_AKZ_ORDNER in p.lower():",
        "if False:",
    ),
    "ABWEICHUNG-Pruefung entfernt": (
        'for m in ABWEICHUNG.finditer(pr.get("body") or ""):',
        "for m in []:",
    ),
    "Sitzungsregeln nicht im Mechanismus": (
        r"|(.*/)?CLAUDE(\.local)?\.md$|(.*/)?\.claude/|\.mcp\.json$",
        "",
    ),
    "Fremder Autor zugelassen": (
        'bot = pr["user"]["login"] in AGENT_AUTHORS and pr["user"]["type"] == "Bot"',
        "bot = True",
    ),
    "Pflicht-Check ignoriert": ("if len(pflicht) != 1 or", "if False and"),
    "HEAD-Vergleich entfernt": ('if pr["head"]["sha"] != head_sha:', "if False:"),
    "Spec-Pflicht entfernt": ('if f"test_{modul}.py" not in akzeptanz:', "if False:"),
    "Syntaxfehler": ("def pruefe(run_id, head_sha):", "def pruefe(:"),
    "Kill-Switch entfernt": ('    if zustand != "ok":\n', "    if False:\n"),
    "Kill-Switch: rot gilt als ok": ('if neu["conclusion"] != "success":', "if False:"),
    "Kill-Switch: laeuft gilt als ok": ('if neu["status"] != "completed":', "if False:"),
    "Branch weitergezogen wird geloescht": ('if aktuell != p["head"]["sha"]:', "if False:"),
    "Standard-Branch loeschbar": ("or ref == standard:", "or False:"),
    "Fork-Branch loeschbar": (
        'p["head"]["repo"]["full_name"] != REPO or ref == standard',
        "False or ref == standard",
    ),
    "Issues fremder Repos geschlossen": (
        'if k["repository"]["nameWithOwner"] != REPO or k["state"] != "OPEN":',
        'if k["state"] != "OPEN":',
    ),
    "Geschlossene Issues erneut": (
        'if k["repository"]["nameWithOwner"] != REPO or k["state"] != "OPEN":',
        'if k["repository"]["nameWithOwner"] != REPO:',
    ),
    "CI-Dispatch immer": ('if zustand == "keine":', "if True:"),
    "Dispatch-Fehler ignoriert": (DISPATCH, DISPATCH + "\n" + " " * 18 + "rc = 0"),
    "Nachlauf-Fehler nicht gezaehlt": ('STAND["fehler"] += probleme', "pass"),
    "Nachlauf mergt mehrere PRs": ('if STAND["gemergt"]:', "if False:"),
    "Nachlauf ignoriert rote main-CI": (
        'if lauf["status"] != "completed" or lauf["conclusion"] != "success":',
        "if False:",
    ),
    "Nachlauf nimmt Mensch-PRs": ('x["user"]["login"] in AGENT_AUTHORS and ', ""),
    "Gemergter PR: kein Nachlauf-Retry": ('if pr.get("merged"):', "if False:"),
    "Fallback ohne merged-Pflicht": (
        'if x.get("merged_at") and x["head"]["sha"] == sha',
        'if x["head"]["sha"] == sha',
    ),
    "Fallback: Mehrdeutigkeit akzeptiert": ("if len(kandidaten) > 1:", "if False:"),
    "Fallback: fremder Head-Commit": ('and x["head"]["sha"] == sha', ""),
    "Geschlossener PR bekommt Check": ('if pr["state"] != "open":', "if False:"),
    "Gemergter PR: Mensch wird bereinigt": (
        'if not bot or pr["head"]["sha"] != head_sha:',
        "if False:",
    ),
    "Warten ignoriert Auto-Merge-Rueckname": ('bool(p.get("auto_merge"))', "True"),
    "Warten ohne Zeitlimit-Ende": ("for i in range(WARTE_VERSUCHE + 1):", "for i in range(1):"),
    "Kein Merge-Zaehler nach --auto": ('STAND["gemergt"] += 1  # ab jetzt', "pass  # ab jetzt"),
    "Warten: Lesefehler nicht gezaehlt": ('STAND["fehler"] += 1', "pass"),
    "G1 Merge mit Standard-Token": ("head_sha, token=MERGE_TOKEN)", "head_sha)"),
    "G1 Ready mit Standard-Token": ('"--repo", REPO, token=MERGE_TOKEN)', '"--repo", REPO)'),
    "G1 Fehlendes App-Token ignoriert": ("if not MERGE_TOKEN:", "if False:"),
    "G1 App-Token wird ausgegeben": (
        'MERGE_TOKEN = os.environ.get("MERGE_TOKEN", "")',
        'MERGE_TOKEN = os.environ.get("MERGE_TOKEN", ""); print(MERGE_TOKEN)',
    ),
    "G1 Mint mit zusaetzlichem Recht": (
        "permission-pull-requests: write",
        "permission-pull-requests: write\n          permission-actions: write",
    ),
    "G1 Mint ohne Repo-Beschraenkung": (
        "repositories: ${{ github.event.repository.name }}",
        "# keine Einschraenkung",
    ),
    "G1 Mint ohne continue-on-error": ("continue-on-error: true", "continue-on-error: false"),
    "G1 Key im Python-Schritt": (
        "MERGE_TOKEN: ${{ steps.merge-token.outputs.token }}",
        "MERGE_TOKEN: ${{ steps.merge-token.outputs.token }}\n"
        "          AGENT_KEY: ${{ secrets.AGENT_APP_KEY }}",
    ),
    "G1 Job-Rechte erweitert": (
        "      checks: write",
        "      checks: write\n      packages: write",
    ),
    "G1 Warten auf Push-CI entfernt": (
        'for _ in range(CI_WARTE_VERSUCHE if zustand == "keine" else 0):',
        "for _ in range(0):",
    ),
    "Auto-Merge-Pflicht entfernt": ('if not repo.get("allow_auto_merge"):', "if False:"),
    # Unabhaengige Freigabe (Stand 2026-10-29): jede Abschwaechung muss die Gate-Tests rot machen.
    "Freigabe: Aenderungsanforderung ignoriert": (
        'if x["state"] == "CHANGES_REQUESTED":',
        "if False:",
    ),
    "Freigabe: Karenz ignoriert": ("if datetime.now(timezone.utc) < ende:", "if False:"),
    "Freigabe: Betreiber-Review auf altem Stand": (
        'if x["state"] != "APPROVED" or x.get("commit_id") != head_sha or login == autor:',
        'if x["state"] != "APPROVED" or login == autor:',
    ),
    "Freigabe: Pruefer-Review auf altem Stand, Typ und Autor ungeprueft": (
        'if not x or x["state"] != "APPROVED" or x.get("commit_id") != head_sha or x["user"]["type"] != "Bot" or FREIGABE_PRUEFER == autor:',
        'if not x or x["state"] != "APPROVED":',
    ),
    "Freigabe: halt-Label ignoriert": (
        'if any((x.get("name") or "").lower() == HALT_LABEL for x in pr.get("labels") or []):',
        "if False:",
    ),
    "Freigabe: fremde Verstoesse erlaubt": (
        "if any(v not in erlaubt for v in verstoesse):",
        "if False:",
    ),
    "Freigabe: Loeschen/Umbenennen erlaubt": (
        'if d["status"] in ("removed", "renamed") or d.get("previous_filename"):',
        "if False:",
    ),
    "Freigabe: Kontrolldatei darf stark gekuerzt werden": (
        'if KERN_PFAD.match(d["filename"]) and d.get("deletions", 0) > MAX_LOESCH_KERN:',
        "if False:",
    ),
    "Freigabe: Groessengrenze entfernt": ("nicht_test_zeilen(dateien) > MAX_ZEILEN_M", "False"),
    "Groesse: Testzeilen zaehlen mit": ('if not TEST_PFAD.search(d["filename"]))', "if True)"),
    "Berechtigungsdatei darf per Freigabe": ("if BERECHTIGUNGSDATEI.match(p):", "if False:"),
    "Freigabe immer aktiv": (
        'FREIGABE_AKTIV = os.environ.get("FREIGABE_AKTIV") == "on"',
        "FREIGABE_AKTIV = True",
    ),
    "Monitor-Reparatur: genau ein Closes entfernt": ("if len(nummern) != 1:", "if False:"),
    "Monitor-Reparatur: Umfang entfernt": (
        'if pr["additions"] + pr["deletions"] > MONITOR_MAX_ZEILEN or len(dateien) > MONITOR_MAX_DATEIEN:',
        "if False:",
    ),
    "Monitor-Reparatur: Pfadliste entfernt": ("or not MONITOR_PFAD.match(n) or", "or False or"),
    "Monitor-Reparatur: Titelmuster entfernt": (
        "if not (MONITOR_TITEL.match(titel) and",
        "if not (True and",
    ),
    "Monitor-Reparatur: Label entfernt": ('and "monitor" in labels and', "and True and"),
    "Monitor-Reparatur: Pull-Request als Issue": ('and "pull_request" not in issue)', "and True)"),
    "Monitor-Reparatur: einmal je Issue entfernt": (
        'if any((e or {}).get("event") in ("closed", "reopened") for e in ereignisse):',
        "if False:",
    ),
    "Monitor-Reparatur: Bot-Autor entfernt": (
        'if not (MONITOR_TITEL.match(titel) and (issue.get("user") or {}).get("login") == BACKLOG_BOT',
        "if not (MONITOR_TITEL.match(titel) and True",
    ),
    "Register: Betreiberkonto nicht geprueft": (
        'gemergt_von.get("login") == REPO.split("/")[0] and',
        "True and",
    ),
    "Register: App-Merge gilt": ('and gemergt_von.get("type") == "User")', "and True)"),
    "Register: ungemergter PR gilt": ('if not (p.get("merged") and', "if not (True and"),
    "Register: Merge-Commit nicht verglichen": ('x.get("merge_commit_sha") == sha', "True"),
    "Register: mehrere PRs zum Commit": (
        "if len(prs) != 1:\n                      return None",
        "if False:\n                      return None",
    ),
    "Register: Version nicht geprueft": ('reg.get("version") != 1 or', "False or"),
    "Register: Parameterbereich ignoriert": ("lo <= int(neu.group(2)) <= hi", "True"),
    "Register: Zeilenende des Parameters frei": ("alt.group(3) == neu.group(3)", "True"),
    "Register: Einrueckung des Parameters frei": ("alt.group(1) == neu.group(1)", "True"),
    "Register: mehrere geaenderte Zeilen": ("if len(minus) != 1 or len(plus) != 1:", "if False:"),
    "Register: Parameter fuer Agenten": (
        "and not bot and p == name and parameter_erlaubt",
        "and p == name and parameter_erlaubt",
    ),
    "Register: Datei nicht geschuetzt": (
        "|docs/betreiberentscheide\\.json)$",
        ")$",
    ),
    "Register: nicht gedeckte Pruefung der alten Spec": (
        "return all(p in gedeckt for p in alt[0])",
        "return True",
    ),
    "Register: Gegenpruefung nicht verlangt": (
        "if vorher not in alt[0] or nachher not in neu_liste:",
        "if False:",
    ),
    "Register: ersatzlos entfallen erlaubt": (
        'if not isinstance(u, dict) or not u.get("alt") or not u.get("neu"):',
        "if False:",
    ),
    "Register: aktiv_wenn der neuen Spec frei": ("if spec[1] != aktiv.get(n):", "if False:"),
    "Register: Marker nicht geprueft": ('spec[1]["enthaelt"] not in inhalt', "False"),
    "Register: wortgleich nicht in alter Spec": ("or p not in alt[0]:", "or False:"),
    "Register: vorhandene Spec darf abweichen": ("frueher[1] != jetzt[1]", "False"),
    "Register: Ziel-Spec nicht im HEAD": ("if jetzt is None or p not in jetzt[0]:", "if False:"),
}


def lauf(item):
    name, (alt, neu) = item
    assert alt in gate, (name, alt)
    d = tempfile.mkdtemp()
    p = os.path.join(d, "agent-gate.yml")
    open(p, "w", encoding="utf-8", newline="\n").write(gate.replace(alt, neu, 1))
    env = dict(os.environ, GATE_TEST_STOP_AT_FIRST_FAIL="1")
    r = subprocess.run(
        [sys.executable, test, p], capture_output=True, text=True, encoding="utf-8", env=env
    )
    return name, r.returncode != 0


MUTANTEN_ALLE = MUTANTEN
MUTANTEN = {n: m for n, m in MUTANTEN_ALLE.items() if m[0] in gate}
for _n in MUTANTEN_ALLE.keys() - MUTANTEN.keys():
    print(f"uebersprungen (Modul fehlt in diesem Projekt): {_n}")
assert len(MUTANTEN) >= MIN_MUTANTEN, f"nur {len(MUTANTEN)} Mutanten uebrig"

with ThreadPoolExecutor(max_workers=6) as pool:
    ergebnisse = list(pool.map(lauf, MUTANTEN.items()))
for name, rot in ergebnisse:
    print(f"{'ROT (gut)' if rot else 'GRUEN (Testluecke!)'}: {name}", flush=True)
alle_rot = all(rot for _, rot in ergebnisse)
print("ALLE MUTANTEN ERKANNT" if alle_rot else "TESTLUECKE", f"({len(ergebnisse)} Mutanten)")
sys.exit(0 if alle_rot else 1)
