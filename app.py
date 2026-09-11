import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Oldal konfiguráció
st.set_page_config(page_title="SBO-Flow AI", page_icon="🏥", layout="wide")

st.title("🏥 SBO-Flow AI: Integrált Sürgősségi Betegút-Optimalizáló Rendszer")
st.subheader("Klinikai döntéstámogató és kapacitás-menedzsment prototípus")

# --- 1. ADATOK BETÖLTÉSE ---
@st.cache_data
def load_and_clean_data():
    edstays = pd.read_csv('edstays.csv.gz')
    triage = pd.read_csv('triage.csv.gz')
    df = pd.merge(edstays, triage, on='stay_id', how='inner')
    
    # Alapértelmezett NEWS2 pontozás a történelmi adatokra
    def get_news2(row):
        score = 0
        if pd.notna(row['heartrate']):
            if row['heartrate'] <= 40 or row['heartrate'] >= 131: score += 3
            elif row['heartrate'] >= 111: score += 2
        if pd.notna(row['o2sat']) and row['o2sat'] <= 91: score += 3
        return score
    
    df['news2_score'] = df.apply(get_news2, axis=1)
    
    orvosi_szotar = {
        'Abd pain': 'Hasi fájdalom', 'Chest pain': 'Mellkasi fájdalom', 
        'Dyspnea': 'Nehézlégzés', 'ILI': 'Influenzaszerű betegség'
    }
    df['panasz_magyarul'] = df['chiefcomplaint'].map(orvosi_szotar).fillna(df['chiefcomplaint'])
    return df

if 'raw_df' not in st.session_state:
    st.session_state['raw_df'] = load_and_clean_data()

# --- 2. INTERAKTÍV OLDALSÁV (A triázs nővér munkafelülete) ---
st.sidebar.header("🕹️ Kórházi Erőforrás Vezérlőpult")
ct_delay = st.sidebar.slider("CT várható várakozási idő (perc)", min_value=5, max_value=180, value=90)
xray_delay = st.sidebar.slider("Röntgen várható várakozási idő (perc)", min_value=5, max_value=60, value=15)

st.sidebar.markdown("---")
st.sidebar.header("📝 Új Beteg Felvétele (Triázs)")
st.sidebar.write("A nővér ide gépeli be a mért adatokat:")

# Nővér beviteli mezői
uj_panasz = st.sidebar.selectbox("Elsődleges panasz:", [
    "Mellkasi fájdalom (Infarktus gyanú)", 
    "Nehézlégzés / Fulladás",
    "Gépjármű baleset / Sérülés", 
    "Hasi fájdalom",
    "Kullancscsípés / Receptírás"
])

pulzus = st.sidebar.number_input("Pulzus (szívverés/perc):", min_value=30, max_value=200, value=75)
oxigen = st.sidebar.slider("Véroxigénszint (SpO2 %):", min_value=70, max_value=100, value=98)

# AZ ALGORITMUSOD KISZÁMOLJA A PONTOT AZ ÉLETFUNKCIÓKBÓL (NEWS2 logika)
uj_score = 0
if pulzus <= 40 or pulzus >= 131: uj_score += 3
elif pulzus >= 111 and pulzus <= 130: uj_score += 2
elif (pulzus >= 41 and pulzus <= 50) or (pulzus >= 91 and pulzus <= 110): uj_score += 1

if oxigen <= 91: uj_score += 3
elif oxigen >= 92 and oxigen <= 93: uj_score += 2
elif oxigen >= 94 and oxigen <= 95: uj_score += 1

# Döntéstámogató logikai ajánlás meghatározása (Mit kell tenni vele?)
if uj_score >= 5 or "baleset" in uj_panasz.lower():
    teendo = "🔴 KRITIKUS: Azonnali orvosi vizsgálat, sokktalanító!"
elif uj_score >= 3 or "mellkasi" in uj_panasz.lower():
    teendo = "🟠 SÜRGŐS: Orvosi vizsgálat 15 percen belül. Röntgen javasolt!"
elif "hasi" in uj_panasz.lower() and ct_delay > 60:
    teendo = "🟡 HALASZTHATÓ: CT dugó miatt első körben ultrahang és labor javasolt."
else:
    teendo = "🟢 NEM SÜRGŐS: Váróterem, ellátás érkezési sorrendben."

# Gomb a mentéshez
if st.sidebar.button("💾 Beteg mentése és sorrend frissítése"):
    uj_beteg = pd.DataFrame({
        'stay_id': [int(np.random.randint(90000000, 99999999))],
        'panasz_magyarul': [uj_panasz],
        'news2_score': [uj_score]
    })
    st.session_state['raw_df'] = pd.concat([uj_beteg, st.session_state['raw_df']], ignore_index=True)
    st.sidebar.success(f"Mentve! Kiszámolt pontszám: {uj_score}")

# --- 3. RENDRE DEZÉS ---
working_df = st.session_state['raw_df'].copy()
working_df['szimulalt_ct_dugo'] = ct_delay
working_df['prioritasi_index'] = working_df['news2_score'] * 10 - (working_df['szimulalt_ct_dugo'] * 0.02)
df_sorted = working_df.sort_values(by='prioritasi_index', ascending=False)

# --- 4. FŐKÉPERNYŐ ---
col1, col2, col3 = st.columns(3)
col1.metric(label="Összes várakozó beteg", value=f"{len(df_sorted)} fő")
col2.metric(label="Aktuális CT Válaszidő", value=f"{ct_delay} perc")
col3.metric(label="Röntgen Válaszidő", value=f"{xray_delay} perc")

# --- 5. ORVOSI TEENDŐ PANEL (Az élő ajánlás!) ---
st.write("### 🤖 Klinikai Döntéstámogató Ajánlás a legutóbbi betegre")
st.info(f"**Értékelt panasz:** {uj_panasz} | **Kiszámított kockázati szint:** {uj_score} pont\n\n**JAVASOLT ELLÁTÁSI UTALÁS:** {teendo}")

# --- 6. ÉLŐ BETEGLISTA ---
st.write("### 📋 AI által menedzselt élő betegsorrend (SBO)")
st.dataframe(df_sorted[['stay_id', 'panasz_magyarul', 'news2_score']].head(10), use_container_width=True)
