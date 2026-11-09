"""Tests fuer den lokalen HTTP-Server in projekt.webserver."""

from __future__ import annotations

import http.client
import threading
from pathlib import Path

import pytest

import projekt.webserver as webserver
from projekt.googlehttp import GoogleQuelle
from projekt.webserver import main, starte

LIMIT = 1024 * 1024


@pytest.fixture
def server(tmp_path):
    datei = tmp_path / "einstellungen.json"
    laufend = starte({"einstellungen_datei": datei}, port=0)
    thread = threading.Thread(target=laufend.serve_forever, daemon=True)
    thread.start()
    try:
        yield laufend
    finally:
        laufend.shutdown()
        laufend.server_close()
        thread.join(timeout=5)


def anfrage(server, methode, pfad, koerper=None, kopf=None):
    verbindung = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        verbindung.request(methode, pfad, body=koerper, headers=kopf or {})
        antwort = verbindung.getresponse()
        return antwort.status, antwort.getheaders(), antwort.read()
    finally:
        verbindung.close()


def kopfwert(kopf, name):
    werte = [wert for schluessel, wert in kopf if schluessel.lower() == name.lower()]
    assert len(werte) == 1
    return werte[0]


def test_starte_bindet_nur_loopback_und_prueft_port(tmp_path):
    for host in ("0.0.0.0", "", "::1", "192.168.1.5", "example.org", None):
        with pytest.raises(ValueError, match="host"):
            starte({"einstellungen_datei": tmp_path / "e.json"}, host=host, port=0)

    for port in (-1, 65536, True, "8765", 1.5):
        with pytest.raises(ValueError, match="port"):
            starte({"einstellungen_datei": tmp_path / "e.json"}, port=port)

    laufend = starte({"einstellungen_datei": tmp_path / "e.json"}, host="localhost", port=0)
    try:
        assert laufend.server_address[0] == "127.0.0.1"
    finally:
        laufend.server_close()


def test_get_und_post_sowie_content_length(server):
    status, kopf, koerper = anfrage(server, "GET", "/settings")
    assert status == 200
    assert b"<form" in koerper
    assert kopfwert(kopf, "Content-Length") == str(len(koerper))
    assert kopfwert(kopf, "Content-Type") == "text/html; charset=utf-8"

    status, kopf, koerper = anfrage(
        server,
        "POST",
        "/settings",
        b"drive_ordner=/tmp/drive&lokaler_ordner=/tmp/lokal",
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200
    assert b"<form" in koerper
    assert kopfwert(kopf, "Content-Length") == str(len(koerper))


def test_handler_gibt_anfrage_an_antwort_weiter(server, monkeypatch):
    gesehen = {}

    def erfassen(methode, pfad, kopf, koerper, kontext):
        gesehen.update(
            methode=methode,
            pfad=pfad,
            kopf={name.lower(): wert for name, wert in kopf.items()},
            koerper=koerper,
            kontext=kontext,
        )
        return 201, {"Content-Type": "text/plain", "Content-Length": "999"}, b"neu"

    monkeypatch.setattr(webserver, "antwort", erfassen)
    status, kopf, koerper = anfrage(
        server,
        "POST",
        "/settings?quelle=test",
        b"a=1",
        {"Content-Type": "text/plain", "X-Test": "ja"},
    )

    assert status == 201
    assert koerper == b"neu"
    assert kopfwert(kopf, "Content-Length") == "3"
    assert kopfwert(kopf, "Content-Type") == "text/plain"
    assert gesehen["methode"] == "POST"
    assert gesehen["pfad"] == "/settings?quelle=test"
    assert gesehen["koerper"] == b"a=1"
    assert gesehen["kopf"]["x-test"] == "ja"
    assert "einstellungen_datei" in gesehen["kontext"]


def test_methoden_ausser_get_und_post_sind_405(server):
    for methode in ("HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "BREW"):
        status, kopf, koerper = anfrage(server, methode, "/settings")
        assert status == 405
        assert kopfwert(kopf, "Allow") == "GET, POST"
        if methode == "HEAD":
            assert koerper == b""
        else:
            assert b"Methode nicht erlaubt" in koerper


def test_koerper_wird_hoechstens_ein_mib_plus_ein_byte_gelesen(server, monkeypatch):
    aufrufe = []

    def erfassen(methode, pfad, kopf, koerper, kontext):
        aufrufe.append(len(koerper))
        return 200, {"Content-Type": "text/plain"}, b"ok"

    monkeypatch.setattr(webserver, "antwort", erfassen)
    for laenge in (LIMIT, LIMIT + 1, LIMIT + 2):
        status, _, koerper = anfrage(server, "POST", "/settings", b"x" * laenge)
        assert status == 200
        assert koerper == b"ok"
    assert aufrufe == [LIMIT, LIMIT + 1, LIMIT + 1]


def test_zu_grosser_koerper_liefert_413(server):
    status, _, koerper = anfrage(
        server,
        "POST",
        "/settings",
        b"x" * (LIMIT + 1),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 413
    assert "zu gross" in koerper.decode("utf-8")


def test_ungueltige_content_length_liefert_400(server):
    status, _, koerper = anfrage(server, "POST", "/settings", None, {"Content-Length": "abc"})
    assert status == 400
    assert b"Anfrage ungueltig" in koerper


@pytest.mark.parametrize("wert", ["", "-1", "1.0", "1_0", "+5"])
def test_content_length_muss_aus_ziffern_bestehen(server, wert):
    status, _, koerper = anfrage(server, "POST", "/settings", None, {"Content-Length": wert})
    assert status == 400
    assert b"Anfrage ungueltig" in koerper


def test_keine_logausgabe(server, capfd):
    assert anfrage(server, "GET", "/settings")[0] == 200
    assert "GET /settings" not in capfd.readouterr().err


def test_main_selbsttest_ohne_socket(monkeypatch, capsys):
    def kein_server(*args, **kwargs):
        raise AssertionError("Selbsttest darf keinen Server starten")

    monkeypatch.setattr(webserver, "starte", kein_server)
    assert main(["--selbsttest"]) == 0
    assert "Selbsttest OK" in capsys.readouterr().out


def test_main_selbsttest_fehler_ist_rueckgabe_1(monkeypatch, capsys):
    monkeypatch.setattr(webserver, "antwort", lambda *args: (500, {}, b""))
    assert main(["--selbsttest"]) == 1
    assert "Selbsttest fehlgeschlagen" in capsys.readouterr().err


def test_main_selbsttest_nutzt_nur_temp_einstellungen(monkeypatch, tmp_path, capsys):
    gesehen = {}

    def erfassen(methode, pfad, kopf, koerper, kontext):
        gesehen.update(kontext)
        return 200, {}, b"<form>"

    monkeypatch.setattr(webserver, "antwort", erfassen)
    fremd = tmp_path / "fremd.json"
    assert main(["--selbsttest", "--einstellungen", str(fremd)]) == 0
    datei = gesehen["einstellungen_datei"]
    assert isinstance(datei, Path)
    assert datei.parent != tmp_path
    assert datei.name == "einstellungen.json"
    assert not fremd.exists()
    assert "Selbsttest OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [["--unbekannt"], ["--port", "abc"], ["--port", "-1"], ["--port", "65536"]],
)
def test_main_aufruffehler_sind_rueckgabe_2(argv, capsys):
    assert main(argv) == 2
    assert "Fehler" in capsys.readouterr().err


def test_main_startet_mit_einstellungen_und_beendet_bei_strg_c(monkeypatch, tmp_path, capsys):
    aufruf = {}
    geschlossen = []

    class FakeServer:
        server_address = ("127.0.0.1", 4321)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            geschlossen.append(True)

    def fake_starte(kontext, host="127.0.0.1", port=8765):
        aufruf.update(kontext=kontext, host=host, port=port)
        return FakeServer()

    monkeypatch.setattr(webserver, "starte", fake_starte)
    einstellungen = tmp_path / "einstellungen.json"
    assert main(["--port", "0", "--einstellungen", str(einstellungen)]) == 0
    assert isinstance(aufruf["kontext"].pop("google"), GoogleQuelle)
    assert aufruf == {
        "kontext": {"einstellungen_datei": einstellungen},
        "host": "127.0.0.1",
        "port": 0,
    }
    assert geschlossen == [True]
    assert "http://127.0.0.1:4321/" in capsys.readouterr().out


def test_main_gibt_host_explizit_an(monkeypatch, tmp_path):
    aufruf = {}

    class FakeServer:
        server_address = ("127.0.0.1", 4321)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    def fake_starte(kontext, host, port):
        aufruf.update(kontext=kontext, host=host, port=port)
        return FakeServer()

    monkeypatch.setattr(webserver, "starte", fake_starte)
    assert main(["--port", "0", "--einstellungen", str(tmp_path / "e.json")]) == 0
    assert isinstance(aufruf["kontext"].pop("google"), GoogleQuelle)
    assert aufruf == {
        "kontext": {"einstellungen_datei": tmp_path / "e.json"},
        "host": "127.0.0.1",
        "port": 0,
    }


def test_main_startfehler_ist_rueckgabe_1(monkeypatch, capsys):
    def fehlschlag(*args, **kwargs):
        raise OSError("Port belegt")

    monkeypatch.setattr(webserver, "starte", fehlschlag)
    assert main([]) == 1
    assert "Server konnte nicht gestartet werden" in capsys.readouterr().err


# Betreiber-PR #47
