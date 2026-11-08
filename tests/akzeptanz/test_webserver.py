"""Akzeptanztest (spec-first) fuer projekt.webserver (Ziel `mv-webserver`)."""

import importlib.util
import io
import json
import threading
import urllib.error
import urllib.request
import zipfile
from urllib.parse import urlencode

import pytest

if importlib.util.find_spec("projekt.webserver") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.webserver import main, starte  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes():
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body><w:p><w:r>'
    xml += (
        '<w:t xml:space="preserve">Mieter {{mieter_name}}</w:t></w:r></w:p></w:body></w:document>'
    )
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return puffer.getvalue()


@pytest.fixture
def laufend(tmp_path):
    for name in ("vl", "al"):
        (tmp_path / name).mkdir()
    (tmp_path / "vl" / "vertrag.docx").write_bytes(docx_bytes())
    datei = tmp_path / "einstellungen.json"
    datei.write_text(
        json.dumps({"vorlagen_lokal": str(tmp_path / "vl"), "ausgabe_lokal": str(tmp_path / "al")}),
        encoding="utf-8",
    )
    server = starte({"einstellungen_datei": datei, "konverter": None}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    server.shutdown()
    server.server_close()


def anfrage(url, felder=None):
    daten = urlencode(felder).encode("utf-8") if felder is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=daten), timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as fehler:
        return fehler.code, fehler.read().decode("utf-8")


def test_server_bindet_nur_an_loopback(tmp_path):
    kontext = {"einstellungen_datei": tmp_path / "e.json", "konverter": None}
    for host in ("0.0.0.0", "", "192.168.1.5", "example.org"):
        with pytest.raises(ValueError):
            starte(kontext, host=host, port=0)
    server = starte(kontext, host="localhost", port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_seiten_ueber_http(laufend):
    url, _ = laufend
    status, text = anfrage(url + "/")
    assert status == 200
    assert "<form" in text
    assert 'value="lokal:vertrag.docx"' in text
    assert anfrage(url + "/settings")[0] == 200
    assert anfrage(url + "/gibt-es-nicht")[0] == 404


def test_vertrag_ueber_http(laufend):
    url, ordner = laufend
    status, text = anfrage(
        url + "/mietvertrag",
        {"vorlage": "lokal:vertrag.docx", "format": "docx", "ziel": "lokal", "mieter_name": "Anna"},
    )
    assert status == 200
    assert "vertrag-anna.docx" in text
    assert [p.name for p in (ordner / "al").iterdir()] == ["vertrag-anna.docx"]
    status, text = anfrage(
        url + "/mietvertrag", {"vorlage": "lokal:fehlt.docx", "mieter_name": "A"}
    )
    assert status == 400
    assert "vorlage" in text


def test_settings_ueber_http(laufend):
    url, ordner = laufend
    status, _ = anfrage(url + "/settings", {"ausgabe_lokal": str(ordner / "al")})
    assert status == 200
    gespeichert = json.loads((ordner / "einstellungen.json").read_text(encoding="utf-8"))
    assert gespeichert == {"ausgabe_lokal": str(ordner / "al")}


def test_aufruf_selbsttest_und_fehler(capsys):
    assert main(["--selbsttest"]) == 0
    assert "Selbsttest OK" in capsys.readouterr().out
    assert main(["--unbekannt"]) == 2
    assert main(["--port", "abc"]) == 2
    assert main(["--port", "70000"]) == 2
