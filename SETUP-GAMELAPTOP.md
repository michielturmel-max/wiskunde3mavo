# De laptop opzetten: Omarchy + NVIDIA + big-pickle

Deze gids neemt je mee naar een schone Omarchy-laptop met een GTX 1050 tot een werkende
wiskunde-app met big-pickle. Alles is getest of nagelopen op een bestaande Omarchy 4.0.4;
de commando's zijn overgenomen uit de installatiescripts van Omarchy zelf, dus ze kloppen
met jouw versie.

Tijdens het schrijven is de laptop niet beschikbaar. Wat hieronder staat komt uit de
scripts op deze machine, uit de NVIDIA-documentatie en uit de CUDA-release-notes. De
één plek waar een meting ontbreekt, is het snelheidscijfer van een lokaal 3B-model op de
1050; daar staat expliciet hoe je het zelf meet.

## 0. Wat je nodig hebt

- De laptop met GTX 1050 (6 GB) en 16 GB RAM.
- Een geïnstalleerde Omarchy. Zo niet, dan via de officiële installatie; de rest van deze
  gids gaat ervan uit dat Hyprland al draait.
- Tijdens het installeren moet de laptop aan de lader.

## 1. NVIDIA-driver: Omarchy regelt het, en het kiest goed

Omarchy detecteert zelf of je NVIDIA-kaart GSP-firmware heeft. Een GTX 1050 is Pascal en
heeft die **niet**, dus Omarchy installeert bewust de `nvidia-580xx`-reeks in plaats van
`nvidia-open-dkms`:

```
$ cat /usr/share/omarchy/install/hardware/nvidia.sh
```

Dat is precies de juiste keuze. NVIDIA heeft aangekondigd dat de 580-branch de laatste is
die Maxwell, Pascal en Volta ondersteunt, tot ongeveer midden 2028. Je kaart blijft dus
gewoon werken, alleen heeft hij geen toekomst buiten die datum.

Tijdens de installatie draait de kaart nog op `nouveau`, en dan is de muisaanwijzer vaak
onzichtbaar onder Hyprland. Omarchy lost dat zelf op door `no_hardware_cursors` aan je
`looknfeel.lua` toe te voegen. Laat dat staan als de aanwijzer na de installatie nog
invisible is; met de echte driver kan het weg.

Controleren of het goed is:

```bash
lspci -k | grep -A2 'VGA compatible controller'   # moet "nvidia" zeggen
nvidia-smi                                        # moet je kaart en driver tonen
```

## 2. opencode installeren

opencode staat niet in de standaardpakketten van Omarchy, maar wel in de AUR:

```bash
omarchy pkg aur add opencode-bin
opencode --version
```

## 3. Inloggen bij opencode

big-pickle is geen gratis model dat je zomaar meegeleverd krijgt; je logt één keer in met
je opencode-account:

```bash
opencode auth login
```

Kies je provider en rond de browserflow af. Controleer daarna of big-pickle praat:

```bash
opencode run --model opencode/big-pickle "Zeg alleen: hallo"
opencode models
```

Doet dat niets, dan staat je account big-pickle nog niet toe. Dat is een accountkwestie,
geen installatieprobleem; het model is dan niet beschikbaar.

### Let op de modelnaam

Het model moet altijd als `provider/model` geschreven worden. `opencode run --model
big-pickle` faalt met een lege foutmelding, terwijl `--model opencode/big-pickle` werkt.
Dat is de meest voorkomende reden dat big-pickle "niet doet".

## 4. De app starten

Kopieer deze map naar de laptop en start hem:

```bash
cd ~/wiskunde3mavo
omarchy pkg add python-pip        # of: pacman -S python-pip
pip install fastapi uvicorn      # mag in een venv, zie onderaan
python main.py
```

Standaard probeert de app `opencode-cli` (big-pickle) en daarna Grok. Dat is bewust zo:
big-pickle is het enige model dat via de app nog werkt, de HTTP-server van opencode
weigert het met een 403. Wil je big-pickle helemaal alleen, dan:

```bash
AI_PROVIDERS=opencode-cli python main.py
```

Verwacht 25 tot 45 seconden per uitleg. Dat is de prijs van big-pickle op een oude laptop
en het is de reden dat `main.py` er altijd een databasefallback in heeft staan.

## 5. Opencode ook als HTTP-server (optioneel)

Handig als je de app vanaf je grote pc wilt draaien en de laptop alleen de rekenaar is.
Let op: over HTTP werkt alleen `space-bunny-free`, big-pickle wordt met een 403 geweigerd.

```bash
opencode serve --port 4196 --hostname 127.0.0.1      # lokaal
opencode serve --port 4196 --hostname 0.0.0.0        # of vanaf je andere pc
```

Dan op de andere pc:

```bash
AI_PROVIDERS=opencode python main.py
```

`opencode serve` zonder wachtwoord is prima op `127.0.0.1`. Bind je hem op `0.0.0.0`, zet
dan `OPENCODE_SERVER_PASSWORD`, anders kan iedereen in je netwerk meelezen.

## 6. Een eigen lokaal model (de 3B-optie)

Als je liever iets hebt dat in een paar seconden antwoordt en helemaal offline draait,
zet dan llama.cpp of Ollama op die 1050. In 6 GB VRAM past comfortabel alles tot ongeveer
4 miljard parameters in Q4, dus je kunt ook groter dan 3B.

### Het CUDA-valkuil, en waarom je Vulkan wilt

CUDA 13 heeft de offline compilatie voor Maxwell, Pascal en Volta **verwijderd**. Een
GTX 1050 is Pascal. Kort gezegd:

- bouw je zelf llama.cpp met CUDA, dan werkt het alleen nog met CUDA 12.x;
- gebruik je een binary die met CUDA 13 is gebouwd, dan wordt je kaart niet eens gezien.

Vulkan heeft die beperking niet. NVIDIA levert de Vulkan-driver mee met `nvidia-utils`, dus
na de installatie van stap 1 werkt Vulkan gewoon. Daarom raadt dit document Vulkan aan.

### Optie A: llama.cpp uit de Arch-repositories

```bash
omarchy pkg add llama-cpp
pacman -Ql llama-cpp | grep bin/          # controleer welke binaries je krijgt
```

Het pakket heet `llama-cpp` (met een koppelteken), niet `llama.cpp`. Model downloaden:

```bash
huggingface-cli download bartowski/Qwen2.5-3B-Instruct-GGUF Qwen2.5-3B-Instruct-Q4_K_M.gguf --local-dir ~/modellen
```

Draaien met Vulkan:

```bash
llama-server --model ~/modellen/Qwen2.5-3B-Instruct-Q4_K_M.gguf \
             --gpu Vulkan --host 127.0.0.1 --port 8080 \
             --alias qwen2.5-3b --jinja
```

Controleer of de kaart echt gebruikt wordt, anders draai je ongemerkt op de processor:

```bash
llama-server --list-devices
```

### Optie B: Ollama

```bash
omarchy pkg add ollama-vulkan       # de Vulkan-versie, dus geschikt voor Pascal
systemctl enable --now ollama
ollama pull qwen2.5:3b
```

### De app aan het lokale model koppelen

```bash
AI_PROVIDERS=lokaal python main.py
```

Standaard verwacht de app `http://127.0.0.1:8080/v1/chat/completions` met modelnaam
`qwen2.5:3b`, wat precies klopt voor Ollama. Met llama-server stuur je de modelnaam uit de
`--alias`, of laat hem staan: llama-server negeert die naam als er één model draait.

### Zelf meten hoe snel het is

Dit is het ene getal dat ik niet voor je kan uitrekenen, dus meet het zelf:

```bash
time curl -s localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"hoi"}],"max_tokens":100}' \
  | tail -c 300
```

Onder de 10 seconden voor 100 woorden is prima voor deze app. Doet hij er 30 seconden
over, draai dan liever op `AI_PROVIDERS=opencode-cli,grok`.

## 7. Als server draaien zonder terminal

Wil je dat de app automatisch mee start, dan is een systemd-unit het handigst:

```ini
# /etc/systemd/system/wiskunde3mavo.service
[Unit]
Description=HAVO 3 Wiskunde
After=network-online.target

[Service]
Type=simple
User=%i
WorkingDirectory=/home/%i/wiskunde3mavo
Environment=AI_PROVIDERS=opencode-cli
ExecStart=/home/%i/wiskunde3mavo/.venv/bin/python main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Aanmaken met `sudo systemctl enable --now wiskunde3mavo.service` (vervang `%i` door je
eigen gebruikersnaam, of laat de `User=%i`-regel weg als je de unit op jouw naam zet).

Vergeet niet de slaapstand uit te schakelen, anders valt de laptop in slaap midden in een
berekening: in GNOME/Omarchy via instellingen, of voor alle gebruikers met
`sudo systemctl mask sleep.target suspend.target`.

## 8. Volgorde van wat je als eerste doet

1. `omarchy pkg aur add opencode-bin`, daarna `opencode auth login`.
2. `opencode run --model opencode/big-pickle "Zeg alleen: hallo"` — werkt het, dan is stap 3 ook goed.
3. `pip install fastapi uvicorn` en `python main.py`.
4. Typ "parabolen" in de browser. Reken op een halve minuut.
5. Pas daarna pas `AI_PROVIDERS` aan als je iets anders wilt dan big-pickle eerst.

## Wat er in deze gids niet is nagelopen

- De snelheid van big-pickle op de 1050. Hier gemeten: 24 tot 45 seconden op een moderne
  pc met een andere internetverbinding. Op de laptop kan dat afwijken; de app geeft het
  altijd in de terminal door.
- Of jouw opencode-account big-pickle mag gebruiken. Dat staat los van alles hierboven.
- Of de 1050 in jouw laptop precies dezelfde chip heeft. De 6 GB-versie is de goede; er
  bestaan ook 3 GB-uitvoeringen met dezelfde chip, en dan wordt het krapper.