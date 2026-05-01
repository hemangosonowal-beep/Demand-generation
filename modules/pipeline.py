"""
Demand Analysis Pipeline — core analysis engine.

Takes pre-loaded DataFrames + category name → returns structured analysis results.
"""

import pandas as pd
import numpy as np
from thefuzz import fuzz
from datetime import datetime
import re


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
    jm_all_keywords = jm_search["Keyword"].unique()
    jm_matched = fuzzy_match_keywords(category_keywords, jm_all_keywords)

    jm_filtered = jm_search[jm_search["Keyword"].isin(jm_matched)]
    jm_grouped = (
        jm_filtered.groupby("Keyword")
        .agg(
            total_vol=("Search Volume", "sum"),
            months_present=("Month", "nunique"),
            avg_monthly=("Search Volume", "mean"),
        )
        .reset_index()
    )

    # Growth metrics
    months_sorted = sorted(jm_filtered["Month"].unique())
    jm_growth = []
    for _, row in jm_grouped.iterrows():
        kw = row["Keyword"]
        kw_data = jm_filtered[jm_filtered["Keyword"] == kw].sort_values("Month")
        vols = kw_data["Search Volume"].values
        growth_pct = None
        cagr_pct = None
        if len(vols) >= 2 and vols[0] > 0:
            growth_pct = ((vols[-1] - vols[0]) / vols[0]) * 100
            # Cap growth_pct to ±500% to avoid tiny-base inflation
            growth_pct = max(-500, min(500, growth_pct))
            n_periods = len(vols) - 1
            if n_periods > 0 and vols[0] > 0 and vols[-1] > 0:
                # Only compute CAGR if base volume >= 10 (avoids 1→200 = 19900% noise)
                if vols[0] >= 10:
                    cagr_pct = ((vols[-1] / vols[0]) ** (12 / max(n_periods, 1)) - 1) * 100
                    # Cap CAGR to ±500% — anything beyond is statistical noise
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
    results["jm_keywords"] = jm_growth

    # ── Keyword Planner matching ──
    update("Matching Google Keyword Planner...", 0.25)
    kp_all_keywords = keyword_planner["Keyword"].unique()
    kp_matched = fuzzy_match_keywords(category_keywords, kp_all_keywords)

    kp_filtered = keyword_planner[keyword_planner["Keyword"].isin(kp_matched)].copy()
    kp_filtered["Avg. monthly searches"] = pd.to_numeric(
        kp_filtered["Avg. monthly searches"], errors="coerce"
    ).fillna(0)
    kp_filtered = kp_filtered.sort_values("Avg. monthly searches", ascending=False)
    results["kp_keywords"] = kp_filtered.head(200).to_dict("records")

    # ── Coverage & Whitespace ──
    jm_kw_set = {k["Keyword"].lower() for k in jm_growth}
    kp_kw_set = set(kp_filtered["Keyword"].str.lower())

    whitespace = kp_filtered[~kp_filtered["Keyword"].str.lower().isin(jm_kw_set)]
    coverage = kp_filtered[kp_filtered["Keyword"].str.lower().isin(jm_kw_set)]

    coverage_pct = round(len(coverage) / max(len(kp_filtered), 1) * 100, 1)
    whitespace_pct = round(len(whitespace) / max(len(kp_filtered), 1) * 100, 1)

    results["coverage_pct"] = coverage_pct
    results["whitespace_pct"] = whitespace_pct
    results["whitespace_count"] = len(whitespace)
    results["whitespace_keywords"] = whitespace.head(100).to_dict("records")
    results["coverage_keywords"] = coverage.head(50).to_dict("records")

    # ── Amazon matching ──
    update("Matching Amazon products...", 0.40)
    amz_matched = _match_amazon(amazon, category_keywords)
    amz_matched = amz_matched.sort_values("Importance", ascending=False)

    amz_price_valid = amz_matched["Offer Price"].dropna()
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
            Avg_Rating=("Rating", "mean"),
        )
        .sort_values("Total_Qty", ascending=False)
        .head(20)
        .reset_index()
        .fillna(0)
    )

    amz_bands = _price_bands(amz_price_valid)

    results["amz_count"] = len(amz_matched)
    results["amz_stats"] = amz_stats
    results["amz_brands"] = amz_brands.to_dict("records")
    results["amz_bands"] = amz_bands
    results["amz_top_products"] = (
        amz_matched.nlargest(20, "Importance")[
            ["Brand", "Title", "Offer Price", "Qty bought in last 30 days", "Rating"]
        ]
        .fillna(0)
        .to_dict("records")
    )

    # ── Flipkart matching ──
    update("Matching Flipkart products...", 0.55)
    fk_matched = _match_flipkart(flipkart, category_keywords)
    fk_matched = fk_matched.sort_values("Importance", ascending=False)

    fk_price_valid = fk_matched["Selling Price"].dropna()
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

    results["fk_count"] = len(fk_matched)
    results["fk_stats"] = fk_stats
    results["fk_brands"] = fk_brands.to_dict("records")
    results["fk_bands"] = fk_bands
    results["fk_top_products"] = (
        fk_matched.nlargest(20, "Importance")[
            ["Product Name", "Selling Price", "MRP", "Rating", "Rating Count", "Page Name", "Brand"]
        ]
        .fillna("")
        .to_dict("records")
    )

    # ── Forecast ──
    update("Building forecast...", 0.65)
    forecast = _build_forecast(jm_growth, amz_stats.get("Median", 1000))
    results["forecast"] = forecast

    # ── Enrichment layers ──
    update("Building action queue & enrichment layers...", 0.75)
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
    amz_brand_set = {b["Brand"].upper() for b in results["amz_brands"]}
    fk_brand_set = set(fk_brands["Brand"].str.upper())
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
    cat_lower = [c.lower() for c in cat_keywords]
    cat_words = set()
    for c in cat_lower:
        cat_words.update(c.split())

    matched_idx = set()
    for idx, row in amazon.iterrows():
        title = str(row.get("Title", "")).lower()
        ic_cols = " ".join(
            str(row.get(c, "")).lower() for c in ["IC L1", "IC L2", "IC L3", "IC L4"] if c in row.index
        )
        combined = title + " " + ic_cols

        for cat in cat_lower:
            cat_w = set(cat.split())
            if cat_w.issubset(set(combined.split())):
                matched_idx.add(idx)
                break
            if fuzz.token_set_ratio(cat, combined) >= 85:
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
