import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.model_selection import train_test_split

MODEL_PATH = Path("backend/models/model.pkl")


FEATURE_COLS = [
    "tc_exact_match",
    "tc_conflict",
    "phone_exact_match",
    "phone_last7_match",
    "email_exact_match",
    "city_exact_match",
    "phonetic_exact_match",
    "metaphone_exact_match",
    "phonetic_close_match",
    "name_similarity",
    "name_jaro_winkler",
    "name_levenshtein_similarity",
    "email_similarity",
    "first_name_similarity",
    "surname_similarity",
    "first_name_jaro_winkler",
    "surname_jaro_winkler",
    "first_name_exact_match",
    "surname_exact_match",
    "shared_contact_flag",
    "shared_contact_name_conflict",
    "household_risk_flag",
    "common_non_empty_fields",
]


def load_data(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        alt_path = Path("backend/models/training_candidates.csv")
        if alt_path.exists():
            path = alt_path
        else:
            raise ValueError(f"Egitim veri dosyasi bulunamadi: {csv_path}")

    df = pd.read_csv(path)

    if "label" not in df.columns:
        df["label"] = ""

    return df


def _derive_weak_labels(df: pd.DataFrame) -> pd.Series:
    def _int_col(col: str) -> pd.Series:
        if col in df.columns:
            return df[col].fillna(0).astype(int)
        return pd.Series([0] * len(df), index=df.index)

    def _float_col(col: str) -> pd.Series:
        if col in df.columns:
            return df[col].fillna(0).astype(float)
        return pd.Series([0.0] * len(df), index=df.index)

    tc_exact = _int_col("tc_exact_match")
    tc_conflict = _int_col("tc_conflict")
    phone_exact = _int_col("phone_exact_match")
    email_exact = _int_col("email_exact_match")
    shared_contact = _int_col("shared_contact_flag")
    shared_contact_name_conflict = _int_col("shared_contact_name_conflict")
    household_risk = _int_col("household_risk_flag")

    name_similarity = _float_col("name_similarity")
    phonetic_exact = _int_col("phonetic_exact_match")
    metaphone_exact = _int_col("metaphone_exact_match")

    weak = pd.Series([-1] * len(df), index=df.index)

    positive_rule = (
        (tc_exact == 1)
        | ((email_exact == 1) & (name_similarity >= 0.85))
        | ((phone_exact == 1) & (name_similarity >= 0.88))
        | ((name_similarity >= 0.97) & ((phonetic_exact == 1) | (metaphone_exact == 1)))
    )

    negative_rule = (
        (tc_conflict == 1)
        | ((household_risk == 1) & (shared_contact_name_conflict == 1) & (tc_exact == 0))
        | ((name_similarity < 0.55) & (shared_contact == 1))
    )

    weak.loc[positive_rule] = 1
    weak.loc[negative_rule] = 0

    return weak


def prepare_training_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    # Label boş olanları çıkar
    source_df = df.copy()
    df = df.copy()
    df["label"] = df["label"].astype(str).str.strip()

    df = df[df["label"].isin(["0", "1", 0, 1])].copy()

    if df.empty:
        weak_labels = _derive_weak_labels(df=source_df)
        use_idx = weak_labels[weak_labels.isin([0, 1])].index

        if len(use_idx) == 0:
            raise ValueError("Egitim icin ne manuel ne de guvenilir otomatik etiket bulunamadi.")

        df = source_df.copy()
        df.loc[use_idx, "label"] = weak_labels.loc[use_idx].astype(int)
        df = df.loc[use_idx].copy()
        print(f"[INFO] Manuel etiket yok. Weak-label fallback kullanildi: {len(df)} satir")

    # Label'ı int'e çevir
    df["label"] = df["label"].astype(int)

    # Eski datasetlerle geriye donuk uyumluluk: eksik yeni feature kolonlarini 0 ile tamamla.
    missing_cols = [col for col in FEATURE_COLS if col not in df.columns]
    for col in missing_cols:
        df[col] = 0

    X = df[FEATURE_COLS].copy()
    y = df["label"].copy()

    # NaN temizliği
    X = X.fillna(0)

    return X, y


def train_model(df: pd.DataFrame):
    X, y = prepare_training_data(df)

    if y.nunique() < 2:
        raise ValueError("Model eğitimi için hem 0 hem 1 sınıfı gerekli.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
        max_depth=None,
        min_samples_split=4,
        min_samples_leaf=2,
        n_jobs=-1,
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)

    print(f"Accuracy : {acc:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")
    print("\nConfusion Matrix:")
    print(cm)
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, zero_division=0))

    # Feature importance yazdır
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
    print("\nFeature Importances:")
    print(importances)

    return model


def save_model(model):
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


def main():
    df = load_data("backend/models/training_data.csv")
    model = train_model(df)
    save_model(model)
    print("Model saved to backend/models/model.pkl")


if __name__ == "__main__":
    main()