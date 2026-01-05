import os
import re
import sys
import argparse
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from podcast_db import query_episode_metadata


def format_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)

    return f"{h:02d}:{m:02d}:{s:02d}"


def sanitize_filename(filename):
    """Replace invalid filesystem characters and limit length"""
    filename = re.sub(r'[<>:"/\\|?*]', '-', filename)
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename.strip()
    return filename[:200]  # Limit length to avoid filesystem issues


def extract_text_from_spans(element):
    """Recursively extract text from nested span elements"""
    text = ""

    # Get direct text content
    if element.text:
        text += element.text

    # Process all child elements
    for child in element:
        # Recursively get text from child
        child_text = extract_text_from_spans(child)

        # Add space after word-level spans to separate words
        # Check both with and without namespace prefix
        unit = child.get('unit') or child.get('{http://podcasts.apple.com/transcript-ttml-internal}unit')
        if child.tag.endswith('span') and unit == 'word':
            child_text += ' '

        text += child_text

        # Get tail text (text after the child element)
        if child.tail:
            text += child.tail

    return text


def extract_transcript(ttml_content, output_path, include_timestamps=False):
    try:
        # Parse XML
        root = ET.fromstring(ttml_content)

        # Define namespace
        ns = {
            'tt': 'http://www.w3.org/ns/ttml',
            'podcasts': 'http://podcasts.apple.com/transcript-ttml-internal'
        }

        # Follow the same structure as JavaScript: result.tt.body[0].div[0].p
        # Access body[0]
        body_elements = root.findall('tt:body', ns)
        if not body_elements:
            body_elements = root.findall('body')

        if not body_elements:
            raise ValueError("No body element found in TTML")

        body = body_elements[0]

        # Access div elements
        div_elements = body.findall('tt:div', ns)
        if not div_elements:
            div_elements = body.findall('div')

        if not div_elements:
            raise ValueError("No div element found in body")

        # Process ALL div elements, not just div[0]
        transcript = []

        for div in div_elements:
            # Access p elements within this div
            paragraphs = div.findall('tt:p', ns)
            if not paragraphs:
                paragraphs = div.findall('p')

            for paragraph in paragraphs:
                # Extract all text from the paragraph as one block (matching JavaScript behavior)
                paragraph_text = extract_text_from_spans(paragraph).strip()
                # Normalize whitespace (replace multiple spaces with single space)
                paragraph_text = ' '.join(paragraph_text.split())

                if paragraph_text:
                    if include_timestamps and 'begin' in paragraph.attrib:
                        timestamp = format_timestamp(float(paragraph.attrib['begin']))
                        transcript.append(f"[{timestamp}] {paragraph_text}")
                    else:
                        transcript.append(paragraph_text)

        # Join paragraphs with double newlines
        output_text = "\n\n".join(transcript)

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_text)

        print(f"Transcript saved to {output_path}")

    except ET.ParseError as e:
        print(f"XML parse error: {e}")
        raise
    except Exception as e:
        print(f"Error extracting transcript: {e}")
        raise


def find_ttml_files(directory, base_dir=None):
    """Recursively find all TTML files in directory"""
    if base_dir is None:
        base_dir = directory

    ttml_files = []

    try:
        for entry in os.listdir(directory):
            full_path = os.path.join(directory, entry)

            if os.path.isdir(full_path):
                ttml_files.extend(find_ttml_files(full_path, base_dir))
            elif full_path.endswith('.ttml'):
                # Extract the transcript identifier (relative path from TTML base directory)
                relative_path = os.path.relpath(full_path, base_dir)

                # Handle duplicate filename pattern (e.g., transcript_123.ttml-123.ttml -> transcript_123.ttml)
                transcript_identifier = re.sub(r'(.+\.ttml)-\d+\.ttml$', r'\1', relative_path)

                if transcript_identifier.startswith('PodcastContent'):
                    # Extract ID from path
                    match = re.search(r'PodcastContent([^/]+)', transcript_identifier)
                    file_id = match.group(1) if match else 'unknown'

                    ttml_files.append({
                        'path': full_path,
                        'transcript_identifier': transcript_identifier,
                        'id': file_id
                    })
    except OSError as e:
        print(f"Error reading directory {directory}: {e}")

    return ttml_files


def main():
    parser = argparse.ArgumentParser(
        description='Extract transcripts from Apple Podcasts TTML files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Process all TTML files in Apple Podcasts cache (quiet mode)
  python extractTranscript.py

  # Process all files with verbose output
  python extractTranscript.py --verbose

  # Process all files with timestamps and custom output directory
  python extractTranscript.py --timestamps -o ~/my-transcripts

  # Process TTML files from a custom directory
  python extractTranscript.py -i ./test_show_download -o ./output_transcripts

  # Process TTML files with timestamps and verbose output
  python extractTranscript.py -i ./ttml_files -o ./transcripts --timestamps --verbose

  # Process a single TTML file
  python extractTranscript.py input.ttml output.txt

  # Process a single file with timestamps
  python extractTranscript.py input.ttml output.txt --timestamps
        '''
    )

    # Positional arguments for single file mode
    parser.add_argument('input_file', nargs='?', help='Input TTML file (for single file mode)')
    parser.add_argument('output_file', nargs='?', help='Output text file (for single file mode)')

    # Optional arguments
    parser.add_argument('--timestamps', action='store_true',
                        help='Include timestamps in the transcript output')
    parser.add_argument('-o', '--output-dir', default='./transcripts',
                        help='Output directory for batch mode (default: ./transcripts)')
    parser.add_argument('-i', '--input-dir',
                        help='Input directory containing TTML files to process')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                        help='Skip files that have already been processed (batch mode only)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print detailed processing information (batch mode only)')

    args = parser.parse_args()

    # Determine mode based on arguments
    if args.input_file and args.output_file:
        # Single file mode
        try:
            with open(args.input_file, 'r', encoding='utf-8') as f:
                data = f.read()
            extract_transcript(data, args.output_file, args.timestamps)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.input_dir:
        # Custom directory mode - process TTML files from specified directory
        output_dir = args.output_dir

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Verify input directory exists
        if not os.path.isdir(args.input_dir):
            print(f"Error: Input directory does not exist: {args.input_dir}")
            sys.exit(1)

        print(f"Searching for TTML files in {args.input_dir}...")

        # Find all TTML files in the input directory
        ttml_files = []
        for filename in os.listdir(args.input_dir):
            if filename.endswith('.ttml'):
                ttml_files.append({
                    'path': os.path.join(args.input_dir, filename),
                    'filename': filename
                })

        print(f"Found {len(ttml_files)} TTML files")

        if not ttml_files:
            print("No TTML files found in input directory")
            sys.exit(0)

        # Process files
        success_count = 0
        skipped_count = 0
        fail_count = 0

        for i, file_info in enumerate(ttml_files, 1):
            try:
                # Use the TTML filename (without extension) as output filename
                base_filename = os.path.splitext(file_info['filename'])[0]
                output_filename = f"{base_filename}.txt"
                output_path = os.path.join(output_dir, output_filename)

                # Skip if file already exists and --skip-existing is set
                if args.skip_existing and os.path.exists(output_path):
                    if args.verbose:
                        print(f"[{i}/{len(ttml_files)}] Skipping (already exists): {output_filename}")
                    skipped_count += 1
                    continue

                if args.verbose:
                    print(f"[{i}/{len(ttml_files)}] Processing: {file_info['filename']}")

                with open(file_info['path'], 'r', encoding='utf-8') as f:
                    data = f.read()

                extract_transcript(data, output_path, args.timestamps)
                success_count += 1

                if not args.verbose:
                    print(f"[{i}/{len(ttml_files)}] Processed: {output_filename}")

            except Exception as error:
                print(f"[{i}/{len(ttml_files)}] Error processing {file_info['filename']}: {error}")
                fail_count += 1

        print(f"\nProcessing complete!")
        print(f"  Success: {success_count}")
        print(f"  Failed: {fail_count}")
        print(f"  Skipped: {skipped_count}")

    elif not args.input_file and not args.output_file:
        # Batch mode - process all TTML files
        output_dir = args.output_dir

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        home_dir = os.path.expanduser("~")
        ttml_base_dir = os.path.join(home_dir, "Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Library/Cache/Assets/TTML")
        db_path = os.path.join(home_dir, "Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite")

        print("Searching for TTML files...")
        ttml_files = find_ttml_files(ttml_base_dir)

        print(f"Found {len(ttml_files)} TTML files")

        if not os.path.exists(db_path):
            print(f"Database not found at: {db_path}")
            print("Please ensure Apple Podcasts app has been used and the database exists.")
            sys.exit(1)

        print("Connecting to Apple Podcasts database...")
        db = sqlite3.connect(db_path)

        # Track filename occurrences to handle duplicates
        filename_counts = {}

        # Process files
        skipped_count = 0
        for file_info in ttml_files:
            try:
                if args.verbose:
                    print(f"Processing: {file_info['transcript_identifier']}")

                # Query database for metadata
                metadata = query_episode_metadata(db, file_info['transcript_identifier'])

                if metadata and metadata['podcast_title'] and metadata['episode_title']:
                    # Use podcast + episode title for filename
                    base_filename = sanitize_filename(f"{metadata['podcast_title']} - {metadata['episode_title']}")

                    # Handle duplicate filenames
                    count = filename_counts.get(base_filename, 0)
                    suffix = "" if count == 0 else f" ({count})"
                    filename = f"{base_filename}{suffix}.txt"
                    filename_counts[base_filename] = count + 1

                    if args.verbose:
                        print(f'  Found metadata: "{metadata["podcast_title"]}" - "{metadata["episode_title"]}"')
                else:
                    # Fallback to original ID-based naming
                    base_filename = file_info['id']
                    count = filename_counts.get(base_filename, 0)
                    suffix = "" if count == 0 else f"-{count}"
                    filename = f"{base_filename}{suffix}.txt"
                    filename_counts[base_filename] = count + 1

                    if args.verbose:
                        print(f"  No metadata found, using ID: {file_info['id']}")

                output_path = os.path.join(output_dir, filename)

                # Skip if file already exists and --skip-existing is set
                if args.skip_existing and os.path.exists(output_path):
                    if args.verbose:
                        print(f"  Skipping (already exists): {filename}")
                    skipped_count += 1
                    continue

                with open(file_info['path'], 'r', encoding='utf-8') as f:
                    data = f.read()

                extract_transcript(data, output_path, args.timestamps)

            except Exception as error:
                print(f"Error processing {file_info['transcript_identifier']}: {error}")

                # Fallback to ID-based naming on error
                base_filename = file_info['id']
                count = filename_counts.get(base_filename, 0)
                suffix = "" if count == 0 else f"-{count}"
                output_path = os.path.join(output_dir, f"{base_filename}{suffix}.txt")
                filename_counts[base_filename] = count + 1

                try:
                    with open(file_info['path'], 'r', encoding='utf-8') as f:
                        data = f.read()
                    extract_transcript(data, output_path, args.timestamps)
                except Exception as fallback_error:
                    print(f"Failed to process {file_info['path']}: {fallback_error}")

        db.close()
        print(f"Processing {len(ttml_files)} files completed! Skipped {skipped_count} files.")

    else:
        # Invalid combination of arguments
        parser.error("Either provide both input and output files for single file mode, or neither for batch mode")



if __name__ == "__main__":
    main()
