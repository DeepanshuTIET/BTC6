# Crypto Trading Dashboard

A real-time cryptocurrency trading dashboard that displays BTC price from Binance API and MT5 account equity from MetaAPI, along with position indicators and historical data visualization.

## Features

### Real-time Monitoring
- Live BTC/USDT price chart from Binance API
- MT5 account equity tracking with MetaAPI integration
- Position indicator (Buy/Sell/No Position) with color coding
- Auto-refresh every 1 second for BTC price and 2.5 seconds for MT5 equity

### Historical Data Analysis
- SQLite database for storing historical BTC prices and MT5 equity
- TradingView-like charts for analyzing historical performance
- Multiple timeframe options (1 hour to 7 days)
- Candlestick charts with customizable intervals
- Line charts with area fills for trend visualization

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd BTC6
```

2. Create a virtual environment:

```bash
python -m venv crypto_dashboard_env
```

3. Activate the virtual environment:
   - Windows: 
   ```bash
   crypto_dashboard_env\Scripts\activate
   ```
   - macOS/Linux: 
   ```bash
   source crypto_dashboard_env/bin/activate
   ```

4. Install the required packages:

```bash
pip install -r requirements.txt
```

## Configuration

The dashboard uses environment variables for configuration. Create a `.env` file in the project root with the following variables:

```
# MetaAPI Credentials
META_ACCOUNT_ID=your_meta_account_id
META_API_KEY=your_meta_api_key

# API and Domain Configuration
META_API_DOMAIN=mt-client-api-v1.london.agiliumtrade.ai
BINANCE_API_URL=https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT

# Database Configuration
DB_PATH=crypto_dashboard.db

# Update Intervals (in seconds)
BTC_UPDATE_INTERVAL=1
MT5_UPDATE_INTERVAL=2.5
MAX_DATA_POINTS=120
```

**Note:** The `.env` file is included in the `.gitignore` file to prevent accidentally committing sensitive API keys.

## Running the Dashboard

After setting up your environment variables, run the dashboard with:

```bash
python app.py
```

The dashboard will be accessible at http://127.0.0.1:5000/ in your web browser.

## Using the Dashboard

### Live View

The main dashboard at http://127.0.0.1:5000/ shows:

- Real-time BTC price chart (top)
- MT5 account equity chart (bottom)
- Current BTC position indicator (Buy/Sell/No Position)

### Historical Data View

Access the historical data visualization at http://127.0.0.1:5000/history, which provides:

1. **Timeframe Selection**:
   - 1 Hour
   - 3 Hours
   - 5 Hours (default)
   - 12 Hours
   - 24 Hours
   - 3 Days
   - 7 Days

2. **Chart Types**:
   - Line Chart: Simple visualization of price and equity trends
   - Candlestick Chart: TradingView-like OHLC representation with customizable intervals (1min to 1hour)

## Database Management

The application automatically:

- Stores BTC price and MT5 equity data in an SQLite database
- Cleans old data (older than 7 days) once per day to prevent database bloat

## Additional Information

- The dashboard displays the most recent data points in the live view for smooth performance
- Error handling is implemented to ensure the dashboard continues running even if there are temporary connection issues
- The historical data view requires some data collection time before meaningful charts can be displayed
