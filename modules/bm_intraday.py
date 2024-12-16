import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from entsoe import EntsoePandasClient
import os
from dotenv import load_dotenv
from data_fetching.entsoe_data import fetch_intraday_imbalance_data  # Importing the function to fetch data
from data_fetching.entsoe_data import wind_solar_generation, actual_generation_source       # Assuming this function is also available
# Importing the wind data
from data_fetching.entsoe_newapi_data import fetch_process_wind_notified, fetch_process_wind_actual_production, preprocess_volue_forecast, fetch_volue_wind_data, combine_wind_production_data, fetching_Cogealac_data_15min, predicting_wind_production_15min, add_solcast_forecast_to_wind_dataframe

#============================================================================Rendering the Intraday Balancing Market Page================================================================

def render_balancing_market_intraday_page():
    st.title("Intraday Balancing Market Dashboard")
    st.write("This dashboard provides a comprehensive overview of intraday balancing, "
             "allowing traders to quickly analyze both the current market conditions and the influencing factors.")

    # CSS code to collapse the sidebar
    collapse_sidebar_css = """
        <style>
            [data-testid="stSidebar"] {
                display: none;
            }
        </style>
    """
    
    # Embed the CSS into the Streamlit app
    st.markdown(collapse_sidebar_css, unsafe_allow_html=True)

    # Fetching imbalance data
    df_imbalance = fetch_intraday_imbalance_data()

    # Handling empty or invalid data
    if df_imbalance.empty:
        st.warning("No data available for today and tomorrow.")
        return

    # Adjust the index to start from 00:00:00
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Generate a range of timestamps for reindexing
    expected_timestamps = pd.date_range(start=start_of_day, periods=len(df_imbalance), freq='15T')
    # Align the DataFrame index to the expected timestamps
    df_imbalance.index = expected_timestamps

    # Resetting the index to make sure it's in a form usable for Streamlit components
    df_imbalance = df_imbalance.reset_index()

    # Rename the index column to 'Timestamp' for clarity
    df_imbalance = df_imbalance.rename(columns={'index': 'Timestamp'})

    # Filtering only valid rows for plotting
    df_imbalance = df_imbalance.dropna(subset=['Excedent Price', 'Deficit Price', 'Imbalance Volume'])

    # Convert columns to numeric types to ensure consistency for plotting
    df_imbalance['Excedent Price'] = pd.to_numeric(df_imbalance['Excedent Price'], errors='coerce')
    df_imbalance['Deficit Price'] = pd.to_numeric(df_imbalance['Deficit Price'], errors='coerce')
    df_imbalance['Imbalance Volume'] = pd.to_numeric(df_imbalance['Imbalance Volume'], errors='coerce')


    # Fetch notified and actual wind production and create the combined dataframe
    df_wind_notified = fetch_process_wind_notified()
    df_wind_actual = fetch_process_wind_actual_production()
    df_wind_volue = preprocess_volue_forecast(fetch_volue_wind_data())
    df_wind = combine_wind_production_data(df_wind_notified, df_wind_actual, df_wind_volue)

    fetching_Cogealac_data_15min()
    df_wind_solcast = predicting_wind_production_15min()
    df_wind = add_solcast_forecast_to_wind_dataframe(df_wind, df_wind_solcast)
    
    # Replace 0 with NaN in 'Actual Production (MW)' to identify missing values
    df_wind['Actual Production (MW)'] = df_wind['Actual Production (MW)'].replace(0, None)

    # Add columns to indicate when forecasts should be used
    df_wind['Volue Forecast (Filtered)'] = df_wind['Volue Forecast (MW)'].where(df_wind['Actual Production (MW)'].isna())
    df_wind['Solcast Forecast (Filtered)'] = df_wind['Solcast Forecast (MW)'].where(df_wind['Actual Production (MW)'].isna())

    # Create a long-format DataFrame for Plotly
    df_wind_long = df_wind.melt(
        id_vars=['Timestamp'],
        value_vars=[
            'Actual Production (MW)',
            'Notified Production (MW)',
            'Volue Forecast (Filtered)',
            'Solcast Forecast (Filtered)'
        ],
        var_name='Type',
        value_name='Production (MW)'
    )

    # Remove rows where 'Production (MW)' is NaN
    df_wind_long = df_wind_long[df_wind_long['Production (MW)'].notna()]



    # Split into two columns
    col1, col2 = st.columns(2)

    # LEFT COLUMN: Monitoring the State of the Balancing Market
    with col1:
        st.header("Balancing Market State Monitoring")

        # Key Metrics Overview for the Market State
        st.write("### Key Metrics Overview")
        system_state = "Deficit" if df_imbalance['Imbalance Volume'].iloc[-1] < 0 else "Excedent"
        st.metric("System State", system_state)
        st.metric("Deficit Price", f"{df_imbalance['Deficit Price'].iloc[-1]:.2f} RON/MWh")
        st.metric("Excedent Price", f"{df_imbalance['Excedent Price'].iloc[-1]:.2f} RON/MWh")
        st.metric("Imbalance Volume", f"{df_imbalance['Imbalance Volume'].iloc[-1]:.2f} MWh")

        # Plotting Excedent and Deficit Prices
        st.write("### Excedent and Deficit Prices Over Time")
        fig_prices = px.line(df_imbalance, x='Timestamp', y=['Excedent Price', 'Deficit Price'],
                             labels={'value': 'Price (RON/MWh)', 'Timestamp': 'Timestamp'},
                             title="Excedent vs Deficit Prices Over Time")
        st.plotly_chart(fig_prices, use_container_width=True)

        # Plotting Imbalance Volume
        st.write("### Imbalance Volume Over Time")
        fig_volume = px.line(df_imbalance, x='Timestamp', y="Imbalance Volume",
                             labels={'Imbalance Volume': 'Volume (MWh)', 'Timestamp': 'Timestamp'},
                             title="Imbalance Volume Over Time")
        st.plotly_chart(fig_volume, use_container_width=True)

    # RIGHT COLUMN: Monitoring and Forecasting Fundamentals
    with col2:
        # Interactive dashboard header
        st.header("Wind Production Monitoring")

        # Plotting Actual vs Notified Wind Production with Forecasts
        st.write("### Actual vs Notified Wind Production Over Time (With Forecasts)")
        fig_wind_forecast = px.line(
            df_wind_long,
            x='Timestamp',
            y='Production (MW)',
            color='Type',
            line_dash='Type',
            labels={'Production (MW)': 'Production (MW)', 'Timestamp': 'Timestamp'},
            title="Actual vs Notified Wind Production (With Forecasts)"
        )

        # Customize styles: Notified should always be solid
        fig_wind_forecast.for_each_trace(lambda trace: trace.update(line_dash=None) if trace.name == 'Notified Production (MW)' else None)

        # Show the plot
        st.plotly_chart(fig_wind_forecast, use_container_width=True)