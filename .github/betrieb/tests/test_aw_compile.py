"""aw-compile.yml: Pins nur in gh-aw-release.env, Digest-Pruefung vor Ausfuehrung, Rechte, Actions.

`pruefe()` liefert die Verstoesse; die Negativfaelle mutieren die echten Texte und muessen je
genau diesen Verstoss melden."""

import json
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[3]
WORKFLOW = (WURZEL / ".github" / "workflows" / "aw-compile.yml").read_text(encoding="utf-8")
ENV = (WURZEL / ".github" / "aw" / "gh-aw-release.env").read_text(encoding="utf-8")
ACTIONS_LOCK = json.loads(
    (WURZEL / ".github" / "aw" / "actions-lock.json").read_text(encoding="utf-8")
)


def pins(env: str) -> dict[str, str]:
    return dict(zeile.split("=", 1) for zeile in env.splitlines() if "=" in zeile)


def pruefe(text: str, env: str, lock: dict) -> list[str]:
    fehler = []
    p = pins(env)
    if not re.fullmatch(r"v\d+\.\d+\.\d+", p.get("GH_AW_VERSION", "")):
        fehler.append("Version")
    if not re.fullmatch(r"[0-9a-f]{64}", p.get("GH_AW_SHA256", "")):
        fehler.append("Digest")
    if not re.fullmatch(r"[0-9a-f]{40}", p.get("GH_AW_ACTION_TAG", "")):
        fehler.append("Action-Tag")
    elif not any(e.get("sha") == p["GH_AW_ACTION_TAG"] for e in lock.get("entries", {}).values()):
        fehler.append("Action-Tag nicht in actions-lock.json")
    if re.search(r"\b[0-9a-f]{64}\b", text) or "v0." in text:
        fehler.append("Pin im Workflow fest eingebaut")
    lesen = text.find("gh-aw-release.env")
    pruef = text.find("sha256sum -c")
    aufruf = text.find('"$RUNNER_TEMP/gh-aw" compile')
    if lesen < 0:
        fehler.append("Pins werden nicht gelesen")
    if pruef < 0:
        fehler.append("Pruefschritt fehlt")
    elif aufruf < 0 or pruef > aufruf:
        fehler.append("Pruefschritt nach dem Aufruf")
    rechte = re.findall(r"^\s*[a-z-]+:\s*(read|write|none)\s*$", text, re.M)
    if "write" in rechte or "permissions: write-all" in text:
        fehler.append("Schreibrecht")
    if re.search(r"^permissions:\s*\n\s+contents: read\s*\n", text, re.M) is None:
        fehler.append("contents: read fehlt")
    if re.search(r"secrets\.", text):
        fehler.append("secrets")
    if "pull_request_target" in text:
        fehler.append("pull_request_target")
    for m in re.finditer(r"^\s*-?\s*uses:\s*(\S+)", text, re.M):
        if not re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", m.group(1)):
            fehler.append("ungepinntes uses: " + m.group(1))
    return fehler


def test_echte_dateien_sind_sauber() -> None:
    assert pruefe(WORKFLOW, ENV, ACTIONS_LOCK) == []


def test_drift_macht_den_lauf_rot() -> None:
    assert "git status --porcelain -- .github" in WORKFLOW and "exit 1" in WORKFLOW


def test_env_datei_hat_genau_drei_pins() -> None:
    assert sorted(pins(ENV)) == ["GH_AW_ACTION_TAG", "GH_AW_SHA256", "GH_AW_VERSION"]


def test_negativ_digest_kein_hex() -> None:
    assert pruefe(WORKFLOW, ENV.replace(pins(ENV)["GH_AW_SHA256"], "0" * 63), ACTIONS_LOCK) == [
        "Digest"
    ]


def test_negativ_version_ungueltig() -> None:
    assert pruefe(WORKFLOW, ENV.replace("v0.92.0", "latest"), ACTIONS_LOCK) == ["Version"]


def test_negativ_action_tag_nicht_im_lock() -> None:
    tag = pins(ENV)["GH_AW_ACTION_TAG"]
    assert pruefe(WORKFLOW, ENV.replace(tag, "1" * 40), ACTIONS_LOCK) == [
        "Action-Tag nicht in actions-lock.json"
    ]


def test_negativ_pin_im_workflow_eingebaut() -> None:
    mutiert = WORKFLOW.replace(
        "# gh-aw compile", "# " + pins(ENV)["GH_AW_SHA256"] + "\n# gh-aw compile", 1
    )
    assert "Pin im Workflow fest eingebaut" in pruefe(mutiert, ENV, ACTIONS_LOCK)


def test_negativ_pins_werden_nicht_gelesen() -> None:
    assert "Pins werden nicht gelesen" in pruefe(
        WORKFLOW.replace("gh-aw-release.env", "x.env"), ENV, ACTIONS_LOCK
    )


def test_negativ_pruefschritt_fehlt() -> None:
    assert "Pruefschritt fehlt" in pruefe(
        WORKFLOW.replace("sha256sum -c -", "true"), ENV, ACTIONS_LOCK
    )


def test_negativ_pruefschritt_nach_dem_aufruf() -> None:
    zeile = '          echo "${GH_AW_SHA256}  $RUNNER_TEMP/gh-aw" | sha256sum -c -\n'
    assert zeile in WORKFLOW
    mutiert = WORKFLOW.replace(zeile, "") + zeile
    assert "Pruefschritt nach dem Aufruf" in pruefe(mutiert, ENV, ACTIONS_LOCK)


def test_negativ_schreibrecht() -> None:
    assert "Schreibrecht" in pruefe(
        WORKFLOW.replace("contents: read", "contents: write", 1), ENV, ACTIONS_LOCK
    )


def test_negativ_secret() -> None:
    mutiert = WORKFLOW.replace("${{ github.token }}", "${{ secrets.X }}")
    assert "secrets" in pruefe(mutiert, ENV, ACTIONS_LOCK)


def test_negativ_pull_request_target() -> None:
    mutiert = WORKFLOW.replace("  pull_request:\n", "  pull_request_target:\n", 1)
    assert "pull_request_target" in pruefe(mutiert, ENV, ACTIONS_LOCK)


def test_negativ_ungepinntes_uses() -> None:
    mutiert = re.sub(r"(actions/checkout@)[0-9a-f]{40}", r"\1v7", WORKFLOW, count=1)
    assert any(f.startswith("ungepinntes uses") for f in pruefe(mutiert, ENV, ACTIONS_LOCK))
