import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import altair as alt
import requests # Trengs for å søke etter ticker

# --- KONFIGURASJON ---
st.set_page_config(page_title="Stop Loss Optimalisering", layout="wide")

st.title("📈 Aksjeanalyse: Stop Loss Optimalisering")
st.markdown("Her analyseres daglige bevegelser (OHLC). Du kan søke med **Selskapsnavn** eller **Ticker**.")

# --- FUNKSJONER ---

def finn_ticker_fra_navn(navn_eller_ticker):
    """
    Søker etter en Ticker basert på navn ved hjelp av Yahoo Finance's søke-endepunkt.
    Hvis input ser ut som en ticker (f.eks. store bokstaver og en børs-suffiks),
    returneres den direkte.
    """
    # Sjekk om input er en ticker (f.eks. "EQNR.OL")
    if navn_eller_ticker.strip().isupper() and ('.' in navn_eller_ticker or len(navn_eller_ticker) <= 5):
        return navn_eller_ticker.upper()
    
    # Prøv å søke etter ticker basert på navn
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" # Nødvendig for å unngå blokkering
        params = {"q": navn_eller_ticker, "quotes_count": 1, "country": "United States"}
        
        # Setter timeout for å unngå at appen henger
        res = requests.get(url=url, params=params, headers={'User-Agent': user_agent}, timeout=5)
        res.raise_for_status() # Kast feil for dårlige statuser (4xx eller 5xx)
        data = res.json()

        if data and 'quotes' in data and len(data['quotes']) > 0:
            # Finner den første og beste matchingen
            beste_match = data['quotes'][0]
            
            # Vi returnerer ticker og exchange (f.eks. for Oslo Børs) for å sikre at yfinance finner den
            ticker = beste_match.get('symbol')
            exchange = beste_match.get('exchange')
            
            if exchange == 'OSL':
                return f"{ticker}.OL" # Spesifikt for Oslo Børs/Euronext Oslo
            
            return ticker
        
    except requests.exceptions.RequestException as e:
        st.warning(f"Klarte ikke å søke etter ticker online: {e}")
        return None # Returner None ved feil

    return None # Returner None hvis ingen match ble funnet

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

# (Resten av funksjonene er uendret...)

def simuler_handel(df, kjops_dato, kjops_pris, stop_loss_pct):
    periode_data = df[df.index > kjops_dato].copy()
    if periode_data.empty:
        return 0.0, None, 0.0

    hoyeste_pris = kjops_pris
    
    for dato, row in periode_data.iterrows():
        if row['High'] > hoyeste_pris:
            hoyeste_pris = row['High']
            
        stop_niva = hoyeste_pris * (1 - stop_loss_pct)
        
        if row['Low'] <= stop_niva:
            salgspris = stop_niva 
            gevinst = salgspris - kjops_pris
            gevinst_pct = gevinst / kjops_pris
            return gevinst_pct, dato, salgspris

    siste_pris = periode_data.iloc[-1]['Close']
    gevinst = siste_pris - kjops_pris
    gevinst_pct = gevinst / kjops_pris
    return gevinst_pct, periode_data.index[-1], siste_pris

# --- SIDEBAR (INPUT - MODIFISERT) ---
with st.sidebar:
    st.header("Innstillinger")
    
    # Endret Ticker input til Navn/Ticker
    input_aksje = st.text_input("Selskapsnavn eller Ticker", value="Equinor")
    
    default_start = pd.to_datetime("today") - pd.DateOffset(years=2)
    start_date = st.date_input("Startdato", value=default_start)
    end_date = st.date_input("Sluttdato", value=pd.to_datetime("today"))
    
    st.markdown("---")
    stop_loss_range = st.slider("Test Stop Loss fra/til %", 1, 90, (3, 50))
    
    kjør_knapp = st.button("Kjør Analyse")

# --- HOVEDLOGIKK ---

if kjør_knapp:
    # 1. KONVERTER NAVN TIL TICKER
    with st.spinner('Søker etter ticker...'):
        # Bruker funksjonen til å finne ticker
        funnet_ticker = finn_ticker_fra_navn(input_aksje)

    if funnet_ticker:
        st.info(f"Fant Ticker: **{funnet_ticker}**")
        
        with st.spinner(f'Henter daglige kurser for {funnet_ticker} og simulerer...'):
            df = hent_data(funnet_ticker, start_date, end_date)
            
            if df is None:
                st.error(f"Fant ingen historisk data for ticker **{funnet_ticker}**. Sjekk om ticker er korrekt.")
            else:
                # (Resten av logikken er den samme som før)
                
                # 1. IDENTIFISER OPTIMALT KJØPSPUNKT
                min_row = df.loc[df['Low'].idxmin()]
                optimal_dato = min_row.name
                optimal_pris = min_row['Low']
                
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

                # --- SEKSJON 1: KPI-er ---
                st.markdown(f"### 📊 Resultater for {funnet_ticker}")
                
                # Formaterer datoene
                dato_kjop = optimal_dato.strftime('%d.%m.%Y')
                
                if best_salgsdato == df.index[-1]:
                    dato_salg = f"{best_salgsdato.strftime('%d.%m.%Y')} (I dag)"
                else:
                    dato_salg = f"{best_salgsdato.strftime('%d.%m.%Y')} (Stop Loss utløst)"

                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Kjøpspris", f"{optimal_pris:.2f} kr")
                    st.caption(f"📅 {dato_kjop}")
                
                with col2:
                    st.metric("Salgspris", f"{best_salgspris:.2f} kr")
                    st.caption(f"📅 {dato_salg}")

                with col3:
                    farge = "normal" if best_gevinst > 0 else "inverse"
                    st.metric("Total Gevinst", f"{best_gevinst*100:.2f} %", delta_color=farge)
                
                with col4:
                    st.metric("Optimal Stop Loss", f"{best_sl} %")

                st.markdown("---")

                # --- SEKSJON 2: GRAFER ---
                plot_data = df.copy() 
                hoyeste = optimal_pris
                sl_line = []
                
                for dato in plot_data.index:
                    if dato < optimal_dato:
                        sl_line.append(np.nan)
                        continue
                    
                    row = plot_data.loc[dato]
                    
                    if row['High'] > hoyeste: 
                        hoyeste = row['High']
                        
                    stop_loss_value = hoyeste * (1 - (best_sl/100.0))
                    sl_line.append(stop_loss_value)
                
                plot_data['Stop Loss Linje'] = sl_line
                
                res_df = pd.DataFrame(results)

                c_graf1, c_graf2 = st.columns(2)
                
                with c_graf1:
                    st.subheader("1. Kursutvikling (Hele perioden)")
                    
                    base = alt.Chart(plot_data.reset_index()).encode(x='Date:T')
                    line_close = base.mark_line(color='#1f77b4').encode(y=alt.Y('Close:Q', title='Kurs (kr)'))
                    line_sl = base.mark_line(color='red', strokeDash=[5,5]).encode(y='Stop Loss Linje:Q')
                    
                    buy_df = pd.DataFrame({'Date': [optimal_dato], 'Price': [optimal_pris]})
                    buy_point = alt.Chart(buy_df).mark_point(color='green', size=150, filled=True, shape='triangle-up').encode(
                        x='Date:T',
                        y=alt.Y('Price:Q')
                    )
                    
                    exit_df = pd.DataFrame({'Date': [best_salgsdato], 'Price': [best_salgspris]})
                    exit_point = alt.Chart(exit_df).mark_point(color='orange', size=150, filled=True).encode(
                        x='Date:T',
                        y='Price:Q'
                    )

                    st.altair_chart(line_close + line_sl + buy_point + exit_point, use_container_width=True)
                    st.caption("Blå linje: Sluttkurs. Rød stiplet: Stop Loss. Grønn trekant: Kjøpspunkt. Oransje prikk: Salgs-/Exitpunkt.")
                
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
        st.error(f"Finner ingen gyldig ticker for '{input_aksje}'. Prøv å bruke en eksakt ticker (f.eks. AAPL) eller et mer spesifikt firmanavn.")

else:
    st.info("Trykk 'Kjør Analyse' for å starte.")