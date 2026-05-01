"""
Data Loader — loads all 6 data sources from pre-processed parquet files.
Uses Streamlit caching to load once per session.

Data sources:
1. JM Search Monthly (15 CSVs → aggregated parquet)
2. Google Keyword Planner (multiple CSVs → deduplicated parquet)
3. GM+Kitchen_Reporting hierarchy (.xlsb → parquet)
4. Amazon Top Sellers (.xlsx → parquet)
5. Flipkart Best Sellers (mixed formats → parquet)
"""

import pandas as pd
import numpy as np
import os
import functools

try:
    import streamlit as st
    _cache = st.cache_data(ttl=3600)
except Exception:
    # Fallback for non-Streamlit environments (testing, CLI)
    _cache = lambda f: f
    class _st:
        @staticmethod
        def error(msg): print(f"ERROR: {msg}")
    st = _st()


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@_cache
def load_hierarchy() -> pd.DataFrame:
    """Load category hierarchy (L1→L4 + AOP mappings)."""
    path = os.path.join(DATA_DIR, "hierarchy.parquet")
    if not os.path.exists(path):
        st.error(f"Hierarchy file not found: {path}. Run prepare_data.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    for col in ["L1", "L2", "L3", "L4", "AOP_L1", "AOP_L2"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


@_cache
def load_jm_search() -> pd.DataFrame:
    """Load JM Search monthly data (all months combined).
    Columns: Keyword, Search Volume, Month, Month_Label
    """
    path = os.path.join(DATA_DIR, "jm_search.parquet")
    if not os.path.exists(path):
        st.error(f"JM Search file not found: {path}. Run prepare_data.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["Keyword"] = df["Keyword"].astype(str).str.strip().str.lower()
    df["Search Volume"] = pd.to_numeric(df["Search Volume"], errors="coerce").fillna(0)
    return df


@_cache
def load_keyword_planner() -> pd.DataFrame:
    """Load Google Keyword Planner data (all files combined, deduplicated).
    Columns: Keyword, Avg. monthly searches, Three month change, YoY change, Competition, etc.
    """
    path = os.path.join(DATA_DIR, "keyword_planner.parquet")
    if not os.path.exists(path):
        st.error(f"Keyword Planner file not found: {path}. Run prepare_data.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["Keyword"] = df["Keyword"].astype(str).str.strip().str.lower()
    return df


@_cache
def load_amazon() -> pd.DataFrame:
    """Load Amazon Top Sellers data.
    Columns: Brand, Title, Offer Price, MRP, Qty bought in last 30 days, Rating, Rating Count, IC L1-L4, AOP L1-L2
    """
    path = os.path.join(DATA_DIR, "amazon.parquet")
    if not os.path.exists(path):
        st.error(f"Amazon file not found: {path}. Run prepare_data.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["Brand"] = df["Brand"].astype(str).str.strip()
    df["Title"] = df["Title"].astype(str).str.strip()
    df["Offer Price"] = pd.to_numeric(df["Offer Price"], errors="coerce")
    df["Qty bought in last 30 days"] = pd.to_numeric(
        df["Qty bought in last 30 days"], errors="coerce"
    )
    df["Rating Count"] = pd.to_numeric(df["Rating Count"], errors="coerce")
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    # Importance score
    df["Importance"] = df["Qty bought in last 30 days"].fillna(0)
    df.loc[df["Importance"] == 0, "Importance"] = df.loc[
        df["Importance"] == 0, "Rating Count"
    ].fillna(0)
    return df


@_cache
def load_flipkart() -> pd.DataFrame:
    """Load Flipkart Best Sellers data (all files combined, normalized).
    Columns: Product Name, Selling Price, MRP, Rating, Rating Count, Page Name, Bestseller Tag, F-Assured Tag
    """
    path = os.path.join(DATA_DIR, "flipkart.parquet")
    if not os.path.exists(path):
        st.error(f"Flipkart file not found: {path}. Run prepare_data.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["Product Name"] = df["Product Name"].astype(str).str.strip()
    df["Selling Price"] = pd.to_numeric(df["Selling Price"], errors="coerce")
    df["MRP"] = pd.to_numeric(df["MRP"], errors="coerce")
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    df["Rating Count"] = pd.to_numeric(df["Rating Count"], errors="coerce")
    df["Importance"] = df["Rating Count"].fillna(0)
    return df


def get_all_categories(hierarchy: pd.DataFrame) -> dict:
    """Extract category options from hierarchy for the dropdown.
    Returns dict: {'AOP L2': [...], 'L2': [...], 'L3': [...], 'L4': [...]}
    """
    cats = {}
    for level in ["AOP_L2", "L2", "L3", "L4"]:
        if level in hierarchy.columns:
            vals = (
                hierarchy[level]
                .dropna()
                .unique()
            )
            vals = sorted([v for v in vals if v and v.lower() not in ("nan", "none", "")])
            display_level = level.replace("_", " ")
            cats[display_level] = vals
    return cats


def check_data_ready() -> dict:
    """Check which data files are available."""
    files = {
        "hierarchy": "hierarchy.parquet",
        "jm_search": "jm_search.parquet",
        "keyword_planner": "keyword_planner.parquet",
        "amazon": "amazon.parquet",
        "flipkart": "flipkart.parquet",
    }
    status = {}
    for name, fname in files.items():
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            size_mb = os.path.getsize(path) / (1024 * 1024)
            status[name] = {"ready": True, "size_mb": round(size_mb, 1)}
        else:
            status[name] = {"ready": False, "size_mb": 0}
    return status
