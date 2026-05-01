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
    json_str = json.dumps(dashboard_data, default=str)
    compressed = gzip.compress(json_str.encode("utf-8"))
    b64 = base64.b64encode(compressed).decode("ascii")

    category = results.get("category", "Category")
    gen_date = results.get("generated_date", "")

    return _build_html(category, gen_date, b64)


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
        "tables": {
            "jm_keywords": results.get("jm_keywords") or [],
            "kp_keywords": (results.get("kp_keywords") or [])[:200],
            "amz_products": results.get("amz_top_products") or [],
            "fk_products": (results.get("fk_top_products") or [])[:50],
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
<div class="nav" id="nav"></div>
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
@media(max-width:768px) { .header{padding:24px} .header h1{font-size:24px} .nav{padding:0 16px} .nav a{margin-right:16px;font-size:12px} .container{padding:16px} .metric-grid.cols-3,.metric-grid.cols-4,.metric-grid.cols-6{grid-template-columns:1fr} .two-col{grid-template-columns:1fr} .complication-cards{grid-template-columns:1fr} .metrics-bar{grid-template-columns:repeat(3,1fr)} .seasonal-grid{grid-template-columns:repeat(2,1fr)} .brand-cards{grid-template-columns:1fr} }
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
  {id:'pricing',label:'Price Positioning'},{id:'forecast',label:'Forecast & Planning'},
  {id:'market',label:'Market Context'},{id:'tables',label:'Data Tables'}
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
execHTML += `<div class="scr-banner"><div class="scr-label">Situation</div>${ex.situation}</div>`;
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
execHTML += `</div></div>`;

// TAB 1: Action Queue
const actions=D.actions||[];
const totalGMV=actions.reduce((s,a)=>s+(a.gmv_potential||0),0);
const top3=actions.slice(0,3).reduce((s,a)=>s+(a.gmv_potential||0),0);
const top3P=totalGMV>0?Math.round(top3/totalGMV*100):0;
let actHTML=`<div class="tab" id="tab-actions"><div class="headline">There are ${actions.length} actions worth ${fmt(totalGMV)}/month. Top 3 = ${top3P}% of opportunity.</div>`;
actHTML+=`<div class="chart-container"><canvas id="chart-ie" height="300"></canvas></div>`;
const aTypes=[...new Set(actions.map(a=>a.type))];
actHTML+=`<div class="filter-pills"><div class="filter-pill active" onclick="filterA('all',this)">All</div>`;
aTypes.forEach(t=>{actHTML+=`<div class="filter-pill" onclick="filterA('${t}',this)">${t}</div>`});
actHTML+=`</div><div style="overflow-x:auto"><table id="atbl"><thead><tr><th>#</th><th>Type</th><th>Action</th><th>Impact</th><th>Est. GMV/mo</th><th>Effort</th><th>Timeline</th><th>Rationale</th></tr></thead><tbody>`;
actions.forEach(a=>{
  const tl=a.type==='Demand Gap'||a.type==='Rising Demand'?'Immediate':a.type==='Brand Gap'?'This Quarter':'Next Quarter';
  actHTML+=`<tr data-type="${a.type}"><td style="font-weight:700;color:var(--navy)">${a.priority}</td><td>${pillHTML(a.type==='Demand Gap'?'High':'Medium',a.type)}</td><td style="font-weight:500;color:var(--navy)">${a.action}</td><td>${pillHTML(a.impact,a.impact)}</td><td style="text-align:right;font-weight:700;color:var(--navy)">${fmt(a.gmv_potential)}</td><td>${a.effort}</td><td>${tl}</td><td style="font-size:12px">${a.rationale}</td></tr>`;
});
actHTML+=`</tbody><tfoot><tr class="takeaway-row"><td colspan="4">Total GMV</td><td style="text-align:right">${fmt(totalGMV)}/mo</td><td colspan="3">${actions.length} actions</td></tr></tfoot></table></div></div>`;

// TAB 2: Demand Gaps
const g=D.demand_gaps||{};
let gHTML=`<div class="tab" id="tab-gaps"><div class="headline">JioMart captures ${g.coverage_pct||0}% of demand. ${g.total_whitespace||0} whitespace keywords have zero JM presence.</div>`;
const wP=(100-(g.coverage_pct||0)).toFixed(0);
gHTML+=`<div class="stacked-bar"><div style="width:${g.coverage_pct||0}%;background:var(--teal)">${g.coverage_pct||0}% Covered</div><div style="width:${wP}%;background:var(--coral)">${wP}% Whitespace</div></div>`;
gHTML+=`<input class="search-input" placeholder="Search keywords..." oninput="searchT('gtbl',this.value)">`;
gHTML+=`<div class="section-title">Whitespace Keywords</div><div style="overflow-x:auto"><table id="gtbl"><thead><tr><th>#</th><th>Keyword</th><th>Google Vol</th><th>Competition</th><th>YoY</th><th>Est. GMV</th><th>Status</th></tr></thead><tbody>`;
(g.whitespace||[]).forEach((k,i)=>{gHTML+=`<tr><td>${i+1}</td><td style="font-weight:500;color:var(--navy)">${k.keyword}</td><td style="text-align:right">${fmtNum(k.google_vol)}</td><td>${k.competition||'—'}</td><td>${k.yoy_change||'—'}</td><td style="text-align:right;font-weight:600">${fmt(k.gmv_opportunity)}</td><td>${pillHTML('gap','Whitespace')}</td></tr>`});
gHTML+=`</tbody></table></div>`;
gHTML+=`<div class="section-title" style="margin-top:32px">Covered Keywords</div><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Keyword</th><th>Google Vol</th><th>JM Vol</th><th>Competition</th><th>Status</th></tr></thead><tbody>`;
(g.coverage||[]).forEach((k,i)=>{gHTML+=`<tr><td>${i+1}</td><td style="font-weight:500;color:var(--navy)">${k.keyword}</td><td style="text-align:right">${fmtNum(k.google_vol)}</td><td style="text-align:right">${fmtNum(k.jm_volume)}</td><td>${k.competition||'—'}</td><td>${pillHTML('covered','Covered')}</td></tr>`});
gHTML+=`</tbody></table></div></div>`;

// TAB 3: Brand & Sourcing
const br=D.brands||{};
const pr0=D.pricing||{};
const aS=pr0.amazon_stats||{};const fS=pr0.flipkart_stats||{};
const aM=Math.round(aS.Median||0);const fM=Math.round(fS.Median||0);
const pD=aM>0?Math.round((aM-fM)/aM*100):0;
let bHTML=`<div class="tab" id="tab-brands"><div class="headline">${(br.only_amazon||[]).length} brands on Amazon missing from FK. Amazon median ₹${fmtNum(aM)} is ${pD}% above Flipkart ₹${fmtNum(fM)}.</div>`;
bHTML+=`<div class="metric-grid cols-3"><div class="metric-card" style="border-left:4px solid var(--amz)"><div class="label">Amazon</div><div class="value" style="color:var(--amz)">₹${fmtNum(aM)}</div><div class="delta">Median · ${D.executive.kpi_cards[2].value} products</div></div><div class="metric-card" style="border-left:4px solid var(--fk)"><div class="label">Flipkart</div><div class="value" style="color:var(--fk)">₹${fmtNum(fM)}</div><div class="delta">Median · ${D.executive.kpi_cards[3].value} products</div></div><div class="metric-card" style="border-left:4px solid var(--coral)"><div class="label">Price Delta</div><div class="value">${pD}%</div><div class="delta">Amazon premium</div></div></div>`;
bHTML+=`<div class="section-title">Top Amazon Brands</div><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Brand</th><th>Products</th><th>Avg Price</th><th>Units/30d</th><th>Rating</th></tr></thead><tbody>`;
(br.amazon||[]).forEach((b,i)=>{bHTML+=`<tr><td>${i+1}</td><td style="font-weight:600;color:var(--navy)">${b.Brand}</td><td>${b.Products||'—'}</td><td>₹${fmtNum(Math.round(b.Avg_Price||0))}</td><td>${fmtNum(Math.round(b.Total_Qty||0))}</td><td>${(b.Avg_Rating||0).toFixed(1)}</td></tr>`});
bHTML+=`</tbody></table></div>`;
bHTML+=`<div class="section-title">Top Flipkart Brands</div><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Brand</th><th>Products</th><th>Avg Price</th><th>Ratings</th><th>Rating</th></tr></thead><tbody>`;
(br.flipkart||[]).forEach((b,i)=>{bHTML+=`<tr><td>${i+1}</td><td style="font-weight:600;color:var(--navy)">${b.Brand}</td><td>${b.Products||'—'}</td><td>₹${fmtNum(Math.round(b.Avg_Price||0))}</td><td>${fmtNum(Math.round(b.Total_Ratings||0))}</td><td>${(b.Avg_Rating||0).toFixed(1)}</td></tr>`});
bHTML+=`</tbody></table></div>`;
if((br.market_leaders||[]).length){bHTML+=`<div class="section-title">Industry Leaders</div><div class="brand-cards">`;(br.market_leaders||[]).forEach(b=>{bHTML+=`<div class="brand-card"><div class="brand-name">${b}</div><div class="brand-meta">Verify JM listing</div></div>`});bHTML+=`</div>`}
bHTML+=`</div>`;

// TAB 4: Price Positioning
const pr=D.pricing||{};const aBands=pr.amazon_bands||{};const fBands=pr.flipkart_bands||{};const aS2=pr.amazon_stats||{};const fS2=pr.flipkart_stats||{};
const bLabels=Object.keys(aBands);
let prHTML=`<div class="tab" id="tab-pricing"><div class="headline">Amazon median ₹${fmtNum(aM)} vs Flipkart ₹${fmtNum(fM)} (${pD}% delta). Target the ₹${fmtNum(Math.round(aS.Q1||0))}–₹${fmtNum(Math.round(aS.Q3||0))} range.</div>`;
prHTML+=`<div class="metric-grid cols-4"><div class="metric-card"><div class="label">AMZ Median</div><div class="value">₹${fmtNum(aM)}</div><div class="delta">Q1-Q3: ₹${fmtNum(Math.round(aS.Q1||0))}-₹${fmtNum(Math.round(aS.Q3||0))}</div></div><div class="metric-card"><div class="label">FK Median</div><div class="value">₹${fmtNum(fM)}</div><div class="delta">Q1-Q3: ₹${fmtNum(Math.round(fS.Q1||0))}-₹${fmtNum(Math.round(fS.Q3||0))}</div></div><div class="metric-card"><div class="label">AMZ Mean</div><div class="value">₹${fmtNum(Math.round(aS.Mean||0))}</div><div class="delta">Indicates premium tail</div></div><div class="metric-card"><div class="label">FK Mean</div><div class="value">₹${fmtNum(Math.round(fS.Mean||0))}</div><div class="delta">Lower positioning</div></div></div>`;
prHTML+=`<div class="chart-container"><canvas id="chart-pb" height="280"></canvas></div>`;
prHTML+=`<div class="two-col"><div><div class="section-title">Top Amazon Products</div><table><thead><tr><th>Product</th><th>Price</th><th>Units</th><th>Rating</th></tr></thead><tbody>`;
(pr.amz_top_products||[]).slice(0,15).forEach(p=>{prHTML+=`<tr><td style="font-size:12px">${(p.Title||p['Product Name']||'').substring(0,60)}</td><td>₹${fmtNum(Math.round(p['Offer Price']||0))}</td><td>${fmtNum(p['Qty bought in last 30 days']||0)}</td><td>${(p.Rating||0).toFixed(1)}</td></tr>`});
prHTML+=`</tbody></table></div><div><div class="section-title">Top Flipkart Products</div><table><thead><tr><th>Product</th><th>Price</th><th>Ratings</th><th>Rating</th></tr></thead><tbody>`;
(pr.fk_top_products||[]).slice(0,15).forEach(p=>{prHTML+=`<tr><td style="font-size:12px">${(p['Product Name']||'').substring(0,60)}</td><td>₹${fmtNum(Math.round(p['Selling Price']||0))}</td><td>${fmtNum(Math.round(p['Rating Count']||0))}</td><td>${(Number(p.Rating)||0).toFixed(1)}</td></tr>`});
prHTML+=`</tbody></table></div></div></div>`;

// TAB 5: Forecast & Planning
const fc=D.forecast||{};const fcKw=fc.keywords||[];
let fcHTML=`<div class="tab" id="tab-forecast"><div class="headline">${fcKw.length} keywords tracked. ${fcKw.filter(k=>k.cagr_pct>15).length} show >15% CAGR — prioritize these.</div>`;
fcHTML+=`<div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Keyword</th><th>Current Vol</th><th>Forecast</th><th>YoY</th><th>CAGR %</th><th>Priority</th></tr></thead><tbody>`;
fcKw.slice(0,25).forEach((k,i)=>{const s=k.cagr_pct>15?'border-left:3px solid var(--teal)':'';fcHTML+=`<tr style="${s}"><td>${i+1}</td><td style="font-weight:500;color:var(--navy)">${k.keyword}</td><td style="text-align:right">${fmtNum(Math.round(k.current_vol||0))}</td><td style="text-align:right">${fmtNum(Math.round(k.forecast_vol||0))}</td><td style="text-align:right">${(k.yoy_ratio||0).toFixed(2)}x</td><td style="text-align:right">${(k.cagr_pct||0).toFixed(1)}%</td><td style="text-align:right;font-weight:700">${(k.priority_score||0).toFixed(1)}</td></tr>`});
fcHTML+=`</tbody></table></div>`;
const seasonal=D.seasonal||{};const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
fcHTML+=`<div class="section-title">Seasonal Calendar</div><div class="seasonal-grid">`;
const curM=new Date().toLocaleString('en',{month:'short'});
months.forEach(m=>{const s=seasonal[m]||{};const dc=s.demand==='Very High'?'var(--coral)':s.demand==='High'?'var(--amber)':'var(--steel)';fcHTML+=`<div class="month-card${m===curM?' style="border-left:4px solid var(--navy)"':''}"><div class="month-name">${m}</div><div class="month-demand" style="color:${dc};font-weight:600">${s.demand||'Medium'}</div><div class="month-note">${s.note||''}</div></div>`});
fcHTML+=`</div></div>`;

// TAB 6: Market Context
const mkt=D.market||{};const cards=D.insight_cards||[];
let mHTML=`<div class="tab" id="tab-market"><div class="headline">${D.category} — ${mkt.market_size||'Enable API for data'}. CAGR: ${mkt.cagr||'—'}.</div>`;
mHTML+=`<div class="metric-grid cols-3"><div class="metric-card"><div class="label">Market Size</div><div class="value" style="font-size:24px">${mkt.market_size||'—'}</div></div><div class="metric-card"><div class="label">CAGR</div><div class="value">${mkt.cagr||'—'}</div></div><div class="metric-card"><div class="label">Key Segments</div><div style="font-size:13px;margin-top:8px;color:var(--navy)">${mkt.key_segments||'—'}</div></div></div>`;
if(cards.length){mHTML+=`<div class="section-title">Strategic Insights</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">`;cards.forEach(c=>{const cls=c.impact==='High'?'impact-high':'impact-medium';mHTML+=`<div class="insight-card ${cls}"><div style="margin-bottom:8px">${pillHTML(c.impact,c.impact)} <span style="font-size:11px;color:var(--steel);margin-left:8px">${c.category}</span></div><div style="font-size:13px;color:var(--steel);margin-bottom:8px">${c.finding}</div><div class="so-what-box">So What? ${c.sowhat}</div></div>`});mHTML+=`</div>`}
const segs=mkt.price_segments||{};
if(Object.keys(segs).length){mHTML+=`<div class="section-title">Price Segments</div><div class="metric-grid cols-4">`;Object.entries(segs).forEach(([k,v])=>{mHTML+=`<div class="metric-card"><div class="label">${k}</div><div style="font-size:13px;margin-top:8px;color:var(--navy)">${v}</div></div>`});mHTML+=`</div>`}
if((mkt.top_india_brands||[]).length){mHTML+=`<div class="section-title">Key Brands</div><div class="brand-cards">`;mkt.top_india_brands.forEach(b=>{mHTML+=`<div class="brand-card"><div class="brand-name">${b}</div></div>`});mHTML+=`</div>`}
mHTML+=`</div>`;

// TAB 7: Data Tables
const tbl=D.tables||{};
let tHTML=`<div class="tab" id="tab-tables"><div class="headline">Reference data for deeper analysis.</div>`;
function mkAcc(title,id,hdr,rows,fn){let h=`<div class="accordion-header" onclick="togAcc('${id}')">${title} (${rows.length}) <span id="i-${id}">▸</span></div><div class="accordion-body" id="${id}"><input class="search-input" placeholder="Search..." oninput="searchT('t-${id}',this.value)"><div style="overflow-x:auto;max-height:500px"><table id="t-${id}"><thead><tr>${hdr.map(h=>'<th>'+h+'</th>').join('')}</tr></thead><tbody>`;rows.forEach(r=>{h+=fn(r)});h+=`</tbody></table></div></div>`;return h}
tHTML+=mkAcc('JM Keywords','jm',['Keyword','Total Vol','Months','Growth %','CAGR %'],tbl.jm_keywords||[],r=>`<tr><td>${r.Keyword||''}</td><td style="text-align:right">${fmtNum(r.total_vol||0)}</td><td>${r.months_present||'—'}</td><td>${r.growth_pct?r.growth_pct.toFixed(0)+'%':'—'}</td><td>${r.cagr_pct?r.cagr_pct.toFixed(1)+'%':'—'}</td></tr>`);
tHTML+=mkAcc('Google KP','kp',['Keyword','Avg Monthly','Competition','3m Change','YoY'],(tbl.kp_keywords||[]).slice(0,100),r=>`<tr><td>${r.Keyword||''}</td><td style="text-align:right">${fmtNum(r['Avg. monthly searches']||0)}</td><td>${r.Competition||'—'}</td><td>${r['Three month change']||'—'}</td><td>${r['YoY change']||'—'}</td></tr>`);
tHTML+=mkAcc('Amazon Products','amz',['Title','Price','Units','Rating'],tbl.amz_products||[],r=>`<tr><td style="font-size:12px">${(r.Title||'').substring(0,80)}</td><td>₹${fmtNum(Math.round(r['Offer Price']||0))}</td><td>${fmtNum(r['Qty bought in last 30 days']||0)}</td><td>${(r.Rating||0).toFixed(1)}</td></tr>`);
tHTML+=mkAcc('Flipkart Products','fk',['Product','Price','Ratings','Rating'],tbl.fk_products||[],r=>`<tr><td style="font-size:12px">${(r['Product Name']||'').substring(0,80)}</td><td>₹${fmtNum(Math.round(r['Selling Price']||0))}</td><td>${fmtNum(Math.round(r['Rating Count']||0))}</td><td>${(Number(r.Rating)||0).toFixed(1)}</td></tr>`);
tHTML+=`</div>`;

content.innerHTML = execHTML+actHTML+gHTML+bHTML+prHTML+fcHTML+mHTML+tHTML;

// Charts
setTimeout(()=>{
  const c1=document.getElementById('chart-ie');
  if(c1){const eM={'Low':1,'Medium':2,'High':3};const tC={'Demand Gap':'#E05A47','Brand Gap':'#2874F0','Price Gap':'#D4920B','Rising Demand':'#00A6A0'};const ds={};actions.forEach(a=>{if(!ds[a.type])ds[a.type]={label:a.type,data:[],backgroundColor:tC[a.type]||'#4A6274',pointRadius:8};ds[a.type].data.push({x:eM[a.effort]||2,y:a.gmv_potential||0})});new Chart(c1,{type:'scatter',data:{datasets:Object.values(ds)},options:{responsive:true,scales:{x:{min:0.5,max:3.5,ticks:{callback:v=>(['','Low','Medium','High'])[v]||''}},y:{beginAtZero:true,ticks:{callback:v=>v>=100000?'₹'+(v/100000).toFixed(0)+'L':v>=1000?'₹'+(v/1000).toFixed(0)+'K':'₹'+v}}},plugins:{title:{display:true,text:'Impact-Effort Matrix',font:{size:16,weight:'700'},color:'#051C2C'}}}})}
},100);
setTimeout(()=>{
  const c2=document.getElementById('chart-pb');
  if(c2){const aBd=D.pricing&&D.pricing.amazon_bands||{};const fBd=D.pricing&&D.pricing.flipkart_bands||{};const lb=Object.keys(aBd);if(lb.length){new Chart(c2,{type:'bar',data:{labels:lb,datasets:[{label:'Amazon',data:lb.map(l=>aBd[l]||0),backgroundColor:'rgba(255,153,0,0.8)',borderRadius:4},{label:'Flipkart',data:lb.map(l=>fBd[l]||0),backgroundColor:'rgba(40,116,240,0.8)',borderRadius:4}]},options:{responsive:true,indexAxis:'y',plugins:{title:{display:true,text:'Price Band: Amazon vs Flipkart',font:{size:16,weight:'700'},color:'#051C2C'}},scales:{x:{beginAtZero:true}}}})}}
},200);

function togAcc(id){const b=document.getElementById(id);const i=document.getElementById('i-'+id);b.classList.toggle('open');i.textContent=b.classList.contains('open')?'▾':'▸'}
function searchT(tid,q){const t=document.getElementById(tid);if(!t)return;t.querySelectorAll('tbody tr').forEach(r=>{r.style.display=r.textContent.toLowerCase().includes(q.toLowerCase())?'':'none'})}
function filterA(type,el){document.querySelectorAll('.filter-pill').forEach(p=>p.classList.remove('active'));el.classList.add('active');document.querySelectorAll('#atbl tbody tr').forEach(r=>{r.style.display=(type==='all'||r.dataset.type===type)?'':'none'})}
"""
