# Crypto Trading Dashboard

A real-time dashboard that displays BTC price from Binance API and MT5 account equity from MetaAPI, along with position indicators.

## Features

- Real-time BTC/USDT price chart from Binance
- MT5 account equity tracking
- Position indicator (Buy/Sell/No Position) with color coding
- Auto-refresh every 10 seconds

## Installation

1. Create a virtual environment:

```bash
python -m venv crypto_dashboard_env
```

2. Activate the virtual environment:
   - Windows: 
   ```bash
   crypto_dashboard_env\Scripts\activate
   ```
   - macOS/Linux: 
   ```bash
   source crypto_dashboard_env/bin/activate
   ```

3. Install the required packages:

```bash
pip install -r requirements.txt
```

## Configuration

Before running the dashboard, you need to update the following credentials in `dashboard.py`:

1. Binance API credentials:
   - `BINANCE_API_KEY`
   - `BINANCE_API_SECRET`

2. MetaAPI credentials:
   - `META_ACCOUNT_ID` (already set)
   - `META_API_KEY` (already set)

**Note:** For security, consider using environment variables instead of hardcoding API keys.

## Running the Dashboard

After setting up your API keys, run the dashboard with:

```bash
python dashboard.py
```

The dashboard will be accessible at http://127.0.0.1:8050/ in your web browser.

## Additional Information

- The dashboard stores the last 100 data points to show trends
- Error handling is implemented to ensure the dashboard continues running even if there are temporary connection issues
- You can modify the refresh interval by changing the `interval` parameter in the `dcc.Interval` component
