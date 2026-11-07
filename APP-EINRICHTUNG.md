# GitHub App fuer Agenten-PRs (einmalig je Konto, je Repo installieren)

Warum: Pull Requests, die der Agent mit dem normalen `GITHUB_TOKEN` erstellt, loesen weder die CI
(ohne Freigabeklick) noch weitere Workflows aus. Mit dem kurzlebigen Installations-Token einer
eigenen GitHub App startet die CI sofort, und das Agent-Gate (`agent-gate.yml`) sieht den PR.
Belegt in ch-import (Stufe D, 2026-10-18).

## Einmalig je Konto (Mensch)

1. GitHub, Settings, Developer settings, GitHub Apps, New GitHub App.
2. Name zum Beispiel `ai-projects-agent-pr` (muss global eindeutig sein). Webhook **deaktivieren**.
   Homepage-URL beliebig. "Where can this GitHub App be installed": Only on this account.
3. Repository permissions, nur diese drei: `Contents`, `Issues`, `Pull requests`, je Read and write.
   Sonst nichts (kein `Workflows`, kein `Actions`).
4. Create GitHub App. Client ID (beginnt mit `Iv`) notieren, Slug aus der App-URL notieren.
5. "Generate a private key" (`.pem`-Datei in Downloads).

## Je Projekt (Mensch oder Claude, Schluessel nie in den Chat oder ins Repo)

6. App auf das Repo installieren: Install App, Only select repositories, nur dieses Repo.
7. `gh variable set AGENT_APP_ID -R <konto>/<repo> --body "<Client ID>"`
8. `Get-Content -Raw "<pfad>\key.pem" | gh secret set AGENT_APP_KEY -R <konto>/<repo>`
9. `.pem` aus Downloads loeschen, wenn kein weiteres Repo mehr folgt (sonst sicher aufbewahren).
10. In `.github/workflows/agent-gate.yml` den Platzhalter `@@APP_SLUG@@` durch den Slug ersetzen
    (der Bot-Login ist `<slug>[bot]`). Danach neu kompilieren mit dem Workflow `aw-compile.yml`
    (PR-Lauf, Lock aus dem Artefakt `aw-compile` in den PR; wegen des neuen Secrets `AGENT_APP_KEY`
    und der Action `create-github-app-token` ist `approve` noetig: Diff pruefen, dann per
    Dispatch mit `-f approve=true` freigeben).
11. Ruleset `ruleset-main.json` erst setzen, **nachdem** `agent-gate.yml` auf main liegt (sonst
    blockiert sich der erste PR selbst): `agent-gate` ist Pflicht-Check.

## Eigenschaften und Grenzen

- Der Token wird pro Lauf gemint (contents, issues, pull-requests: write, nur dieses Repo) und laeuft
  ab. Der Private Key bleibt als Secret das empfindlichste Stueck: nur dieses Repo, nie lokal speichern.
- Commit-Autor und PR-Autor sind `<slug>[bot]`; das Gate akzeptiert `github-actions[bot]` und genau diesen Slug.
- Gate-Merge (G1): Das Gate mintet zusaetzlich pro Lauf ein Token (nur contents + pull-requests: write,
  nur dieses Repo) und nutzt es ausschliesslich fuer `gh pr ready` und `gh pr merge`. Grund: Ein Merge mit
  dem Standard-Token (GITHUB_TOKEN) loest keine CI auf main aus, ein App-Merge schon; deren Ende startet
  den Gate-Nachlauf. Gleiche Variable und gleiches Secret wie oben, keine neuen App-Rechte. Fehlt das
  Token, merged das Gate nicht (Exit 1, Check bleibt gesetzt). Belegt in vorlage-test (PR #9).
- Ohne App funktioniert der Ablauf weiter, aber die CI braucht pro PR einen Freigabeklick und das Gate
  laeuft bei Bot-PRs nicht; der Merge bleibt Handarbeit.
