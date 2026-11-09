# Puffy Pal: web MVP

An AI monkey friend that helps children aged 4–12 practise English by talking. The web app follows the Figma design (page 2).

```
docs/index.html   web app (GitHub Pages serves this folder)
docs/monkey.png   toy image exported from Figma
server/app.py     backend: /api/chat (LLM), /api/tts (Kokoro voice), /api/health
server/check.py   smoke test: speed, clean output, safety
```

## Run on the laptop (fastest: RTX 4060 + toy-brain + Kokoro)

```bash
./start.sh            # starts the AI server and opens the live site (it talks to this laptop)
./start.sh local      # same, but opens http://localhost:5000
./start.sh public     # public https link for phones / other networks (Cloudflare quick tunnel)
python3 server/check.py   # speed + safety + voice round-trip test
```

While the laptop runs the server, https://nepes2008j-max.github.io/puffy-pal/ talks on this laptop.
Speech: local Whisper (mic) → toy-brain (streamed) → Kokoro on the GPU, about 1 s from the child to the first sound.
See [PLAN.md](PLAN.md) for what's done and what's next.

Without Whisper on the server (e.g. PythonAnywhere), the browser's own speech recognition is used (Chrome/Edge).

## Put it online 24/7

**1. Web app → GitHub Pages**
Push this folder to a GitHub repo. Then go to Settings → Pages → Source: `main` branch, `/docs` folder.
The site will be at `https://<you>.github.io/<repo>/`.

**2. Backend → PythonAnywhere** (Hacker plan, about $5/month; the free plan blocks most outside APIs)
- Upload `server/app.py` and create a Flask web app that points at it (`from app import app as application` in the WSGI file).
- Get a Groq API key at console.groq.com and set these in the WSGI file before the import:
  ```python
  os.environ["LLM_URL"] = "https://api.groq.com/openai/v1/chat/completions"
  os.environ["LLM_MODEL"] = "qwen/qwen3-32b"      # or another fast Groq model
  os.environ["LLM_KEY"] = "gsk_..."               # keep this secret: never put it in docs/
  os.environ["APP_TOKEN"] = "pick-a-code"         # the parent enters this in Settings → Connection
  os.environ["ALLOWED_ORIGINS"] = "https://nepes2008j-max.github.io"  # only this site may call the API
  os.environ["ALLOWED_HOSTS"] = "<you>.pythonanywhere.com"           # the server's own address
  ```
- Kokoro doesn't fit on PythonAnywhere, so the app uses the browser's voice there automatically.

**3. Connect them:** set `HOSTED_API` at the top of the script in `docs/index.html` to `https://<you>.pythonanywhere.com`.

## The toy brain

The prompt lives in `system_prompt()` in `server/app.py`, not in the Ollama Modelfile, so the same prompt works on Ollama and Groq.
It adapts to the child's name, age, hobbies, home language, English level, learning focus and the Gentle Help setting.
Code enforces these rules regardless of the model:
- Qwen "thinking" is turned off (`reasoning_effort: none`).
- Replies are capped at 3 sentences (6 for stories).
- Emoji and markdown are removed before the voice reads them.
- A keyword safety filter (a stopgap until a real moderation model).
