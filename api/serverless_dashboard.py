import json
import os
import requests
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API URLs and configuration from environment variables
BINANCE_API_URL = os.getenv('BINANCE_API_URL', 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
BINANCE_KLINE_URL = 'https://api.binance.com/api/v3/klines'

# Create Flask app
app = Flask(__name__, 
            template_folder='../templates',  # Adjust template path for Vercel deployment
            static_folder='../static',      # Adjust static path for Vercel deployment
            static_url_path='/static')     # Explicit static URL path for Vercel

# Store last fetched data in memory (note: this will reset between function invocations)
last_btc_price = 0
last_equity = 10000  # Simulated starting value
btc_position = "No Position"

# Function to fetch BTC price
def fetch_btc_price():
    try:
        response = requests.get(BINANCE_API_URL)
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Error fetching BTC price: {e}")
        return last_btc_price if last_btc_price else 0

# Function to get historical BTC price data directly from Binance
def fetch_historical_btc_data(timeframe='5h'):
    # Map timeframe string to milliseconds
    timeframe_map = {
        '1h': 60 * 60 * 1000,
        '3h': 3 * 60 * 60 * 1000,
        '5h': 5 * 60 * 60 * 1000,
        '12h': 12 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
        '3d': 3 * 24 * 60 * 60 * 1000,
        '7d': 7 * 24 * 60 * 60 * 1000
    }
    
    # Calculate start time based on timeframe
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = end_time - timeframe_map.get(timeframe, timeframe_map['5h'])
    
    # Determine appropriate interval
    if timeframe in ['1h', '3h', '5h']:
        interval = '1m'  # 1-minute candles for shorter timeframes
    elif timeframe in ['12h', '1d']:
        interval = '5m'  # 5-minute candles for medium timeframes
    else:
        interval = '15m'  # 15-minute candles for longer timeframes
    
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

# Function to simulate MT5 equity data
def simulate_mt5_equity_data(timeframe='5h', btc_data=None):
    if not btc_data:
        return []
    
    # Use BTC data as a base and add some variation
    equity_data = []
    base_equity = 10000
    
    for i, btc_point in enumerate(btc_data):
        # Create a simulation where equity follows BTC price with some lag and variation
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
            btc_change = (btc_price - first_btc) / first_btc  # Percentage change from first point
            
            # Add randomness and lag to make it look more realistic
            import random
            random_factor = random.uniform(0.8, 1.2)
            lag_factor = 0.85  # Equity responds slower than BTC price
            
            equity = base_equity * (1 + (btc_change * lag_factor * random_factor))
            
            equity_data.append({
                'timestamp': btc_point['timestamp'],
                'equity': equity
            })
    
    return equity_data

# Function to generate plots
def generate_plots(btc_price=None, equity=None, refresh=True):
    if btc_price is None:
        btc_price = fetch_btc_price()
    
    if equity is None:
        # Simulate an equity value that correlates with BTC price
        import random
        base = 10000
        variation = (btc_price % 100) / 10  # Use last 2 digits of BTC price to create variation
        equity = base + (variation * random.uniform(0.8, 1.2) * 100)
    
    # Create subplot with 2 rows
    fig = make_subplots(rows=2, cols=1, 
                        vertical_spacing=0.08,
                        subplot_titles=("BTC Price", "MT5 Account Equity"))
    
    # Add BTC price trace to the first row
    fig.add_trace(
        go.Scatter(
            x=[datetime.now()],
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
            x=[datetime.now()],
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
def generate_historical_plots(timeframe='5h', chart_type='line', interval='5m'):
    # Get historical BTC data directly from Binance
    btc_data = fetch_historical_btc_data(timeframe=timeframe)
    
    # Simulate MT5 equity data based on BTC data
    equity_data = simulate_mt5_equity_data(timeframe=timeframe, btc_data=btc_data)
    
    # Create subplot with 2 rows
    fig = make_subplots(rows=2, cols=1, 
                        vertical_spacing=0.08,
                        subplot_titles=("BTC Price", "MT5 Account Equity"))
    
    # Format timestamps for x-axis
    timestamps = [datetime.fromtimestamp(point['timestamp']) for point in btc_data]
    
    if chart_type == 'candlestick' and len(btc_data) > 0:
        # Group data into candlesticks based on interval
        interval_seconds = {
            '1m': 60,
            '3m': 3 * 60,
            '5m': 5 * 60,
            '15m': 15 * 60,
            '30m': 30 * 60,
            '1h': 60 * 60
        }.get(interval, 300)  # Default to 5 minutes
        
        # For candlestick, we already have OHLC data directly from Binance
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
    return render_template('index.html', btc_position=btc_position)

# Route for historical data view
@app.route('/history')
def history():
    return render_template('history.html')

# API endpoint for updating chart data
@app.route('/update-data')
def update_data():
    global last_btc_price, last_equity, btc_position
    
    # Fetch BTC price from Binance
    btc_price = fetch_btc_price()
    last_btc_price = btc_price  # Update the last known price
    
    # Simulate MT5 equity (varies with BTC price in a realistic way)
    import random
    import math
    base_equity = 10000
    time_component = math.sin(datetime.now().timestamp() / 1800)  # 30-minute cycle
    price_factor = (btc_price % 1000) / 1000  # Use the last 3 digits of BTC price
    
    # Combine factors for a realistic, correlated movement
    equity = base_equity * (1 + (time_component * 0.02) + (price_factor * 0.04))
    last_equity = equity
    
    # Generate a random position occasionally to simulate trading
    if random.random() < 0.05:  # 5% chance of position change
        positions = ["Buy", "Sell", "No Position"]
        weights = [0.3, 0.2, 0.5]  # Weighted probabilities
        btc_position = random.choices(positions, weights=weights, k=1)[0]
    
    # Create position color mapping
    position_color = {
        "Buy": "#4CAF50",  # Green
        "Sell": "#F44336",  # Red
        "No Position": "#9E9E9E"  # Grey
    }.get(btc_position, "#9E9E9E")
    
    # Generate the plot
    graph_json = generate_plots(btc_price=btc_price, equity=equity)
    
    return jsonify({
        'btc_price': btc_price,
        'equity': equity,
        'position': btc_position,
        'position_color': position_color,
        'graph': graph_json,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# API endpoint for getting historical data
@app.route('/historical-data')
def historical_data():
    timeframe = request.args.get('timeframe', '5h')
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
