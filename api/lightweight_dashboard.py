import json
import os
import requests
import math
import random
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API URLs
BINANCE_API_URL = os.getenv('BINANCE_API_URL', 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
BINANCE_KLINE_URL = 'https://api.binance.com/api/v3/klines'

# Create Flask app
app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static',
            static_url_path='/static')

# Store last fetched data in memory (will reset between function invocations in serverless)
last_btc_price = 0
positions = ["Buy", "Sell", "No Position"]
position_weights = [0.3, 0.2, 0.5]  # Weighted probabilities

# Function to fetch BTC price
def fetch_btc_price():
    """Fetch current BTC price from Binance API"""
    global last_btc_price
    try:
        response = requests.get(BINANCE_API_URL)
        data = response.json()
        price = float(data['price'])
        last_btc_price = price  # Update last known price
        return price
    except Exception as e:
        print(f"Error fetching BTC price: {e}")
        # Return last known price if we have one, otherwise a more realistic default
        # Based on current market conditions (≈65k in April 2025)
        return last_btc_price if last_btc_price else 65000.0

# Function to simulate MT5 equity based on BTC price
def simulate_mt5_equity(btc_price):
    """Generate simulated MT5 equity value correlated with BTC price"""
    # Fixed base equity that doesn't grow without bounds
    base_equity = 10000
    
    # Make equity generally follow BTC trend but with lower volatility
    time_component = math.cos(datetime.now().timestamp() / 3600) * 0.01  # 1-hour cycle
    
    # Normalize BTC price to a reasonable range (64k-68k)
    # This ensures price changes have the right effect without causing extreme values
    normalized_btc = max(min(btc_price, 68000), 64000)  # Clamp between 64k-68k
    price_factor = ((normalized_btc - 64000) / 4000)  # 0-1 range based on BTC variation
    price_influence = price_factor * 0.02  # Max 2% influence
    
    # Small uptrend based on time - max 1% per day
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

# Function to determine BTC position based on price movement
def simulate_btc_position():
    """Determine BTC position based on recent price movement"""
    try:
        # Get recent BTC prices to determine trend
        params = {
            'symbol': 'BTCUSDT',
            'interval': '1m',  # 1-minute candles
            'limit': 10  # Look at 10 recent candles for better trend identification
        }
        response = requests.get(BINANCE_KLINE_URL, params=params)
        data = response.json()
        
        if len(data) >= 5:
            # Extract closing prices from the candles
            closes = [float(candle[4]) for candle in data]
            
            # Calculate trend using simple moving averages
            short_ma = sum(closes[-3:]) / 3  # 3-period MA
            long_ma = sum(closes[-8:]) / 8   # 8-period MA
            
            # Calculate price momentum
            momentum = (closes[-1] / closes[-5] - 1) * 100  # 5-period price change %
            
            # Determine position based on MA crossover and momentum
            # This will create a more consistent trading signal
            current_minute = int(datetime.now().minute)
            
            # Use a combination of current minute and price to ensure position consistency
            # This ensures same position for a reasonable time period
            position_seed = int(current_minute / 5)  # Changes every 5 minutes
            random.seed(position_seed + int(closes[-1]) % 10)  # Add some price influence
            
            if short_ma > long_ma and momentum > 0.1:
                # Strong uptrend - high chance of Buy
                position = random.choices(positions, weights=[0.85, 0.05, 0.1], k=1)[0]
            elif short_ma < long_ma and momentum < -0.1:
                # Strong downtrend - high chance of Sell
                position = random.choices(positions, weights=[0.05, 0.85, 0.1], k=1)[0]
            else:
                # Sideways or unclear trend
                position = random.choices(positions, weights=[0.25, 0.25, 0.5], k=1)[0]
            
            # Reset random seed
            random.seed()
            return position
            
    except Exception as e:
        print(f"Error determining position: {e}")
    
    # Default to No Position if we couldn't determine a trend
    return "No Position"

# Function to get historical BTC data from Binance
def fetch_historical_btc_data(timeframe='5h'):
    """Fetch historical BTC price data directly from Binance API"""
    # Map timeframe string to milliseconds
    timeframe_map = {
        '1': 60 * 60 * 1000,        # 1 hour
        '3': 3 * 60 * 60 * 1000,    # 3 hours
        '5': 5 * 60 * 60 * 1000,    # 5 hours
        '12': 12 * 60 * 60 * 1000,  # 12 hours
        '24': 24 * 60 * 60 * 1000,  # 24 hours
        '72': 3 * 24 * 60 * 60 * 1000,  # 3 days
        '168': 7 * 24 * 60 * 60 * 1000,  # 7 days
    }
    
    # Calculate start time based on timeframe
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = end_time - timeframe_map.get(timeframe, timeframe_map['5'])
    
    # Determine appropriate interval
    if timeframe in ['1', '3', '5']:
        interval = '1m'  # 1-minute candles
    elif timeframe in ['12', '24']:
        interval = '5m'  # 5-minute candles
    else:
        interval = '15m'  # 15-minute candles
    
    # Fetch data from Binance
    params = {
        'symbol': 'BTCUSDT',
        'interval': interval,
        'startTime': start_time,
        'endTime': end_time,
        'limit': 1000
    }
    
    try:
        response = requests.get(BINANCE_KLINE_URL, params=params)
        data = response.json()
        
        # Transform data to the format we need
        btc_data = []
        for candle in data:
            # Binance kline format: [Open time, Open, High, Low, Close, Volume, Close time, ...]
            timestamp = candle[0] / 1000  # Convert from milliseconds to seconds
            open_price = float(candle[1])
            high_price = float(candle[2])
            low_price = float(candle[3])
            close_price = float(candle[4])
            
            btc_data.append({
                'timestamp': timestamp,
                'price': close_price,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price
            })
        
        return btc_data
    except Exception as e:
        print(f"Error fetching historical BTC data: {e}")
        return []

# Function to simulate MT5 equity data based on BTC data
def simulate_mt5_equity_data(btc_data):
    """Generate simulated MT5 equity data correlated with BTC price data"""
    if not btc_data:
        return []
    
    # Use BTC data as a base and add some variation
    equity_data = []
    base_equity = 10000
    
    for i, btc_point in enumerate(btc_data):
        # Create a simulation where equity follows BTC price with lag and variation
        btc_price = btc_point['price']
        # Normalize BTC price to a percentage change from first point
        if i == 0:
            first_btc = btc_price
            equity_data.append({
                'timestamp': btc_point['timestamp'],
                'equity': base_equity
            })
        else:
            # Simulate equity based on BTC price with some noise
            btc_change = (btc_price - first_btc) / first_btc  # Percentage change
            random_factor = random.uniform(0.8, 1.2)
            lag_factor = 0.85  # Equity responds slower than BTC price
            
            equity = base_equity * (1 + (btc_change * lag_factor * random_factor))
            
            equity_data.append({
                'timestamp': btc_point['timestamp'],
                'equity': round(equity, 2)
            })
    
    return equity_data

# Function to generate live plots
def generate_plots(btc_price=None, equity=None):
    """Generate plots for the main dashboard"""
    if btc_price is None:
        btc_price = fetch_btc_price()
    
    if equity is None:
        equity = simulate_mt5_equity(btc_price)
    
    # Create subplot with 2 rows
    fig = make_subplots(rows=2, cols=1, 
                        vertical_spacing=0.08,
                        subplot_titles=("BTC Price", "MT5 Account Equity"))
    
    current_time = datetime.now()
    
    # Add BTC price trace to the first row
    fig.add_trace(
        go.Scatter(
            x=[current_time],
            y=[btc_price],
            mode='lines',
            name='BTC Price',
            line=dict(width=2, color='#F2A900')
        ),
        row=1, col=1
    )
    
    # Add equity trace to the second row
    fig.add_trace(
        go.Scatter(
            x=[current_time],
            y=[equity],
            mode='lines',
            name='MT5 Equity',
            line=dict(width=2, color='#3D9970')
        ),
        row=2, col=1
    )
    
    # Update layout
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#121212",
        plot_bgcolor="#121212",
        font=dict(color="white"),
        height=700,
        margin=dict(l=50, r=30, t=50, b=50),
        showlegend=False
    )
    
    # Update y-axes
    price_range = btc_price * 0.005  # 0.5% range around current price
    fig.update_yaxes(title_text="Price (USDT)", row=1, col=1, 
                     range=[btc_price - price_range, btc_price + price_range])
    
    equity_range = equity * 0.05  # 5% range around current equity
    fig.update_yaxes(title_text="Equity (USD)", row=2, col=1,
                     range=[equity - equity_range, equity + equity_range])
    
    # Generate the plot
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

# Function to generate historical plots
def generate_historical_plots(timeframe='5', chart_type='line', interval='5m'):
    """Generate historical data plots"""
    # Get historical BTC data from Binance
    btc_data = fetch_historical_btc_data(timeframe=timeframe)
    
    # Simulate MT5 equity data based on BTC data
    equity_data = simulate_mt5_equity_data(btc_data)
    
    # Create subplot with 2 rows
    fig = make_subplots(rows=2, cols=1, 
                        vertical_spacing=0.08,
                        subplot_titles=("BTC Price", "MT5 Account Equity"))
    
    # Format timestamps for x-axis
    timestamps = [datetime.fromtimestamp(point['timestamp']) for point in btc_data]
    
    if chart_type == 'candlestick' and len(btc_data) > 0:
        # For candlestick chart, we already have OHLC data from Binance
        open_prices = [point['open'] for point in btc_data]
        high_prices = [point['high'] for point in btc_data]
        low_prices = [point['low'] for point in btc_data]
        close_prices = [point['close'] for point in btc_data]
        
        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=timestamps,
                open=open_prices,
                high=high_prices,
                low=low_prices,
                close=close_prices,
                name='BTC Price',
                increasing_line_color='#26A69A',
                decreasing_line_color='#EF5350'
            ),
            row=1, col=1
        )
    else:
        # Regular line chart for BTC price
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=[point['price'] for point in btc_data],
                mode='lines',
                name='BTC Price',
                line=dict(width=2, color='#F2A900'),
                fill='tozeroy',
                fillcolor='rgba(242, 169, 0, 0.1)'
            ),
            row=1, col=1
        )
    
    # Add equity trace to the second row
    fig.add_trace(
        go.Scatter(
            x=[datetime.fromtimestamp(point['timestamp']) for point in equity_data],
            y=[point['equity'] for point in equity_data],
            mode='lines',
            name='MT5 Equity',
            line=dict(width=2, color='#3D9970'),
            fill='tozeroy',
            fillcolor='rgba(61, 153, 112, 0.1)'
        ),
        row=2, col=1
    )
    
    # Update layout for a dark theme
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#121212",
        plot_bgcolor="#121212",
        font=dict(color="white"),
        height=800,
        margin=dict(l=50, r=30, t=50, b=50),
        showlegend=False,
        xaxis=dict(
            rangeslider=dict(visible=False),
            type='date'
        ),
        xaxis2=dict(
            rangeslider=dict(visible=False),
            type='date'
        )
    )
    
    # Update y-axes
    if btc_data:
        btc_prices = [point['price'] for point in btc_data]
        btc_min = min(btc_prices) * 0.999
        btc_max = max(btc_prices) * 1.001
        fig.update_yaxes(title_text="Price (USDT)", row=1, col=1, range=[btc_min, btc_max])
    
    if equity_data:
        equity_values = [point['equity'] for point in equity_data]
        equity_min = min(equity_values) * 0.995
        equity_max = max(equity_values) * 1.005
        fig.update_yaxes(title_text="Equity (USD)", row=2, col=1, range=[equity_min, equity_max])
    
    # Generate the plot
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

# Route for main page
@app.route('/')
def index():
    btc_position = simulate_btc_position()
    return render_template('index.html', btc_position=btc_position)

# Route for historical data view
@app.route('/history')
def history():
    return render_template('history.html')

# API endpoint for updating chart data
@app.route('/update-data')
def update_data():
    global last_btc_price
    
    # Fetch BTC price from Binance
    btc_price = fetch_btc_price()
    last_btc_price = btc_price  # Update the last known price
    
    # Simulate MT5 equity
    equity = simulate_mt5_equity(btc_price)
    
    # Simulate a BTC position
    btc_position = simulate_btc_position()
    
    # Create position color mapping
    position_color = {
        "Buy": "#4CAF50",  # Green
        "Sell": "#F44336",  # Red
        "No Position": "#9E9E9E"  # Grey
    }.get(btc_position, "#9E9E9E")
    
    # We don't need to generate the plot anymore as we'll build it client-side
    # This is just here for backwards compatibility
    graph_json = "{}"
    
    # Get current timestamp formatted for display
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({
        'btc_price': btc_price,
        'equity': equity,
        'position': btc_position,
        'position_color': position_color,
        'graph': graph_json,  # Empty placeholder, not used anymore
        'timestamp': current_time
    })

# API endpoint for getting historical data
@app.route('/historical-data')
def historical_data():
    timeframe = request.args.get('timeframe', '5')
    chart_type = request.args.get('chart_type', 'line')
    interval = request.args.get('interval', '5m')
    
    # Generate the historical plots
    graph_json = generate_historical_plots(
        timeframe=timeframe,
        chart_type=chart_type,
        interval=interval
    )
    
    return jsonify({
        'graph': graph_json,
        'timeframe': timeframe,
        'chart_type': chart_type,
        'interval': interval,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# For local development
if __name__ == '__main__':
    app.run(debug=True)
