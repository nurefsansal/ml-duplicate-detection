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
    "name_similarity",
    "email_similarity",
    "first_name_similarity",
    "surname_similarity",
    "first_name_exact_match",
    "surname_exact_match",
    "shared_contact_flag",
    "shared_contact_name_conflict",
    "household_risk_flag",
    "common_non_empty_fields",
]


def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    if "label" not in df.columns:
        raise ValueError("training_data.csv içinde 'label' kolonu yok.")

    return df


def prepare_training_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    # Label boş olanları çıkar
    df = df.copy()
    df["label"] = df["label"].astype(str).str.strip()

    df = df[df["label"].isin(["0", "1", 0, 1])].copy()

    if df.empty:
        raise ValueError("Eğitim için geçerli label bulunamadı. Label kolonunu 0/1 olarak doldurmalısın.")

    # Label'ı int'e çevir
    df["label"] = df["label"].astype(int)

    # Feature kolonlarını kontrol et
    missing_cols = [col for col in FEATURE_COLS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Eksik feature kolonları var: {missing_cols}")

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