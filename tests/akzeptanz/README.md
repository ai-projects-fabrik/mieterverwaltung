# Akzeptanztests (spec-first)

Hier liegen die Tests, die ein **Mensch vor dem Label `agent`** festlegt. Sie sind die unabhaengige
Wahrheit zu einem Issue: der Agent schreibt seine eigenen Tests in `tests/`, darf aber diesen Ordner
nicht anlegen, aendern, loeschen oder umbenennen (Agent-Gate und `AGENTS.md`).

## Regeln

- Ein Modul `src/<paket>/<modul>.py` hat genau eine Datei `tests/akzeptanz/test_<modul>.py`.
- Die Datei entsteht in einem eigenen kleinen Pull Request **vor** dem Umsetzungs-Issue und wird von
  einem Menschen gemergt (Review der Beispiele, nicht des Codes). Inhalt: die Beispiele der
  Acceptance Criteria, nichts Zusaetzliches.
- Das Agent-Gate verlangt fuer jeden Bot-PR, der ein Modul aendert, diese Datei auf dem
  Standard-Branch. Ohne sie wird `agent-gate` rot und es gibt keinen automatischen Merge.
- Vor dem Merge des Spec-Pull-Requests Konflikte mit `AGENTS.md` pruefen (Leerraum, Schreibweise,
  Fehlerverhalten). Die Spec gewinnt; widerspricht `AGENTS.md`, wird `AGENTS.md` vorher angepasst.
  Sonst meldet der Agent zu Recht `ABWEICHUNG:` und der Pull Request braucht einen Menschen.

## Neues Modul (Spec vor der Umsetzung)

Existiert `src/<paket>/<modul>.py` noch nicht, darf die Spec-Datei die CI nicht rot machen. Dafuer
steht am Anfang genau dieser Waechter: ueberspringen nur, solange die Quelldatei **fehlt**. Sobald
der Agent sie anlegt, laeuft die Spec; eine defekte Datei (Syntaxfehler, Importfehler) macht die
CI rot statt uebersprungen zu werden.

```python
import importlib.util

import pytest

if importlib.util.find_spec("<paket>.<modul>") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from <paket>.<modul> import <funktion>  # noqa: E402
```

Die Beispiele (`GUELTIG`, `UNGUELTIG`) gehoeren als Listen an den Anfang der Datei und werden im
Issue wortgleich wiederholt. `__init__.py` in diesem Ordner verhindert Namenskollisionen mit
`tests/test_<modul>.py`.

Beispiel und Beweis aus ch-import: `tests/akzeptanz/test_jahr.py` und
`.github/gate-tests/test_akzeptanz_mutanten.py` (sieben falsche Umsetzungen scheitern an der Spec).
