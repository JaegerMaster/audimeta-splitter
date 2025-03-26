#!/usr/bin/env python3

"""
AudiMeta Client Module - Handle book metadata and chapter information retrieval
Version: 1.0.6
"""

import json
import requests
from tabulate import tabulate
from mutagen.mp3 import MP3
from mutagen.id3 import ID3

class AudiMetaClient:
    def __init__(self):
        self.api_base_url = "https://audimeta.de"
        self.headers = {
            'User-Agent': 'AudioMetaSplitter/1.0.6',
            'Accept': 'application/json'
        }

    def get_metadata_from_file(self, file_path):
        """Extract metadata from MP3 file to help identify the audiobook"""
        print(f"Extracting metadata from: {file_path}")
        try:
            audio = MP3(file_path, ID3=ID3)
            metadata = {}
            
            if audio.tags:
                title = str(audio.tags.get('TIT2', ''))
                album = str(audio.tags.get('TALB', ''))
                metadata['title'] = title or album or "Mother"
                
                author = str(audio.tags.get('TPE1', ''))
                metadata['author'] = author or "m.s. RedCherries"
                
                metadata['region'] = 'US'
                
                print(f"Extracted metadata: {json.dumps(metadata, indent=2)}")
                return metadata
            else:
                return {
                    'title': "Mother",
                    'author': "m.s. RedCherries",
                    'region': 'US'
                }
        except Exception as e:
            print(f"Error reading metadata: {str(e)}")
            return None

    def display_search_results(self, results):
        """Display search results in a table format"""
        if not results:
            print("No results found.")
            return 0
        
        table_data = []
        for idx, book in enumerate(results, 1):
            try:
                title = book.get('title', 'Unknown')
                author = book.get('authors', [{'name': 'Unknown'}])[0].get('name', 'Unknown')
                duration = book.get('lengthMinutes', 'Unknown')
                release_date = book.get('releaseDate', 'Unknown')
                if release_date and release_date != 'Unknown':
                    release_date = release_date[:10]
                publisher = book.get('publisher', 'Unknown')
                asin = book.get('asin', 'Unknown')
                
                genre_names = []
                for genre in book.get('genres', []):
                    if isinstance(genre, dict):
                        genre_name = genre.get('name')
                        if genre_name:
                            genre_names.append(genre_name)
                genres_str = ', '.join(genre_names)
                if len(genres_str) > 50:
                    genres_str = genres_str[:47] + '...'
                elif not genres_str:
                    genres_str = 'Unknown'
                
                table_data.append([
                    idx,
                    title,
                    author,
                    f"{duration} min" if duration != 'Unknown' else duration,
                    release_date,
                    publisher,
                    genres_str,
                    asin
                ])
                
            except Exception as e:
                print(f"Error processing book {idx}: {str(e)}")
                continue
        
        if table_data:
            headers = ['#', 'Title', 'Author', 'Duration', 'Release', 'Publisher', 'Genres', 'ASIN']
            print("\nSearch Results:")
            print(tabulate(table_data, headers=headers, tablefmt='grid'))
            return len(table_data)
        else:
            print("No valid results to display.")
            return 0

    def get_user_choice(self, results):
        """Get user's choice from search results"""
        if not results:
            return self.manual_search()
        
        count = self.display_search_results(results)
        if count == 0:
            return self.manual_search()
        
        while True:
            try:
                choice = input(f"\nSelect a book (1-{count}, or 0 to search manually): ")
                if choice == '0':
                    return self.manual_search()
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    selected = results[idx]
                    title = selected.get('title', 'Unknown')
                    author = selected.get('authors', [{'name': 'Unknown'}])[0].get('name', 'Unknown')
                    print(f"\nSelected: {title} by {author}")
                    confirm = input("Is this correct? (y/n): ").lower()
                    if confirm == 'y':
                        return selected if isinstance(selected, dict) else None
                    if confirm == 'n':
                        retry = input("Would you like to select another book? (y/n): ").lower()
                        if retry != 'y':
                            return self.manual_search()
                else:
                    print(f"Please enter a number between 1 and {count}")
            except ValueError:
                print("Please enter a valid number")
            except Exception as e:
                print(f"Error: {str(e)}")
                return self.manual_search()

    def manual_search(self):
        """Manual search if automatic search fails"""
        print("\nPerforming manual search...")
        while True:
            try:
                title = input("Enter book title (or press Enter to exit): ").strip()
                if not title:
                    return None
                    
                author = input("Enter author name: ").strip()
                
                params = {
                    'title': title,
                    'author': author,
                    'region': 'US',
                    'localTitle': title,
                    'localAuthor': author
                }
                
                print(f"\nSearching for: {title} by {author}")
                response = requests.get(
                    f"{self.api_base_url}/search",
                    params=params,
                    headers=self.headers
                )
                response.raise_for_status()
                results = response.json()
                
                if results:
                    return self.get_user_choice(results)
                else:
                    print("No results found.")
                    retry = input("Would you like to try another search? (y/n): ").lower()
                    if retry != 'y':
                        return None
                        
            except requests.exceptions.RequestException as e:
                print(f"Search error: {str(e)}")
                retry = input("Would you like to try again? (y/n): ").lower()
                if retry != 'y':
                    return None
            except Exception as e:
                print(f"Unexpected error: {str(e)}")
                retry = input("Would you like to try again? (y/n): ").lower()
                if retry != 'y':
                    return None

    def fetch_book_metadata(self, search_params):
        """Search for book in AudiMeta API"""
        try:
            params = {
                'title': search_params.get('title', ''),
                'author': search_params.get('author', ''),
                'region': search_params.get('region', 'US'),
                'localTitle': search_params.get('title', ''),
                'localAuthor': search_params.get('author', '')
            }
            
            print(f"Searching AudiMeta with parameters: {json.dumps(params, indent=2)}")
            
            response = requests.get(
                f"{self.api_base_url}/search",
                params=params,
                headers=self.headers
            )
            response.raise_for_status()
            
            results = response.json()
            
            if results:
                return self.get_user_choice(results)
            else:
                print("No matches found with file metadata.")
                return self.manual_search()
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching book metadata: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response status code: {e.response.status_code}")
                print(f"Response content: {e.response.text}")
            return self.manual_search()
        except Exception as e:
            print(f"Error processing search results: {str(e)}")
            return self.manual_search()

    def fetch_chapters(self, asin):
        """Fetch chapter information from AudiMeta API"""
        try:
            print(f"Fetching chapters for ASIN: {asin}")
            response = requests.get(
                f"{self.api_base_url}/chapters/{asin}",
                headers=self.headers
            )
            response.raise_for_status()
            
            data = response.json()
            
            if isinstance(data, dict) and 'chapters' in data:
                chapters = data['chapters']
            else:
                print(f"Unexpected chapter data format: {data}")
                return None
                
            print(f"Found {len(chapters)} chapters")
            
            processed_chapters = []
            for chapter in chapters:
                processed_chapter = {
                    'title': chapter.get('title', 'Unknown'),
                    'start': chapter.get('startOffsetSec', 0),
                    'duration': int(chapter.get('lengthMs', 0) / 1000)
                }
                processed_chapters.append(processed_chapter)
            
            table_data = []
            for i, chapter in enumerate(processed_chapters, 1):
                try:
                    title = chapter.get('title', f'Chapter {i}')
                    start = chapter.get('start', 0)
                    duration = chapter.get('duration', 0)
                    table_data.append([i, title, start, duration])
                except Exception as e:
                    print(f"Error processing chapter {i} data: {str(e)}")
                    print(f"Raw chapter data: {chapter}")
                    return None
            
            print("\nChapter Information:")
            print(tabulate(
                table_data,
                headers=['#', 'Title', 'Start (s)', 'Duration (s)'],
                tablefmt='grid'
            ))
            
            return processed_chapters
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching chapters: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response content: {e.response.text}")
        except Exception as e:
            print(f"Error processing chapter data: {str(e)}")
            print(f"Raw response data: {response.text if 'response' in locals() else 'No response'}")
        return None
