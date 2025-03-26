#!/usr/bin/env python3

"""
AudioMetaSplitter - Split audiobooks using AudiMeta API and ffmpeg
Created by: JaegerMaster
Created on: 2025-03-26 05:15:40 UTC
Version: 1.0.6
"""

import os
import json
import requests
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC, TPOS
from tabulate import tabulate

class AudioMetaSplitter:
    def __init__(self, folder_path: str, verbose: bool = False):
        self.folder_path = Path(folder_path).resolve()
        self.api_base_url = "https://audimeta.de/api/v1"
        self.combined_file = self.folder_path / "combined_temp.mp3"
        self.headers = {
            'User-Agent': 'AudioMetaSplitter/1.0.6',
            'Accept': 'application/json'
        }
        
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"Initialized AudioMetaSplitter for folder: {self.folder_path}")

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is installed and accessible."""
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
            return True
        except FileNotFoundError:
            self.logger.error("ffmpeg not found. Please install ffmpeg to use this tool.")
            return False

    def _get_mp3_files(self) -> List[Path]:
        """Get all MP3 files in the specified folder."""
        mp3_files = sorted(self.folder_path.glob("*.mp3"))
        if not mp3_files:
            self.logger.error(f"No MP3 files found in {self.folder_path}")
            return []
        self.logger.info(f"Found {len(mp3_files)} MP3 files")
        return mp3_files

    def _extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from MP3 file."""
        try:
            audio = MP3(file_path)
            tags = ID3(file_path)
            
            metadata = {
                'title': str(tags.get('TIT2', '')),
                'artist': str(tags.get('TPE1', '')),
                'album': str(tags.get('TALB', '')),
                'duration': int(audio.info.length),
                'asin': str(tags.get('TXXX:ASIN', ''))
            }
            
            self.logger.debug(f"Extracted metadata from {file_path}: {metadata}")
            return metadata
        except Exception as e:
            self.logger.error(f"Error extracting metadata from {file_path}: {e}")
            return {}

    def _combine_mp3_files(self, files: List[Path]) -> bool:
        """Combine multiple MP3 files into one."""
        if len(files) == 1:
            self.logger.info("Only one file found, skipping combination")
            self.combined_file = files[0]
            return True

        try:
            with open('file_list.txt', 'w') as f:
                for file in files:
                    f.write(f"file '{file}'\n")

            subprocess.run([
                'ffmpeg', '-f', 'concat', '-safe', '0',
                '-i', 'file_list.txt',
                '-c', 'copy',
                str(self.combined_file)
            ], check=True)

            os.remove('file_list.txt')
            self.logger.info("Successfully combined MP3 files")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error combining MP3 files: {e}")
            return False

    def _fetch_audimeta_data(self, asin: str) -> Dict:
        """Fetch metadata from AudiMeta API."""
        try:
            # Fetch book metadata
            book_response = requests.get(
                f"{self.api_base_url}/book/{asin}",
                headers=self.headers
            )
            book_data = book_response.json()

            # Fetch chapter data
            chapter_response = requests.get(
                f"{self.api_base_url}/chapters/{asin}",
                headers=self.headers
            )
            chapter_data = chapter_response.json()

            return {
                'book': book_data,
                'chapters': chapter_data
            }
        except requests.RequestException as e:
            self.logger.error(f"Error fetching data from AudiMeta: {e}")
            return {}

    def _split_by_chapters(self, chapters: List[Dict]) -> bool:
        """Split the combined file according to chapter timestamps."""
        try:
            for i, chapter in enumerate(chapters, 1):
                output_file = self.folder_path / f"{i:02d} - {chapter['title']}.mp3"
                start_time = chapter['start_time']
                duration = chapter['duration']

                subprocess.run([
                    'ffmpeg', '-i', str(self.combined_file),
                    '-ss', str(start_time),
                    '-t', str(duration),
                    '-acodec', 'copy',
                    str(output_file)
                ], check=True)

                self._tag_file(output_file, chapter, i, len(chapters))

            self.logger.info("Successfully split and tagged all chapters")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error splitting chapters: {e}")
            return False

    def _tag_file(self, file_path: Path, chapter: Dict, 
                 track_num: int, total_tracks: int) -> None:
        """Add ID3 tags to the split file."""
        try:
            audio = ID3(file_path)
            audio.add(TIT2(encoding=3, text=chapter['title']))
            audio.add(TPE1(encoding=3, text=chapter['author']))
            audio.add(TALB(encoding=3, text=chapter['album']))
            audio.add(TRCK(encoding=3, text=f"{track_num}/{total_tracks}"))
            audio.add(TCON(encoding=3, text='Audiobook'))
            audio.add(TDRC(encoding=3, text=str(chapter['year'])))
            audio.add(TPOS(encoding=3, text=str(chapter.get('disc_number', '1'))))
            audio.save()
        except Exception as e:
            self.logger.error(f"Error tagging file {file_path}: {e}")

    def _cleanup(self) -> None:
        """Clean up temporary files."""
        if self.combined_file.exists() and self.combined_file.name == "combined_temp.mp3":
            try:
                self.combined_file.unlink()
                self.logger.info("Cleaned up temporary files")
            except Exception as e:
                self.logger.error(f"Error cleaning up temporary files: {e}")

    def process_folder(self) -> bool:
        """Main process to handle the audiobook splitting."""
        if not self._check_ffmpeg():
            return False

        mp3_files = self._get_mp3_files()
        if not mp3_files:
            return False

        # Extract metadata from first file
        metadata = self._extract_metadata(mp3_files[0])
        if not metadata.get('asin'):
            self.logger.error("No ASIN found in file metadata")
            return False

        # Combine files if necessary
        if not self._combine_mp3_files(mp3_files):
            return False

        # Fetch metadata and chapter information
        audi_data = self._fetch_audimeta_data(metadata['asin'])
        if not audi_data:
            self._cleanup()
            return False

        # Split the file according to chapters
        success = self._split_by_chapters(audi_data['chapters'])
        self._cleanup()
        
        return success

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
    
    splitter = AudioMetaSplitter(args.folder_path, args.verbose)
    success = splitter.process_folder()
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
