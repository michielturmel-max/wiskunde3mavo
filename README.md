# HAVO 3 Wiskunde — lokale uitleg, nul euro

Een webappje dat van elk wiskunde-onderwerp een uitleg maakt in Jip-en-Janneketaal: samenvatting,
stappenplan, een tekengbare grafiek en een oefensom met uitleg. Alles draait op je eigen computer.

De kern is één bestand: `main.py`. Er is geen database, geen docker, geen build-stap.
De ingebouwde database met vier uitgewerkte onderwerpen is altijd beschikbaar, dus de app
werkt ook als er geen enkel AI-model bereikbaar is.

## Downloaden en installeren

```bash
git clone https://github.com/michielturmel-max/wiskunde3mavo.git
cd wiskunde3mavo
pip install fastapi uvicorn      # eenmalig
python main.py                   # daarna: http://127.0.0.1:8000
```

Er is geen database, docker of build-stap nodig. De ingebouwde onderwerpen
werken zonder AI-model; wil je vrije onderwerpen, kies dan een provider met de
omgevingsvariabelen hieronder. `python main.py` opnieuw starten is genoeg om
wijzigingen te zien.

## Snel starten

```bash
pip install fastapi uvicorn      # eenmalig
python main.py                   # daarna: http://127.0.0.1:8000
```

Open dezelfde map vanuit een andere computer in je netwerk via `http://<ip-van-deze-pc>:8000`.

## Zo werkt het

Je typt een onderwerp ("parabolen", "sinus", "ontbinden in factoren"). De app stuurt dat
naar de eerste bereikbare AI-provider uit `AI_PROVIDERS`. Elk antwoord wordt nagekeken en
schoongemaakt: ongeldige formules worden vervangen, het stappenplan wordt ingekort tot 3–5
stappen, en een quiz zonder geldige antwoordopties wordt vervangen door de ingebouwde.

Antwoordt een provider niet, of doet hij er 45 seconden over, dan gaat de app automatisch
naar de volgende. Lukt het helemaal niet, dan komt het antwoord uit de ingebouwde database —
in ongeveer 80 milliseconden, dus altijd.

| Provider | Wat het is | Snelheid | Kosten |
|---|---|---|---|
| `opencode-cli` | opencode als los proces, hiermee werkt **big-pickle** | 25–45 s | 0,00 |
| `opencode` | opencode HTTP-server, alleen `space-bunny-free` werkt | ~30 s | 0,00 |
| `grok` | gratis Grok via OpenRouter, alleen `:free`-modellen | 2–4 s | 0,00 |
| `lokaal` | je eigen model via llama-server of Ollama | 3–15 s | 0,00 |
| database | vier uitgewerkte onderwerpen in `main.py` | 0,08 s | 0,00 |

Alles gemeten, zie [MODELLEN.md](MODELLEN.md).

## Instellen met omgevingsvariabelen

Alles heeft een standaardwaarde, je hoeft niets te zetten om de app te starten.

```bash
# alleen opencode met big-pickle, en niets anders
AI_PROVIDERS=opencode-cli python main.py

# big-pickle eerst, daarna gratis Grok, daarna de database
AI_PROVIDERS=opencode-cli,grok python main.py

# volledig offline, met een eigen lokaal model op poort 8080
AI_PROVIDERS=lokaal python main.py
```

| Variabele | Standaard | Betekenis |
|---|---|---|
| `AI_PROVIDERS` | `opencode-cli,grok` | volgorde waarin de AI-providers geprobeerd worden |
| `OPENCODE_CLI_BIN` | `opencode` | programma dat aangeroepen wordt |
| `OPENCODE_CLI_MODELLEN` | `opencode/big-pickle,opencode/space-bunny-free` | altijd met `provider/model` schrijven |
| `OPENCODE_CLI_TIMEOUT` | `300` | seconden voordat de app het opgeeft |
| `OPENCODE_CLI_PURE` | `1` | `0` als je plugins van opencode wilt gebruiken |
| `OPENCODE_URL` | `http://127.0.0.1:4196` | adres van `opencode serve` |
| `OPENCODE_MODELLEN` | `space-bunny-free,big-pickle` | modellen voor de HTTP-route |
| `LOKAAL_URL` | `http://127.0.0.1:8080/v1/chat/completions` | llama-server of Ollama |
| `LOKAAL_MODELLEN` | `qwen2.5:3b` | bij Ollama moet dit de echte modelnaam zijn |
| `LOKAAL_JSON_SCHEMA` | `1` | `0` als je server geen json_schema snapt |
| `GROK_API_KEY` | — | of `OPENROUTER_API_KEY`; een gratis key kost niets |
| `GROK_MODELLEN` | `x-ai/grok-4-fast:free,x-ai/grok-3-mini:free` | modellen zonder `:free` worden geweigerd |

## De kostenbelofte

Er wordt nooit een betaald model aangeroepen. Dat is niet alleen een belofte maar een
controle in de code: bij Grok worden alle modellen zonder het label `:free` weggegooid
voordat er een verzoek uitgaat, en `GROK_MODELLEN` wordt bij het opstarten geprint.
opencode-modellen draaien via je eigen opencode-account; de app print per aanroep de kosten
die opencode teruggeeft, zodat je het kunt nalezen.

## Wat er in de map zit

| Bestand | |
|---|---|
| `main.py` | de hele app: backend, HTML, JavaScript en de database |
| `README.md` | dit bestand |
| `SETUP-GAMELAPTOP.md` | stap voor stap naar de laptop met Omarchy, NVIDIA en big-pickle |
| `MODELLEN.md` | gemeten tijden, welk model je wanneer kiest, lokaal 3B-model |
| `API.md` | de vier HTTP-endpoints en het JSON-formaat |
| `tests/test_grok.py` | 14 tests: gratis-garantie, fouten, databasefallback |
| `tests/test_opencode.py` | 8 tests: opencode HTTP, JSON-parse en sessieopruiming |

## Tests draaien

```bash
python tests/test_grok.py        # de gratis-garantie en de database
AI_PROVIDERS=opencode python tests/test_opencode.py
```

Beide suites draaien volledig offline: ze vervangen de netwerklaag door een nep.
Gebruik een Python waar FastAPI geïnstalleerd is.

## Als er iets misgaat

| Wat je ziet | Wat het betekent |
|---|---|
| Badge zegt "alleen de ingebouwde database" | geen provider uit `AI_PROVIDERS` gaf antwoord; kijk in de terminal |
| badge blijft hangen op "bezig" | je provider duurt lang; zet `OPENCODE_CLI_TIMEOUT` omlaag of zet Grok ervoor |
| grafiek blijft leeg | het model gaf een formule die niet getekend kan worden; er valt automatisch terug op `x^2-4` |
| `opencode gaf geen sessie terug` | `opencode serve` draait niet of niet op `OPENCODE_URL` |

`curl localhost:8000/api/health` geeft in één oogopslag wat er werkt.