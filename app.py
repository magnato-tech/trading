import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# Konfigurasjon av siden
st.set_page_config(page_title="Stop Loss Optimalisering", layout="wide")

st.title("📈 Aksjeanalyse: Optimal Glidende Stop Loss")
st.markdown("""
Denne appen simulerer handlestrategien din på historiske data for å finne:
1. **Optimalt kjøpspunkt:** Hvilken dag og pris ga høyest gevinst?
2. **Beste stop-loss:** Hvilken prosent ga best resultat for dette kjøpet?
3. **Generell statistikk:** Hvilken stop-loss prosent fungerer best i snitt?
""")

# --- INPUT FRA BRUKER ---
with st.sidebar:
    st.header("Innstillinger")
    ticker = st.text_input("Aksje Ticker (f.eks. EQNR.OL, NHY.OL, TSLA)", value="EQNR.OL")
    start_date = st.date_input("Startdato", value=pd.to_datetime("2023-01-01"))
    end_date = st.date_input("Sluttdato", value=pd.to_datetime("today"))
    
    st.markdown("---")
    st.markdown("**Simulerings-innstillinger**")
    stop_loss_range = st.slider("Test Stop Loss fra/til %", 1, 50, (3, 20))
    
    kjør_knapp = st.button("Kjør Analyse")

# --- FUNKSJONER ---

def hent_data(ticker, start, end):
    """Henter data fra Yahoo Finance"""
    df = yf.download(ticker, start=start, end=end)
    if df.empty:
        return None
    # Flat ut multi-index kolonner hvis de finnes (vanlig i nyere yfinance)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def simuler_handel(df, kjops_dato, kjops_pris, stop_loss_pct):
    """
    Kjører logikken:
    1. Går dag for dag etter kjøpsdato.
    2. Oppdaterer 'High Water Mark' (høyeste pris).
    3. Setter stop loss = Høyeste * (1 - stop_loss_pct).
    4. Sjekker om Low treffer stop loss.
    """
    # Vi ser kun på data ETTER kjøpsdatoen
    periode_data = df[df.index > kjops_dato]
    
    if periode_data.empty:
        return 0.0, None # Ingen data etter kjøp

    hoyeste_pris = kjops_pris
    
    for dato, row in periode_data.iterrows():
        # Oppdater høyeste pris
        if row['High'] > hoyeste_pris:
            hoyeste_pris = row['High']
            
        # Beregn stop nivå
        stop_niva = hoyeste_pris * (1 - stop_loss_pct)
        
        # Sjekk om vi blir stoppet ut (Low er lavere enn stop nivå)
        if row['Low'] <= stop_niva:
            # Selg til 'Low' som spesifisert (konservativt)
            gevinst_pct = (row['Low'] - kjops_pris) / kjops_pris
            return gevinst_pct, dato # Returner gevinst og salgsdato

    # Hvis vi aldri ble stoppet ut, beregn gevinst ved sluttdato
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
            # Selv om strategien skal testes for alle dager, er "Optimalt kjøpspunkt"
            # ofte definert som den dagen kursen var på sitt absolutte bunnpunkt.
            min_row = df.loc[df['Low'].idxmin()]
            optimal_dato = min_row.name
            optimal_pris = min_row['Low']
            
            st.subheader(f"🔍 Resultater for {ticker}")
            
            # --- ANALYSE 1: OPTIMALT KJØPSPUNKT (BUNNEN) ---
            # Vi tester alle stop-loss nivåer for akkurat denne dagen
            best_sl_pct = 0
            best_gevinst = -100.0
            results_optimal = []
            
            # Progress bar for loopen
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

            # Vis resultater
            col1, col2, col3 = st.columns(3)
            col1.metric("Optimal Kjøpsdato", f"{optimal_dato.strftime('%d.%m.%Y')}")
            col1.metric("Kjøpspris (Low)", f"{optimal_pris:.2f} kr")
            col2.metric("Beste Stop Loss", f"{best_sl_pct} %")
            col2.metric("Salgsdato", f"{best_salgsdato.strftime('%d.%m.%Y') if best_salgsdato else 'Holdes fremdeles'}")
            col3.metric("Maks Gevinst", f"{best_gevinst*100:.2f} %", delta_color="normal")

            # Tegn graf for det optimale handlingsforløpet
            st.markdown("### Visuell utvikling av den optimale handelen")
            
            # Lag data for plotting
            plot_data = df[df.index >= optimal_dato].copy()
            # Beregn stop-loss linjen for visualisering
            hoyeste = optimal_pris
            sl_line = []
            for dato, row in plot_data.iterrows():
                if row['High'] > hoyeste: hoyeste = row['High']
                sl_verdi = hoyeste * (1 - (best_sl_pct/100))
                sl_line.append(sl_verdi)
            
            plot_data['Stop Loss Linje'] = sl_line
            
            # Kutt grafen ved salgsdato for ryddighet
            if best_salgsdato:
                plot_data = plot_data[plot_data.index <= best_salgsdato]

            st.line_chart(plot_data[['Close', 'Stop Loss Linje']])
            
            # --- ANALYSE 2: GENERELT (HVA FUNKER I SNITT?) ---
            with st.expander("Se statistikk for ALLE stop-loss nivåer (Tabell)"):
                res_df = pd.DataFrame(results_optimal)
                st.dataframe(res_df.style.highlight_max(axis=0, color='lightgreen'))
                
                st.line_chart(res_df.set_index('SL %')['Gevinst %'])
                st.caption("Grafen viser hvordan gevinsten endrer seg basert på hvilken Stop Loss % du velger.")

else:
    st.info("Velg innstillinger i menyen til venstre og trykk 'Kjør Analyse'")
