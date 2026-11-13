# Modellen: snelheid, kosten en wanneer je wat kiest

Alle tijden hieronder zijn gemeten, niet geschat. De metingen van big-pickle en
space-bunny-free zijn gedaan op een moderne pc met de laptop nog uit; op de laptop zelf
kan het afwijken. De database en de JSON-verwerking zijn machine-onafhankelijk.

## Gemeten tijden

| Route | Model | Volledige uitleg | Kosten | Opmerking |
|---|---|---|---|---|
| `opencode-cli` | `opencode/big-pickle` | 24 s – 45 s | 0 | de enige route waarin big-pickle werkt |
| `opencode` (HTTP) | `space-bunny-free` | 29 s | 0 | echte json_schema-afdwinging |
| `grok` | `x-ai/grok-4-fast:free` | 2–4 s | 0 | 20 verzoeken per minuut, 50 per dag |
| `lokaal` | Qwen2.5-3B Q4 op een 1050 | niet gemeten | 0 | zie onder, meet het zelf |
| database | — | 0,08 s | 0 | altijd beschikbaar |

Het verschil tussen 3 seconden en 30 seconden is het verschil tussen iets dat een leerling
gebruikt en iets dat ze na drie keer niet meer opent. Dat is de enige overweging die telt.

## Waarom big-pickle niet via HTTP werkt

Opencode weigert zijn eigen gratis laag zodra je de HTTP-API gebruikt:

```
HTTP 403 bij model big-pickle
OpenCode's free tier can only be used from within OpenCode
```

Dat is een beleidsregel van OpenCode, geen fout in deze app. `space-bunny-free` mag
wél over HTTP en is daarom de standaard in `OPENCODE_MODELLEN`. Ook getest en afgevallen:
`grok-4-fast:free`, `gpt-5-nano:free`, `gemini-2.5-flash:free` — allemaal 403.

De omweg is de commandoregel. `opencode run --model opencode/big-pickle` doet precies wat
HTTP weigert te doen, levert geldige JSON en meldt per aanroep wat het kost:

```
[opencode-cli] model opencode/big-pickle klaar, kosten 0
tijd: 44.9s | bron: ai:opencode/big-pickle
```

## Waarom de HTTP-route toch bestaat

De HTTP-server dwingt het JSON-schema echt af: het model krijgt een grammatica en kan geen
valid JSON anders dan het gevraagde teruggeven. Via de CLI stuur je alleen een instructie
en hoop je op naleving. Dat klinkt slordig, maar `main.py` vangt het op:

- de parser zoekt het eerste JSON-object, ook als er tekst of een markdownblok omheen staat;
- het antwoord wordt door dezelfde schoonmaak gestuurd als bij Grok;
- klopt het niet, dan gaat het naar het volgende model en uiteindelijk de database.

De gemeten big-pickle-uitvoer was gewoon valide: 4 stappen, 4 opties, `correct_index` 1,
formule `x^2-4`.

## Het JSON-formaat

Elk antwoord bestaat uit deze sleutels, en `main.py` vult aan wat ontbreekt:

```json
{
  "titel": "Parabolen",
  "samenvatting": "Eén zin op leekenniveau.",
  "praktijk_voorbeeld": "Waar je dit in het echte leven tegenkomt.",
  "ezelsbruggetje": "Een onthoudregel die blijft hangen.",
  "stappenplan": ["1. ...", "2. ...", "3. ..."],
  "grafiek_formule": "x^2-4",
  "veelgemaakte_fout": "De klassieke valkuil op de toets.",
  "oefensom": {
    "vraag": "Hoeveel nulpunten heeft y = x^2 - 4?",
    "opties": ["één", "twee", "drie"],
    "correct_index": 1,
    "uitleg": "Omdat x = 2 en x = -2."
  }
}
```

Sanitisatie in het kort:

| Veld | Regel |
|---|---|
| `stappenplan` | 3 tot 5 items, elk hoogstens 120 tekens |
| `grafiek_formule` | alleen `x`, cijfers, `+ - * / ^ ( )`, `sin cos tan sqrt abs`; anders valt hij terug op de databasewaarde |
| `oefensom.opties` | 2 tot 6 opties |
| `correct_index` | moet binnen de opties vallen, anders wordt hij op 0 gezet |
| alle tekst | wordt door een seinteller gefilterd op `<script>`, `javascript:` en dergelijke |

## Als je een lokaal model op de laptop zet

Qwen2.5-3B-Instruct in Q4_K_M is mijn voorkeur voor deze taak. Waarom:

- Nederlands is een van de sterkste talen van Qwen, en dat is hier het enige dat telt;
- JSON naleven doet het model goed, wat het oefensom-gedeelte betrouwbaar maakt;
- 3 miljard parameters in Q4 is ongeveer 2 GB, dus ruim binnen 6 GB VRAM.

Alternatieven, allemaal getest beschikbaar als GGUF:

| Model | Grootte (Q4) | Wanneer |
|---|---|---|
| `bartowski/Qwen2.5-3B-Instruct-GGUF` `Q4_K_M` | ~2,0 GB | beste balans tussen snelheid en kwaliteit |
| `Qwen/Qwen3-4B-GGUF` `Qwen3-4B-Q4_K_M` | ~2,5 GB | iets slimmer in wiskunde, ook goed in Nederlands |
| Qwen2.5-7B-Instruct Q4 | ~4,7 GB | past nog in 6 GB, maar merkbaar trager |

Niet kiezen: Llama 3.2 3B (zwak in Nederlands en in JSON naleven), Phi-3.5-mini (Nederlands
is zwak, en het model is groter dan het lijkt), en alles van 1 miljard parameters of minder.

Het GPU-gebruik controleer je met `llama-server --list-devices`. Zie
[SETUP-GAMELAPTOP.md](SETUP-GAMELAPTOP.md) voor de Vulkan-vraag op een GTX 1050.

## Overzicht: welke volgorde

| Wil je | Gebruik |
|---|---|
| altijd de beste uitleg, ook als het 45 s duurt | `AI_PROVIDERS=opencode-cli,grok` |
| zo snel mogelijk, alles gratis | `AI_PROVIDERS=grok,opencode-cli` |
| volledig offline | `AI_PROVIDERS=lokaal` of `AI_PROVIDERS=` |
| niets configureren, database is prima | laat de standaard staan |

De laatste regel is de belangrijkste: als je alles op `opencode-cli` zet en big-pickle
weigert, dan ziet de leerling gewoon een uitleg uit de database en weet niemand dat er
iets mis is. Zo hoort het.