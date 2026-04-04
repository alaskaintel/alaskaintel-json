import json
import os
import csv
import requests
from datetime import datetime, timezone

# Add csv URL
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
CSV_OUTPUT_PATH = os.path.join("data", "ourairports.csv")

# We will modify the save_data function to include runways
