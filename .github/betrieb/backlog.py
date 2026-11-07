# ruff: noqa: E501
"""Backlog-Manager: macht aus freigegebenen Zielen (backlog/ziele.json auf main) testbare Issues und uebergibt sie.

Laeuft per Zeitplan in GitHub Actions (also ohne offenes Terminal). Er baut NICHTS Neues neben dem Dispatcher auf:
Er legt hoechstens wenige Issues pro Lauf an (Text wortgleich aus der Zielliste, Label `agent-kandidat`) und ruft danach
.github/betrieb/agent_dispatch.py auf, der alle bisherigen Pruefungen, Limits (15 Laeufe/24 h, 5 parallel, in der DeepSeek-Spitzenzeit 2, keine gemeinsamen Dateien)
und die Kill-Switch-Variable AGENT_AUTO weiter selbst durchsetzt. Die Zielliste ist Teil des Schutzkerns: Nur ein Mensch aendert
sie (PR auf main), kein Agent. Es werden nur Ziele angelegt, deren Abhaengigkeiten erledigt (Issue geschlossen als completed) sind.

Kontrollen: Kosten (Tageslimit minus bisherige Laeufe), Qualitaet (zwei abgebrochene Ziele = Pause), Fortschritt (zwei
Ziel-Issues seit ueber 24 h in Arbeit ohne Abschluss = Pause). Kill-Switch aus = nichts passiert.

Tarifzeit: In der teuren DeepSeek-Spitzenzeit (Mo-Fr 01-04 und 06-10 UTC) legt er keine normalen Ziele an; sie warten hoechstens
4 Stunden auf die guenstige Zeit. Ziele mit `"dringend": true` starten sofort (Label `dringend`, volle Parallelitaet).
"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import agent_dispatch as ad

MAX_NEU_PRO_LAUF = 2
STAU_STUNDEN = 24
MAX_STAU = 2
MAX_ABGEBROCHEN = 2


def ziel_id(issue):
    """Ziel-ID eines vom Manager angelegten Issues (Marker in der ersten Zeile), sonst None."""
    m = ad.ZIEL_MARKER.match(issue.get("body") or "")
    if not m or (issue.get("user") or {}).get("login") != ad.BACKLOG_BOT:
        return None
    return m.group(1)


def zustaende(issues):
    """Ziel-ID -> 'offen' | 'erledigt' | 'abgebrochen' (neuestes Issue je Ziel zaehlt)."""
    z = {}
    for i in sorted(issues, key=lambda i: i["number"]):
        zid = ziel_id(i)
        if zid is None or i.get("pull_request"):
            continue
        if i["state"] == "open":
            z[zid] = "offen"
        else:
            z[zid] = "erledigt" if i.get("state_reason") == "completed" else "abgebrochen"
    return z


def waehle(ziele, issues, laeufe_24h, jetzt):
    """Gibt (Liste neu anzulegender Ziele, Grund) zurueck. Rein; keine Netzwerkzugriffe."""
    zust = zustaende(issues)
    if sum(1 for v in zust.values() if v == "abgebrochen") >= MAX_ABGEBROCHEN:
        return (
            [],
            f"Pause: {MAX_ABGEBROCHEN} abgebrochene Ziele (Qualitaetskontrolle, Mensch pruefen)",
        )
    grenze = jetzt - timedelta(hours=STAU_STUNDEN)
    offen = [i for i in issues if ziel_id(i) and i["state"] == "open"]
    alt = [
        i for i in offen if datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")) < grenze
    ]
    if len(alt) >= MAX_STAU:
        return (
            [],
            f"Pause: {len(alt)} Ziel-Issues seit ueber {STAU_STUNDEN} h offen (Fortschrittskontrolle)",
        )
    spitze = ad.ist_spitze(jetzt)
    plaetze = min(
        ad.parallel_grenze(jetzt, dringend=True) - len(offen),
        ad.MAX_LAEUFE_24H - laeufe_24h,
        MAX_NEU_PRO_LAUF,
    )
    if plaetze <= 0:
        return [], "keine freie Kapazitaet (parallel oder Tageslimit)"
    belegt = {p for i in issues if i["state"] == "open" for p in ad.felder(i.get("body") or "")[0]}
    ids = {z.get("id") for z in ziele}
    gewaehlt = []
    for z in ziele:
        if z.get("freigegeben") is not True or z.get("id") in zust:
            continue
        if spitze and z.get("dringend") is not True:
            continue  # normale Ziele warten auf die guenstige Tarifzeit
        deps = z.get("abhaengig_von", [])
        if any(d not in ids or zust.get(d) != "erledigt" for d in deps):
            continue
        pfade = set(ad.felder(z["text"])[0])
        if not pfade or pfade & belegt:
            continue
        gewaehlt.append(z)
        belegt |= pfade
        if len(gewaehlt) >= plaetze:
            break
    zusatz = "; Spitzenzeit: nur dringende Ziele" if spitze else ""
    return gewaehlt, f"{len(gewaehlt)} Ziel(e) bereit, {plaetze} Platz/Plaetze{zusatz}"


def alle_issues(repo):
    teile = []
    for seite in (1, 2, 3):
        teil = json.loads(ad.gh("api", f"repos/{repo}/issues?state=all&per_page=100&page={seite}"))
        teile += teil
        if len(teil) < 100:
            break
    return teile


def main(argv):
    repo = os.environ["GH_REPO"]
    trocken = "--trocken" in argv
    if os.environ.get("AGENT_AUTO") != "on":
        print("Kill-Switch aus (AGENT_AUTO ist nicht on): nichts zu tun.")
        return 0
    standard = json.loads(ad.gh("api", f"repos/{repo}"))["default_branch"]
    ziele = ad.lade_ziele(repo, standard)
    issues = alle_issues(repo)
    jetzt = datetime.now(UTC)
    gewaehlt, grund = waehle(ziele, issues, ad.laeufe_24h_api(repo), jetzt)
    print(grund)
    if trocken:
        print("Trockenlauf:", [z["id"] for z in gewaehlt])
        return 0
    if gewaehlt:
        ad.gh("label", "create", ad.KANDIDAT, "--repo", repo, "--force", "--color", "fbca04")
        ad.gh("label", "create", ad.DRINGEND, "--repo", repo, "--force", "--color", "b60205")
    for z in gewaehlt:
        url = ad.gh(
            "issue", "create", "--repo", repo, "--title", z["titel"],
            "--body", ad.rendere_ziel(z),
            "--label", ad.KANDIDAT + (f",{ad.DRINGEND}" if z.get("dringend") is True else ""),
        ).strip()  # fmt: skip
        nr = url.rsplit("/", 1)[-1]
        print(f"Ziel {z['id']}: Issue #{nr} angelegt, Uebergabe wird geprueft")
        try:
            ad.main(["agent_dispatch.py", nr])
        except subprocess.CalledProcessError as fehler:
            print(f"Uebergabe von #{nr} fehlgeschlagen: {fehler}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
