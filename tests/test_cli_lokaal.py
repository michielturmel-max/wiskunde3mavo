import io
import json
import pathlib
import sys
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient

import main

c = TestClient(main.app)

GOED = {
    "titel": "Parabolen",
    "samenvatting": "Een U-vormige kromme.",
    "praktijk_voorbeeld": "De baan van een bal.",
    "ezelsbruggetje": "Omhoog, omlaag, omhoog.",
    "stappenplan": ["1. Tabel maken", "2. Punten tekenen", "3. Laagste punt zoeken"],
    "grafiek_formule": "x^2-4",
    "veelgemaakte_fout": "Negatieve x-waarden overslaan.",
    "oefensom": {
        "vraag": "Hoeveel nulpunten?",
        "opties": ["1", "2", "3"],
        "correct_index": 1,
        "uitleg": "Twee: x = 2 en x = -2.",
    },
}


def opencode_uitvoer(regels, returncode=0):
    return type(
        "Schijn",
        (),
        {
            "returncode": returncode,
            "stdout": "".join(json.dumps(r) + "\n" for r in regels),
            "stderr": "",
        },
    )()


def cli_schijn(uitvoeren, vastgelegd):
    def run(cmd, **kw):
        vastgelegd.append(cmd)
        return uitvoeren()
    return run


print("1. big-pickle via opencode run ->")
vastgelegd = []
uitvoer = opencode_uitvoer([
    {"type": "step_start", "part": {"type": "step-start"}},
    {"type": "text", "part": {"type": "text", "text": json.dumps(GOED)}},
    {"type": "step_finish", "part": {"reason": "stop", "cost": 0}},
])
main.subprocess.run = cli_schijn(lambda: uitvoer, vastgelegd)
main.AI_PROVIDERS = ["opencode-cli"]
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:opencode/big-pickle", d["bron"]
assert d["titel"] == "Parabolen" and d["oefensom"]["correct_index"] == 1
cmd = vastgelegd[0]
assert cmd[0] == "opencode" and cmd[1] == "run", cmd
assert "--format" in cmd and "json" in cmd and "--pure" in cmd, cmd
assert "opencode/big-pickle" in cmd, "model moet provider/model zijn"
assert cmd[-1].startswith("Je bent een heel geduldige wiskunde-docent"), "prompt ontbreekt"
print("   commando:", " ".join(cmd[:6]), "...")
print("   bron:", d["bron"], "| titel:", d["titel"])

print("2. model faalt met een error-gebeurtenis -> volgende model ->")
gemaakt = {"n": 0}


def volgorde():
    gemaakt["n"] += 1
    if gemaakt["n"] == 1:
        return opencode_uitvoer(
            [{"type": "error", "error": {"name": "UnknownError", "data": {"message": "server error"}}}]
        )
    return opencode_uitvoer([
        {"type": "text", "part": {"type": "text", "text": json.dumps(GOED)}},
        {"type": "step_finish", "part": {"reason": "stop", "cost": 0}},
    ])


main.subprocess.run = cli_schijn(volgorde, vastgelegd)
main.OPENCODE_CLI_MODELLEN = ["opencode/big-pickle", "opencode/space-bunny-free"]
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:opencode/space-bunny-free", d["bron"]
print("   big-pickle fout -> space-bunny-free werkte ->", d["bron"])

print("3. JSON in een markdownblok ->")
rommel = opencode_uitvoer([
    {"type": "text", "part": {"type": "text", "text": "Hier is je JSON:\n```json\n" + json.dumps(GOED) + "\n```"}},
    {"type": "step_finish", "part": {"reason": "stop", "cost": 0}},
])
main.subprocess.run = cli_schijn(lambda: rommel, vastgelegd)
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:opencode/big-pickle", d["bron"]
print("   opgeschoond tot:", d["bron"])

print("4. geen JSON -> database ->")
leeg = opencode_uitvoer([{"type": "text", "part": {"type": "text", "text": "geen JSON hier"}}])
main.subprocess.run = cli_schijn(lambda: leeg, vastgelegd)
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "database" and d["titel"] == "Parabolen", d["bron"]
print("   bron:", d["bron"], "| titel:", d["titel"])

print("5. opencode ontbreekt -> database, geen crash ->")


def weg():
    raise FileNotFoundError("opencode")


main.subprocess.run = cli_schijn(weg, vastgelegd)
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "database", d["bron"]
print("   bron:", d["bron"])

print("6. lokaal model (OpenAI-compatibel) ->")
main.AI_PROVIDERS = ["lokaal"]
main.LOKAAL_MODELLEN = ["qwen2.5:3b"]
gevangen = {}


def nep(url, timeout=None):
    gevangen["url"] = url
    if url.data is None:
        return io.BytesIO(json.dumps({"data": [{"id": "qwen2.5:3b"}]}).encode())
    lading = json.loads(url.data.decode())
    gevangen["lading"] = lading
    gevangen["model"] = lading.get("model")
    antwoord = {"choices": [{"message": {"content": json.dumps(GOED)}}]}
    return io.BytesIO(json.dumps(antwoord).encode())


main.urllib.request.urlopen = nep
main.PING_CACHE.clear()
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:lokaal/qwen2.5:3b", d["bron"]
assert gevangen["lading"]["response_format"]["type"] == "json_schema", gevangen["lading"]["response_format"]
assert gevangen["lading"]["response_format"]["json_schema"]["schema"]["required"], "schema ontbreekt"
assert gevangen["model"] == "qwen2.5:3b", gevangen["model"]
print("   bron:", d["bron"])
print("   schema afgegeven met", len(gevangen["lading"]["response_format"]["json_schema"]["schema"]["required"]), "sleutels")
main.PING_CACHE.clear()
h = c.get("/api/health").json()
assert h["volgorde"] == ["lokaal"], h["volgorde"]
print("   health:", h["volgorde"], "|", h["let_op"])

print("7. lokaal model valt terug op de database ->")


def dood(url, timeout=None):
    raise urllib.error.URLError("connection refused")


main.urllib.request.urlopen = dood
main.PING_CACHE.clear()
d = c.post("/api/uitleg", json={"onderwerp": "pythagoras in 3d"}).json()
assert d["bron"] == "database" and d["titel"] == "Pythagoras in 3D", d["bron"]
print("   bron:", d["bron"], "| titel:", d["titel"])

print()
print("ALLE OPENCODE-CLI- EN LOKALE-TESTS GESLAAGD")