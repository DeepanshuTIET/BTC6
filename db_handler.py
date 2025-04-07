import sqlite3
import time
import pandas as pd
from datetime import datetime, timedelta

class DatabaseHandler:
    def __init__(self, db_path='crypto_dashboard.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.initialize_db()
        
    def connect(self):
        """Establish database connection"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
    
    def initialize_db(self):
        """Initialize database tables if they don't exist"""
        self.connect()
        
        # Create BTC price table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS btc_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            datetime TEXT NOT NULL,
            price REAL NOT NULL
        )
        ''')
        
        # Create MT5 equity table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS mt5_equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            datetime TEXT NOT NULL,
            equity REAL NOT NULL,
            position TEXT
        )
        ''')
        
        # Create index on timestamp for faster queries
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_btc_timestamp ON btc_prices(timestamp)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_mt5_timestamp ON mt5_equity(timestamp)')
        
        self.conn.commit()
        self.disconnect()
    
    def save_btc_price(self, price):
        """Save BTC price to database"""
        self.connect()
        current_time = time.time()
        datetime_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        
        self.cursor.execute(
            'INSERT INTO btc_prices (timestamp, datetime, price) VALUES (?, ?, ?)',
            (current_time, datetime_str, price)
        )
        
        self.conn.commit()
        self.disconnect()
        
    def save_mt5_equity(self, equity, position="No Position"):
        """Save MT5 equity to database"""
        self.connect()
        current_time = time.time()
        datetime_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        
        self.cursor.execute(
            'INSERT INTO mt5_equity (timestamp, datetime, equity, position) VALUES (?, ?, ?, ?)',
            (current_time, datetime_str, equity, position)
        )
        
        self.conn.commit()
        self.disconnect()
    
    def get_btc_data(self, timeframe_hours=5):
        """Get BTC price data for the specified timeframe"""
        self.connect()
        
        # Calculate the timestamp for the start of the timeframe
        start_time = time.time() - (timeframe_hours * 60 * 60)
        
        # Query data after start_time
        self.cursor.execute(
            'SELECT timestamp, price FROM btc_prices WHERE timestamp > ? ORDER BY timestamp',
            (start_time,)
        )
        
        results = self.cursor.fetchall()
        self.disconnect()
        
        if not results:
            return [], []
            
        # Unpack results
        timestamps, prices = zip(*results)
        return list(timestamps), list(prices)
    
    def get_mt5_data(self, timeframe_hours=5):
        """Get MT5 equity data for the specified timeframe"""
        self.connect()
        
        # Calculate the timestamp for the start of the timeframe
        start_time = time.time() - (timeframe_hours * 60 * 60)
        
        # Query data after start_time
        self.cursor.execute(
            'SELECT timestamp, equity, position FROM mt5_equity WHERE timestamp > ? ORDER BY timestamp',
            (start_time,)
        )
        
        results = self.cursor.fetchall()
        self.disconnect()
        
        if not results:
            return [], [], []
            
        # Unpack results
        timestamps, equity_values, positions = zip(*results)
        return list(timestamps), list(equity_values), list(positions)
    
    def get_btc_ohlc(self, timeframe_hours=5, interval_minutes=15):
        """Get BTC OHLC (Open-High-Low-Close) data for TradingView-like charts"""
        self.connect()
        
        # Calculate the timestamp for the start of the timeframe
        start_time = time.time() - (timeframe_hours * 60 * 60)
        
        # Get all price data in the timeframe
        self.cursor.execute(
            'SELECT timestamp, price FROM btc_prices WHERE timestamp > ? ORDER BY timestamp',
            (start_time,)
        )
        
        results = self.cursor.fetchall()
        self.disconnect()
        
        if not results:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(results, columns=['timestamp', 'price'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # Resample to desired interval
        interval = f'{interval_minutes}min'
        ohlc = df.set_index('datetime').resample(interval)['price'].ohlc().dropna()
        
        # Add timestamp column back for Plotly
        ohlc['timestamp'] = ohlc.index.astype(int) // 10**9
        
        return ohlc
    
    def get_btc_prices(self, start_time, end_time):
        """Get BTC price data for the specified time range
        
        Args:
            start_time: datetime object for the start of the range
            end_time: datetime object for the end of the range
            
        Returns:
            List of tuples (timestamp, price)
        """
        self.connect()
        
        # Convert datetime objects to timestamps
        start_timestamp = start_time.timestamp()
        end_timestamp = end_time.timestamp()
        
        # Query data within the time range
        self.cursor.execute(
            'SELECT timestamp, price FROM btc_prices WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp',
            (start_timestamp, end_timestamp)
        )
        
        results = self.cursor.fetchall()
        self.disconnect()
        
        return results
    
    def get_mt5_equity(self, start_time, end_time):
        """Get MT5 equity data for the specified time range
        
        Args:
            start_time: datetime object for the start of the range
            end_time: datetime object for the end of the range
            
        Returns:
            List of tuples (timestamp, equity, position)
        """
        self.connect()
        
        # Convert datetime objects to timestamps
        start_timestamp = start_time.timestamp()
        end_timestamp = end_time.timestamp()
        
        # Query data within the time range
        self.cursor.execute(
            'SELECT timestamp, equity, position FROM mt5_equity WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp',
            (start_timestamp, end_timestamp)
        )
        
        results = self.cursor.fetchall()
        self.disconnect()
        
        return results
        
    def clean_old_data(self, max_days=7):
        """Clean data older than max_days to prevent database bloat"""
        self.connect()
        
        # Calculate cutoff timestamp
        cutoff_time = time.time() - (max_days * 24 * 60 * 60)
        
        # Delete old data
        self.cursor.execute('DELETE FROM btc_prices WHERE timestamp < ?', (cutoff_time,))
        self.cursor.execute('DELETE FROM mt5_equity WHERE timestamp < ?', (cutoff_time,))
        
        # Get number of deleted rows
        deleted_btc = self.cursor.rowcount
        deleted_mt5 = self.cursor.rowcount
        
        self.conn.commit()
        self.disconnect()
        
        return deleted_btc, deleted_mt5
