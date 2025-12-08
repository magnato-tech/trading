import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import altair as alt

# --- KONFIGURASJON ---
st.set_page_config(page_title="Stop Loss Optimalisering", layout="wide")

st.title("📈 Aksjeanalyse: Stop Loss Optimalisering")
st.markdown("Her analyseres daglige bevegelser (OHLC). Simuleringen sjekker om **Dagens Laveste (Low)** treffer din Stop Loss.")

# --- SIDEBAR (INPUT) ---
with st.sidebar:
    st.header("Innstillinger")
    ticker = st.text_input("Ticker", value="EQNR.OL")
    
    # Standard: 2 år tilbake i tid
    default_start = pd.to_datetime("today") - pd.DateOffset(years=2)
    start_date = st.date_input("Startdato", value=default_start)
    end_date = st.date_input("Sluttdato", value=pd.to_datetime("today"))
    
    st.markdown("---")
    stop_loss_range = st.slider("Test Stop Loss fra/til %", 1, 90, (3, 50))
    
    kjør_knapp = st.button("Kjør Analyse")

# --- FUNKSJONER ---

def hent_data(ticker, start, end):
    try:
        # Henter daglige data (interval="1d" er standard)
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
        return 0.0, None, 0.0

    hoyeste_pris = kjops_pris
    
    for dato, row in periode_data.iterrows():
        # 1. Oppdater høyeste pris (Trailing logikk)
        if row['High'] > hoyeste_pris:
            hoyeste_pris = row['High']
            
        # 2. Beregn stop nivå basert på høyeste
        stop_niva = hoyeste_pris * (1 - stop_loss_pct)
        
        # 3. Sjekk om vi blir stoppet ut (Low treffer stop loss)
        # Dette fanger opp volatilitet i løpet av dagen
        if row['Low'] <= stop_niva:
            salgspris = stop_niva 
            gevinst = salgspris - kjops_pris
            gevinst_pct = gevinst / kjops_pris
            return gevinst_pct, dato, salgspris

    # Hvis vi aldri ble stoppet ut (holder fremdeles ved sluttdato)
    siste_pris = periode_data.iloc[-1]['Close']
    gevinst = siste_pris - kjops_pris
    gevinst_pct = gevinst / kjops_pris
    return gevinst_pct, periode_data.index[-1], siste_pris

# --- HOVEDLOGIKK ---

if kjør_knapp:
    with st.spinner('Henter daglige kurser og simulerer...'):
        df = hent_data(ticker, start_date, end_date)
        
        if df is None:
            st.error("Fant ingen data. Sjekk ticker.")
        else:
            # 1. IDENTIFISER OPTIMALT KJØPSPUNKT (Lavest i perioden)
            min_row = df.loc[df['Low'].idxmin()]
            optimal_dato = min_row.name
            optimal_pris = min_row['Low']
            
            # Variabler for å lagre "Beste" resultat
            best_gevinst = -100.0
            best_sl = 0
            best_salgsdato = None
            best_salgspris = 0
            results = []
            
            # --- SIMULERINGSLØKKE ---
            my_bar = st.progress(0)
            r_start, r_end = stop_loss_range
            range_sl = range(r_start, r_end + 1)
            
            for i, sl in enumerate(range_sl):
                sl_desimal = sl / 100.0
                g, s_dato, s_pris = simuler_handel(df, optimal_dato, optimal_pris, sl_desimal)
                results.append({'Stop Loss %': sl, 'Gevinst %': g*100})
                
                if g > best_gevinst:
                    best_gevinst = g
                    best_sl = sl
                    best_salgsdato = s_dato
                    best_salgspris = s_pris
                
                my_bar.progress((i + 1) / len(range_sl))
            
            my_bar.empty()

            # --- SEKSJON 1: KPI-er (OPPDATERT MED DATOER) ---
            st.markdown("### 📊 Resultater")
            
            # Formaterer datoene til norsk format (Dag.Måned.År)
            dato_kjop = optimal_dato.strftime('%d.%m.%Y')
            
            if best_salgsdato == df.index[-1]:
                dato_salg = f"{best_salgsdato.strftime('%d.%m.%Y')} (I dag)"
            else:
                dato_salg = f"{best_salgsdato.strftime('%d.%m.%Y')} (Stop Loss)"

            # Vi bruker kolonner for å vise dette ryddig
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Kjøpspris", f"{optimal_pris:.2f} kr")
                st.caption(f"📅 {dato_kjop}") # Dato vises tydelig under prisen
            
            with col2:
                st.metric("Salgspris", f"{best_salgspris:.2f} kr")
                st.caption(f"📅 {dato_salg}") # Dato vises tydelig under prisen

            with col3:
                farge = "normal" if best_gevinst > 0 else "inverse"
                st.metric("Total Gevinst", f"{best_gevinst*100:.2f} %", delta_color=farge)
            
            with col4:
                st.metric("Optimal Stop Loss", f"{best_sl} %")

            st.markdown("---")

            # --- SEKSJON 2: GRAFER ---
            plot_data = df[df.index >= optimal_dato].copy()
            hoyeste = optimal_pris
            sl_line = []
            for dato, row in plot_data.iterrows():
                if row['High'] > hoyeste: hoyeste = row['High']
                sl_line.append(hoyeste * (1 - (best_sl/100.0)))
            plot_data['Stop Loss Linje'] = sl_line
            
            if best_salgsdato:
                plot_data = plot_data[plot_data.index <= best_salgsdato]

            res_df = pd.DataFrame(results)

            c_graf1, c_graf2 = st.columns(2)
            
            with c_graf1:
                st.subheader("1. Kursutvikling")
                st.line_chart(plot_data[['Close', 'Stop Loss Linje']])
                st.caption("Blå linje er kursen. Rød linje er din Stop Loss.")
            
            with c_graf2:
                st.subheader("2. Hvilken % fungerer best?")
                chart = alt.Chart(res_df).mark_line().encode(
                    x=alt.X('Stop Loss %', title='Stop Loss Prosent'),
                    y=alt.Y('Gevinst %', title='Gevinst (%)'),
                    tooltip=['Stop Loss %', 'Gevinst %']
                ).interactive()
                
                best_point = pd.DataFrame({'Stop Loss %': [best_sl], 'Gevinst %': [best_gevinst*100]})
                point = alt.Chart(best_point).mark_circle(color='green', size=100).encode(x='Stop Loss %', y='Gevinst %')
                
                st.altair_chart(chart + point, use_container_width=True)

            # --- SEKSJON 3: TABELL ---
            with st.expander("Se detaljert tabell"):
                st.dataframe(res_df.style.highlight_max(axis=0, subset=['Gevinst %'], color='lightgreen'), use_container_width=True)

else:
    st.info("Trykk 'Kjør Analyse' for å starte.")