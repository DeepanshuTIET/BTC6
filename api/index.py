import os
import sys
import json
import requests
import math
import random
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get correct absolute paths for Vercel deployment
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
template_path = os.path.join(root_dir, 'templates')
static_path = os.path.join(root_dir, 'static')

# Create Flask app with absolute paths
app = Flask(__name__, 
          template_folder=template_path,
          static_folder=static_path,
          static_url_path='/static')

# API URLs and credentials
BINANCE_API_URL = os.getenv('BINANCE_API_URL', 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
BINANCE_KLINE_URL = 'https://api.binance.com/api/v3/klines'
META_ACCOUNT_ID = os.getenv('META_ACCOUNT_ID')
META_API_KEY = os.getenv('META_API_KEY')
META_API_DOMAIN = os.getenv('META_API_DOMAIN', 'mt-client-api.agiliumtrade.ai')

# Store last fetched data in memory
last_btc_price = 65000.0  # Default to realistic value (April 2025)
last_equity = 10000.0    # Default equity value
last_position = "No Position"  # Default position

# Check if MetaAPI credentials are available
meta_api_ready = False
if META_API_KEY and META_ACCOUNT_ID:
    print(f"MetaAPI credentials found for account: {META_ACCOUNT_ID}")
    meta_api_ready = True
else:
    print("MetaAPI credentials not found. Using simulation mode.")

# Function to fetch BTC price from Binance API
def fetch_btc_price():
    global last_btc_price
    try:
        response = requests.get(BINANCE_API_URL)
        data = response.json()
        price = float(data['price'])
        last_btc_price = price  # Update last known price
        return price
    except Exception as e:
        print(f"Error fetching BTC price: {e}")
        return last_btc_price

# Function to get MT5 equity (using direct REST API call)
def get_mt5_equity():
    global last_equity
    
    if meta_api_ready:
        try:
            # Direct API call to MetaAPI (REST API)
            headers = {
                'auth-token': META_API_KEY
            }
            
            # Get account information endpoint
            url = f"https://{META_API_DOMAIN}/users/current/accounts/{META_ACCOUNT_ID}/account-information"
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if 'equity' in data:
                    equity = float(data['equity'])
                    last_equity = equity  # Update last known equity
                    print(f"Retrieved real equity: {equity}")
                    return equity
        except Exception as e:
            print(f"Error fetching MT5 equity via API: {e}")
    
    # Simulation mode - generate semi-realistic equity value
    btc_price = fetch_btc_price()
    base_equity = 10000
    time_component = math.cos(datetime.now().timestamp() / 3600) * 0.01
    price_factor = ((btc_price / 65000) - 1) * 0.03  # Correlate with BTC price changes
    equity = base_equity * (1 + price_factor + time_component)
    simulated_equity = round(equity, 2)
    print(f"Using simulated equity: {simulated_equity}")
    return simulated_equity

# Function to get BTC position (using direct REST API call)
def get_btc_position():
    global last_position
    
    if meta_api_ready:
        try:
            # Direct API call to MetaAPI (REST API)
            headers = {
                'auth-token': META_API_KEY
            }
            
            # Get positions endpoint
            url = f"https://{META_API_DOMAIN}/users/current/accounts/{META_ACCOUNT_ID}/positions"
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                positions = response.json()
                
                # Look for BTC positions
                btc_positions = [p for p in positions if 'BTC' in p.get('symbol', '')]
                
                if btc_positions:
                    # Determine position type
                    for position in btc_positions:
                        if position.get('type') == 'POSITION_TYPE_BUY':
                            last_position = "Buy"
                            print("Found BTC Buy position")
                            return "Buy"
                        elif position.get('type') == 'POSITION_TYPE_SELL':
                            last_position = "Sell"
                            print("Found BTC Sell position")
                            return "Sell"
                
                # No BTC positions found
                last_position = "No Position"
                print("No BTC positions found")
                return "No Position"
        except Exception as e:
            print(f"Error fetching BTC position via API: {e}")
    
    # Simulation mode - generate semi-random position with some persistence
    current_hour = datetime.now().hour
    current_minute = datetime.now().minute
    
    # Change position roughly every 5 minutes based on time
    position_seed = (current_hour * 60 + current_minute) // 5
    random.seed(position_seed)
    position_rand = random.random()
    
    if position_rand < 0.4:  # 40% chance of Buy
        simulated_position = "Buy"
    elif position_rand < 0.7:  # 30% chance of Sell
        simulated_position = "Sell"
    else:  # 30% chance of No Position
        simulated_position = "No Position"
    
    if simulated_position != last_position:
        last_position = simulated_position
        print(f"Using simulated position: {simulated_position}")
    
    return simulated_position

# Route for main page
@app.route('/')
def index():
    # Get real BTC position from MetaAPI
    btc_position = get_btc_position()
    
    # Add a status message to indicate whether we're using real data or simulation
    status = "LIVE DATA" if meta_api_ready else "SIMULATION MODE"
    
    return render_template('index.html', btc_position=btc_position, status=status)

# API endpoint for updating chart data
@app.route('/update-data')
def update_data():
    # Fetch BTC price from Binance
    btc_price = fetch_btc_price()
    
    # Get real MT5 equity from MetaAPI
    equity = get_mt5_equity()
    
    # Get real BTC position from MetaAPI
    btc_position = get_btc_position()
    
    # Position color mapping
    position_color = {
        "Buy": "#4CAF50",  # Green
        "Sell": "#F44336",  # Red
        "No Position": "#9E9E9E"  # Grey
    }.get(btc_position, "#9E9E9E")
    
    # Current timestamp
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # API status message
    api_status = "LIVE MT5 DATA" if meta_api_ready else "SIMULATION MODE"
    
    return jsonify({
        'btc_price': btc_price,
        'equity': equity,
        'position': btc_position,
        'position_color': position_color,
        'graph': "{}",  # Empty placeholder, we build charts client-side now
        'timestamp': current_time,
        'api_status': api_status
    })

# Endpoint for BTC price only (fast updates - every 1 second)
@app.route('/btc-price')
def btc_price_endpoint():
    # Fetch BTC price from Binance
    btc_price = fetch_btc_price()
    
    return jsonify({
        'btc_price': btc_price
    })

# Endpoint for MT5 data only (slower updates - every 3 seconds)
@app.route('/mt5-data')
def mt5_data_endpoint():
    # Get real MT5 equity from MetaAPI
    equity = get_mt5_equity()
    
    # Get real BTC position from MetaAPI
    btc_position = get_btc_position()
    
    # Position color mapping
    position_color = {
        "Buy": "#4CAF50",  # Green
        "Sell": "#F44336",  # Red
        "No Position": "#9E9E9E"  # Grey
    }.get(btc_position, "#9E9E9E")
    
    # API status message
    api_status = "LIVE MT5 DATA" if meta_api_ready else "SIMULATION MODE"
    
    return jsonify({
        'equity': equity,
        'position': btc_position,
        'position_color': position_color,
        'api_status': api_status
    })

# Route for historical data view - simplified for Vercel
@app.route('/history')
def history():
    return render_template('history.html')

# For local development
if __name__ == "__main__":
    app.run(debug=True)
