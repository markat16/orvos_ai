import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Oldal konfiguráció
st.set_page_config(page_title="SBO-Flow AI", page_icon="🏥", layout="wide")

st.title("🏥 SBO-Flow AI: Integrált Sürgősségi Betegút-Optimalizáló Rendszer")
st.subheader("Klinikai döntéstámogató és kapacitás-menedzsment prototípus")

# --- 1. ADATOK BETÖLTÉSE ÉS VALÓSÁGHŰ ÁTALAKÍTÁSA ---
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
        'Dyspnea': 'Nehézlégzés', 'ILI': 'Influenzaszerű betegség',
        'Altered mental status': 'Zavart tudatállapot', 'Fever': 'Láz'
    }
    df['panasz_magyarul'] = df['chiefcomplaint'].map(orvosi_szotar).fillna(df['chiefcomplaint'])
    
    # VALÓSÁGHŰ HOZZÁRENDELÉS: Milyen vizsgálat kell a betegnek a panasza alapján?
    def rendel_vizsgalat(panasz):
        p_low = str(panasz).lower()
        if "chest" in p_low or "mellkasi" in p_low or "abd" in p_low or "hasi" in p_low:
            return "CT Vizsgálat"
        elif "fall" in p_low or "esés" in p_low or "pain" in p_low or "sérülés" in p_low:
            return "Röntgen"
        else:
            return "Labor / Megfigyelés"
            
    df['Szükséges_Vizsgálat'] = df['panasz_magyarul'].apply(rendel_vizsgalat)
    return df

if 'raw_df' not in st.session_state:
    st.session_state['raw_df'] = load_and_clean_data()

# --- 2. VALÓDI AUTOMATIKUS KÓRHÁZI KAPACITÁS (Nincs csúszka a nővérnek!) ---
# A gépek leterheltségét a kórházi rendszer automatikusan méri (fix szimulált értékek, nem állítható)
ct_auto_delay = 115    # A CT gép jelenleg kritizálódik, 115 perc a dugó
xray_auto_delay = 20   # A Röntgen viszonylag szabad, 20 perc

osszes_panasz_lista = sorted(st.session_state['raw_df']['panasz_magyarul'].dropna().unique())

# --- 3. INTERAKTÍV OLDALSÁV (Tiszta Triázs felület a nővérnek) ---
st.sidebar.header("📝 Új Beteg Felvétele (Triázs)")
st.sidebar.write("A nővér kizárólag a beteg mérhető adatait rögzíti:")

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

# Automatikus vizsgálat hozzárendelés az új betegnek is
uj_vizsgalat = "Labor / Megfigyelés"
if any(x in panaszok_szoveg.lower() for x in ["hasi", "mellkasi", "abd", "chest"]): uj_vizsgalat = "CT Vizsgálat"
elif any(x in panaszok_szoveg.lower() for x in ["baleset", "sérülés", "pain", "törés"]): uj_vizsgalat = "Röntgen"

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

# Az algoritmus beállítja a gép alapidejét
working_df['Gép_Alap_Várakozás'] = working_df['Szükséges_Vizsgálat'].apply(
    lambda x: ct_auto_delay if x == "CT Vizsgálat" else (xray_auto_delay if x == "Röntgen" else 10)
)

# Kiszámoljuk a végső prioritási indexet (NEWS2 határozza meg)
working_df['prioritasi_index'] = working_df['news2_score'] * 10
df_sorted = working_df.sort_values(by='prioritasi_index', ascending=False).copy()

# Kiszámoljuk a dinamikus várható várakozási időt (ETA-t) percekben:
# Minél magasabb a NEWS2 score, annál kevesebbet kell várnia a gép alapidejéhez képest!
def becsult_eta(row):
    if row['news2_score'] >= 5: return "Azonnal (0-5 perc)"
    elif row['news2_score'] >= 3: return f"{int(row['Gép_Alap_Várakozás'] * 0.3)} perc (Prioritásos)"
    else: return f"{int(row['Gép_Alap_Várakozás'] * 1.2)} perc (Normál sor)"

df_sorted['Várható_Várakozás_ETA'] = df_sorted.apply(becsult_eta, axis=1)

# --- 5. FŐKÉPERNYŐ AUTOMATIKUS KÓRHÁZI KPI JELENTÉSE ---
col1, col2, col3 = st.columns(3)
col1.metric(label="Összes várakozó beteg az SBO-n", value=f"{len(df_sorted)} fő")
col2.metric(label="🖥️ CT Gép Élő Állapota", value="TÚLTERHELT", delta=f"{ct_auto_delay} perc sorbanállás", delta_color="inverse")
col3.metric(label="🩻 Röntgen Élő Állapota", value="SZABAD SÁV", delta=f"{xray_delay} perc sorbanállás", delta_color="normal")

# --- 6. ÉLŐ BETEGLISTA (A precíz orvosi táblázat) ---
st.write("### 📋 AI által menedzselt élő betegsorrend és Diagnosztikai Alokáció")
st.dataframe(
    df_sorted[['stay_id', 'panasz_magyarul', 'news2_score', 'Szükséges_Vizsgálat', 'Várható_Várakozás_ETA']].head(12), 
    use_container_width=True
)
