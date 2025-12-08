import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- KONFIGURASJON ---
st.set_page_config(page_title="Stop Loss Optimalisering", layout="wide")

st.title("📈 Aksjeanalyse: Optimal Glidende Stop Loss")
st.markdown("""
Denne appen simulerer handlestrategien din på historiske data for å finne:
1. **Optimalt kjøpspunkt:** Hvilken dag og pris ga høyest gevinst (hvis du traff bunnen)?
2. **Beste stop-loss:** Hvilken prosent ga best resultat for dette kjøpet?
3. **Generell statistikk:** Hvilken stop-loss prosent fungerer best i snitt for denne perioden?
""")

# --- SIDEBAR (INPUT) ---
with st.sidebar:
    st.header("Innstillinger")
    ticker = st.text_input("Aksje Ticker (f.eks. EQNR.OL, NHY.OL, TSLA)", value="EQNR.OL")
    
    # Bruker dagens dato minus 12 måneder som standard startdato
    default_start = pd.to_datetime("today") - pd.DateOffset(years=1)
    start_date = st.date_input("Startdato", value=default_start)
    end_date = st.date_input("Sluttdato", value=pd.to_datetime("today"))
    
    st.markdown("---")
    st.markdown("**Simulerings-innstillinger**")
    # Slider returnerer en tuple (min, max)
    stop_loss_range = st.slider("Test Stop Loss fra/til %", 1, 90, (3, 50))
    
    kjør_knapp = st.button("Kjør Analyse")

# --- FUNKSJONER ---

def hent_data(ticker, start, end):
    """Henter data fra Yahoo Finance og rydder i formatet."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty:
            return None
        
        # Håndtering av MultiIndex kolonner (vanlig i nyere yfinance versjoner)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        return df
    except Exception as e:
        st.error(f"En feil oppstod under nedlasting: {e}")
        return None

def simuler_handel(df, kjops_dato, kjops_pris, stop_loss_pct):
    """
    Kjører logikken for 'Trailing Stop Loss':
    """
    # Vi ser kun på data ETTER kjøpsdatoen
    periode_data = df[df.index > kjops_dato].copy()
    
    if periode_data.empty:
        return 0.0, None # Ingen data etter kjøp

    hoyeste_pris = kjops_pris
    
    for dato, row in periode_data.iterrows():
        # Oppdater høyeste pris (Trailing logikk)
        if row['High'] > hoyeste_pris:
            hoyeste_pris = row['High']
            
        # Beregn stop nivå basert på den nye høyeste prisen
        stop_niva = hoyeste_pris * (1 - stop_loss_pct)
        
        # Sjekk om vi blir stoppet ut (Low er lavere enn stop nivå)
        if row['Low'] <= stop_niva:
            # Vi selger når stop-loss treffes
            salgspris = stop_niva 
            gevinst_pct = (salgs
