import logging
import os
from metaapi_cloud_sdk import MetaApi

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('position_tracker')

class PositionTracker:
    def __init__(self):
        self.connection = None
        self.meta_api = None
        self.is_initialized = False
        self.account_id = os.getenv('META_ACCOUNT_ID', '6e26b1d7-0c75-4a5d-ae1f-4059fb8e82f1')
        self.token = os.getenv('TOKEN') or os.getenv('META_API_KEY')
        
    async def initialize(self):
        """Initialize the MetaAPI connection if not already initialized"""
        if self.is_initialized:
            return
            
        try:
            logger.info("Initializing MetaAPI connection")
            self.meta_api = MetaApi(self.token)
            account = await self.meta_api.metatrader_account_api.get_account(self.account_id)
            
            # Check if deployed
            if account.state not in ['DEPLOYING', 'DEPLOYED']:
                logger.info("Account not deployed, deploying now")
                await account.deploy()
                
            # Connect to the account
            logger.info("Waiting for MetaAPI to connect to broker")
            await account.wait_connected()
            
            # Get streaming connection
            self.connection = account.get_streaming_connection()
            await self.connection.connect()
            
            # Wait for synchronization
            logger.info("Waiting for terminal state synchronization")
            await self.connection.wait_synchronized()
            
            self.is_initialized = True
            logger.info("MetaAPI connection successfully initialized")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing MetaAPI connection: {e}")
            if self.meta_api:
                logger.error(self.meta_api.format_error(e))
            return False
    
    async def get_btc_positions(self):
        """Get all BTC positions with detailed information"""
        if not self.is_initialized:
            success = await self.initialize()
            if not success:
                return []
                
        try:
            if self.connection and self.connection.terminal_state:
                # Get positions from terminal state (more accurate than API call)
                positions = self.connection.terminal_state.positions
                btc_keywords = ['BTC', 'BITCOIN', 'XBT', 'BTCUSD', 'XBTUSD']
                btc_positions = [p for p in positions if any(keyword in p['symbol'].upper() for keyword in btc_keywords)]
                return btc_positions
            else:
                logger.warning("Connection or terminal state not available")
                return []
        except Exception as e:
            logger.error(f"Error fetching BTC positions: {e}")
            return []
    
    async def get_position_status(self):
        """Get the current BTC position status (Buy, Sell, or No Position)"""
        positions = await self.get_btc_positions()
        
        if not positions:
            return {
                'status': 'No Position',
                'color': '#999999',
                'details': None
            }
            
        # Get the first BTC position (assuming one position at a time)
        position = positions[0]
        
        if position['type'] == 'POSITION_TYPE_BUY':
            return {
                'status': 'Buy',
                'color': '#00aa00',  # Green for buy
                'details': {
                    'volume': position.get('volume', 0),
                    'profit': position.get('profit', 0),
                    'open_price': position.get('openPrice', 0),
                    'symbol': position.get('symbol', ''),
                    'time': position.get('time', 0),
                    'comment': position.get('comment', ''),
                    'swap': position.get('swap', 0),
                    'margin_rate': position.get('marginRate', 0)
                }
            }
        else:
            return {
                'status': 'Sell',
                'color': '#aa0000',  # Red for sell
                'details': {
                    'volume': position.get('volume', 0),
                    'profit': position.get('profit', 0),
                    'open_price': position.get('openPrice', 0),
                    'symbol': position.get('symbol', ''),
                    'time': position.get('time', 0),
                    'comment': position.get('comment', ''),
                    'swap': position.get('swap', 0),
                    'margin_rate': position.get('marginRate', 0)
                }
            }
    
    async def get_account_information(self):
        """Get account information including balance and equity"""
        if not self.is_initialized:
            success = await self.initialize()
            if not success:
                return None
                
        try:
            if self.connection and self.connection.terminal_state:
                account_info = self.connection.terminal_state.account_information
                return account_info
            else:
                logger.warning("Connection or terminal state not available")
                return None
        except Exception as e:
            logger.error(f"Error fetching account information: {e}")
            return None
            
    async def close_connection(self):
        """Close the MetaAPI connection properly"""
        if self.connection:
            try:
                await self.connection.close()
                logger.info("MetaAPI connection closed")
                self.is_initialized = False
            except Exception as e:
                logger.error(f"Error closing MetaAPI connection: {e}")

# Singleton instance
position_tracker = PositionTracker()
