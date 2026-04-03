# NeuralNexus — Data Directory

## Getting the PaySim Dataset

> [!IMPORTANT]
> You must download PaySim manually from Kaggle (requires free account).

1. Go to: https://www.kaggle.com/datasets/ealaxi/paysim1
2. Click **Download** → you get `archive.zip`
3. Extract → find the file named `PS_20174392719_1491204439457_log.csv`
4. Rename it to `paysim.csv` and place it here: `data/raw/paysim.csv`

File size: ~493 MB  
Rows: 6,362,620  
Fraud rate: ~1.3%  

## Directory Layout

```
data/
├── raw/
│   └── paysim.csv              ← place downloaded file here
├── processed/                  ← created by data_pipeline.py
│   ├── paysim_features.parquet ← model training data
│   ├── feature_columns.json    ← exact feature column order
│   ├── class_weights.json      ← scale_pos_weight for XGBoost
│   └── dataset_stats.json      ← EDA summary
└── blacklist_merchants.txt     ← add merchant names (one per line)
```

## Running the Pipeline

```bash
# Quick smoke test (no dataset needed — 1000 synthetic rows):
python backend/data_pipeline.py --smoke-test

# Full pipeline (requires paysim.csv):
python backend/data_pipeline.py

# Faster iteration (20% sample):
python backend/data_pipeline.py --sample 0.2
```

## Expected Runtime

| Mode | Rows | Time |
|---|---|---|
| Smoke test | 1,000 | < 5s |
| 20% sample | ~1.2M | ~2-3 min |
| Full dataset | 6.3M | ~10-15 min |
