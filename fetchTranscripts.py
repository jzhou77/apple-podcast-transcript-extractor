import requests
import json
import sys
import os
import argparse
import sqlite3
import re
from pathlib import Path
from datetime import datetime
from podcast_db import query_all_episodes_for_show, query_show_info


def load_config():
    """Load configuration from config.json file."""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        print("Please create config.json from config.json.example")
        sys.exit(1)

    with open(config_path, "r") as f:
        config = json.load(f)

    # Validate required fields
    if not config.get("bearer_token"):
        print("Error: bearer_token not found in config.json")
        sys.exit(1)

    return config


def get_bearer_token(config):
    url = f"https://sf-api-token-service.itunes.apple.com/apiToken?clientClass=apple&clientId=com.apple.podcasts.macos&os=OS%20X&osVersion=15.5&productVersion=1.1.0&version=2"
    bearer_token = requests.get(
        url,
        headers={
            "x-request-timestamp": config["timestamp"],
            "X-Apple-ActionSignature": config["signature"],
            "X-Apple-Store-Front": "143441-1,42 t:podcasts1",
        },
    ).json()["token"]
    return bearer_token


def sanitize_filename(filename):
    """Replace invalid filesystem characters and limit length."""
    filename = re.sub(r'[<>:"/\\|?*]', "-", filename)
    filename = re.sub(r"\s+", " ", filename)
    filename = filename.strip()
    return filename[:200]  # Limit length to avoid filesystem issues



def fetch_transcript(bearer_token, podcast_id, output_file=None, verbose=True):
    """
    Fetch a podcast transcript TTML file.

    Args:
        bearer_token: Bearer token for authentication
        podcast_id: The Apple Podcasts episode ID (ZSTORETRACKID)
        output_file: Optional output filename. If not specified, uses the filename from ttmlToken
        verbose: Whether to print progress messages

    Returns:
        The path to the downloaded TTML file

    Raises:
        Exception: If transcript cannot be fetched or downloaded
    """
    if verbose:
        print(f"  Fetching transcript for episode ID: {podcast_id}")

    # Request transcript metadata
    url = f"https://amp-api.podcasts.apple.com/v1/catalog/us/podcast-episodes/{podcast_id}/transcripts?fields=ttmlToken,ttmlAssetUrls&include%5Bpodcast-episodes%5D=podcast&l=en-US&with=entitlements"

    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {bearer_token}",
            },
        )
        response.raise_for_status()
        attributes = response.json()["data"][0]["attributes"]
    except (requests.RequestException, KeyError, IndexError) as e:
        raise Exception(f"Error fetching transcript metadata: {e}")

    # Determine output filename
    if output_file is None:
        output_file = attributes["ttmlToken"].split("/")[-1]

    # Download TTML file
    ttml_url = attributes["ttmlAssetUrls"]["ttml"]
    if verbose:
        print(f"  Downloading TTML from: {ttml_url}")

    try:
        with requests.get(ttml_url, stream=True) as r:
            r.raise_for_status()
            with open(output_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        if verbose:
            print(f"  Transcript saved to: {output_file}")
        return output_file
    except requests.RequestException as e:
        raise Exception(f"Error downloading TTML file: {e}")


def download_show_transcripts(store_collection_id, output_dir, db_path):
    """
    Download all transcripts for a podcast show.

    Args:
        store_collection_id: The podcast's store collection ID
        output_dir: Directory to save transcript files
        db_path: Path to the Apple Podcasts database
    """
    # Load config and get bearer token
    config = load_config()
    bearer_token = config["bearer_token"]

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Connect to database
    db = sqlite3.connect(db_path)

    # Get show information
    show = query_show_info(db, store_collection_id)
    if show:
        print(f"Downloading transcripts for: {show['podcast_title']}")
        print(f"Author: {show['author']}\n")
    else:
        print(f"Error: Could not find show with ID {store_collection_id}")
        db.close()
        sys.exit(1)

    # Get all episodes for the show
    episodes = query_all_episodes_for_show(db, store_collection_id)
    db.close()

    if not episodes:
        print(f"No episodes found for show {store_collection_id}")
        return

    print(f"Found {len(episodes)} episodes\n")

    # Download transcript for each episode
    success_count = 0
    fail_count = 0

    for i, episode in enumerate(episodes, 1):
        episode_id = episode["episode_id"]
        episode_title = episode["episode_title"]
        pub_date = episode["pub_date"]

        # Convert Apple's Core Data timestamp to Unix timestamp
        # Apple uses 2001-01-01 as epoch, Unix uses 1970-01-01
        unix_timestamp = pub_date + 978307200
        date_str = datetime.fromtimestamp(unix_timestamp).strftime("%Y-%m-%d")

        # Create filename: date + title.ttml
        filename = sanitize_filename(f"{date_str} {episode_title}.ttml")
        output_file = os.path.join(output_dir, filename)

        # Skip if file already exists
        if os.path.exists(output_file):
            print(f"[{i}/{len(episodes)}] Skipping (exists): {filename}")
            continue

        print(f"[{i}/{len(episodes)}] Downloading: {filename}")

        try:
            fetch_transcript(bearer_token, episode_id, output_file, verbose=False)
            success_count += 1
        except Exception as e:
            print(f"  Error downloading episode {episode_id}: {e}")
            fail_count += 1
            continue

    print(f"\nDownload complete!")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Skipped: {len(episodes) - success_count - fail_count}")


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download podcast transcripts from Apple Podcasts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all transcripts for a show
  python fetchTranscripts.py 1483081827

  # Download to a specific directory
  python fetchTranscripts.py 1483081827 -o ~/podcast-transcripts

  # Download a single episode
  python fetchTranscripts.py --episode-id 1000714478537 -o ./transcripts
        """,
    )

    # Main argument: store collection ID
    parser.add_argument(
        "store_collection_id",
        type=int,
        nargs="?",
        help="Podcast store collection ID (to download all episodes)",
    )

    # Optional arguments
    parser.add_argument(
        "-o",
        "--output-dir",
        default="./transcripts",
        help="Output directory for transcript files (default: ./transcripts)",
    )

    parser.add_argument(
        "--episode-id",
        type=int,
        help="Download a single episode by episode ID (ZSTORETRACKID)",
    )

    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to Apple Podcasts database (default: auto-detect)",
    )

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        home_dir = os.path.expanduser("~")
        db_path = os.path.join(
            home_dir,
            "Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite",
        )

    # Single episode mode
    if args.episode_id:
        os.makedirs(args.output_dir, exist_ok=True)
        config = load_config()
        output_file = os.path.join(
            args.output_dir, f"transcript_{args.episode_id}.ttml"
        )
        print(f"Downloading episode {args.episode_id}...")
        try:
            fetch_transcript(config["bearer_token"], args.episode_id, output_file)
            print(f"Saved to: {output_file}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Show mode (download all episodes)
    if not args.store_collection_id:
        parser.error(
            "Either provide store_collection_id or use --episode-id for single episode download"
        )

    download_show_transcripts(args.store_collection_id, args.output_dir, db_path)


if __name__ == "__main__":
    main()
