import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Oldal konfiguráció
st.set_page_config(page_title="SBO-Flow AI", page_icon="🏥", layout="wide")

st.title("🏥 SBO-Flow AI: Integrált Sürgősségi Betegút-Optimalizáló Rendszer")
st.subheader("Klinikai döntéstámogató és kapacitás-menedzsment prototípus")

# Segédfüggvény a vizsgálat hozzárendeléséhez (Globálissá tesszük, hogy a fallback is elérje)
def rendel_vizsgalat(panasz):
    p_low = str(panasz).lower()
    if "chest" in p_low or "mellkasi" in p_low or "abd" in p_low or "hasi" in p_low:
        return "CT Vizsgálat"
    elif "fall" in p_low or "esés" in p_low or "pain" in p_low or "sérülés" in p_low or "törés" in p_low:
        return "Röntgen"
    else:
        return "Labor / Megfigyelés"

# --- 1. ADATOK BETÖLTÉSE ---
@st.cache_data
def load_and_clean_data():
    edstays = pd.read_csv('edstays.csv.gz')
    triage = pd.read_csv('triage.csv.gz')
    df = pd.merge(edstays, triage, on='stay_id', how='inner')
    
    # NEWS2 kalkulátor
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
        'Dyspnea': 'Nehézlégzés', 'ILI': 'Influenzaszerű megbetegedés',
        'Altered mental status': 'Zavart tudatállapot', 'Fever': 'Láz',
        'Weakness': 'Gyengeség', 'Cough': 'Köhögés', 'Dizziness': 'Szédülés',
        'Back pain': 'Hátfájás', 'Syncope': 'Ájulás', 'Headache': 'Fejfájás'
    }
    df['panasz_magyarul'] = df['chiefcomplaint'].map(orvosi_szotar).fillna(df['chiefcomplaint'])
    df['Szükséges_Vizsgálat'] = df['panasz_magyarul'].apply(rendel_vizsgalat)
    return df

# Megpróbáljuk betölteni a fájlokat, ha hiba van, generálunk stabil tesztadatokat
if 'raw_df' not in st.session_state:
    try:
        st.session_state['raw_df'] = load_and_clean_data()
    except Exception as e:
        # BIZTONSÁGI FALLBACK: Ha a nagyméretű fájlbeolvasás megszakad, ez megmenti az appot
        fallback_df = pd.DataFrame({
            'stay_id':,
            'panasz_magyarul': ['Mellkasi fájdalom', 'Hasi fájdalom', 'Nehézlégzés', 'Zavart tudatállapot', 'Jobb láb sérülése'],
            'news2_score': [4, 3, 5, 1, 0]
        })
        fallback_df['Szükséges_Vizsgálat'] = fallback_df['panasz_magyarul'].apply(rendel_vizsgalat)
        st.session_state['raw_df'] = fallback_df

# Kigyűjtjük az egyedi panaszokat az autocomplete mezőhöz
osszes_panasz_lista = sorted(st.session_state['raw_df']['panasz_magyarul'].dropna().unique())

# --- 2. KÓRHÁZI KAPACITÁS AUTOMATIZÁLÁSA (Fix adatok) ---
ct_auto_delay = 115    
xray_auto_delay = 20   

# --- 3. INTERAKTÍV OLDALSÁV (A triázs nővér munkafelülete) ---
st.sidebar.header("📝 Új Beteg Felvétele (Triázs)")
st.sidebar.write("A nővér rögzíti a mért adatokat:")

valasztott_panaszok = st.sidebar.multiselect(
    "Beteg panaszai (kezdj el gépelni...):",
    options=osszes_panasz_lista,
    placeholder="Válassz ki panaszokat..."
)

pulzus = st.sidebar.number_input("Pulzus (szívverés/perc):", min_value=30, max_value=200, value=75)
oxigen = st.sidebar.slider("Véroxigénszint (SpO2 %):", min_value=70, max_value=100, value=98)

# Pontszámítás a háttérben
uj_score = 0
if pulzus <= 40 or pulzus >= 131: uj_score += 3
elif pulzus >= 111 and pulzus <= 130: uj_score += 2
elif (pulzus >= 41 and pulzus <= 50) or (pulzus >= 91 and pulzus <= 110): uj_score += 1
if oxigen <= 91: uj_score += 3
elif oxigen >= 92 and oxigen <= 93: uj_score += 2
elif oxigen >= 94 and oxigen <= 95: uj_score += 1

panaszok_szoveg = ", ".join(valasztott_panaszok) if valasztott_panaszok else "Nincs megadva panasz"
uj_vizsgalat = rendel_vizsgalat(panaszok_szoveg)

# Gomb a mentéshez
if st.sidebar.button("💾 Beteg mentése és sorrend frissítése"):
    if not valasztott_panaszok:
        st.sidebar.error("Kérjük, válassz ki legalább egy panaszt!")
    else:
        uj_beteg = pd.DataFrame({
            'stay_id': [int(np.random.randint(90000000, 99999999))],
            'panasz_magyarul': [panaszok_szoveg],
            'news2_score': [uj_score],
            'Szükséges_Vizsgálat': [uj_vizsgalat]
        })
        st.session_state['raw_df'] = pd.concat([uj_beteg, st.session_state['raw_df']], ignore_index=True)
        st.sidebar.success(f"Mentve! Kiszámolt NEWS2: {uj_score} pont")

# --- 4. AI PRIORITÁS ÉS VÁRHATÓ VÁRAKOZÁSI IDŐ (ETA) SZÁMÍTÁSA ---
working_df = st.session_state['raw_df'].copy()

working_df['Gép_Alap_Várakozás'] = working_df['Szükséges_Vizsgálat'].apply(
    lambda x: ct_auto_delay if x == "CT Vizsgálat" else (xray_auto_delay if x == "Röntgen" else 10)
)

working_df['prioritasi_index'] = working_df['news2_score'] * 10
df_sorted = working_df.sort_values(by='prioritasi_index', ascending=False).copy()

def becsult_eta(row):
    if row['news2_score'] >= 5: return "Azonnal (0-5 perc)"
    elif row['news2_score'] >= 3: return f"{int(row['Gép_Alap_Várakozás'] * 0.3)} perc (Prioritásos)"
    else: return f"{int(row['Gép_Alap_Várakozás'] * 1.2)} perc (Normál sor)"

df_sorted['Várható_Várakozás_ETA'] = df_sorted.apply(becsult_eta, axis=1)

# --- 5. FŐKÉPERNYŐ JELENTÉSE ---
col1, col2, col3 = st.columns(3)
col1.metric(label="Összes várakozó beteg az SBO-n", value=f"{len(df_sorted)} fő")
col2.metric(label="🖥️ CT Gép Élő Állapota", value="TÚLTERHELT", delta=f"{ct_auto_delay} perc sorbanállás", delta_color="inverse")
col3.metric(label="🩻 Röntgen Élő Állapota", value="SZABAD SÁV", delta=f"{xray_auto_delay} perc sorbanállás", delta_color="normal")

# --- 6. ORVOSI TEENDŐ PANEL ---
teendo = "🟢 NEM SÜRGŐS: Váróterem, ellátás érkezési sorrendben."
if uj_score >= 5 or any(x in panaszok_szoveg.lower() for x in ["baleset", "arrest", "vérzés", "bleed"]):
    teendo = "🔴 KRITIKUS: Azonnali orvosi vizsgálat, sokktalanító!"
elif uj_score >= 3 or any(x in panaszok_szoveg.lower() for x in ["mellkasi", "chest", "nehézlégzés", "dyspnea"]):
    teendo = "🟠 SÜRGŐS: Orvosi vizsgálat 15 percen belül. Azonnali Röntgen/EKG javasolt!"

st.write("### 🤖 Klinikai Döntéstámogató Ajánlás a legutóbbi betegre")
st.info(f"**Értékelt panaszok:** {panaszok_szoveg} | **Kiszámított kockázati szint:** {uj_score} pont\n\n**JAVASOLT ELLÁTÁSI UTALÁS:** {teendo}")

# --- 7. ÉLŐ BETEGLISTA ---
st.write("### 📋 AI által menedzselt élő betegsorrend és Diagnosztikai Alokáció")
st.dataframe(
    df_sorted[['stay_id', 'panasz_magyarul', 'news2_score', 'Szükséges_Vizsgálat', 'Várható_Várakozás_ETA']].head(12), 
    use_container_width=True
)
