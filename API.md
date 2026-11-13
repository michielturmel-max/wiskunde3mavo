# API

De app praat met de browser via drie endpoints. Handig als je er zelf iets aan wilt hangen,
of om te controleren wat er onder water gebeurt.

## `GET /`

De hele pagina. Tailwind, Function Plot en de quiz zitten inline in het antwoord, dus er
wordt niets van je eigen server geladen behalve deze pagina zelf.

## `GET /api/health`

Zegt welke providers er op dat moment echt bereikbaar zijn.

```bash
curl -s localhost:8000/api/health
```

```json
{
  "status": "ok",
  "actieve_ai": "opencode-cli",
  "volgorde": ["opencode-cli", "grok"],
  "lokaal":      { "bereikbaar": false, "url": "...", "modellen": ["qwen2.5:3b"], "kosten": "0,00" },
  "opencode":    { "bereikbaar": false, "url": "...", "modellen": ["space-bunny-free", "big-pickle"], "kosten": "0,00" },
  "opencode_cli":{ "bereikbaar": true, "programma": "opencode", "modellen": ["opencode/big-pickle", "opencode/space-bunny-free"], "kosten": "0,00" },
  "grok":        { "beschikbaar": false, "modellen": ["x-ai/grok-4-fast:free"], "geweigerde_modellen": [], "alleen_gratis": true, "api": "...", "kosten": "0,00" },
  "database_onderwerpen": ["parabolen", "product-som", "pythagoras3d", "soscastoa"],
  "let_op": "Opencode draait lokaal met opencode/big-pickle; reken op 20 tot 30 seconden per uitleg."
}
```

`actieve_ai` is `database` als er geen provider antwoord geeft. De pingen worden 30 seconden
gecached, zodat de pagina snel blijft laden.

## `POST /api/uitleg`

```bash
curl -s -X POST localhost:8000/api/uitleg \
  -H 'Content-Type: application/json' \
  -d '{"onderwerp":"parabolen"}'
```

Vraag is `{ "onderwerp": string }`. Een leeg onderwerp geeft het algemene database-antwoord.

Het antwoord is het volledige uitleg-object uit [MODELLEN.md](MODELLEN.md), plus:

| Veld | Betekenis |
|---|---|
| `bron` | `ai:opencode/big-pickle`, `ai:x-ai/grok-4-fast:free`, `ai:lokaal/qwen2.5:3b` of `database` |

De acht sleutels uit het JSON-schema zijn altijd gevuld. Wat het model te kort of te
onbruikbaar vindt, wordt aangevuld uit de ingebouwde database, dus de browser hoeft nooit
te controleren op lege velden.

## Tijdsduur

`POST /api/uitleg` kan even duren, omdat de eerste provider geprobeerd wordt:

| Eerste provider | Verwachte duur van de HTTP-aanroep |
|---|---|
| `grok` | 2–4 s |
| `opencode` | circa 30 s |
| `opencode-cli` met big-pickle | 25–45 s |
| `lokaal` | 3–15 s |

Het is een gewone synchrone aanroep, geen job met een poll-endpoint. Zet
`OPENCODE_CLI_TIMEOUT` omlaag als je sneller wilt terugvallen op een volgende provider.

## Waarom er geen OpenAI-compatibele uitgang voor is

De app is makkelijk uit te breiden, maar er zit bewust geen `/v1/chat/completions` op
deze server. De bronnen zijn OpenAI-compatibel (`grok` en `lokaal` spreken die taal), dus
als je ooit meer dan één client hebt is dat een uitbreiding van een uur werk. Voor nu is één
scherm en één JSON-contract minder om te onderhouden.