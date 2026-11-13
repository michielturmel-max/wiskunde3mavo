import pathlib
import sys
import io
import json
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient

import main

c = TestClient(main.app)
main.AI_PROVIDERS = ["opencode"]

GOED = {
    "titel": "Parabolen via opencode",
    "samenvatting": "Een U-vormige kromme.",
    "praktijk_voorbeeld": "De baan van een geworpen bal.",
    "ezelsbruggetje": "Omhoog, omlaag, weer omhoog.",
    "stappenplan": ["Maak een tabel", "Teken de punten", "Zoek het laagste punt"],
    "grafiek_formule": "x^2 - 4",
    "veelgemaakte_fout": "Negatieve x-waarden overslaan.",
    "oefensom": {
        "vraag": "Hoeveel nulpunten?",
        "opties": ["1", "2", "3"],
        "correct_index": 1,
        "uitleg": "Twee, want x = 2 en x = -2.",
    },
}

SLEUTELS = ["titel", "samenvatting", "praktijk_voorbeeld", "ezelsbruggetje",
            "stappenplan", "grafiek_formule", "veelgemaakte_fout", "oefensom"]


def nep_server(reacties):
    """Nep-opencode: /session, /session/{id}/message, DELETE /session/{id}."""
    log = []

    def opener(verzoek, timeout=None):
        url = verzoek.full_url
        methode = verzoek.get_method()
        lading = json.loads(verzoek.data.decode()) if verzoek.data else None
        log.append({"url": url, "methode": methode, "lading": lading})
        if not reacties:
            raise urllib.error.URLError("connection refused")
        reactie = reacties.pop(0)
        if isinstance(reactie, Exception):
            raise reactie
        return io.BytesIO(json.dumps(reactie).encode())

    return opener, log


def als_tool(inhoud):
    return {"info": {"cost": 0, "error": None},
            "parts": [{"type": "tool", "tool": "StructuredOutput",
                       "state": {"status": "completed", "input": inhoud}}]}


sessie_antwoord = {"id": "ses_test123", "title": "wiskunde3mavo"}

print("1. opencode levert JSON via het StructuredOutput-tool ->")
opener, log = nep_server([sessie_antwoord, als_tool(GOED), {}])
main.urllib.request.urlopen = opener
main.ping_opencode = lambda: True
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:space-bunny-free", d["bron"]
assert d["titel"] == "Parabolen via opencode"
assert d["oefensom"]["correct_index"] == 1
assert len(d["stappenplan"]) == 3
print("   bron:", d["bron"], "| titel:", d["titel"], "| formule:", d["grafiek_formule"])
print("   verzoeken:", [x["methode"] + " " + x["url"].split("4196")[-1] for x in log])
assert log[2]["methode"] == "DELETE", "sessie wordt niet opgeruimd"
print("   sessie wordt opgeruimd: ja")

print("2. JSON komt als tekst-part ->")
tekst_antwoord = {"info": {"cost": 0},
                  "parts": [{"type": "text", "text": json.dumps(GOED)}]}
opener, log = nep_server([sessie_antwoord, tekst_antwoord, {}])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:space-bunny-free", d["bron"]
print("   ok:", d["bron"])

print("3. json_schema en model worden meegestuurd ->")
opener, log = nep_server([sessie_antwoord, als_tool(GOED), {}])
main.urllib.request.urlopen = opener
c.post("/api/uitleg", json={"onderwerp": "parabolen"})
lading = log[1]["lading"]
assert lading["model"] == {"providerID": "opencode", "modelID": "space-bunny-free"}, lading["model"]
assert lading["format"]["type"] == "json_schema"
schema = lading["format"]["schema"]
assert schema["required"] == SLEUTELS, schema["required"]
assert schema["properties"]["oefensom"]["properties"]["correct_index"]["type"] == "integer"
assert lading["tools"]["bash"] is False, "tools moeten uit staan"
assert "Nederlands" in lading["system"]
print("   model:", lading["model"])
print("   format:", lading["format"]["type"], "met", len(schema["required"]), "verplichte sleutels")
print("   tools uitgezet:", lading["tools"])

print("4. opencode weigert (403 free tier, zoals big-pickle) -> volgende model ->")
fout = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b'{"error":"free tier"}'))
opener, log = nep_server([fout, sessie_antwoord, als_tool(GOED), {}])
main.urllib.request.urlopen = opener
main.OPENCODE_MODELLEN = ["big-pickle", "space-bunny-free"]
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:space-bunny-free", d["bron"]
print("   big-pickle geweigerd, toen space-bunny-free gebruikt ->", d["bron"])

print("5. model geeft een fout in info.error -> volgende model ->")
antwoord_fout = {"info": {"error": {"data": {"message": "OpenCode's free tier can only be used from within OpenCode"}}},
                 "parts": []}
opener, log = nep_server([sessie_antwoord, antwoord_fout, {}, sessie_antwoord, als_tool(GOED), {}])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:space-bunny-free", d["bron"]
print("   error afgevangen, volgende model werkte ->", d["bron"])

print("6. opencode draait niet -> database ->")
opener, log = nep_server([urllib.error.URLError("connection refused")])
main.urllib.request.urlopen = opener
main.PING_CACHE.clear()
main.ping_opencode = lambda: False
main.OPENCODE_MODELLEN = ["space-bunny-free", "big-pickle"]
d = c.post("/api/uitleg", json={"onderwerp": "pythagoras in 3d"}).json()
assert d["bron"] == "database" and d["titel"] == "Pythagoras in 3D", d
assert all(k in d for k in SLEUTELS)
print("   bron:", d["bron"], "| titel:", d["titel"])

print("7. health toont beide providers ->")
main.PING_CACHE.clear()
main.ping_opencode = lambda: True
main.GROK_API_KEY = "or-v1-x"
main.AI_PROVIDERS = ["opencode", "grok"]
h = c.get("/api/health").json()
assert h["volgorde"] == ["opencode", "grok"], h["volgorde"]
assert h["opencode"]["kosten"] == "0,00" and h["grok"]["kosten"] == "0,00"
print("   volgorde:", h["volgorde"], "| actief:", h["actieve_ai"])
print("   let op:", h["let_op"])

main.PING_CACHE.clear()
main.ping_opencode = lambda: False
main.GROK_API_KEY = ""
h = c.get("/api/health").json()
assert h["volgorde"] == [] and h["actieve_ai"] == "database", h
print("   zonder AI -> actief:", h["actieve_ai"], "|", h["let_op"])

print("8. AI_PROVIDERS volgorde is configureerbaar ->")
main.PING_CACHE.clear()
main.ping_opencode = lambda: True
main.GROK_API_KEY = "or-v1-x"
main.AI_PROVIDERS = ["grok", "opencode"]
h = c.get("/api/health").json()
assert h["volgorde"] == ["grok", "opencode"], h["volgorde"]
print("   AI_PROVIDERS=grok,opencode ->", h["volgorde"])
main.AI_PROVIDERS = ["opencode", "grok"]

print()
print("ALLE OPENCODE-TESTS GESLAAGD")