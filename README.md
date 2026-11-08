# mieterverwaltung

Mietvertrag per Anfrage auf den aktuellen Mieter anpassen (Vorlage .docx, Platzhalter, Aenderungsbericht). Coding-Agenten setzen Issues autonom um; ein Mensch legt vorab die Akzeptanztests fest
(`tests/akzeptanz/`) und merged, sofern Auto-Merge nicht bewusst erlaubt ist.
Konventionen: `ai-projects/KONVENTIONEN.md`.

## Ablauf

1. Issue schreiben und Label `agent` setzen.
2. GitHub Agentic Workflows startet den Coding-Agenten (Anbieter: `.github/workflows/shared/anbieter.md`)
   mit Leserechten, Netzwerk-Allowlist und API-Key nur im Proxy.
3. Der Agent setzt das Issue um und fuehrt `ruff` und `pytest` aus (Regeln in `AGENTS.md`).
   Technisch erzwungen (Workflow, nicht verhandelbar): nur `src/` und `tests/`, Manifest- und
   Anweisungsdateien gesperrt, Patch hoechstens 200 KB. Verstoesse verhindern den Pull Request.
4. Ein Pruefjob kontrolliert das Ergebnis, danach entsteht ein Draft-Pull-Request.
5. Der Pull Request wird mit dem Token der eigenen GitHub App erstellt (`APP-EINRICHTUNG.md`): die CI
   (`.github/workflows/ci.yml`, Pflicht-Check `test`) startet ohne Freigabeklick. Ohne App braucht
   sie pro PR einen Klick ("Approve and run").
6. Das Agent-Gate (`.github/workflows/agent-gate.yml`) prueft nach der CI Autor, HEAD, Dateien
   (nur `src/` und `tests/`), Tests, Groesse, Akzeptanztest (`tests/akzeptanz/`, spec-first),
   `ABWEICHUNG:`-Zeile und den Zustand der CI auf main, und setzt den Pflicht-Check `agent-gate`.
7. Merge: Standard ist Handarbeit (Mensch prueft und merged). Nur wenn das Repo Auto-Merge
   (`allow_auto_merge`) bewusst erlaubt, merged das Gate gruene Agenten-PRs selbst (Ready/Merge mit kurzlebigem App-Token, G1, siehe
   `APP-EINRICHTUNG.md`; ohne Token kein Merge). Der App-Merge startet die CI auf main; deren Ende loest den
   Gate-Nachlauf aus (Issues schliessen, Branch loeschen, naechsten PR bewerten).

## Kostenbremsen

Standardbudget (1 AIC = 0.01 USD): Agent hoechstens 12 AI-Credits pro Lauf, Pruefjob 2,
alle Laeufe zusammen 300 pro 24 Stunden (3 USD, Betreiberentscheid 2026-11-08), hoechstens 30 Minuten. Der Proxy stoppt Anfragen ueber dem Limit
(Lauf endet ohne PR). Reale Laeufe: Median ca. 1.2, Maximum 3.1 AIC; Limit je Projekt nur bewusst erhoehen
(`max-ai-credits` im Frontmatter, danach neu kompilieren). Harte Grenze zusaetzlich: Prepaid-Guthaben beim Anbieter.

## Entwicklung lokal

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\ruff check .
.venv\Scripts\pytest
```
