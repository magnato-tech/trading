import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- KONFIGURASJON ---
st.set_page_config(page_title="Stop Loss Optimalisering", layout="wide")

st.title("📈 Aksjeanalyse: Optimal Glidende Stop Loss")
st.markdown("""
Denne appen simulerer handlestrategien din på historiske data for å finne:
1. **Optimalt kjøpspunkt:** Hvilken dag og pris ga høyest gevinst?
2. **Beste stop-loss:** Hvilken prosent fungerte best?
""")

# --- SIDEBAR (INPUT) ---
with st.sidebar:
    st.header("Innstillinger")
    ticker = st.text_input("Ticker", value="EQNR.OL")
    
    default_start = pd.to_datetime("today") - pd.DateOffset(years=1)
    start_date = st.date_input("Startdato", value=default_start)
    end_date = st.date_input("Sluttdato", value=pd.to_datetime("today"))
    
    st.markdown("---")
    # Slider returnerer en tuple (min, max)
    stop_loss_range = st.slider("Stop Loss fra/til %", 1, 90, (3, 50))
    
    kjør_knapp = st.button("Kjør Analyse")

# --- FUNKSJONER ---

def hent_data(ticker, start, end):
    try:
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None

def simuler_handel(df, kjops_dato, kjops_pris, stop_loss_pct):
    # Vi ser kun på data ETTER kjøpsdatoen
    periode_data = df[df.index > kjops_dato].copy()
    
    if periode_data.empty:
        return 0.0, None 

    hoyeste_pris = kjops_pris
    
    for dato, row in periode_data.iterrows():
        # Oppdater høyeste pris (Trailing logikk)
        if row['High'] > hoyeste_pris:
            hoyeste_pris = row['High']
            
        # Beregn stop nivå
        stop_niva = hoyeste_pris * (1 - stop_loss_pct)
        
        # Sjekk om vi blir stoppet ut (Low treffer stop loss)
        if row['Low'] <= stop_niva:
            salgspris = stop_niva 
            # Deler opp regnestykket for å unngå linjebrudd-feil
            gevinst = salgspris - kjops_pris
            gevinst_pct = gevinst / kjops_pris
            return gevinst_pct, dato

    # Hvis vi aldri ble stoppet ut
    siste_pris = periode_data.iloc[-1]['Close']
    gevinst = siste_pris - kjops_pris
    gevinst_pct = gevinst / kjops_pris
    return gevinst_pct, periode_data.index[-1]

# --- HOVEDLOGIKK ---

if kjør_knapp:
    with st.spinner('Kjører simulering...'):
        df = hent_data(ticker, start_date, end_date)
        
        if df is None:
            st.error("Fant ingen data. Sjekk ticker.")
        else:
            # 1. IDENTIFISER OPTIMALT KJØPSPUNKT (Lavest i perioden)
            min_row = df.loc[df['Low'].idxmin()]
            optimal_dato = min_row.name
            optimal_pris = min_row['Low']
            
            st.subheader(f"Resultater for {ticker}")
            st.write(f"Bunn: {optimal_dato.strftime('%d.%m.%Y')} til {optimal_pris:.2f}")
            
            best_gevinst = -100.0
            best_sl = 0
            best_salgsdato = None
            results = []
            
            my_bar = st.progress(0)
            r_start, r_end = stop_loss_range
            range_sl = range(r_start, r_end + 1)
            
            for i, sl in enumerate(range_sl):
                sl_desimal = sl / 100.0
                g, s_dato = simuler_handel(df, optimal_dato, optimal_pris, sl_desimal)
                results.append({'SL %': sl, 'Gevinst %': g*100})
                
                if g > best_gevinst:
                    best_gevinst = g
                    best_sl = sl
                    best_salgsdato = s_dato
                
                my_bar.progress((i + 1) / len(range_sl))
            
            my_bar.empty()

            # Vis nøkkeltall
            c1, c2, c3 = st.columns(3)
            c1.metric("Kjøp (Bunn)", f"{optimal_pris:.2f}")
            c2.metric("Beste Stop Loss", f"{best_sl} %")
            c3.metric("Maks Gevinst", f"{best_gevinst*100:.2f} %")

            # Tegn graf
            plot_data = df[df.index >= optimal_dato].copy()
            hoyeste = optimal_pris
            sl_line = []
            
            for dato, row in plot_data.iterrows():
                if row['High'] > hoyeste: hoyeste = row['High']
                sl_line.append(hoyeste * (1 - (best_sl/100.0)))
            
            plot_data['Stop Loss'] = sl_line
            
            if best_salgsdato:
                plot_data = plot_data[plot_data.index <= best_salgsdato]

            st.line_chart(plot_data[['Close', 'Stop Loss']])
            
            with st.expander("Se tabell"):
                st.dataframe(pd.DataFrame(results).style.highlight_max(axis=0))

else:
    st.info("Trykk 'Kjør Analyse' for å starte.")
