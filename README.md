# Puffy Pal: web MVP

An AI monkey friend that helps children aged 4–12 practise English by talking. The web app follows the Figma design (page 2).

```
docs/index.html   web app (GitHub Pages serves this folder)
docs/monkey.png   toy image exported from Figma
server/app.py     backend: /api/chat (LLM), /api/tts (Kokoro voice), /api/health
server/check.py   server test: speed, clean output, safety, security
server/e2e.mjs    browser test: real page + fake microphone, every main flow
```

## Run on the laptop (fastest: RTX 4060 + toy-brain + Kokoro)

```bash
./start.sh            # starts the AI server and opens the live site (it talks to this laptop)
./start.sh local      # same, but opens http://localhost:5000
./start.sh public     # public https link for phones / other networks (Cloudflare quick tunnel)
python3 server/check.py   # server: speed + safety + security + voice round trip
node server/e2e.mjs       # the real page in headless Chrome with a fake mic (12 user flows)
```

While the laptop runs the server, https://nepes2008j-max.github.io/puffy-pal/ talks on this laptop.
Speech: local Whisper (mic) → toy-brain (streamed) → Kokoro on the GPU, about 1 s from the child to the first sound.
See [PLAN.md](PLAN.md) for what's done and what's next.

Servers without a GPU (e.g. PythonAnywhere) use Groq's cloud Whisper when STT_URL is set, otherwise the browser's own speech recognition.

## Put it online 24/7

**1. Web app → GitHub Pages**
Push this folder to a GitHub repo. Then go to Settings → Pages → Source: `main` branch, `/docs` folder.
The site will be at `https://<you>.github.io/<repo>/`.

**2. Everything 24/7 → PythonAnywhere** (app + AI at `https://<username>.pythonanywhere.com`)
1. Groq: make a free API key at console.groq.com → API Keys.
2. PythonAnywhere free accounts can only reach approved sites. In a Bash console run
   `curl -s -o /dev/null -w "%{http_code}\n" https://api.groq.com/openai/v1/models`. `401` = reachable (good); `403`/error = blocked, so you need the $5 plan.
3. Files tab → upload `deploy/puffy_pal_pythonanywhere.zip` to your home folder, then in a Bash console: `unzip -o puffy_pal_pythonanywhere.zip`
4. Web tab → Add a new web app → Manual configuration → Python 3.10 or newer.
5. Click the "WSGI configuration file" link, replace everything with `deploy/pythonanywhere_wsgi.py`, put in your username + Groq key, Save, then Reload.
6. Open `https://<username>.pythonanywhere.com` → Toy page should show AI brain: Online.

There: the brain is Groq (Qwen3), the ears are Groq's cloud Whisper, the voice is the phone's own voice (no GPU for Kokoro).
The free plan's web app stops after 3 months unless you click "Run until 3 months from today" on the Web tab.

## The toy brain

The prompt lives in `system_prompt()` in `server/app.py`, not in the Ollama Modelfile, so the same prompt works on Ollama and Groq.
It adapts to the child's name, age, hobbies, home language, English level, learning focus and the Gentle Help setting.
Code enforces these rules regardless of the model:
- Qwen "thinking" is turned off (`reasoning_effort: none`).
- Replies are capped at 3 sentences (6 for stories).
- Emoji and markdown are removed before the voice reads them.
- A keyword safety filter (a stopgap until a real moderation model).
