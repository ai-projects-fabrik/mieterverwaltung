# Planung: Format fuer Projektdefinition und Planergebnisse

Diese Datei beschreibt, wie ein Globalziel in ein mehrstufiges Projekt zerlegt wird. Sie ist die einzige Quelle fuer das Format; geprueft wird mit
`python tools/ziel_pruefen.py <projektordner>` (im Verzeichnis ai-projects, offline, ohne KI und ohne Kosten). Ein Planergebnis gilt nur, wenn dieses
Werkzeug Exit 0 liefert. Es gibt keine zweite Planungs-Infrastruktur: Zerlegung macht die Zielsteuerung der Leitstelle (Planungslauf) oder ein Mensch,
Bau, CI und Gates laufen im Projekt (Backlog-Manager, Dispatcher, Agent, `agent-gate`).

## 1. Zerlegung in Stufen

- Eine Stufe = ein Eintrag in `backlog/ziele.json` = ein Issue = **ein neues Modul** `src/<paket>/<modul>.py` plus `tests/test_<modul>.py`.
- Reihenfolge ueber `abhaengig_von` (Ziel-Ids). Der Backlog-Manager legt ein Issue erst an, wenn alle Voraussetzungen gemergt sind; er startet nach jeder
  gruenen CI auf main, die naechste Stufe folgt also von selbst.
- Keine Datei in zwei Stufen, auch nicht `__init__.py`. Abhaengige Module importieren nur oeffentliche Namen laut Modulvertrag in `AGENTS.md`.
- Spec-first: Zu jeder Stufe liegt `tests/akzeptanz/test_<modul>.py` auf main, von einem Menschen gemergt. Ohne sie uebergibt der Dispatcher nichts und das
  Gate merged nicht. Die Spec-Dateien enthalten die Beispiele wortgleich wie das Ziel (siehe `tests/akzeptanz/README.md`).

## 2. Eintrag in `backlog/ziele.json`

```json
{
  "id": "notizen-speicher",
  "titel": "Notizen-Speicher (Modul speicher)",
  "freigegeben": true,
  "abhaengig_von": [],
  "text": "**Datei:** `src/projekt/speicher.py` `tests/test_speicher.py`\n**Akzeptanztest:** `tests/akzeptanz/test_speicher.py`\n\n<Aufgabe, Modulvertrag, Regeln, Acceptance Criteria nach ISSUE-VORLAGE.md>"
}
```

`id`: Kleinbuchstaben, Ziffern, Bindestrich. `text`: hoechstens 6000 Zeichen; **Datei:** und **Akzeptanztest:** stehen je in einer eigenen Zeile.
Der Text wird wortgleich zum Issue; ausser diesen Feldern sind keine weiteren erlaubt.

## 3. Planergebnis (Nachplanung und Folgestufen)

Ein Planungslauf liefert eine JSON-Liste neuer Eintraege im Format aus Abschnitt 2 (hoechstens `max_offene_einheiten`, bei der Zielsteuerung ueblich 1 bis 3).
Pruefung vor jedem PR:

```
python tools/ziel_pruefen.py <projektordner> --eintraege plan.json --max 3 [--json]
```

Der Validator prueft die Liste als Anhang an die vorhandene `ziele.json`: Aufbau, Ids eindeutig und neu, Abhaengigkeiten aufloesbar und zyklenfrei,
keine Datei doppelt, und je Stufe die Eignung laut Dispatcher des Projekts (Zuschnitt, Spec auf main). Eine Stufe, deren Spec fehlt, ist nicht planbar:
Die Spec ist ein eigener Betreiber-PR, danach erst der Eintrag.

## 4. Projektdefinition (fuer `projekt_anlegen.py --definition`)

Ordner mit:

| Datei | Inhalt |
|---|---|
| `definition.json` | `fachregeln` (Liste einzeiliger Regeln), `modulvertrag` (Liste `{modul, funktionen, hinweis}`), `ziel` (`titel`, `beschreibung`, `erfolgskriterien`, `budget`) |
| `akzeptanz/test_<modul>.py` | Specs aller geplanten Module (kommen in den ersten Commit) |
| `backlog/ziele.json` | die geplanten Stufen laut Abschnitt 2 |

`ziel.erfolgskriterien`: 1 bis 5 Eintraege `{id, art: "befehl", befehl: [<Argumente>]}`, Exit 0 = erfuellt. `{python}` steht fuer den Interpreter;
die Befehle laufen im Projektwurzelordner und sind Argumentlisten, keine Shell-Zeilen. `ziel.budget`: `max_runden`, `max_usd`, `max_offene_einheiten`, `frist_tage`.

Der Generator prueft die Definition und die Zielliste **vor** dem Anlegen (bei Befund entsteht nichts) und schreibt `ziel-entwurf.json` im Format von
`ziel_anlegen` der Leitstelle (ohne Ziel-Id; Autorisierung per Klick dort).

## 5. Grenzen

Nie Teil eines Plans: Aenderungen an `.github/`, `AGENTS.md`, `tests/akzeptanz/`, Secrets, Berechtigungen, Merge, Push, neue Abhaengigkeiten oder Netzwerkzugriffe.
Ein Plan, der das braucht, ist `nicht_erreichbar` und geht als Frage an den Betreiber.
