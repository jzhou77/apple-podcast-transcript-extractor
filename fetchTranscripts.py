import requests
import json
import sys
import os
from pathlib import Path

# Load configuration
config_path = Path(__file__).parent / 'config.json'
if not config_path.exists():
    print(f"Error: Configuration file not found at {config_path}")
    print("Please create config.json from config.json.example")
    sys.exit(1)

with open(config_path, 'r') as f:
    config = json.load(f)

# Extract credentials from config
timestamp = config.get('timestamp')
signature = config.get('signature')
bearer_token = config.get('bearer_token')

# Configuration for the podcast to download
podcast_id = 1000714478537

# Validate required fields
if not bearer_token:
    print("Error: bearer_token not found in config.json")
    sys.exit(1)

print(f'Bearer Token: {bearer_token}\n')

url = f'https://amp-api.podcasts.apple.com/v1/catalog/us/podcast-episodes/{podcast_id}/transcripts?fields=ttmlToken,ttmlAssetUrls&include%5Bpodcast-episodes%5D=podcast&l=en-US&with=entitlements'
attributes = requests.get(url, headers={
  'Authorization': f'Bearer {bearer_token}',
}).json()['data'][0]['attributes']

with requests.get(attributes['ttmlAssetUrls']['ttml'], stream=True) as r:
  r.raise_for_status()
  with open(attributes['ttmlToken'].split('/')[-1], "wb") as f:
    for chunk in r.iter_content(chunk_size=8192):
      if chunk:
        f.write(chunk)