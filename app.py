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
            gevinst_pct = (salgspris - kjops_pris) / kjops_pris
            return gevinst_pct, dato # Returner gevinst og salgsdato

    # Hvis vi aldri ble stoppet ut, beregn gevinst ved sluttdato (papirgevinst)
    siste_pris = periode_data.iloc[-1]['Close']
    gevinst_pct = (siste_pris - kjops_pris) / kjops_pris
    return gevinst_pct, periode_data.index[-1]

# --- HOVEDLOGIKK ---

if kjør_knapp:
    with st.spinner(f'Henter data for {ticker} og kjører simulering...'):
        df = hent_data(ticker, start_date, end_date)
        
        if df is None:
            st.error("Fant ingen data for denne tickeren. Sjekk at du har skrevet riktig (f.eks. EQNR.OL for Equinor).")
        else:
            st.success(f"Lastet ned {len(df)} dager med data.")
            
            # 1. IDENTIFISER OPTIMALT KJØPSPUNKT (Lavest i perioden)
            min_row = df.loc[df['Low'].idxmin()]
            optimal_dato = min_row.name
            optimal_pris = min_row['Low']
            
            st.subheader(f"🔍 Resultater for {ticker}")
            st.write(f"Simuleringen antar at du traff den absolutte bunnen den **{optimal_dato.strftime('%d.%m.%Y')}** på kurs **{optimal_pris:.2f}**.")
            
            # --- ANALYSE: OPTIMALT KJØPSPUNKT ---
            best_sl_pct = 0
            best_gevinst = -100.0
            best_salgsdato = None
            results_optimal = []
            
            # Progress bar
            my_bar = st.progress(0)
            range_sl = range(stop_loss_range[0], stop_loss_range[1] + 1)
            
            for i, sl in enumerate(range_sl):
                sl_desimal = sl / 100.0
                gevinst, salgsdato = simuler_handel(df, optimal_dato, optimal_pris, sl_desimal)
                results_optimal.append({'SL %': sl, 'Gevinst %': gevinst*100})
                
                if gevinst > best_gevinst:
                    best_gevinst = gevinst
                    best_sl_pct = sl
                    best_salgsdato = salgsdato
                
                my_bar.progress((i + 1) / len(range_sl))
            
            my_bar.empty()

            # Vis nøkkeltall
            col1, col2, col3 = st.columns(3)
            col1.metric("Optimal Kjøpsdato", f"{optimal_dato.strftime('%d.%m.%Y')}")
            col1.metric("Kjøpspris (Bunn)", f"{optimal_pris:.2f} kr")
            
            col2.metric("Beste Stop Loss", f"{best_sl_pct} %")
            salgsdato_str = best_salgsdato.strftime('%d.%m.%Y') if best_salgsdato else 'Holdes fremdeles'
            col2.metric("Salgsdato", salgsdato_str)
            
            col3.metric("Maks Gevinst", f"{best_gevinst*100:.2f} %", delta_color="normal")

            # --- VISUALISERING ---
            st.markdown("### Visuell utvikling av den optimale handelen
