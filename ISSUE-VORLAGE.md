# Issue-Vorlage fuer Agentenlaeufe

Kopieren, fuellen, als Issue anlegen. Das Label `agent` erst setzen, wenn alle genannten
Abhaengigkeiten gemergt sind. Bewaehrt im Autonomietest (acht Issues, acht gruene PRs im ersten Lauf).

**Spec-first (Pflicht fuer Projekte mit Auto-Merge):** Bevor das Label `agent` gesetzt wird, liegt
`tests/akzeptanz/test_<modul>.py` auf dem Standard-Branch. Die Datei enthaelt genau die Beispiele
der Acceptance Criteria, ein Mensch hat sie in einem eigenen kleinen Pull Request gemergt, und der
Agent darf sie nicht aendern (Agent-Gate). Ohne diese Datei gibt es fuer das Modul keinen
automatischen Merge. Vorgehen, Waechter fuer noch fehlende Module und Beispiel: `tests/akzeptanz/README.md`
im Projekt (Beispiel ch-import: `test_jahr.py`).

```
**Datei:** nur `src/<paket>/<modul>.py` und `tests/test_<modul>.py`. **Abhaengigkeiten:** keine
(oder: Issues #x, #y muessen gemergt sein). **Akzeptanztest:** `tests/akzeptanz/test_<modul>.py`
(gemergt in PR #z).

Funktionen laut Modulvertrag in `AGENTS.md`: `<name>(<typ>) -> <typ>`.

**Regeln**
- <Fachregel mit Quelle, die in den Modul-Docstring gehoert>
- <Eingabeformate und Standardschreibweise mit Beispiel>

**Acceptance Criteria**
- gueltig: <konkrete Beispiele>
- ungueltig: <konkrete Grenzfaelle, auch Nicht-ASCII und leere Eingabe>
- <Verhalten bei ungueltiger Eingabe: bool oder ValueError>
- Kollision mit `AGENTS.md` geprueft (Leerraum, Schreibweise, Fehlerverhalten): <ja, keine / Spec
  gewinnt, `AGENTS.md` angepasst in PR #y>
```

Regeln fuer den Zuschnitt:

- Ein Issue = ein Modul + dessen Testdatei. Keine Datei in zwei Issues, auch nicht `__init__.py`.
- Beispielwerte im Issue selbst nachrechnen; der Agent uebernimmt sie als Testfaelle. Dieselben
  Werte stehen wortgleich im Akzeptanztest (eine Quelle, kein Auseinanderlaufen).
- Abhaengige Issues erst nach dem Merge ihrer Voraussetzungen starten, nicht nur nach dem Draft-PR.
