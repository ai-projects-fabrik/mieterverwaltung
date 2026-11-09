# Vorlagen direkt aus Google Docs / Drive

Die App listet Vertrags- und Protokollvorlagen direkt ueber die Google Drive API: **eigene und mit dir
geteilte** Dateien, **Google Docs und Word (.docx)**. Beim Erstellen holt sie die gewaehlte Vorlage in den
Arbeitsspeicher (Google Docs werden dabei als .docx exportiert), fuellt sie und legt nur das fertige
Ergebnis wie bisher in den Ausgabeordner. Es wird nichts heruntergeladen, kopiert oder dauerhaft lokal
gespeichert. Die Festplatte (Ordner `Vorlagen`) bleibt eine eigene, zweite Quelle.

Nur Python-Standardbibliothek, nichts zu installieren. Die App darf Drive **nur lesen**
(`drive.readonly`); Vorlagen in Google Docs aenderst du weiterhin in Google Docs selbst.

## Einmalige Einrichtung (ca. 10 Minuten, nur beim ersten Mal)

Google verlangt, dass du der App den Zugriff einmal freigibst. Dafuer legst du im Google-Konto einen
Zugang an. Alle Schritte mit dem Konto, dem die Dateien zugaenglich sind (swisssellerch@gmail.com).

1. **Projekt anlegen** (einmalig): <https://console.cloud.google.com/projectcreate>, Name `Mietverwaltung`,
   Erstellen.
2. **Drive API einschalten** (einmalig): <https://console.cloud.google.com/apis/library/drive.googleapis.com>
   mit diesem Projekt, Button *Aktivieren*.
3. **Zustimmungsbildschirm** (einmalig): *APIs und Dienste > OAuth-Zustimmungsbildschirm* (bzw. *Google Auth
   Platform*). Nutzertyp *Extern*, App-Name `Mietverwaltung`, deine E-Mail als Support- und Kontaktadresse,
   speichern. Unter *Zielgruppe* den Status auf **In Produktion** setzen. (Im Status *Test* laeuft die
   Anmeldung nach 7 Tagen ab. Fuer eine nur von dir genutzte App ist keine Google-Pruefung noetig.)
4. **Zugangsdaten** (einmalig): *Anmeldedaten > Anmeldedaten erstellen > OAuth-Client-ID*, Anwendungstyp
   **Desktop-App**, Name `Mietverwaltung`, Erstellen, **JSON herunterladen**.
5. Die Datei speichern als `C:\Users\NEO\.mieterverwaltung\google_client.json` (Ordner anlegen, falls er
   fehlt). Sie liegt nie im Repo.
6. **Einmal anmelden:** in der App unter *Einstellungen* auf *Mit Google verbinden*. Der Browser oeffnet
   sich. Konto waehlen. Erscheint *Google hat diese App nicht ueberprueft*, auf *Erweitert > Weiter zu
   Mietverwaltung* klicken (die App ist deine eigene). Zugriff *Dateien in Google Drive ansehen* erlauben.
   Die Seite meldet *Fertig*; der Browser-Tab kann zu.

Danach laeuft alles ohne weitere Schritte; das Token liegt in `~/.mieterverwaltung/google_token.json` und
erneuert sich selbst. Zugriff widerrufen: <https://myaccount.google.com/permissions> (App entfernen).

## Welche Dateien erscheinen

Standard: der Name enthaelt **Vertrag** oder **Protokoll** (ohne Gross-/Kleinschreibung, auch als Teilwort:
"Kaufvertrag", "August26-Uebergabeprotokoll"). Die Stichworte stehen als Konstante `STICHWORTE` in
`gdrive.py`. Hinweis: Drive-eigene Namenssuche findet nur Wortanfaenge, deshalb listet die App alle Google
Docs und Word-Dateien und filtert selbst.

## Aufbau (Fabrik und Handarbeit)

| Teil | Wer | Inhalt |
|---|---|---|
| `googleauth.py` | Agent (Gate) | OAuth-Logik ohne Netzwerk, Token-Datei |
| `gdrive.py` | Agent (Gate) | Drive-Anfragen, Antworten, Auswahl |
| `googlehttp.py` | Mensch (Netzwerk, `urllib.request`, `http.server`) | Transport, Loopback-Anmeldung, Abruf, Test mit Fake-Transport |
| Einbindung | Mensch | Quelle `google` im Vorlagen-Dropdown (`google:<id>`), Knopf *Mit Google verbinden*, Abruf in `auftraege` |

**Datenschutz:** Fuer die Vorlage verarbeitet Google den Vertragstext ohnehin; die App sendet nie Mieterdaten
an Google (nur lesen). Das Repo enthaelt nie Zugangsdaten oder Token.
