# Puffy Pal MVP: plan and status

Sources: the user guide PDF (29 pages) and the Figma file, page 2 (27 screens).

## Done
- [x] Talk screen: voice in (local Whisper), streamed AI reply (toy-brain), voice out (Kokoro on the GPU). About 1 s from the child finishing to Puffy Pal speaking.
- [x] Prompt built from the child's profile (name, age, hobbies, home language, English level, focus, Gentle Help), with gentle grammar correction.
- [x] Safety enforced in code: sentence cap, emoji/markdown removed, keyword filter, kind replies for sad children.
- [x] Home, History (daily/weekly/monthly, average, streak), Toy status, Test Connection, Profile, Settings (level, focus, Gentle Help, speed, volume, sleep mode, connection, reset).
- [x] GitHub Pages site that uses the laptop's server while the laptop is on.

## Tonight (no input needed)
- [x] First-run welcome: ask the child's name, age and hobbies, then pick a level (Figma "Get Started").
- [x] Grown-up check before Settings, Profile and Reset, so kids can't change them (a simple math question; no PIN to forget).
- [x] Reminders (guide, page 22): the parent types a message and a time, and Puffy Pal says it out loud while the app is open.
- [x] Installable on phones (PWA manifest and icons): "Add to Home Screen" opens full screen like an app.
- [x] About Puffy Pal screen (Figma "About").
- [x] `start.sh`: one command starts the server and opens the app.
- [x] `./start.sh public`: a Cloudflare quick tunnel gives a public https link that works from any network while the laptop is on. One request per turn (audio in, voiced sentences out as MP3): about 1.2–1.7 s to the first sound over the internet, sometimes 2.5–3 s because quick tunnels vary.

- [x] Browser test (`node server/e2e.mjs`): welcome, greeting, spoken question through the real mic, typed question, history, safety, grown-up check, reminder, status, usage. 12/12 passing on localhost and over the public tunnel. It found and fixed two bugs: the mic never stopped by itself, and reminders could be skipped.

## Needs you
- [ ] **Steadier public link**: a free Cloudflare account turns the quick tunnel into a fixed address with steadier speed.
- [ ] **24/7 backend**: a PythonAnywhere account and a Groq API key (see README). Until then the live site only talks while this laptop runs `start.sh`.
- [ ] **Contact Us screen**: needs your real support email or phone number.
- [ ] **GitHub 2FA** by Dec 12, 2026, or the account gets restricted.
- [ ] **Fix the laptop's proxy variables**: `HTTPS_PROXY` points at 192.168.2.8 and `https_proxy` at 192.168.2.4, and nothing answers at either. This breaks `gh`/`git push`.

## Later (after the MVP is shown)
- A real moderation model (e.g. Llama Guard) instead of the keyword list.
- "Words learned" for parents: track new words the child used or was taught.
- An accounts backend so profiles and history sync across devices (now they're saved in the browser only).
- Physical toy: ESP32 + mic + speaker streaming to the same `/api/stt` → `/api/chat` → `/api/tts` endpoints. The backend is already shaped for this.
- Wake word ("Hey Puffy") instead of tapping.
