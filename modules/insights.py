"""
AI Insights — generates market research, SCR executive brief, and 'So What' recommendations.

Supports two providers:
  1. Google Gemini (free tier — 1,500 req/day with Gemini 2.0 Flash)
  2. Fallback: template-based insights from data patterns (no API needed)

Set GOOGLE_API_KEY in Streamlit secrets or environment variable.
Get your free key at: https://aistudio.google.com/apikey
"""

import json
import os
import re

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False
    class _st:
        @staticmethod
        def warning(msg): print(f"WARNING: {msg}")
        secrets = {}
    st = _st()

try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def get_api_key() -> str:
    """Get Google API key from Streamlit secrets or environment."""
    if _HAS_ST:
        try:
            return st.secrets["GOOGLE_API_KEY"]
        except (KeyError, FileNotFoundError, AttributeError):
            pass
    return os.environ.get("GOOGLE_API_KEY", "")


def is_available() -> bool:
    """Check if Gemini API is configured and available."""
    return HAS_GEMINI and bool(get_api_key())


def generate_insights(category: str, results: dict, progress_callback=None) -> dict:
    """Generate market research and strategic insights.

    Uses Google Gemini if configured, otherwise falls back to templates.

    Returns dict with keys:
        - situation, complication, resolution (SCR framework)
        - market_research (market size, CAGR, segments, drivers)
        - seasonal (12-month demand calendar)
        - insight_cards (6-8 'So What for JioMart?' cards)
    """
    if not is_available():
        return _fallback_insights(category, results)

    if progress_callback:
        progress_callback("Generating AI-powered insights via Gemini...", 0.88)

    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    context = _build_context(category, results)

    prompt = f"""You are a McKinsey senior consultant analyzing the "{category}" category for JioMart (India's leading ecommerce platform by Reliance).

Based on the following data analysis results, generate strategic insights in JSON format.

DATA CONTEXT:
{context}

Return ONLY valid JSON (no markdown, no code fences, no explanation) with this exact structure:
{{
  "situation": "1-2 sentence situation statement about the category market in India",
  "complication": "1-2 sentence complication — what JioMart is missing based on the data",
  "resolution": "1-2 sentence resolution — top priorities for JioMart",
  "market_research": {{
    "market_size": "e.g. $X.XB (2025) → $X.XB (2034)",
    "cagr": "X.X%",
    "key_segments": "top 3-4 segments separated by comma",
    "growth_drivers": ["driver 1", "driver 2", "driver 3", "driver 4", "driver 5"],
    "regulatory": "any relevant Indian regulations or mandates for this category",
    "top_india_brands": ["brand1", "brand2", "brand3", "brand4", "brand5", "brand6", "brand7"],
    "price_segments": {{
      "Economy (₹X-Y)": "description",
      "Mid-range (₹X-Y)": "description",
      "Premium (₹X-Y)": "description",
      "Super-premium (₹X+)": "description"
    }}
  }},
  "seasonal": {{
    "Jan": {{"demand": "Low/Medium/High/Very High", "note": "brief India-specific note"}},
    "Feb": {{"demand": "...", "note": "..."}},
    "Mar": {{"demand": "...", "note": "..."}},
    "Apr": {{"demand": "...", "note": "..."}},
    "May": {{"demand": "...", "note": "..."}},
    "Jun": {{"demand": "...", "note": "..."}},
    "Jul": {{"demand": "...", "note": "..."}},
    "Aug": {{"demand": "...", "note": "..."}},
    "Sep": {{"demand": "...", "note": "..."}},
    "Oct": {{"demand": "...", "note": "..."}},
    "Nov": {{"demand": "...", "note": "..."}},
    "Dec": {{"demand": "...", "note": "..."}}
  }},
  "insight_cards": [
    {{
      "category": "e.g. Regulatory / Consumer Trend / E-commerce / Pricing",
      "impact": "High/Medium",
      "finding": "2-3 sentence factual finding specific to India",
      "sowhat": "Specific actionable recommendation for JioMart"
    }}
  ],
  "sweet_spot": "price range that represents the highest-volume opportunity for JioMart"
}}

Be specific to the Indian market. Use real market data you know about "{category}" in India.
Generate exactly 6 insight cards. Make the seasonal calendar India-specific (Diwali, monsoon, Republic Day sales, etc.).
Return ONLY the JSON — no other text.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "temperature": 0.3,
                "max_output_tokens": 4000,
            },
        )

        # Handle empty or blocked responses
        if not response.candidates:
            st.warning("Gemini returned no candidates. Using fallback insights.")
            return _fallback_insights(category, results)

        text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                text += part.text

        text = text.strip()
        if not text:
            st.warning("Gemini returned empty response. Using fallback insights.")
            return _fallback_insights(category, results)

        # Clean JSON if wrapped in code fences
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if match:
                text = match.group(1).strip()

        # Try to find JSON object in text
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)

        insights = json.loads(text)
        return insights

    except json.JSONDecodeError:
        # Try to repair common JSON issues from LLM output
        try:
            repaired = _repair_json(text)
            insights = json.loads(repaired)
            return insights
        except (json.JSONDecodeError, Exception):
            pass
        st.warning("Gemini returned invalid JSON. Using fallback insights.")
        return _fallback_insights(category, results)
    except Exception as e:
        st.warning(f"Gemini API call failed: {e}. Using fallback insights.")
        return _fallback_insights(category, results)


def _repair_json(text: str) -> str:
    """Attempt to fix common JSON issues from LLM output."""
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Fix missing commas between key-value pairs: }"key" → },"key"
    text = re.sub(r'"\s*\n\s*"', '",\n"', text)
    # Fix missing commas after values: "value"\n"key" patterns
    text = re.sub(r'([\d\w"])\s*\n\s*"(\w+)":', r'\1,\n"\2":', text)
    # Fix missing commas between array elements: }\n{
    text = re.sub(r"}\s*\n\s*{", "},\n{", text)
    return text


def _build_context(category: str, results: dict) -> str:
    """Build a concise context string from analysis results."""
    jm_count = len(results.get("jm_keywords", []))
    kp_count = len(results.get("kp_keywords", []))
    amz_count = results.get("amz_count", 0)
    fk_count = results.get("fk_count", 0)
    coverage = results.get("coverage_pct", 0)
    whitespace = results.get("whitespace_count", 0)
    amz_median = results.get("amz_stats", {}).get("Median", 0)
    fk_median = results.get("fk_stats", {}).get("Median", 0)

    top_jm = ", ".join(k["Keyword"] for k in results.get("jm_keywords", [])[:10])
    top_amz_brands = ", ".join(b["Brand"] for b in results.get("amz_brands", [])[:10])
    top_gap_kw = ", ".join(k["Keyword"] for k in results.get("whitespace_keywords", [])[:10])
    amz_bands = results.get("amz_bands", {})
    fk_bands = results.get("fk_bands", {})

    return f"""
Category: {category}
JM Search: {jm_count} matched keywords. Top: {top_jm}
Google KP: {kp_count} keywords. Coverage: {coverage}%. Whitespace: {whitespace} keywords.
Top whitespace keywords: {top_gap_kw}
Amazon: {amz_count} products, median ₹{amz_median}. Top brands: {top_amz_brands}
Amazon price bands: {json.dumps(amz_bands)}
Flipkart: {fk_count} products, median ₹{fk_median}.
Flipkart price bands: {json.dumps(fk_bands)}
Brand gaps (on Amazon but not FK): {', '.join(results.get('brands_only_amz', [])[:10])}
Total prioritized actions: {len(results.get('actions', []))}
"""


def _fallback_insights(category: str, results: dict) -> dict:
    """Generate basic insights without API — template-based."""
    amz_median = results.get("amz_stats", {}).get("Median", 0)
    fk_median = results.get("fk_stats", {}).get("Median", 0)
    coverage = results.get("coverage_pct", 0)
    whitespace = results.get("whitespace_count", 0)
    amz_count = results.get("amz_count", 0)
    fk_count = results.get("fk_count", 0)

    return {
        "situation": f"The {category} category shows active demand across search and e-commerce platforms with {amz_count} Amazon and {fk_count} Flipkart products competing for consumer attention.",
        "complication": f"JioMart captures only {coverage}% of addressable search demand. {whitespace} high-volume keywords have zero JM presence, representing significant missed revenue.",
        "resolution": f"Prioritize filling top demand gaps, onboarding missing brands, and positioning pricing competitively around the ₹{int(amz_median*0.8)}-₹{int(amz_median*1.2)} range.",
        "market_research": {
            "market_size": "Enable Gemini API for market intelligence",
            "cagr": "—",
            "key_segments": "Enable Gemini API for segment analysis",
            "growth_drivers": [
                "E-commerce penetration growth in India",
                "Rising disposable income in Tier 2-3 cities",
                "Festive season demand surges",
                "Brand premiumization trend",
                "Digital-first purchase behavior",
            ],
            "regulatory": "Enable Gemini API for regulatory analysis",
            "top_india_brands": [b["Brand"] for b in results.get("amz_brands", [])[:7]],
            "price_segments": {
                f"Economy (Under ₹{int(amz_median*0.4)})": "Basic/unbranded",
                f"Mid-range (₹{int(amz_median*0.4)}-₹{int(amz_median)})": "Branded, volume segment",
                f"Premium (₹{int(amz_median)}-₹{int(amz_median*2)})": "Premium features",
                f"Super-premium (₹{int(amz_median*2)}+)": "Imported/luxury",
            },
        },
        "seasonal": {
            m: {"demand": "Medium", "note": "Enable Gemini API for seasonal intelligence"}
            for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        },
        "insight_cards": [
            {
                "category": "Search Demand",
                "impact": "High",
                "finding": f"{whitespace} keywords with Google search volume have zero JM presence.",
                "sowhat": "Fill top 10 whitespace keywords to capture immediate demand.",
            },
            {
                "category": "Competitive",
                "impact": "High",
                "finding": f"Amazon has {amz_count} products vs Flipkart's {fk_count}. {len(results.get('brands_only_amz', []))} brands sell on Amazon but not Flipkart.",
                "sowhat": "Prioritize onboarding Amazon-proven brands to JioMart.",
            },
            {
                "category": "Pricing",
                "impact": "Medium",
                "finding": f"Amazon median is ₹{int(amz_median)}, Flipkart is ₹{int(fk_median)}. Price gap indicates positioning opportunity.",
                "sowhat": f"Position JM pricing between ₹{int(fk_median)} and ₹{int(amz_median)} for competitive advantage.",
            },
        ],
        "sweet_spot": f"₹{int(amz_median*0.6)}-₹{int(amz_median*1.2)}",
    }
