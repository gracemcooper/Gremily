import base64
import sqlite3
import json
import os
import time
from dotenv import load_dotenv
from requests import get
import logging

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Get Spotify API credentials
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")

import requests

#PART 1 LOAD THE DATA 

def get_token():
    auth_string = client_id + ":" + client_secret
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": "Basic " + auth_base64,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    
    result = requests.post(url, headers=headers, data=data)
    if result.status_code != 200:
        raise Exception(f"Failed to retrieve token: {result.status_code}, {result.text}")
    
    json_result = result.json()
    return json_result["access_token"]


def get_spotify_features(song_name, artist_name):
    try:
        token = get_token()

        if not song_name or not artist_name:
            print(f"Missing song name or artist name: {song_name}, {artist_name}")
            return None
    
    # Prepare headers for authorization
        headers = {
            "Authorization": f"Bearer {token}"
        }

        # Search for the song on Spotify
        search_url = f"https://api.spotify.com/v1/search?q={song_name} {artist_name}&type=track&limit=1"
        search_result = get(search_url, headers=headers).json()
    
        if 'tracks' in search_result and 'items' in search_result['tracks'] and search_result['tracks']['items']:
            song = search_result['tracks']['items'][0]
            track_id = song['id']
        
            # Fetch audio features for the track
            features_url = f"https://api.spotify.com/v1/audio-features/{track_id}"
            features = get(features_url, headers=headers).json()

            # Extract relevant features
            if all(key in features for key in ['energy', 'danceability', 'valence', 'acousticness', 'tempo', 'loudness', 'key', 'mode']):
                return {
                    'song_name': song_name,
                    'artist_name': artist_name,
                    'energy': features['energy'],
                    'danceability': features['danceability'],
                    'valence': features['valence'],
                    'acousticness': features['acousticness'],
                    'tempo': features['tempo'],
                    'loudness': features['loudness'],
                    'key': features['key'],
                    'mode': features['mode']
                }
        else:
            print(f"No tracks found for {song_name} by {artist_name}")
    except Exception as e:
        print(f"Error fetching Spotify features for {song_name} by {artist_name}: {str(e)}")
    return None

import requests
from bs4 import BeautifulSoup

# URL to scrape Billboard Hot 100 chart
billboard_url = "https://www.billboard.com/charts/hot-100/#"

def scrape_billboard_hot_100():
    response = requests.get(billboard_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all <li> tags with the class 'o-chart-results-list__item'
    songs = []
    
    # Scrape each <li> and find the <h3> inside it for the song name and <span> for artist name
    for li_tag in soup.find_all('li', class_='lrv-u-width-100p'):
        # Find the <h3> inside each <li> tag for song title
        h3_tag = li_tag.find('h3', class_='c-title')
        # Find the <span> for artist name
        span_tag = li_tag.find('span', class_='c-label')
        
        if h3_tag and span_tag:
            song_title = h3_tag.get_text(strip=True)
            artist_name = span_tag.get_text(strip=True)
            
            # Add song title and artist name to the list as a tuple
            if song_title and artist_name:
                songs.append((song_title, artist_name))
    if not songs:
        raise Exception("Unable to scrape Billboard Hot 100 data. Verify the HTML structure.")
    return songs

# PART 2 STORE THE DATA 

import sqlite3

# Connect to the SQLite database
conn = sqlite3.connect("music_trends.db")
conn.execute("PRAGMA foreign_keys = ON")  # Ensure foreign keys are enforced
cursor = conn.cursor()

#Create BillboradSongs table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS BillboardSongs (
        song_id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_name TEXT NOT NULL COLLATE NOCASE,
        artist_name TEXT NOT NULL COLLATE NOCASE,
        UNIQUE(song_name, artist_name)
    )
""")

# Create SpotifyFeatures table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS SpotifyFeatures (
        feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_id INTEGER NOT NULL,
        danceability REAL,
        tempo REAL,
        energy REAL,
        valence REAL,
        acousticness REAL,
        loudness REAL,
        key INTEGER,
        mode INTEGER,       
        FOREIGN KEY(song_id) REFERENCES BillboardSongs(song_id) ON DELETE CASCADE
    )
""")

#Commit changes
conn.commit()

#insert data into the tables
def insert_billboard_data(songs):
    for song_name, artist_name in songs:
        cursor.execute("""
            INSERT OR IGNORE INTO BillboardSongs (song_name, artist_name) 
            VALUES (?, ?)
        """, (song_name.lower(), artist_name.lower()))
    conn.commit()

# Insert Spotify features data
def insert_spotify_data(song_features):
    for song in song_features:
        cursor.execute("""
            SELECT song_id FROM BillboardSongs
            WHERE LOWER(song_name) = ? AND LOWER(artist_name) = ?
        """, (song['song_name'].strip().lower(), song['artist_name'].strip().lower()))
        
        song_id = cursor.fetchone()

        if song_id:  # Only proceed if song_id is found
            cursor.execute("""
                INSERT INTO SpotifyFeatures 
                (song_id, danceability, tempo, energy, valence, acousticness, loudness, key, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (song_id[0], song['danceability'], song['tempo'], song['energy'], song['valence'],
                  song['acousticness'], song['loudness'], song['key'], song['mode']))
            print(f"Inserted Spotify features for {song['song_name']} by {song['artist_name']}")
        else:
            print(f"Warning: Song ID not found for {song['song_name']} by {song['artist_name']}. Skipping...")
    
    conn.commit()

# STEP 3 CALCULATIONS 

# Calculate average tempo and danceability
def calculate_averages():
    cursor.execute("""
        SELECT AVG(sf.tempo) AS avg_tempo, AVG(sf.danceability) AS avg_danceability
        FROM SpotifyFeatures AS sf
    """)
    result = cursor.fetchone()
    with open("calculated_data.txt", "w") as file:
        if result and result[0] is not None and result[1] is not None:
            file.write(f"Average Tempo: {result[0]:.2f}\n")
            file.write(f"Average Danceability: {result[1]:.2f}\n")
        else:
            file.write("No data available to calculate averages.\n")
            print("Warning: No data available to calculate averages.")


import matplotlib.pyplot as plt

# Visualization: Scatter plot for tempo vs danceability
def plot_tempo_vs_danceability():
    cursor.execute("""
        SELECT tempo, danceability
        FROM SpotifyFeatures
    """)
    data = cursor.fetchall()
    tempos = [row[0] for row in data]
    danceabilities = [row[1] for row in data]
    
    plt.scatter(tempos, danceabilities, color='blue', alpha=0.5)
    plt.xlabel("Tempo")
    plt.ylabel("Danceability")
    plt.title("Danceability vs Tempo")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

# Visualization: Bar chart of top 10 artists by number of songs
def plot_top_artists():
    cursor.execute("""
        SELECT artist_name, COUNT(*) AS song_count
        FROM BillboardSongs
        GROUP BY artist_name
        ORDER BY song_count DESC
        LIMIT 10
    """)
    data = cursor.fetchall()
    artists = [row[0] for row in data]
    counts = [row[1] for row in data]

    plt.bar(artists, counts, color='orange')
    plt.xticks(rotation=45, ha='right')
    plt.xlabel("Artists")
    plt.ylabel("Number of Songs")
    plt.title("Top 10 Artists by Number of Songs")
    plt.tight_layout()
    plt.show()


def main():
    # Gather Billboard data
    billboard_songs = scrape_billboard_hot_100()

    # Limit to the first 50 songs
    limited_songs = billboard_songs[:50]

    # Insert limited Billboard data
    insert_billboard_data(limited_songs)

    # Fetch Spotify features for limited songs
    spotify_features = []
    for song_name, artist_name in limited_songs:
        feature = get_spotify_features(song_name, artist_name)
        if feature:
            spotify_features.append(feature)
    
    # Insert Spotify data
    insert_spotify_data(spotify_features)

    # Perform calculations and visualize
    calculate_averages()
    plot_tempo_vs_danceability()
    plot_top_artists()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"An error occurred during execution: {e}")
    finally:
        conn.close()