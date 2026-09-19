import importlib
import sys
import json
import re
import subprocess
from urllib.request import Request, urlopen
from pathlib import Path
from difflib import SequenceMatcher

yt_dlp = importlib.import_module("yt_dlp")

def similar(a, b):
    """Compares two strings and returns a similarity score from 0.0 to 1.0"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def get_spotify_playlist_tracks(playlist_url):
    """Bypasses the locked API by scraping Spotify's public embed widget."""
    match = re.search(r'playlist/([a-zA-Z0-9]+)', playlist_url)
    if not match:
        print("Error: Could not extract a valid Spotify playlist ID.")
        sys.exit(1)
        
    playlist_id = match.group(1)
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    
    print("Scraping Spotify embed widget for tracks...")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        request = Request(embed_url, headers=headers)
        with urlopen(request) as response:
            status_code = response.status
            page_text = response.read().decode("utf-8")

        if status_code != 200:
            print(f"Error loading embed page: {status_code}")
            sys.exit(1)
            
        json_match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            page_text,
            re.DOTALL,
        )
        if not json_match:
            print("Error: Could not find track data. Spotify might have changed their embed structure.")
            sys.exit(1)
            
        data = json.loads(json_match.group(1))
        queries = []
        
        track_list = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {}).get('trackList', [])
        
        if not track_list:
            print("Error: Playlist is empty or track list could not be parsed.")
            sys.exit(1)
            
        for item in track_list:
            title = item.get('title', '')
            subtitle = item.get('subtitle', '')
            if title:
                # Combine title and subtitle (artist) into a single search query
                queries.append(f"{title} {subtitle}")
                
        return queries
            
    except Exception as e:
        print(f"Scraping error: {e}")
        sys.exit(1)

def get_text_file_tracks(file_path):
    """Reads a list of song queries from a text file."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: The file '{file_path}' does not exist.")
        sys.exit(1)
        
    with open(path, 'r', encoding='utf-8') as f:
        # Read lines, strip whitespace, and ignore empty lines
        queries = [line.strip() for line in f if line.strip()]
        
    return queries

def main():
    print("=== Universal Music Downloader ===")
    print("1. Download from a public Spotify Playlist")
    print("2. Download from a .txt file")
    
    choice = input("Select an option (1 or 2): ").strip()
    
    if choice == '1':
        spotify_url = input("Enter the public Spotify Playlist URL: ").strip()
        queries = get_spotify_playlist_tracks(spotify_url)
    elif choice == '2':
        txt_file = input("Enter the path to your .txt file (e.g., songs.txt): ").strip()
        queries = get_text_file_tracks(txt_file)
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)

    if not queries:
        print("No songs found to download.")
        sys.exit(1)

    folder_input = input("Enter the download folder path (e.g., ./music or C:/Downloads): ").strip()
    
    # Setup the output directory
    download_dir = Path(folder_input)
    download_dir.mkdir(parents=True, exist_ok=True)
    
    urls_file = download_dir / "urls.txt"
    not_found_file = download_dir / "not-found.txt"

    print(f"\nFound {len(queries)} songs. Searching YouTube...\n")

    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
    }

    found_urls = []
    not_found = []
    
    SEARCH_COUNT = 5
    SIMILARITY_THRESHOLD = 0.35

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for query in queries:
            print(f"Searching: {query}...", end=" ", flush=True)
            
            try:
                result = ydl.extract_info(f"ytsearch{SEARCH_COUNT}:{query}", download=False)
                
                best_match_url = None
                best_score = 0
                
                if 'entries' in result and result['entries']:
                    for entry in result['entries']:
                        yt_title = entry.get('title', '')
                        yt_uploader = entry.get('uploader', '')
                        
                        # Compare expected query against actual YouTube metadata
                        actual_str = f"{yt_title} {yt_uploader}"
                        
                        score = similar(query, actual_str)
                        if score > best_score:
                            best_score = score
                            best_match_url = entry.get('original_url') or entry.get('webpage_url') or entry.get('url')
                            
                if best_match_url and best_score >= SIMILARITY_THRESHOLD:
                    found_urls.append(best_match_url)
                    print(f"Match found! (Accuracy: {best_score:.2f})")
                else:
                    not_found.append(query)
                    print("No close match found.")
                    
            except Exception as e:
                not_found.append(query)
                print(f"Error: {e}")

    # Output text files directly into the target folder
    with open(urls_file, "w", encoding="utf-8") as f:
        for url in found_urls:
            f.write(f"{url}\n")
            
    if not_found:
        with open(not_found_file, "w", encoding="utf-8") as f:
            for q in not_found:
                f.write(f"{q}\n")

    print(f"\nDone! Saved {len(found_urls)} URLs to {urls_file}.")
    if not_found:
        print(f"Could not find valid matches for {len(not_found)} songs. Logged in {not_found_file}.")
        
    print("\nStarting automatic download process via yt-dlp...\n")
    
    output_template = str(download_dir / "%(title)s.%(ext)s")
    
    download_command = [
        "yt-dlp",
        "-a", str(urls_file),
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", output_template
    ]
    
    try:
        subprocess.run(download_command, check=True)
        print(f"\nAll downloads completed successfully! Check your '{download_dir.absolute()}' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nAn error occurred during the download phase: {e}")
    except FileNotFoundError:
        print("\nError: yt-dlp command not found. Ensure it is accessible in your system PATH.")

if __name__ == "__main__":
    main()