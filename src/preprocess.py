import re

import pandas as pd


class DataCleaner:
    """
    Excel / tabular donor data cleaner.

    Creates normalized "clean_*" columns used by the matching engine:
    - clean_name, clean_city, clean_phone, clean_tc, clean_email
    """

    # Turkish uppercase letters and their ASCII equivalents
    _TR_MAP = str.maketrans(
        {
            "İ": "I",
            "I": "I",
            "Ğ": "G",
            "Ü": "U",
            "Ş": "S",
            "Ö": "O",
            "Ç": "C",
            "ı": "I",
            "ğ": "G",
            "ü": "U",
            "ş": "S",
            "ö": "O",
            "ç": "C",
        }
    )

    def __init__(self) -> None:
        # No state required; kept as a class for future extensibility.
        pass

    def _normalize_tr_text(self, value: object) -> str:
        """
        For 'Ad Soyad' and 'Şehir':
        - uppercase
        - translate Turkish chars to ASCII
        - remove punctuation
        - collapse whitespace
        """
        if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
            return ""

        text = str(value).strip().upper().translate(self._TR_MAP)

        # Keep letters/numbers/spaces only; drop punctuation/symbols
        text = re.sub(r"[^A-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _clean_phone(self, value: object) -> str:
        """
        For 'Telefon':
        - keep only digits
        - return last 10 digits (e.g., 532xxxxxxx)
        """
        if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
            return ""

        digits = re.sub(r"\D", "", str(value))
        if not digits:
            return ""

        # Common cases: +90 / 90 / 0 prefixed numbers; last 10 digits is safest.
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    def _clean_tc(self, value: object) -> str:
        """For 'TC': keep only digits."""
        if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
            return ""
        return re.sub(r"\D", "", str(value))

    def _clean_email(self, value: object) -> str:
        """For 'E-mail': lowercase + remove spaces."""
        if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
            return ""
        return re.sub(r"\s+", "", str(value)).lower()

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Adds new columns to a *copy* of the input df:
        - clean_name from 'Ad Soyad'
        - clean_city from 'Şehir'
        - clean_phone from 'Telefon'
        - clean_tc from 'TC'
        - clean_email from 'E-mail'
        """
        out = df.copy()

        # These are the dataset columns provided in the project definition.
        name_col = "Ad Soyad"
        city_col = "Şehir"
        phone_col = "Telefon"
        tc_col = "TC"
        email_col = "E-mail"

        # If a column is missing, create an empty series so the pipeline keeps working.
        if name_col not in out.columns:
            out[name_col] = ""
        if city_col not in out.columns:
            out[city_col] = ""
        if phone_col not in out.columns:
            out[phone_col] = ""
        if tc_col not in out.columns:
            out[tc_col] = ""
        if email_col not in out.columns:
            out[email_col] = ""

        out["clean_name"] = out[name_col].apply(self._normalize_tr_text)
        out["clean_city"] = out[city_col].apply(self._normalize_tr_text)
        out["clean_phone"] = out[phone_col].apply(self._clean_phone)
        out["clean_tc"] = out[tc_col].apply(self._clean_tc)
        out["clean_email"] = out[email_col].apply(self._clean_email)

        return out

