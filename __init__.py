"""The OpenAI Conversation integration."""
from __future__ import annotations

from functools import partial
import logging
from typing import Literal

import json
from datetime import datetime

import openai
from openai import error
import voluptuous as vol

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, MATCH_ALL
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
from .functions import ApiFunctions as api

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


_LOGGER = logging.getLogger(__name__)
SERVICE_GENERATE_IMAGE = "generate_image"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_API_KEY): cv.string,
                vol.Required(CONF_SPOTIFY_CLIENT_ID): cv.string,
                vol.Required(CONF_SPOTIFY_CLIENT_SECRET): cv.string,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up OpenAI Conversation."""
    logging.info("async_setup()")

    async def render_image(call: ServiceCall) -> ServiceResponse:
        """Render an image with dall-e."""
        try:
            response = await openai.Image.acreate(
                api_key=hass.data[DOMAIN][call.data["config_entry"]],
                prompt=call.data["prompt"],
                n=1,
                size=f'{call.data["size"]}x{call.data["size"]}',
            )
        except error.OpenAIError as err:
            raise HomeAssistantError(f"Error generating image: {err}") from err

        return response["data"][0]

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_IMAGE,
        render_image,
        schema=vol.Schema(
            {
                vol.Required("config_entry"): selector.ConfigEntrySelector(
                    {
                        "integration": DOMAIN,
                    }
                ),
                vol.Required(CONF_SPOTIFY_CLIENT_ID): cv.string,
                vol.Required(CONF_SPOTIFY_CLIENT_SECRET): cv.string,
                vol.Required("prompt"): cv.string,
                vol.Optional("size", default="512"): vol.In(("256", "512", "1024")),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OpenAI Conversation from a config entry."""
    try:
        await hass.async_add_executor_job(
            partial(
                openai.Engine.list,
                api_key=entry.data[CONF_API_KEY],
                request_timeout=10,
            )
        )
    except error.AuthenticationError as err:
        _LOGGER.error("Invalid API key: %s", err)
        return False
    except error.OpenAIError as err:
        raise ConfigEntryNotReady(err) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data[CONF_API_KEY]

    conversation.async_set_agent(hass, entry, OpenAIAgent(hass, entry))

    
    
    await api.setup(hass, entry)


    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload OpenAI."""
    hass.data[DOMAIN].pop(entry.entry_id)
    conversation.async_unset_agent(hass=hass, entry=entry)

    return True


class OpenAIAgent(conversation.AbstractConversationAgent):
    """OpenAI conversation agent."""


    

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry
        self.history: dict[str, list[dict]] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL        



    def handle_func_call(self, response):
        logging.info("handle_response()")
        available_functions = {
            "get_current_datetime": api.get_current_datetime,
            "search_music_tracks": api.search_music_tracks,
            "play_track": api.play_track,
        }

        function_name = response["function_call"]["name"]
        #check that function exists
        function_exists = False
        for function in available_functions:
            if function == function_name:
                function_exists = True
                break
        if not function_exists:
            return {
                "role": "function",
                "name": function_name,
                "content": "Unknown function",
            }
        
        function_args = json.loads(response["function_call"]["arguments"])

        logging.info("OpenAI wants to call %s with args %s" % (function_name, function_args))

        function_result = api.call(self.hass, function_name, function_args)

        my_response = {
                "role": "function",
                "name": function_name,
                "content": function_result,
            }
        
        logging.info("Function called and returned ", function_result)
        return my_response

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a sentence."""

        logging.info("async_process()")
        raw_prompt = self.entry.options.get(CONF_PROMPT, DEFAULT_PROMPT)
        model = self.entry.options.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL)
        max_tokens = self.entry.options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS)
        top_p = self.entry.options.get(CONF_TOP_P, DEFAULT_TOP_P)
        temperature = self.entry.options.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)

        if user_input.conversation_id in self.history:
            conversation_id = user_input.conversation_id
            messages = self.history[conversation_id]
        else:
            conversation_id = ulid.ulid()
            try:
                prompt = self._async_generate_prompt(raw_prompt)
            except TemplateError as err:
                _LOGGER.error("Error rendering prompt: %s", err)
                intent_response = intent.IntentResponse(language=user_input.language)
                intent_response.async_set_error(
                    intent.IntentResponseErrorCode.UNKNOWN,
                    f"Sorry, I had a problem with my template: {err}",
                )
                return conversation.ConversationResult(
                    response=intent_response, conversation_id=conversation_id
                )
            messages = [{"role": "system", "content": prompt}]

        messages.append({"role": "user", "content": user_input.text})

        _LOGGER.debug("Prompt for %s: %s", model, messages)

        safety_counter = 10
        while 1:
            safety_counter -= 1
            if safety_counter == 0:
                break
            try:
                result = await openai.ChatCompletion.acreate(
                    api_key=self.entry.data[CONF_API_KEY],
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    temperature=temperature,
                    user=conversation_id,
                    functions=api.get_functions(),
                )
            except error.OpenAIError as err:
                intent_response = intent.IntentResponse(language=user_input.language)
                intent_response.async_set_error(
                    intent.IntentResponseErrorCode.UNKNOWN,
                    f"Sorry, I had a problem talking to OpenAI: {err}",
                )
                return conversation.ConversationResult(
                    response=intent_response, conversation_id=conversation_id
                )

            _LOGGER.debug("Response %s", result)
            response = result["choices"][0]["message"]
            messages.append(response)
            if response.get("function_call"):
                #run handle_func_call in executor
                func_result = await self.hass.async_add_executor_job(self.handle_func_call, response)
                

                logging.info("Function returned: ", func_result)
                messages.append(func_result)
                logging.info("messages now: ", messages)
            else:
                break


        self.history[conversation_id] = messages

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response["content"])
        return conversation.ConversationResult(
            response=intent_response, conversation_id=conversation_id
        )

    def _async_generate_prompt(self, raw_prompt: str) -> str:
        """Generate a prompt for the user."""
        return template.Template(raw_prompt, self.hass).async_render(
            {
                "ha_name": self.hass.config.location_name,
            },
            parse_result=False,
        )
