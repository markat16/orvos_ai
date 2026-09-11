import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Oldal konfiguráció beállítása (orvosi téma)
st.set_page_config(page_title="SBO-Flow AI", page_icon="🏥", layout="wide")

st.title("🏥 SBO-Flow AI: Integrált Sürgősségi Betegút-Optimalizáló Rendszer")
st.subheader("Klinikai döntéstámogató és kapacitás-menedzsment prototípus")

# --- 1. ADATOK BETÖLTÉSE ÉS ELŐKÉSZÍTÉSE ---
@st.cache_data # Gyorsítótárazás, hogy ne olvassa be újra minden kattintásra
def load_and_clean_data():
    # Itt a te meglévő Drive-os útvonalaidat kell megadni, vagy ha lokálisan futtatod, a sima fájlnevet
    edstays = pd.read_csv('edstays.csv.gz')
    triage = pd.read_csv('triage.csv.gz')
    df = pd.merge(edstays, triage, on='stay_id', how='inner')
    
    # Egyszerűsített NEWS2 kalkulátor a háttérben
    def get_news2(row):
        score = 0
        if pd.notna(row['heartrate']):
            if row['heartrate'] <= 40 or row['heartrate'] >= 131: score += 3
            elif row['heartrate'] >= 111: score += 2
        if pd.notna(row['o2sat']) and row['o2sat'] <= 91: score += 3
        return score
    
    df['news2_score'] = df.apply(get_news2, axis=1)
    
    # A te magyar szótárad leképezése
    orvosi_szotar = {'Abd pain': 'Hasi fájdalom', 'Chest pain': 'Mellkasi fájdalom', 'Dyspnea': 'Nehézlégzés', 'ILI': 'Influenzaszerű betegség'}
    df['panasz_magyarul'] = df['chiefcomplaint'].map(orvosi_szotar).fillna(df['chiefcomplaint'])
    return df

# Próbáljuk betölteni az adatokat (ha nincsenek a mappában, tesztadatokat generálunk)
try:
    df = load_and_clean_data()
except:
    # Biztonsági fallback tesztadatok, ha a fájlok épp nincsenek kéznél
    df = pd.DataFrame({
        'stay_id': [3001, 3002, 3003, 3004, 3005],
        'panasz_magyarul': ['Mellkasi fájdalom', 'Hasi fájdalom', 'Nehézlégzés', 'Zavart tudatállapot', 'Lábtörés'],
        'news2_score': [4, 1, 4, 3, 0]
    })

# --- 2. INTERAKTÍV OLDALSÁV (A felhasználói vezérlés) ---
st.sidebar.header("🕹️ Kórházi Erőforrás Vezérlőpult")
st.sidebar.write("Állítsd be a diagnosztikai gépek aktuális leterheltségét:")

# Csúszkák (Sliders) létrehozása – ezek módosítják a Python változókat élőben!
ct_delay = st.sidebar.slider("CT várható várakozási idő (perc)", min_value=5, max_value=180, value=90)
xray_delay = st.sidebar.slider("Röntgen várható várakozási idő (perc)", min_value=5, max_value=60, value=15)

# --- 3. DINAMIKUS PRIORITÁS ÚJRASZÁMÍTÁSA ---
# Az optimalizációs logikád: kombináljuk a klinikai pontot és a gép leterheltségét
df['szimulalt_ct_dugo'] = ct_delay
df['prioritasi_index'] = df['news2_score'] * 10 - (df['szimulalt_ct_dugo'] * 0.05)
df_sorted = df.sort_values(by='prioritasi_index', ascending=False)

# --- 4. FŐKÉPERNYŐ MEGJELENÍTÉSE (KPI Kártyák) ---
col1, col2, col3 = st.columns(3)
col1.metric(label="Összes várakozó beteg", value=f"{len(df_sorted)} fő")
col2.metric(label="Aktuális CT Válaszidő", value=f"{ct_delay} perc", delta="Túlterhelt!" if ct_delay > 60 else "Normál")
col3.metric(label="Röntgen Válaszidő", value=f"{xray_delay} perc")

# --- 5. ÉLŐ BETEGLISTA (A dinamikus táblázat) ---
st.write("### 📋 AI által menedzselt élő betegsorrend (SBO)")
st.dataframe(
    df_sorted[['stay_id', 'panasz_magyarul', 'news2_score']].head(10),
    use_container_width=True
)

# --- 6. A GYÖNYÖRŰ MATPLOTLIB GRAFIKONOD INTEGRÁLÁSA ---
st.write("### 📈 Betegallokációs Térkép")
fig, ax = plt.subplots(figsize=(10, 4))
sns.scatterplot(data=df_sorted, x='szimulalt_ct_dugo', y='news2_score', hue='news2_score', palette='flare', ax=ax)
ax.set_xlabel("Szimulált gép várakozási idő (perc)")
ax.set_ylabel("NEWS2 Pontszám")
st.pyplot(fig)
