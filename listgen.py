
import requests
import yaml
import re
import datetime as dt
import subprocess as sp
import logging
import os
from pathlib import Path
from uuid import uuid4
from pprint import pprint
from tqdm import tqdm
from typing import Any, Optional, Union, Callable

logging.basicConfig(level=logging.DEBUG)


class Jellyfin:
    def __init__(self, *, app_name: str, app_version: str, server_url: str, username: str, password: str):
        self.logger = logging.getLogger(__class__.__name__)

        self.app_name = app_name
        self.app_version = app_version
        self.server_url = server_url
        
        self.device_id = str(uuid4())
        self.headers = {"Authorization": f'MediaBrowser Client="other", Device="{self.app_name}", DeviceId="{self.device_id}", Version="{self.app_version}"'}
        self.authenticate_as_user(username, password)

    def authenticate_as_user(self, username: str, password: str) -> None:
        response = requests.post(
            self.join_url(self.server_url, "Users", "AuthenticateByName"),
            headers=self.headers,
            json={"username": username, "Pw": password}
        )
        response.raise_for_status()
        
        self.auth_token = response.json()["AccessToken"]
        self.user_id = response.json()["User"]["Id"]
        self.headers["Authorization"] += f', Token="{self.auth_token}"'
        self.logger.info(f"Authenticated token={self.auth_token} userid={self.user_id}")

    @staticmethod
    def join_url(*urls: str) -> str:
        urls_cleaned = [ re.sub(r"[^\:][\/]\/+", "/", str(url).strip("/")) for url in urls ]
        return "/".join(urls_cleaned)
        
    def get_item_metadata(self, item_id: str) -> dict:
        url = self.join_url(self.server_url, "Users", self.user_id, "Items", item_id)
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
        


class StaticPlaylist:
    def __init__(self, name: str, item_ids: list[str], sort_by: str = "order", sort_ascending: bool = True):
        self.name = name
        self.item_ids = item_ids
        self.sort_by = sort_by
        self.sort_ascending = sort_ascending
    
    def sort(self, jellyfin: Jellyfin) -> list[str]:
        item_ids = []
        ... #TODO
        return item_ids

    
class DynamicPlaylist:
    def __init__(self, name: str, filters: dict[str, Any] = {}, sort_by: str = "order", sort_ascending: bool = True):
        self.name = name
        self.filters = filters
        self.sort_by = sort_by
        self.sort_ascending = sort_ascending

    def bake(self, jellyfin: Jellyfin) -> StaticPlaylist:
        item_ids = []
        ... #TODO
        new_playlist = StaticPlaylist(self.name, item_ids, self.sort_by, self.sort_ascending)
        return new_playlist



class Conditional:
    def __init__(self, name: str, conditions: dict[str, Any] = {}):
        self.name = name
        self.conditions = conditions
    
    def is_true(self) -> bool:
        any_condition_failed = False
        ... #TODO
        return not any_condition_failed



class MediaBar:
    def __init__(self, *, filename: Path):
        self.logger = logging.getLogger(__class__.__name__)
        self.parse_file(filename)
    
    def parse_file(self, filename: Path) -> None:
        with open(filename, "r", encoding="utf-8", errors="replace") as file:
            filedata = yaml.load(file.read(), yaml.Loader)
        
        self.conditionals = self.parse_selection(filedata["selection"])
        self.playlists = self.parse_playlists(filedata["playlists"])

    def parse_selection(self, data: dict) -> list[Conditional]:
        unique_names = set()
        conditionals = []
        for entry in data:
            name = entry.pop("name")

            if name in unique_names:
                raise ValueError(f"Conditions for playlist '{name}' are already defined.")
            unique_names.add(name)
            
            new_conditional = Conditional(name, entry)
            conditionals.append(new_conditional)
        return conditionals

    def parse_playlists(self, data: dict) -> list[Union[StaticPlaylist, DynamicPlaylist]]:
        unique_names = set()
        playlists = []
        for entry in data:
            name = entry["name"]
            items = entry["items"]
            _type = items.pop("type")       # only conditions or item ids are left after popping the type
            
            if name in unique_names:
                raise ValueError(f"Playlist '{name}' is already defined.")
            unique_names.add(name)
            
            if _type == "static":
                new_playlist = StaticPlaylist(
                    name,
                    items["ids"],
                    entry.get("sort_by", "order"),
                    entry.get("sort_ascending", True)
                )
            
            elif _type == "dynamic":
                new_playlist = DynamicPlaylist(
                    name,
                    items,
                    entry.get("sort_by", "order"),
                    entry.get("sort_ascending", True)
                )
            
            else:
                raise ValueError(f"Unknown playlist type: {_type}")
            
            playlists.append(new_playlist)
        return playlists
    
    def get_selected(self) -> Conditional:
        selected = self.conditionals[-1]
        for conditional in self.conditionals:
            if conditional.is_true():
                selected = conditional
                break
        return selected
    
    def get_playlist(self, name: str) -> Union[StaticPlaylist, DynamicPlaylist]:
        for playlist in self.playlists:
            if playlist.name.lower() == name.lower():
                return playlist
        raise KeyError(f"Selected playlist '{name}' not defined.")
    
    def evaluate(self, jellyfin: Jellyfin) -> tuple[str, list[str]]:
        conditional = self.get_selected()
        playlist = self.get_playlist(conditional.name)
        static_playlist = playlist.bake(jellyfin) if isinstance(playlist, DynamicPlaylist) else playlist
        item_ids = static_playlist.sort(jellyfin)
        return conditional.name, item_ids
    
    @staticmethod
    def export_legacy_format(playlist_name: str, item_ids: list[str], filename: Path) -> None:
        with open(filename, "w", encoding="utf-8") as file:
            file.writelines([playlist_name])
            file.writelines(item_ids)



def main() -> None:
    jellyfin = Jellyfin(
        app_name="Media-Bar listgen.py",
        app_version="0.0.1",
        server_url="http://192.168.0.10:8096",
        username="api-user",        # this user needs access to all libraries that should be included in the list
        password=r"super-secret-password",
    )
    
    mediabar = MediaBar(filename=Path(r"mediabar.yaml"))
    playlist_name, item_ids = mediabar.evaluate(jellyfin)
    mediabar.export_legacy_format(playlist_name, item_ids, Path("list.txt"))


if __name__ == "__main__":
    main()
