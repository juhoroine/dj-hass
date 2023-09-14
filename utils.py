"""The OpenAI Conversation integration functions."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.const import CONF_API_KEY
from spotipy.oauth2 import SpotifyClientCredentials

from homeassistant.components.spotify.const import SPOTIFY_SCOPES

from spotipy import Spotify, SpotifyException
import aiohttp
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_CHAT_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROMPT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DOMAIN,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_CLIENT_SECRET
)


class SpotifyUtils:
    async def setup_spotify_connection(hass: HomeAssistant, entry: ConfigEntry):
        client_id = entry.data[CONF_SPOTIFY_CLIENT_ID]
        client_secret = entry.data[CONF_SPOTIFY_CLIENT_SECRET]
        client_credentials_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        return Spotify(client_credentials_manager=client_credentials_manager)

    def get_spotify_search_string(artist, track):
        search_string =""
        if artist != None and artist != "":
            search_string += f" artist:'%s'" % artist
        if track != None and track != "":
            search_string += f" track:'%s'" % track

        if artist != "" and track != "":
            type="track,artist"
        else:
            if artist != "":
                type="artist"
            elif track != "":
                type="track"
            else:
                return None, None
        return search_string, type

    def export_artists(artists_obj):
        #Sort by popularity
        artists_obj = sorted(artists_obj, key=lambda k: k['popularity'], reverse=True)

        result = []
        for i, artist in enumerate(artists_obj, 1):
            result.append({
                "name": artist['name'],
                "id": artist['id'],
                "genres": artist['genres'],
                "popularity": artist['popularity'],
            })
        return result

    def export_tracks(tracks_obj):
        #Sort by popularity
        tracks_obj = sorted(tracks_obj, key=lambda k: k['popularity'], reverse=True)

        result = []
        for i, track in enumerate(tracks_obj, 1):
            duration_ms = track['duration_ms']
            duration_min = duration_ms // 60000
            duration_sec = (duration_ms % 60000) // 1000

            result.append({
                "name": track['name'],
                "id": track['id'],
                "popularity": track['popularity'],
                "release_date": track['album']['release_date'],
                "duration": f"{duration_min} min {duration_sec} s",
                "explicit": track['explicit'],
                "album": track['album']['name'],
                "artist": track['artists'][0]['name'],
            })
            
        return result

    def export_search_results(obj):
        result={}
        if 'tracks' in obj and 'items' in obj['tracks']:
            result['tracks'] = SpotifyUtils.export_tracks(obj['tracks']['items'])
        
        if 'artists' in obj and 'items' in obj['artists']:
            result['artists'] = SpotifyUtils.export_artists(obj['artists']['items'])

        return result

