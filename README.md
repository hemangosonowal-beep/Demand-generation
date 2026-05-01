# JioMart Demand Analysis

McKinsey-style demand analysis dashboard for JioMart categories. Select a category, click Generate, get an interactive HTML dashboard with competitive intelligence, demand gaps, pricing analysis, and AI-powered strategic insights.

## Live Demo

Deploy on Streamlit Cloud → [streamlit.io/cloud](https://streamlit.io/cloud)

## Features

- **6 data sources**: JM Search (15 months), Google Keyword Planner, GM+Kitchen hierarchy, Amazon Top Sellers, Flipkart Best Sellers
- **Fuzzy category matching**: Works at AOP L2, L2, L3, L4 levels or free-form input
- **AI insights** (optional): Google Gemini 2.0 Flash generates market research, seasonal calendar, and "So What for JioMart?" cards
- **McKinsey-style dashboard**: 7-tab interactive HTML with Chart.js visualizations
- **Downloadable**: One-click HTML download for offline sharing

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Prepare data (first time only)

Convert raw data files from your Demand Analysis folder into optimized parquet files:

```bash
python prepare_data.py --source "/path/to/Demand Analysis"
```

**Expected folder structure:**
```
Demand Analysis/
├── JM search/                    # 15 monthly CSVs (Jan 2025.csv ... Mar 2026.csv)
├── Keyword planner search/       # Keyword Stats*.csv files (UTF-16, tab-separated)
├── GM+Kitchen_Reporting.xlsb     # Category hierarchy (.xlsb)
├── Amazon top sellers.xlsx       # Amazon competitive data
└── Flipkart best sellers/        # Mixed format files (.xlsx, .csv, .xls)
```

### 3. Run the app

```bash
streamlit run app.py
```

### 4. (Optional) Enable AI insights

Get a free Google API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey), then:

```bash
# Local: create .streamlit/secrets.toml
echo 'GOOGLE_API_KEY = "your-key-here"' > .streamlit/secrets.toml

# Streamlit Cloud: Settings → Secrets → paste the key
```

Free tier: 1,500 requests/day with Gemini 2.0 Flash.

## Project Structure

```
jm-demand-app/
├── app.py                  # Streamlit UI
├── prepare_data.py         # Raw data → parquet converter
├── requirements.txt        # Python dependencies
├── .streamlit/
│   ├── config.toml         # Theme (McKinsey navy)
│   └── secrets.toml.example
├── data/                   # Pre-processed parquet files
│   ├── hierarchy.parquet
│   ├── jm_search.parquet
│   ├── keyword_planner.parquet
│   ├── amazon.parquet
│   └── flipkart.parquet
└── modules/
    ├── data_loader.py      # Cached parquet loading
    ├── pipeline.py         # Category resolution + analysis engine
    ├── insights.py         # Gemini AI insights (with fallback)
    └── dashboard.py        # McKinsey-style HTML generator
```

## Streamlit Cloud Deployment

1. Push this repo to GitHub
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) → New app
3. Point to this repo → `app.py`
4. Add `GOOGLE_API_KEY` in Settings → Secrets (optional)
5. Deploy

Data files (~28MB parquet) are included in the repo for Streamlit Cloud compatibility.

## Built By

JioMart Category Intelligence
