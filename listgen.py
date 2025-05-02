
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
        
    def get_item(self, item_id: str) -> dict:
        # request a single item
        url = self.join_url(self.server_url, "Users", self.user_id, "Items", item_id)
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_items(self, item_ids: list[str]) -> dict:
        # request given items
        url = self.join_url(self.server_url, "Users", self.user_id, "Items")
        response = self.session.get(url, params={"ids": item_ids})
        response.raise_for_status()
        return response.json()

    def get_all_items(self, *, sort_by: str = "SortName", sort_ascending: bool = True, item_types: list[str] = ["Series", "Movies"], recursive: bool = True, parent_ids: list[str] = []) -> list[dict]:
        # request all items from all or given libraries (parent_ids)
        url = self.join_url(self.server_url, "Users", self.user_id, "Items")
        params = {
            "SortBy": sort_by,
            "SortOrder": "Ascending" if sort_ascending else "Descending",
            "IncludeItemTypes": ",".join(item_types),
            "Recursive": recursive,
            "ParentId": ",".join(parent_ids),
        }
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_all_libraries(self) -> list[dict]:
        # request all libraries
        url = self.join_url(self.server_url, "Library", "VirtualFolders")
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
        


class Interval:
    def __init__(self, interval: str):
        self.__interval = interval
        self.__parse_interval()
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(interval={self.__interval.__repr__()})"

    def __parse_interval(self) -> None:
        numeric_pattern = r"[0-9]+(\.[0-9]+)?"
        alphabetic_pattern = r"[a-z]+"
        date_pattern = r"[0-9]{4}_[0-9]{2}_[0-9]{2}"    # YYYY_MM_DD    (does not validate the date itself!)
        any_pattern = r"[^-]+"
        separator_pattern = r" *- *"
        
        # match interval type: closed, left-open, right-open, open, exact
        if re.fullmatch(any_pattern + separator_pattern + any_pattern, self.__interval):
            self.__interval_type = "closed"
        elif re.fullmatch(separator_pattern + any_pattern, self.__interval):
            self.__interval_type = "left-open"
        elif re.fullmatch(any_pattern + separator_pattern, self.__interval):
            self.__interval_type = "right-open"
        elif re.fullmatch(separator_pattern, self.__interval):
            self.__interval_type = "open"
        elif re.fullmatch(any_pattern, self.__interval):
            self.__interval_type = "exact"
        else:
            raise SyntaxError("Expected format: 'any-any' or 'any-' or '-any' or '-' or 'any'")

        # TODO: re-work the following using match-case syntax
        # https://stackoverflow.com/questions/74713626/how-to-use-structural-pattern-matching-match-case-with-regex

        # extract lower and/or upper bound values
        lower_bound, upper_bound, *_ = re.split(separator_pattern, self.__interval) + [None, None]

        # match data type: numeric, alphabetic, date
        numeric_lower_bound = re.fullmatch(numeric_pattern, lower_bound)
        numeric_upper_bound = re.fullmatch(numeric_pattern, upper_bound)
        alphabetic_lower_bound = re.fullmatch(alphabetic_pattern, lower_bound)
        alphabetic_upper_bound = re.fullmatch(alphabetic_pattern, upper_bound)
        date_lower_bound = re.fullmatch(date_pattern, lower_bound)
        date_upper_bound = re.fullmatch(date_pattern, upper_bound)
        
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
            elif date_lower_bound:
                if date_upper_bound:
                    self.__data_type = "date"
                    self.__lower_bound = dt.datetime.strftime(lower_bound, r"%Y_%m_%d")
                    self.__upper_bound = dt.datetime.strftime(upper_bound, r"%Y_%m_%d")
                else:
                    raise TypeError(f"Expected date data type for upper bound: {upper_bound}")
            else:
                raise TypeError(f"Expected same data type numeric, alphabetic or date for lower bound ({lower_bound}) and upper bound ({upper_bound}).")

            # lower bound higher than upper bound is allowed and inverts the condition
            self.__is_inverted = self.__lower_bound > self.__upper_bound
            
        elif self.__interval_type == "left-open":
            if numeric_upper_bound:
                self.__data_type = "numeric"
                self.__upper_bound = float(upper_bound)
            elif alphabetic_upper_bound:
                self.__data_type = "alphabetic"
                self.__upper_bound = str(upper_bound)
            elif date_upper_bound:
                self.__data_type = "date"
                self.__upper_bound = dt.datetime.strftime(upper_bound, r"%Y_%m_%d")
            else:
                raise TypeError(f"Expected data type numeric, alphabetic or date for upper bound: {upper_bound}")
            
        elif self.__interval_type == "right-open" or self.__interval_type == "exact":
            if numeric_lower_bound:
                self.__data_type = "numeric"
                self.__lower_bound = float(lower_bound)
            elif alphabetic_lower_bound:
                self.__data_type = "alphabetic"
                self.__lower_bound = str(lower_bound)
            elif date_lower_bound:
                self.__data_type = "date"
                self.__lower_bound = dt.datetime.strftime(lower_bound, r"%Y_%m_%d")
            else:
                raise TypeError(f"Expected data type numeric, alphabetic or date for lower bound: {lower_bound}")
        
        elif self.__interval_type == "open":
            self.__data_type = None
            self.__lower_bound = None
            self.__upper_bound = None
    
    def __contains__(self, value: Any) -> bool:
        return self.is_in_interval(value)
    
    def is_in_interval(self, value: Any) -> bool:
        # always in range without bounding
        if self.__interval_type == "open":
            return True
        
        # check if value is in range, depending on the interval type
        if self.__interval_type == "closed":
            if not self.__is_inverted:
                return self.__lower_bound <= value <= self.__upper_bound
            else:
                return self.__lower_bound >= value or value <= self.__upper_bound
        elif self.__interval_type == "left-open":
            return value <= self.__upper_bound
        elif self.__interval_type == "right-open":
            return self.__lower_bound <= value
        elif self.__interval_type == "exact":
            return self.__lower_bound == value
        raise ValueError(f"Unknown interval type '{self.__interval_type}'")



class StaticPlaylist:
    def __init__(self, *, name: str, item_ids: list[str], sort_by: str, sort_ascending: bool, sort_strict: bool):
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
        items_metadata = [ jellyfin.get_item(item_id) for item_id in self.item_ids ]

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
                        if (rating := metadata.get(self.sort_by)) is not None:
                            return float(rating)
                        if self.sort_by == "CriticRating":
                            return float(metadata.get("CommunityRating", 0)) * 10
                        elif self.sort_by == "CommunityRating":
                            return float(metadata.get("CriticRating", 0)) / 10

                case "PremiereDate" | "ProductionYear":
                    def sort_func(metadata):
                        if (dateyear := metadata.get(self.sort_by)) is not None:
                            return dateutil.parser.isoparse(dateyear if self.sort_by == "PremiereDate" else f"{dateyear}-01-01")
                        if self.sort_by == "PremiereDate":
                            return dateutil.parser.isoparse(f"{metadata.get('ProductionYear', '0001')}-01-01")
                        elif self.sort_by == "ProductionYear":
                            return dateutil.parser.isoparse(str(metadata.get("PremiereDate", "0001-01-01")))
        
        # apply the defined sort function
        items_metadata.sort(key=sort_func, reverse=not self.sort_ascending)
        item_ids = [ item["Id"] for item in items_metadata ]
        return item_ids


    
class DynamicPlaylist:
    def __init__(self, *, name: str, limit: int, include: dict[str, Any], exclude: dict[str, Any], sort_by: str, sort_ascending: bool, sort_strict: bool):
        self.name = name
        self.limit = limit
        self.include = include
        self.exclude = exclude
        self.sort_by = sort_by
        self.sort_ascending = sort_ascending
        self.sort_strict = sort_strict
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, filters={self.filters.__repr__()}, sort_by={self.sort_by.__repr__()}, sort_ascending={self.sort_ascending.__repr__()}, sort_strict={self.sort_strict.__repr__()})"

    @staticmethod
    def parse_list(value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, str):
            return re.split(r" *, *", value)
        elif isinstance(value, list):
            return [ str(el) for el in value ]
        raise TypeError(f"Expected comma separated strings or list: {value}")

    def compile(self, jellyfin: Jellyfin) -> StaticPlaylist:
        # create a static playlist based on a variety of filters

        # get all items
        if self.filters.get(""):
            pass

        item_ids = []
        new_playlist = StaticPlaylist(self.name, item_ids, self.sort_by, self.sort_ascending)
        return new_playlist



class Conditional:
    def __init__(self, name: str, conditions: dict[str, Any] = {}):
        self.name = name
        self.conditions = conditions
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, conditions={self.conditions.__repr__()})"
    
    def __bool__(self) -> bool:
        return self.is_true()
    
    def is_true(self) -> bool:
        if self.conditions.get("disabled", False):
            return False
        
        elif (hours := self.conditions.get("hours")) is not None:         # from hour 0 to 23
            if not Interval(hours).is_in_interval(dt.datetime.now().hour):
                return False
        elif (weekdays := self.conditions.get("weekdays")) is not None:   # from monday=1 to sunday=7
            if not Interval(weekdays).is_in_interval(dt.datetime.now().isoweekday()):
                return False
        elif (days := self.conditions.get("days")) is not None:           # from 1st day of the month up to max 31st day
            if not Interval(days).is_in_interval(dt.datetime.now().day):
                return False
        elif (weeks := self.conditions.get("weeks")) is not None:         # from 1st week of the year up to max 52nd week
            if not Interval(weeks).is_in_interval(dt.datetime.now().isocalendar()[1]):
                return False
        elif (months := self.conditions.get("months")) is not None:       # from january=1 to december=12
            if not Interval(months).is_in_interval(dt.datetime.now().month):
                return False
        elif (years := self.conditions.get("years")) is not None:         # from year 1 AD up to year 9999 AD 
            if not Interval(years).is_in_interval(dt.datetime.now().year):
                return False
        elif (dates := self.conditions.get("dates")) is not None:         # date format YYYY_MM_DD
            if not Interval(dates).is_in_interval(dt.datetime.now()):
                return False
        
        return True



class MediaBar:
    def __init__(self, *, filename: Path):
        self.logger = logging.getLogger(__class__.__name__)
        self.__filename = filename
        self.__parse_file()
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(filename={self.__filename.__repr__()}"
    
    def __parse_file(self) -> None:
        with open(self.__filename, "r", encoding="utf-8", errors="replace") as file:
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
            _type = items.pop("type")       # only filters or item ids are left after popping the type
            
            if name in unique_names:
                raise ValueError(f"Playlist '{name}' is already defined.")
            unique_names.add(name)
            
            if _type == "static":
                new_playlist = StaticPlaylist(
                    name = name,
                    ids = items["ids"],
                    sort_by = entry.get("sort_by", "order"),
                    sort_ascending = entry.get("sort_ascending", True),
                    sort_strict = entry.get("sort_strict", False),
                )
            
            elif _type == "dynamic":
                new_playlist = DynamicPlaylist(
                    name = name,
                    limit = items.get("limit", 20),
                    include = items.get("include", {}),
                    exclude = items.get("exclude", {}),
                    sort_by = entry.get("sort_by", "order"),
                    sort_ascending = entry.get("sort_ascending", True),
                    sort_strict = entry.get("sort_strict", False),
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
    def export_legacy_format(playlist_name: str, item_ids: list[str], filename: Path = Path("list.txt")) -> None:
        # the name of the playlist, followed by a list of item ids, one per line
        with open(filename, "w", encoding="utf-8") as file:
            file.writelines([playlist_name])
            file.writelines(item_ids)



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
    mediabar.export_legacy_format(playlist_name, item_ids)


if __name__ == "__main__":
    main()
