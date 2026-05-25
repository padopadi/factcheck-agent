# 🔍 FactCheck Agent

An AI-powered fact-checking web app that automatically verifies claims in PDF documents.

## What it does
1. **Upload** any PDF (marketing content, reports, articles)
2. **AI extracts** all verifiable claims (stats, dates, figures)
3. **Web searches** to verify each claim in real-time
4. **Reports** each claim as ✅ Verified / ⚠️ Inaccurate / ❌ False

## Tech Stack
- **Frontend:** Streamlit
- **AI:** Google Gemini 1.5 Flash (free via AI Studio)
- **Web Search:** DuckDuckGo (no API key needed)
- **PDF Parsing:** pdfplumber

## Setup & Run Locally

```bash
git clone https://github.com/YOUR_USERNAME/factcheck-agent
cd factcheck-agent
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Get Your Free API Key
1. Go to https://aistudio.google.com/app/apikey
2. Sign in with Google
3. Click "Create API Key"
4. Paste it in the sidebar of the app

## Deploy on Streamlit Cloud (Free)
1. Push this repo to GitHub
2. Go to https://share.streamlit.io
3. Click "New app" → select your repo → set `app.py` as main file
4. Deploy! You'll get a public URL.

## Project Structure
```
factcheck-agent/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## Evaluation
The app is designed to catch "Trap Documents" — PDFs with intentional lies and outdated statistics. It flags them clearly with a ⚠️ alert when more than 40% of claims are inaccurate/false.
