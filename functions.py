"""The OpenAI Conversation integration."""
import logging
import json
from datetime import datetime

#Spotify functions
from .utils import SpotifyUtils

from homeassistant.config_entries import ConfigEntry

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    TemplateError,
)
from homeassistant.helpers import config_validation as cv, intent, selector, template
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import ulid


class ApiFunctions:
    spotify = None
    functions = [
        {
            "name": "get_current_datetime",
            "description": "Get current datetime",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "search_music_tracks",
            "description": "Search for music and artists from backend",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist": {
                        "type": "string",
                        "description": "Artist name",
                    },
                    "track": {
                        "type": "string",
                        "description": "Track name",
                    },
                    "search_type": {
                        "type": "string",
                        "description": "what to search for: tracks (track), artists (artist) or both (track,artist)",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "play_track",
            "description": "Plays music by track-ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "track_id": {
                        "type": "string",
                        "description": "Track-id",
                    },
                },
                "required": ["track_id"],
            },
        },
    ]
    async def setup(hass: HomeAssistant, entry: ConfigEntry):
        ApiFunctions.spotify = await SpotifyUtils.setup_spotify_connection(hass, entry)
        pass
        
    def get_functions():
        return ApiFunctions.functions

    def get_current_datetime(hass):
        logging.info("get_current_datetime()")
        now = datetime.now()
        return json.dumps({
            "datetime": now.isoformat(timespec='seconds'),
        })

    #search music tracks from spotify
    def search_music_tracks(hass, search_string="", search_type="track,artist"):
        
        search_result = ApiFunctions.spotify.search(q=search_string, type=search_type, limit=3)
        logging.error("search_music_tracks() = ", search_result)
        
        function_result = SpotifyUtils.export_search_results(search_result)

        return json.dumps(function_result)

    #play track by calling media_player.play_media
    def play_track(hass, track_id):
        logging.info("play_track()")
        result = hass.services.call("media_player", "play_media", {
            "entity_id": "media_player.spotify_spotify_premium",
            "media_content_id": "spotify:track:" + track_id,
            "media_content_type": "track",
        })

        return json.dumps({
            "result": "OK, playing track %s" % track_id,
        })

    def call(hass, function_name, function_args):
        if function_name == "get_current_datetime":
            function_result = ApiFunctions.get_current_datetime(hass)
        elif function_name == "search_music_tracks":
            #process function args to search string
            search_string=""
            search_type="track,artist"
            if "artist" in function_args and function_args["artist"]:
                search_string += f" artist:'%s'" % function_args["artist"]
            if "track" in function_args and function_args["track"]:
                search_string += f" track:'%s'" % function_args["track"]
            if "search_type" in function_args and function_args["search_type"]:
                search_type = function_args["search_type"]
            function_result = ApiFunctions.search_music_tracks(hass, search_string, search_type)

        elif function_name == "play_track":
            spotify_track_id = function_args["track_id"]
            function_result = ApiFunctions.play_track(hass, spotify_track_id)
        else:
            function_result = "Unknown function"
        return function_result

