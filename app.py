"""
JioMart Demand Analysis — Streamlit App
========================================
Select a category, click Generate, get a McKinsey-style demand dashboard.

Data is pre-loaded from parquet files in data/ folder.
AI insights powered by Google Gemini API (optional — works without it too).
"""

import streamlit as st
import time
from modules.data_loader import (
    load_hierarchy,
    load_jm_search,
    load_keyword_planner,
    load_amazon,
    load_flipkart,
    get_all_categories,
    check_data_ready,
)
from modules.pipeline import resolve_category, run_analysis
from modules.insights import generate_insights, is_available as api_available
from modules.dashboard import generate_html


# ─────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="JioMart Demand Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for McKinsey-style look
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global */
    .stApp { font-family: 'Inter', 'Segoe UI', sans-serif; }

    /* Sidebar branding */
    [data-testid="stSidebar"] {
        background: #051C2C;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4,
    [data-testid="stSidebar"] li, [data-testid="stSidebar"] a,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stTextInput label {
        color: #E8ECF0 !important;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] span,
    [data-testid="stSidebar"] .stTextInput input {
        color: #051C2C !important;
    }

    /* Main header */
    .main-header {
        background: linear-gradient(135deg, #051C2C 0%, #0A3A5C 100%);
        color: white;
        padding: 2rem 2.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 {
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
    }
    .main-header p {
        opacity: 0.7;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }

    /* Status cards */
    .status-card {
        background: white;
        border: 1px solid #E8ECF0;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        text-align: center;
    }
    .status-card .value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #051C2C;
    }
    .status-card .label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #4A6274;
        margin-top: 0.25rem;
    }

    /* Hide Streamlit defaults */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="main-header">
    <h1>📊 JioMart Demand Analysis</h1>
    <p>Select a category → Generate an AI-powered McKinsey-style demand dashboard</p>
</div>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────
# Check data readiness
# ─────────────────────────────────────────────────────────────────────
data_status = check_data_ready()
all_ready = all(s["ready"] for s in data_status.values())

if not all_ready:
    st.error("⚠️ Data files not found. Run `python prepare_data.py` first to convert raw data to parquet format.")
    st.markdown("**Missing files:**")
    for name, status in data_status.items():
        icon = "✅" if status["ready"] else "❌"
        st.markdown(f"- {icon} `{name}` — {'Ready' if status['ready'] else 'Missing'}")
    st.info("See README.md for setup instructions.")
    st.stop()


# ─────────────────────────────────────────────────────────────────────
# Sidebar — category selection
# ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")

    # Load hierarchy for category dropdown
    hierarchy = load_hierarchy()
    categories = get_all_categories(hierarchy)

    # Category level selector
    level = st.selectbox(
        "CATEGORY LEVEL",
        options=["AOP L2", "L2", "L3", "L4", "Custom"],
        index=0,
        help="Choose the hierarchy level to analyze",
    )

    if level == "Custom":
        category_input = st.text_input(
            "ENTER CATEGORY NAME",
            placeholder="e.g., Pressure Cookers, Helmets",
            help="Free-form category name — will fuzzy match against hierarchy",
        )
    else:
        level_key = level.replace(" ", "_") if level != "Custom" else ""
        options = categories.get(level, [])
        if options:
            category_input = st.selectbox(
                f"SELECT {level}",
                options=[""] + options,
                index=0,
                help=f"Choose from {len(options)} available {level} categories",
            )
        else:
            category_input = ""
            st.warning(f"No categories found at {level} level")

    st.markdown("---")

    # API status
    if api_available():
        st.success("🤖 Gemini API: Connected")
    else:
        st.warning("🤖 Gemini API: Not configured")
        st.caption("Add GOOGLE_API_KEY to .streamlit/secrets.toml for AI insights")
        st.caption("[Get free key →](https://aistudio.google.com/apikey)")

    st.markdown("---")

    # Data status
    st.markdown("### 📁 Data Sources")
    for name, status in data_status.items():
        icon = "🟢" if status["ready"] else "🔴"
        st.caption(f"{icon} {name} ({status['size_mb']}MB)")

    st.markdown("---")
    st.caption("Built by JioMart Category Intelligence")


# ─────────────────────────────────────────────────────────────────────
# Main panel — Generate button & output
# ─────────────────────────────────────────────────────────────────────
if not category_input:
    st.info("👈 Select a category from the sidebar to begin")
    st.stop()

# Show selected category
st.markdown(f"### Analyzing: **{category_input}**")

# Generate button
col1, col2 = st.columns([1, 4])
with col1:
    generate_btn = st.button("🚀 Generate Analysis", type="primary", use_container_width=True)

if generate_btn:
    # Resolve category
    with st.spinner("Resolving category..."):
        cat_keywords = resolve_category(hierarchy, category_input)

    if not cat_keywords:
        st.error(f"Could not resolve '{category_input}' in the hierarchy. Try a different name or level.")
        st.stop()

    st.caption(f"Matched {len(cat_keywords)} hierarchy keywords: {', '.join(cat_keywords[:10])}")

    # Load data
    progress = st.progress(0, text="Loading data sources...")

    jm_search = load_jm_search()
    progress.progress(5, text="JM Search loaded...")

    kp = load_keyword_planner()
    progress.progress(10, text="Keyword Planner loaded...")

    amazon = load_amazon()
    progress.progress(15, text="Amazon data loaded...")

    flipkart = load_flipkart()
    progress.progress(20, text="Flipkart data loaded...")

    # Run pipeline
    def update_progress(msg, pct):
        progress.progress(int(pct * 80) + 20, text=msg)

    results = run_analysis(
        category=category_input,
        category_keywords=cat_keywords,
        jm_search=jm_search,
        keyword_planner=kp,
        amazon=amazon,
        flipkart=flipkart,
        progress_callback=update_progress,
    )

    # Generate AI insights
    progress.progress(85, text="Generating AI insights...")
    insights = generate_insights(category_input, results, progress_callback=update_progress)

    # Generate HTML dashboard
    progress.progress(92, text="Building McKinsey-style dashboard...")
    html = generate_html(results, insights)

    progress.progress(100, text="✅ Dashboard ready!")
    time.sleep(0.5)
    progress.empty()

    # ── Summary stats ──
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("JM Keywords", len(results.get("jm_keywords", [])))
    c2.metric("Google Keywords", len(results.get("kp_keywords", [])))
    c3.metric("Amazon Products", results.get("amz_count", 0))
    c4.metric("Flipkart Products", results.get("fk_count", 0))
    c5.metric("Actions", len(results.get("actions", [])))

    # ── Preview in iframe ──
    st.markdown("### 📊 Dashboard Preview")
    st.components.v1.html(html, height=800, scrolling=True)

    # ── Download button ──
    st.markdown("---")
    filename = f"Demand_Analysis_{category_input.replace(' ', '_')}.html"
    st.download_button(
        label=f"⬇️ Download Dashboard ({filename})",
        data=html,
        file_name=filename,
        mime="text/html",
        type="primary",
    )

    st.success(f"Dashboard generated successfully for **{category_input}** with {len(results.get('actions', []))} prioritized actions.")
