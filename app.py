import pandas as pd
import streamlit as st

from src.db import create_db_engine, save_duplicates, test_connection
from src.matching import EntityMatcher
from src.preprocess import DataCleaner


st.set_page_config(
    page_title="Dedupli-AI",
    page_icon="🧠",
    layout="wide",
)

st.title("Dedupli-AI: Akıllı Kayıt Tekilleştirme Platformu")
st.caption("Excel yükle → veri temizle → olası duplicate kayıtları bul → sonuçları incele")

if "db_engine" not in st.session_state:
    st.session_state.db_engine = create_db_engine()

if "session_id" not in st.session_state:
    st.session_state.session_id = str(pd.Timestamp.utcnow().value)

db_ok, db_message = test_connection(st.session_state.db_engine)
if db_ok:
    st.success(db_message)
else:
    st.error(db_message)
    st.caption("Docker PostgreSQL ayağa kalkmadıysa önce devops klasöründe docker compose up -d komutunu çalıştır.")

uploaded = st.file_uploader("Excel dosyanı yükle (.xlsx)", type=["xlsx"])

if uploaded is None:
    st.info("Başlamak için bir Excel dosyası yükle.")
    st.stop()

with st.spinner("Excel okunuyor..."):
    df_raw = pd.read_excel(uploaded)

st.success(f"Dosya yüklendi. Kayıt sayısı: {len(df_raw):,}".replace(",", "."))

if df_raw.empty:
    st.warning("Yüklenen dosyada kayıt yok. Lütfen en az 1 satır veri içeren bir Excel yükle.")
    st.stop()

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

    if st.button("Duplicate sonuçlarını PostgreSQL'e kaydet", type="primary"):
        if not db_ok:
            st.error("Kayıt yapılamadı: PostgreSQL bağlantısı yok.")
        else:
            with st.spinner("Sonuçlar PostgreSQL'e kaydediliyor..."):
                inserted = save_duplicates(st.session_state.db_engine, duplicates_view, st.session_state.session_id)
            st.success(f"Kayıt tamamlandı. Eklenen satır sayısı: {inserted}")

with st.expander("Kural çıktıları (debug amaçlı)", expanded=False):
    st.write(
        "Aşağıdaki tablo, bloklama sonrası aday çiftlerde her kuralın 0/1 çıktısını gösterir. "
        "Duplicate filtrelemesi: `name_jw + tc_exact + phone_exact + email_exact >= 2`"
    )
    st.dataframe(duplicates_features.reset_index().rename(columns={"level_0": "left_index", "level_1": "right_index"}), use_container_width=True)