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

# API URLs
BINANCE_API_URL = os.getenv('BINANCE_API_URL', 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
BINANCE_KLINE_URL = 'https://api.binance.com/api/v3/klines'

# Store last fetched data in memory
last_btc_price = 65000.0  # Default to realistic value (April 2025)

# Function to fetch BTC price
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

# Function to simulate MT5 equity based on BTC price
def simulate_mt5_equity(btc_price):
    # Fixed base equity that doesn't grow without bounds
    base_equity = 10000
    
    # Make equity generally follow BTC trend but with lower volatility
    time_component = math.cos(datetime.now().timestamp() / 3600) * 0.01  # 1-hour cycle
    
    # Use BTC price normalized to a reasonable range (64k-68k)
    # This ensures price changes have the right effect without causing extreme values
    normalized_btc = max(min(btc_price, 68000), 64000)  # Clamp between 64k-68k
    price_factor = ((normalized_btc - 64000) / 4000)  # 0-1 range based on BTC variation
    price_influence = price_factor * 0.02  # Max 2% influence
    
    # Small uptrend based on time - max 1% per day
    # Using seconds since midnight % 86400 gives us a 0-1 daily cycle
    seconds_since_midnight = (datetime.now().timestamp() % 86400) 
    daily_cycle = seconds_since_midnight / 86400  # 0-1 range
    time_uptrend = daily_cycle * 0.01  # 0-1% range
    
    # Combine all factors with limits to prevent extreme values
    change_pct = time_component + price_influence + time_uptrend
    change_pct = max(min(change_pct, 0.05), -0.03)  # Limit to -3% to +5%
    
    equity = base_equity * (1 + change_pct)
    
    # Apply an absolute limit to prevent any possibility of extreme values
    equity = max(min(equity, 12000), 9500)
    
    return round(equity, 2)

# Function to determine BTC position
def simulate_btc_position():
    # Simplified position simulation for Vercel
    positions = ["Buy", "Sell", "No Position"]
    weights = [0.3, 0.2, 0.5]  # Weighted probabilities
    
    # Use time-based seed for consistency (changes every 5 minutes)
    position_seed = int(datetime.now().minute / 5)
    random.seed(position_seed)
    
    # Make more Buy signals when BTC price is rising, more Sell when falling
    hour_of_day = datetime.now().hour
    if 8 <= hour_of_day <= 16:  # During typical trading hours
        # Adjust weights to favor Buy during trading hours
        weights = [0.4, 0.1, 0.5]
    
    return random.choices(positions, weights=weights, k=1)[0]

# Route for main page
@app.route('/')
def index():
    btc_position = simulate_btc_position()
    return render_template('index.html', btc_position=btc_position)

# API endpoint for updating chart data
@app.route('/update-data')
def update_data():
    # Fetch BTC price from Binance
    btc_price = fetch_btc_price()
    
    # Simulate MT5 equity
    equity = simulate_mt5_equity(btc_price)
    
    # Simulate a BTC position
    btc_position = simulate_btc_position()
    
    # Position color mapping
    position_color = {
        "Buy": "#4CAF50",  # Green
        "Sell": "#F44336",  # Red
        "No Position": "#9E9E9E"  # Grey
    }.get(btc_position, "#9E9E9E")
    
    # Current timestamp
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({
        'btc_price': btc_price,
        'equity': equity,
        'position': btc_position,
        'position_color': position_color,
        'graph': "{}",  # Empty placeholder, we build charts client-side now
        'timestamp': current_time
    })

# Route for historical data view - simplified for Vercel
@app.route('/history')
def history():
    return render_template('history.html')

# For local development
if __name__ == "__main__":
    app.run(debug=True)
