from __future__ import annotations

import re
from typing import Any

import pandas as pd

from src.preprocess import DataCleaner
from backend.schemas.requests import RecordIn
from backend.services.advanced_matching_service import build_name_keys

NAME_COLUMN = "Ad Soyad"
TC_COLUMN = "TC"
PHONE_COLUMN = "Telefon"
EMAIL_COLUMN = "E-mail"
CITY_COLUMN = "Åehir"
ADDRESS_COLUMN = "Adres"
MUHATAP_NO_COLUMN = "Muhatap No"

PREVIEW_COLUMNS = [
    NAME_COLUMN,
    CITY_COLUMN,
    PHONE_COLUMN,
    TC_COLUMN,
    EMAIL_COLUMN,
    MUHATAP_NO_COLUMN,
    "clean_name",
    "first_name",
    "last_name",
    "ordered_name",
    "canonical_name",
    "name_phonetic",
    "name_phonetic_key",
    "clean_city",
    "clean_address",
    "clean_muhatap_no",
    "clean_phone",
    "phone_last7",
    "clean_tc",
    "clean_email",
    "email_normalized_key",
    "blocking_key",
    "is_valid",
]

SOURCE_FIELD_TARGETS = {
    "ad soyad": "name",
    "ad": "name",
    "soyad": "name",
    "name": "name",
    "full name": "name",
    "fullname": "name",
    "tc kimlik no": "tc",
    "tc": "tc",
    "tckn": "tc",
    "identity": "tc",
    "idnumber": "tc",
    "telefon": "phone",
    "phone": "phone",
    "tel": "phone",
    "mobile": "phone",
    "email": "email",
    "e-posta": "email",
    "mail": "email",
    "e mail": "email",
    "sehir": "city",
    "şehir": "city",
    "city": "city",
    "il": "city",
    "adres": "address",
    "address": "address",
    "muhatap no": "muhatap_no",
    "muhatap kodu": "muhatap_no",
    "muhatap": "muhatap_no",
    "customer id": "muhatap_no",
    "customerid": "muhatap_no",
    "donor id": "muhatap_no",
    "donorid": "muhatap_no",
    "musteri no": "muhatap_no",
    "musteri kodu": "muhatap_no",
}

FILE_COLUMN_MAP = {
    "ad soyad": NAME_COLUMN,
    "ad": NAME_COLUMN,
    "soyad": NAME_COLUMN,
    "name": NAME_COLUMN,
    "tc kimlik no": TC_COLUMN,
    "tc": TC_COLUMN,
    "tckn": TC_COLUMN,
    "telefon": PHONE_COLUMN,
    "phone": PHONE_COLUMN,
    "tel": PHONE_COLUMN,
    "email": EMAIL_COLUMN,
    "e-posta": EMAIL_COLUMN,
    "mail": EMAIL_COLUMN,
    "sehir": CITY_COLUMN,
    "şehir": CITY_COLUMN,
    "city": CITY_COLUMN,
    "il": CITY_COLUMN,
    "adres": ADDRESS_COLUMN,
    "address": ADDRESS_COLUMN,
    "muhatap no": MUHATAP_NO_COLUMN,
    "muhatap kodu": MUHATAP_NO_COLUMN,
    "muhatap": MUHATAP_NO_COLUMN,
    "customer id": MUHATAP_NO_COLUMN,
    "customerid": MUHATAP_NO_COLUMN,
    "donor id": MUHATAP_NO_COLUMN,
    "donorid": MUHATAP_NO_COLUMN,
    "musteri no": MUHATAP_NO_COLUMN,
    "musteri kodu": MUHATAP_NO_COLUMN,
}


def canonical_name(value: str) -> str:
    if not value:
        return ""
    tokens = [token for token in str(value).split(" ") if token]
    return " ".join(sorted(dict.fromkeys(tokens)))


def phonetic_name_key(value: str) -> str:
    return build_name_keys(value).get("soundex_key", "")


def metaphone_name_key(value: str) -> str:
    return build_name_keys(value).get("metaphone_key", "")


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
                NAME_COLUMN: r.adSoyad,
                TC_COLUMN: r.tcKimlikNo,
                PHONE_COLUMN: r.telefon,
                EMAIL_COLUMN: r.email,
                CITY_COLUMN: r.sehir,
                ADDRESS_COLUMN: getattr(r, "adres", ""),
            }
            for r in records
        ]
    )


def json_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.where(pd.notna(df), None).to_dict(orient="records")


def dict_records_from_df(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty:
        return []

    def pick(row: pd.Series, *keys: str) -> str:
        for key in keys:
            if key in row and pd.notna(row[key]):
                value = str(row[key]).strip()
                if value:
                    return value
        return ""

    out: list[dict[str, str]] = []
    for _, row in df.iterrows():
        out.append(
            {
                "adSoyad": pick(row, NAME_COLUMN, "adSoyad", "name", "fullName"),
                "tcKimlikNo": pick(row, TC_COLUMN, "tcKimlikNo", "tc", "identity", "idNumber"),
                "telefon": pick(row, PHONE_COLUMN, "telefon", "phone", "mobile"),
                "email": pick(row, EMAIL_COLUMN, "email", "mail"),
                "sehir": pick(row, CITY_COLUMN, "Sehir", "sehir", "city"),
            }
        )
    return out


def extract_first_last_name(clean_name: str) -> tuple[str, str]:
    value = str(clean_name or "").strip()
    if not value:
        return "", ""

    parts = [part for part in value.split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def generate_ordered_name(clean_name: str) -> str:
    return canonical_name(clean_name)


def generate_name_phonetic(clean_name: str) -> str:
    ordered_name = generate_ordered_name(clean_name)
    return phonetic_name_key(ordered_name or clean_name)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    text = str(value).strip().upper()
    replacements = str.maketrans(
        {
            "Ç": "C",
            "Ğ": "G",
            "İ": "I",
            "I": "I",
            "Ö": "O",
            "Ş": "S",
            "Ü": "U",
            "ç": "C",
            "ğ": "G",
            "ı": "I",
            "ö": "O",
            "ş": "S",
            "ü": "U",
        }
    )
    text = text.translate(replacements)
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def infer_target_field_name(source_column_name: str) -> str:
    normalized = re.sub(r"\s+", " ", str(source_column_name or "").strip().lower())
    return SOURCE_FIELD_TARGETS.get(normalized, "ignored")


def build_column_mapping_definitions(source_columns: list[str]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    for source_column_name in source_columns:
        target_field_name = infer_target_field_name(source_column_name)
        mapping_type = "direct" if target_field_name != "ignored" else "ignored"
        mappings.append(
            {
                "source_column_name": str(source_column_name),
                "target_field_name": target_field_name,
                "is_required": target_field_name == "name",
                "mapping_type": mapping_type,
            }
        )
    return mappings


def canonicalize_upload_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df.columns = [
        FILE_COLUMN_MAP.get(str(column).lower().strip(), column)
        for column in df.columns
    ]

    if NAME_COLUMN not in df.columns:
        raise ValueError("Eksik zorunlu kolon: Ad Soyad")

    for column in [TC_COLUMN, PHONE_COLUMN, EMAIL_COLUMN, CITY_COLUMN, ADDRESS_COLUMN, MUHATAP_NO_COLUMN]:
        if column not in df.columns:
            df[column] = ""

    return df


def generate_blocking_key(record: dict[str, Any]) -> str:
    clean_tc = str(record.get("clean_tc", "") or "").strip()
    clean_phone = str(record.get("clean_phone", "") or "").strip()
    clean_email = str(record.get("email_normalized_key", "") or "").strip()
    name_phonetic = str(record.get("name_phonetic", "") or "").strip()
    clean_city = str(record.get("clean_city", "") or "").strip()
    ordered_name = str(record.get("ordered_name", "") or "").strip()

    if clean_tc:
        return f"tc:{clean_tc}"
    if clean_phone:
        return f"phone:{clean_phone[-7:]}"
    if clean_email:
        return f"email:{clean_email}"
    if name_phonetic and clean_city:
        return f"phonetic_city:{name_phonetic}:{clean_city}"
    if ordered_name:
        return f"name:{ordered_name}"
    return ""


def prepare_normalized_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    cleaner = DataCleaner()
    normalized = cleaner.process(df_raw.copy())

    if ADDRESS_COLUMN not in normalized.columns:
        normalized[ADDRESS_COLUMN] = ""

    name_parts = normalized["clean_name"].apply(extract_first_last_name)
    normalized["first_name"] = name_parts.apply(lambda value: value[0])
    normalized["last_name"] = name_parts.apply(lambda value: value[1])
    normalized["ordered_name"] = normalized["clean_name"].apply(generate_ordered_name)
    normalized["canonical_name"] = normalized["ordered_name"]
    normalized["name_phonetic"] = normalized["ordered_name"].apply(generate_name_phonetic)
    normalized["name_phonetic_key"] = normalized["name_phonetic"]
    normalized["phone_last7"] = normalized["clean_phone"].apply(
        lambda value: str(value or "")[-7:] if value else ""
    )
    normalized["email_normalized_key"] = normalized["clean_email"].apply(normalize_email_key)
    normalized["clean_address"] = normalized[ADDRESS_COLUMN].apply(normalize_text)
    if MUHATAP_NO_COLUMN in normalized.columns:
        normalized["clean_muhatap_no"] = normalized[MUHATAP_NO_COLUMN].apply(
            lambda v: re.sub(r"\s+", "", str(v or "")).upper() if v and not (isinstance(v, float) and pd.isna(v)) else ""
        )
    else:
        normalized["clean_muhatap_no"] = ""
    normalized["is_valid"] = normalized["clean_name"].astype(str).str.strip() != ""
    normalized["blocking_key"] = normalized.apply(
        lambda row: generate_blocking_key(row.to_dict()),
        axis=1,
    )
    return normalized


def build_preview_rows(normalized_df: pd.DataFrame) -> list[dict[str, Any]]:
    selected = normalized_df[[col for col in PREVIEW_COLUMNS if col in normalized_df.columns]]
    return json_rows(selected)
