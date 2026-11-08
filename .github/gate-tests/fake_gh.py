"""Fake-gh fuer die Gate-Tests: liefert Fixtures aus $FIXDIR und protokolliert Schreibaufrufe.

Fehler lassen sich per Marker-Datei erzwingen: fail_dispatch, fail_issue, fail_delete, fail_graphql,
fail_ref_403 (Branch-Abfrage mit HTTP 403), ref_404 (Branch existiert nicht mehr), akzeptanz_404.
"""

import json
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

fx = os.environ["FIXDIR"]
a = sys.argv[1:]


def load(n):
    return open(os.path.join(fx, n), encoding="utf-8").read()


def hat(n):
    return os.path.exists(os.path.join(fx, n))


def wer():
    """Welches Token hat der Aufruf? (Marker statt echter Werte)"""
    t = os.environ.get("GH_TOKEN", "")
    return "app" if t == "APP-TOKEN-XYZ" else "default" if t == "DEFAULT-TOKEN-ABC" else "anderes"


def log(t):
    open(os.path.join(fx, "writes.log"), "a").write(t + "\n")


def geschrieben(praefix):
    p = os.path.join(fx, "writes.log")
    return os.path.exists(p) and any(z.startswith(praefix) for z in open(p).read().splitlines())


def zaehle():
    """Zaehlt Abfragen des PR nach dem Auto-Merge-Aufruf (simuliert verzoegerten Merge)."""
    p = os.path.join(fx, "zaehler")
    n = int(open(p).read()) if os.path.exists(p) else 0
    open(p, "w").write(str(n + 1))
    return n


def zaehle_main():
    p = os.path.join(fx, "mruns_zaehler")
    n = int(open(p).read()) if os.path.exists(p) else 0
    open(p, "w").write(str(n + 1))
    return n


def fehler(text, code=1):
    print(text, file=sys.stderr)
    sys.exit(code)


if a[0] == "api":
    path = [x for x in a[1:] if x.startswith("repos/") or x == "graphql"][0]
    roh = path.split("?")[0]
    query = parse_qs(urlparse(path).query)
    methode = a[a.index("-X") + 1] if "-X" in a else "GET"
    if methode in ("POST", "PATCH") and "check-runs" in path:
        concl = [x.split("=", 1)[1] for x in a if x.startswith("conclusion=")][0]
        log(("check-patch " if methode == "PATCH" else "check ") + concl)
        log("tok check " + wer())
    elif methode == "DELETE" and "/git/refs/heads/" in path:
        if hat("fail_delete"):
            fehler("HTTP 403: Resource not accessible by integration", 1)
        log("branch-delete " + path.split("/git/refs/heads/")[1])
        log("tok branch-delete " + wer())
    elif path == "graphql":
        if hat("fail_graphql"):
            fehler("HTTP 403", 1)
        print(load("closing.json"))
    elif re.search(r"/issues/[0-9]+/comments$", roh):
        if hat("fail_comments"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print('[{"body": "<!-- gate-retry -->"}]' if hat("retry_marker") else "[]")
    elif re.search(r"/issues/[0-9]+$", path):
        print(load("issue.json"))
    elif roh.endswith("/reviews"):
        if hat("reviews_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print(load("reviews.json") if hat("reviews.json") else "[]")
    elif roh.endswith("/actions/runs") and "head_sha" in query:
        if hat("ciruns_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print(load("ciruns.json") if hat("ciruns.json") else '{"workflow_runs": []}')
    elif "/contents/backlog/" in roh:
        # Auftragsdaten: Version auf dem Standard-Branch (ref=main) oder im PR-HEAD (sonstiger ref)
        if hat("auftrag_404"):
            print('{"message": "Not Found"}')
            sys.exit(1)
        import base64

        text = load(
            "auftrag_basis.txt" if query.get("ref", [""])[0] == "main" else "auftrag_head.txt"
        )
        print(
            json.dumps({"encoding": "base64", "content": base64.b64encode(text.encode()).decode()})
        )
    elif "/contents/monitor/qualitaet_bekannt.json" in roh:
        if hat("bekannt_404") or not hat("bekannt_basis.txt"):
            print('{"message": "Not Found"}')
            sys.exit(1)
        import base64

        text = load(
            "bekannt_basis.txt" if query.get("ref", [""])[0] == "main" else "bekannt_head.txt"
        )
        print(
            json.dumps({"encoding": "base64", "content": base64.b64encode(text.encode()).decode()})
        )
    elif roh.endswith("/commits") and "path" in query:
        if hat("commits_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print(load("commits_auftrag.json") if hat("commits_auftrag.json") else "[]")
    elif "/git/ref/heads/" in path:
        if hat("ref_404"):
            print('{"message": "Not Found"}')
            fehler("gh: Not Found (HTTP 404)", 1)
        if hat("fail_ref_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print(load("ref.json"))
    elif roh.endswith("/src/Resources/config/services.xml"):
        if hat("services_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        if not hat("services.txt"):
            print('{"message": "Not Found"}')
            sys.exit(1)
        import base64

        print(
            json.dumps(
                {
                    "encoding": "base64",
                    "content": base64.b64encode(load("services.txt").encode()).decode(),
                }
            )
        )
    elif "/contents/shop/app/custom/plugins/" in path:
        if hat("pakz_404"):
            print('{"message": "Not Found"}')
            sys.exit(1)
        print(load("plugin_akz.json"))
    elif "/contents/tests/akzeptanz" in path:
        if hat("akzeptanz_404"):
            print('{"message": "Not Found"}')
            sys.exit(1)
        print(load("akzeptanz.json"))
    elif "/contents/tests/browser" in path:
        if hat("browser_404"):
            print('{"message": "Not Found"}')
            sys.exit(1)
        print(load("browser.json"))
    elif "/contents/.github/workflows/ci.yml" in path:
        import base64

        text = "run: php tools/storefront/twig_lint.php shop/app/custom/plugins" + chr(10)
        text += "run: php tools/storefront/scss_check.php shop/app/custom/plugins" + chr(10)
        if hat("ci_ohne"):
            text = "run: pytest" + chr(10)
        print(
            json.dumps({"encoding": "base64", "content": base64.b64encode(text.encode()).decode()})
        )
    elif "/contents/.github/workflows/" in path and not hat("alle_basis"):
        if "monitor-secret.yml" in path or hat("basis_secret"):
            import base64

            text = "env: X=${{ secrets.BEKANNT }}" + chr(10)
            print(
                json.dumps(
                    {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}
                )
            )
        else:
            print('{"message": "Not Found"}')
            sys.exit(1)
    elif "/actions/workflows/monitor.yml/runs" in roh:
        if hat("monitor_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print(load("monitor.json"))
    elif "/actions/workflows/deploy-staging.yml/runs" in roh:
        if hat("deploy_403"):
            fehler("gh: Forbidden (HTTP 403)", 1)
        print(load("deploys.json"))
    elif "/actions/workflows/" in path and roh.endswith("/runs"):
        sha = query.get("head_sha", [""])[0]
        if sha == json.loads(load("main.json"))["sha"]:
            nach = hat("mainruns_nach.json") and geschrieben("auto")
            datei = "mainruns_nach.json" if nach else "mainruns.json"
            if nach and hat("mainruns_spaeter.json"):
                z = zaehle_main()
                if z >= int(load("mainruns_spaeter_ab")):
                    datei = "mainruns_spaeter.json"
            print(load(datei))
        else:
            print(load("prruns.json"))
    elif "/actions/runs/" in path:
        # Lauf-Abfrage: je nach angefragter ID Standard-Branch-Lauf (main_run.json) oder PR-Lauf
        if roh.endswith("/runs/main") and hat("main_run.json"):
            print(load("main_run.json"))
        else:
            print(load("run.json"))
    elif "/check-runs" in path:
        print(load("checks.json"))
    elif roh.endswith("/files"):
        d = json.loads(load("files.json"))
        for i in range(0, max(len(d), 1), 30):
            print(json.dumps(d[i : i + 30]))
    elif roh.endswith("/pulls") and "/commits/" in roh:
        print(load("commit_pulls.json"))
    elif roh.endswith("/pulls") and hat("pulls.json"):
        print(load("pulls.json"))
    elif "/pulls/" in path:
        if geschrieben("auto") and (hat("pr_nach.json") or hat("pr_wartet.json")):
            k = int(load("merge_nach_abfragen")) if hat("merge_nach_abfragen") else 0
            z = zaehle()
            if z < k or not hat("pr_nach.json"):
                print(load("pr_wartet.json" if hat("pr_wartet.json") else "pr.json"))
            else:
                print(load("pr_nach.json"))
        else:
            print(load("pr.json"))
    elif roh.count("/") == 4 and "/commits/" in roh:
        print(load("main.json"))
    elif roh.count("/") == 2:
        print(load("repo.json"))
    else:
        fehler(f"unbekannt {a}", 2)
elif a[:2] == ["pr", "ready"]:
    log("ready")
    log("tok ready " + wer())
elif a[:2] == ["pr", "merge"] and "--disable-auto" in a:
    log("disable-auto")
    log("tok merge-disable " + wer())
elif a[:2] == ["pr", "merge"] and "--auto" in a:
    if hat("fail_merge"):
        fehler("HTTP 403: Resource not accessible by integration", 1)
    log("auto " + a[a.index("--match-head-commit") + 1])
    log("tok merge-auto " + wer())
elif a[:2] == ["label", "create"]:
    log("label-create")
elif a[:2] == ["issue", "edit"]:
    log("issue-edit " + " ".join(x for x in a[a.index("--repo") + 2 :]))
    log("tok issue-edit " + wer())
elif a[:2] == ["issue", "comment"]:
    if hat("fail_comment"):
        fehler("HTTP 403: Resource not accessible by integration", 1)
    log("issue-comment")
elif a[:2] == ["pr", "close"]:
    log("pr-close")
elif a[:2] == ["workflow", "run"]:
    if hat("fail_dispatch"):
        fehler("HTTP 403: Resource not accessible by integration", 1)
    log(
        ("neu-dispatch " if a[2] == "agent-neuuebergabe.yml" else "ci-dispatch ")
        + a[a.index("--ref") + 1]
    )
    log("tok ci-dispatch " + wer())
elif a[:2] == ["issue", "close"]:
    if hat("fail_issue"):
        fehler("HTTP 403: Resource not accessible by integration", 1)
    log("issue-close " + a[2])
    log("tok issue-close " + wer())
else:
    fehler(f"unbekannter Aufruf {a}", 2)
