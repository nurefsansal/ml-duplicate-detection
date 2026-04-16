import pandas as pd
import streamlit as st

from src.matching import EntityMatcher
from src.preprocess import DataCleaner


st.set_page_config(
    page_title="Dedupli-AI",
    page_icon="🧠",
    layout="wide",
)

st.title("Dedupli-AI: Akıllı Kayıt Tekilleştirme Platformu")
st.caption("Excel yükle → veri temizle → olası duplicate kayıtları bul → sonuçları incele")

uploaded = st.file_uploader("Excel dosyanı yükle (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Başlamak için bir Excel dosyası yükle.")
    st.stop()

with st.spinner("Excel okunuyor..."):
    df_raw = pd.read_excel(uploaded)

st.success(f"Dosya yüklendi. Kayıt sayısı: {len(df_raw):,}".replace(",", "."))

with st.spinner("Veri temizleniyor (clean_* sütunları üretiliyor)..."):
    cleaner = DataCleaner()
    df_clean = cleaner.process(df_raw)

with st.expander("Temizlenmiş alanlardan örnek (ilk 20 satır)", expanded=False):
    cols = [c for c in ["Ad Soyad", "Şehir", "Telefon", "TC", "E-mail", "clean_name", "clean_city", "clean_phone", "clean_tc", "clean_email"] if c in df_clean.columns]
    st.dataframe(df_clean[cols].head(20), use_container_width=True)

with st.spinner("Akıllı eşleştirme çalışıyor (recordlinkage)..."):
    matcher = EntityMatcher()
    pairs, features, duplicates_features = matcher.find_duplicates(df_clean)
    duplicates_view = matcher.duplicates_as_dataframe(df_clean, duplicates_features)

left, right = st.columns(2)
with left:
    st.metric("Aday karşılaştırma çifti", f"{len(pairs):,}".replace(",", "."))
with right:
    st.metric("Olası duplicate çifti (>= 2 kural)", f"{len(duplicates_features):,}".replace(",", "."))

st.subheader("Olası duplicate kayıtlar")
if duplicates_view.empty:
    st.warning("Bu kurallara göre duplicate bulunamadı.")
else:
    st.dataframe(duplicates_view, use_container_width=True, height=520)

with st.expander("Kural çıktıları (debug amaçlı)", expanded=False):
    st.write(
        "Aşağıdaki tablo, bloklama sonrası aday çiftlerde her kuralın 0/1 çıktısını gösterir. "
        "Duplicate filtrelemesi: `name_jw + tc_exact + phone_exact + email_exact >= 2`"
    )
    st.dataframe(duplicates_features.reset_index().rename(columns={"level_0": "left_index", "level_1": "right_index"}), use_container_width=True)