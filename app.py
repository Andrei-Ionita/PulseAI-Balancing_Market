import streamlit as st
from modules.bm_intraday import render_balancing_market_intraday_page
from modules.bm_day_ahead import render_day_ahead_forecast
import asyncio
from modules.bm_intraday import refresh_app

# Set the page configuration for a wide layout and dark theme
st.set_page_config(page_title="Balancing Market Dashboard", layout="wide")

# Sidebar navigation
# This will be the only sidebar navigation setup
st.sidebar.title("Navigation")
page = st.sidebar.selectbox("Choose a page:", ["Intraday Monitoring", "Day Ahead Forecast"])

# Render pages based on selection
if page == "Intraday Monitoring":
    render_balancing_market_intraday_page()  # Render the Intraday Monitoring page
elif page == "Day Ahead Forecast":
    render_day_ahead_forecast()  # Render the Day Ahead Forecast page

# Start the refresh loop
if __name__ == "__main__":
    asyncio.run(refresh_app())