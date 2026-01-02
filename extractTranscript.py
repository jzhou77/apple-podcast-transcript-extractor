import os
import re
import sys
import argparse
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


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


def query_episode_metadata(db, transcript_identifier):
    query = """
        SELECT
            e.ZTITLE as episode_title,
            e.ZPUBDATE,
            e.ZDURATION,
            p.ZTITLE as podcast_title,
            p.ZAUTHOR,
            p.ZCATEGORY
        FROM ZMTEPISODE e
        JOIN ZMTPODCAST p ON e.ZPODCASTUUID = p.ZUUID
        WHERE e.ZTRANSCRIPTIDENTIFIER = ?
    """

    try:
        cursor = db.cursor()
        cursor.execute(query, (transcript_identifier,))
        row = cursor.fetchone()

        if row:
            return {
                'episode_title': row[0],
                'pub_date': row[1],
                'duration': row[2],
                'podcast_title': row[3],
                'author': row[4],
                'category': row[5]
            }
        return None
    except sqlite3.Error as e:
        print(f"Database query error for {transcript_identifier}: {e}")
        return None


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

        # Try with namespace first
        paragraphs = root.findall('.//tt:p', ns)

        # If no paragraphs found with namespace, try without
        if not paragraphs:
            paragraphs = root.findall('.//p')

        transcript = []

        for paragraph in paragraphs:
            # Find all sentence-level spans using iter() to traverse all descendants
            sentence_spans = [
                span for span in paragraph.iter()
                if span.tag.endswith('span') and
                (span.get('{http://podcasts.apple.com/transcript-ttml-internal}unit') == 'sentence'
                 or span.get('unit') == 'sentence')
            ]

            # If we found sentence spans, extract each sentence separately
            if sentence_spans:
                for sentence_span in sentence_spans:
                    sentence_text = extract_text_from_spans(sentence_span).strip()
                    # Normalize whitespace
                    sentence_text = ' '.join(sentence_text.split())

                    if sentence_text:
                        if include_timestamps and 'begin' in sentence_span.attrib:
                            timestamp = format_timestamp(float(sentence_span.attrib['begin']))
                            transcript.append(f"[{timestamp}] {sentence_text}")
                        else:
                            transcript.append(sentence_text)
            else:
                # Fallback: extract all text from the paragraph as one block
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
  # Process all TTML files in Apple Podcasts cache
  python extractTranscript.py

  # Process all files with timestamps and custom output directory
  python extractTranscript.py --timestamps -o ~/my-transcripts

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

    args = parser.parse_args()

    # Determine mode based on positional arguments
    if args.input_file and args.output_file:
        # Single file mode
        try:
            with open(args.input_file, 'r', encoding='utf-8') as f:
                data = f.read()
            extract_transcript(data, args.output_file, args.timestamps)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

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
        for file_info in ttml_files:
            try:
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

                    print(f'  Found metadata: "{metadata["podcast_title"]}" - "{metadata["episode_title"]}"')
                else:
                    # Fallback to original ID-based naming
                    base_filename = file_info['id']
                    count = filename_counts.get(base_filename, 0)
                    suffix = "" if count == 0 else f"-{count}"
                    filename = f"{base_filename}{suffix}.txt"
                    filename_counts[base_filename] = count + 1

                    print(f"  No metadata found, using ID: {file_info['id']}")

                output_path = os.path.join(output_dir, filename)

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
        print("Processing completed!")

    else:
        # Invalid combination of arguments
        parser.error("Either provide both input and output files for single file mode, or neither for batch mode")



if __name__ == "__main__":
    main()
