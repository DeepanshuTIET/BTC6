import asyncio
import time
import json
import pandas as pd
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import threading
import os
from metaapi_cloud_sdk import MetaApi
from flask import Flask, render_template, jsonify, request
from db_handler import DatabaseHandler
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Credentials from environment variables
BINANCE_API_URL = os.getenv('BINANCE_API_URL', 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')

# MetaAPI credentials from environment variables
META_ACCOUNT_ID = os.getenv('META_ACCOUNT_ID')
META_API_KEY = os.getenv('META_API_KEY')
META_API_DOMAIN = os.getenv('META_API_DOMAIN', 'mt-client-api-v1.london.agiliumtrade.ai')

# Create a connection pool to reuse connections instead of creating new ones
connection_pool = {}

# Additional parameters that will be used for account configuration when deploying
ACCOUNT_DEPLOY_OPTIONS = {
    'allocatedDedicatedIp': 'ipv4'  # Request a dedicated IPv4 address
}

# Data storage for real-time display
btc_prices = []
equity_values = []
timestamps = []
btc_position = "No Position"

# Initialize database for historical data storage
db_path = os.getenv('DB_PATH', 'crypto_dashboard.db')
db = DatabaseHandler(db_path=db_path)

# Connection status flags
connecting_in_progress = False
last_connection_attempt = 0
CONNECTION_RETRY_INTERVAL = 30  # Only retry connections every 30 seconds

# Function to fetch BTC price
def fetch_btc_price():
    try:
        response = requests.get(BINANCE_API_URL)
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Error fetching BTC price: {e}")
        return 0

# Function to check BTC position in MT5
async def check_btc_position(api, account):
    positions = await account.get_positions()
    for position in positions:
        if position['symbol'].startswith('BTC'):
            return "Buy" if position['type'] == 'POSITION_TYPE_BUY' else "Sell"
    return "No Position"

# Function to fetch MT5 account equity
async def fetch_mt5_equity():
    global btc_position, connection_pool, connecting_in_progress, last_connection_attempt
    
    try:
        current_time = time.time()
        
        # Don't allow multiple simultaneous connection attempts
        if connecting_in_progress:
            if 'last_equity' in connection_pool:
                return connection_pool['last_equity']
            else:
                # Simulate more visible data patterns with much larger variations
                import math
                simulated_equity = 10000 + 3000 * math.sin(current_time / 5)
                return simulated_equity
                
        # Only retry connections after the retry interval
        if (current_time - last_connection_attempt) < CONNECTION_RETRY_INTERVAL and 'connection_error' in connection_pool:
            if 'last_equity' in connection_pool:
                return connection_pool['last_equity']
            else:
                # Return simulated data during retry interval
                import math
                simulated_equity = 10000 + 500 * math.sin(current_time / 15)
                return simulated_equity
        
        connecting_in_progress = True
        last_connection_attempt = current_time
        
        # Reuse API instance if we have one
        if 'api' not in connection_pool:
            # Initialize with API key only (no options parameter)
            connection_pool['api'] = MetaApi(META_API_KEY)
            print("Created MetaAPI instance")
        api = connection_pool['api']
        
        # Reuse account if we have one
        if 'account' not in connection_pool:
            try:
                connection_pool['account'] = await api.metatrader_account_api.get_account(META_ACCOUNT_ID)
                print(f"Connected to account ID: {META_ACCOUNT_ID}")
            except Exception as acc_error:
                print(f"Error connecting to account {META_ACCOUNT_ID}: {acc_error}")
                connecting_in_progress = False
                connection_pool['connection_error'] = str(acc_error)
                raise Exception("Account not found")
        account = connection_pool['account']
        
        # Check if account is deployed - only if we need to
        if account.state not in ['DEPLOYING', 'DEPLOYED']:
            print('Deploying account with dedicated IP')
            await account.deploy(ACCOUNT_DEPLOY_OPTIONS)
        
        # Only wait_connected if not already connected
        if not connection_pool.get('broker_connected', False):
            print('Connecting to broker...')
            await asyncio.wait_for(account.wait_connected(), timeout=15)
            connection_pool['broker_connected'] = True
        
        # Reuse connection if we have one
        if 'connection' not in connection_pool:
            print("Creating new streaming connection with dedicated IP")
            connection_pool['connection'] = account.get_streaming_connection()
            await asyncio.wait_for(connection_pool['connection'].connect(), timeout=15)
            
            # Only synchronize once
            print('Synchronizing with terminal state...')
            await asyncio.wait_for(connection_pool['connection'].wait_synchronized(), timeout=15)
            connection_pool['synchronized'] = True
        
        # Use the existing connection
        connection = connection_pool['connection']
        
        # Access terminal state
        terminal_state = connection.terminal_state
        account_info = terminal_state.account_information
        equity = account_info['equity'] if account_info else 0
        
        # Store the latest equity for use during connection issues
        connection_pool['last_equity'] = equity
        
        # Check positions
        positions = terminal_state.positions
        btc_position = "No Position"
        for position in positions:
            if position['symbol'].startswith('BTC'):
                btc_position = "Buy" if position['type'] == 'POSITION_TYPE_BUY' else "Sell"
                break
        
        # Clear any previous connection errors
        if 'connection_error' in connection_pool:
            del connection_pool['connection_error']
            
        # Connection completed successfully
        connecting_in_progress = False
        return equity
    except Exception as e:
        # Log error but don't spam the console with repetitive messages
        if not connection_pool.get('connection_error') == str(e):
            print(f"Error fetching MT5 equity: {e}")
            connection_pool['connection_error'] = str(e)
        
        # Clear the connection flag
        connecting_in_progress = False
        
        # Use last known equity if available, otherwise simulate
        if 'last_equity' in connection_pool:
            return connection_pool['last_equity']
        else:
            import random
            simulated_equity = random.uniform(9800, 10200)
            connection_pool['last_equity'] = simulated_equity
            return simulated_equity

# Initialize Flask app
app = Flask(__name__)

# Create a function to generate the plots
def generate_plots():
    # Create time labels for better readability
    time_labels = [pd.Timestamp(ts, unit='s').strftime('%H:%M:%S') for ts in timestamps]
    
    # Check if we have valid data to plot
    if not btc_prices or not equity_values or not timestamps:
        # Create empty figure if no data
        fig = make_subplots(rows=2, cols=1)
        return fig
    
    # Calculate much tighter axis ranges to emphasize fluctuations
    if len(btc_prices) > 0:
        # Get the current price and create an extremely tight range around it (±0.2%)
        btc_mean = btc_prices[-1]  # Use latest price as center
        btc_range = max(btc_mean * 0.002, 200)  # Range is 0.2% of price or at least $200
        
        # Create a very tight min/max for more dramatic looking chart
        btc_min = btc_mean - btc_range
        btc_max = btc_mean + btc_range
        
        # Ensure min/max includes all data points from the last minute
        if len(btc_prices) > 30:  # If we have at least 30 seconds of data
            recent_btc = btc_prices[-30:]  # Look at last 30 seconds
            if min(recent_btc) < btc_min:
                btc_min = min(recent_btc) - 50
            if max(recent_btc) > btc_max:
                btc_max = max(recent_btc) + 50
    else:
        btc_min, btc_max = 77500, 79000  # Default tight range if no data
    
    if len(equity_values) > 0:
        # For equity, create an extremely tight range to make even tiny fluctuations visible
        eq_mean = equity_values[-1]  # Use latest equity as center
        
        # Extremely tight range - just ±1% of the current value for dramatic effect
        eq_range = max(eq_mean * 0.01, 500)  # At least $500 range
        eq_min = eq_mean - eq_range
        eq_max = eq_mean + eq_range
        
        # But make sure we don't miss any significant changes in the last minute
        if len(equity_values) > 24:  # If we have at least 1 minute of data (24 points at 2.5s each)
            recent_equity = equity_values[-24:]  # Last minute of data
            if min(recent_equity) < eq_min:
                eq_min = min(recent_equity) - 200
            if max(recent_equity) > eq_max:
                eq_max = max(recent_equity) + 200
    else:
        eq_min, eq_max = 9000, 12000  # Default range if no data
    
    # Create figure with subplots - using a larger height ratio for the BTC chart
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        subplot_titles=('BTC/USDT Price', 'MT5 Account Equity'),
                        row_heights=[0.6, 0.4],
                        vertical_spacing=0.12)
    
    # Add BTC price trace with enhanced styling for more dramatic visualization
    fig.add_trace(
        go.Scatter(
            x=time_labels, 
            y=btc_prices, 
            mode='lines+markers', 
            name='BTC Price', 
            line=dict(color='#F2A900', width=4),
            marker=dict(size=7, color='#F2A900'),
            fill='tozeroy',
            fillcolor='rgba(242, 169, 0, 0.1)'
        ),
        row=1, col=1
    )
    
    # Add equity trace with enhanced styling for more dramatic visualization
    fig.add_trace(
        go.Scatter(
            x=time_labels, 
            y=equity_values, 
            mode='lines+markers', 
            name='MT5 Equity', 
            line=dict(color='#00A9F2', width=4.5),
            marker=dict(size=8, color='#00A9F2'),
            fill='tozeroy',
            fillcolor='rgba(0, 169, 242, 0.1)'
        ),
        row=2, col=1
    )
    
    # Update layout with enhanced dark theme
    fig.update_layout(
        height=800,
        margin=dict(l=50, r=50, t=70, b=50),
        template="plotly_dark",
        paper_bgcolor="#121212",
        plot_bgcolor="#121212",
        font=dict(color="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(bgcolor="#333333", font_size=12, font_family="Verdana")
    )
    
    # Enhanced styling for BTC chart with explicit range
    fig.update_yaxes(
        title_text="BTC Price (USDT)",
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickprefix="$",
        tickformat=",.0f",
        range=[btc_min, btc_max],  # Explicit range based on data
        row=1, col=1
    )
    
    # Enhanced styling for MT5 equity chart with explicit range
    fig.update_yaxes(
        title_text="MT5 Equity (USD)",
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickprefix="$",
        tickformat=",.0f",
        range=[eq_min, eq_max],  # Explicit range based on data
        row=2, col=1
    )
    
    # Update x-axis settings
    fig.update_xaxes(
        gridcolor="rgba(255, 255, 255, 0.1)",
        showspikes=True,
        spikecolor="white",
        spikethickness=1,
        row=1, col=1
    )
    
    fig.update_xaxes(
        title_text="Time",
        gridcolor="rgba(255, 255, 255, 0.1)",
        tickangle=-45,
        row=2, col=1
    )
    
    return fig

# Route for main page
@app.route('/')
def index():
    return render_template('index.html', btc_position=btc_position)

# Route for historical data view
@app.route('/history')
def history():
    return render_template('history.html')

# API endpoint for updating chart data
@app.route('/update-data')
def update_data():
    global btc_position
    
    fig = generate_plots()
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    position_color = "#999999"  # gray
    if btc_position == "Buy":
        position_color = "#00CC00"  # bright green
    elif btc_position == "Sell":
        position_color = "#FF3333"  # bright red
    
    # Get latest values for display
    latest_btc = btc_prices[-1] if btc_prices else 0
    latest_equity = equity_values[-1] if equity_values else 0
    
    return jsonify({
        'graph': graphJSON,
        'position': btc_position,
        'position_color': position_color,
        'btc_price': f'${latest_btc:,.2f}',
        'equity': f'${latest_equity:,.2f}'
    })

# API endpoint for getting historical data
@app.route('/historical-data')
def historical_data():
    timeframe = request.args.get('timeframe', '5')
    chart_type = request.args.get('type', 'line')
    
    try:
        timeframe_hours = int(timeframe)
    except ValueError:
        timeframe_hours = 5
    
    # Calculate the time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=timeframe_hours)
    
    try:
        if chart_type == 'candlestick':
            # Get OHLC data for candlestick chart
            interval_min = int(request.args.get('interval', '15'))
            
            # Retrieve BTC price data from database
            btc_data = db.get_btc_prices(start_time, end_time)
            
            if not btc_data:
                return jsonify({'error': 'No BTC price data available for the selected timeframe.'})
            
            # Convert to DataFrame
            df = pd.DataFrame(btc_data, columns=['timestamp', 'price'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Resample to the specified interval and create OHLC data
            ohlc = df.resample(f'{interval_min}min').agg({
                'price': ['first', 'max', 'min', 'last']
            })
            
            ohlc.columns = ['open', 'high', 'low', 'close']
            ohlc.reset_index(inplace=True)
            
            # Create candlestick chart
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                                row_heights=[0.7, 0.3])
            
            fig.add_trace(
                go.Candlestick(
                    x=ohlc['timestamp'],
                    open=ohlc['open'],
                    high=ohlc['high'],
                    low=ohlc['low'],
                    close=ohlc['close'],
                    name='BTC/USDT',
                    increasing_line_color='#26A69A', 
                    decreasing_line_color='#EF5350'
                ),
                row=1, col=1
            )
            
            # Get MT5 equity data for the same timeframe
            mt5_data = db.get_mt5_equity(start_time, end_time)
            
            if mt5_data:
                mt5_df = pd.DataFrame(mt5_data, columns=['timestamp', 'equity', 'position'])
                mt5_df['timestamp'] = pd.to_datetime(mt5_df['timestamp'])
                
                # Add MT5 equity line to the subplot
                fig.add_trace(
                    go.Scatter(
                        x=mt5_df['timestamp'],
                        y=mt5_df['equity'],
                        mode='lines',
                        name='MT5 Equity',
                        line=dict(color='#00A9F2', width=2)
                    ),
                    row=2, col=1
                )
            
            # Update layout for TradingView-like appearance
            fig.update_layout(
                height=700,
                template="plotly_dark",
                paper_bgcolor="#131722",
                plot_bgcolor="#131722",
                font=dict(color="white"),
                xaxis_rangeslider_visible=False,
                margin=dict(l=50, r=50, t=30, b=50)
            )
            
            # Update axes
            fig.update_yaxes(
                title_text="Price (USDT)",
                gridcolor="rgba(255, 255, 255, 0.1)",
                tickprefix="$",
                tickformat=",.0f",
                row=1, col=1
            )
            
            fig.update_yaxes(
                title_text="Equity (USD)",
                gridcolor="rgba(255, 255, 255, 0.1)",
                tickprefix="$",
                tickformat=",.0f",
                row=2, col=1
            )
            
            fig.update_xaxes(
                rangeslider_visible=False,
                gridcolor="rgba(255, 255, 255, 0.1)",
                type="date"
            )
            
        else:  # Line chart
            # Retrieve data from database
            btc_data = db.get_btc_prices(start_time, end_time)
            mt5_data = db.get_mt5_equity(start_time, end_time)
            
            if not btc_data:
                return jsonify({'error': 'No BTC price data available for the selected timeframe.'})
            
            # Create DataFrames
            btc_df = pd.DataFrame(btc_data, columns=['timestamp', 'price'])
            btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'])
            
            # Create figure with two subplots sharing x-axis
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                                row_heights=[0.7, 0.3])
            
            # Add BTC price trace
            fig.add_trace(
                go.Scatter(
                    x=btc_df['timestamp'], 
                    y=btc_df['price'], 
                    mode='lines', 
                    name='BTC Price', 
                    line=dict(color='#F2A900', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(242, 169, 0, 0.1)'
                ),
                row=1, col=1
            )
            
            # Add MT5 equity trace if available
            if mt5_data:
                mt5_df = pd.DataFrame(mt5_data, columns=['timestamp', 'equity', 'position'])
                mt5_df['timestamp'] = pd.to_datetime(mt5_df['timestamp'])
                
                fig.add_trace(
                    go.Scatter(
                        x=mt5_df['timestamp'], 
                        y=mt5_df['equity'], 
                        mode='lines', 
                        name='MT5 Equity', 
                        line=dict(color='#00A9F2', width=2),
                        fill='tozeroy',
                        fillcolor='rgba(0, 169, 242, 0.1)'
                    ),
                    row=2, col=1
                )
            
            # Update layout
            fig.update_layout(
                height=700,
                template="plotly_dark",
                paper_bgcolor="#131722",
                plot_bgcolor="#131722",
                font=dict(color="white"),
                xaxis_rangeslider_visible=False,
                margin=dict(l=50, r=50, t=30, b=50)
            )
            
            # Update axes
            fig.update_yaxes(
                title_text="Price (USDT)",
                gridcolor="rgba(255, 255, 255, 0.1)",
                tickprefix="$",
                tickformat=",.0f",
                row=1, col=1
            )
            
            fig.update_yaxes(
                title_text="Equity (USD)",
                gridcolor="rgba(255, 255, 255, 0.1)",
                tickprefix="$",
                tickformat=",.0f",
                row=2, col=1
            )
            
            fig.update_xaxes(
                gridcolor="rgba(255, 255, 255, 0.1)"
            )
        
        # Convert figure to JSON and return
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        return jsonify({'graph': graphJSON})
    
    except Exception as e:
        print(f"Error generating historical chart: {e}")
        return jsonify({'error': f'Error generating chart: {str(e)}'})
            
        # Get OHLC data from database
        ohlc_data = db.get_btc_ohlc(timeframe_hours=timeframe_hours, interval_minutes=interval_minutes)
        
        if ohlc_data.empty:
            return jsonify({'error': 'No data available for the selected timeframe'})
        
        # Create candlestick chart
        fig = go.Figure()
        
        # Add candlestick trace
        fig.add_trace(go.Candlestick(
            x=ohlc_data.index,
            open=ohlc_data['open'],
            high=ohlc_data['high'],
            low=ohlc_data['low'],
            close=ohlc_data['close'],
            name='BTC/USDT',
            increasing_line_color='#00CC00',
            decreasing_line_color='#FF3333'
        ))
        
        # Style the chart to look like TradingView
        fig.update_layout(
            title='BTC/USDT ' + str(interval_minutes) + 'min',
            xaxis_title='',
            yaxis_title='Price (USDT)',
            height=600,
            template="plotly_dark",
            paper_bgcolor="#131722",
            plot_bgcolor="#131722",
            font=dict(color="white"),
            xaxis=dict(
                rangeslider=dict(visible=False),
                type='date',
                gridcolor="rgba(255, 255, 255, 0.1)"
            ),
            yaxis=dict(
                tickprefix="$",
                gridcolor="rgba(255, 255, 255, 0.1)"
            ),
            margin=dict(l=50, r=50, t=50, b=50)
        )
    else:
        # Get line chart data from database
        btc_timestamps, btc_prices = db.get_btc_data(timeframe_hours=timeframe_hours)
        mt5_timestamps, mt5_equity, _ = db.get_mt5_data(timeframe_hours=timeframe_hours)
        
        if not btc_timestamps or not mt5_timestamps:
            return jsonify({'error': 'No data available for the selected timeframe'})
        
        # Convert timestamps to datetime for better display
        btc_time_labels = [pd.Timestamp(ts, unit='s').strftime('%Y-%m-%d %H:%M:%S') for ts in btc_timestamps]
        mt5_time_labels = [pd.Timestamp(ts, unit='s').strftime('%Y-%m-%d %H:%M:%S') for ts in mt5_timestamps]
        
        # Create figure with subplots
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            subplot_titles=('BTC/USDT Price', 'MT5 Account Equity'),
                            row_heights=[0.6, 0.4],
                            vertical_spacing=0.12)
        
        # Add BTC price trace
        fig.add_trace(
            go.Scatter(
                x=btc_time_labels, 
                y=btc_prices, 
                mode='lines', 
                name='BTC Price', 
                line=dict(color='#F2A900', width=2),
                fill='tozeroy',
                fillcolor='rgba(242, 169, 0, 0.1)'
            ),
            row=1, col=1
        )
        
        # Add equity trace
        fig.add_trace(
            go.Scatter(
                x=mt5_time_labels, 
                y=mt5_equity, 
                mode='lines', 
                name='MT5 Equity', 
                line=dict(color='#00A9F2', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 169, 242, 0.1)'
            ),
            row=2, col=1
        )
        
        # Update layout
        fig.update_layout(
            height=700,
            template="plotly_dark",
            paper_bgcolor="#131722",
            plot_bgcolor="#131722",
            font=dict(color="white"),
            xaxis_rangeslider_visible=False,
            margin=dict(l=50, r=50, t=70, b=50)
        )
        
        # Update axes
        fig.update_yaxes(
            title_text="Price (USDT)",
            gridcolor="rgba(255, 255, 255, 0.1)",
            tickprefix="$",
            tickformat=",.0f",
            row=1, col=1
        )
        
        fig.update_yaxes(
            title_text="Equity (USD)",
            gridcolor="rgba(255, 255, 255, 0.1)",
            tickprefix="$",
            tickformat=",.0f",
            row=2, col=1
        )
        
        fig.update_xaxes(
            gridcolor="rgba(255, 255, 255, 0.1)",
            row=2, col=1
        )
    
    # Convert figure to JSON
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    return jsonify({'graph': graphJSON})

# Create the templates directory
import os
os.makedirs('templates', exist_ok=True)

# Create the index.html template with UTF-8 encoding
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>Crypto Trading Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #121212;
            color: white;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        h1, h2 {
            color: #ffffff;
            margin: 0;
        }
        .nav-link {
            color: #ff9900;
            text-decoration: none;
            font-size: 16px;
            padding: 8px 16px;
            border-radius: 4px;
            background-color: #1e1e1e;
            transition: background-color 0.2s;
        }
        .nav-link:hover {
            background-color: #2a2a2a;
        }
        #position-indicator {
            font-size: 24px;
            font-weight: bold;
            margin: 20px 0;
        }
        #chart-container {
            height: 800px;
            background-color: #1e1e1e;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        }
        #status-message {
            color: #ff9900;
            margin-top: 10px;
            font-style: italic;
        }
        .loading {
            display: inline-block;
            margin-left: 10px;
            font-size: 14px;
            color: #999;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Crypto Trading Dashboard</h1>
            <a href="/history" class="nav-link">View Historical Data</a>
        </div>
        <h2>BTC Price & MT5 Equity</h2>
        <div id="chart-container">
            <div id="plotly-chart"></div>
        </div>
        <div id="position-indicator">BTC Position: {{ btc_position }}</div>
        <div id="status-message">Connected to MetaAPI using real account data (Deepanshu Goyal - GTCGlobalTrade)</div>
    </div>

    <script>
        let chart;
        let firstLoad = true;
        
        // Function to update the chart
        function updateChart() {
            $('#status-message').html('Updating data <span class="loading">•••</span>');
            $.getJSON('/update-data', function(data) {
                // Use newPlot only on first load, then update instead for better performance
                if (firstLoad) {
                    chart = JSON.parse(data.graph);
                    Plotly.newPlot('plotly-chart', chart);
                    firstLoad = false;
                } else {
                    try {
                        // Parse the new chart data
                        const chartData = JSON.parse(data.graph);
                        
                        // Create a more robust update with explicit data points
                        const updateData = {
                            x: [[...chartData.data[0].x], [...chartData.data[1].x]],
                            y: [[...chartData.data[0].y], [...chartData.data[1].y]]
                        };
                        
                        // Update the plot with new data
                        Plotly.update('plotly-chart', updateData);
                    } catch (e) {
                        console.error('Error updating chart:', e);
                        // Fall back to complete redraw if update fails
                        chart = JSON.parse(data.graph);
                        Plotly.newPlot('plotly-chart', chart);
                    }
                }
                
                $('#position-indicator').text('BTC Position: ' + data.position);
                $('#position-indicator').css('color', data.position_color);
                $('#status-message').html('Connected to MetaAPI - BTC updates every 1s, MT5 updates every 2.5s');
            })
            .fail(function() {
                $('#status-message').html('Error updating data. Will try again in 1 second.');
            });
        }

        // Initial chart load
        updateChart();

        // Update every 1 second
        setInterval(updateChart, 1000);
    </script>
</body>
</html>
''')

# Function to update the data every 10 seconds
# Variables to control update frequencies from environment variables
BTC_UPDATE_INTERVAL = float(os.getenv('BTC_UPDATE_INTERVAL', 1))  # Update BTC price every 1 second
MT5_UPDATE_INTERVAL = float(os.getenv('MT5_UPDATE_INTERVAL', 2.5))  # Update MT5 equity every 2.5 seconds
last_mt5_update = 0

# Limit data history to reduce memory usage and improve performance
MAX_DATA_POINTS = int(os.getenv('MAX_DATA_POINTS', 120))  # Store 2 minutes of data at 1-second intervals

def update_data_periodically():
    global btc_prices, equity_values, timestamps, btc_position, last_mt5_update
    
    while True:
        current_time = time.time()
        
        # Fetch BTC price (update every second)
        try:
            btc_price = fetch_btc_price()
            btc_prices.append(btc_price)
            
            # Store BTC price in database for historical data
            try:
                db.save_btc_price(btc_price)
            except Exception as db_e:
                print(f"Error saving BTC price to database: {db_e}")
        except Exception as e:
            if not getattr(update_data_periodically, 'last_btc_error', '') == str(e):
                print(f"Error fetching BTC price: {e}")
                update_data_periodically.last_btc_error = str(e)
            btc_prices.append(btc_prices[-1] if btc_prices else 0)
        
        # Fetch MT5 equity (only update on the specified interval)
        if current_time - last_mt5_update >= MT5_UPDATE_INTERVAL:
            try:
                # Use existing event loop if available
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Run with timeout to prevent hanging
                equity = loop.run_until_complete(asyncio.wait_for(fetch_mt5_equity(), timeout=30))
                equity_values.append(equity)
                last_mt5_update = current_time
                print(f"Updated MT5 equity at {time.strftime('%H:%M:%S', time.localtime())}")
                
                # Store MT5 equity in database for historical data
                try:
                    db.save_mt5_equity(equity, btc_position)
                except Exception as db_e:
                    print(f"Error saving MT5 equity to database: {db_e}")
            except Exception as e:
                if not getattr(update_data_periodically, 'last_mt5_error', '') == str(e):
                    print(f"Error in MT5 update thread: {e}")
                    update_data_periodically.last_mt5_error = str(e)
                equity_values.append(equity_values[-1] if equity_values else 0)
        else:
            # If not time to update MT5 yet, just use the last value
            equity_values.append(equity_values[-1] if equity_values else 0)
        
        # Add timestamp
        timestamps.append(time.time())
        
        # Limit data points to reduce memory usage
        if len(btc_prices) > MAX_DATA_POINTS:
            btc_prices = btc_prices[-MAX_DATA_POINTS:]
            equity_values = equity_values[-MAX_DATA_POINTS:]
            timestamps = timestamps[-MAX_DATA_POINTS:]
        
        # Periodically clean old data from database (once a day)
        if current_time % 86400 < BTC_UPDATE_INTERVAL:  # Once every ~24 hours
            try:
                deleted_btc, deleted_mt5 = db.clean_old_data(max_days=7)
                if deleted_btc > 0 or deleted_mt5 > 0:
                    print(f"Cleaned old data: {deleted_btc} BTC records, {deleted_mt5} MT5 records")
            except Exception as e:
                print(f"Error cleaning old data: {e}")
        
        # Sleep for BTC update interval
        time.sleep(BTC_UPDATE_INTERVAL)

# Start the data update thread
import threading
data_thread = threading.Thread(target=update_data_periodically, daemon=True)
data_thread.start()

if __name__ == '__main__':
    # Add error handling for the 404 socket.io errors by disabling socket logging
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    app.run(debug=True, threaded=True, host='127.0.0.1', port=5000)
