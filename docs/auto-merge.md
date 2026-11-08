# Auto-Merge bei gruener CI

Betreiber-Anweisung LS-20261108-042 (Variante A). Der Workflow `.github/workflows/auto-merge.yml` ruft
`.github/betrieb/auto_merge.py` auf und setzt bei offenen, nicht als Entwurf markierten PRs `gh pr merge --auto --squash`.
Gemergt wird erst, wenn alle Pflichtchecks des Rulesets (`test`, `agent-gate`) gruen sind.

## Was beim Betreiber bleibt (Label `needs-operator`, kein Auto-Merge)

- `.github/` (Workflows, Betrieb, Locks), `tests/akzeptanz/`, `backlog/`, `ziel-entwurf.json`
- Rechte/Schutz: `ruleset*.json`, `allowlist*.json`, `CODEOWNERS`, `hooks/`, `.claude/`, `.mcp.json`, `settings*.json`,
  `AGENTS.md`, `CLAUDE.md`
- Kostenbremsen: jede geaenderte Zeile mit `max-ai-credits`, `max-daily-ai-credits`, `max-usd`, `max-runden` oder `budget`
- nicht lesbare Patches (zu gross, binaer)

Traegt ein PR das Label schon, aktiviert der Workflow nichts; ein bereits aktivierter Auto-Merge wird bei einem neuen
Push mit geschuetzten Aenderungen zurueckgenommen. Das Label entfernt nur der Betreiber.

## Einmalig einrichten (Betreiber, nicht der Workflow)

Der Workflow aendert keine Repo-Einstellungen. Voraussetzungen pruefen bzw. setzen (PowerShell, Repo anpassen):

```powershell
$R = "ai-projects-fabrik/mieterverwaltung"
gh api repos/$R --jq '{allow_auto_merge, delete_branch_on_merge}'     # allow_auto_merge muss true sein
gh api -X PATCH repos/$R -F allow_auto_merge=true                       # falls false
gh api repos/$R/rulesets --jq '.[] | {id, name, enforcement}'          # main-schutz aktiv?
gh api repos/$R/rulesets/<ID> --jq '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks'
gh variable list -R $R                                                  # AGENT_APP_ID und AGENT_AUTO=on
gh secret list -R $R                                                    # AGENT_APP_KEY (nur Name)
```

Klicks: Repo, Settings, General, Pull Requests, "Allow auto-merge" anhaken. Settings, Rules, Rulesets, `main-schutz`:
"Require status checks" mit `test` und `agent-gate`. Ohne diese Pflicht-Checks wuerde Auto-Merge sofort mergen.

## Rueckweg

- Sofort stoppen: Settings, General, "Allow auto-merge" abwaehlen (`gh api -X PATCH repos/$R -F allow_auto_merge=false`).
  Schon aktivierte PRs mergen dann nicht mehr automatisch.
- Dauerhaft entfernen: den PR, der `auto-merge.yml` und `auto_merge.py` einfuehrt, per `git revert` zurueckdrehen (PR, Betreiber-Merge).
- Einzelnen PR anhalten: Label `needs-operator` setzen und im PR "Disable auto-merge" klicken.

## Grenzen

- Der Check laeuft bei jedem Push erneut. Ein Push kann zwischen Pruefung und Merge liegen, wenn alle Checks schon gruen sind;
  `--match-head-commit` bindet die Aktivierung an den geprueften Stand, ein spaeterer Push wird beim naechsten Lauf neu bewertet.
- Das Gate (`agent-gate`) bleibt Pflicht-Check und entscheidet bei Agenten-PRs weiter ueber Spec, Dateien und Tests.
