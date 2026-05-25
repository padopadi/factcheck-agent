import streamlit as st
import pdfplumber
import google.generativeai as genai
import requests
import json
import re
from datetime import datetime

st.set_page_config(page_title="FactCheck Agent", page_icon="🔍", layout="wide")

st.markdown("""
<style>
    .verdict-verified {
        background: linear-gradient(135deg, #1a3a2a, #0d2b1a);
        border-left: 4px solid #00c853;
        border-radius: 8px; padding: 16px; margin: 10px 0;
    }
    .verdict-inaccurate {
        background: linear-gradient(135deg, #3a2a00, #2b1f00);
        border-left: 4px solid #ffd600;
        border-radius: 8px; padding: 16px; margin: 10px 0;
    }
    .verdict-false {
        background: linear-gradient(135deg, #3a1a1a, #2b0d0d);
        border-left: 4px solid #ff1744;
        border-radius: 8px; padding: 16px; margin: 10px 0;
    }
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


def extract_claims(text: str, model) -> list:
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
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        claims = json.loads(raw)
        return claims if isinstance(claims, list) else []
    except Exception:
        return []


def google_search(query: str, api_key: str, cx: str) -> str:
    """Real-time Google Custom Search."""
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cx, "q": query, "num": 5}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "error" in data:
            return f"Search error: {data['error']['message']}"
        snippets = []
        for item in data.get("items", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            snippets.append(f"{title}: {snippet}")
        return " | ".join(snippets) if snippets else "No results found."
    except Exception as e:
        return f"Search error: {e}"


def verify_claim(claim: str, model, google_api_key: str, google_cx: str) -> dict:
    search_result = google_search(claim, google_api_key, google_cx)

    prompt = f"""
You are a strict fact-checker with access to real-time web search results.

CLAIM: {claim}

REAL-TIME WEB SEARCH RESULTS:
{search_result}

Based on the evidence above, classify the claim as exactly one of:
- "Verified" — the claim matches current evidence
- "Inaccurate" — the claim is partially wrong, outdated, or exaggerated
- "False" — the claim is clearly wrong or completely unsupported

Return ONLY a raw JSON object (no markdown, no backticks):
- "verdict": one of Verified / Inaccurate / False
- "explanation": 1-2 sentence explanation citing the evidence
- "correct_fact": the correct/current information if Inaccurate or False, else ""
- "sources_used": brief mention of what sources confirmed this
"""
    response = model.generate_content(prompt)
    raw = response.text.strip()
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
        result["claim"] = claim
        result["search_snippet"] = search_result[:300]
        return result
    except Exception:
        return {
            "claim": claim,
            "verdict": "False",
            "explanation": "Could not verify this claim.",
            "correct_fact": "",
            "sources_used": "",
            "search_snippet": search_result[:300],
        }


def render_result(item: dict):
    verdict = item.get("verdict", "False")
    css_class = {"Verified": "verdict-verified", "Inaccurate": "verdict-inaccurate", "False": "verdict-false"}.get(verdict, "verdict-false")
    badge_class = {"Verified": "badge-verified", "Inaccurate": "badge-inaccurate", "False": "badge-false"}.get(verdict, "badge-false")
    emoji = {"Verified": "✅", "Inaccurate": "⚠️", "False": "❌"}.get(verdict, "❌")

    correct = ""
    if item.get("correct_fact"):
        correct = f'<div class="explanation"><b>✔ Correct fact:</b> {item["correct_fact"]}</div>'

    sources = ""
    if item.get("sources_used"):
        sources = f'<div class="explanation"><b>🌐 Sources:</b> {item["sources_used"]}</div>'

    st.markdown(f"""
<div class="{css_class}">
    <span class="verdict-badge {badge_class}">{emoji} {verdict}</span>
    <div class="claim-text"><b>Claim:</b> {item['claim']}</div>
    <div class="explanation">{item.get('explanation','')}</div>
    {correct}
    {sources}
</div>
""", unsafe_allow_html=True)


# ── UI ────────────────────────────────────────────────────────────────────────
st.markdown("# 🔍 FactCheck Agent")
st.markdown("**Upload a PDF** → AI extracts claims → **Real-time Google Search** verifies each one → Get a full report")
st.divider()

with st.sidebar:
    st.header("⚙️ Configuration")

    gemini_key = st.text_input("Google Gemini API Key", type="password", placeholder="AIza...")
    st.markdown("[🔑 Get Gemini key (free)](https://aistudio.google.com/app/apikey)")

    st.divider()

    google_api_key = st.text_input("Google Search API Key", type="password", placeholder="AIza...")
    google_cx = st.text_input("Search Engine ID (cx)", placeholder="e.g. 123abc456:xyz")

    with st.expander("📖 How to get Google Search keys"):
        st.markdown("""
**Step 1 - Search API Key:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project → Enable **"Custom Search API"**
3. Go to Credentials → Create API Key → Copy it

**Step 2 - Search Engine ID:**
1. Go to [programmablesearchengine.google.com](https://programmablesearchengine.google.com)
2. Click **"Add"** → Name it anything
3. Select **"Search the entire web"**
4. Copy the **Search engine ID**
        """)

    st.divider()
    st.markdown("**How it works:**")
    st.markdown("1. Upload PDF\n2. Gemini extracts claims\n3. 🔴 **Live Google Search** verifies each\n4. Get verdicts with sources")

uploaded_file = st.file_uploader("📄 Upload your PDF", type=["pdf"])

all_keys_ready = gemini_key and google_api_key and google_cx

if uploaded_file and all_keys_ready:
    if st.button("🚀 Run Fact-Check", type="primary", use_container_width=True):

        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        with st.spinner("📖 Reading PDF..."):
            pdf_text = extract_text_from_pdf(uploaded_file)

        if not pdf_text:
            st.error("Could not extract text. Make sure it's not a scanned image PDF.")
            st.stop()

        with st.expander("📄 Extracted PDF Text (preview)"):
            st.text(pdf_text[:2000] + ("..." if len(pdf_text) > 2000 else ""))

        with st.spinner("🧠 Identifying claims with Gemini AI..."):
            claims = extract_claims(pdf_text, model)

        if not claims:
            st.warning("No verifiable claims found in this PDF.")
            st.stop()

        st.success(f"Found **{len(claims)} claims** to verify with real-time Google Search!")

        results = []
        progress = st.progress(0, text="Verifying claims via Google Search...")
        for i, claim_obj in enumerate(claims):
            claim_text = claim_obj.get("claim", "")
            if claim_text:
                with st.spinner(f"🔎 Googling: {claim_text[:60]}..."):
                    result = verify_claim(claim_text, model, google_api_key, google_cx)
                    result["category"] = claim_obj.get("category", "Other")
                    results.append(result)
            progress.progress((i + 1) / len(claims), text=f"Verified {i+1}/{len(claims)} claims")

        progress.empty()

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

        if (inaccurate + false) > len(results) * 0.4:
            st.error("🚨 **TRAP DOCUMENT DETECTED! High number of false/inaccurate claims found.**")

        st.divider()
        st.markdown("## 📋 Detailed Fact-Check Report")

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        show_all = filter_col1.checkbox("All", value=True)
        show_verified = filter_col2.checkbox("✅ Verified")
        show_inaccurate = filter_col3.checkbox("⚠️ Inaccurate")
        show_false = filter_col4.checkbox("❌ False")

        for item in results:
            v = item["verdict"]
            if show_all or (show_verified and v == "Verified") or \
               (show_inaccurate and v == "Inaccurate") or (show_false and v == "False"):
                render_result(item)

        report_lines = [
            f"FACT-CHECK REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"File: {uploaded_file.name}",
            f"Total: {len(results)} | Verified: {verified} | Inaccurate: {inaccurate} | False: {false}",
            "=" * 60,
        ]
        for r in results:
            report_lines.append(f"\n[{r['verdict']}] {r['claim']}")
            report_lines.append(f"  → {r.get('explanation','')}")
            if r.get("correct_fact"):
                report_lines.append(f"  ✔ Correct: {r['correct_fact']}")
            if r.get("sources_used"):
                report_lines.append(f"  🌐 Sources: {r['sources_used']}")

        st.download_button("📥 Download Full Report", "\n".join(report_lines),
                           file_name="factcheck_report.txt", mime="text/plain", use_container_width=True)

elif uploaded_file and not all_keys_ready:
    st.warning("⬅️ Please fill in all 3 keys in the sidebar (Gemini + Google Search API + Search Engine ID)")
else:
    st.info("👈 Fill in your API keys in the sidebar, then upload a PDF.")
