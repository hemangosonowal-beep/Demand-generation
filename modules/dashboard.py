"""
McKinsey-style HTML Dashboard Generator.

Takes analysis results + AI insights → returns a self-contained HTML string
with embedded gzip+base64 data, Chart.js charts, and interactive tabs.
"""

import json
import gzip
import base64


def generate_html(results: dict, insights: dict) -> str:
    """Generate the full McKinsey-style HTML dashboard.

    Args:
        results: Output from pipeline.run_analysis()
        insights: Output from insights.generate_insights()

    Returns:
        Complete HTML string ready to save or embed
    """
    # Compile dashboard data
    dashboard_data = _compile_data(results, insights)

    # Compress to base64
    # CRITICAL: allow_nan=False replaces NaN/Infinity with null,
    # because JS JSON.parse() rejects NaN (invalid per RFC 8259)
    dashboard_data = _sanitize_nans(dashboard_data)
    json_str = json.dumps(dashboard_data, default=str, allow_nan=False)
    compressed = gzip.compress(json_str.encode("utf-8"))
    b64 = base64.b64encode(compressed).decode("ascii")

    category = results.get("category", "Category")
    gen_date = results.get("generated_date", "")

    return _build_html(category, gen_date, b64)


def _sanitize_nans(obj):
    """Recursively replace float NaN/Infinity with None (null in JSON).

    Python json.dumps outputs 'NaN' for float('nan'), which is invalid JSON.
    JavaScript JSON.parse() throws SyntaxError on NaN, blanking the entire page.
    """
    import math
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nans(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nans(v) for v in obj]
    return obj


def _compile_data(results: dict, insights: dict) -> dict:
    """Merge pipeline results and AI insights into dashboard data structure."""
    category = results.get("category", "") or ""
    ex = insights or {}
    amz_stats = results.get("amz_stats") or {}
    fk_stats = results.get("fk_stats") or {}

    # KPI cards — use `or` to handle None values
    jm_kw = results.get("jm_keywords") or []
    kp_kw = results.get("kp_keywords") or []
    cov_pct = results.get("coverage_pct") or 0
    ws_count = results.get("whitespace_count") or 0
    amz_count = results.get("amz_count") or 0
    fk_count = results.get("fk_count") or 0
    actions = results.get("actions") or []

    kpi_cards = [
        {"label": "JM Keywords", "value": str(len(jm_kw)),
         "delta": f"{cov_pct}% coverage"},
        {"label": "Google Keywords", "value": str(len(kp_kw)),
         "delta": f"{ws_count} whitespace"},
        {"label": "Amazon Products", "value": str(amz_count),
         "delta": f"Median ₹{int(amz_stats.get('Median') or 0)}"},
        {"label": "Flipkart Products", "value": str(fk_count),
         "delta": f"Median ₹{int(fk_stats.get('Median') or 0)}"},
        {"label": "Coverage", "value": f"{cov_pct}%",
         "delta": f"{ws_count} gaps"},
        {"label": "Actions", "value": str(len(actions)),
         "delta": "prioritized by GMV"},
    ]

    # Demand gaps
    demand_gaps_raw = results.get("demand_gaps") or []
    coverage_kw_raw = results.get("coverage_keywords") or []
    demand_gaps = {
        "whitespace": [
            {
                "keyword": k.get("Keyword", "") or "",
                "google_vol": k.get("Avg. monthly searches", 0) or 0,
                "competition": k.get("Competition", "") or "",
                "yoy_change": k.get("YoY change", "") or "",
                "gmv_opportunity": k.get("GMV_opportunity", 0) or 0,
            }
            for k in demand_gaps_raw[:50]
        ],
        "coverage": [
            {
                "keyword": k.get("Keyword", "") or "",
                "google_vol": k.get("Avg. monthly searches", 0) or 0,
                "jm_volume": k.get("jm_volume", 0) or 0,
                "jm_growth": k.get("jm_growth", 0) or 0,
                "competition": k.get("Competition", "") or "",
            }
            for k in coverage_kw_raw[:50]
        ],
        "total_whitespace": results.get("whitespace_count") or 0,
        "total_coverage": len(coverage_kw_raw),
        "coverage_pct": results.get("coverage_pct") or 0,
    }

    market = insights.get("market_research") or {}

    return {
        "category": category,
        "generated_date": results.get("generated_date") or "",
        "executive": {
            "situation": ex.get("situation") or "",
            "complication": ex.get("complication") or "",
            "resolution": ex.get("resolution") or "",
            "kpi_cards": kpi_cards,
            "top_actions": actions[:5],
        },
        "actions": actions,
        "demand_gaps": demand_gaps,
        "brands": {
            "amazon": (results.get("amz_brands") or [])[:20],
            "flipkart": (results.get("fk_brands") or [])[:20],
            "only_amazon": results.get("brands_only_amz") or [],
            "only_flipkart": results.get("brands_only_fk") or [],
            "on_both": results.get("brands_both") or [],
            "market_leaders": market.get("top_india_brands") or [],
        },
        "pricing": {
            "amazon_bands": results.get("amz_bands") or {},
            "flipkart_bands": results.get("fk_bands") or {},
            "amazon_stats": amz_stats,
            "flipkart_stats": fk_stats,
            "market_segments": market.get("price_segments") or {},
            "sweet_spot": insights.get("sweet_spot") or "",
            "amz_top_products": (results.get("amz_top_products") or [])[:20],
            "fk_top_products": (results.get("fk_top_products") or [])[:20],
        },
        "forecast": results.get("forecast") or {},
        "seasonal": insights.get("seasonal") or {},
        "market": market,
        "insight_cards": insights.get("insight_cards") or [],
        "google_trends": results.get("google_trends") or {},
        "jm_seasonality": results.get("jm_seasonality") or {},
        "youtube_suggestions": results.get("youtube_suggestions") or {},
        "ai_readiness": {
            "intents": results.get("ai_intents") or {},
            "paa": results.get("paa_questions") or {},
        },
        "data_availability": {
            "jm_search": results.get("jm_data_available") is not False,
            "keyword_planner": results.get("kp_data_available") is not False,
            "amazon": results.get("amz_data_available") is not False,
            "flipkart": results.get("fk_data_available") is not False,
        },
    }


def _build_html(category: str, gen_date: str, b64_data: str) -> str:
    """Build the complete HTML string with embedded compressed data."""

    # The HTML template is large — built as a single string
    # Using the McKinsey design system from the skill
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Demand Analysis — {category} | JioMart</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js"></script>
{_CSS}
</head>
<body>
<div class="header">
  <h1 id="page-title">Demand Analysis — {category}</h1>
  <div class="sub">Generated {gen_date} | JioMart Category Intelligence</div>
</div>
<div class="nav-wrap"><div class="nav" id="nav"></div></div>
<div class="container" id="content"></div>
<script>
const B64 = "{b64_data}";
const bin = Uint8Array.from(atob(B64), c => c.charCodeAt(0));
const D = JSON.parse(new TextDecoder().decode(pako.inflate(bin)));
{_JS}
</script>
</body>
</html>'''


# ─────────────────────────────────────────────────────────────────────
# CSS — McKinsey consulting style
# ─────────────────────────────────────────────────────────────────────
_CSS = """<style>
:root {
  --navy: #051C2C; --navy-light: #0A3A5C; --steel: #4A6274;
  --bg: #F7F8FA; --card: #FFFFFF; --border: #E8ECF0;
  --teal: #00A6A0; --coral: #E05A47; --amber: #D4920B;
  --amz: #FF9900; --fk: #2874F0; --highlight: #F0F4F8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family:'Inter','Segoe UI',-apple-system,sans-serif; font-size:14px; color:var(--steel); line-height:1.6; background:var(--bg); -webkit-font-smoothing:antialiased; }
.header { background:var(--navy); color:#fff; padding:40px 48px 32px; }
.header h1 { font-size:32px; font-weight:700; letter-spacing:-0.02em; }
.header .sub { font-size:13px; opacity:0.6; margin-top:8px; }
.nav { background:var(--card); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:100; padding:0 48px; overflow-x:auto; white-space:nowrap; }
.nav a { display:inline-block; padding:16px 0; margin-right:32px; color:var(--steel); text-decoration:none; font-size:13px; font-weight:600; letter-spacing:0.02em; border-bottom:2px solid transparent; transition:all 0.2s; cursor:pointer; }
.nav a.active { color:var(--navy); border-bottom-color:var(--navy); }
.nav a:hover { color:var(--navy); }
.container { max-width:1280px; margin:0 auto; padding:32px 48px; }
.tab { display:none; } .tab.active { display:block; }
.headline { background:var(--highlight); border-left:4px solid var(--navy); padding:20px 24px; margin-bottom:32px; border-radius:0 8px 8px 0; font-size:15px; font-weight:500; color:var(--navy); line-height:1.5; }
.section-title { font-size:14px; font-weight:700; color:var(--navy); text-transform:uppercase; letter-spacing:0.08em; margin:32px 0 16px; }
.metric-grid { display:grid; gap:16px; margin-bottom:32px; }
.metric-grid.cols-3 { grid-template-columns:repeat(3,1fr); }
.metric-grid.cols-4 { grid-template-columns:repeat(4,1fr); }
.metric-grid.cols-6 { grid-template-columns:repeat(6,1fr); }
.metric-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:24px 20px; text-align:left; }
.metric-card .label { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.1em; color:var(--steel); }
.metric-card .value { font-size:32px; font-weight:700; color:var(--navy); margin:6px 0 4px; letter-spacing:-0.02em; }
.metric-card .delta { font-size:12px; color:var(--steel); }
.so-what-box { background:var(--navy); color:#fff; padding:14px 18px; border-radius:6px; font-size:13px; font-weight:500; line-height:1.5; margin-top:12px; }
table { width:100%; border-collapse:collapse; font-size:13px; margin-bottom:16px; }
th { background:var(--navy); color:#fff; padding:12px 14px; text-align:left; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; }
td { padding:10px 14px; border-bottom:1px solid var(--border); color:var(--steel); }
tr:hover { background:var(--highlight); }
.takeaway-row { background:var(--highlight); font-weight:600; color:var(--navy); font-size:13px; border-top:2px solid var(--border); }
.takeaway-row td { font-weight:600; color:var(--navy); }
.pill { display:inline-block; padding:3px 12px; border-radius:20px; font-size:11px; font-weight:600; }
.pill.high { background:rgba(224,90,71,0.12); color:var(--coral); }
.pill.medium { background:rgba(212,146,11,0.12); color:var(--amber); }
.pill.low { background:rgba(0,166,160,0.12); color:var(--teal); }
.pill.gap { background:rgba(224,90,71,0.12); color:var(--coral); }
.pill.covered { background:rgba(0,166,160,0.12); color:var(--teal); }
.insight-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:24px; border-left:4px solid var(--teal); margin-bottom:16px; }
.insight-card.impact-high { border-left-color:var(--coral); }
.insight-card.impact-medium { border-left-color:var(--amber); }
.action-num { width:40px; height:40px; border-radius:50%; background:var(--navy); color:#fff; display:flex; align-items:center; justify-content:center; font-size:18px; font-weight:700; flex-shrink:0; }
.action-card { display:flex; gap:16px; align-items:flex-start; background:var(--card); border:1px solid var(--border); border-radius:8px; padding:20px; margin-bottom:12px; }
.action-card .action-body { flex:1; }
.action-card .action-title { font-weight:600; color:var(--navy); font-size:14px; }
.action-card .action-meta { font-size:12px; color:var(--steel); margin-top:4px; }
.action-card .action-gmv { font-weight:700; color:var(--navy); font-size:16px; white-space:nowrap; }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
.chart-container { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:24px; margin-bottom:24px; }
.accordion-header { cursor:pointer; padding:16px 20px; background:var(--card); border:1px solid var(--border); border-radius:8px; font-size:14px; font-weight:600; color:var(--navy); margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
.accordion-header:hover { background:var(--highlight); }
.accordion-body { display:none; padding:0 0 16px; max-height:500px; overflow-y:auto; }
.accordion-body.open { display:block; }
.search-input { padding:8px 16px; border:1px solid var(--border); border-radius:6px; font-size:13px; width:280px; margin-bottom:16px; outline:none; }
.search-input:focus { border-color:var(--navy); }
.filter-pills { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
.filter-pill { padding:6px 16px; border-radius:20px; font-size:12px; font-weight:600; cursor:pointer; border:1px solid var(--border); background:var(--card); color:var(--steel); transition:all 0.2s; }
.filter-pill.active { background:var(--navy); color:#fff; border-color:var(--navy); }
.scr-banner { background:var(--navy-light); color:#fff; padding:24px; border-radius:8px; margin-bottom:24px; line-height:1.6; font-size:14px; }
.scr-label { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; opacity:0.6; margin-bottom:6px; }
.complication-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:32px; }
.comp-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:24px; border-left:4px solid var(--coral); }
.comp-card .comp-value { font-size:28px; font-weight:700; color:var(--coral); margin:8px 0; }
.comp-card .comp-label { font-size:12px; color:var(--steel); }
.metrics-bar { display:grid; grid-template-columns:repeat(6,1fr); gap:12px; background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px 20px; margin-top:32px; }
.mb-item .mb-value { font-size:16px; font-weight:700; color:var(--navy); }
.mb-item .mb-label { font-size:10px; color:var(--steel); text-transform:uppercase; letter-spacing:0.08em; }
.seasonal-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }
.month-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; font-size:13px; }
.month-card .month-name { font-weight:700; color:var(--navy); font-size:14px; }
.month-card .month-demand { font-size:12px; margin-top:4px; }
.month-card .month-note { font-size:11px; color:var(--steel); margin-top:4px; }
.stacked-bar { height:50px; display:flex; border-radius:6px; overflow:hidden; margin-bottom:16px; }
.stacked-bar div { display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:600; color:#fff; }
.brand-cards { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:24px; }
.brand-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:20px; }
.brand-card .brand-name { font-weight:700; color:var(--navy); font-size:15px; margin-bottom:4px; }
.brand-card .brand-meta { font-size:12px; color:var(--steel); }
/* Nav scroll fade indicators */
.nav { -ms-overflow-style:none; scrollbar-width:none; position:relative; }
.nav::-webkit-scrollbar { display:none; }
.nav-wrap { position:relative; }
.nav-wrap::after { content:''; position:absolute; right:0; top:0; bottom:0; width:40px; background:linear-gradient(90deg,transparent,var(--card)); pointer-events:none; z-index:101; }

/* Collapsible text */
.collapsible-text { max-height:60px; overflow:hidden; transition:max-height 0.3s ease; position:relative; }
.collapsible-text.expanded { max-height:2000px; }
.collapsible-text:not(.expanded)::after { content:''; position:absolute; bottom:0; left:0; right:0; height:30px; background:linear-gradient(transparent,var(--navy-light)); }
.toggle-btn { background:none; border:1px solid rgba(255,255,255,0.3); color:#fff; padding:4px 14px; border-radius:4px; font-size:11px; cursor:pointer; margin-top:8px; font-family:inherit; }
.toggle-btn:hover { background:rgba(255,255,255,0.1); }
.toggle-btn.dark { border-color:var(--border); color:var(--steel); }
.toggle-btn.dark:hover { background:var(--highlight); }

/* Action queue show-more */
.action-hidden { display:none; }
.show-more-btn { width:100%; padding:12px; background:var(--highlight); border:1px dashed var(--border); border-radius:8px; font-size:13px; font-weight:600; color:var(--navy); cursor:pointer; margin:8px 0 16px; font-family:inherit; }
.show-more-btn:hover { background:var(--card); border-color:var(--navy); }

/* Mobile table → card view */
@media(max-width:768px) {
  .header{padding:24px} .header h1{font-size:24px}
  .nav{padding:0 16px} .nav a{margin-right:16px;font-size:12px}
  .container{padding:16px}
  .metric-grid.cols-3,.metric-grid.cols-4,.metric-grid.cols-6{grid-template-columns:1fr}
  .two-col{grid-template-columns:1fr}
  .complication-cards{grid-template-columns:1fr}
  .metrics-bar{grid-template-columns:repeat(2,1fr)}
  .seasonal-grid{grid-template-columns:repeat(2,1fr)}
  .brand-cards{grid-template-columns:1fr}
  .metric-card .value{font-size:24px}
  .action-card{flex-direction:column;gap:8px}
  .action-card .action-gmv{align-self:flex-start}
  .headline{font-size:13px;padding:14px 16px}
  .so-what-box{font-size:12px;padding:10px 14px}
  .insight-card{padding:16px}
  /* Card-view tables on mobile */
  .m-card-view thead{display:none}
  .m-card-view tbody tr{display:block;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px}
  .m-card-view tbody td{display:flex;justify-content:space-between;padding:4px 0;border:none;font-size:13px}
  .m-card-view tbody td::before{content:attr(data-label);font-weight:600;color:var(--navy);margin-right:12px;white-space:nowrap}
  .m-card-view tbody td:first-child{font-weight:600;color:var(--navy)}
}
</style>"""


# ─────────────────────────────────────────────────────────────────────
# JS — dashboard rendering logic
# ─────────────────────────────────────────────────────────────────────
_JS = r"""
Chart.defaults.font.family = "'Inter','Segoe UI',sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = '#4A6274';
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.tooltip.backgroundColor = '#051C2C';
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.tooltip.padding = 12;

const TABS = [
  {id:'exec',label:'Executive Brief'},{id:'actions',label:'Action Queue'},
  {id:'gaps',label:'Demand Gaps'},{id:'brands',label:'Brand & Sourcing'},
  {id:'pricing',label:'Price Positioning'},{id:'forecast',label:'Trends & Forecast'},
  {id:'ai',label:'AI Readiness'}
];

const nav = document.getElementById('nav');
TABS.forEach((t,i) => {
  const a = document.createElement('a');
  a.textContent = t.label; a.className = i===0?'active':'';
  a.onclick = () => switchTab(t.id); a.id = 'nav-'+t.id;
  nav.appendChild(a);
});

function switchTab(id) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  document.getElementById('nav-'+id).classList.add('active');
}

const content = document.getElementById('content');
function fmt(n){if(n==null||isNaN(n))return'—';n=Number(n);if(n>=10000000)return'₹'+(n/10000000).toFixed(1)+'Cr';if(n>=100000)return'₹'+(n/100000).toFixed(1)+'L';if(n>=1000)return'₹'+(n/1000).toFixed(1)+'K';return'₹'+Math.round(n)}
function fmtNum(n){if(n==null||isNaN(n))return'—';return Number(n).toLocaleString('en-IN')}
function pillHTML(t,text){const cls=t==='High'?'high':t==='Medium'?'medium':t==='Low'?'low':t==='gap'?'gap':t==='covered'?'covered':'';return`<span class="pill ${cls}">${text}</span>`}

// TAB 0: Executive Brief
let execHTML = `<div class="tab active" id="tab-exec">`;
const ex = D.executive;
execHTML += `<div class="scr-banner"><div class="scr-label">Situation</div><div class="collapsible-text" id="scr-sit">${ex.situation}</div><button class="toggle-btn" onclick="toggleText('scr-sit',this)">Read more</button></div>`;
const ws_pct = D.demand_gaps?(100-D.demand_gaps.coverage_pct).toFixed(0):'—';
const brand_gaps = (D.brands.only_amazon||[]).length;
const cov_pct = D.demand_gaps?D.demand_gaps.coverage_pct:0;
execHTML += `<div class="scr-label" style="margin-bottom:8px;color:var(--coral)">Complication</div>
<div class="complication-cards">
  <div class="comp-card"><div class="comp-label">Whitespace</div><div class="comp-value">${ws_pct}%</div><div class="comp-label">of Google demand has zero JM presence</div></div>
  <div class="comp-card"><div class="comp-label">Brand Gaps</div><div class="comp-value">${brand_gaps}</div><div class="comp-label">brands on Amazon/FK missing from JM</div></div>
  <div class="comp-card"><div class="comp-label">Coverage</div><div class="comp-value">${cov_pct}%</div><div class="comp-label">of addressable keywords captured</div></div>
</div>`;
execHTML += `<div class="scr-label" style="margin-bottom:12px;color:var(--teal)">Resolution — Top 5 Actions</div>`;
(ex.top_actions||[]).forEach((a,i)=>{
  execHTML += `<div class="action-card"><div class="action-num">${i+1}</div><div class="action-body"><div class="action-title">${a.action}</div><div class="action-meta">${pillHTML(a.impact,a.impact)} ${pillHTML(a.type==='Demand Gap'?'gap':'covered',a.type)} — ${a.rationale}</div></div><div class="action-gmv">${fmt(a.gmv_potential)}</div></div>`;
});
execHTML += `<div style="font-size:13px;color:var(--steel);margin:8px 0 0 56px">→ ${(D.actions||[]).length} total actions in Action Queue</div>`;
execHTML += `<div class="metrics-bar">`;
(ex.kpi_cards||[]).forEach(k=>{execHTML+=`<div class="mb-item"><div class="mb-value">${k.value}</div><div class="mb-label">${k.label}</div><div style="font-size:10px;color:var(--steel)">${k.delta}</div></div>`});
execHTML += `</div>`;
// Market context + Insight cards (merged from old Market Context tab)
const mkt=D.market||{};const cards=D.insight_cards||[];
if(mkt.market_size||mkt.cagr){execHTML+=`<div class="section-title" style="margin-top:32px">Market Context</div><div class="metric-grid cols-3"><div class="metric-card"><div class="label">Market Size</div><div class="value" style="font-size:24px">${mkt.market_size||'—'}</div></div><div class="metric-card"><div class="label">CAGR</div><div class="value">${mkt.cagr||'—'}</div></div><div class="metric-card"><div class="label">Key Segments</div><div style="font-size:13px;margin-top:8px;color:var(--navy)">${mkt.key_segments||'—'}</div></div></div>`}
if(cards.length){execHTML+=`<div class="section-title">Strategic Insights</div><div class="two-col">`;cards.forEach(c=>{const cls=c.impact==='High'?'impact-high':'impact-medium';execHTML+=`<div class="insight-card ${cls}"><div style="margin-bottom:8px">${pillHTML(c.impact,c.impact)} <span style="font-size:11px;color:var(--steel);margin-left:8px">${c.category}</span></div><div style="font-size:13px;color:var(--steel);margin-bottom:8px">${c.finding}</div><div class="so-what-box">So What? ${c.sowhat}</div></div>`});execHTML+=`</div>`}
execHTML += `</div>`;

// TAB 1: Action Queue
const actions=D.actions||[];
const totalGMV=actions.reduce((s,a)=>s+(a.gmv_potential||0),0);
const top3=actions.slice(0,3).reduce((s,a)=>s+(a.gmv_potential||0),0);
const top3P=totalGMV>0?Math.round(top3/totalGMV*100):0;
let actHTML=`<div class="tab" id="tab-actions"><div class="headline">There are ${actions.length} actions worth ${fmt(totalGMV)}/month. Top 3 = ${top3P}% of opportunity.</div>`;
actHTML+=`<div class="chart-container"><canvas id="chart-ie" height="300"></canvas></div>`;
// Top 5 action cards
actHTML+=`<div class="section-title">Top 5 Priority Actions</div>`;
actions.slice(0,5).forEach((a,i)=>{
  const tl=a.type==='Demand Gap'||a.type==='Rising Demand'?'Immediate':a.type==='Brand Gap'?'This Quarter':'Next Quarter';
  actHTML+=`<div class="action-card"><div class="action-num">${i+1}</div><div class="action-body"><div class="action-title">${a.action}</div><div class="action-meta">${pillHTML(a.impact,a.impact)} ${pillHTML(a.type==='Demand Gap'?'gap':'covered',a.type)} · ${a.effort} effort · ${tl}</div></div><div class="action-gmv">${fmt(a.gmv_potential)}</div></div>`;
});
if(actions.length>5){actHTML+=`<button class="show-more-btn" onclick="toggleAllActions(this)">Show all ${actions.length} actions ▾</button>`}
// Full table (hidden initially if >5)
const aTypes=[...new Set(actions.map(a=>a.type))];
actHTML+=`<div id="full-action-list" ${actions.length>5?'class="action-hidden"':''}>`;
actHTML+=`<div class="filter-pills"><div class="filter-pill active" onclick="filterA('all',this)">All</div>`;
aTypes.forEach(t=>{actHTML+=`<div class="filter-pill" onclick="filterA('${t}',this)">${t}</div>`});
actHTML+=`</div><div style="overflow-x:auto"><table id="atbl"><thead><tr><th>#</th><th>Type</th><th>Action</th><th>Impact</th><th>Est. GMV/mo</th><th>Effort</th><th>Timeline</th><th>Rationale</th></tr></thead><tbody>`;
actions.forEach(a=>{
  const tl=a.type==='Demand Gap'||a.type==='Rising Demand'?'Immediate':a.type==='Brand Gap'?'This Quarter':'Next Quarter';
  actHTML+=`<tr data-type="${a.type}"><td style="font-weight:700;color:var(--navy)">${a.priority}</td><td>${pillHTML(a.type==='Demand Gap'?'High':'Medium',a.type)}</td><td style="font-weight:500;color:var(--navy)">${a.action}</td><td>${pillHTML(a.impact,a.impact)}</td><td style="text-align:right;font-weight:700;color:var(--navy)">${fmt(a.gmv_potential)}</td><td>${a.effort}</td><td>${tl}</td><td style="font-size:12px">${a.rationale}</td></tr>`;
});
actHTML+=`</tbody><tfoot><tr class="takeaway-row"><td colspan="4">Total GMV</td><td style="text-align:right">${fmt(totalGMV)}/mo</td><td colspan="3">${actions.length} actions</td></tr></tfoot></table></div></div></div>`;

// TAB 2: Demand Gaps
const g=D.demand_gaps||{};
let gHTML=`<div class="tab" id="tab-gaps"><div class="headline">JioMart captures ${g.coverage_pct||0}% of demand. ${g.total_whitespace||0} whitespace keywords have zero JM presence.</div>`;
const wP=(100-(g.coverage_pct||0)).toFixed(0);
gHTML+=`<div class="stacked-bar"><div style="width:${g.coverage_pct||0}%;background:var(--teal)">${g.coverage_pct||0}% Covered</div><div style="width:${wP}%;background:var(--coral)">${wP}% Whitespace</div></div>`;
gHTML+=`<div class="chart-container"><canvas id="chart-dg" height="300"></canvas></div>`;
gHTML+=`<input class="search-input" placeholder="Search keywords..." oninput="searchT('gtbl',this.value)">`;
gHTML+=`<div class="section-title">Whitespace Keywords</div><div style="overflow-x:auto"><table id="gtbl" class="m-card-view"><thead><tr><th>#</th><th>Keyword</th><th>Google Vol</th><th>Competition</th><th>YoY</th><th>Est. GMV</th><th>Status</th></tr></thead><tbody>`;
(g.whitespace||[]).forEach((k,i)=>{gHTML+=`<tr><td data-label="#">${i+1}</td><td data-label="Keyword" style="font-weight:500;color:var(--navy)">${k.keyword}</td><td data-label="Google Vol" style="text-align:right">${fmtNum(k.google_vol)}</td><td data-label="Competition">${k.competition||'—'}</td><td data-label="YoY">${k.yoy_change||'—'}</td><td data-label="Est. GMV" style="text-align:right;font-weight:600">${fmt(k.gmv_opportunity)}</td><td data-label="Status">${pillHTML('gap','Whitespace')}</td></tr>`});
gHTML+=`</tbody></table></div>`;
gHTML+=`<div class="section-title" style="margin-top:32px">Covered Keywords</div><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Keyword</th><th>Google Vol</th><th>JM Vol</th><th>Competition</th><th>Status</th></tr></thead><tbody>`;
(g.coverage||[]).forEach((k,i)=>{gHTML+=`<tr><td>${i+1}</td><td style="font-weight:500;color:var(--navy)">${k.keyword}</td><td style="text-align:right">${fmtNum(k.google_vol)}</td><td style="text-align:right">${fmtNum(k.jm_volume)}</td><td>${k.competition||'—'}</td><td>${pillHTML('covered','Covered')}</td></tr>`});
gHTML+=`</tbody></table></div></div>`;

// TAB 3: Brand & Sourcing
const br=D.brands||{};const avail=D.data_availability||{};
const pr0=D.pricing||{};
const aS=pr0.amazon_stats||{};const fS=pr0.flipkart_stats||{};
const aM=Math.round(aS.Median||0);const fM=Math.round(fS.Median||0);
const pD=aM>0?Math.round((aM-fM)/aM*100):0;
const noAmz=!avail.amazon;const noFk=!avail.flipkart;
let bHTML=`<div class="tab" id="tab-brands">`;
if(noAmz&&noFk){bHTML+=`<div class="headline" style="border-left-color:var(--coral)">Amazon and Flipkart data not available. Upload the data files and re-run prepare_data.py to enable competitive analysis.</div>`}
else{bHTML+=`<div class="headline">${noAmz?'Amazon data not available. ':noFk?'Flipkart data not available. ':''}${!noAmz&&!noFk?(br.only_amazon||[]).length+' brands on Amazon missing from FK. Amazon median ₹'+fmtNum(aM)+' is '+pD+'% above Flipkart ₹'+fmtNum(fM)+'.':''}</div>`}
if(!noAmz||!noFk){bHTML+=`<div class="metric-grid cols-3">`;
if(!noAmz){bHTML+=`<div class="metric-card" style="border-left:4px solid var(--amz)"><div class="label">Amazon</div><div class="value" style="color:var(--amz)">₹${fmtNum(aM)}</div><div class="delta">Median · ${D.executive.kpi_cards[2].value} products</div></div>`}
if(!noFk){bHTML+=`<div class="metric-card" style="border-left:4px solid var(--fk)"><div class="label">Flipkart</div><div class="value" style="color:var(--fk)">₹${fmtNum(fM)}</div><div class="delta">Median · ${D.executive.kpi_cards[3].value} products</div></div>`}
if(!noAmz&&!noFk){bHTML+=`<div class="metric-card" style="border-left:4px solid var(--coral)"><div class="label">Price Delta</div><div class="value">${pD}%</div><div class="delta">Amazon premium</div></div>`}
bHTML+=`</div>`}
if(!noAmz){bHTML+=`<div class="section-title">Top Amazon Brands</div><div style="overflow-x:auto"><table class="m-card-view"><thead><tr><th>#</th><th>Brand</th><th>Products</th><th>Avg Price</th><th>Units/30d</th><th>Rating</th></tr></thead><tbody>`;
(br.amazon||[]).forEach((b,i)=>{bHTML+=`<tr><td data-label="#">${i+1}</td><td data-label="Brand" style="font-weight:600;color:var(--navy)">${b.Brand}</td><td data-label="Products">${b.Products||'—'}</td><td data-label="Avg Price">₹${fmtNum(Math.round(b.Avg_Price||0))}</td><td data-label="Units/30d">${fmtNum(Math.round(b.Total_Qty||0))}</td><td data-label="Rating">${(b.Avg_Rating||0).toFixed(1)}</td></tr>`});
bHTML+=`</tbody></table></div>`} else {bHTML+=`<div class="section-title">Amazon Brands</div><div style="background:var(--highlight);padding:20px;border-radius:8px;color:var(--steel);font-size:13px;margin-bottom:16px">Amazon data not available. Upload Amazon Top Sellers file to enable.</div>`}
if(!noFk){bHTML+=`<div class="section-title">Top Flipkart Brands</div><div style="overflow-x:auto"><table class="m-card-view"><thead><tr><th>#</th><th>Brand</th><th>Products</th><th>Avg Price</th><th>Ratings</th><th>Rating</th></tr></thead><tbody>`;
(br.flipkart||[]).forEach((b,i)=>{bHTML+=`<tr><td data-label="#">${i+1}</td><td data-label="Brand" style="font-weight:600;color:var(--navy)">${b.Brand}</td><td data-label="Products">${b.Products||'—'}</td><td data-label="Avg Price">₹${fmtNum(Math.round(b.Avg_Price||0))}</td><td data-label="Ratings">${fmtNum(Math.round(b.Total_Ratings||0))}</td><td data-label="Rating">${(b.Avg_Rating||0).toFixed(1)}</td></tr>`});
bHTML+=`</tbody></table></div>`} else {bHTML+=`<div class="section-title">Flipkart Brands</div><div style="background:var(--highlight);padding:20px;border-radius:8px;color:var(--steel);font-size:13px;margin-bottom:16px">Flipkart data not available. Upload Flipkart Best Sellers files to enable.</div>`}
if((br.market_leaders||[]).length){bHTML+=`<div class="section-title">Industry Leaders</div><div class="brand-cards">`;(br.market_leaders||[]).forEach(b=>{bHTML+=`<div class="brand-card"><div class="brand-name">${b}</div><div class="brand-meta">Verify JM listing</div></div>`});bHTML+=`</div>`}
bHTML+=`</div>`;

// TAB 4: Price Positioning
const pr=D.pricing||{};const aBands=pr.amazon_bands||{};const fBands=pr.flipkart_bands||{};const aS2=pr.amazon_stats||{};const fS2=pr.flipkart_stats||{};
const bLabels=Object.keys(aBands);
let prHTML=`<div class="tab" id="tab-pricing">`;
if(noAmz&&noFk){prHTML+=`<div class="headline" style="border-left-color:var(--coral)">Price positioning data not available. Upload Amazon and/or Flipkart data files to enable this analysis.</div></div>`;} else {
prHTML+=`<div class="headline">${noAmz?'Amazon data not available. Showing Flipkart only.':noFk?'Flipkart data not available. Showing Amazon only.':'Amazon median ₹'+fmtNum(aM)+' vs Flipkart ₹'+fmtNum(fM)+' ('+pD+'% delta). Target the ₹'+fmtNum(Math.round(aS.Q1||0))+'–₹'+fmtNum(Math.round(aS.Q3||0))+' range.'}</div>`;
prHTML+=`<div class="metric-grid cols-4">`;
if(!noAmz){prHTML+=`<div class="metric-card"><div class="label">AMZ Median</div><div class="value">₹${fmtNum(aM)}</div><div class="delta">Q1-Q3: ₹${fmtNum(Math.round(aS.Q1||0))}-₹${fmtNum(Math.round(aS.Q3||0))}</div></div><div class="metric-card"><div class="label">AMZ Mean</div><div class="value">₹${fmtNum(Math.round(aS.Mean||0))}</div><div class="delta">Indicates premium tail</div></div>`}
if(!noFk){prHTML+=`<div class="metric-card"><div class="label">FK Median</div><div class="value">₹${fmtNum(fM)}</div><div class="delta">Q1-Q3: ₹${fmtNum(Math.round(fS.Q1||0))}-₹${fmtNum(Math.round(fS.Q3||0))}</div></div><div class="metric-card"><div class="label">FK Mean</div><div class="value">₹${fmtNum(Math.round(fS.Mean||0))}</div><div class="delta">Lower positioning</div></div>`}
prHTML+=`</div>`;
if(bLabels.length||Object.keys(fBands).length){prHTML+=`<div class="chart-container"><canvas id="chart-pb" height="280"></canvas></div>`}
prHTML+=`<div class="two-col">`;
if(!noAmz){prHTML+=`<div><div class="section-title">Top Amazon Products</div><table class="m-card-view"><thead><tr><th>Product</th><th>Price</th><th>Units</th><th>Ratings</th><th>Rating</th></tr></thead><tbody>`;
(pr.amz_top_products||[]).slice(0,15).forEach(p=>{prHTML+=`<tr><td data-label="Product" style="font-size:12px">${(p.Title||p['Product Name']||'').substring(0,60)}</td><td data-label="Price">₹${fmtNum(Math.round(p['Offer Price']||0))}</td><td data-label="Units">${fmtNum(p['Qty bought in last 30 days']||0)}</td><td data-label="Ratings">${fmtNum(Math.round(p['Rating Count']||0))}</td><td data-label="Rating">${(p.Rating||0).toFixed(1)}</td></tr>`});
prHTML+=`</tbody></table></div>`} else {prHTML+=`<div><div class="section-title">Amazon Products</div><div style="background:var(--highlight);padding:20px;border-radius:8px;color:var(--steel);font-size:13px">Data not available</div></div>`}
if(!noFk){prHTML+=`<div><div class="section-title">Top Flipkart Products</div><table class="m-card-view"><thead><tr><th>Product</th><th>Price</th><th>Ratings</th><th>Rating</th></tr></thead><tbody>`;
(pr.fk_top_products||[]).slice(0,15).forEach(p=>{prHTML+=`<tr><td data-label="Product" style="font-size:12px">${(p['Product Name']||'').substring(0,60)}</td><td data-label="Price">₹${fmtNum(Math.round(p['Selling Price']||0))}</td><td data-label="Ratings">${fmtNum(Math.round(p['Rating Count']||0))}</td><td data-label="Rating">${(Number(p.Rating)||0).toFixed(1)}</td></tr>`});
prHTML+=`</tbody></table></div>`} else {prHTML+=`<div><div class="section-title">Flipkart Products</div><div style="background:var(--highlight);padding:20px;border-radius:8px;color:var(--steel);font-size:13px">Data not available</div></div>`}
prHTML+=`</div></div>`}

// TAB 5: Trends & Forecast
const fc=D.forecast||{};const fcKw=fc.keywords||[];
const gt=D.google_trends||{};const jmSeas=D.jm_seasonality||{};const ytSug=D.youtube_suggestions||{};
let fcHTML=`<div class="tab" id="tab-forecast"><div class="headline">${fcKw.length} keywords tracked. ${fcKw.filter(k=>k.cagr_pct>15).length} show >15% CAGR. ${(gt.interest_over_time||[]).length>0?'Google Trends: 12-month data loaded.':''}  ${(jmSeas.monthly_totals||[]).length} months of JM seasonality.</div>`;

// Google Trends section
if((gt.interest_over_time||[]).length>0){
fcHTML+=`<div class="section-title">Google Trends — 12 Month Interest (India)</div>`;
fcHTML+=`<div class="chart-container"><canvas id="chart-gtrends" height="280"></canvas></div>`;
// Breakout & rising queries
const bq=gt.breakout_queries||[];const rq=gt.related_queries||[];
if(bq.length||rq.length){fcHTML+=`<div class="two-col">`;
if(bq.length){fcHTML+=`<div><div class="section-title">Rising Queries</div><table><thead><tr><th>Query</th><th>Growth</th></tr></thead><tbody>`;bq.forEach(q=>{fcHTML+=`<tr><td style="font-weight:500;color:var(--navy)">${q.query||''}</td><td style="font-weight:600;color:var(--teal)">${q.value||'—'}</td></tr>`});fcHTML+=`</tbody></table></div>`}
if(rq.length){fcHTML+=`<div><div class="section-title">Top Related Queries</div><table><thead><tr><th>Query</th><th>Score</th></tr></thead><tbody>`;rq.forEach(q=>{fcHTML+=`<tr><td style="font-weight:500;color:var(--navy)">${q.query||''}</td><td>${q.value||'—'}</td></tr>`});fcHTML+=`</tbody></table></div>`}
fcHTML+=`</div>`}
// Regional interest
const reg=gt.regional||[];
if(reg.length){fcHTML+=`<div class="section-title">Regional Interest (India)</div><div class="chart-container"><canvas id="chart-gregion" height="220"></canvas></div>`}
} else if(gt.error){fcHTML+=`<div style="background:var(--highlight);padding:16px;border-radius:8px;margin-bottom:24px;font-size:13px;color:var(--steel)">Google Trends: ${gt.error}</div>`}

// JM Search Seasonality — actual data
const mTotals=jmSeas.monthly_totals||[];
if(mTotals.length>0){
fcHTML+=`<div class="section-title">JM Search Seasonality — Actual Monthly Volume</div>`;
fcHTML+=`<div class="chart-container"><canvas id="chart-jmseas" height="280"></canvas></div>`;
// Seasonal index grid
const sIdx=jmSeas.seasonal_index||{};const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const curM=new Date().toLocaleString('en',{month:'short'});
fcHTML+=`<div class="seasonal-grid">`;
months.forEach(m=>{const s=sIdx[m]||{};const dc=s.demand==='Very High'?'var(--coral)':s.demand==='High'?'var(--amber)':s.demand==='Low'?'var(--fk)':'var(--steel)';fcHTML+=`<div class="month-card${m===curM?' style="border-left:4px solid var(--navy)"':''}"><div class="month-name">${m}</div><div class="month-demand" style="color:${dc};font-weight:600">${s.demand||'—'}</div><div style="font-size:12px;color:var(--steel)">Index: ${s.index||'—'} · Vol: ${fmtNum(s.volume||0)}</div></div>`});
fcHTML+=`</div>`;
// Peak/Trough
const pk=jmSeas.peak_month||{};const tr=jmSeas.trough_month||{};
fcHTML+=`<div class="metric-grid cols-3" style="margin-top:16px"><div class="metric-card" style="border-left:4px solid var(--coral)"><div class="label">Peak Month</div><div class="value" style="font-size:20px">${pk.month||'—'}</div><div class="delta">${fmtNum(pk.volume||0)} searches</div></div><div class="metric-card" style="border-left:4px solid var(--fk)"><div class="label">Trough Month</div><div class="value" style="font-size:20px">${tr.month||'—'}</div><div class="delta">${fmtNum(tr.volume||0)} searches</div></div><div class="metric-card"><div class="label">Seasonality Ratio</div><div class="value" style="font-size:20px">${pk.volume&&tr.volume&&tr.volume>0?(pk.volume/tr.volume).toFixed(1)+'x':'—'}</div><div class="delta">Peak / Trough</div></div></div>`;
}

// YouTube Social Signals
const ytClusters=ytSug.clusters||[];
if(ytClusters.length>0){
fcHTML+=`<div class="section-title">Social Listening — YouTube Search Signals</div>`;
fcHTML+=`<div style="font-size:13px;color:var(--steel);margin-bottom:16px">${ytSug.total_signals||0} unique demand signals scraped from YouTube autocomplete</div>`;
ytClusters.forEach(c=>{
fcHTML+=`<div style="margin-bottom:16px"><div style="font-weight:600;color:var(--navy);margin-bottom:8px">"${c.query_term}" — ${c.count} signals</div><div style="display:flex;flex-wrap:wrap;gap:8px">`;
(c.suggestions||[]).forEach(s=>{fcHTML+=`<span class="pill" style="background:var(--highlight);color:var(--navy);padding:6px 14px;font-size:12px">${s}</span>`});
fcHTML+=`</div></div>`});
}

// Forecast table
fcHTML+=`<div class="section-title">Keyword Forecast</div>`;
fcHTML+=`<div style="overflow-x:auto"><table class="m-card-view"><thead><tr><th>#</th><th>Keyword</th><th>Current Vol</th><th>Forecast</th><th>YoY</th><th>CAGR %</th><th>Priority</th></tr></thead><tbody>`;
fcKw.slice(0,25).forEach((k,i)=>{const s=k.cagr_pct>15?'border-left:3px solid var(--teal)':'';fcHTML+=`<tr style="${s}"><td data-label="#">${i+1}</td><td data-label="Keyword" style="font-weight:500;color:var(--navy)">${k.keyword}</td><td data-label="Current Vol" style="text-align:right">${fmtNum(Math.round(k.current_vol||0))}</td><td data-label="Forecast" style="text-align:right">${fmtNum(Math.round(k.forecast_vol||0))}</td><td data-label="YoY" style="text-align:right">${(k.yoy_ratio||0).toFixed(2)}x</td><td data-label="CAGR %" style="text-align:right">${(k.cagr_pct||0).toFixed(1)}%</td><td data-label="Priority" style="text-align:right;font-weight:700">${(k.priority_score||0).toFixed(1)}</td></tr>`});
fcHTML+=`</tbody></table></div></div>`;

// TAB 6: AI Readiness
const aiR=D.ai_readiness||{};const aiInt=aiR.intents||{};const aiPAA=aiR.paa||{};
const aiDist=aiInt.distribution||[];const aiKw=aiInt.keywords||[];
const aiScore=aiInt.ai_readiness_score||0;const aiTotal=aiInt.total_keywords||0;
const paaQ=aiPAA.questions||[];const paaClusters=aiPAA.clusters||{};const paaTotal=aiPAA.total||0;
let aiHTML=`<div class="tab" id="tab-ai">`;
aiHTML+=`<div class="headline">AI Readiness Score: <strong>${aiScore}%</strong> — ${aiTotal} keywords classified across ${aiDist.length} intent buckets. ${paaTotal} question-format queries discovered for content strategy.</div>`;

// Score card + summary metrics
const scoreColor=aiScore>=50?'var(--teal)':aiScore>=30?'var(--amber)':'var(--coral)';
const transVol=aiDist.find(d=>d.intent==='Transactional');
const infoVol=aiDist.find(d=>d.intent==='Informational');
const compVol=aiDist.find(d=>d.intent==='Comparison');
aiHTML+=`<div class="metric-grid cols-4">`;
aiHTML+=`<div class="metric-card" style="border-left:4px solid ${scoreColor}"><div class="label">AI Readiness Score</div><div class="value" style="color:${scoreColor}">${aiScore}%</div><div class="delta">Informational + Comparison + Voice queries</div></div>`;
aiHTML+=`<div class="metric-card"><div class="label">Transactional</div><div class="value" style="font-size:24px">${transVol?transVol.pct:0}%</div><div class="delta">${transVol?fmtNum(transVol.count):0} keywords · Buy-intent</div></div>`;
aiHTML+=`<div class="metric-card"><div class="label">Informational</div><div class="value" style="font-size:24px">${infoVol?infoVol.pct:0}%</div><div class="delta">${infoVol?fmtNum(infoVol.count):0} keywords · Content opportunity</div></div>`;
aiHTML+=`<div class="metric-card"><div class="label">Comparison</div><div class="value" style="font-size:24px">${compVol?compVol.pct:0}%</div><div class="delta">${compVol?fmtNum(compVol.count):0} keywords · AI assistant fit</div></div>`;
aiHTML+=`</div>`;

// Donut chart + distribution table side by side
aiHTML+=`<div class="section-title">Query Intent Distribution</div>`;
aiHTML+=`<div class="two-col">`;
aiHTML+=`<div class="chart-container"><canvas id="chart-intent-donut" height="300"></canvas></div>`;
aiHTML+=`<div><table><thead><tr><th>Intent</th><th>Keywords</th><th>% Share</th><th>Volume</th><th>Vol %</th></tr></thead><tbody>`;
const intentColors={'Transactional':'#00A6A0','Informational':'#2874F0','Comparison':'#D4920B','Price-sensitive':'#E05A47','Voice/Long-tail':'#9B59B6','Navigational':'#4A6274'};
aiDist.forEach(d=>{
  const ic=intentColors[d.intent]||'#4A6274';
  aiHTML+=`<tr><td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${ic};margin-right:8px"></span><span style="font-weight:600;color:var(--navy)">${d.intent}</span></td><td style="text-align:right">${fmtNum(d.count)}</td><td style="text-align:right;font-weight:600">${d.pct}%</td><td style="text-align:right">${fmtNum(d.volume)}</td><td style="text-align:right">${d.vol_pct}%</td></tr>`;
});
aiHTML+=`</tbody></table>`;
aiHTML+=`<div class="so-what-box" style="margin-top:16px">So What? ${aiScore>=50?'High AI readiness — invest in conversational commerce, AI-powered product recommendations, and content marketing for informational queries.':aiScore>=30?'Moderate AI readiness — build content for comparison and informational queries while optimizing transactional funnel.':'Low AI readiness — demand is primarily transactional. Focus on search optimization, pricing, and direct conversion paths before AI content.'}</div>`;
aiHTML+=`</div></div>`;

// Top classified keywords table
aiHTML+=`<div class="section-title">Top Keywords by Intent</div>`;
aiHTML+=`<div class="filter-pills"><div class="filter-pill active" onclick="filterAI('all',this)">All</div>`;
aiDist.forEach(d=>{aiHTML+=`<div class="filter-pill" onclick="filterAI('${d.intent}',this)">${d.intent} (${d.count})</div>`});
aiHTML+=`</div>`;
aiHTML+=`<input class="search-input" placeholder="Search keywords..." oninput="searchT('aitbl',this.value)">`;
aiHTML+=`<div style="overflow-x:auto"><table id="aitbl" class="m-card-view"><thead><tr><th>#</th><th>Keyword</th><th>Volume</th><th>Source</th><th>Intent</th></tr></thead><tbody>`;
aiKw.slice(0,80).forEach((k,i)=>{
  const ic=intentColors[k.primary_intent]||'#4A6274';
  aiHTML+=`<tr data-intent="${k.primary_intent}"><td data-label="#">${i+1}</td><td data-label="Keyword" style="font-weight:500;color:var(--navy)">${k.keyword}</td><td data-label="Volume" style="text-align:right">${fmtNum(Math.round(k.volume||0))}</td><td data-label="Source">${k.source}</td><td data-label="Intent"><span class="pill" style="background:${ic}20;color:${ic}">${k.primary_intent}</span></td></tr>`;
});
aiHTML+=`</tbody></table></div>`;

// People Also Ask / Question Bank
if(paaTotal>0){
aiHTML+=`<div class="section-title" style="margin-top:32px">Question Bank — People Also Ask Proxy</div>`;
aiHTML+=`<div style="font-size:13px;color:var(--steel);margin-bottom:16px">${paaTotal} questions scraped from Google autocomplete. ${Object.keys(paaClusters).length} intent clusters identified.</div>`;
// Cluster cards
const clusterKeys=Object.keys(paaClusters);
aiHTML+=`<div class="metric-grid cols-3" style="margin-bottom:24px">`;
clusterKeys.forEach(ck=>{
  const cqs=paaClusters[ck]||[];
  aiHTML+=`<div class="metric-card" style="border-left:4px solid var(--teal)"><div class="label">${ck}</div><div class="value" style="font-size:24px">${cqs.length}</div><div class="delta">questions found</div></div>`;
});
aiHTML+=`</div>`;

// Question table
aiHTML+=`<div style="overflow-x:auto"><table class="m-card-view"><thead><tr><th>#</th><th>Question</th><th>Source Term</th><th>Intent Cluster</th></tr></thead><tbody>`;
paaQ.slice(0,60).forEach((q,i)=>{
  aiHTML+=`<tr><td data-label="#">${i+1}</td><td data-label="Question" style="font-weight:500;color:var(--navy)">${q.question}</td><td data-label="Source">${q.source_term}</td><td data-label="Intent"><span class="pill" style="background:rgba(0,166,160,0.12);color:var(--teal)">${q.intent}</span></td></tr>`;
});
aiHTML+=`</tbody></table></div>`;

// Content strategy so-what
aiHTML+=`<div class="so-what-box">Content Strategy: Create ${clusterKeys.filter(k=>k.includes('Best')||k.includes('choose')).length>0?'buying guides and comparison articles':'FAQ pages and product education content'} to capture ${paaTotal} question-format queries. These queries signal pre-purchase research — ideal for AI chatbot training data and SEO content.</div>`;
}
aiHTML+=`</div>`;

content.innerHTML = execHTML+actHTML+gHTML+bHTML+prHTML+fcHTML+aiHTML;

// Charts
setTimeout(()=>{
  const c1=document.getElementById('chart-ie');
  if(c1){const eM={'Low':1,'Medium':2,'High':3};const tC={'Demand Gap':'#E05A47','Brand Gap':'#2874F0','Price Gap':'#D4920B','Rising Demand':'#00A6A0'};const ds={};actions.forEach(a=>{if(!ds[a.type])ds[a.type]={label:a.type,data:[],backgroundColor:tC[a.type]||'#4A6274',pointRadius:8};ds[a.type].data.push({x:eM[a.effort]||2,y:a.gmv_potential||0})});new Chart(c1,{type:'scatter',data:{datasets:Object.values(ds)},options:{responsive:true,scales:{x:{min:0.5,max:3.5,ticks:{callback:v=>(['','Low','Medium','High'])[v]||''}},y:{beginAtZero:true,ticks:{callback:v=>v>=100000?'₹'+(v/100000).toFixed(0)+'L':v>=1000?'₹'+(v/1000).toFixed(0)+'K':'₹'+v}}},plugins:{title:{display:true,text:'Impact-Effort Matrix',font:{size:16,weight:'700'},color:'#051C2C'}}}})}
},100);
setTimeout(()=>{
  const c2=document.getElementById('chart-pb');
  if(c2){const aBd=D.pricing&&D.pricing.amazon_bands||{};const fBd=D.pricing&&D.pricing.flipkart_bands||{};const lb=Object.keys(aBd);if(lb.length){new Chart(c2,{type:'bar',data:{labels:lb,datasets:[{label:'Amazon',data:lb.map(l=>aBd[l]||0),backgroundColor:'rgba(255,153,0,0.8)',borderRadius:4},{label:'Flipkart',data:lb.map(l=>fBd[l]||0),backgroundColor:'rgba(40,116,240,0.8)',borderRadius:4}]},options:{responsive:true,indexAxis:'y',plugins:{title:{display:true,text:'Price Band: Amazon vs Flipkart',font:{size:16,weight:'700'},color:'#051C2C'}},scales:{x:{beginAtZero:true}}}})}}
},200);

// Demand gap horizontal bar chart
setTimeout(()=>{
  const c3=document.getElementById('chart-dg');
  if(c3){
    const ws=(D.demand_gaps&&D.demand_gaps.whitespace)||[];
    const top10=ws.slice(0,10).reverse();
    if(top10.length){
      new Chart(c3,{type:'bar',data:{labels:top10.map(k=>k.keyword.length>25?k.keyword.substring(0,25)+'…':k.keyword),datasets:[{label:'Google Search Vol',data:top10.map(k=>k.google_vol||0),backgroundColor:'rgba(224,90,71,0.8)',borderRadius:4},{label:'Est. GMV Opportunity',data:top10.map(k=>k.gmv_opportunity||0),backgroundColor:'rgba(0,166,160,0.8)',borderRadius:4}]},options:{indexAxis:'y',responsive:true,plugins:{title:{display:true,text:'Top 10 Whitespace Keywords — Demand vs GMV',font:{size:16,weight:'700'},color:'#051C2C'}},scales:{x:{beginAtZero:true,ticks:{callback:v=>v>=100000?'₹'+(v/100000).toFixed(0)+'L':v>=1000?(v/1000).toFixed(0)+'K':v}}}}})
    }
  }
},300);

// Google Trends line chart
setTimeout(()=>{
  const c4=document.getElementById('chart-gtrends');
  if(c4){
    const iot=D.google_trends&&D.google_trends.interest_over_time||[];
    const terms=D.google_trends&&D.google_trends.trend_terms||[];
    if(iot.length&&terms.length){
      const colors=['#051C2C','#E05A47','#00A6A0','#D4920B','#2874F0'];
      const datasets=terms.map((t,i)=>({label:t,data:iot.map(d=>d[t]||0),borderColor:colors[i%5],backgroundColor:colors[i%5]+'20',tension:0.3,fill:i===0,pointRadius:2,borderWidth:2}));
      new Chart(c4,{type:'line',data:{labels:iot.map(d=>{const dt=new Date(d.date);return dt.toLocaleDateString('en-IN',{month:'short',year:'2-digit'})}),datasets},options:{responsive:true,interaction:{intersect:false,mode:'index'},plugins:{title:{display:true,text:'Google Trends — Interest Over Time (India)',font:{size:16,weight:'700'},color:'#051C2C'},legend:{position:'bottom'}},scales:{y:{beginAtZero:true,max:100,title:{display:true,text:'Interest (0-100)'}}}}})}
  }
},400);

// JM Seasonality chart
setTimeout(()=>{
  const c5=document.getElementById('chart-jmseas');
  if(c5){
    const mT=D.jm_seasonality&&D.jm_seasonality.monthly_totals||[];
    if(mT.length){
      const kwCurves=D.jm_seasonality.keyword_curves||[];
      const datasets=[{label:'Total Volume',data:mT.map(m=>m.volume),borderColor:'#051C2C',backgroundColor:'rgba(5,28,44,0.1)',tension:0.3,fill:true,borderWidth:2.5,pointRadius:4,yAxisID:'y'}];
      const kColors=['#E05A47','#00A6A0','#D4920B','#2874F0','#FF9900'];
      kwCurves.forEach((kc,i)=>{
        const kData=mT.map(m=>{const match=kc.data.find(d=>d.month===m.month);return match?match.volume:0});
        datasets.push({label:kc.keyword,data:kData,borderColor:kColors[i%5],tension:0.3,borderWidth:1.5,pointRadius:2,borderDash:[4,4],yAxisID:'y2'})
      });
      new Chart(c5,{type:'line',data:{labels:mT.map(m=>m.month),datasets},options:{responsive:true,interaction:{intersect:false,mode:'index'},plugins:{title:{display:true,text:'JM Search Volume — Monthly Trend',font:{size:16,weight:'700'},color:'#051C2C'},legend:{position:'bottom'}},scales:{y:{beginAtZero:true,title:{display:true,text:'Total Volume'},position:'left'},y2:{beginAtZero:true,display:false,position:'right',grid:{drawOnChartArea:false}}}}})
    }
  }
},500);

// Google Trends regional chart
setTimeout(()=>{
  const c6=document.getElementById('chart-gregion');
  if(c6){
    const reg=D.google_trends&&D.google_trends.regional||[];
    if(reg.length){
      new Chart(c6,{type:'bar',data:{labels:reg.map(r=>r.region),datasets:[{label:'Interest',data:reg.map(r=>r.interest),backgroundColor:'rgba(5,28,44,0.8)',borderRadius:4}]},options:{indexAxis:'y',responsive:true,plugins:{title:{display:true,text:'Regional Interest — Top States',font:{size:16,weight:'700'},color:'#051C2C'},legend:{display:false}},scales:{x:{beginAtZero:true,max:100}}}})
    }
  }
},600);

// AI Readiness intent donut chart
setTimeout(()=>{
  const c7=document.getElementById('chart-intent-donut');
  if(c7){
    const dist=D.ai_readiness&&D.ai_readiness.intents&&D.ai_readiness.intents.distribution||[];
    if(dist.length){
      const iColors={'Transactional':'#00A6A0','Informational':'#2874F0','Comparison':'#D4920B','Price-sensitive':'#E05A47','Voice/Long-tail':'#9B59B6','Navigational':'#4A6274'};
      new Chart(c7,{type:'doughnut',data:{labels:dist.map(d=>d.intent),datasets:[{data:dist.map(d=>d.count),backgroundColor:dist.map(d=>iColors[d.intent]||'#4A6274'),borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,cutout:'55%',plugins:{title:{display:true,text:'Query Intent Mix',font:{size:16,weight:'700'},color:'#051C2C'},legend:{position:'bottom',labels:{padding:16,font:{size:12}}}}}})
    }
  }
},700);

function filterAI(intent,el){document.querySelectorAll('.filter-pills .filter-pill').forEach(p=>p.classList.remove('active'));el.classList.add('active');document.querySelectorAll('#aitbl tbody tr').forEach(r=>{r.style.display=(intent==='all'||r.dataset.intent===intent)?'':'none'})}
function togAcc(id){const b=document.getElementById(id);const i=document.getElementById('i-'+id);b.classList.toggle('open');i.textContent=b.classList.contains('open')?'▾':'▸'}
function searchT(tid,q){const t=document.getElementById(tid);if(!t)return;t.querySelectorAll('tbody tr').forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q.toLowerCase())?'':'none'})}
function filterA(type,el){document.querySelectorAll('.filter-pill').forEach(p=>p.classList.remove('active'));el.classList.add('active');document.querySelectorAll('#atbl tbody tr').forEach(r=>{r.style.display=(type==='all'||r.dataset.type===type)?'':'none'})}
function toggleText(id,btn){const el=document.getElementById(id);el.classList.toggle('expanded');btn.textContent=el.classList.contains('expanded')?'Show less':'Read more'}
function toggleAllActions(btn){const el=document.getElementById('full-action-list');el.classList.toggle('action-hidden');btn.textContent=el.classList.contains('action-hidden')?'Show all '+actions.length+' actions ▾':'Collapse ▴'}

// Auto-expand SCR text if short (< 100 chars)
setTimeout(()=>{const sit=document.getElementById('scr-sit');if(sit&&sit.scrollHeight<=60){sit.classList.add('expanded');const btn=sit.nextElementSibling;if(btn)btn.style.display='none'}},50);
"""
