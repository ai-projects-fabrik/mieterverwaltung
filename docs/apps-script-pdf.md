# PDF ueber Google Drive

Die Oberflaeche erzeugt kein PDF selbst. Bei Format `pdf` oder `docx+pdf` legt sie die fertige .docx in den
Ordner `MV-zu-pdf` in Google Drive fuer Desktop (Wurzel in den Settings, Standard `G:\My Drive`). Ein
Google-Apps-Script im Drive des Betreibers wandelt neue .docx alle 5 Minuten in PDF um:

| Ordner (unter der Drive-Wurzel) | Inhalt |
|---|---|
| `MV-zu-pdf` | Eingang: hier legt die App die .docx ab |
| `MV-pdf` | Ausgang: hier erscheinen die PDFs |
| `MV-erledigt` | umgewandelte .docx |

Das Script und seine Einrichtung liegen beim Betreiber (Anleitung der Leitstelle), nicht in diesem Repo.
**Datenschutz:** Fuer das PDF verarbeitet Google den kompletten Vertrag; das Repo enthaelt nie echte Daten.
