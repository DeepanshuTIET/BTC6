// Serverless function to fetch MetaAPI account data
const { MetaApi } = require('metaapi.cloud-sdk');

// Maximum time to wait for connection in seconds
const CONNECTION_TIMEOUT = 20;

// Connection pool to reuse between function invocations
let connectionPool = {};

exports.handler = async function(event, context) {
  try {
    // CORS headers
    const headers = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Content-Type': 'application/json'
    };
    
    // Handle preflight OPTIONS request
    if (event.httpMethod === 'OPTIONS') {
      return {
        statusCode: 200,
        headers,
        body: ''
      };
    }
    
    // Only accept POST requests with API credentials
    if (event.httpMethod !== 'POST') {
      return { 
        statusCode: 405, 
        headers, 
        body: JSON.stringify({ error: 'Method not allowed' }) 
      };
    }
    
    // Parse request body
    const requestData = JSON.parse(event.body || '{}');
    const { apiKey, accountId } = requestData;
    
    if (!apiKey || !accountId) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ 
          error: 'Missing required credentials',
          simulation: true,
          // Return simulated data as fallback
          simulatedData: generateSimulatedData()
        })
      };
    }
    
    // Create unique key for this connection
    const connectionKey = `${accountId}`;
    
    // Initialize or reuse MetaAPI connection
    if (!connectionPool[connectionKey]) {
      // Initialize with new connection
      connectionPool[connectionKey] = {
        api: new MetaApi(apiKey),
        lastAccessTime: Date.now(),
        connecting: false
      };
    }
    
    let connection = connectionPool[connectionKey];
    connection.lastAccessTime = Date.now();
    
    // Get account
    if (!connection.account) {
      try {
        connection.account = await connection.api.metatrader_account_api.get_account(accountId);
      } catch (error) {
        console.error('Error connecting to account:', error);
        return {
          statusCode: 500,
          headers,
          body: JSON.stringify({ 
            error: `Error connecting to account: ${error.message}`,
            simulation: true,
            simulatedData: generateSimulatedData()
          })
        };
      }
    }
    
    // Deploy account if needed
    if (connection.account.state !== 'DEPLOYED') {
      await connection.account.deploy();
      // Wait for deployment to complete
      let deploymentTimeout = CONNECTION_TIMEOUT;
      while (connection.account.state !== 'DEPLOYED' && deploymentTimeout > 0) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        deploymentTimeout--;
      }
      
      if (connection.account.state !== 'DEPLOYED') {
        return {
          statusCode: 500,
          headers,
          body: JSON.stringify({ 
            error: 'Account deployment timed out',
            simulation: true,
            simulatedData: generateSimulatedData()
          })
        };
      }
    }
    
    // Create connection to MetaTrader terminal
    if (!connection.mtConnection) {
      connection.mtConnection = connection.account.get_streaming_connection();
    }
    
    // Connect if not connected
    if (!connection.connected) {
      await connection.mtConnection.connect();
      connection.connected = true;
    }
    
    // Wait for synchronization
    if (!connection.synchronized) {
      await connection.mtConnection.wait_synchronized();
      connection.synchronized = true;
    }
    
    // Get account information
    const terminalState = connection.mtConnection.terminal_state;
    const accountInfo = terminalState.account_information;
    
    // Get positions
    const positions = terminalState.positions;
    let btcPosition = null;
    
    // Find BTC position if exists
    for (const position of positions) {
      if (position.symbol.includes('BTC')) {
        btcPosition = {
          symbol: position.symbol,
          type: position.type === 'POSITION_TYPE_BUY' ? 'BUY' : 'SELL',
          volume: position.volume,
          openPrice: position.openPrice,
          currentPrice: position.currentPrice,
          profit: position.profit,
          swap: position.swap,
          commission: position.commission,
          magic: position.magic,
          orderId: position.id
        };
        break;
      }
    }
    
    // Return account data
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        simulation: false,
        accountInfo: {
          balance: accountInfo.balance,
          equity: accountInfo.equity,
          margin: accountInfo.margin,
          freeMargin: accountInfo.freeMargin,
          marginLevel: accountInfo.marginLevel
        },
        btcPosition: btcPosition
      })
    };
    
  } catch (error) {
    console.error('Function error:', error);
    return {
      statusCode: 500,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ 
        error: `Server error: ${error.message}`,
        simulation: true,
        simulatedData: generateSimulatedData()
      })
    };
  }
};

// Generate simulated data if MetaAPI connection fails
function generateSimulatedData() {
  const currentTime = Date.now();
  const btcPrice = 65000 + Math.sin(currentTime/1000) * 1000;
  
  return {
    accountInfo: {
      balance: 723715.34,
      equity: 723248.54,
      margin: 23533.89,
      freeMargin: 699714.65,
      marginLevel: 3073.22
    },
    btcPosition: {
      symbol: 'BTCUSDT',
      type: 'BUY',
      volume: 20.0,
      openPrice: 94135.57,
      currentPrice: 94114.43,
      profit: -422.80,
      swap: 0,
      commission: 0,
      magic: 0,
      orderId: 85229195
    }
  };
}
