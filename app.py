import streamlit as st
import pdfplumber
import google.generativeai as genai
import requests
import json
import re
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FactCheck Agent",
    page_icon="🔍",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f1117; }
    .stApp { background-color: #0f1117; }
    h1 { color: #ffffff; font-size: 2.5rem !important; }
    .verdict-verified {
        background: linear-gradient(135deg, #1a3a2a, #0d2b1a);
        border-left: 4px solid #00c853;
        border-radius: 8px;
        padding: 16px;
        margin: 10px 0;
    }
    .verdict-inaccurate {
        background: linear-gradient(135deg, #3a2a00, #2b1f00);
        border-left: 4px solid #ffd600;
        border-radius: 8px;
        padding: 16px;
        margin: 10px 0;
    }
    .verdict-false {
        background: linear-gradient(135deg, #3a1a1a, #2b0d0d);
        border-left: 4px solid #ff1744;
        border-radius: 8px;
        padding: 16px;
        margin: 10px 0;
    }
    .claim-text { color: #e0e0e0; font-size: 0.95rem; }
    .verdict-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.85rem;
        margin-bottom: 8px;
    }
    .badge-verified { background-color: #00c853; color: #000; }
    .badge-inaccurate { background-color: #ffd600; color: #000; }
    .badge-false { background-color: #ff1744; color: #fff; }
    .explanation { color: #b0bec5; font-size: 0.88rem; margin-top: 6px; }
    .summary-box {
        background: #1e2130;
        border-radius: 12px;
        padding: 20px;
        margin: 20px 0;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_text_from_pdf(uploaded_file) -> str:
    """Extract all text from an uploaded PDF."""
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def extract_claims(text: str, model) -> list[dict]:
    """Use Gemini to pull out verifiable claims from the PDF text."""
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
    response = model.generate_content(prompt)
    raw = response.text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        claims = json.loads(raw)
        return claims if isinstance(claims, list) else []
    except Exception:
        return []


def web_search(query: str) -> str:
    """Search DuckDuckGo (no API key needed) and return snippets."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_redirect": 1, "no_html": 1}
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        snippets = []
        if data.get("AbstractText"):
            snippets.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(topic["Text"])
        return " | ".join(snippets) if snippets else "No search results found."
    except Exception as e:
        return f"Search error: {e}"


def verify_claim(claim: str, model) -> dict:
    """Verify a single claim using web search + Gemini reasoning."""
    search_result = web_search(claim)

    prompt = f"""
You are a strict fact-checker. A claim has been made and web search results are provided.

CLAIM: {claim}

WEB SEARCH RESULTS: {search_result}

Based on the evidence, classify the claim as exactly one of:
- "Verified" — the claim matches the evidence
- "Inaccurate" — the claim is partially wrong or outdated
- "False" — the claim is clearly wrong or unsupported

Return ONLY a raw JSON object with these keys (no markdown, no backticks):
- "verdict": one of Verified / Inaccurate / False
- "explanation": 1-2 sentence explanation
- "correct_fact": the correct information if Inaccurate or False, else ""
"""
    response = model.generate_content(prompt)
    raw = response.text.strip()
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
        result["claim"] = claim
        return result
    except Exception:
        return {
            "claim": claim,
            "verdict": "False",
            "explanation": "Could not verify this claim.",
            "correct_fact": "",
        }


def render_result(item: dict):
    """Render a single fact-check result card."""
    verdict = item.get("verdict", "False")
    css_class = {
        "Verified": "verdict-verified",
        "Inaccurate": "verdict-inaccurate",
        "False": "verdict-false",
    }.get(verdict, "verdict-false")

    badge_class = {
        "Verified": "badge-verified",
        "Inaccurate": "badge-inaccurate",
        "False": "badge-false",
    }.get(verdict, "badge-false")

    emoji = {"Verified": "✅", "Inaccurate": "⚠️", "False": "❌"}.get(verdict, "❌")

    correct = ""
    if item.get("correct_fact"):
        correct = f'<div class="explanation"><b>✔ Correct fact:</b> {item["correct_fact"]}</div>'

    st.markdown(f"""
<div class="{css_class}">
    <span class="verdict-badge {badge_class}">{emoji} {verdict}</span>
    <div class="claim-text"><b>Claim:</b> {item['claim']}</div>
    <div class="explanation">{item.get('explanation','')}</div>
    {correct}
</div>
""", unsafe_allow_html=True)


# ── UI ────────────────────────────────────────────────────────────────────────

st.markdown("# 🔍 FactCheck Agent")
st.markdown("**Upload a PDF** → AI extracts claims → Web verifies each one → Get a full report")
st.divider()

# Sidebar: API Key
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="Paste your key from aistudio.google.com",
        help="Get a free key at https://aistudio.google.com/app/apikey"
    )
    st.markdown("[🔑 Get free API key](https://aistudio.google.com/app/apikey)")
    st.divider()
    st.markdown("**How it works:**")
    st.markdown("1. Upload PDF\n2. Gemini extracts claims\n3. Web search verifies each\n4. Get verdicts")

# Main upload area
uploaded_file = st.file_uploader(
    "📄 Upload your PDF",
    type=["pdf"],
    help="Upload any document — marketing content, reports, articles",
)

if uploaded_file and api_key:
    if st.button("🚀 Run Fact-Check", type="primary", use_container_width=True):

        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Step 1: Extract text
        with st.spinner("📖 Reading PDF..."):
            pdf_text = extract_text_from_pdf(uploaded_file)

        if not pdf_text:
            st.error("Could not extract text from this PDF. Make sure it's not a scanned image.")
            st.stop()

        with st.expander("📄 Extracted PDF Text (preview)"):
            st.text(pdf_text[:2000] + ("..." if len(pdf_text) > 2000 else ""))

        # Step 2: Extract claims
        with st.spinner("🧠 Identifying claims with AI..."):
            claims = extract_claims(pdf_text, model)

        if not claims:
            st.warning("No verifiable claims found in this PDF.")
            st.stop()

        st.success(f"Found **{len(claims)} claims** to verify!")

        # Step 3: Verify each claim
        results = []
        progress = st.progress(0, text="Verifying claims...")
        for i, claim_obj in enumerate(claims):
            claim_text = claim_obj.get("claim", "")
            if claim_text:
                with st.spinner(f"🔎 Verifying: {claim_text[:60]}..."):
                    result = verify_claim(claim_text, model)
                    result["category"] = claim_obj.get("category", "Other")
                    results.append(result)
            progress.progress((i + 1) / len(claims), text=f"Verified {i+1}/{len(claims)} claims")

        progress.empty()

        # Step 4: Summary
        verified = sum(1 for r in results if r["verdict"] == "Verified")
        inaccurate = sum(1 for r in results if r["verdict"] == "Inaccurate")
        false = sum(1 for r in results if r["verdict"] == "False")

        st.divider()
        st.markdown("## 📊 Results Summary")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Claims", len(results))
        col2.metric("✅ Verified", verified)
        col3.metric("⚠️ Inaccurate", inaccurate)
        col4.metric("❌ False", false)

        # Trap document alert
        if (inaccurate + false) > len(results) * 0.4:
            st.error("🚨 **High number of false/inaccurate claims detected — this may be a Trap Document!**")

        st.divider()
        st.markdown("## 📋 Detailed Fact-Check Report")

        # Filter buttons
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        show_all = filter_col1.checkbox("All", value=True)
        show_verified = filter_col2.checkbox("✅ Verified", value=False)
        show_inaccurate = filter_col3.checkbox("⚠️ Inaccurate", value=False)
        show_false = filter_col4.checkbox("❌ False", value=False)

        for item in results:
            v = item["verdict"]
            if show_all or (show_verified and v == "Verified") or \
               (show_inaccurate and v == "Inaccurate") or (show_false and v == "False"):
                render_result(item)

        # Download report
        report_lines = [f"FACT-CHECK REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
                        f"File: {uploaded_file.name}\n",
                        f"Total: {len(results)} | Verified: {verified} | Inaccurate: {inaccurate} | False: {false}\n",
                        "=" * 60 + "\n"]
        for r in results:
            report_lines.append(f"\n[{r['verdict']}] {r['claim']}")
            report_lines.append(f"  → {r.get('explanation','')}")
            if r.get("correct_fact"):
                report_lines.append(f"  ✔ Correct: {r['correct_fact']}")

        st.download_button(
            "📥 Download Full Report",
            "\n".join(report_lines),
            file_name="factcheck_report.txt",
            mime="text/plain",
            use_container_width=True,
        )

elif uploaded_file and not api_key:
    st.warning("⬅️ Please enter your Gemini API key in the sidebar to continue.")
elif not uploaded_file and api_key:
    st.info("📄 Please upload a PDF to get started.")
else:
    st.info("👈 Enter your API key in the sidebar, then upload a PDF above.")
