import pandas as pd
import re

from backend.schemas.requests import RecordIn


def canonical_name(value: str) -> str:
    if not value:
        return ""
    tokens = [t for t in str(value).split(" ") if t]
    return " ".join(sorted(set(tokens)))


def phonetic_name_key(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"[^A-Z]", "", str(value).upper())
    no_vowels = re.sub(r"[AEIIOOUU]", "", text)
    return re.sub(r"(.)\1+", r"\1", no_vowels)[:16]


def normalize_email_key(value: str) -> str:
    if not value:
        return ""
    email = str(value).lower().strip()
    if "@" not in email:
        return email
    user, domain = email.split("@", 1)
    user = user.split("+")[0].replace(".", "")
    return f"{user}@{domain}"


def to_dataframe(records: list[RecordIn]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Ad Soyad": r.adSoyad,
                "TC": r.tcKimlikNo,
                "Telefon": r.telefon,
                "E-mail": r.email,
                "Şehir": r.sehir,
            }
            for r in records
        ]
    )


def json_rows(df: pd.DataFrame) -> list[dict]:
    return df.where(pd.notna(df), None).to_dict(orient="records")


def dict_records_from_df(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []

    def pick(row: pd.Series, *keys: str) -> str:
        for key in keys:
            if key in row and pd.notna(row[key]):
                value = str(row[key]).strip()
                if value:
                    return value
        return ""

    out: list[dict] = []
    for _, row in df.iterrows():
        out.append(
            {
                "adSoyad": pick(row, "Ad Soyad", "adSoyad", "name", "fullName"),
                "tcKimlikNo": pick(row, "TC", "tcKimlikNo", "tc", "identity", "idNumber"),
                "telefon": pick(row, "Telefon", "telefon", "phone", "mobile"),
                "email": pick(row, "E-mail", "email", "mail"),
                "sehir": pick(row, "Şehir", "Sehir", "sehir", "city"),
            }
        )
    return out