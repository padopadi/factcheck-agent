import streamlit as st
import pdfplumber
import requests
import json
import re
from datetime import datetime

st.set_page_config(page_title="FactCheck Agent", page_icon="🔍", layout="wide")

st.markdown("""
<style>
    .verdict-verified { background: linear-gradient(135deg, #1a3a2a, #0d2b1a); border-left: 4px solid #00c853; border-radius: 8px; padding: 16px; margin: 10px 0; }
    .verdict-inaccurate { background: linear-gradient(135deg, #3a2a00, #2b1f00); border-left: 4px solid #ffd600; border-radius: 8px; padding: 16px; margin: 10px 0; }
    .verdict-false { background: linear-gradient(135deg, #3a1a1a, #2b0d0d); border-left: 4px solid #ff1744; border-radius: 8px; padding: 16px; margin: 10px 0; }
    .claim-text { color: #e0e0e0; font-size: 0.95rem; }
    .verdict-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; margin-bottom: 8px; }
    .badge-verified { background-color: #00c853; color: #000; }
    .badge-inaccurate { background-color: #ffd600; color: #000; }
    .badge-false { background-color: #ff1744; color: #fff; }
    .explanation { color: #b0bec5; font-size: 0.88rem; margin-top: 6px; }
</style>
""", unsafe_allow_html=True)


def extract_text_from_pdf(uploaded_file) -> str:
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def call_gemini(prompt: str, gemini_key: str) -> str:
    """Try multiple Gemini models until one works."""
    models = [
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
    ]
    last_error = ""
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            body = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=body, timeout=30)
            data = r.json()
            if "error" in data:
                last_error = data["error"]["message"]
                continue
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            last_error = str(e)
            continue
    raise Exception(f"All models failed. Last error: {last_error}")


def extract_claims(text: str, gemini_key: str) -> list:
    prompt = f"""
You are a fact-checking assistant. Read the text below and extract ALL specific, verifiable claims.
Focus on: statistics, percentages, dates, financial figures, scientific facts, named data points.

For each claim return a JSON array. Each item must have:
- "claim": the exact claim as a short sentence
- "category": one of [Statistic, Date, Financial, Scientific, Other]

Return ONLY a raw JSON array. No explanation, no markdown, no backticks.

TEXT:
{text[:8000]}
"""
    raw = call_gemini(prompt, gemini_key)
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        claims = json.loads(raw)
        return claims if isinstance(claims, list) else []
    except Exception:
        return []


def google_search(query: str, api_key: str, cx: str) -> str:
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cx, "q": query, "num": 5}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "error" in data:
            return f"Search error: {data['error']['message']}"
        snippets = []
        for item in data.get("items", []):
            snippets.append(f"{item.get('title','')}: {item.get('snippet','')}")
        return " | ".join(snippets) if snippets else "No results found."
    except Exception as e:
        return f"Search error: {e}"


def verify_claim(claim: str, gemini_key: str, google_api_key: str, google_cx: str) -> dict:
    search_result = google_search(claim, google_api_key, google_cx)
    prompt = f"""
You are a strict fact-checker with access to real-time web search results.

CLAIM: {claim}
REAL-TIME WEB SEARCH RESULTS: {search_result}

Classify the claim as exactly one of:
- "Verified" — matches current evidence
- "Inaccurate" — partially wrong or outdated
- "False" — clearly wrong or unsupported

Return ONLY a raw JSON object (no markdown, no backticks):
- "verdict": Verified / Inaccurate / False
- "explanation": 1-2 sentence explanation
- "correct_fact": correct info if Inaccurate or False, else ""
- "sources_used": brief mention of sources
"""
    raw = call_gemini(prompt, gemini_key)
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
        result["claim"] = claim
        return result
    except Exception:
        return {"claim": claim, "verdict": "False", "explanation": "Could not verify.", "correct_fact": "", "sources_used": ""}


def render_result(item: dict):
    verdict = item.get("verdict", "False")
    css_class = {"Verified": "verdict-verified", "Inaccurate": "verdict-inaccurate", "False": "verdict-false"}.get(verdict, "verdict-false")
    badge_class = {"Verified": "badge-verified", "Inaccurate": "badge-inaccurate", "False": "badge-false"}.get(verdict, "badge-false")
    emoji = {"Verified": "✅", "Inaccurate": "⚠️", "False": "❌"}.get(verdict, "❌")
    correct = f'<div class="explanation"><b>✔ Correct fact:</b> {item["correct_fact"]}</div>' if item.get("correct_fact") else ""
    sources = f'<div class="explanation"><b>🌐 Sources:</b> {item["sources_used"]}</div>' if item.get("sources_used") else ""
    st.markdown(f"""
<div class="{css_class}">
    <span class="verdict-badge {badge_class}">{emoji} {verdict}</span>
    <div class="claim-text"><b>Claim:</b> {item['claim']}</div>
    <div class="explanation">{item.get('explanation','')}</div>
    {correct}{sources}
</div>
""", unsafe_allow_html=True)


# ── UI ──────────────────────────────────────────────────────────────────────
st.markdown("# 🔍 FactCheck Agent")
st.markdown("**Upload a PDF** → AI extracts claims → Real-time Google Search verifies → Full report")
st.divider()

with st.sidebar:
    st.header("⚙️ Configuration")
    gemini_key = st.text_input("Google Gemini API Key", type="password", placeholder="AIza... (from aistudio.google.com)")
    st.markdown("[🔑 Get FREE Gemini key here](https://aistudio.google.com/app/apikey)")
    st.divider()
    google_api_key = st.text_input("Google Search API Key", type="password", placeholder="AIza... (from cloud console)")
    google_cx = st.text_input("Search Engine ID (cx)", placeholder="e.g. c383e856ec1b445f5")
    st.divider()
    st.markdown("1. Upload PDF\n2. Gemini extracts claims\n3. Google verifies each\n4. Get verdicts")

uploaded_file = st.file_uploader("📄 Upload your PDF", type=["pdf"])
all_keys_ready = gemini_key and google_api_key and google_cx

if uploaded_file and all_keys_ready:
    if st.button("🚀 Run Fact-Check", type="primary", use_container_width=True):

        with st.spinner("📖 Reading PDF..."):
            pdf_text = extract_text_from_pdf(uploaded_file)

        if not pdf_text:
            st.error("Could not extract text from PDF.")
            st.stop()

        with st.expander("📄 Extracted PDF Text (preview)"):
            st.text(pdf_text[:2000] + ("..." if len(pdf_text) > 2000 else ""))

        with st.spinner("🧠 Identifying claims with Gemini..."):
            try:
                claims = extract_claims(pdf_text, gemini_key)
            except Exception as e:
                st.error(f"Gemini API error: {e}\n\n**Go to aistudio.google.com/app/apikey → create a brand new key in a NEW project → paste it here**")
                st.stop()

        if not claims:
            st.warning("No verifiable claims found.")
            st.stop()

        st.success(f"Found **{len(claims)} claims** to verify!")

        results = []
        progress = st.progress(0, text="Verifying claims...")
        for i, claim_obj in enumerate(claims):
            claim_text = claim_obj.get("claim", "")
            if claim_text:
                result = verify_claim(claim_text, gemini_key, google_api_key, google_cx)
                result["category"] = claim_obj.get("category", "Other")
                results.append(result)
            progress.progress((i + 1) / len(claims), text=f"Verified {i+1}/{len(claims)}")

        progress.empty()

        verified = sum(1 for r in results if r["verdict"] == "Verified")
        inaccurate = sum(1 for r in results if r["verdict"] == "Inaccurate")
        false = sum(1 for r in results if r["verdict"] == "False")

        st.divider()
        st.markdown("## 📊 Results Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(results))
        c2.metric("✅ Verified", verified)
        c3.metric("⚠️ Inaccurate", inaccurate)
        c4.metric("❌ False", false)

        if (inaccurate + false) > len(results) * 0.4:
            st.error("🚨 TRAP DOCUMENT DETECTED! High number of false/inaccurate claims found.")

        st.divider()
        st.markdown("## 📋 Detailed Report")
        for item in results:
            render_result(item)

        report = [f"FACT-CHECK REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                  f"File: {uploaded_file.name}",
                  f"Total: {len(results)} | Verified: {verified} | Inaccurate: {inaccurate} | False: {false}", "="*60]
        for r in results:
            report.append(f"\n[{r['verdict']}] {r['claim']}")
            report.append(f"  → {r.get('explanation','')}")
            if r.get("correct_fact"): report.append(f"  ✔ {r['correct_fact']}")

        st.download_button("📥 Download Report", "\n".join(report), file_name="factcheck_report.txt", use_container_width=True)

elif uploaded_file and not all_keys_ready:
    st.warning("⬅️ Please fill in all 3 keys in the sidebar")
else:
    st.info("👈 Enter your API keys in the sidebar, then upload a PDF")
