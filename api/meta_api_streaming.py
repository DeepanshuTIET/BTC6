import os
import asyncio
from metaapi_cloud_sdk import MetaApi
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger('meta_api_streaming')

class MetaApiStreamingManager:
    def __init__(self, token=None, account_id=None):
        """Initialize the MetaAPI Streaming Manager.
        
        Args:
            token (str): MetaAPI token. If None, reads from environment variable.
            account_id (str): MetaAPI account ID. If None, reads from environment variable.
        """
        self.token = token or os.getenv('META_API_KEY')
        self.account_id = account_id or os.getenv('META_ACCOUNT_ID')
        self.api = None
        self.account = None
        self.connection = None
        self.is_connected = False
        self.is_synchronized = False
        self.is_connecting = False
        self.last_connection_attempt = 0
        self.reconnect_interval = 30  # seconds

    async def initialize(self):
        """Initialize the API client."""
        if not self.api:
            self.api = MetaApi(self.token)
            logger.info("MetaAPI client initialized")
        return self.api

    async def get_account(self):
        """Get the MetaTrader account."""
        if not self.account:
            try:
                self.api = await self.initialize()
                self.account = await self.api.metatrader_account_api.get_account(self.account_id)
                logger.info(f"Connected to account ID: {self.account_id}")
            except Exception as e:
                logger.error(f"Error connecting to account: {e}")
                raise
        return self.account

    async def ensure_deployed(self):
        """Ensure the account is deployed and ready to use."""
        account = await self.get_account()
        initial_state = account.state
        deployed_states = ['DEPLOYING', 'DEPLOYED']

        if initial_state not in deployed_states:
            logger.info('Deploying account...')
            await account.deploy()
            logger.info('Account deployed')

        return account

    async def connect_streaming(self, wait_for_sync=True):
        """Connect to the streaming API.
        
        Args:
            wait_for_sync (bool): Whether to wait for terminal state synchronization.
            
        Returns:
            connection: The streaming connection object.
        """
        current_time = time.time()
        
        # Prevent multiple concurrent connection attempts
        if self.is_connecting:
            return self.connection
            
        # Rate limit reconnection attempts
        if current_time - self.last_connection_attempt < self.reconnect_interval and self.connection:
            return self.connection
            
        self.is_connecting = True
        self.last_connection_attempt = current_time
        
        try:
            account = await self.ensure_deployed()
            
            logger.info('Waiting for API server to connect to broker...')
            await account.wait_connected()
            
            # Connect to MetaApi API
            if not self.connection:
                self.connection = account.get_streaming_connection()
                
            if not self.is_connected:
                await self.connection.connect()
                self.is_connected = True
                logger.info('Connected to streaming API')
            
            # Wait for synchronization if requested
            if wait_for_sync and not self.is_synchronized:
                logger.info('Waiting for terminal state synchronization...')
                await self.connection.wait_synchronized()
                self.is_synchronized = True
                logger.info('Terminal state synchronized')
                
            return self.connection
            
        except Exception as e:
            logger.error(f"Error in connect_streaming: {e}")
            raise
        finally:
            self.is_connecting = False
            
    async def get_account_information(self):
        """Get account information from the streaming connection.
        
        Returns:
            dict: Account information.
        """
        try:
            connection = await self.connect_streaming()
            terminal_state = connection.terminal_state
            return terminal_state.account_information
        except Exception as e:
            logger.error(f"Error getting account information: {e}")
            return None
            
    async def get_positions(self):
        """Get open positions from the streaming connection.
        
        Returns:
            list: List of open positions.
        """
        try:
            connection = await self.connect_streaming()
            terminal_state = connection.terminal_state
            return terminal_state.positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
            
    async def get_orders(self):
        """Get pending orders from the streaming connection.
        
        Returns:
            list: List of pending orders.
        """
        try:
            connection = await self.connect_streaming()
            terminal_state = connection.terminal_state
            return terminal_state.orders
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
            
    async def get_symbol_price(self, symbol):
        """Get current price for a symbol.
        
        Args:
            symbol (str): Symbol to get price for, e.g. 'BTCUSD'
            
        Returns:
            dict: Symbol price information.
        """
        try:
            connection = await self.connect_streaming()
            terminal_state = connection.terminal_state
            
            # Subscribe to market data if not already subscribed
            try:
                await connection.subscribe_to_market_data(symbol)
            except Exception as e:
                if "already subscribed" not in str(e).lower():
                    logger.warning(f"Subscription error for {symbol}: {e}")
            
            return terminal_state.price(symbol)
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
            
    async def get_historical_deals(self, days=1):
        """Get historical deals for the specified time period.
        
        Args:
            days (int): Number of days to look back.
            
        Returns:
            list: List of historical deals.
        """
        try:
            connection = await self.connect_streaming()
            history_storage = connection.history_storage
            
            start_time = datetime.now() - timedelta(days=days)
            end_time = datetime.now()
            
            return history_storage.get_deals_by_time_range(start_time, end_time)
        except Exception as e:
            logger.error(f"Error getting historical deals: {e}")
            return []
            
    async def calculate_margin(self, order_params):
        """Calculate margin required for a trade.
        
        Args:
            order_params (dict): Order parameters including symbol, type, volume, and openPrice.
            
        Returns:
            dict: Margin calculation result.
        """
        try:
            connection = await self.connect_streaming()
            return await connection.calculate_margin(order_params)
        except Exception as e:
            logger.error(f"Error calculating margin: {e}")
            return None
            
    async def close_connection(self):
        """Close the streaming connection."""
        if self.connection and self.is_connected:
            try:
                await self.connection.close()
                self.is_connected = False
                self.is_synchronized = False
                logger.info("Closed streaming connection")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")

    async def reconnect(self):
        """Reconnect to the streaming API."""
        if self.connection and self.is_connected:
            await self.close_connection()
        
        self.connection = None
        return await self.connect_streaming()
