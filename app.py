import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import altair as alt
import requests  # Trengs for å søke etter ticker

# --- KONFIGURASJON ---
st.set_page_config(page_title="Stop Loss Optimalisering", layout="wide")

st.title("📈 Aksjeanalyse: Stop Loss Optimalisering")
st.markdown(
    "Her analyseres daglige bevegelser (OHLC). Du kan søke med **Selskapsnavn** eller **Ticker**."
)

# --- FUNKSJONER ---


@st.cache_data(ttl=60 * 60 * 6)  # cache 6 timer for å redusere kall mot Yahoo
def finn_ticker_fra_navn(navn_eller_ticker: str) -> str | None:
    """
    Søker etter en ticker basert på navn ved hjelp av Yahoo Finance sitt søk-endepunkt.

    Heuristikk:
      - Hvis input ser ut som en ticker (f.eks. AAPL, EQNR.OL), returner direkte.
      - Ellers: slå opp i Yahoo search og returner beste match.
    """
    query = (navn_eller_ticker or "").strip()
    if not query:
        return None

    # Heuristikk: ser det ut som en ticker?
    looks_like_ticker = (
        (len(query) <= 10)
        and any(ch.isalpha() for ch in query)
        and (" " not in query)
    )
    if looks_like_ticker:
        return query.upper()

    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        params = {"q": query, "quotes_count": 5}

        res = requests.get(url=url, params=params, headers={"User-Agent": user_agent}, timeout=7)
        res.raise_for_status()
        data = res.json()

        quotes = (data or {}).get("quotes", [])
        if not quotes:
            return None

        # Velg første "fornuftige" symbol (prioriter aksjer/ETF)
        for q in quotes:
            sym = q.get("symbol")
            qtype = (q.get("quoteType") or "").upper()
            if sym and qtype in {"EQUITY", "ETF"}:
                return sym

        # fallback: bare ta første symbol
        sym0 = quotes[0].get("symbol")
        return sym0

    except requests.exceptions.RequestException as e:
        st.warning(f"Klarte ikke å søke etter ticker online: {e}")
        return None


@st.cache_data(ttl=60 * 60 * 6)
def hent_data(ticker: str, start, end) -> pd.DataFrame | None:
    """
    Henter daglige data fra Yahoo Finance via yfinance.
    Returnerer None hvis ingen data.
    """
    try:
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df is None or df.empty:
            return None
        # Noen ganger kommer MultiIndex-kolonner
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


@st.cache_data(ttl=60 * 60 * 24)
def hent_valuta(ticker: str) -> str:
    """
    Forsøker å hente valutakode for tickeren. Returnerer tom streng hvis ukjent.
    NB: yfinance kan være ustabil på dette feltet, så vi holder det defensivt.
    """
    try:
        t = yf.Ticker(ticker)
        fi = getattr(t, "fast_info", None)
        if fi and "currency" in fi and fi["currency"]:
            return str(fi["currency"])
        info = getattr(t, "info", None)
        if info and isinstance(info, dict) and info.get("currency"):
            return str(info["currency"])
    except Exception:
        pass
    return ""


def velg_kjopspunkt(df: pd.DataFrame, mode: str):
    """
    Velger kjøpsdato og pris basert på valgt modus.
    Returnerer (dato, pris, label)
    """
    if df is None or df.empty:
        return None, None, ""

    if mode == "Demo: Beste historiske kjøp (laveste Low)":
        min_row = df.loc[df["Low"].idxmin()]
        return min_row.name, float(min_row["Low"]), "Laveste Low i perioden (demo)"

    if mode == "Kjøp første dag (Close)":
        first = df.iloc[0]
        return df.index[0], float(first["Close"]), "Første dag (Close)"

    # Kjøp ved første Close over SMA50
    df2 = df.copy()
    df2["SMA50"] = df2["Close"].rolling(window=50).mean()
    cross = df2[(df2["SMA50"].notna()) & (df2["Close"] > df2["SMA50"])]
    if not cross.empty:
        d = cross.index[0]
        p = float(df2.loc[d, "Close"])
        return d, p, "Første Close over SMA50"

    # fallback
    first = df.iloc[0]
    return df.index[0], float(first["Close"]), "Fallback: første dag (Close)"


def simuler_handel(df: pd.DataFrame, kjops_dato, kjops_pris: float, stop_loss_pct: float):
    """
    Simulerer én handel med trailing stop-loss (basert på høyeste pris etter kjøp).
    stop_loss_pct er andel (0.10 = 10%).
    Returnerer (gevinst_andel, salgsdato, salgspris).
    """
    periode_data = df[df.index > kjops_dato].copy()
    if periode_data.empty:
        return 0.0, None, 0.0

    hoyeste_pris = kjops_pris

    for dato, row in periode_data.iterrows():
        if pd.isna(row.get("High")) or pd.isna(row.get("Low")):
            continue

        if row["High"] > hoyeste_pris:
            hoyeste_pris = row["High"]

        stop_niva = hoyeste_pris * (1 - stop_loss_pct)

        if row["Low"] <= stop_niva:
            salgspris = float(stop_niva)  # antakelse: fylles på stop-nivå
            gevinst = salgspris - kjops_pris
            gevinst_pct = gevinst / kjops_pris
            return float(gevinst_pct), dato, salgspris

    siste_pris = float(periode_data.iloc[-1]["Close"])
    gevinst = siste_pris - kjops_pris
    gevinst_pct = gevinst / kjops_pris
    return float(gevinst_pct), periode_data.index[-1], siste_pris


# --- SIDEBAR (INPUT) ---
with st.sidebar:
    st.header("Innstillinger")

    input_aksje = st.text_input("Selskapsnavn eller Ticker", value="Equinor")

    default_start = pd.to_datetime("today") - pd.DateOffset(years=2)
    start_date = st.date_input("Startdato", value=default_start)
    end_date = st.date_input("Sluttdato", value=pd.to_datetime("today"))

    st.markdown("---")
    stop_loss_range = st.slider("Test Stop Loss fra/til %", 1, 90, (3, 50))

    st.markdown("---")
    kjop_mode = st.selectbox(
        "Kjøpsregel",
        [
            "Demo: Beste historiske kjøp (laveste Low)",
            "Kjøp første dag (Close)",
            "Kjøp ved første Close over SMA50",
        ],
        index=0,
    )

    kjør_knapp = st.button("Kjør Analyse")

# --- HOVEDLOGIKK ---

if kjør_knapp:
    # 1. KONVERTER NAVN TIL TICKER
    with st.spinner("Søker etter ticker..."):
        funnet_ticker = finn_ticker_fra_navn(input_aksje)

    if funnet_ticker:
        st.info(f"Fant Ticker: **{funnet_ticker}**")

        with st.spinner(f"Henter daglige kurser for {funnet_ticker} og simulerer..."):
            df = hent_data(funnet_ticker, start_date, end_date)

        if df is None:
            st.error(
                f"Fant ingen historisk data for ticker **{funnet_ticker}**. "
                f"Sjekk om ticker er korrekt og at perioden har data."
            )
        else:
            currency = hent_valuta(funnet_ticker)
            currency_label = f" ({currency})" if currency else ""

            # 2. VELG KJØPSPUNKT (avhengig av modus)
            optimal_dato, optimal_pris, kjop_label = velg_kjopspunkt(df, kjop_mode)
            if optimal_dato is None:
                st.error("Klarte ikke å velge kjøpspunkt (mangler data).")
                st.stop()

            best_gevinst = -100.0
            best_sl = 0
            best_salgsdato = None
            best_salgspris = 0.0
            results = []

            # --- SIMULERINGSLØKKE ---
            my_bar = st.progress(0)
            r_start, r_end = stop_loss_range
            range_sl = range(r_start, r_end + 1)

            for i, sl in enumerate(range_sl):
                sl_desimal = sl / 100.0
                g, s_dato, s_pris = simuler_handel(df, optimal_dato, optimal_pris, sl_desimal)
                results.append({"Stop Loss %": sl, "Gevinst %": g * 100})

                if g > best_gevinst:
                    best_gevinst = g
                    best_sl = sl
                    best_salgsdato = s_dato
                    best_salgspris = s_pris

                my_bar.progress((i + 1) / len(range_sl))

            my_bar.empty()

            # --- SEKSJON 1: KPI-er ---
            st.markdown(f"### 📊 Resultater for {funnet_ticker}")
            st.caption(f"Kjøpsregel: {kjop_label}")

            dato_kjop = optimal_dato.strftime("%d.%m.%Y")

            if best_salgsdato == df.index[-1]:
                dato_salg = f"{best_salgsdato.strftime('%d.%m.%Y')} (Siste dag i datasettet)"
            else:
                dato_salg = f"{best_salgsdato.strftime('%d.%m.%Y')} (Stop Loss utløst)"

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Kjøpspris", f"{optimal_pris:.2f}{currency_label}")
                st.caption(f"📅 {dato_kjop}")

            with col2:
                st.metric("Salgspris", f"{best_salgspris:.2f}{currency_label}")
                st.caption(f"📅 {dato_salg}")

            with col3:
                farge = "normal" if best_gevinst > 0 else "inverse"
                st.metric("Total Gevinst", f"{best_gevinst * 100:.2f} %", delta_color=farge)

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

                if pd.isna(row.get("High")):
                    sl_line.append(np.nan)
                    continue

                if row["High"] > hoyeste:
                    hoyeste = row["High"]

                stop_loss_value = hoyeste * (1 - (best_sl / 100.0))
                sl_line.append(stop_loss_value)

            plot_data["Stop Loss Linje"] = sl_line

            res_df = pd.DataFrame(results)

            c_graf1, c_graf2 = st.columns(2)

            with c_graf1:
                st.subheader("1. Kursutvikling (Hele perioden)")

                base = alt.Chart(plot_data.reset_index()).encode(x="Date:T")
                line_close = base.mark_line(color="#1f77b4").encode(
                    y=alt.Y("Close:Q", title=f"Kurs{currency_label}")
                )
                line_sl = base.mark_line(color="red", strokeDash=[5, 5]).encode(
                    y="Stop Loss Linje:Q"
                )

                buy_df = pd.DataFrame({"Date": [optimal_dato], "Price": [optimal_pris]})
                buy_point = (
                    alt.Chart(buy_df)
                    .mark_point(color="green", size=150, filled=True, shape="triangle-up")
                    .encode(x="Date:T", y="Price:Q")
                )

                exit_df = pd.DataFrame({"Date": [best_salgsdato], "Price": [best_salgspris]})
                exit_point = (
                    alt.Chart(exit_df)
                    .mark_point(color="orange", size=150, filled=True)
                    .encode(x="Date:T", y="Price:Q")
                )

                st.altair_chart(line_close + line_sl + buy_point + exit_point, use_container_width=True)
                st.caption(
                    "Blå linje: Sluttkurs. Rød stiplet: Stop Loss. "
                    "Grønn trekant: Kjøpspunkt. Oransje prikk: Salgs-/Exitpunkt."
                )

            with c_graf2:
                st.subheader("2. Hvilken % fungerer best?")
                chart = (
                    alt.Chart(res_df)
                    .mark_line()
                    .encode(
                        x=alt.X("Stop Loss %", title="Stop Loss Prosent"),
                        y=alt.Y("Gevinst %", title="Gevinst (%)"),
                        tooltip=["Stop Loss %", "Gevinst %"],
                    )
                    .interactive()
                )

                best_point = pd.DataFrame({"Stop Loss %": [best_sl], "Gevinst %": [best_gevinst * 100]})
                point = alt.Chart(best_point).mark_circle(color="green", size=100).encode(
                    x="Stop Loss %", y="Gevinst %"
                )

                st.altair_chart(chart + point, use_container_width=True)

            # --- SEKSJON 3: TABELL ---
            with st.expander("Se detaljert tabell"):
                st.dataframe(
                    res_df.style.highlight_max(axis=0, subset=["Gevinst %"], color="lightgreen"),
                    use_container_width=True,
                )

    else:
        st.error(
            f"Finner ingen gyldig ticker for '{input_aksje}'. "
            f"Prøv en eksakt ticker (f.eks. AAPL eller EQNR.OL) eller et mer spesifikt firmanavn."
        )

else:
    st.info("Trykk 'Kjør Analyse' for å starte.")
