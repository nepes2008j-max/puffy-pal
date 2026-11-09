# PythonAnywhere WSGI file for Puffy Pal.
# Paste this whole file into: Web tab -> "WSGI configuration file" link, replacing everything there.
# Then replace the two things marked  <<<  below and click the green "Reload" button.
import os
import sys

USERNAME = "your-pythonanywhere-username"            # <<< your PythonAnywhere username
os.environ["LLM_KEY"] = "paste-your-groq-key-here"   # <<< from console.groq.com -> API Keys (keep it secret)

# AI brain: Groq (OpenAI-compatible). Qwen3 needs REASONING_EFFORT "none" (no slow "thinking").
os.environ["LLM_URL"] = "https://api.groq.com/openai/v1/chat/completions"
os.environ["LLM_MODEL"] = "qwen/qwen3-32b"
os.environ["REASONING_EFFORT"] = "none"
# If Groq says that model doesn't exist, use a fast Llama instead:
# os.environ["LLM_MODEL"] = "llama-3.1-8b-instant"; os.environ["REASONING_EFFORT"] = ""

# Ears: Groq's cloud Whisper (same key). Voice: the phone's own voice (no GPU here for Kokoro).
os.environ["STT_URL"] = "https://api.groq.com/openai/v1/audio/transcriptions"

# Only this site may use the API.
os.environ["ALLOWED_HOSTS"] = f"{USERNAME}.pythonanywhere.com"
os.environ["ALLOWED_ORIGINS"] = f"https://{USERNAME}.pythonanywhere.com,https://nepes2008j-max.github.io"

sys.path.insert(0, f"/home/{USERNAME}/puffy_pal/server")
from app import app as application  # noqa: E402
