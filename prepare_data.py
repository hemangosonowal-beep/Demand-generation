"""
Data Preparation Script
========================
Converts raw data files from the Demand Analysis folder into optimized parquet files.

Usage:
    python prepare_data.py --source "/path/to/Demand Analysis"

The script will create/overwrite parquet files in the data/ folder.
Run this whenever you update the source data files.
"""

import pandas as pd
import numpy as np
import os
import sys
import glob
import argparse
from datetime import datetime
from lxml import etree
from pyxlsb import open_workbook


def main():
    parser = argparse.ArgumentParser(description="Prepare data for JioMart Demand Analysis app")
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Path to the Demand Analysis folder containing raw data files",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "data"),
        help="Output folder for parquet files (default: ./data/)",
    )
    args = parser.parse_args()

    source = args.source
    output = args.output
    os.makedirs(output, exist_ok=True)

    if not os.path.isdir(source):
        print(f"ERROR: Source folder not found: {source}")
        sys.exit(1)

    print(f"Source: {source}")
    print(f"Output: {output}")
    print("=" * 60)

    # 1. Hierarchy
    print("\n[1/5] Processing GM+Kitchen_Reporting hierarchy...")
    prepare_hierarchy(source, output)

    # 2. JM Search
    print("\n[2/5] Processing JM Search monthly data...")
    prepare_jm_search(source, output)

    # 3. Keyword Planner
    print("\n[3/5] Processing Google Keyword Planner...")
    prepare_keyword_planner(source, output)

    # 4. Amazon
    print("\n[4/5] Processing Amazon Top Sellers...")
    prepare_amazon(source, output)

    # 5. Flipkart
    print("\n[5/5] Processing Flipkart Best Sellers...")
    prepare_flipkart(source, output)

    print("\n" + "=" * 60)
    print("✅ All done! Parquet files saved to:", output)
    for f in sorted(glob.glob(os.path.join(output, "*.parquet"))):
        size_mb = os.path.getsize(f) / (1024 * 1024)
        print(f"  {os.path.basename(f)}: {size_mb:.1f} MB")


def prepare_hierarchy(source, output):
    gm_path = os.path.join(source, "GM+Kitchen_Reporting.xlsb")
    if not os.path.exists(gm_path):
        print("  WARNING: GM+Kitchen_Reporting.xlsb not found, skipping")
        return

    data = []
    wb = open_workbook(gm_path)
    with wb.get_sheet("1P+3P") as sheet:
        for i, row in enumerate(sheet.rows()):
            if i <= 1:
                continue
            vals = [c.v for c in row]
            data.append(
                {
                    "L1": str(vals[2]).strip() if vals[2] else "",
                    "L2": str(vals[3]).strip() if vals[3] else "",
                    "L3": str(vals[4]).strip() if vals[4] else "",
                    "L4": str(vals[5]).strip() if vals[5] else "",
                    "AOP_L1": str(vals[6]).strip() if vals[6] else "",
                    "AOP_L2": str(vals[7]).strip() if vals[7] else "",
                }
            )
    wb.close()

    df = pd.DataFrame(data)
    out_path = os.path.join(output, "hierarchy.parquet")
    df.to_parquet(out_path, index=False)
    print(f"  Saved {len(df)} rows → {out_path}")


def prepare_jm_search(source, output):
    jm_folder = os.path.join(source, "JM search")
    if not os.path.isdir(jm_folder):
        print("  WARNING: JM search/ folder not found, skipping")
        return

    frames = []
    for f in sorted(glob.glob(os.path.join(jm_folder, "*.csv"))):
        fname = os.path.basename(f).replace(".csv", "")
        try:
            month_dt = datetime.strptime(fname, "%b %Y")
        except ValueError:
            continue
        df = pd.read_csv(f)
        df["Keyword"] = df["Keyword"].astype(str).str.strip().str.lower()
        df["Search Volume"] = pd.to_numeric(df["Search Volume"], errors="coerce").fillna(0)
        df["Month"] = month_dt
        df["Month_Label"] = fname
        frames.append(df[["Keyword", "Search Volume", "Month", "Month_Label"]])

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        out_path = os.path.join(output, "jm_search.parquet")
        combined.to_parquet(out_path, index=False)
        print(f"  Saved {len(combined)} rows from {len(frames)} months → {out_path}")
    else:
        print("  WARNING: No CSV files found in JM search/")


def prepare_keyword_planner(source, output):
    kp_folder = os.path.join(source, "Keyword planner search")
    if not os.path.isdir(kp_folder):
        print("  WARNING: Keyword planner search/ folder not found, skipping")
        return

    frames = []
    for f in glob.glob(os.path.join(kp_folder, "Keyword Stats*.csv")):
        try:
            df = pd.read_csv(f, encoding="utf-16", sep="\t", skiprows=2)
            frames.append(df)
        except Exception as e:
            print(f"  WARNING: Could not read {os.path.basename(f)}: {e}")

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined["Keyword"] = combined["Keyword"].astype(str).str.strip().str.lower()
        combined.drop_duplicates(subset="Keyword", keep="first", inplace=True)
        out_path = os.path.join(output, "keyword_planner.parquet")
        combined.to_parquet(out_path, index=False)
        print(f"  Saved {len(combined)} unique keywords from {len(frames)} files → {out_path}")
    else:
        print("  WARNING: No Keyword Stats files found")


def prepare_amazon(source, output):
    amz_path = os.path.join(source, "Amazon top sellers.xlsx")
    if not os.path.exists(amz_path):
        print("  WARNING: Amazon top sellers.xlsx not found, skipping")
        return

    df = pd.read_excel(amz_path, header=1)
    df["Brand"] = df["Brand"].astype(str).str.strip()
    df["Title"] = df["Title"].astype(str).str.strip()
    df["Offer Price"] = pd.to_numeric(df["Offer Price"], errors="coerce")
    df["MRP"] = pd.to_numeric(df["MRP"], errors="coerce")
    df["Qty bought in last 30 days"] = pd.to_numeric(
        df["Qty bought in last 30 days"], errors="coerce"
    )
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    df["Rating Count"] = pd.to_numeric(df["Rating Count"], errors="coerce")

    # Keep essential columns
    cols = [
        "Brand", "Title", "Offer Price", "MRP", "Qty bought in last 30 days",
        "Rating", "Rating Count", "IC L1", "IC L2", "IC L3", "IC L4",
        "AOP L1", "AOP L2",
    ]
    available_cols = [c for c in cols if c in df.columns]
    df = df[available_cols]

    # Ensure string columns are actually strings (avoid mixed type parquet errors)
    for col in ["Brand", "Title", "IC L1", "IC L2", "IC L3", "IC L4", "AOP L1", "AOP L2"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    out_path = os.path.join(output, "amazon.parquet")
    df.to_parquet(out_path, index=False)
    print(f"  Saved {len(df)} products → {out_path}")


def prepare_flipkart(source, output):
    fk_folder = os.path.join(source, "Flipkart best sellers")
    if not os.path.isdir(fk_folder):
        print("  WARNING: Flipkart best sellers/ folder not found, skipping")
        return

    def clean_price(val):
        s = str(val).replace("₹", "").replace("?", "").replace(",", "").strip()
        try:
            return float(s) if s and s.lower() not in ("nan", "none", "") else np.nan
        except ValueError:
            return np.nan

    def load_file(filepath):
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".xlsx":
            df = pd.read_excel(filepath)
        elif ext == ".csv":
            df = pd.read_csv(filepath)
        elif ext == ".xls":
            try:
                df = pd.read_csv(filepath, sep="\t", encoding="latin-1")
                if len(df.columns) >= 5:
                    return normalize(df)
            except Exception:
                pass
            df = parse_xml(filepath)
        else:
            return pd.DataFrame()
        return normalize(df)

    def parse_xml(filepath):
        tree = etree.parse(filepath)
        ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
        rows = tree.findall(".//ss:Table/ss:Row", ns)
        if not rows:
            return pd.DataFrame()
        header = [c.text for c in rows[0].findall(".//ss:Data", ns)]
        data = []
        for row in rows[1:]:
            cells = row.findall("ss:Cell", ns)
            vals = []
            for c in cells:
                d = c.find("ss:Data", ns)
                vals.append(d.text if d is not None else "")
            vals.extend([""] * (len(header) - len(vals)))
            data.append(dict(zip(header, vals[: len(header)])))
        return pd.DataFrame(data)

    def normalize(df):
        col_map = {}
        for col in df.columns:
            cl = str(col).lower().strip().replace("_", " ")
            if "product name" in cl or cl == "productname":
                col_map[col] = "Product Name"
            elif "selling price" in cl or cl == "sellingprice":
                col_map[col] = "Selling Price"
            elif cl in ("mrp", "mrp (₹)", "mrp (rs)"):
                col_map[col] = "MRP"
            elif "rating count" in cl or cl == "ratingcount":
                col_map[col] = "Rating Count"
            elif cl == "rating":
                col_map[col] = "Rating"
            elif "page name" in cl or cl == "pagename":
                col_map[col] = "Page Name"
            elif "bestseller" in cl:
                col_map[col] = "Bestseller Tag"
            elif "assured" in cl:
                col_map[col] = "F-Assured Tag"
        return df.rename(columns=col_map)

    frames = []
    for f in glob.glob(os.path.join(fk_folder, "*")):
        if os.path.isfile(f):
            try:
                df = load_file(f)
                if len(df) > 0:
                    frames.append(df)
                    print(f"  Loaded {os.path.basename(f)}: {len(df)} rows")
            except Exception as e:
                print(f"  WARNING: Failed to load {os.path.basename(f)}: {e}")

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined["Selling Price"] = combined["Selling Price"].apply(clean_price)
        combined["MRP"] = combined["MRP"].apply(clean_price)
        combined["Rating"] = pd.to_numeric(combined["Rating"], errors="coerce")
        combined["Rating Count"] = (
            combined["Rating Count"].astype(str).str.replace(",", "").pipe(pd.to_numeric, errors="coerce")
        )
        combined["Product Name"] = combined["Product Name"].astype(str).str.strip()

        # Fix mixed types — convert all object columns to string
        for col in combined.select_dtypes(include=["object"]).columns:
            combined[col] = combined[col].astype(str)

        out_path = os.path.join(output, "flipkart.parquet")
        combined.to_parquet(out_path, index=False)
        print(f"  Saved {len(combined)} products from {len(frames)} files → {out_path}")
    else:
        print("  WARNING: No files loaded from Flipkart best sellers/")


if __name__ == "__main__":
    main()
