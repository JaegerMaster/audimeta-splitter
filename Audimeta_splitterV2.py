import os
import glob
import json
import subprocess
from fuzzywuzzy import fuzz
import requests
from natsort import natsorted
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TPE2, TCOM, TCON, TRCK, TPUB, TDRC, COMM, APIC

# --- Tab Completion Setup ---
try:
    import readline

    def path_completer(text, state):
        matches = glob.glob(text + '*')
        matches = [match + '/' if os.path.isdir(match) else match for match in matches]
        return matches[state] if state < len(matches) else None

    readline.set_completer(path_completer)
    readline.parse_and_bind("tab: complete")
    print("Tab completion for folder paths is enabled.")
except ImportError:
    print("Readline not available. For tab completion on Windows, run: pip install pyreadline3")
# --- End of Tab Completion Setup ---


def get_directory_from_user():
    """Gets a directory path from the user and validates it."""
    while True:
        directory = input("Please enter the path to the directory containing your audiobook files: ")
        directory = os.path.expanduser(directory)
        if os.path.isdir(directory):
            return directory
        else:
            print("Invalid directory. Please try again.")

def find_mp3_files(directory):
    """Finds all MP3 files in a given directory."""
    return glob.glob(os.path.join(directory, '*.mp3'))

def merge_mp3s(mp3_files, output_filename):
    """Merges a list of MP3 files (already naturally sorted) into a single file using ffmpeg."""
    if not mp3_files:
        print("No MP3 files to merge.")
        return None

    file_list_path = os.path.join(os.path.dirname(output_filename), 'filelist.txt')
    with open(file_list_path, 'w') as f:
        for mp3_file in mp3_files:
            f.write(f"file '{os.path.basename(mp3_file)}'\n")

    command = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', file_list_path,
        '-c', 'copy', '-map_metadata', '-1', # Explicitly drop metadata from merged file
        output_filename
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Successfully merged files into {os.path.basename(output_filename)}")
        os.remove(file_list_path)
        return output_filename
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ffmpeg is required. Please install it and ensure it's in your system's PATH.")
        os.remove(file_list_path)
        return None

def get_mp3_metadata(mp3_file):
    """Extracts title and artist from an MP3 file's metadata."""
    try:
        audio = EasyID3(mp3_file)
        title = audio.get('title', ['Unknown Title'])[0]
        artist = audio.get('artist', ['Unknown Artist'])[0]
        return title, artist
    except Exception as e:
        print(f"Could not read metadata from {os.path.basename(mp3_file)}: {e}")
        return None, None

def search_audimeta(title, author):
    """Searches the AudiMeta API for a book matching the title and author."""
    url = "https://beta.audimeta.de/search"
    params = {'title': title, 'author': author, 'limit': 10, 'region': 'us'}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return None

def display_and_select_match(search_results, original_title, original_author):
    """Displays search results and prompts the user to select the correct one."""
    if not search_results or not isinstance(search_results, list):
        print("No matches found or invalid data received from API.")
        return None

    print("\nPossible matches found:")
    matches = []
    for result in search_results:
        # Defensive check in case API returns non-dictionary items in the list
        if not isinstance(result, dict):
            continue
            
        title_ratio = fuzz.ratio(original_title.lower(), result.get('title', '').lower())
        author_names = [author.get('name') for author in result.get('authors', []) if author.get('name')]
        author_ratio = fuzz.ratio(original_author.lower(), ' '.join(author_names).lower())
        confidence = (title_ratio + author_ratio) / 2
        matches.append({'result': result, 'confidence': confidence})

    matches.sort(key=lambda x: x['confidence'], reverse=True)

    for i, match in enumerate(matches):
        result = match['result']
        authors = ', '.join([author.get('name') for author in result.get('authors', []) if author.get('name')])
        narrators = ', '.join([narrator.get('name') for narrator in result.get('narrators', []) if narrator.get('name')])
        duration_minutes = result.get('lengthMinutes', 0)
        hours, minutes = divmod(duration_minutes, 60)
        print(f"  {i+1}. Title: {result.get('title')}")
        print(f"     Author(s): {authors}")
        print(f"     Narrator(s): {narrators}")
        print(f"     Publisher: {result.get('publisher')}")
        print(f"     Duration: {int(hours)}h {int(minutes)}m")
        print(f"     Confidence: {match['confidence']:.2f}%")
        print("-" * 20)

    while True:
        try:
            choice = int(input("Please select the correct match (enter the number): "))
            if 1 <= choice <= len(matches):
                return matches[choice - 1]['result']
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a valid number.")

def get_audimeta_details(asin, region='us'):
    """Fetches book and chapter details from the AudiMeta API."""
    book_url = f"https://beta.audimeta.de/book/{asin}?region={region}"
    chapters_url = f"https://beta.audimeta.de/chapters/{asin}?region={region}"
    try:
        print(f"Fetching book details for ASIN: {asin}...")
        book_response = requests.get(book_url)
        book_response.raise_for_status()
        book_data = book_response.json()
        book_details = book_data[0] if isinstance(book_data, list) and book_data else book_data

        print("Fetching chapter details...")
        chapters_response = requests.get(chapters_url)
        chapters_response.raise_for_status()
        chapter_details = chapters_response.json()
        return book_details, chapter_details
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error fetching details: {e}")
        return None, None
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch details from AudiMeta: {e}")
        return None, None

def tag_mp3_file(filename, book_details, chapter_info, track_number):
    """Adds ID3 metadata to a single MP3 file."""
    audio = MP3(filename, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    audio.tags.add(TIT2(encoding=3, text=chapter_info.get('title', '')))
    audio.tags.add(TALB(encoding=3, text=book_details.get('title', '')))
    
    authors = ', '.join([author['name'] for author in book_details.get('authors', [])])
    audio.tags.add(TPE1(encoding=3, text=authors))
    audio.tags.add(TPE2(encoding=3, text=authors))
    
    narrators = ', '.join([narrator['name'] for narrator in book_details.get('narrators', [])])
    audio.tags.add(TCOM(encoding=3, text=narrators))
    
    genres = ', '.join([genre['name'] for genre in book_details.get('genres', [])])
    audio.tags.add(TCON(encoding=3, text=genres))

    audio.tags.add(TRCK(encoding=3, text=str(track_number)))
    audio.tags.add(TPUB(encoding=3, text=book_details.get('publisher', '')))
    
    if book_details.get('releaseDate'):
        audio.tags.add(TDRC(encoding=3, text=str(book_details['releaseDate'][:4])))
    
    description = book_details.get('description') or book_details.get('summary', '')
    if description:
        audio.tags.add(COMM(encoding=3, lang='eng', desc='desc', text=description))

    image_url = book_details.get('imageUrl')
    if image_url:
        try:
            response = requests.get(image_url)
            response.raise_for_status()
            audio.tags.add(APIC(
                encoding=3, mime='image/jpeg', type=3, desc='Cover', data=response.content
            ))
        except requests.exceptions.RequestException as e:
            print(f"    - Warning: Could not download cover art: {e}")

    audio.save()

def split_mp3_by_chapters(mp3_file, book_details, chapters_data, output_dir):
    """Splits an MP3 file into chapters using ffmpeg and tags them."""
    if 'chapters' not in chapters_data or not chapters_data['chapters']:
        print("No chapter information available to split the file.")
        return

    print("\nSplitting and tagging MP3 file into chapters...")
    chapters = chapters_data['chapters']

    for i, chapter in enumerate(chapters):
        start_time_ms = chapter['startOffsetMs']
        duration_ms = chapter['lengthMs']
        title = chapter['title']

        if start_time_ms == 0 and i > 0:
            print(f"Warning: Chapter '{title}' starts at 0 seconds.")

        safe_title = "".join(x for x in title if x.isalnum() or x in " .-_").strip()
        output_filename = os.path.join(output_dir, f"{i+1:02d} - {safe_title}.mp3")

        command = [
            'ffmpeg', '-y', '-i', mp3_file, '-ss', str(start_time_ms / 1000),
            '-t', str(duration_ms / 1000), '-c', 'copy', '-map_metadata', '-1',
            output_filename
        ]
        
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            tag_mp3_file(output_filename, book_details, chapter, i + 1)
            print(f"  - Created & Tagged: {os.path.basename(output_filename)}")
        except subprocess.CalledProcessError as e:
            print(f"Error splitting chapter '{title}': {e.stderr.decode()}")
        except FileNotFoundError:
            print("Error: ffmpeg is required for splitting.")
            return
        except Exception as e:
            print(f"An error occurred during tagging of '{title}': {e}")


def main():
    """Main function to orchestrate the audiobook processing."""
    directory = get_directory_from_user()
    
    mp3_files = natsorted(find_mp3_files(directory))

    if not mp3_files:
        print("No MP3 files found in the specified directory.")
        return

    merged_file_path = None
    original_files_to_delete = list(mp3_files)
    if len(mp3_files) > 1:
        output_filename = os.path.join(directory, 'merged_audiobook.mp3')
        merged_file_path = merge_mp3s(mp3_files, output_filename)
        if not merged_file_path:
            return
    else:
        merged_file_path = mp3_files[0]
        print(f"Processing single file: {os.path.basename(merged_file_path)}")

    # === THE FIX IS HERE ===
    # Read metadata from the FIRST original file, not the merged one.
    # This is the reliable source of truth for the book's title and author.
    metadata_source_file = mp3_files[0]
    print(f"Reading metadata from: {os.path.basename(metadata_source_file)}")
    title, author = get_mp3_metadata(metadata_source_file)
    
    if not title or not author or title == 'Unknown Title' or author == 'Unknown Artist':
        print("\nCould not read complete metadata from the source MP3 file.")
        title_input = input(f"Please enter the audiobook title (or press Enter to keep '{title}'): ")
        author_input = input(f"Please enter the author's name (or press Enter to keep '{author}'): ")
        if title_input: title = title_input
        if author_input: author = author_input

    search_results = search_audimeta(title, author)
    selected_book = display_and_select_match(search_results, title, author)

    if not selected_book:
        print("No match selected. Exiting.")
        return

    book_details, chapter_details = get_audimeta_details(selected_book['asin'])
    if not book_details or not chapter_details:
        return

    split_mp3_by_chapters(merged_file_path, book_details, chapter_details, directory)
    
    metadata_path = os.path.join(directory, 'metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump({'book_details': book_details, 'chapter_details': chapter_details}, f, indent=4)
    print(f"\nSaved full metadata to {os.path.basename(metadata_path)}")
    
    print("\nCleaning up original files...")
    for f in original_files_to_delete:
        try:
            os.remove(f)
            print(f"  - Deleted: {os.path.basename(f)}")
        except OSError as e:
            print(f"Error deleting file {f}: {e}")

    if len(original_files_to_delete) > 1 and os.path.exists(merged_file_path):
        try:
            os.remove(merged_file_path)
            print(f"  - Deleted: {os.path.basename(merged_file_path)}")
        except OSError as e:
            print(f"Error deleting merged file: {e}")
    
    print("\nProcess completed successfully!")


if __name__ == '__main__':
    main()
