# AGENTS.md - Regeln fuer jeden Coding-Agenten in diesem Repo

Diese Datei gilt unabhaengig vom Agenten (Codex, Claude Code oder andere) und vom Modell.

## Projekt

Mietvertrag per Anfrage auf den aktuellen Mieter anpassen (Vorlage .docx, Platzhalter, Aenderungsbericht).

- Code: `src/projekt/`
- Tests: `tests/` (pytest)
- Python 3.12, keine Laufzeit-Abhaengigkeiten
- Datenklasse: oeffentlich-tauglich

## Fachregeln

- Nur Standardbibliothek; keine Netzwerkzugriffe ausser dem lokalen Webserver auf 127.0.0.1 (nur `gui.py` und `webserver.py`) und dem Google-Zugriff der App (nur `googlehttp.py`, von einem Menschen gebaut und gemergt); kein Subprozess, keine echten Personendaten, in Tests nur erfundene Daten. Die Module `googleauth.py` und `gdrive.py` sind reine Logik ohne Netzwerk (kein `urllib.request`, kein `http`).
- Der Vertragstext bleibt fest; nur die Felder aus `projekt.felder` sind veraenderlich (Platzhalter `{{feldname}}` in der .docx-Vorlage). Das Uebergabeprotokoll hat eigene Felder in `projekt.protokoll`.
- Stammdaten, Einstellungen, Vorlagen und Ausgaben liegen lokal ausserhalb des Repos; Google Drive nur als synchronisierter Ordner (Google Drive fuer Desktop). PDFs entstehen durch ein Google-Apps-Script im Drive des Betreibers (siehe `docs/apps-script-pdf.md`), nicht im Programm.
- Betraege in CHF mit Apostroph-Tausendern und zwei Nachkommastellen, Daten als `DD.MM.YYYY`.
- Fehler in den Modulen immer als `ValueError` mit deutschem Klartext, der den Feldnamen nennt.
- Das Programm sendet nie E-Mails und schreibt nie ueber eine vorhandene Ausgabedatei; ein Mensch prueft jeden neuen Vertrag.
- Aus anderen Modulen des Projekts nur oeffentliche Namen importieren (ohne fuehrenden
  Unterstrich). Fehlt etwas, die Funktion im eigenen Modul oeffentlich machen, wenn das Issue
  dieses Modul zustaendig macht, sonst die Luecke im Pull-Request-Text nennen.
- Jede oeffentliche Funktion hat Typangaben und einen Docstring.

## Modulvertrag (bei mehreren Aufgaben ausfuellen)

Wenn mehrere Issues parallel laufen sollen, legt diese Tabelle vorab fest, welches Modul welche
Namen mit welcher Signatur bereitstellt. Abhaengige Module nutzen nur diese Namen. Loeschen, wenn
das Projekt nur aus einer Aufgabe besteht.

| Modul | Funktionen | Hinweis |
|---|---|---|
| `felder.py` | `FELDER`, `normalisiere(daten: dict) -> dict[str, str]` | `ValueError` bei ungueltigen Werten, unbekannten Feldern oder Nicht-dict |
| `docx_fuellen.py` | `platzhalter(docx: bytes) -> list[str]`, `fuelle(docx: bytes, werte: dict[str, str]) -> bytes` | `ValueError` bei ungueltigem docx oder Nicht-`str`-Werten |
| `anfrage.py` | `aenderungen_aus_text(text: str) -> dict[str, str]` | Zeilen `Feld: Wert`; `ValueError` mit Feldnamen |
| `bericht.py` | `bericht(alt: dict, neu: dict) -> str` | `keine Aenderungen` ohne Unterschied; `ValueError` bei fremden Schluesseln |
| `cli.py` | `main(argv: list[str] \| None = None) -> int` | `--vorlage`, `--daten`, `--anfrage`, `--ausgabe`, `--selbsttest`; Rueckgabe 0, 1 oder 2 |
| `gui.py` | `antwort`, `starte`, `main` | GUI v1, nur 127.0.0.1 |
| `objekte.py` | `normalisiere_objekt`, `objekt_als_felder`, `setze_objekt`, `entferne_objekt`, `lade_objekte`, `speichere_objekte` | `ValueError` mit Feldname |
| `einstellungen.py` | `EINSTELLUNGEN_FELDER`, `DRIVE_STANDARD`, `normalisiere_einstellungen`, `lade_einstellungen`, `speichere_einstellungen`, `einstellungen_pfad`, `ordner`, `pdf_ordner` | atomar schreiben |
| `ablage.py` | `liste_vorlagen`, `lese_vorlage`, `schreibe_ausgabe` | nie ueberschreiben |
| `protokoll.py` | `PROTOKOLL_FELDER`, `normalisiere_protokoll` | `ValueError` mit Feldname |
| `auftraege.py` | `FORMATE`, `slug`, `erstelle_vertrag`, `erstelle_protokoll` | Logik ohne HTTP; PDF nur als Auftrag im Drive-Ordner |
| `seiten.py` | `TABS`, `rahmen`, `formular_mietvertrag`, `formular_protokoll`, `formular_settings`, `ergebnis` | nur HTML, maskiert |
| `webapp.py` | `antwort(methode, pfad, kopf, koerper, kontext)` | ohne Socket |
| `webserver.py` | `starte`, `main` | nur 127.0.0.1 |
| `pfade.py` | `standard_lokal`, `erkenne_drive`, `drive_ordner`, `lokaler_ordner`, `einstellungen_aus_ordnern`, `lege_ordner_an` | GUI v3: zwei Ordner, Rest abgeleitet |
| `auswahl.py` | `AUSWAHL_FELDER`, `auswahl_pfad`, `lade_auswahl`, `speichere_auswahl` | letzte Auswahl, atomar |
| `objekttabelle.py` | `SPALTEN`, `neue_id`, `zeilen_aus_formular`, `objekte_aus_zeilen` | id automatisch, deutsche Fehler |
| `vorauswahl.py` | `vorauswahl`, `merke` | Standardwerte der Formulare |
| `seiten_einfach.py` | `TABS_EINFACH`, `rahmen_einfach`, `formular_ordner`, `formular_objekttabelle`, `formular_vertrag`, `formular_uebergabe` | nur HTML, maskiert |
| `webapp_einfach.py` | `antwort(methode, pfad, kopf, koerper, kontext)` | ohne Socket; Nachfolger von `webapp.py` |
| `googleauth.py` | `SCOPE`, `lade_client`, `neues_pkce`, `anmelde_url`, `code_aus_redirect`, `token_anfrage_code`, `token_anfrage_refresh`, `token_aus_antwort`, `token_gueltig`, `client_pfad`, `lade_client_datei`, `token_pfad`, `lade_token`, `speichere_token` | Google-OAuth (Loopback, PKCE) ohne Netzwerk; Client-Datei `google-client.json` und Token `google-token.json` nur unter `~/.mieterverwaltung` |
| `gdrive.py` | `GOOGLE_DOC`, `WORD`, `STICHWORTE`, `passt`, `liste_anfrage`, `auswerte_liste`, `abruf_anfrage` | Drive-API-Anfragen und -Antworten ohne Netzwerk |
| `googlehttp.py` | Transport, Anmeldung, Abruf | Mensch-gemergt (Netzwerk); spaeter, siehe `docs/google-einrichtung.md` |

## Arbeitsablauf

1. Aufgabe aus dem Issue lesen. Unklarheit nicht raten: Annahme im Pull-Request-Text nennen.
   Weicht deine Umsetzung von einer Acceptance Criterion des Issues ab (oder laesst du eine aus,
   oder gewinnt eine Regel aus dieser Datei gegen das Issue), schreibe im Pull-Request-Text eine
   eigene Zeile `ABWEICHUNG: <was und warum>`. Ein solcher Pull Request wird nicht automatisch
   gemergt, sondern von einem Menschen geprueft.
2. Nur `src/` und `tests/` aendern. README nur, wenn die Aufgabe es verlangt.
3. Fuer jede neue Funktion Tests schreiben, inklusive Grenzfaelle aus dem Issue.
4. Vor dem Abschluss alle drei Pruefungen ausfuehren und gruen machen:
   - `ruff check .`
   - `ruff format --check .` (bei Bedarf vorher `ruff format .`)
   - `pytest`
5. Bleibt eine Pruefung nach drei Korrekturrunden rot: aufhoeren und den Fehler im
   Pull-Request-Text offen beschreiben, nicht Tests abschwaechen oder loeschen.

## Akzeptanztests und Widersprueche

- Akzeptanztests in `tests/akzeptanz/` definieren das fachliche Soll. Widerspricht einer davon einer
  Regel in dieser Datei oder dem Issue, **klaert ein Mensch den Widerspruch vor dem Bau** (Spec oder
  diese Datei per Pull Request anpassen). Das Label `agent` kommt erst danach.
- Stoesst der Agent trotzdem auf einen Widerspruch, baut er nach dem Akzeptanztest und meldet den
  Widerspruch im Pull-Request-Text mit `ABWEICHUNG: <was und warum>`. Diese Meldung wird nie
  weggelassen oder abgeschwaecht; der Pull Request braucht dann einen Menschen.

## Verboten

- Aenderungen an `.github/`, `AGENTS.md`, `pyproject.toml` oder `requirements-dev.txt`.
- Aenderungen an `tests/akzeptanz/`: diese Akzeptanztests gibt ein Mensch vorab vor. Die
  Implementierung muss sie erfuellen; schlagen sie fehl, die Implementierung anpassen oder nach
  drei Runden offen melden.
- Tests loeschen, ueberspringen oder Erwartungen aufweichen, damit sie gruen werden.
- Neue Abhaengigkeiten, Netzwerkzugriffe, Secrets oder Zugangsdaten im Code.
- Personen- oder Kundendaten, ausser die Datenklasse oben erlaubt sie ausdruecklich.
