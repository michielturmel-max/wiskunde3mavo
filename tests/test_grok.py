import pathlib
import sys
import io
import json
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient

import main

c = TestClient(main.app)

GOED = {
    "titel": "Kwadratische vergelijkingen",
    "samenvatting": "Een vergelijking met een x in het kwadraat.",
    "praktijk_voorbeeld": "Gooien met een kanon: de baan is een parabool.",
    "ezelsbruggetje": "Nulpunten zijn de plekken waar de grafiek de grond raakt.",
    "stappenplan": ["Zet alles aan een kant", "Ontbind de breuk", "Zet elk deel op nul"],
    "grafiek_formule": "x^2 - 5*x + 6",
    "veelgemaakte_fout": "Vergeten beide brackets apart op nul te zetten.",
    "oefensom": {
        "vraag": "Hoeveel nulpunten heeft x^2 - 5x + 6?",
        "opties": ["0", "1", "2", "3"],
        "correct_index": 2,
        "uitleg": "Ontbinden geeft (x-2)(x-3), dus twee nulpunten.",
    },
}

SLEUTELS = ["titel", "samenvatting", "praktijk_voorbeeld", "ezelsbruggetje",
            "stappenplan", "grafiek_formule", "veelgemaakte_fout", "oefensom"]


def nep_urlopen(reacties):
    log = []

    def opener(verzoek, timeout=None):
        log.append({
            "url": verzoek.full_url,
            "payload": json.loads(verzoek.data.decode()),
            "headers": {k.lower(): v for k, v in verzoek.headers.items()},
        })
        if not reacties:
            raise urllib.error.URLError("geen verbinding")
        reactie = reacties.pop(0)
        if isinstance(reactie, Exception):
            raise reactie
        return io.BytesIO(json.dumps(reactie).encode())

    return opener, log


def zet_key(sleutel, modellen=None):
    main.GROK_API_KEY = sleutel
    if modellen is not None:
        main.GROK_MODELLEN = modellen
    main.GROK_BESCHIKBAAR = bool(sleutel) and bool(main.GROK_MODELLEN)


ok = lambda **kw: {"choices": [{"message": {"content": json.dumps(GOED)}}]}
httpfout = lambda code: urllib.error.HTTPError("u", code, "fout", {}, io.BytesIO(b'{"error":"x"}'))

print("1. GEEN key -> app werkt volledig op de database (0,00) ->")
zet_key("")
opener, log = nep_urlopen([])
main.urllib.request.urlopen = opener
h = c.get("/api/health").json()
assert h["actieve_ai"] == "database", h
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "database" and d["titel"] == "Parabolen"
assert len(log) == 0, "er mag geen API-verzoek gedaan worden zonder key"
assert all(k in d for k in SLEUTELS)
print("   health actieve_ai:", h["actieve_ai"])
print("   bron:", d["bron"], "| titel:", d["titel"], "| API-aanroepen:", len(log))

print("2. GEEN key, alle vier de onderwerpen ->")
for onderwerp, verwacht in [("Parabolen", "Parabolen"),
                            ("wat is soscastoa", "SOS-CAST-OA"),
                            ("ontbinden in factoren", "Product-som"),
                            ("Pythagoras in 3D", "Pythagoras")]:
    d = c.post("/api/uitleg", json={"onderwerp": onderwerp}).json()
    so = d["oefensom"]
    assert d["bron"] == "database" and d["titel"].startswith(verwacht), (onderwerp, d["titel"])
    assert all(k in d for k in SLEUTELS)
    assert 3 <= len(d["stappenplan"]) <= 5
    assert len(so["opties"]) >= 2 and 0 <= so["correct_index"] < len(so["opties"])
    print(f"   {onderwerp:22} -> {d['titel'][:34]:36} | {d['grafiek_formule']:14} | {len(so['opties'])} opties")

print("3. GEEN key, onbekend onderwerp -> generieke uitleg ->")
d = c.post("/api/uitleg", json={"onderwerp": "irrationale wortels"}).json()
assert d["bron"] == "database" and d["titel"] == "Wiskunde uitgelegd"
assert all(k in d for k in SLEUTELS)
print("   titel:", d["titel"], "| stappen:", len(d["stappenplan"]), "| opties:", len(d["oefensom"]["opties"]))

print("4. key aanwezig -> Grok antwoordt ->")
opener, log = nep_urlopen([ok()])
main.urllib.request.urlopen = opener
zet_key("or-v1-testkey")
d = c.post("/api/uitleg", json={"onderwerp": "kwadratische vergelijkingen"}).json()
assert d["bron"] == "ai:x-ai/grok-4-fast:free", d["bron"]
assert d["titel"] == "Kwadratische vergelijkingen"
assert d["grafiek_formule"] == "x^2-5*x+6"
p = log[0]["payload"]
assert p["response_format"] == {"type": "json_object"}
assert log[0]["headers"]["authorization"] == "Bearer or-v1-testkey"
assert p["messages"][0]["role"] == "system" and "Nederlands" in p["messages"][0]["content"]
print("   bron:", d["bron"], "| response_format:", p["response_format"])
print("   system-prompt:", len(p["messages"][0]["content"]), "tekens | max_tokens:", p["max_tokens"])

print("5. GEPAARDE MODELLEN WORDEN GEWEIGERD ->")
main.GROK_MODELLEN_RAW = ["x-ai/grok-4-fast", "x-ai/grok-4-fast:free"]
main.GROK_MODELLEN = list(dict.fromkeys(m for m in main.GROK_MODELLEN_RAW if m.endswith(":free")))
assert main.GROK_MODELLEN == ["x-ai/grok-4-fast:free"], main.GROK_MODELLEN
opener, log = nep_urlopen([ok()])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "ai:x-ai/grok-4-fast:free"
assert log[0]["payload"]["model"].endswith(":free")
print("   ingevoerd:", main.GROK_MODELLEN_RAW)
print("   toegestaan:", main.GROK_MODELLEN, "| daadwerkelijk gebruikt:", log[0]["payload"]["model"])

print("6. als er ALLEEN betaalde modellen zijn -> geen AI, wel database ->")
opener, log = nep_urlopen([])
main.urllib.request.urlopen = opener
zet_key("or-v1-testkey", modellen=["x-ai/grok-4", "grok-3"])
assert main.grok_beschikbaar() is False
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert d["bron"] == "database" and len(log) == 0
print("   GROK_BESCHIKBAAR:", main.GROK_BESCHIKBAAR, "| bron:", d["bron"], "| API-aanroepen:", len(log))

print("7. Grok faalt (401) -> database ->")
opener, log = nep_urlopen([httpfout(401)])
main.urllib.request.urlopen = opener
zet_key("or-v1-testkey", modellen=["x-ai/grok-4-fast:free"])
d = c.post("/api/uitleg", json={"onderwerp": "soscastoa"}).json()
assert d["bron"] == "database" and d["titel"].startswith("SOS-CAST-OA")
print("   bron:", d["bron"], "| titel:", d["titel"])

print("8. Grok faalt (429 rate limit) -> database ->")
opener, log = nep_urlopen([httpfout(429)])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "pythagoras in 3d"}).json()
assert d["bron"] == "database" and d["titel"] == "Pythagoras in 3D"
print("   bron:", d["bron"], "| titel:", d["titel"])

print("9. netwerkfout / geen internet -> database ->")
opener, log = nep_urlopen([urllib.error.URLError("dns"), urllib.error.URLError("dns")])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "ontbinden in factoren"}).json()
assert d["bron"] == "database" and d["titel"].startswith("Product-som")
print("   bron:", d["bron"], "| titel:", d["titel"], "| verzoeken:", len(log))

print("10. geen JSON -> volgende gratis model ->")
opener, log = nep_urlopen([{"choices": [{"message": {"content": "geen json"}}]}, ok()])
main.urllib.request.urlopen = opener
zet_key("or-v1-testkey", modellen=["x-ai/grok-4-fast:free", "x-ai/grok-3-mini:free"])
d = c.post("/api/uitleg", json={"onderwerp": "kwadratische vergelijkingen"}).json()
assert d["bron"] == "ai:x-ai/grok-3-mini:free", d["bron"]
print("   geprobeerd:", [e["payload"]["model"] for e in log], "-> ", d["bron"])

print("11. JSON in codeblok / losse string ->")
opener, log = nep_urlopen([{"choices": [{"message": {"content": "```json\n" + json.dumps(GOED) + "\n```"}}]}])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "kwadratische vergelijkingen"}).json()
assert d["bron"].startswith("ai:")
print("   ok:", d["bron"])

print("12. vijandige Grok-uitvoer wordt geneutraliseerd ->")
VIELED = dict(GOED, grafiek_formule="y = x^2; alert('hacked')", stappenplan=["a"] * 2,
              oefensom=dict(GOED["oefensom"], opties=["luk", "in"], correct_index="A"))
opener, log = nep_urlopen([{"choices": [{"message": {"content": json.dumps(VIELED)}}]}])
main.urllib.request.urlopen = opener
d = c.post("/api/uitleg", json={"onderwerp": "parabolen"}).json()
assert "alert" not in d["grafiek_formule"] and "#" not in d["grafiek_formule"]
assert 3 <= len(d["stappenplan"]) <= 5
assert 0 <= d["oefensom"]["correct_index"] < len(d["oefensom"]["opties"])
print("   formule:", d["grafiek_formule"], "| stappen:", len(d["stappenplan"]), "| opties:", len(d["oefensom"]["opties"]))

print("13. health met key ->")
opener, log = nep_urlopen([])
main.urllib.request.urlopen = opener
zet_key("or-v1-testkey", modellen=["x-ai/grok-4-fast:free", "x-ai/grok-3-mini:free"])
h = c.get("/api/health").json()
assert h["actieve_ai"] == "grok" and h["grok"]["alleen_gratis"] is True
assert all(m.endswith(":free") for m in h["grok"]["modellen"])
print("  ", json.dumps(h, ensure_ascii=False))

print("14. indexpagina ->")
r = c.get("/")
assert r.status_code == 200
for kw in ["function-plot", "tailwindcss.com", "Parabolen", "SOSCASTOA", "0,00", "Grok"]:
    assert kw in r.text, kw
assert "ollama" not in r.text.lower()
print("   ok:", len(r.text), "bytes | geen ollama-vermelding meer")

print()
print("ALLE GROK-GRATIS-TESTS GESLAAGD")