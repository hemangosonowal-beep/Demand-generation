"""
Demand Analysis Pipeline — core analysis engine.

Takes pre-loaded DataFrames + category name → returns structured analysis results.
"""

import pandas as pd
import numpy as np
from thefuzz import fuzz
from datetime import datetime
import re
import json
import urllib.request
import urllib.parse


# ─────────────────────────────────────────────────────────────────────
# STEP 1: Resolve category → keyword list from hierarchy
# ─────────────────────────────────────────────────────────────────────
def resolve_category(hierarchy: pd.DataFrame, category_input: str) -> list:
    """Resolve user-entered category to a list of hierarchy names (L2/L3/L4)."""
    cat_lower = category_input.strip().lower()
    keywords = set()

    # Try AOP_L2 first
    for level, children in [
        ("AOP_L2", ["L2", "L3", "L4"]),
        ("L2", ["L3", "L4"]),
        ("L3", ["L4"]),
        ("L4", []),
    ]:
        if level not in hierarchy.columns:
            continue
        mask = hierarchy[level].str.lower() == cat_lower
        if mask.any():
            sub = hierarchy[mask]
            keywords.add(category_input)
            for child in children:
                if child in sub.columns:
                    keywords.update(sub[child].unique())
            cleaned = _clean_keywords(keywords)
            if cleaned:
                return cleaned

    # Fuzzy fallback
    all_names = set()
    for col in ["L2", "L3", "L4"]:
        if col in hierarchy.columns:
            all_names.update(hierarchy[col].unique())
    for name in all_names:
        if fuzz.token_sort_ratio(cat_lower, str(name).lower()) >= 75:
            keywords.add(name)
    return _clean_keywords(keywords)


def _clean_keywords(kw_set):
    return sorted(
        {str(k).strip() for k in kw_set if str(k).strip().lower() not in ("nan", "none", "")}
    )


# ─────────────────────────────────────────────────────────────────────
# STEP 2: Fuzzy match keywords against data
# ─────────────────────────────────────────────────────────────────────
def fuzzy_match_keywords(category_keywords: list, data_keywords) -> set:
    """Match category names against search keywords using word-level strategies."""
    matched = set()
    cat_lower = [str(c).lower().strip() for c in category_keywords]

    # Pre-filter: build word set from category keywords
    cat_words = set()
    for c in cat_lower:
        cat_words.update(c.split())

    for dk in data_keywords:
        dk_lower = str(dk).lower().strip()
        dk_words = set(dk_lower.split())

        # Quick pre-filter
        if not (cat_words & dk_words):
            continue

        for cat in cat_lower:
            if len(cat) < 3:
                continue
            cat_w = set(cat.split())

            # Strategy 1: all words containment
            if cat_w.issubset(dk_words):
                matched.add(dk)
                break

            # Strategy 2: singular/plural
            cat_stems = {w.rstrip("s") for w in cat_w}
            dk_stems = {w.rstrip("s") for w in dk_words}
            if cat_stems.issubset(dk_stems):
                matched.add(dk)
                break

            # Strategy 3: tight fuzzy
            if fuzz.token_set_ratio(cat, dk_lower) >= 90 and fuzz.ratio(cat, dk_lower) >= 70:
                matched.add(dk)
                break

    return matched


# ─────────────────────────────────────────────────────────────────────
# STEP 2b: Google Trends via pytrends
# ─────────────────────────────────────────────────────────────────────
def fetch_google_trends(category: str, top_keywords: list) -> dict:
    """Fetch Google Trends data for category and top keywords.

    Returns dict with interest_over_time, breakout_queries, regional data.
    Gracefully returns empty dict on failure (pytrends can be flaky).
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return {"error": "pytrends not installed"}

    result = {
        "interest_over_time": [],
        "breakout_queries": [],
        "related_queries": [],
        "regional": [],
    }

    try:
        pytrends = TrendReq(hl="en-IN", tz=330, timeout=(10, 25))

        # Use category + top 4 keywords (max 5 terms for pytrends)
        terms = [category] + [k for k in top_keywords[:4] if k.lower() != category.lower()]
        terms = terms[:5]

        pytrends.build_payload(terms, cat=0, timeframe="today 12-m", geo="IN")

        # Interest over time
        iot = pytrends.interest_over_time()
        if not iot.empty and "isPartial" in iot.columns:
            iot = iot.drop(columns=["isPartial"])
        if not iot.empty:
            iot_data = []
            for date_idx, row in iot.iterrows():
                entry = {"date": date_idx.strftime("%Y-%m-%d")}
                for col in iot.columns:
                    entry[col] = int(row[col])
                iot_data.append(entry)
            result["interest_over_time"] = iot_data
            result["trend_terms"] = list(iot.columns)

        # Related queries for the main category term
        try:
            related = pytrends.related_queries()
            if category in related and related[category]:
                top_q = related[category].get("top")
                rising_q = related[category].get("rising")
                if top_q is not None and not top_q.empty:
                    result["related_queries"] = top_q.head(10).to_dict("records")
                if rising_q is not None and not rising_q.empty:
                    result["breakout_queries"] = rising_q.head(10).to_dict("records")
        except Exception:
            pass

        # Regional interest
        try:
            region = pytrends.interest_by_region(resolution="REGION", inc_low_vol=True)
            if not region.empty and category in region.columns:
                reg_data = region[category].sort_values(ascending=False).head(10)
                result["regional"] = [
                    {"region": idx, "interest": int(val)}
                    for idx, val in reg_data.items()
                    if val > 0
                ]
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


# ─────────────────────────────────────────────────────────────────────
# STEP 2c: JM Search Seasonality from monthly data
# ─────────────────────────────────────────────────────────────────────
def compute_jm_seasonality(jm_filtered: pd.DataFrame) -> dict:
    """Compute month-over-month seasonality from actual JM Search data.

    jm_filtered: DataFrame with columns [Keyword, Search Volume, Month]
    Returns dict with monthly_totals (list) and keyword_curves (top 5 keywords).
    """
    if jm_filtered.empty or "Month" not in jm_filtered.columns:
        return {"monthly_totals": [], "keyword_curves": []}

    # Aggregate total volume per month
    monthly = (
        jm_filtered.groupby("Month")["Search Volume"]
        .sum()
        .sort_index()
        .reset_index()
    )
    monthly["Month_Label"] = monthly["Month"].dt.strftime("%b %Y")

    monthly_totals = [
        {
            "month": row["Month_Label"],
            "date": row["Month"].strftime("%Y-%m-%d"),
            "volume": int(row["Search Volume"]),
        }
        for _, row in monthly.iterrows()
    ]

    # Compute month-name averages for seasonal pattern
    jm_filtered = jm_filtered.copy()
    jm_filtered["MonthName"] = jm_filtered["Month"].dt.strftime("%b")
    month_avg = (
        jm_filtered.groupby("MonthName")["Search Volume"]
        .sum()
        .reindex(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    )
    overall_avg = month_avg.mean() if len(month_avg) > 0 else 1
    seasonal_index = {}
    for m in month_avg.index:
        v = month_avg.get(m, 0) or 0
        idx = round(v / overall_avg, 2) if overall_avg > 0 else 1.0
        demand = "Very High" if idx >= 1.5 else "High" if idx >= 1.2 else "Low" if idx <= 0.7 else "Medium"
        seasonal_index[m] = {"index": idx, "volume": int(v), "demand": demand}

    # Top 5 keywords by volume — their monthly curves
    top_kw = (
        jm_filtered.groupby("Keyword")["Search Volume"]
        .sum()
        .nlargest(5)
        .index.tolist()
    )
    keyword_curves = []
    for kw in top_kw:
        kw_data = (
            jm_filtered[jm_filtered["Keyword"] == kw]
            .groupby("Month")["Search Volume"]
            .sum()
            .sort_index()
        )
        curve = [
            {"month": dt.strftime("%b %Y"), "volume": int(vol)}
            for dt, vol in kw_data.items()
        ]
        keyword_curves.append({"keyword": kw, "data": curve})

    # Peak and trough months
    if monthly_totals:
        peak = max(monthly_totals, key=lambda x: x["volume"])
        trough = min(monthly_totals, key=lambda x: x["volume"])
    else:
        peak = trough = {"month": "—", "volume": 0}

    return {
        "monthly_totals": monthly_totals,
        "seasonal_index": seasonal_index,
        "keyword_curves": keyword_curves,
        "peak_month": peak,
        "trough_month": trough,
    }


# ─────────────────────────────────────────────────────────────────────
# STEP 2d: YouTube Search Suggestions (social listening)
# ─────────────────────────────────────────────────────────────────────
def fetch_youtube_suggestions(category: str, keywords: list) -> dict:
    """Scrape YouTube autocomplete API for demand signals.

    Queries like "[category] best in India 2026", "[keyword] review", etc.
    Returns list of suggestion clusters.
    """
    result = {"clusters": [], "all_suggestions": []}

    suffixes = [
        "",
        " best",
        " best in india",
        " review",
        " vs",
        " under 500",
        " under 1000",
    ]

    seen = set()
    clusters = []

    # Query category + top 3 keywords
    query_terms = [category] + [k for k in keywords[:3] if k.lower() != category.lower()]

    for term in query_terms:
        term_suggestions = []
        for suffix in suffixes:
            query = f"{term}{suffix}"
            try:
                encoded = urllib.parse.quote(query)
                url = f"https://suggestqueries.google.com/complete/search?client=youtube&ds=yt&q={encoded}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = resp.read().decode("latin-1")
                    # Response is JSONP: window.google.ac.h([...])
                    # Extract the JSON array
                    start = raw.index("[")
                    data = json.loads(raw[start:])
                    suggestions = [s[0] for s in data[1] if isinstance(s, list) and len(s) > 0]
                    for s in suggestions:
                        s_clean = s.strip().lower()
                        if s_clean not in seen and len(s_clean) > 3:
                            seen.add(s_clean)
                            term_suggestions.append(s_clean)
            except Exception:
                continue

        if term_suggestions:
            clusters.append({
                "query_term": term,
                "suggestions": term_suggestions[:15],
                "count": len(term_suggestions[:15]),
            })

    result["clusters"] = clusters
    result["all_suggestions"] = list(seen)[:50]
    result["total_signals"] = len(seen)

    return result


# ─────────────────────────────────────────────────────────────────────
# STEP 3: Run full analysis
# ─────────────────────────────────────────────────────────────────────
def run_analysis(
    category: str,
    category_keywords: list,
    jm_search: pd.DataFrame,
    keyword_planner: pd.DataFrame,
    amazon: pd.DataFrame,
    flipkart: pd.DataFrame,
    progress_callback=None,
) -> dict:
    """Run the complete demand analysis pipeline. Returns structured results dict."""

    results = {
        "category": category,
        "category_keywords": category_keywords,
        "generated_date": datetime.now().strftime("%Y-%m-%d"),
    }

    def update(msg, pct):
        if progress_callback:
            progress_callback(msg, pct)

    # ── JM Search matching ──
    update("Matching JM Search keywords...", 0.10)
    jm_growth = []
    jm_filtered = pd.DataFrame()
    try:
        if not jm_search.empty and "Keyword" in jm_search.columns:
            jm_all_keywords = jm_search["Keyword"].unique()
            jm_matched = fuzzy_match_keywords(category_keywords, jm_all_keywords)

            jm_filtered = jm_search[jm_search["Keyword"].isin(jm_matched)]
            if not jm_filtered.empty:
                jm_grouped = (
                    jm_filtered.groupby("Keyword")
                    .agg(
                        total_vol=("Search Volume", "sum"),
                        months_present=("Month", "nunique"),
                        avg_monthly=("Search Volume", "mean"),
                    )
                    .reset_index()
                )

                for _, row in jm_grouped.iterrows():
                    kw = row["Keyword"]
                    kw_data = jm_filtered[jm_filtered["Keyword"] == kw].sort_values("Month")
                    vols = kw_data["Search Volume"].values
                    growth_pct = None
                    cagr_pct = None
                    if len(vols) >= 2 and vols[0] > 0:
                        growth_pct = ((vols[-1] - vols[0]) / vols[0]) * 100
                        growth_pct = max(-500, min(500, growth_pct))
                        n_periods = len(vols) - 1
                        if n_periods > 0 and vols[0] > 0 and vols[-1] > 0:
                            if vols[0] >= 10:
                                cagr_pct = ((vols[-1] / vols[0]) ** (12 / max(n_periods, 1)) - 1) * 100
                                cagr_pct = max(-500, min(500, cagr_pct))
                    jm_growth.append(
                        {
                            "Keyword": kw,
                            "total_vol": float(row["total_vol"]),
                            "months_present": int(row["months_present"]),
                            "avg_monthly": float(row["avg_monthly"]),
                            "growth_pct": round(growth_pct, 1) if growth_pct is not None else None,
                            "cagr_pct": round(cagr_pct, 1) if cagr_pct is not None else None,
                        }
                    )
                jm_growth.sort(key=lambda x: x["total_vol"], reverse=True)
        else:
            results["jm_data_available"] = False
    except Exception:
        results["jm_data_available"] = False
    results["jm_keywords"] = jm_growth

    # ── Keyword Planner matching ──
    update("Matching Google Keyword Planner...", 0.25)
    kp_filtered = pd.DataFrame()
    try:
        if not keyword_planner.empty and "Keyword" in keyword_planner.columns:
            kp_all_keywords = keyword_planner["Keyword"].unique()
            kp_matched = fuzzy_match_keywords(category_keywords, kp_all_keywords)

            kp_filtered = keyword_planner[keyword_planner["Keyword"].isin(kp_matched)].copy()
            kp_filtered["Avg. monthly searches"] = pd.to_numeric(
                kp_filtered["Avg. monthly searches"], errors="coerce"
            ).fillna(0)
            kp_filtered = kp_filtered.sort_values("Avg. monthly searches", ascending=False)
            results["kp_keywords"] = kp_filtered.head(200).to_dict("records")
        else:
            results["kp_keywords"] = []
            results["kp_data_available"] = False
    except Exception:
        results["kp_keywords"] = []
        results["kp_data_available"] = False

    # ── Coverage & Whitespace ──
    jm_kw_set = {k["Keyword"].lower() for k in jm_growth}
    try:
        if not kp_filtered.empty:
            whitespace = kp_filtered[~kp_filtered["Keyword"].str.lower().isin(jm_kw_set)]
            coverage = kp_filtered[kp_filtered["Keyword"].str.lower().isin(jm_kw_set)]
            coverage_pct = round(len(coverage) / max(len(kp_filtered), 1) * 100, 1)
        else:
            whitespace = pd.DataFrame()
            coverage = pd.DataFrame()
            coverage_pct = 0
    except Exception:
        whitespace = pd.DataFrame()
        coverage = pd.DataFrame()
        coverage_pct = 0

    results["coverage_pct"] = coverage_pct
    results["whitespace_pct"] = round(100 - coverage_pct, 1)
    results["whitespace_count"] = len(whitespace)
    results["whitespace_keywords"] = whitespace.head(100).to_dict("records") if not whitespace.empty else []
    results["coverage_keywords"] = coverage.head(50).to_dict("records") if not coverage.empty else []

    # ── Amazon matching ──
    update("Matching Amazon products...", 0.40)
    amz_stats = {"Median": 0, "Q1": 0, "Q3": 0, "Mean": 0}
    try:
        if not amazon.empty and "Title" in amazon.columns:
            amz_matched = _match_amazon(amazon, category_keywords)

            if amz_matched.empty:
                raise ValueError("No Amazon products matched")

            # Ensure Importance column is numeric
            if "Importance" not in amz_matched.columns:
                qty = pd.to_numeric(amz_matched.get("Qty bought in last 30 days", 0), errors="coerce").fillna(0)
                rc = pd.to_numeric(amz_matched.get("Rating Count", 0), errors="coerce").fillna(0)
                amz_matched["Importance"] = qty.where(qty > 0, rc)
            else:
                amz_matched["Importance"] = pd.to_numeric(amz_matched["Importance"], errors="coerce").fillna(0)

            amz_matched = amz_matched.sort_values("Importance", ascending=False)

            amz_price_valid = pd.to_numeric(amz_matched["Offer Price"], errors="coerce").dropna()
            amz_stats = {
                "Median": round(float(amz_price_valid.median()), 0) if len(amz_price_valid) > 0 else 0,
                "Q1": round(float(amz_price_valid.quantile(0.25)), 0) if len(amz_price_valid) > 0 else 0,
                "Q3": round(float(amz_price_valid.quantile(0.75)), 0) if len(amz_price_valid) > 0 else 0,
                "Mean": round(float(amz_price_valid.mean()), 0) if len(amz_price_valid) > 0 else 0,
            }

            amz_brands = (
                amz_matched.groupby("Brand")
                .agg(
                    Products=("Title", "count"),
                    Avg_Price=("Offer Price", "mean"),
                    Total_Qty=("Qty bought in last 30 days", "sum"),
                    Total_Ratings=("Rating Count", "sum"),
                    Avg_Rating=("Rating", "mean"),
                )
                .fillna(0)
                .reset_index()
            )
            amz_brands["_sort"] = amz_brands["Total_Qty"].where(amz_brands["Total_Qty"] > 0, amz_brands["Total_Ratings"])
            amz_brands = amz_brands.sort_values("_sort", ascending=False).drop(columns=["_sort"]).head(20)

            amz_bands = _price_bands(amz_price_valid)

            # Safe column selection
            amz_prod_cols = [c for c in ["Brand", "Title", "Offer Price", "Qty bought in last 30 days", "Rating", "Rating Count"] if c in amz_matched.columns]
            results["amz_count"] = len(amz_matched)
            results["amz_stats"] = amz_stats
            results["amz_brands"] = amz_brands.to_dict("records")
            results["amz_bands"] = amz_bands
            results["amz_top_products"] = (
                amz_matched.head(20)[amz_prod_cols]
                .fillna(0)
                .to_dict("records")
            )
        else:
            raise ValueError("Amazon data empty or missing columns")
    except Exception:
        results["amz_count"] = 0
        results["amz_stats"] = amz_stats
        results["amz_brands"] = []
        results["amz_bands"] = {}
        results["amz_top_products"] = []
        results["amz_data_available"] = False

    # ── Flipkart matching ──
    update("Matching Flipkart products...", 0.55)
    fk_stats = {"Median": 0, "Q1": 0, "Q3": 0, "Mean": 0}
    fk_brands = pd.DataFrame()
    try:
        if not flipkart.empty and "Product Name" in flipkart.columns:
            fk_matched = _match_flipkart(flipkart, category_keywords)

            if fk_matched.empty:
                raise ValueError("No Flipkart products matched")

            # Ensure Importance column is numeric
            if "Importance" not in fk_matched.columns:
                fk_matched["Importance"] = pd.to_numeric(fk_matched.get("Rating Count", 0), errors="coerce").fillna(0)
            else:
                fk_matched["Importance"] = pd.to_numeric(fk_matched["Importance"], errors="coerce").fillna(0)

            fk_matched = fk_matched.sort_values("Importance", ascending=False)

            fk_price_valid = pd.to_numeric(fk_matched["Selling Price"], errors="coerce").dropna()
            fk_stats = {
                "Median": round(float(fk_price_valid.median()), 0) if len(fk_price_valid) > 0 else 0,
                "Q1": round(float(fk_price_valid.quantile(0.25)), 0) if len(fk_price_valid) > 0 else 0,
                "Q3": round(float(fk_price_valid.quantile(0.75)), 0) if len(fk_price_valid) > 0 else 0,
                "Mean": round(float(fk_price_valid.mean()), 0) if len(fk_price_valid) > 0 else 0,
            }

            # FK brand extraction
            fk_matched["Brand"] = fk_matched["Product Name"].apply(
                lambda x: str(x).split()[0].upper() if str(x).split() else "Unknown"
            )
            fk_brands = (
                fk_matched.groupby("Brand")
                .agg(
                    Products=("Product Name", "count"),
                    Avg_Price=("Selling Price", "mean"),
                    Total_Ratings=("Rating Count", "sum"),
                    Avg_Rating=("Rating", "mean"),
                )
                .sort_values("Total_Ratings", ascending=False)
                .head(20)
                .reset_index()
                .fillna(0)
            )

            fk_bands = _price_bands(fk_price_valid)

            # Safe column selection — only include columns that exist
            fk_prod_cols = [c for c in ["Product Name", "Selling Price", "MRP", "Rating", "Rating Count", "Page Name", "Brand"] if c in fk_matched.columns]
            results["fk_count"] = len(fk_matched)
            results["fk_stats"] = fk_stats
            results["fk_brands"] = fk_brands.to_dict("records")
            results["fk_bands"] = fk_bands
            results["fk_top_products"] = (
                fk_matched.head(20)[fk_prod_cols]
                .fillna("")
                .to_dict("records")
            )
        else:
            raise ValueError("Flipkart data empty or missing columns")
    except Exception:
        results["fk_count"] = 0
        results["fk_stats"] = fk_stats
        results["fk_brands"] = []
        results["fk_bands"] = {}
        results["fk_top_products"] = []
        results["fk_data_available"] = False

    # ── JM Seasonality (from actual monthly data) ──
    update("Computing JM Search seasonality...", 0.60)
    seasonality = compute_jm_seasonality(jm_filtered)
    results["jm_seasonality"] = seasonality

    # ── Google Trends ──
    update("Fetching Google Trends...", 0.65)
    top_kw_names = [k["Keyword"] for k in jm_growth[:10]]
    google_trends = fetch_google_trends(category, top_kw_names)
    results["google_trends"] = google_trends

    # ── YouTube Suggestions (social listening) ──
    update("Scraping YouTube search suggestions...", 0.70)
    yt_suggestions = fetch_youtube_suggestions(category, top_kw_names[:5])
    results["youtube_suggestions"] = yt_suggestions

    # ── Forecast ──
    update("Building forecast...", 0.75)
    forecast = _build_forecast(jm_growth, amz_stats.get("Median", 1000))
    results["forecast"] = forecast

    # ── Enrichment layers ──
    update("Building action queue & enrichment layers...", 0.80)
    avg_price = amz_stats.get("Median", 1000)
    conv_rate = 0.02

    # Demand gaps with GMV
    demand_gaps = []
    for k in results["whitespace_keywords"][:100]:
        vol = float(k.get("Avg. monthly searches", 0) or 0)
        entry = dict(k)
        entry["GMV_opportunity"] = round(vol * conv_rate * avg_price)
        demand_gaps.append(entry)
    results["demand_gaps"] = demand_gaps

    # Brand gaps
    amz_brand_set = {b["Brand"].upper() for b in results.get("amz_brands", [])}
    fk_brand_set = set(fk_brands["Brand"].str.upper()) if not fk_brands.empty and "Brand" in fk_brands.columns else set()
    results["brands_only_amz"] = list(amz_brand_set - fk_brand_set)[:15]
    results["brands_only_fk"] = list(fk_brand_set - amz_brand_set)[:15]
    results["brands_both"] = list(amz_brand_set & fk_brand_set)[:15]

    # Action queue
    actions = _build_actions(results, avg_price, conv_rate)
    results["actions"] = actions

    update("Analysis complete!", 0.85)
    return results


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _match_amazon(amazon: pd.DataFrame, cat_keywords: list) -> pd.DataFrame:
    """Match Amazon products against category keywords.

    Priority: IC columns (structured category) > title (free text).
    For title matching, require the category phrase to appear as a
    contiguous substring to avoid false positives like
    "bike riding face cover" matching "bike covers".
    """
    cat_lower = [c.lower().strip() for c in cat_keywords if len(str(c).strip()) >= 3]
    if not cat_lower:
        return pd.DataFrame(columns=amazon.columns)

    # Pre-build AOP/IC column values for vectorized filtering
    ic_cols_available = [c for c in ["IC L1", "IC L2", "IC L3", "IC L4", "AOP L1", "AOP L2"] if c in amazon.columns]

    matched_idx = set()
    for idx, row in amazon.iterrows():
        # Strategy 1: Exact match in IC/AOP columns (most reliable)
        ic_values = [str(row.get(c, "")).lower().strip() for c in ic_cols_available]
        ic_matched = False
        for cat in cat_lower:
            for ic_val in ic_values:
                if ic_val and (cat == ic_val or cat in ic_val):
                    matched_idx.add(idx)
                    ic_matched = True
                    break
            if ic_matched:
                break
        if ic_matched:
            continue

        # Strategy 2: Category phrase appears as contiguous substring in title
        title = str(row.get("Title", "")).lower()
        for cat in cat_lower:
            # Check singular/plural: "bike covers" matches "bike cover" and vice versa
            cat_base = cat.rstrip("s")
            if cat in title or cat_base in title or (cat + "s") in title:
                matched_idx.add(idx)
                break

    return amazon.loc[list(matched_idx)].copy() if matched_idx else pd.DataFrame(columns=amazon.columns)


def _match_flipkart(flipkart: pd.DataFrame, cat_keywords: list) -> pd.DataFrame:
    cat_lower = [c.lower() for c in cat_keywords]
    cat_words = set()
    for c in cat_lower:
        cat_words.update(c.split())

    matched_idx = set()
    for idx, row in flipkart.iterrows():
        pn = str(row.get("Product Name", "")).lower()
        pg = str(row.get("Page Name", "")).lower()
        combined = pn + " " + pg

        for cat in cat_lower:
            cat_w = set(cat.split())
            if cat_w.issubset(set(combined.split())):
                matched_idx.add(idx)
                break

    return flipkart.loc[list(matched_idx)].copy() if matched_idx else pd.DataFrame(columns=flipkart.columns)


def _price_bands(prices: pd.Series) -> dict:
    bands = {}
    for label, lo, hi in [
        ("Under ₹500", 0, 500),
        ("₹500-1K", 500, 1000),
        ("₹1K-2K", 1000, 2000),
        ("₹2K-3K", 2000, 3000),
        ("₹3K-5K", 3000, 5000),
        ("₹5K+", 5000, 999999),
    ]:
        bands[label] = int(((prices >= lo) & (prices < hi)).sum())
    return bands


def _build_forecast(jm_keywords: list, avg_price: float) -> dict:
    """Simple quarterly forecast from JM keyword growth."""
    fc_keywords = []
    for k in jm_keywords:
        vol = k.get("total_vol", 0) or 0
        cagr = k.get("cagr_pct", 0) or 0
        growth = k.get("growth_pct", 0) or 0
        # Cap values to avoid display overflow from tiny-base keywords
        cagr = max(-500, min(500, cagr))
        growth = max(-500, min(500, growth))
        yoy_ratio = 1 + (growth / 100) if growth else 1.0
        forecast_vol = vol * (1 + cagr / 100 / 4) if cagr else vol
        forecast_vol = max(0, min(forecast_vol, vol * 10))  # cap at 10x current
        priority_score = (vol * 0.5 + forecast_vol * 0.3 + abs(cagr) * 10) / 100
        fc_keywords.append(
            {
                "keyword": k["Keyword"],
                "current_vol": vol,
                "forecast_vol": round(forecast_vol),
                "yoy_ratio": round(yoy_ratio, 2),
                "cagr_pct": round(cagr, 1),
                "priority_score": round(priority_score, 1),
            }
        )
    fc_keywords.sort(key=lambda x: x["priority_score"], reverse=True)
    return {"keywords": fc_keywords[:25]}


def _build_actions(results: dict, avg_price: float, conv_rate: float) -> list:
    actions = []

    # Demand gap actions
    for gap in results.get("demand_gaps", [])[:10]:
        actions.append(
            {
                "priority": len(actions) + 1,
                "action": f"List products for '{gap['Keyword']}'",
                "type": "Demand Gap",
                "impact": "High" if gap.get("GMV_opportunity", 0) > 50000 else "Medium",
                "effort": "Low",
                "gmv_potential": gap.get("GMV_opportunity", 0),
                "rationale": f"Google vol {gap.get('Avg. monthly searches', 0)}/mo, zero JM coverage",
            }
        )

    # Brand gap actions
    for brand in results.get("brands_only_amz", [])[:5]:
        amz_b = next((b for b in results["amz_brands"] if b["Brand"].upper() == brand), None)
        if amz_b:
            actions.append(
                {
                    "priority": len(actions) + 1,
                    "action": f"Onboard brand '{amz_b['Brand']}'",
                    "type": "Brand Gap",
                    "impact": "High" if amz_b.get("Products", 0) > 5 else "Medium",
                    "effort": "Medium",
                    "gmv_potential": int(amz_b.get("Products", 0) * avg_price * 10),
                    "rationale": f"{amz_b.get('Products', 0)} products on Amazon, not on FK",
                }
            )

    # Price band gaps
    amz_bands = results.get("amz_bands", {})
    fk_bands = results.get("fk_bands", {})
    for band in amz_bands:
        ac = amz_bands.get(band, 0)
        fc = fk_bands.get(band, 0)
        if ac > 5 and fc < ac * 0.3:
            actions.append(
                {
                    "priority": len(actions) + 1,
                    "action": f"Expand {band} price band",
                    "type": "Price Gap",
                    "impact": "Medium",
                    "effort": "Medium",
                    "gmv_potential": int(ac * avg_price * 5),
                    "rationale": f"Amazon {ac} vs FK {fc} products",
                }
            )

    # Rising demand
    for k in results.get("jm_keywords", []):
        if k.get("growth_pct") and k["growth_pct"] > 50:
            actions.append(
                {
                    "priority": len(actions) + 1,
                    "action": f"Boost '{k['Keyword']}'",
                    "type": "Rising Demand",
                    "impact": "Medium",
                    "effort": "Low",
                    "gmv_potential": int(k.get("total_vol", 0) * conv_rate * avg_price),
                    "rationale": f"Growing {k['growth_pct']:.0f}% with {k['total_vol']} vol",
                }
            )
            if len(actions) >= 30:
                break

    actions.sort(key=lambda x: x.get("gmv_potential", 0), reverse=True)
    for i, a in enumerate(actions):
        a["priority"] = i + 1

    return actions
