// Netlify serverless function to proxy requests to our Flask app
const serverless = require('serverless-http');
const express = require('express');
const { app } = require('../../api/index');

// Create serverless handler
const handler = serverless(app);

module.exports = { handler };
