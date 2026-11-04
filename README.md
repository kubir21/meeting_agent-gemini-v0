# Video Analysis Report Generator

Upload a video → Gemini extracts the **exact transcript** and answers 3 fixed questions →
a professional **PDF report** is generated → it is **emailed** to `rk26.ftw@gmail.com`.

Stack: FastAPI · `google-genai` (Gemini File API, JSON mode) · fpdf2 · Brevo email API · vanilla HTML/CSS/JS.

## Project layout

```
app.py            FastAPI server (serves UI + POST /generate-report)
pipeline.py       Shared pipeline: Gemini -> PDF -> email -> cleanup (try/finally)
gemini_client.py  Upload video, wait for ACTIVE, prompt + robust JSON parsing
pdf_report.py     Unicode-safe PDF (Noto fonts incl. Devanagari)
emailer.py        Brevo transactional-email sender with PDF attachment
config.py         All settings (model name, recipient, questions, timeouts)
test_pipeline.py  CLI test using the sample video in the project root
static/           Frontend (index.html, styles.css, app.js)
fonts/            Bundled Noto Sans fonts (OFL licence)
temp/             Temporary uploads/PDFs (auto-created, auto-cleaned)
```

## Setup (Windows / PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Then open `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `BREVO_API_KEY` | Brevo dashboard → SMTP & API → API Keys → Generate (https://app.brevo.com/settings/keys/api) |
| `BREVO_SENDER_EMAIL` | An address verified as a **sender** in Brevo (Senders, Domains & Dedicated IPs → Senders → Add a sender) |
| `BREVO_SENDER_NAME` *(optional)* | Display name of the sender (default `Video Analysis Bot`) |
| `GEMINI_MODEL` *(optional)* | Defaults to `gemini-3.8-flash` (also editable in `config.py`) |

(macOS/Linux: `source venv/bin/activate` and `cp .env.example .env`.)

## Run the web app

```powershell
python app.py
```

Open **http://localhost:8000**, choose a video, and click **Generate Report**.

## Run the test script (sample video, no browser)

```powershell
python test_pipeline.py --no-email   # prints JSON, keeps PDF in temp/ for inspection
python test_pipeline.py              # full run incl. email
```

The script finds the first video in the project root (e.g. `Alia_Proposed.mp4`), copies it into
`temp/`, and works only on that copy. **The original is never modified or deleted.**

## Notes & troubleshooting

- **Cleanup:** the temp video copy, the temp PDF and the Gemini remote file are always deleted
  (`try/finally`), and deletion is restricted to files inside `temp/`.
- **Email errors (HTTP 400/401/403 from Brevo):** check `BREVO_API_KEY`, and make sure `BREVO_SENDER_EMAIL`
  is a verified sender in your Brevo account.
- **Model errors (404 / not found):** set `GEMINI_MODEL` in `.env` to a model available to your key.
- **Timeouts:** large videos may take minutes; adjust `FILE_PROCESSING_TIMEOUT_S` in `config.py`.
