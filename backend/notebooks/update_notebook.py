"""Fix cell source strings and execute notebook to populate all cell outputs."""

import os
import sys
from pathlib import Path
import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

NOTEBOOK_PATH = Path("backend/notebooks/freight_cost_analysis.ipynb")
nb = nbformat.read(NOTEBOOK_PATH, as_version=4)

sec11_code_1 = r"""# Cell 11A: Leakage-Free Feature Engineering
from backend.app.services.ml_features import FEATURE_NAMES, FEATURE_SPECS, MLFeatureEngineer

engineer = MLFeatureEngineer()
engineered_df, X = engineer.extract_features(analysis_df, is_training=True)

print("Engineered Feature Matrix Shape:", X.shape)
print("Canonical ML Features:", FEATURE_NAMES)
print("\nFeature Summary Statistics:")
display(X.describe().round(4))
"""

sec11_code_2 = r"""# Cell 11B: Chronological Holdout Partition & Isolation Forest Training
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
import numpy as np

# Chronological split on unique weeks
unique_weeks = sorted(engineered_df['week_of'].unique())
holdout_count = 26
train_weeks = unique_weeks[:-holdout_count]
holdout_weeks = unique_weeks[-holdout_count:]
split_week = holdout_weeks[0]

train_mask = engineered_df['week_of'].isin(train_weeks)
holdout_mask = engineered_df['week_of'].isin(holdout_weeks)

X_train = X.loc[train_mask, FEATURE_NAMES].copy()
X_holdout = X.loc[holdout_mask, FEATURE_NAMES].copy()

df_train = engineered_df.loc[train_mask].copy()
df_holdout = engineered_df.loc[holdout_mask].copy()

print(f"Chronological Split Week: {split_week}")
print(f"Training Partition:  {len(df_train)} observations across {len(train_weeks)} weeks")
print(f"Holdout Partition:   {len(df_holdout)} observations across {len(holdout_weeks)} weeks")

# Preprocessing: Fit RobustScaler strictly on train set
scaler = RobustScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_holdout_scaled = scaler.transform(X_holdout)

# Train Isolation Forest
iso_forest = IsolationForest(
    n_estimators=150,
    contamination=0.03,
    random_state=42,
    n_jobs=-1
)
iso_forest.fit(X_train_scaled)

# Score both partitions
train_scores = iso_forest.decision_function(X_train_scaled)
train_preds = iso_forest.predict(X_train_scaled) == -1

holdout_scores = iso_forest.decision_function(X_holdout_scaled)
holdout_preds = iso_forest.predict(X_holdout_scaled) == -1

all_scaled = scaler.transform(X[FEATURE_NAMES])
all_scores = iso_forest.decision_function(all_scaled)
all_preds = iso_forest.predict(all_scaled) == -1

engineered_df['is_ml_anomaly'] = all_preds
engineered_df['raw_decision_score'] = all_scores

# Calibrated normalized anomaly score [0.0 = normal, 1.0 = severe outlier]
min_s = float(np.percentile(train_scores, 0.5))
max_s = float(np.percentile(train_scores, 99.5))
s_range = max(1e-5, max_s - min_s)
engineered_df['ml_anomaly_score'] = np.clip((max_s - all_scores) / s_range, 0.0, 1.0).round(4)

print("Model successfully trained and calibrated.")
"""

sec11_code_3 = r"""# Cell 11C: Empirical Evaluation Against Deterministic Baseline
import pandas as pd

# Ground-rule comparison
det_flag = engineered_df['flagged'].values
ml_flag = engineered_df['is_ml_anomaly'].values

both_flagged = int(np.sum(ml_flag & det_flag))
ml_only = int(np.sum(ml_flag & ~det_flag))
det_only = int(np.sum(~ml_flag & det_flag))
neither = int(np.sum(~ml_flag & ~det_flag))

total = len(engineered_df)
agreement_rate = (both_flagged + neither) / total * 100.0
jaccard = both_flagged / max(1, (both_flagged + ml_only + det_only))

# Holdout partition metrics
h_det = df_holdout['flagged'].values
h_ml = holdout_preds
h_both = int(np.sum(h_ml & h_det))
h_ml_only = int(np.sum(h_ml & ~h_det))
h_det_only = int(np.sum(~h_ml & h_det))
h_neither = int(np.sum(~h_ml & ~h_det))
holdout_agreement = (h_both + h_neither) / len(df_holdout) * 100.0

contingency = pd.DataFrame(
    [[both_flagged, det_only], [ml_only, neither]],
    index=['ML Flagged', 'ML Normal'],
    columns=['Deterministic Flagged', 'Deterministic Normal']
)

print("=" * 60)
print(" EMPIRICAL EVALUATION MATRIX (vs Deterministic Rule)")
print("=" * 60)
display(contingency)
print(f"Overall Agreement Rate: {agreement_rate:.2f}%")
print(f"Holdout Agreement Rate: {holdout_agreement:.2f}% ({len(df_holdout)} out-of-sample weeks)")
print(f"Jaccard Similarity:     {jaccard:.4f}")
print(f"Rule Flagged Identified: {both_flagged}/{both_flagged + det_only} ({both_flagged/(both_flagged+det_only)*100:.1f}%)")
print("=" * 60)

# Discrepancy Inspection: Why did ML and Deterministic Rules disagree?
print("\n--- Discrepancy Inspection: ML Flagged, but Deterministic Rule Normal ---")
ml_novel = engineered_df[engineered_df['is_ml_anomaly'] & ~engineered_df['flagged']][
    ['route', 'week_of', 'cost_per_tonne_km', 'pct_vs_history', 'pct_vs_peers', 'momentum_1w', 'history_volatility', 'ml_anomaly_score']
].head(5)
display(ml_novel)

print("\n--- Discrepancy Inspection: Deterministic Rule Flagged, but ML Normal ---")
rule_novel = engineered_df[~engineered_df['is_ml_anomaly'] & engineered_df['flagged']][
    ['route', 'week_of', 'cost_per_tonne_km', 'pct_vs_history', 'pct_vs_peers', 'momentum_1w', 'history_volatility', 'ml_anomaly_score']
].head(5)
display(rule_novel)
"""

nb.cells[23].source = sec11_code_1
nb.cells[24].source = sec11_code_2
nb.cells[25].source = sec11_code_3

nbformat.write(nb, NOTEBOOK_PATH)
print("Updated cells 23, 24, 25 with raw strings. Now executing notebook...")

ep = ExecutePreprocessor(timeout=600, kernel_name='python3')
# Working dir at project root so imports like `backend.app.services...` work seamlessly
ep.preprocess(nb, {'metadata': {'path': str(Path('.').resolve())}})

nbformat.write(nb, NOTEBOOK_PATH)
print("SUCCESS: Notebook fully executed and saved with all cell outputs!")
