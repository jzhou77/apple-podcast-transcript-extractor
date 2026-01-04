import unittest
import hashlib
import os
from pathlib import Path
import tempfile
from fetchTranscripts import load_config, fetch_transcript


class TestFetchTranscripts(unittest.TestCase):
    """Test suite for fetchTranscripts.py"""

    def test_transcript_md5_hash(self):
        """Test that the downloaded transcript has the expected MD5 hash."""
        # Use the default podcast ID from the script
        podcast_id = 1000714478537
        expected_md5 = '062dfc97859c61131a7c78676aef27b5'

        # Load config and get bearer token
        config = load_config()
        bearer_token = config['bearer_token']

        # Create a temporary file for the download
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.ttml') as tmp_file:
            output_file = tmp_file.name

        try:
            # Fetch the transcript
            downloaded_file = fetch_transcript(bearer_token, podcast_id, output_file)

            # Calculate MD5 hash of the downloaded file
            md5_hash = hashlib.md5()
            with open(downloaded_file, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5_hash.update(chunk)

            actual_md5 = md5_hash.hexdigest()

            # Assert the MD5 hash matches
            self.assertEqual(
                actual_md5,
                expected_md5,
                f"MD5 hash mismatch for podcast_id {podcast_id}. "
                f"Expected: {expected_md5}, Got: {actual_md5}"
            )

            print(f"\n✓ Successfully verified MD5 hash for podcast_id {podcast_id}")
            print(f"  Expected: {expected_md5}")
            print(f"  Actual:   {actual_md5}")

        finally:
            # Clean up the temporary file
            if os.path.exists(output_file):
                os.remove(output_file)


if __name__ == '__main__':
    unittest.main()
