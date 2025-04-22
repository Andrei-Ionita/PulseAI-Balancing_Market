import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from entsoe import EntsoePandasClient
import os
from dotenv import load_dotenv
import asyncio

from data_fetching.entsoe_data import fetch_intraday_imbalance_data  # Importing the function to fetch data
from data_fetching.entsoe_data import wind_solar_generation, actual_generation_source       # Assuming this function is also available
# Importing the wind data
from data_fetching.entsoe_newapi_data import fetch_process_wind_notified, fetch_process_wind_actual_production, preprocess_volue_forecast, fetch_volue_wind_data, combine_wind_production_data, fetching_Cogealac_data_15min, predicting_wind_production_15min, add_solcast_forecast_to_wind_dataframe
# Importing the solar data
from data_fetching.entsoe_newapi_data import fetch_process_solar_notified, fetch_process_solar_actual_production, fetch_volue_solar_data, combine_solar_production_data
# Importing the hydro data
from data_fetching.entsoe_newapi_data import fetch_process_hydro_water_reservoir_actual_production, fetch_process_hydro_river_actual_production, fetch_volue_hydro_data, align_and_combine_hydro_data
# Importing consumption data
from data_fetching.entsoe_newapi_data import fetch_consumption_forecast, fetch_actual_consumption, combine_consumption_data
# Importing the unintended deviations data
from data_fetching.entsoe_newapi_data import fetch_unintended_deviation_data
# Importing the IGCC data
from data_fetching.entsoe_newapi_data import fetch_igcc_netting_flows, plot_igcc_netting_flows

#============================================================================Rendering the Intraday Balancing Market Page================================================================

def render_balancing_market_intraday_page():
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
    # df_wind['Solcast Forecast (Filtered)'] = df_wind['Solcast Forecast (MW)'].where(df_wind['Actual Production (MW)'].isna())

    # Create a long-format DataFrame for Plotly
    df_wind_long = df_wind.melt(
        id_vars=['Timestamp'],
        value_vars=[
            'Actual Production (MW)',
            'Notified Production (MW)',
            'Volue Forecast (Filtered)'
            # 'Solcast Forecast (Filtered)'
        ],
        var_name='Type',
        value_name='Production (MW)'
    )

    # Remove rows where 'Production (MW)' is NaN
    df_wind_long = df_wind_long[df_wind_long['Production (MW)'].notna()]

    # Processing the Solar Production
    df_solar_notified = fetch_process_solar_notified()
    df_solar_actual = fetch_process_solar_actual_production()
    df_solar_volue = preprocess_volue_forecast(fetch_volue_solar_data())
    df_solar = combine_solar_production_data(df_solar_notified, df_solar_actual, df_solar_volue)

    # Step 1: Identify the last interval with actual production > 0
    last_actual_index = df_solar[df_solar['Actual Production (MW)'] > 0].index.max()

    # Step 2: Compute Deviations
    df_solar['Deviation_Actual'] = df_solar['Actual Production (MW)'] - df_solar['Notified Production (MW)']
    df_solar['Deviation_Forecast'] = df_solar['Volue Forecast (MW)'] - df_solar['Notified Production (MW)']

    # Step 3: Split the data for solid and dashed lines
    df_solar['Deviation_Combined'] = np.where(
        df_solar.index <= last_actual_index,
        df_solar['Deviation_Actual'],
        np.nan
    )
    df_solar['Deviation_Forecast_Line'] = np.where(
        df_solar.index > last_actual_index,
        df_solar['Deviation_Forecast'],
        np.nan
    )

    # Step 4: Visualization for Actual vs Notified Solar Productio
    # Plot 1: Actual vs Notified Solar Production Over Time
    fig_actual_vs_notified = px.line(
        df_solar, 
        x='Timestamp', 
        y=['Notified Production (MW)', 'Actual Production (MW)', 'Volue Forecast (MW)'],
        labels={'value': 'Production (MW)', 'Timestamp': 'Timestamp'},
        title="Actual vs Notified Solar Production (With Forecast)"
    )
    # Update line styles
    fig_actual_vs_notified.update_traces(selector=dict(name='Notified Production (MW)'),
                                         line=dict(color='blue', dash='solid'))
    fig_actual_vs_notified.update_traces(selector=dict(name='Actual Production (MW)'),
                                         line=dict(color='skyblue', dash='solid'))
    fig_actual_vs_notified.update_traces(selector=dict(name='Volue Forecast (MW)'),
                                         line=dict(color='orange', dash='dash'))

    # Processing the hydro production data
    df_hydro_reservoir_actual = fetch_process_hydro_water_reservoir_actual_production()
    df_hydro_river_actual = fetch_process_hydro_river_actual_production()
    df_hydro_volue = fetch_volue_hydro_data()
    df_hydro = align_and_combine_hydro_data(df_hydro_reservoir_actual, df_hydro_river_actual, df_hydro_volue)

    # Combine Actual Hydro Production (Hydro Reservoir + Hydro River)
    df_hydro['Hydro_Actual'] = df_hydro['Hydro Reservoir Actual (MW)'] + df_hydro['Hydro River Actual (MW)']

    # Identify the last interval with actual production > 0
    last_actual_index = df_hydro[df_hydro['Hydro_Actual'] > 0].index.max()

    # Replace Hydro Actual after the last valid production with None
    df_hydro.loc[last_actual_index + 1:, 'Hydro_Actual'] = None

    # Melt the DataFrame to long format for Plotly Express
    df_hydro_long = df_hydro.melt(id_vars=['Timestamp'], 
                                  value_vars=['Hydro_Actual', 'Volue Forecast (MW)'],
                                  var_name='Type', value_name='Production')

    # Create line dash mapping
    line_dash_map = {
        'Hydro_Actual': 'solid',
        'Volue Forecast (MW)': 'dash'
    }

    # Visualization: Hydro Actual vs Forecast
    fig_hydro_actual_forecast = px.line(
        df_hydro_long, 
        x='Timestamp', 
        y='Production', 
        color='Type', 
        line_dash='Type',
        line_dash_map=line_dash_map,
        title="Actual vs Forecasted Hydro Production",
        labels={'Production': 'Production (MW)', 'Timestamp': 'Timestamp'},
        color_discrete_map={
            'Hydro_Actual': 'blue',
            'Volue Forecast (MW)': 'orange'
        }
    )

    # Processing the Consumption data
    df_consumption_forecast = fetch_consumption_forecast()
    df_consumption_actual = fetch_actual_consumption()
    df_consumption = combine_consumption_data(df_consumption_forecast, df_consumption_actual)

    # Drop rows with None in 'Actual Consumption (MW)' for clean plotting
    df_actual = df_consumption.dropna(subset=['Actual Consumption (MW)'])

    # Plotly Graph: Actual vs Forecasted Consumption
    fig = px.line()

    # Add Actual Consumption line
    fig.add_scatter(
        x=df_actual['Timestamp'],
        y=df_actual['Actual Consumption (MW)'],
        mode='lines',
        name='Actual Consumption (MW)',
        line=dict(color='#1f77b4')  # Blue line
    )

    # Add Forecasted Consumption line
    fig.add_scatter(
        x=df_consumption['Timestamp'],
        y=df_consumption['Consumption Forecast (MW)'],
        mode='lines',
        name='Consumption Forecast (MW)',
        line=dict(color='#ff7f0e')  # Orange line
    )

    # Update layout for clarity
    fig.update_layout(
        title="Actual vs Forecasted Consumption Over Time",
        xaxis_title="Timestamp",
        yaxis_title="Consumption (MW)",
        legend_title="Type",
        template="plotly_dark",
        hovermode="x unified"
    )

    # Processing the unintended deviations data
    df_unintended = fetch_unintended_deviation_data()
    # Convert timestamp column to datetime
    df_unintended['Timestamp'] = pd.to_datetime(df_unintended['Timestamp'])

    # Create the figure
    fig_unintended = go.Figure()

    # Add Unintended Import (solid line)
    fig_unintended .add_trace(go.Scatter(
        x=df_unintended['Timestamp'], 
        y=df_unintended['Unintended_Import (MW)'], 
        mode='lines', 
        name="Unintended Import",
        line=dict(color="green", width=2)
    ))

    # Add Unintended Export (solid line)
    fig_unintended.add_trace(go.Scatter(
        x=df_unintended['Timestamp'], 
        y=df_unintended['Unintended_Export (MW)'], 
        mode='lines', 
        name="Unintended Export",
        line=dict(color="red", width=2)
    ))

    # Update layout for professional look
    fig_unintended.update_layout(
        title="<b>Unintended Energy Flows Monitoring</b>",
        xaxis_title="Timestamp",
        yaxis_title="Power Flow (MW)",
        legend_title="Flow Type",
        template="plotly_dark",
        hovermode="x unified",
        font=dict(family="Arial", size=14),
        margin=dict(l=40, r=40, t=60, b=40),
    )

    # Processing the IGCC data
    df_igcc = fetch_igcc_netting_flows()

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

        # Solar Production Visualizations
        st.plotly_chart(fig_actual_vs_notified, use_container_width=True)
        st.subheader("Actual and Forecasted Deviations from Notified Solar Production")
        fig_deviation = px.line(
            df_solar, 
            x='Timestamp', 
            y=['Deviation_Combined', 'Deviation_Forecast_Line'],
            labels={'value': 'Deviation (MW)', 'Timestamp': 'Timestamp'},
            title="Actual and Forecasted Deviations from Notified Solar Production"
        )
        # Update line styles
        fig_deviation.update_traces(selector=dict(name='Deviation_Combined'),
                                    line=dict(color='skyblue', dash='solid'),
                                    name="Deviation - Actual Production")
        fig_deviation.update_traces(selector=dict(name='Deviation_Forecast_Line'),
                                    line=dict(color='orange', dash='dash'),
                                    name="Deviation - Forecast")

        st.plotly_chart(fig_deviation, use_container_width=True)

        # Hydro Production Visualizations
        st.subheader("Hydro Production Monitoring")
        st.plotly_chart(fig_hydro_actual_forecast, use_container_width=True)

        # Consumption Visualization
        st.header("Consumption Monitoring")
        st.write("### Actual vs Forecasted Consumption Over Time")
        st.plotly_chart(fig, use_container_width=True)

        # Unintended Deviations Visualization
        st.header("Unintended Deviations Monitoring")
        st.plotly_chart(fig_unintended , use_container_width=True)

        # IGCC Netting Flows Monitoring
        st.header("IGCC Netting Flows Monitoring")
        fig_igcc = plot_igcc_netting_flows(df_igcc)

async def refresh_app():
    while True:
        await asyncio.sleep(15*60)  # Wait for 15 minutes
        st.rerun()

