import requests
import json
import sys
import os
from pathlib import Path


def load_config():
    """Load configuration from config.json file."""
    config_path = Path(__file__).parent / 'config.json'
    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        print("Please create config.json from config.json.example")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = json.load(f)

    # Validate required fields
    if not config.get('bearer_token'):
        print("Error: bearer_token not found in config.json")
        sys.exit(1)

    return config


def get_bearer_token(config):
    url = f'https://sf-api-token-service.itunes.apple.com/apiToken?clientClass=apple&clientId=com.apple.podcasts.macos&os=OS%20X&osVersion=15.5&productVersion=1.1.0&version=2'
    bearer_token = requests.get(url, headers={
       'x-request-timestamp': config['timestamp'],
       'X-Apple-ActionSignature': config['signature'],
       'X-Apple-Store-Front': '143441-1,42 t:podcasts1',
    }).json()['token']
    return bearer_token


def fetch_transcript(bearer_token, podcast_id, output_file=None):
    """
    Fetch a podcast transcript TTML file.

    Args:
        podcast_id: The Apple Podcasts episode ID (ZSTORETRACKID)
        output_file: Optional output filename. If not specified, uses the filename from ttmlToken

    Returns:
        The path to the downloaded TTML file
    """
    print(f'Fetching transcript for episode ID: {podcast_id}')

    # Request transcript metadata
    url = f'https://amp-api.podcasts.apple.com/v1/catalog/us/podcast-episodes/{podcast_id}/transcripts?fields=ttmlToken,ttmlAssetUrls&include%5Bpodcast-episodes%5D=podcast&l=en-US&with=entitlements'

    try:
        response = requests.get(url, headers={
            'Authorization': f'Bearer {bearer_token}',
        })
        response.raise_for_status()
        attributes = response.json()['data'][0]['attributes']
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"Error fetching transcript metadata: {e}")
        sys.exit(1)

    # Determine output filename
    if output_file is None:
        output_file = attributes['ttmlToken'].split('/')[-1]

    # Download TTML file
    ttml_url = attributes['ttmlAssetUrls']['ttml']
    print(f'Downloading TTML from: {ttml_url}')

    try:
        with requests.get(ttml_url, stream=True) as r:
            r.raise_for_status()
            with open(output_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        print(f'Transcript saved to: {output_file}')
        return output_file
    except requests.RequestException as e:
        print(f"Error downloading TTML file: {e}")
        sys.exit(1)


if __name__ == '__main__':
    # Example usage
    podcast_id = 1000714478537
    config = load_config()
    fetch_transcript(config['bearer_token'], podcast_id)
