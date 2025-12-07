import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# --- TITTEL OG OPPSETT ---
st.set_page_config(page_title="Stop-Loss Analyse", layout="centered")
st.title("📈 Aksje-analyse: Optimal Stop-Loss")
st.write("Last opp historiske data (Excel eller CSV) for å finne den optimale stop-loss prosenten.")

# --- 1. LAST OPP FIL ---
uploaded_file = st.file_uploader("Last opp fil her", type=['xlsx', 'csv'])

if uploaded_file is not None:
    st.success("Fil lastet opp! Analyserer...")

    # --- INNLESING AV DATA ---
    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, header=None)
        else:
            df = pd.read_csv(uploaded_file, header=None, on_bad_lines='skip')
        
        # Vi antar strukturen: Dato(1), Close(2), High(4), Low(5)
        # Sjekk at vi har nok kolonner
        if df.shape[1] < 6:
            st.error("Filen har feil format. Sjekk at det er en Nordnet/Yahoo eksport.")
        else:
            data = pd.DataFrame()
            data['Date'] = pd.to_datetime(df[1], errors='coerce')
            data['Close'] = pd.to_numeric(df[2], errors='coerce')
            data['High'] = pd.to_numeric(df[4], errors='coerce')
            data['Low'] = pd.to_numeric(df[5], errors='coerce')
            
            data = data.dropna().sort_values('Date').reset_index(drop=True)
            
            st.write(f"✅ Fant **{len(data)}** handelsdager fra {data['Date'].iloc[0].date()} til {data['Date'].iloc[-1].date()}.")
            
            # --- 2. ANALYSE-LOGIKK ---
            def run_simulation(trade_data, stop_loss_pct):
                entry_price = trade_data.iloc[0]['Close']
                highest_high = trade_data.iloc[0]['High']
                
                for i in range(1, len(trade_data)):
                    current_high = trade_data.iloc[i]['High']
                    current_low = trade_data.iloc[i]['Low']
                    
                    if current_high > highest_high:
                        highest_high = current_high
                    
                    stop_price = highest_high * (1 - stop_loss_pct)
                    
                    if current_low <= stop_price:
                        return (stop_price - entry_price) / entry_price
                        
                return (trade_data.iloc[-1]['Close'] - entry_price) / entry_price

            # Progress bar for visual effekt
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            stop_loss_range = np.arange(0.05, 0.51, 0.01)
            results = []
            
            # Kjører simulering
            step_size = 20 # Kjøp hver 20. dag
            entry_points = range(0, len(data) - step_size, step_size)
            
            total_iterations = len(stop_loss_range)
            
            for idx, sl in enumerate(stop_loss_range):
                # Oppdater progress bar
                progress = (idx + 1) / total_iterations
                progress_bar.progress(progress)
                status_text.text(f"Tester Stop-Loss: {sl:.0%}")
                
                returns = []
                for start_idx in entry_points:
                    subset = data.iloc[start_idx:].reset_index(drop=True)
                    if len(subset) > 5:
                        r = run_simulation(subset, sl)
                        returns.append(r)
                
                if returns:
                    avg_ret = np.mean(returns)
                    win_rate = np.mean([1 if x > 0 else 0 for x in returns])
                    results.append({'StopLoss': sl, 'AvgReturn': avg_ret, 'WinRate': win_rate})
            
            status_text.text("Ferdig!")
            res_df = pd.DataFrame(results)

            # --- 3. VIS RESULTATER ---
            if not res_df.empty:
                best_sl = res_df.loc[res_df['AvgReturn'].idxmax()]
                
                st.subheader("Resultat")
                st.metric(label="Anbefalt Stop-Loss", value=f"{best_sl['StopLoss']:.0%}")
                st.metric(label="Gjennomsnittlig Avkastning", value=f"{best_sl['AvgReturn']:.1%}")
                
                # Graf
                fig, ax = plt.subplots(figsize=(10, 5))
                ax.plot(res_df['StopLoss']*100, res_df['AvgReturn']*100, color='blue', linewidth=2)
                ax.axvline(best_sl['StopLoss']*100, color='green', linestyle='--', label=f"Best: {best_sl['StopLoss']:.0%}")
                ax.set_title("Resultat av Backtest")
                ax.set_xlabel("Stop-Loss (%)")
                ax.set_ylabel("Avkastning (%)")
                ax.grid(True, alpha=0.3)
                ax.legend()
                
                st.pyplot(fig)
                
                # Vis tabell med data hvis brukeren vil se detaljer
                with st.expander("Se detaljerte data"):
                    st.dataframe(res_df)
                    
    except Exception as e:
        st.error(f"Noe gikk galt: {e}")
