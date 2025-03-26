#!/usr/bin/env python3

"""
Audio Splitter Module - Handle audio file processing and tagging
Version: 1.0.6
"""

import os
import subprocess
from datetime import datetime
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC
from .audimeta_client import AudiMetaClient

class AudioSplitter:
    def __init__(self, folder_path):
        self.folder_path = os.path.abspath(folder_path)
        self.combined_file = "combined_temp.mp3"
        self.audimeta_client = AudiMetaClient()
        print(f"Initialized AudioSplitter for folder: {self.folder_path}")

    def get_mp3_files(self):
        """Get all MP3 files in the specified folder"""
        try:
            mp3_files = sorted([
                f for f in os.listdir(self.folder_path) 
                if f.lower().endswith('.mp3')
            ])
            if mp3_files:
                print(f"Found MP3 files: {', '.join(mp3_files)}")
            else:
                print("No MP3 files found in the folder")
            return mp3_files
        except Exception as e:
            print(f"Error reading folder contents: {str(e)}")
            return []

    def calculate_total_duration(self, mp3_files):
        """Calculate total duration of all MP3 files"""
        total_duration = 0
        for mp3_file in mp3_files:
            file_path = os.path.join(self.folder_path, mp3_file)
            try:
                audio = MP3(file_path)
                total_duration += audio.info.length
            except Exception as e:
                print(f"Error reading duration from {mp3_file}: {str(e)}")
                raise
        return total_duration

    def combine_mp3_files(self, mp3_files):
        """Combine multiple MP3 files into one using ffmpeg"""
        if len(mp3_files) == 1:
            print("Only one MP3 file found, no need to combine")
            return mp3_files[0]
            
        print(f"Combining {len(mp3_files)} MP3 files...")
        
        file_list = "files.txt"
        output_file = os.path.join(self.folder_path, self.combined_file)
        
        try:
            with open(file_list, 'w', encoding='utf-8') as f:
                for mp3 in mp3_files:
                    full_path = os.path.join(self.folder_path, mp3)
                    escaped_path = full_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            print("Created concat file. Contents:")
            with open(file_list, 'r') as f:
                print(f.read())
            
            cmd = [
                'ffmpeg', 
                '-v', 'info',
                '-f', 'concat', 
                '-safe', '0',
                '-i', file_list,
                '-c', 'copy',
                '-y',
                output_file
            ]
            
            print(f"Executing ffmpeg command:")
            print(' '.join(cmd))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print("FFmpeg Error Output:")
                print(result.stderr)
                raise subprocess.CalledProcessError(
                    result.returncode, 
                    cmd,
                    result.stdout, 
                    result.stderr
                )
            
            print("FFmpeg combination successful")
            return self.combined_file
            
        except Exception as e:
            print(f"Error during file combination: {str(e)}")
            raise
        finally:
            if os.path.exists(file_list):
                os.remove(file_list)
                print("Cleaned up temporary files list")

    def tag_file(self, file_path, chapter, track_num, total_tracks, book_metadata):
        """Add ID3 tags to the split file"""
        try:
            audio = MP3(file_path, ID3=ID3)
            if not audio.tags:
                audio.tags = ID3()
            
            audio.tags.add(TIT2(encoding=3, text=chapter['title']))
            audio.tags.add(TRCK(encoding=3, text=f"{track_num}/{total_tracks}"))
            
            audio.tags.add(TPE1(encoding=3, text=book_metadata.get('authors', [{'name': 'm.s. RedCherries'}])[0].get('name', 'm.s. RedCherries')))
            audio.tags.add(TALB(encoding=3, text=book_metadata.get('title', 'Mother')))
            
            if 'releaseDate' in book_metadata:
                audio.tags.add(TDRC(encoding=3, text=book_metadata['releaseDate'][:4]))
            
            if 'genres' in book_metadata and book_metadata['genres']:
                genres = [g['name'] for g in book_metadata['genres'] if 'name' in g]
                if genres:
                    audio.tags.add(TCON(encoding=3, text=genres[0]))
            
            audio.save()
            print(f"Added metadata tags to {os.path.basename(file_path)}")
            
        except Exception as e:
            print(f"Error tagging file {file_path}: {str(e)}")

    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        filename = ''.join(c for c in filename if c not in invalid_chars)
        filename = filename.strip()
        return filename[:200] if len(filename) > 200 else filename

    def split_by_chapters(self, input_file, chapters, book_metadata):
        """Split the combined file according to chapter information"""
        input_path = os.path.join(self.folder_path, input_file)
        
        print(f"Splitting into {len(chapters)} chapters...")
        successful_splits = 0
        
        for i, chapter in enumerate(chapters, 1):
            try:
                title = chapter.get('title', f'Chapter {i}')
                start = str(chapter.get('start', 0))
                duration = str(chapter.get('duration', 0))
                
                safe_title = self.sanitize_filename(title)
                output_file = os.path.join(
                    self.folder_path,
                    f"{i:02d}_{safe_title}.mp3"
                )
                
                cmd = [
                    'ffmpeg',
                    '-i', input_path,
                    '-ss', start,
                    '-t', duration,
                    '-c', 'copy',
                    '-y',
                    output_file
                ]
                
                print(f"\nProcessing chapter {i}/{len(chapters)}: {safe_title}")
                print(f"Start time: {start}s, Duration: {duration}s")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"Error splitting chapter {i}:")
                    print(result.stderr)
                    continue
                
                self.tag_file(output_file, chapter, i, len(chapters), book_metadata)
                print(f"Created chapter {i:02d}: {safe_title}")
                successful_splits += 1
                
            except Exception as e:
                print(f"Error processing chapter {i}: {str(e)}")
                print(f"Chapter data: {chapter}")
                continue
                
        return successful_splits == len(chapters)

    def process_folder(self):
        """Main method to process the folder"""
        start_time = datetime.utcnow()
        print(f"\nStarting process at {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"Processing folder: {self.folder_path}")
        
        try:
            # Get and validate MP3 files
            mp3_files = self.get_mp3_files()
            if not mp3_files:
                print("No MP3 files found in the specified folder")
                return False
            
            # Store original file paths for later cleanup
            original_files = [os.path.join(self.folder_path, f) for f in mp3_files]
            
            # Get metadata from the first file
            first_file = os.path.join(self.folder_path, mp3_files[0])
            metadata = self.audimeta_client.get_metadata_from_file(first_file)
            
            if not metadata:
                print("Could not extract metadata from file")
                return False
            
            # Calculate total duration
            print("Calculating total duration...")
            total_duration = self.calculate_total_duration(mp3_files)
            metadata['lengthMinutes'] = int(total_duration / 60)
            print(f"Total duration: {metadata['lengthMinutes']} minutes")
            
            # Search for book and get user confirmation
            print("Searching for book in AudiMeta...")
            book_metadata = self.audimeta_client.fetch_book_metadata(metadata)
            if not book_metadata:
                print("Could not find book in AudiMeta database")
                return False
            
            # Fetch and validate chapter information
            print("Fetching chapter information...")
            chapters = self.audimeta_client.fetch_chapters(book_metadata['asin'])
            if not chapters:
                print("Could not fetch chapter information")
                return False
            
            # Combine files if necessary
            if len(mp3_files) > 1:
                print("Combining MP3 files...")
                combined_file = self.combine_mp3_files(mp3_files)
            else:
                combined_file = mp3_files[0]
            
            # Split the combined file into chapters
            splitting_successful = self.split_by_chapters(combined_file, chapters, book_metadata)
            
            # Clean up files
            cleanup_successful = True
            if splitting_successful:
                print("\nSplitting completed successfully. Cleaning up original files...")
                for file_path in original_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            print(f"Removed original file: {os.path.basename(file_path)}")
                    except Exception as e:
                        print(f"Error removing file {file_path}: {str(e)}")
                        cleanup_successful = False
                
                # Clean up combined file if it was created
                if len(mp3_files) > 1:
                    cleanup_file = os.path.join(self.folder_path, self.combined_file)
                    if os.path.exists(cleanup_file):
                        try:
                            os.remove(cleanup_file)
                            print("Cleaned up combined temporary file")
                        except Exception as e:
                            print(f"Error removing combined file: {str(e)}")
                            cleanup_successful = False
            
            end_time = datetime.utcnow()
            duration = end_time - start_time
            
            print("\nProcessing completed!")
            print(f"Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"Total processing time: {duration}")
            
            if splitting_successful and cleanup_successful:
                print("All operations completed successfully!")
            elif splitting_successful:
                print("Splitting completed successfully, but some cleanup operations failed.")
            else:
                print("Splitting operation failed.")
                
            return splitting_successful
            
        except Exception as e:
            print(f"An error occurred during processing: {str(e)}")
            return False

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Split MP3 files based on chapter data from AudiMeta'
    )
    parser.add_argument(
        'folder_path',
        help='Path to the folder containing MP3 files'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    splitter = AudioSplitter(args.folder_path)
    success = splitter.process_folder()
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
