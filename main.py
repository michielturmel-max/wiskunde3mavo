from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Alleen gratis AI: Grok via OpenRouter, uitsluitend modellen met het :free-label.
GROK_API_URL = os.getenv("GROK_API_URL", "https://openrouter.ai/api/v1/chat/completions").strip()
GROK_SITE_URL = os.getenv("GROK_SITE_URL", "http://localhost")
GROK_APP_NAAM = os.getenv("GROK_APP_NAAM", "wiskunde3mavo")
GROK_TIMEOUT = float(os.getenv("GROK_TIMEOUT", "45"))
GROK_MODELLEN_RAW = [
    m.strip()
    for m in os.getenv("GROK_MODELLEN", "x-ai/grok-4-fast:free,x-ai/grok-3-mini:free").split(",")
    if m.strip()
]
GROK_MODELLEN = list(dict.fromkeys(m for m in GROK_MODELLEN_RAW if m.endswith(":free")))
GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip() or os.getenv("OPENROUTER_API_KEY", "").strip()
GROK_BESCHIKBAAR = bool(GROK_API_KEY) and bool(GROK_MODELLEN)


def alleen_gratis_modellen(modellen: list[str]) -> list[str]:
    return list(dict.fromkeys(m.strip() for m in modellen if m.strip().endswith(":free")))


def grok_beschikbaar() -> bool:
    return bool(GROK_API_KEY) and bool(alleen_gratis_modellen(GROK_MODELLEN))


# AI 0: lokaal model op je eigen laptop. Werkt met llama-server (llama.cpp) en met Ollama,
# want beide spreken OpenAI-compatibel /v1/chat/completions.
LOKAAL_URL = os.getenv("LOKAAL_URL", "http://127.0.0.1:8080/v1/chat/completions").strip()
LOKAAL_BASIS = LOKAAL_URL.rsplit("/v1", 1)[0]
LOKAAL_SLEUTEL = os.getenv("LOKAAL_API_KEY", "").strip()
LOKAAL_MODELLEN = [
    m.strip() for m in os.getenv("LOKAAL_MODELLEN", "qwen2.5:3b").split(",") if m.strip()
]
LOKAAL_TIMEOUT = float(os.getenv("LOKAAL_TIMEOUT", "180"))
LOKAAL_JSON_SCHEMA = os.getenv("LOKAAL_JSON_SCHEMA", "1").lower() not in ("0", "nee", "false", "no")

# AI 1: opencode als los proces. Dit is de ENIGE route waarin big-pickle werkt,
# want de HTTP-API van opencode weigert de gratis laag (HTTP 403).
OPENCODE_CLI_BIN = os.getenv("OPENCODE_CLI_BIN", "opencode").strip() or "opencode"
OPENCODE_CLI_MODELLEN = [
    m.strip()
    for m in os.getenv("OPENCODE_CLI_MODELLEN", "opencode/big-pickle,opencode/space-bunny-free").split(",")
    if m.strip()
]
OPENCODE_CLI_TIMEOUT = float(os.getenv("OPENCODE_CLI_TIMEOUT", "300"))
OPENCODE_CLI_PURE = os.getenv("OPENCODE_CLI_PURE", "1").lower() not in ("0", "nee", "false", "no")


# AI 1: opencode. Start zelf een headless server:  opencode serve --port 4196
OPENCODE_URL = os.getenv("OPENCODE_URL", "http://127.0.0.1:4196").strip().rstrip("/")
OPENCODE_PROVIDER = os.getenv("OPENCODE_PROVIDER", "opencode").strip()
OPENCODE_MODELLEN = [
    m.strip()
    for m in os.getenv("OPENCODE_MODELLEN", "space-bunny-free,big-pickle").split(",")
    if m.strip()
]
OPENCODE_TIMEOUT = float(os.getenv("OPENCODE_TIMEOUT", "180"))

# Volgorde waarin de AI-providers worden geprobeerd; database is altijd de laatste.
AI_PROVIDERS = [
    p.strip().lower()
    for p in os.getenv("AI_PROVIDERS", "opencode-cli,grok").split(",")
    if p.strip()
]

UITLEG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "samenvatting": {"type": "string"},
        "praktijk_voorbeeld": {"type": "string"},
        "ezelsbruggetje": {"type": "string"},
        "stappenplan": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
        "grafiek_formule": {"type": "string"},
        "veelgemaakte_fout": {"type": "string"},
        "oefensom": {
            "type": "object",
            "properties": {
                "vraag": {"type": "string"},
                "opties": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 6},
                "correct_index": {"type": "integer", "minimum": 0, "maximum": 5},
                "uitleg": {"type": "string"},
            },
            "required": ["vraag", "opties", "correct_index", "uitleg"],
            "additionalProperties": False,
        },
    },
    "required": [
        "titel",
        "samenvatting",
        "praktijk_voorbeeld",
        "ezelsbruggetje",
        "stappenplan",
        "grafiek_formule",
        "veelgemaakte_fout",
        "oefensom",
    ],
    "additionalProperties": False,
}

SLEUTELS = [
    "titel",
    "samenvatting",
    "praktijk_voorbeeld",
    "ezelsbruggetje",
    "stappenplan",
    "grafiek_formule",
    "veelgemaakte_fout",
    "oefensom",
]

STAPPEN_HULP = [
    "Schrijf op wat je al weet: welke getallen of woorden staan er in de vraag?",
    "Zet alles wat je weet in een wiskundige formule of een tekening.",
    "Werk stap voor stap verder en schrijf elke stap op.",
    "Controleer je antwoord met de grafiek of door terug te rekenen.",
    "Noteer het antwoord met de juiste eenheid en een punt.",
]

SYSTEEM_PROMPT = f"""Je bent een heel geduldige wiskunde-docent voor HAVO 3 (Nederland).

Je legt elk onderwerp uit in Jip-en-Janneketaal: gewone woorden, korte zinnen, geen jargon.
Als je een vakterm moet gebruiken, leg je die meteen in hetzelfde zinnetje uit.

Je antwoordt ALTIJD met uitsluitend één JSON-object, zonder tekst eromheen, zonder markdown.
Het JSON-object heeft exact deze sleutels:

{{
  "titel": "korte naam van het onderwerp",
  "samenvatting": "één zin uitleg op leekenniveau, zonder jargon",
  "praktijk_voorbeeld": "één of twee zinnen: waar gebruik je dit in het echte leven of in de volgende les?",
  "ezelsbruggetje": "een handige onthoudregel of een visuele truc die blijft hangen",
  "stappenplan": ["stap 1", "stap 2", "stap 3", "stap 4", "stap 5"],
  "grafiek_formule": "een wiskundige formule die als functie van x getekend kan worden",
  "veelgemaakte_fout": "de klassieke valkuil op de toets, en hoe je hem voorkomt",
  "oefensom": {{
    "vraag": "een korte meerkeuzevraag over het onderwerp",
    "opties": ["optie A", "optie B", "optie C", "optie D"],
    "correct_index": 0,
    "uitleg": "waarom dat antwoord klopt, in twee zinnen"
  }}
}}

Regels:
- "stappenplan" telt 3 tot 5 items, elk maximaal 120 tekens, elk begint met "1. ", "2. " enzovoort bij het eerste item.
- "grafiek_formule" gebruikt alleen x, cijfers, + - * / ^ ( ) en eventueel sin, cos, tan, sqrt, abs.
  Gebruik * voor vermenigvuldigen en ^ voor machten, dus "x^2 - 4" en niet "x² − 4".
  Kies een formule die de uitleg echt laat zien (niet altijd x^2).
- "correct_index" is een getal vanaf 0 dat de juiste optie aanwijst.
- Alles in het Nederlands, gericht op HAVO 3-niveau.
"""

GEGEVEN_ONDERWERP = "Het onderwerp waarover ik nu een uitleg wil schrijven is: \"{onderwerp}\".\n\nLever het JSON-object."

FALLBACK: dict[str, dict[str, Any]] = {
    "parabolen": {
        "trefwoorden": ["parabool", "parabolen", "parabol", "kwadratische", "x2", "x^2", "kwadraat"],
        "data": {
            "titel": "Parabolen",
            "samenvatting": "Een parabool is een U-vormige of omgekeerde U-vormige kromme die je krijgt als je van x een kwadraat neemt.",
            "praktijk_voorbeeld": "Slecht wervelende ballen vliegen in een parabool: een werper gooit de bal zo dat hij in een mooie boog in het handscheken terechtkomt. Ook het water uit een fontein beschrijft bij elke waterstraal een stukje parabool.",
            "ezelsbruggetje": "Denk aan een bal die je omhoog gooit: eerst gaat hij omhoog (zoals het stijgende stuk), daalt hij naar het laagste punt en gaat hij weer omhoog. Die vorm heet een parabool.",
            "stappenplan": [
                "1. Schrijf de formule op in de vorm y = ax^2 + bx + c.",
                "2. Teken een tabel: kies getallen voor x en reken y uit. Neem ook negatieve getallen voor x.",
                "3. Zet de punten in een assenstelsel en teken een vloeiende lijn door de punten.",
                "4. Bepaal het laagste of hoogste punt en schrijf het als (x, y).",
                "5. Lees de snijpunten met de x-as af uit de tabel: dat zijn de nulpunten.",
            ],
            "grafiek_formule": "x^2 - 4",
            "veelgemaakte_fout": "Veel leerlingen vergeten negatieve waarden voor x mee te rekenen, of vinden het toppunt door in de tabel te blijven zoeken. Reken altijd x^2 eerst helemaal uit en gebruik daarna pas de tabel.",
            "oefensom": {
                "vraag": "Welke uitspraak over de grafiek van y = x^2 - 4 klopt?",
                "opties": [
                    "De grafiek ligt overal onder de x-as.",
                    "De grafiek snijdt de x-axis op twee plekken.",
                    "Het laagste punt ligt op (0, 4).",
                    "De grafiek is een rechte lijn.",
                ],
                "correct_index": 1,
                "uitleg": "Zet y op 0: dan is x^2 = 4, dus x = 2 of x = -2. De grafiek snijdt de x-axis dus twee keer. Het laagste punt is (0, -4), niet (0, 4).",
            },
        },
    },
    "soscastoa": {
        "trefwoorden": ["soscastoa", "sinus", "cosinus", "tangens", "sin", "cos", "tan", "rechthoekige driehoek", "golf", "trig"],
        "data": {
            "titel": "SOS-CAST-OA (sinus, cosinus, tangens)",
            "samenvatting": "In een rechthoekige driehoek vertelt sin, cos en tan je de verhoudingen tussen de hoeken en de zijden, en je kunt er ook hoeken mee terugrekenen.",
            "praktijk_voorbeeld": "Je gebruikt het om te bepalen hoe hoog je moet mikken bij een hoek, hoe ver een bal schuin wegschiet, of hoeveel een helling oploopt. Ook in de natuurkunde (golven) en in de bouw (steile daken) komt het voor.",
            "ezelsbruggetje": "S-CAST-OA: Sinus is COSinus ACHTERste, Tangens is COSinus bovenin. Altijd tegenover (T) klopt de lange zijde (langs de schuine); bij cos en sin mag je nooit tegenover de hoek staan.",
            "stappenplan": [
                "1. Herken in de driehoek de rechte hoek (90 graden); de zijte ertegen is de schuine zijde.",
                "2. Zet de hoek die je zoekt neer, en zet er 'S' (sinus), 'C' (cosinus) of 'T' (tangens) bij.",
                "3. Kies twee getallen: het ene uit de tabel van sin/cos/tan, het andere uit de driehoek.",
                "4. Reken het derde getallen uit met de verhouding (= of : op de rekenmachine).",
                "5. Wil je een hoek terugrekenen? Gebruik dan de knop SIN^-1, COS^-1 of TAN^-1 op je rekenmachine.",
            ],
            "grafiek_formule": "sin(x)",
            "veelgemaakte_fout": "Het meest fout gaat het met de schuine zijde: die is alleen bij sinus en tangens de deler. Bij cosinus deel je door de schuine zijde, maar die staat in de teller.",
            "oefensom": {
                "vraag": "In een rechthoekige driehoek is de hoek die je zoekt 30 graden. Welke verhouding is SO-CAST-OA?",
                "opties": [
                    "Tegenover de hoek : schuine zijde",
                    "Aanliggende zijde : schuine zijde",
                    "Tegenover de hoek : aanliggende zijde",
                    "Aanliggende zijde : tegenover de hoek",
                ],
                "correct_index": 1,
                "uitleg": "Een 'C' of 'S' betekent dat je door de schuine zijde deelt. Bij cosinus zoek je de aanliggende zijde, en die staat bij de letter C in de teller, dus: aanliggend : schuine zijde.",
            },
        },
    },
    "product-som": {
        "trefwoorden": [
            "ontbinden",
            "factoren",
            "factor",
            "product",
            "product-som",
            "product som",
            "aantallen",
            "kwadratische vergelijking",
        ],
        "data": {
            "titel": "Product-sommethode (ontbinden in factoren)",
            "samenvatting": "Bij de product-sommethode zoek je twee getallen die je samen vermenigvuldigen moeten krijgen en opgeteld hetzelfde zijn als het getal in het midden.",
            "praktijk_voorbeeld": "Dit is de snelste manier om x^2 + 5x + 6 op te schrijven als (x + 2)(x + 3), en daarmee de nulpunten en de grafiek van een parabool te vinden. Je komt er ook uit bij het wegstrepen van breuken.",
            "ezelsbruggetje": "Twee getallen moeten het product én de som leveren. Zet ze in een vakje-schema: product linksboven, som linksonder, dan het midden erboven.",
            "stappenplan": [
                "1. Zet de kwadratische vergelijking neer en splits het middelste getal op in twee getallen die je kunt vermenigvuldigen (denk aan 1 en het getal zelf).",
                "2. Controleer: vermenigvuldig die twee getallen: is dat het getal vóór de breuk of achter de breuk?",
                "3. Tel die twee getallen op: klopt dat met het middelste getal?",
                "4. Schrijf de ontbinding: (x + eerste getal)(x + tweede getal).",
                "5. Zet elk bracket apart op nul en reken de nulpunten uit.",
            ],
            "grafiek_formule": "(x - 1) * (x + 3)",
            "veelgemaakte_fout": "Let op de volgorde: bij x^2 - 5x + 6 moet je x^2 - 2x - 3x + 6 gebruiken, want het middelste getal is -5. Vergeet het minteken niet als je het eerste bracket in een minteken schrijft.",
            "oefensom": {
                "vraag": "Hoe ontbind je x^2 + 7x + 12 in factoren?",
                "opties": [
                    "(x + 2)(x + 6)",
                    "(x + 3)(x + 4)",
                    "(x + 1)(x + 12)",
                    "(x + 7)(x + 12)",
                ],
                "correct_index": 1,
                "uitleg": "Zoek twee getallen met product 12 en som 7. Dat zijn 3 en 4: 3 keer 4 is 12 en 3 plus 4 is 7. Dus x^2 + 7x + 12 = (x + 3)(x + 4).",
            },
        },
    },
    "pythagoras3d": {
        "trefwoorden": ["pythagoras", "3d", "aanschouwelijk", "ribbe", "diagonaal", "ruimte", "lichaam", "kamer", "doos", "balk"],
        "data": {
            "titel": "Pythagoras in 3D",
            "samenvatting": "In een balk of andere 3D-vorm los je eerst stap voor stap vlakke driehoeken op, en pas dan pas ga je de echte diagonaal berekenen.",
            "praktijk_voorbeeld": "Je rekent uit hoe lang een koord door een kamer is, of hoe lang een ladder moet zijn die schuin tegen een muur staat. Ook GPS-ontvangers en gamemakers gebruiken dit om afstanden in de ruimte te bepalen.",
            "ezelsbruggetje": "Verdeel de 3D-vorm in vlakke vlakken en teken drie keer een driehoek. Onthoud: de schuine zijde is altijd de langste, dus hij staat altijd aan de linkerkant van het kwadraat.",
            "stappenplan": [
                "1. Teken de 3D-vorm plat neer en zet alle afmetingen erin: lengte, breedte, hoogte.",
                "2. Zoek de driehoek die de diagonaal over de vloer (of het plafond) bevat: rechthoekszijden zijn bijvoorbeeld breedte en diepte.",
                "3. Reken die diagonaal met a^2 + b^2 = c^2.",
                "4. Die uitkomst is nu een zijde van de tweede driehoek, samen met de hoogte.",
                "5. Reken de echte diagonaal met a^2 + b^2 = c^2 en druk het antwoord uit in meters.",
            ],
            "grafiek_formule": "sqrt(x^2 + 9)",
            "veelgemaakte_fout": "De grootste fout is meteen alles in één keer in de stelling zetten. Je moet altijd eerst het vlakke stuk uitrekenen, en dát getal gebruik je pas als zijde in de volgende driehoek.",
            "oefensom": {
                "vraag": "Een kamer is 4 m breed en 3 m diep. Hoe lang is de diagonaal over de vloer?",
                "opties": ["5 m", "6 m", "7 m", "12 m"],
                "correct_index": 0,
                "uitleg": "Gebruik a^2 + b^2 = c^2: 4^2 + 3^2 = 16 + 9 = 25. De wortel van 25 is 5, dus de diagonaal is 5 meter.",
            },
        },
    },
}

STANDAARD = {
    "titel": "Wiskunde uitgelegd",
    "samenvatting": "Een korte uitleg van het onderwerp, in gewone woorden en met telkens een stap-voor-stap plan.",
    "praktijk_voorbeeld": "Je komt dit tegen bij het instorten van je volgende proefwerk én in het echte leven, bijvoorbeeld bij het inschatten van afstanden en prijzen.",
    "ezelsbruggetje": "Schrijf eerst in eigen woorden op wat de vraag je vraagt. Daarna pas ga je rekenen: eerst tekenen, dan pas rekenen.",
    "stappenplan": STAPPEN_HULP,
    "grafiek_formule": "x^2",
    "veelgemaakte_fout": "Te snel rekenen zonder eerst een tekening of tabel te maken. Even tekenen kost minder tijd dan drie keer opnieuw beginnen.",
    "oefensom": {
        "vraag": "Wat is de beste eerste stap bij een wiskundige opgave?",
        "opties": [
            "Direct met de rekenmachine gaan rekenen.",
            "Opschrijven wat er gevraagd wordt en een tekening of tabel maken.",
            "Het antwoord gokken.",
            "Alle getallen in één keer optellen.",
        ],
        "correct_index": 1,
        "uitleg": "Door te schrijven wat er gevraagd wordt, weet je welke formule je nodig hebt. Een tekening of tabel helpt daarbij en voorkomt dat je in een hoekje vastloopt.",
    },
}

FORMULE_TOKENS = ("sin", "cos", "tan", "sqrt", "abs", "log", "exp", "PI", "pi", "x", "X")


class Oefensom(BaseModel):
    vraag: str = ""
    opties: list[str] = Field(default_factory=list)
    correct_index: int = 0
    uitleg: str = ""


class Uitleg(BaseModel):
    titel: str = ""
    samenvatting: str = ""
    praktijk_voorbeeld: str = ""
    ezelsbruggetje: str = ""
    stappenplan: list[str] = Field(default_factory=list)
    grafiek_formule: str = ""
    veelgemaakte_fout: str = ""
    oefensom: Oefensom = Field(default_factory=Oefensom)
    bron: str = "database"


class UitlegVraag(BaseModel):
    onderwerp: str = ""


app = FastAPI(title="HAVO 3 Wiskunde", description="Gratis uitleg op leekenniveau met Grok.")


def naar_tekst(waarde: Any, standaard: str = "") -> str:
    if isinstance(waarde, str):
        schoon = waarde.strip()
        return schoon if schoon else standaard
    if isinstance(waarde, bool):
        return standaard
    if isinstance(waarde, (int, float)):
        return str(waarde)
    if isinstance(waarde, (list, tuple)):
        delen = [naar_tekst(deel) for deel in waarde]
        return " ".join(delen).strip() or standaard
    if isinstance(waarde, dict):
        delen = [naar_tekst(deel) for deel in waarde.values()]
        return " ".join(delen).strip() or standaard
    return standaard


def formule_schoonen(formule: str, standaard: str = "x^2") -> str:
    schoon = naar_tekst(formule)
    schoon = re.sub(r"^\s*[a-zA-Z]\s*(\([^()]*\))?\s*=\s*", "", schoon)
    schoon = schoon.replace("X", "x")
    schoon = re.sub(r"\bx\s*(\d)\b", r"x^\1", schoon)
    schoon = re.sub(r"\bx\s*\^\s*", "x^", schoon)
    schoon = re.sub(r"[^0-9a-zA-Z.+\-*/^() ]", "#", schoon)
    schoon = re.sub(
        r"[a-zA-Z][a-zA-Z0-9]*",
        lambda m: m.group(0) if m.group(0) in FORMULE_TOKENS else "#",
        schoon,
    )
    schoon = schoon.replace(" ", "")
    ongeldig = (
        "#" in schoon
        or schoon.count("(") != schoon.count(")")
        or "**" in schoon
        or "##" in schoon
        or not re.search(r"[0-9x]", schoon)
    )
    if ongeldig:
        return standaard
    return schoon[:60]


def stappen_schoonen(stappen: Any) -> list[str]:
    if not isinstance(stappen, (list, tuple)):
        tekst = naar_tekst(stappen)
        stappen = (
            [deel for deel in re.split(r"\n+|\s*(?=\d+\s*[.:)]?\s)", tekst) if deel.strip()]
            if tekst
            else []
        )
    schoon: list[str] = []
    for stap in list(stappen)[:5]:
        regel = naar_tekst(stap)
        regel = re.sub(r"^\s*(?:stap\s*)?\d+\s*[.):-]?\s*", "", regel, flags=re.IGNORECASE)
        if regel:
            schoon.append(f"{len(schoon) + 1}. {regel}")
    if len(schoon) < 3:
        for hulp in STAPPEN_HULP:
            if len(schoon) >= 5:
                break
            schoon.append(f"{len(schoon) + 1}. {hulp}")
    return schoon[:5]


def oefensom_schoonen(ruw: Any) -> dict[str, Any]:
    if not isinstance(ruw, dict):
        ruw = {}
    opties = ruw.get("opties", [])
    if isinstance(opties, dict):
        opties = [opties[k] for k in sorted(opties)]
    if not isinstance(opties, (list, tuple)):
        opties = [opties] if opties else []
    schoon_opties = [naar_tekst(optie) for optie in list(opties)[:6]]
    schoon_opties = [optie for optie in schoon_opties if optie][:6]
    while len(schoon_opties) < 2:
        schoon_opties.append("Ik weet het niet zeker")

    index = ruw.get("correct_index", 0)
    if isinstance(index, str):
        cijfers = re.findall(r"\d+", index)
        index = int(cijfers[0]) if cijfers else -1
    if not isinstance(index, int):
        index = 0
    index = 0 if index < 0 else min(index, len(schoon_opties) - 1)

    return {
        "vraag": naar_tekst(ruw.get("vraag"), "Los de volgende vraag op."),
        "opties": schoon_opties,
        "correct_index": index,
        "uitleg": naar_tekst(ruw.get("uitleg"), "Bekijk de uitleg bij het juiste antwoord."),
    }


def antwoord_schoonen(ruw: Any, basis: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(ruw, dict):
        ruw = {}
    if basis is None:
        basis = STANDAARD
    return {
        "titel": naar_tekst(ruw.get("titel"), basis["titel"]),
        "samenvatting": naar_tekst(ruw.get("samenvatting"), basis["samenvatting"]),
        "praktijk_voorbeeld": naar_tekst(ruw.get("praktijk_voorbeeld"), basis["praktijk_voorbeeld"]),
        "ezelsbruggetje": naar_tekst(ruw.get("ezelsbruggetje"), basis["ezelsbruggetje"]),
        "stappenplan": stappen_schoonen(ruw.get("stappenplan")),
        "grafiek_formule": formule_schoonen(naar_tekst(ruw.get("grafiek_formule"), basis["grafiek_formule"])),
        "veelgemaakte_fout": naar_tekst(ruw.get("veelgemaakte_fout"), basis["veelgemaakte_fout"]),
        "oefensom": oefensom_schoonen(ruw.get("oefensom")),
    }


def database_antwoord(onderwerp: str) -> dict[str, Any]:
    zoekwoord = (onderwerp or "").strip().lower()
    beste: dict[str, Any] | None = None
    beste_score = 0
    for onderdeel in FALLBACK.values():
        score = 0
        for trefwoord in onderdeel["trefwoorden"]:
            if trefwoord in zoekwoord:
                score = max(score, len(trefwoord))
        if score > beste_score:
            beste_score = score
            beste = onderdeel["data"]
    gekozen = dict(beste if beste is not None else STANDAARD)
    gekozen["stappenplan"] = list(gekozen["stappenplan"])
    gekozen["oefensom"] = dict(gekozen["oefensom"])
    schoon = antwoord_schoonen(gekozen)
    schoon["bron"] = "database"
    return schoon


def eerste_json_object(tekst: str) -> dict[str, Any] | None:
    """Haal het eerste kloppende JSON-object uit een lap tekst."""
    start = tekst.find("{")
    while start != -1:
        diepte = 0
        in_tekst = ontsnapt = False
        for positie in range(start, len(tekst)):
            teken = tekst[positie]
            if in_tekst:
                if ontsnapt:
                    ontsnapt = False
                elif teken == "\\":
                    ontsnapt = True
                elif teken == '"':
                    in_tekst = False
                continue
            if teken == '"':
                in_tekst = True
            elif teken == "{":
                diepte += 1
            elif teken == "}":
                diepte -= 1
                if diepte == 0:
                    kandidaat = tekst[start : positie + 1]
                    try:
                        uit = json.loads(kandidaat)
                    except json.JSONDecodeError:
                        uit = None
                    if isinstance(uit, dict):
                        return uit
                    if uit is not None:
                        return uit
                    break
        start = tekst.find("{", start + 1)
    return None


def json_uit_antwoord(antwoord: Any) -> Any:
    if isinstance(antwoord, dict):
        return antwoord
    if isinstance(antwoord, str):
        schoon = antwoord.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(schoon)
        except json.JSONDecodeError:
            return eerste_json_object(schoon)
    return None


def bericht_paren(onderwerp: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEEM_PROMPT},
        {"role": "user", "content": GEGEVEN_ONDERWERP.format(onderwerp=onderwerp)},
    ]


def http_json(url: str, lading: dict[str, Any], headers: dict[str, str], methode: str = "POST") -> Any:
    verzoek = urllib.request.Request(
        url,
        data=json.dumps(lading).encode("utf-8") if lading is not None else None,
        headers={**headers, "Content-Type": "application/json"},
        method=methode,
    )
    with urllib.request.urlopen(verzoek, timeout=OPENCODE_TIMEOUT) as antwoord:
        ruw = antwoord.read().decode("utf-8")
    return json.loads(ruw) if ruw.strip() else None


def json_uit_parts(parts: Any) -> Any:
    """opencode levert gestructureerde output via de StructuredOutput-tool, of als tekst."""
    if not isinstance(parts, list):
        return None
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "tool":
            toestand = part.get("state") or {}
            invoer = toestand.get("input")
            if isinstance(invoer, dict):
                return invoer
            geparseerd = json_uit_antwoord(invoer)
            if isinstance(geparseerd, dict):
                return geparseerd
    tekst = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
    return json_uit_antwoord(tekst)


def vraag_opencode(onderwerp: str) -> dict[str, Any] | None:
    basis = database_antwoord(onderwerp)
    koppen = {"Accept": "application/json"}
    for model in OPENCODE_MODELLEN:
        sessie: dict[str, Any] | None = None
        try:
            sessie = http_json(f"{OPENCODE_URL}/session", {"title": "wiskunde3mavo"}, koppen)
            if not isinstance(sessie, dict) or not sessie.get("id"):
                raise RuntimeError("opencode gaf geen sessie terug")
            bericht = http_json(
                f"{OPENCODE_URL}/session/{sessie['id']}/message",
                {
                    "model": {"providerID": OPENCODE_PROVIDER, "modelID": model},
                    "system": SYSTEEM_PROMPT,
                    "tools": {"bash": False, "edit": False, "write": False, "read": False, "webfetch": False},
                    "format": {"type": "json_schema", "schema": UITLEG_SCHEMA, "retryCount": 2},
                    "parts": [{"type": "text", "text": GEGEVEN_ONDERWERP.format(onderwerp=onderwerp)}],
                },
                koppen,
            )
            info = (bericht or {}).get("info") or {}
            foutmelding = info.get("error")
            if foutmelding:
                print(f"[opencode] model {model} weigerde: {foutmelding.get('data', {}).get('message', foutmelding)}")
                continue
            geparseerd = json_uit_parts((bericht or {}).get("parts"))
            if isinstance(geparseerd, dict) and (geparseerd.get("titel") or geparseerd.get("samenvatting")):
                uit = antwoord_schoonen(geparseerd, basis)
                uit["bron"] = f"ai:{model}"
                return uit
            print(f"[opencode] geen bruikbare JSON bij model {model}")
        except urllib.error.HTTPError as fout:
            print(f"[opencode] HTTP {fout.code} bij model {model}: {fout.read()[:200].decode('utf-8', 'ignore')}")
        except Exception as fout:
            print(f"[opencode] {type(fout).__name__} bij model {model}: {fout}")
            break
        finally:
            if sessie and sessie.get("id"):
                try:
                    http_json(f"{OPENCODE_URL}/session/{sessie['id']}", None, koppen, methode="DELETE")
                except Exception:
                    pass
    return None


def vraag_openai_compatibel(
    onderwerp: str,
    naam: str,
    url: str,
    sleutel: str,
    modellen: list[str],
    timeout: float,
    bron_voorvoegsel: str,
    schema: dict[str, Any] | None = None,
    extra_koppen: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    basis = database_antwoord(onderwerp)
    koppen = {"Content-Type": "application/json", "Accept": "application/json"}
    if sleutel:
        koppen["Authorization"] = f"Bearer {sleutel}"
    koppen.update(extra_koppen or {})
    if schema:
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {"name": "uitleg", "strict": True, "schema": schema},
        }
    else:
        response_format = {"type": "json_object"}
    for model in modellen:
        lading = {
            "model": model,
            "messages": bericht_paren(onderwerp),
            "response_format": response_format,
            "temperature": 0.4,
            "max_tokens": 900,
        }
        verzoek = urllib.request.Request(
            url, data=json.dumps(lading).encode("utf-8"), headers=koppen, method="POST"
        )
        try:
            with urllib.request.urlopen(verzoek, timeout=timeout) as antwoord:
                ruw = json.loads(antwoord.read().decode("utf-8"))
        except urllib.error.HTTPError as fout:
            print(f"[{naam}] HTTP {fout.code} bij model {model}: {fout.read()[:300].decode('utf-8', 'ignore')}")
            continue
        except Exception as fout:
            print(f"[{naam}] {type(fout).__name__} bij model {model}: {fout}")
            continue
        keuzes = ruw.get("choices") or []
        inhoud = keuzes[0].get("message", {}).get("content") if keuzes else None
        geparseerd = json_uit_antwoord(inhoud)
        if isinstance(geparseerd, dict) and (geparseerd.get("titel") or geparseerd.get("samenvatting")):
            uit = antwoord_schoonen(geparseerd, basis)
            uit["bron"] = f"ai:{bron_voorvoegsel}{model}"
            return uit
        print(f"[{naam}] geen bruikbare JSON bij model {model}")
    return None


def vraag_lokaal(onderwerp: str) -> dict[str, Any] | None:
    return vraag_openai_compatibel(
        onderwerp,
        "lokaal",
        LOKAAL_URL,
        LOKAAL_SLEUTEL,
        LOKAAL_MODELLEN,
        LOKAAL_TIMEOUT,
        "lokaal/",
        UITLEG_SCHEMA if LOKAAL_JSON_SCHEMA else None,
    )


def vraag_grok(onderwerp: str) -> dict[str, Any] | None:
    modellen = alleen_gratis_modellen(GROK_MODELLEN)
    if not GROK_API_KEY or not modellen:
        return None
    return vraag_openai_compatibel(
        onderwerp,
        "grok",
        GROK_API_URL,
        GROK_API_KEY,
        modellen,
        GROK_TIMEOUT,
        "",
        None,
        {"HTTP-Referer": GROK_SITE_URL, "X-Title": GROK_APP_NAAM},
    )


def vraag_opencode_cli(onderwerp: str) -> dict[str, Any] | None:
    basis = database_antwoord(onderwerp)
    prompt = f"{SYSTEEM_PROMPT.strip()}\n\n{GEGEVEN_ONDERWERP.format(onderwerp=onderwerp)}"
    for model in OPENCODE_CLI_MODELLEN:
        cmd = [OPENCODE_CLI_BIN, "run", "--format", "json", "--model", model]
        if OPENCODE_CLI_PURE:
            cmd.append("--pure")
        cmd.append(prompt)
        try:
            voltooid = subprocess.run(
                cmd, capture_output=True, text=True, timeout=OPENCODE_CLI_TIMEOUT
            )
        except FileNotFoundError:
            print(f"[opencode-cli] {OPENCODE_CLI_BIN} staat niet in je PATH")
            return None
        except subprocess.TimeoutExpired:
            print(f"[opencode-cli] model {model} deed langer dan {OPENCODE_CLI_TIMEOUT:.0f}s over")
            continue
        if voltooid.returncode != 0:
            print(f"[opencode-cli] model {model} gaf code {voltooid.returncode}: {voltooid.stderr[:200].strip()}")
            continue
        tekstdelen: list[str] = []
        fout_in_evenement = False
        for regel in voltooid.stdout.splitlines():
            regel = regel.strip()
            if not regel:
                continue
            try:
                evenement = json.loads(regel)
            except json.JSONDecodeError:
                continue
            if not isinstance(evenement, dict):
                continue
            deel = evenement.get("part") or {}
            if evenement.get("type") == "text" and deel.get("text"):
                tekstdelen.append(deel["text"])
            elif evenement.get("type") == "step_finish":
                print(f"[opencode-cli] model {model} klaar, kosten {deel.get('cost', 0)}")
            elif evenement.get("type") == "error":
                fout_in_evenement = True
        if fout_in_evenement and not tekstdelen:
            print(f"[opencode-cli] model {model} gaf een foutgebeurtenis")
            continue
        geparseerd = json_uit_antwoord("".join(tekstdelen))
        if isinstance(geparseerd, dict) and (geparseerd.get("titel") or geparseerd.get("samenvatting")):
            uit = antwoord_schoonen(geparseerd, basis)
            uit["bron"] = f"ai:{model}"
            return uit
        print(f"[opencode-cli] geen bruikbare JSON bij model {model}")
    return None


def ping_opencode_cli() -> bool:
    try:
        voltooid = subprocess.run(
            [OPENCODE_CLI_BIN, "--version"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        return False
    return voltooid.returncode == 0


def ping_lokaal() -> bool:
    verzoek = urllib.request.Request(
        f"{LOKAAL_BASIS}/v1/models", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(verzoek, timeout=3) as antwoord:
            antwoord.read()
        return True
    except Exception:
        return False


def ping_opencode() -> bool:
    try:
        verzoek = urllib.request.Request(f"{OPENCODE_URL}/session", headers={"Accept": "application/json"})
        with urllib.request.urlopen(verzoek, timeout=2.0) as antwoord:
            return bool(json.loads(antwoord.read().decode("utf-8")) or True)
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


PING_CACHE: dict[str, tuple[float, bool]] = {}


def ping_cache(naam: str, functie) -> bool:
    nu = time.monotonic()
    oud = PING_CACHE.get(naam)
    if oud and nu - oud[0] < 30:
        return oud[1]
    uitkomst = bool(functie())
    PING_CACHE[naam] = (nu, uitkomst)
    return uitkomst


@app.get("/api/health")
def health() -> dict[str, Any]:
    gratis_modellen = alleen_gratis_modellen(GROK_MODELLEN)
    bereikbaar = {
        "lokaal": ping_cache("lokaal", ping_lokaal),
        "opencode": ping_cache("opencode", ping_opencode),
        "opencode-cli": ping_cache("opencode-cli", ping_opencode_cli),
        "grok": grok_beschikbaar(),
    }
    volgorde = [p for p in AI_PROVIDERS if bereikbaar.get(p)]
    if volgorde[:1] == ["opencode-cli"]:
        let_op = (
            f"Opencode draait lokaal met {', '.join(OPENCODE_CLI_MODELLEN)}; "
            "reken op 20 tot 30 seconden per uitleg."
        )
    elif volgorde[:1] == ["opencode"]:
        let_op = "Opencode staat aan (space-bunny-free); een volledige uitleg duurt ongeveer 30 seconden."
    elif volgorde[:1] == ["grok"]:
        let_op = f"Grok (gratis via OpenRouter): {len(gratis_modellen)} gratis modellen, 20 verzoeken per minuut."
    elif volgorde[:1] == ["lokaal"]:
        let_op = "Je eigen lokale model draait; snel, gratis en volledig offline."
    else:
        let_op = "Geen AI bereikbaar: de app werkt volledig op de ingebouwde database."
    return {
        "status": "ok",
        "actieve_ai": volgorde[0] if volgorde else "database",
        "volgorde": volgorde,
        "lokaal": {
            "bereikbaar": bereikbaar["lokaal"],
            "url": LOKAAL_URL,
            "modellen": LOKAAL_MODELLEN,
            "kosten": "0,00",
        },
        "opencode": {
            "bereikbaar": bereikbaar["opencode"],
            "url": OPENCODE_URL,
            "modellen": OPENCODE_MODELLEN,
            "kosten": "0,00",
        },
        "opencode_cli": {
            "bereikbaar": bereikbaar["opencode-cli"],
            "programma": OPENCODE_CLI_BIN,
            "modellen": OPENCODE_CLI_MODELLEN,
            "kosten": "0,00",
        },
        "grok": {
            "beschikbaar": bereikbaar["grok"],
            "modellen": gratis_modellen,
            "geweigerde_modellen": [m for m in GROK_MODELLEN if m not in gratis_modellen],
            "alleen_gratis": True,
            "api": GROK_API_URL,
            "kosten": "0,00",
        },
        "database_onderwerpen": sorted(FALLBACK.keys()),
        "let_op": let_op,
    }


@app.post("/api/uitleg", response_model=Uitleg)
def uitleg(vraag: UitlegVraag) -> Uitleg:
    onderwerp = (vraag.onderwerp or "").strip()
    if not onderwerp:
        return Uitleg(**database_antwoord(""))
    aanbod = {
        "lokaal": vraag_lokaal,
        "opencode": vraag_opencode,
        "opencode-cli": vraag_opencode_cli,
        "grok": vraag_grok,
    }
    for naam in AI_PROVIDERS:
        provider = aanbod.get(naam)
        if not provider:
            continue
        ai_antwoord = provider(onderwerp)
        if ai_antwoord:
            return Uitleg(**ai_antwoord)
    return Uitleg(**database_antwoord(onderwerp))


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(HTML_PAGINA)


HTML_PAGINA = r"""<!DOCTYPE html>
<html lang="nl" class="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HAVO 3 Wiskunde &mdash; Jip &amp; Janneke</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = { darkMode: 'class' };
document.documentElement.classList.add('dark');
</script>
<script src="https://unpkg.com/function-plot/dist/function-plot.js"></script>
<style>
  body { font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif; }
  .kaart { background-color: rgb(30 41 59); border: 1px solid rgb(51 65 85); border-radius: 1rem; }
  .knop-optie { transition: all .15s ease; }
  .knop-optie:hover:not(:disabled) { transform: translateY(-1px); border-color: rgb(252 211 77); }
  input[type="text"] { outline: none; }
</style>
</head>
<body class="min-h-screen bg-slate-900 text-slate-100">

<div class="mx-auto max-w-5xl px-4 py-8 sm:py-12">

  <header class="mb-8">
    <p class="text-sm font-semibold uppercase tracking-widest text-amber-400">HAVO 3 &middot; Wiskunde B</p>
    <h1 class="mt-1 text-3xl font-bold text-white sm:text-4xl">Leg het uit in Jip-en-Janneketaal</h1>
    <p class="mt-3 max-w-2xl text-slate-400">
      Typ een wiskunde-onderwerp en je krijgt een uitleg, een stappenplan, een grafiek en een oefensom.
      De uitleg komt van opencode, van je eigen lokale model of van gratis Grok, in elk geval zonder kosten.
      Lukt het niet, dan neemt de ingebouwde database het over en blijft alles gewoon werken.
    </p>
    <div id="bron-badge" class="mt-4 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-400">
      <span id="wiel" class="inline-block h-2 w-2 rounded-full bg-slate-500"></span>
      <span id="bron-tekst">klaar</span>
    </div>
  </header>

  <form id="formulier" class="kaart p-4 sm:p-5">
    <div class="flex flex-col gap-3 sm:flex-row">
      <input id="onderwerp" type="text" autocomplete="off" placeholder="Bijv. parabolen, of: wat is SOS-CAST-OA?"
             class="w-full rounded-lg border border-slate-600 bg-slate-900 px-4 py-3 text-slate-100 placeholder-slate-500 focus:border-amber-400" />
      <button type="submit" id="knop"
              class="shrink-0 rounded-lg bg-amber-400 px-6 py-3 font-semibold text-slate-900 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-50">
        Leg uit
      </button>
    </div>
    <div class="mt-4 flex flex-wrap gap-2">
      <span class="self-center text-xs uppercase tracking-wider text-slate-500">Snel:</span>
      <button type="button" data-onderwerp="Parabolen"
              class="snelkoppeling rounded-full border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:border-amber-400 hover:text-amber-300">Parabolen</button>
      <button type="button" data-onderwerp="SOSCASTOA"
              class="snelkoppeling rounded-full border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:border-amber-400 hover:text-amber-300">SOSCASTOA</button>
      <button type="button" data-onderwerp="Product-som methode"
              class="snelkoppeling rounded-full border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:border-amber-400 hover:text-amber-300">Product-som methode</button>
      <button type="button" data-onderwerp="Pythagoras in 3D"
              class="snelkoppeling rounded-full border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:border-amber-400 hover:text-amber-300">Pythagoras in 3D</button>
    </div>
  </form>

  <div id="fout" class="mt-4 hidden rounded-lg border border-red-800 bg-red-950/60 px-4 py-3 text-sm text-red-300"></div>

  <div id="laden" class="mt-6 hidden space-y-3" aria-live="polite">
    <div class="kaart h-24 animate-pulse"></div>
    <div class="kaart h-40 animate-pulse"></div>
  </div>

  <main id="resultaat" class="mt-6 hidden space-y-6">

    <section class="kaart p-6">
      <h2 id="titel" class="text-2xl font-bold text-white"></h2>
      <p id="samenvatting" class="mt-3 text-lg text-slate-200"></p>
      <div class="mt-4 rounded-lg border-l-4 border-amber-400 bg-slate-900/60 p-4">
        <p class="text-xs font-semibold uppercase tracking-wider text-amber-400">Ezelsbruggetje</p>
        <p id="ezelsbruggetje" class="mt-1 text-slate-200"></p>
      </div>
    </section>

    <section class="kaart p-6">
      <h3 class="text-lg font-semibold text-white">Waar wordt dit voor gebruikt?</h3>
      <p id="praktijk" class="mt-2 text-slate-300"></p>
    </section>

    <section class="kaart p-6">
      <h3 class="text-lg font-semibold text-white">Stappenplan</h3>
      <ol id="stappen" class="mt-3 space-y-2"></ol>
    </section>

    <section class="kaart p-6">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h3 class="text-lg font-semibold text-white">Grafiek</h3>
        <p class="text-sm text-slate-400">formule: <span id="formule" class="font-mono text-amber-300"></span></p>
      </div>
      <div id="grafiek" class="mt-3 h-72 w-full overflow-hidden rounded-lg bg-slate-900"></div>
      <p id="grafiek-fout" class="mt-2 hidden text-sm text-slate-400"></p>
    </section>

    <section class="kaart border-amber-500/40 p-6">
      <h3 class="text-lg font-semibold text-amber-300">Oefensom</h3>
      <p id="vraag" class="mt-2 text-slate-100"></p>
      <div id="opties" class="mt-4 grid gap-3 sm:grid-cols-2"></div>
      <div id="feedback" class="mt-4 hidden rounded-lg p-4 text-sm"></div>
      <button type="button" id="opnieuw"
              class="mt-4 hidden rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 transition hover:border-amber-400 hover:text-amber-300">
        Opnieuw proberen
      </button>
    </section>

    <section class="kaart border-red-900/60 p-6">
      <h3 class="text-lg font-semibold text-red-300">Veelgemaakte fout</h3>
      <p id="foutje" class="mt-2 text-slate-300"></p>
    </section>

  </main>

</div>

<script>
const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];
const $ = (id) => document.getElementById(id);
let huidigeAntwoord = null;
let laatsteAntwoord = null;

function zetBron(tekst, kleur) {
  $('bron-tekst').textContent = tekst;
  $('wiel').className = 'inline-block h-2 w-2 rounded-full ' + kleur;
}

async function vraagUitleg(onderwerp) {
  $('fout').classList.add('hidden');
  $('resultaat').classList.add('hidden');
  $('laden').classList.remove('hidden');
  $('knop').disabled = true;
  zetBron('bezig met denken...', 'bg-amber-400 animate-pulse');
  try {
    const reactie = await fetch('/api/uitleg', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ onderwerp: onderwerp })
    });
    if (!reactie.ok) throw new Error('HTTP ' + reactie.status);
    const data = await reactie.json();
    toon(data);
    laatsteAntwoord = data;
    if (data.bron && data.bron.indexOf('ai:') === 0) {
      zetBron('AI: ' + data.bron.slice(3) + ' \u00b7 0,00', 'bg-emerald-400');
    } else {
      zetBron('antwoord uit de ingebouwde database \u00b7 0,00', 'bg-sky-400');
    }
  } catch (e) {
    $('fout').textContent = 'Kon geen antwoord ophalen: ' + e.message + ' Probeer het nog eens.';
    $('fout').classList.remove('hidden');
    zetBron('backend niet bereikbaar', 'bg-red-400');
  } finally {
    $('laden').classList.add('hidden');
    $('knop').disabled = false;
  }
}

function toon(data) {
  huidigeAntwoord = data.oefensom;
  $('titel').textContent = data.titel;
  $('samenvatting').textContent = data.samenvatting;
  $('ezelsbruggetje').textContent = data.ezelsbruggetje;
  $('praktijk').textContent = data.praktijk_voorbeeld;
  $('foutje').textContent = data.veelgemaakte_fout;
  $('vraag').textContent = data.oefensom.vraag;
  $('formule').textContent = 'y = ' + data.grafiek_formule;

  const lijst = $('stappen');
  lijst.innerHTML = '';
  data.stappenplan.forEach((stap) => {
    const li = document.createElement('li');
    li.className = 'flex gap-3 rounded-lg bg-slate-900/60 px-3 py-2 text-slate-200';
    li.textContent = stap;
    lijst.appendChild(li);
  });

  const opties = $('opties');
  opties.innerHTML = '';
  data.oefensom.opties.forEach((tekst, i) => {
    const knop = document.createElement('button');
    knop.type = 'button';
    knop.className = 'knop-optie flex items-start gap-3 rounded-lg border border-slate-600 bg-slate-900 px-4 py-3 text-left text-slate-100';
    const label = document.createElement('span');
    label.className = 'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-slate-700 text-xs font-bold text-amber-300';
    label.textContent = LETTERS[i] || (i + 1);
    const inhoud = document.createElement('span');
    inhoud.textContent = tekst;
    knop.appendChild(label);
    knop.appendChild(inhoud);
    knop.addEventListener('click', () => beantwoord(i));
    opties.appendChild(knop);
  });

  $('feedback').classList.add('hidden');
  $('opnieuw').classList.add('hidden');
  $('resultaat').classList.remove('hidden');
  tekenGrafiek(data.grafiek_formule);
  $('resultaat').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function tekenGrafiek(formule) {
  const doel = $('grafiek');
  const fout = $('grafiek-fout');
  doel.innerHTML = '';
  fout.classList.add('hidden');
  if (typeof functionPlot === 'undefined') {
    fout.textContent = 'De grafiekbibliotheek kon niet worden geladen (geen internet?). De formule is: y = ' + formule;
    fout.classList.remove('hidden');
    return;
  }
  try {
    functionPlot({
      target: doel,
      data: [{
        fn: formule,
        graphColor: '#fbbf24',
        fill: 'rgba(251, 191, 36, 0.10)'
      }],
      gridColor: '#334155',
      xAxisColor: '#94a3b8',
      yAxisColor: '#94a3b8',
      dataColor: '#fbbf24',
      cursor: { show: true, color: '#fbbf24' },
      xAxis: { domain: [-10, 10], label: 'x' },
      yAxis: { domain: [-10, 10], label: 'y' },
      legend: { show: false },
      evaluate: { samples: 400 },
      width: doel.clientWidth || 640,
      height: 288
    });
  } catch (e) {
    fout.textContent = 'Kon de formule y = ' + formule + ' niet tekenen. Kijk even na in je boek.';
    fout.classList.remove('hidden');
  }
}

function beantwoord(index) {
  if (!huidigeAntwoord) return;
  const goed = index === huidigeAntwoord.correct_index;
  const knoppen = Array.from($('opties').children);
  knoppen.forEach((knop, i) => {
    knop.disabled = true;
    if (i === huidigeAntwoord.correct_index) {
      knop.className = 'knop-optie flex items-start gap-3 rounded-lg border-2 border-emerald-500 bg-emerald-500/20 px-4 py-3 text-left text-emerald-100';
    } else if (i === index) {
      knop.className = 'knop-optie flex items-start gap-3 rounded-lg border-2 border-red-500 bg-red-500/20 px-4 py-3 text-left text-red-200';
    } else {
      knop.className = 'knop-optie flex items-start gap-3 rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-3 text-left text-slate-400 opacity-60';
    }
  });

  const panel = $('feedback');
  panel.className = goed
    ? 'mt-4 rounded-lg border border-emerald-700 bg-emerald-950/60 p-4 text-sm text-emerald-200'
    : 'mt-4 rounded-lg border border-red-800 bg-red-950/60 p-4 text-sm text-red-200';
  panel.innerHTML = '';
  const kop = document.createElement('p');
  kop.className = 'font-bold';
  kop.textContent = goed ? 'Goed gedaan!' : 'Niet helemaal: het juiste antwoord is ' + (LETTERS[huidigeAntwoord.correct_index] || '?') + '.';
  const uitleg = document.createElement('p');
  uitleg.className = 'mt-2';
  uitleg.textContent = huidigeAntwoord.uitleg;
  panel.appendChild(kop);
  panel.appendChild(uitleg);
  panel.classList.remove('hidden');

  $('opnieuw').classList.remove('hidden');
}

$('opnieuw').addEventListener('click', () => {
  if (laatsteAntwoord) toon(laatsteAntwoord);
});

document.querySelectorAll('.snelkoppeling').forEach((knop) => {
  knop.addEventListener('click', () => {
    $('onderwerp').value = knop.dataset.onderwerp;
    vraagUitleg(knop.dataset.onderwerp);
  });
});

$('formulier').addEventListener('submit', (e) => {
  e.preventDefault();
  const waarde = $('onderwerp').value.trim();
  if (waarde) vraagUitleg(waarde);
});

window.addEventListener('resize', () => {
  const formule = $('formule').textContent.replace('y = ', '');
  if (formule && !$('resultaat').classList.contains('hidden')) tekenGrafiek(formule);
});

const NAMEN = {
  'lokaal': 'jouw eigen lokale model',
  'opencode': 'opencode (space-bunny-free)',
  'opencode-cli': 'opencode (big-pickle)',
  'grok': 'gratis Grok',
  'database': 'alleen de ingebouwde database'
};

fetch('/api/health').then((r) => r.json()).then((d) => {
  if (d.volgorde && d.volgorde.length) {
    zetBron(NAMEN[d.volgorde[0]] + ' \u00b7 0,00', 'bg-emerald-400');
  } else {
    zetBron(NAMEN.database + ' \u00b7 0,00', 'bg-sky-400');
  }
}).catch(() => zetBron(NAMEN.database + ' \u00b7 0,00', 'bg-sky-400'));
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    print("=" * 68)
    print("HAVO 3 Wiskunde - nooit een cent, wel een echte uitleg")
    print("Open lokaal:   http://127.0.0.1:8000")
    print("Open via Tailscale: http://<jouw-tailscale-ip>:8000")
    for naam, bereikbaar, regels in (
        (
            "lokaal (jouw eigen model)",
            ping_lokaal(),
            [f"      model: {LOKAAL_MODELLEN[0]}", f"      endpoint: {LOKAAL_URL}"],
        ),
        (
            "opencode-cli (los proces)",
            ping_opencode_cli(),
            [
                f"      programma: {OPENCODE_CLI_BIN}",
                f"      modellen: {', '.join(OPENCODE_CLI_MODELLEN)}",
                "      big-pickle werkt alleen via deze route.",
            ],
        ),
        (
            "opencode (HTTP-server)",
            ping_opencode(),
            [
                f"      endpoint: {OPENCODE_URL}",
                f"      modellen: {', '.join(OPENCODE_MODELLEN)}",
                "      big-pickle weigert HTTP (403) en wordt hier overgeslagen.",
            ],
        ),
    ):
        print(f"{naam}: {'AAN' if bereikbaar else 'UIT'}")
        if bereikbaar:
            for regel in regels:
                print(regel)
    if grok_beschikbaar():
        print(f"grok (gratis via OpenRouter): AAN")
        print(f"      gratis modellen: {', '.join(alleen_gratis_modellen(GROK_MODELLEN))}")
    else:
        print("grok (gratis via OpenRouter): UIT - zet GROK_API_KEY=or-v1-... voor gratis Grok.")
    print(f"Volgorde: {' > '.join(AI_PROVIDERS)} > database")
    print("Kosten: 0,00 - er wordt nooit een betaald model aangeroepen.")
    geweigerd = [m for m in GROK_MODELLEN_RAW if m not in alleen_gratis_modellen([m])]
    if geweigerd:
        print(f"Gewijgerd (niet gratis): {', '.join(geweigerd)}")
    print("=" * 68)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")