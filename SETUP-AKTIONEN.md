# Einrichtung von mieterverwaltung: Befehle und Zustaendigkeiten

Erzeugt von `ai-projects/tools/projekt_anlegen.py`. Reihenfolge einhalten. Kostenlos bis einschliesslich Schritt G.
Der Generator hat nichts bei GitHub veraendert.

## A. Git initialisieren, erster Commit (ohne Lock) (Claude (nach OK))

```powershell
git init -b main
git config user.name "ai-projects-fabrik"
git config user.email "noreply@example.invalid"
git add -A
git commit -m "Projekt aus ai-projects/vorlage"
```

## B. Repo ai-projects-fabrik/mieterverwaltung einrichten (public, Rechte, Labels, Ruleset, Schalter) (Claude (nach autorisiertem Ziel))

```powershell
python tools/projekt_einrichten.py mieterverwaltung --ziel <Z-ID>    # Trockenlauf, zeigt Plan und fehlende Voraussetzungen
python tools/projekt_einrichten.py mieterverwaltung --ziel <Z-ID> --ja
```

Nur mit autorisiertem Ziel der Leitstelle, dessen Text Repo, Sichtbarkeit, Budget, allow_auto_merge und AGENT_AUTO nennt. Secrets setzt das Werkzeug nie; Org-Ebene pruefen: python tools/org_einrichten.py --org ai-projects-fabrik

## C. Lock der Agenten-Workflows (aw-compile), .github-PR (Claude (nach OK))

```powershell
gh workflow run aw-compile.yml -R ai-projects-fabrik/mieterverwaltung -f approve=true  # Diff der neuen Secrets/Actions vorher pruefen
gh run download <run-id> -R ai-projects-fabrik/mieterverwaltung -n aw-compile  # Lock als .github-PR; Betreiber merged (Freigabemechanismus)
```

Bis die Vorlage das Lock mitbringt (Pruefung LS-20261104-006 Punkt 3).

## K. Zielsteuerung der Leitstelle anbinden (Betreiber (ein Klick) + leitstelle-bau)

```powershell
ziel_anlegen mit ziel-entwurf.json, danach ziel_autorisieren: voller Text, ein Klick
Projekt in der Leitstellen-Konfiguration registrieren (Schluessel laut Auftrag L1)
```

`ziel-entwurf.json` danach entfernen.
