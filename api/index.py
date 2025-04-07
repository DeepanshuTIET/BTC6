import os
import sys

# Add the parent directory to sys.path to import modules from the main directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the lightweight version of the dashboard
from api.lightweight_dashboard import app

# For local development
if __name__ == "__main__":
    app.run(debug=True)
