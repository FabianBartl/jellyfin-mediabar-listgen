
import dateutil.parser
import requests_cache
import yaml
import json
import random
import re
import dateutil.parser
import datetime as dt
import logging
from pathlib import Path
from uuid import uuid4
from pprint import pprint
from tqdm import tqdm
from typing import Any, Optional, Union, Callable

logging.basicConfig(level=logging.DEBUG)



class Jellyfin:
    def __init__(self, *, app_name: str, app_version: str, server_url: str, username: str, password: str, headers: dict = {}):
        self.logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")

        self.app_name = app_name
        self.app_version = app_version
        self.server_url = server_url
        self.device_id = str(uuid4()).split("-")[0]
        
        # create cached session with 1 hour lifespan and authorize as user to get a token
        self.session = requests_cache.CachedSession(
            f"{self.logger.name}.cache",
            expire_after=dt.timedelta(hours=1),
        )
        self.session.headers.update(headers)
        self.session.headers.update({
            "Authorization": f'MediaBrowser Client="other", Device="{self.app_name}", DeviceId="{self.device_id}", Version="{self.app_version}"',
        })
        self.__authenticate_as_user(username, password)
        
    def __repr__(self) -> str:
        return f"{__class__.__name__}(app_name={self.app_name.__repr__()}, app_version={self.app_version.__repr__()}, server_url={self.server_url.__repr__()}, username=***, password=***, headers={self.headers.__repr__()})\nuserid={self.user_id.__repr__()}, token={self.auth_token.__repr__()}"

    def __authenticate_as_user(self, username: str, password: str) -> None:
        response = self.session.post(
            self.join_url(self.server_url, "Users", "AuthenticateByName"),
            json={"username": username, "Pw": password}
        )
        response.raise_for_status()
        
        self.auth_token = response.json()["AccessToken"]
        self.user_id = response.json()["User"]["Id"]
        self.session.headers["Authorization"] += f', Token="{self.auth_token}"'
        self.logger.info(f"Authenticated as userid={self.user_id} with token={self.auth_token}")

    @staticmethod
    def join_url(*urls: str) -> str:
        return re.sub(r"[^\:][\/]\/+", "/", "/".join(urls))
        
    def get_item_metadata(self, item_id: str) -> dict:
        # request metadata of a single item
        url = self.join_url(self.server_url, "Users", self.user_id, "Items", item_id)
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
        


class RangeFilter:
    def __init__(self, _range: str):
        self.range = _range
        self.parse_range()
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(_range={self.range.__repr__()})"

    def parse_range(self) -> None:
        numeric_pattern = r"[0-9]+(\.[0-9]+)?"
        alphabetic_pattern = r"[a-z]+"
        any_pattern = r"[^-]+"
        separator_pattern = r" *- *"
        
        # match interval type: closed, left-open, right-open
        if re.match(any_pattern + separator_pattern + any_pattern, self.range):
            self.__interval_type = "closed"
        elif re.match(separator_pattern + any_pattern, self.range):
            self.__interval_type = "left-open"
        elif re.match(any_pattern + separator_pattern, self.range):
            self.__interval_type = "right-open"
        else:
            raise SyntaxError("Expected format: 'any-any' or 'any-' or '-any'")

        # match data type: numeric, alphabetic
        # and extract lower and/or upper bound values
        lower_bound, upper_bound = re.split(separator_pattern, self.range)
        numeric_lower_bound, numeric_upper_bound = re.match(numeric_pattern, lower_bound), re.match(numeric_pattern, upper_bound)
        alphabetic_lower_bound, alphabetic_upper_bound = re.match(alphabetic_pattern, lower_bound), re.match(alphabetic_pattern, upper_bound)
        
        if self.__interval_type == "closed":
            if numeric_lower_bound:
                if numeric_upper_bound:
                    self.__data_type = "numeric"
                    self.__lower_bound = float(lower_bound)
                    self.__upper_bound = float(upper_bound)
                else:
                    raise TypeError(f"Expected numeric data type for upper bound: {upper_bound}")
            elif alphabetic_lower_bound:
                if alphabetic_upper_bound:
                    self.__data_type = "alphabetic"
                    self.__lower_bound = str(lower_bound)
                    self.__upper_bound = str(upper_bound)
                else:
                    raise TypeError(f"Expected alphabetic data type for upper bound: {upper_bound}")
            else:
                raise TypeError(f"Expected same data type numeric or alphabetic for lower bound ({lower_bound}) and upper bound ({upper_bound}).")

            # lower bound higher than upper bound is allowed and inverts the condition
            self.__is_inverted = self.__lower_bound > self.__upper_bound
            
        elif self.__interval_type == "left-open":
            if numeric_upper_bound:
                self.__data_type = "numeric"
                self.__upper_bound = float(upper_bound)
            elif alphabetic_upper_bound:
                self.__data_type = "alphabetic"
                self.__upper_bound = str(upper_bound)
            else:
                raise TypeError(f"Expected data type numeric or alphabetic for upper bound: {upper_bound}")
            
        elif self.__interval_type == "right-open":
            if numeric_lower_bound:
                self.__data_type = "numeric"
                self.__lower_bound = float(lower_bound)
            elif alphabetic_lower_bound:
                self.__data_type = "alphabetic"
                self.__lower_bound = str(lower_bound)
            else:
                raise TypeError(f"Expected data type numeric or alphabetic for lower bound: {lower_bound}")

    def is_in_range(self, value: Union[int, float, str]) -> bool:
        # ensure data type
        if self.__data_type == "numeric":
            value = float(value)
        elif self.__data_type == "alphabetic":
            value = str(value)
        else:
            raise ValueError(f"Unknown data type '{self.__data_type}'")
        
        # check if value is in range, depending on the interval type and inversion
        if self.__interval_type == "closed":
            if not self.__is_inverted:
                return self.__lower_bound <= value <= self.__upper_bound
            else:
                return self.__lower_bound <= value >= self.__upper_bound
        elif self.__interval_type == "left-open":
            return value <= self.__upper_bound
        elif self.__interval_type == "right-open":
            return self.__lower_bound <= value
        raise ValueError(f"Unknown interval type '{self.__interval_type}'")
        


class StaticPlaylist:
    def __init__(self, name: str, item_ids: list[str], sort_by: str = "order", sort_ascending: bool = True, sort_strict: bool = False):
        self.name = name
        self.item_ids = sorted(set(item_ids), key=item_ids.index)       # remove duplicate item ids
        self.sort_by = sort_by
        self.raise_for_unsupported_sort_by()
        self.sort_ascending = sort_ascending
        self.sort_strict = sort_strict
        
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, item_ids={self.item_ids.__repr__()}, sort_by={self.sort_by.__repr__()}, sort_ascending={self.sort_ascending.__repr__()}, sort_strict={self.sort_strict.__repr__()})"

    def raise_for_unsupported_sort_by(self) -> None:
        self.__supported_sort_by = {                                                # data types:
            "order", "random",                                                      #   any
            "Name", "OriginalTitle", "SortName",                                    #   string
            "DateCreated", "PremiereDate",                                          #   datetime
            "CriticRating", "CommunityRating", "RunTimeTicks", "ProductionYear",    #   number
        }
        if self.sort_by not in self.__supported_sort_by:
            raise ValueError(f"Can't sort by '{self.sort_by}'")

    @staticmethod
    def dict_priority_get(data: dict[str, Any], default_value: Any, primary_key: str, *secondary_keys: str) -> Any:
        # returns value of the first valid dictionary key, else the set default value
        for key in [primary_key, *secondary_keys]:
            value = data.get(key, ...)
            if value is not ...:
                return value
        return default_value
    
    def sort(self, jellyfin: Jellyfin) -> list[str]:
        self.raise_for_unsupported_sort_by()
        match self.sort_by:
            case "order":
                return self.item_ids[:] if self.sort_ascending else self.item_ids[::-1]
            case "random":
                item_ids = self.item_ids[:]
                random.shuffle(item_ids)
                return item_ids
        
        # request item metadata from jellyfin one by one
        # not in a single bulk request, otherwise the cache functionality won't work as good
        items_metadata = [ jellyfin.get_item_metadata(item_id) for item_id in self.item_ids ]

        # define strict sorting function
        match self.sort_by:
            case "Name" | "OriginalTitle" | "SortName":
                sort_func = lambda metadata: str(metadata.get(self.sort_by, ""))
            case "DateCreated" | "PremiereDate":
                sort_func = lambda metadata: dateutil.parser.isoparse(str(metadata.get(self.sort_by, "0001-01-01")))                    
            case "CriticRating" | "CommunityRating" | "RunTimeTicks" | "ProductionYear":
                sort_func = lambda metadata: float(metadata.get(self.sort_by, 0))

        if not self.sort_strict:
            # overwrite strict sorting function if there is one
            match self.sort_by:
                case "Name" | "OriginalTitle" | "SortName":
                    sort_func = lambda metadata: str(self.dict_priority_get(metadata, "", self.sort_by, "SortName", "Name"))
                
                case "CriticRating" | "CommunityRating":
                    def sort_func(metadata):
                        if rating := metadata.get(self.sort_by, ...) is not ...:
                            return float(rating)
                        if self.sort_by == "CriticRating":
                            return float(metadata.get("CommunityRating", 0)) * 10
                        elif self.sort_by == "CommunityRating":
                            return float(metadata.get("CriticRating", 0)) / 10

                case "PremiereDate" | "ProductionYear":
                    def sort_func(metadata):
                        if dateyear := metadata.get(self.sort_by, ...) is not ...:
                            return dateutil.parser.isoparse(dateyear if self.sort_by == "PremiereDate" else f"{dateyear}-01-01")
                        if self.sort_by == "PremiereDate":
                            return dateutil.parser.isoparse(f"{metadata.get('ProductionYear', '0001')}-01-01")
                        elif self.sort_by == "ProductionYear":
                            return dateutil.parser.isoparse(str(metadata.get("PremiereDate", "0001-01-01")))
        
        items_metadata.sort(key=sort_func, reverse=not self.sort_ascending)
        item_ids = [ item["Id"] for item in items_metadata ]
        return item_ids


    
class DynamicPlaylist:
    def __init__(self, name: str, filters: dict[str, Any] = {}, sort_by: str = "order", sort_ascending: bool = True, sort_strict: bool = False):
        self.name = name
        self.filters = filters
        self.sort_by = sort_by
        self.sort_ascending = sort_ascending
        self.sort_strict = sort_strict
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, filters={self.filters.__repr__()}, sort_by={self.sort_by.__repr__()}, sort_ascending={self.sort_ascending.__repr__()}, sort_strict={self.sort_strict.__repr__()})"

    def compile(self, jellyfin: Jellyfin) -> StaticPlaylist:
        # create a static playlist based on a variety of filters
        item_ids = []
        ... #TODO
        new_playlist = StaticPlaylist(self.name, item_ids, self.sort_by, self.sort_ascending)
        return new_playlist



class Conditional:
    def __init__(self, name: str, conditions: dict[str, Any] = {}):
        self.name = name
        self.conditions = conditions
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, conditions={self.conditions.__repr__()})"
    
    def is_true(self) -> bool:
        if self.conditions.get("disabled", False):
            return False
        
        elif hours := self.conditions.get("hours"):         # 24-hour format
            if not RangeFilter(hours).is_in_range(dt.datetime.now().hour):
                return False
        elif weekdays := self.conditions.get("weekdays"):   # from monday=1 to sunday=7
            if not RangeFilter(weekdays).is_in_range(dt.datetime.now().isoweekday()):
                return False
        elif days := self.conditions.get("days"):           # from 1st day of the month up to max 32th day
            if not RangeFilter(days).is_in_range(dt.datetime.now().day):
                return False
        elif weeks := self.conditions.get("weeks"):         # from 1st week of the year up to max 52th week
            if not RangeFilter(weeks).is_in_range(dt.datetime.now().isocalendar()[1]):
                return False
        elif months := self.conditions.get("months"):       # from january=1 to december=12
            if not RangeFilter(months).is_in_range(dt.datetime.now().month):
                return False
        elif years := self.conditions.get("years"):         # from year 1 AD up to year 9999 AD 
            if not RangeFilter(years).is_in_range(dt.datetime.now().year):
                return False
        
        return True



class MediaBar:
    def __init__(self, *, filename: Path):
        self.logger = logging.getLogger(__class__.__name__)
        self.__filename = filename
        self.__parse_file(filename)
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(filename={self.__filename.__repr__()}"
    
    def __parse_file(self, filename: Path) -> None:
        with open(filename, "r", encoding="utf-8", errors="replace") as file:
            filedata = yaml.load(file.read(), yaml.Loader)
        
        # all playlist names are converted to lower case when imported
        # altough the StaticPlaylist/DynamicPlaylist and Conditional classes don't requiere lower case names
        self.conditionals = self.__parse_selection(filedata["selection"])
        self.playlists = self.__parse_playlists(filedata["playlists"])

    def __parse_selection(self, data: dict) -> list[Conditional]:
        unique_names = set()
        conditionals = []
        for entry in data:
            name = entry.pop("name").lower()

            if name in unique_names:
                raise ValueError(f"Conditions for playlist '{name}' are already defined.")
            unique_names.add(name)
            
            new_conditional = Conditional(name, entry)
            conditionals.append(new_conditional)
        return conditionals

    def __parse_playlists(self, data: dict) -> list[Union[StaticPlaylist, DynamicPlaylist]]:
        unique_names = set()
        playlists = []
        for entry in data:
            name = entry["name"].lower()
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
                    entry.get("sort_ascending", True),
                    entry.get("sort_strict", False),
                )
            
            elif _type == "dynamic":
                new_playlist = DynamicPlaylist(
                    name,
                    items,
                    entry.get("sort_by", "order"),
                    entry.get("sort_ascending", True),
                    entry.get("sort_strict", False),
                )
            
            else:
                raise ValueError(f"Unknown playlist type '{_type}'")
            
            playlists.append(new_playlist)
        return playlists
    
    def get_selected(self) -> Conditional:
        # returns first Conditional where all conditions are met, otherwise the last one
        selected = self.conditionals[-1]
        for conditional in self.conditionals:
            if conditional.is_true():
                selected = conditional
                break
        return selected
    
    def get_playlist(self, name: str) -> Union[StaticPlaylist, DynamicPlaylist]:
        # returns first Playlist with matching name
        for playlist in self.playlists:
            if playlist.name.lower() == name.lower():
                return playlist
        raise KeyError(f"Selected playlist '{name}' not defined.")
    
    def evaluate(self, jellyfin: Jellyfin) -> tuple[str, list[str]]:
        # evaluates the whole imported config and returns the selected playlist name and sorted playlist item ids
        conditional = self.get_selected()
        playlist = self.get_playlist(conditional.name)
        static_playlist = playlist.compile(jellyfin) if isinstance(playlist, DynamicPlaylist) else playlist
        item_ids = static_playlist.sort(jellyfin)
        return conditional.name, item_ids
    
    @staticmethod
    def export_legacy_format(playlist_name: str, item_ids: list[str], filename: Path) -> None:
        # the name of the playlist, followed by a list of item ids, one per line
        with open(filename, "w", encoding="utf-8") as file:
            file.writelines([playlist_name])
            file.writelines(item_ids)



def test() -> None:
    mediabar = MediaBar(filename=Path(r"mediabar.yaml"))
    pprint(mediabar.conditionals)
    pprint(mediabar.playlists)
    
    playlist: StaticPlaylist = mediabar.get_playlist("featured")
    print(playlist.name, playlist.sort_by, playlist.sort_ascending)
    pprint(playlist.item_ids)
    
    jellyfin = Jellyfin(
        app_name="Media-Bar listgen.py",
        app_version="0.0.1",
        server_url="http://192.168.0.10:8096",
        username="api-user",        # this user needs access to all libraries that should be included in the list
        password=r"C5n0RS^8*Uv0D$I0ZEEr2D3Dn&QO&%b2",
    )
    item_ids = playlist.sort(jellyfin)
    pprint(item_ids)
    
    

def main() -> None:
    jellyfin = Jellyfin(
        app_name="Media-Bar listgen.py",
        app_version="0.0.1",
        server_url="http://192.168.0.10:8096",
        username="api-user",        # this user needs access to all libraries that should be included in the list
        password=r"C5n0RS^8*Uv0D$I0ZEEr2D3Dn&QO&%b2",
    )
    
    mediabar = MediaBar(filename=Path(r"mediabar.yaml"))
    playlist_name, item_ids = mediabar.evaluate(jellyfin)
    mediabar.export_legacy_format(playlist_name, item_ids, Path("list.txt"))


if __name__ == "__main__":
    main()
