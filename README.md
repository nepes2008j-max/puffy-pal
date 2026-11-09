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
~/Desktop/ai/.venv/bin/python server/app.py     # open http://localhost:5000
python3 server/check.py                         # every reply should take under 1.5s
```

Speech-to-text uses the browser's built-in recognition, so use Chrome or Edge. Typing works everywhere.

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
  os.environ["ALLOWED_ORIGIN"] = "https://<you>.github.io"
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
