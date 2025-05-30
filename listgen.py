
"""
License: MIT
Author: Fabian Bartl
Repository: https://github.com/FabianBartl/jellyfin-mediabar-listgen
Last update: 2025-05-05
"""


import logging
logging.basicConfig(level=logging.DEBUG)

import requests_cache
import dateutil.parser
import yaml
import json
import random
import re
import time
import datetime as dt
import uuid
import socket

from pathlib import Path
from pprint import pprint
from typing import Any, Optional, Union, Callable, Iterable
from tqdm import tqdm

from colorama import init as colorama_init
from colorama import Fore, Back, Style
colorama_init(autoreset=True)


class Toolkit:
    @staticmethod
    def join_url(*urls: str) -> str:
        return re.sub(r"[^\:][\/]\/+", "/", "/".join(urls))

    @staticmethod
    def dict_priority_get(data: dict[str, Any], default_value: Any, primary_key: str, *secondary_keys: str) -> Any:
        # returns value of the first valid dictionary key, else the set default value
        for key in [primary_key, *secondary_keys]:
            value = data.get(key, ...)
            if value is not ...:
                return value
        return default_value

    @staticmethod
    def dict_get_all(data: Iterable[dict], key: Any, default: Optional[Any] = None, discard: bool = False) -> list[Any]:
        values = []
        for entry in data:
            if key not in entry and not discard:
                values.append(default)
            else:
                values.append(entry.get(key, default))
        return values

    @staticmethod
    def parse_list(value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, str):
            return re.split(r" *, *", value)
        elif isinstance(value, list):
            return [ str(el) for el in value ]
        raise TypeError(f"Expected comma separated strings or list: {value}")
    
    @staticmethod
    def match_fuzzy(fuzzy: str, available: Iterable, get_func: Callable, default: Any = None, pattern: re.Pattern = r"[a-z0-9]+") -> Any:
        mapping = { re.findall(pattern, get_func(entry).lower())[0]: entry for entry in available }
        return mapping.get(re.findall(pattern, fuzzy.lower())[0], default)
    
    @staticmethod
    def is_none(value: Any) -> bool:
        return value is None
    
    @staticmethod
    def limit(items: Union[list,set], limit: Optional[int] = None, logger: Optional[logging.Logger] = None) -> list:
        if limit is None:
            return items
        if isinstance(logger, logging.Logger):
            logger.debug("limit number of items to %d", limit)
        return list(items)[:limit]

    @staticmethod
    def contains_any(setlike: Iterable, setlike_or_element: Union[Iterable, Any]) -> bool:
        if isinstance(setlike_or_element, (set, list, Iterable)):
            for element in set(setlike_or_element):
                if element in setlike:
                    return True
            return False
        return setlike_or_element in setlike



class Jellyfin:
    def __init__(self, *, server_url: str, username: str, password: str, headers: dict = {}):
        self.__logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")

        self.app_name = "Jellyfin Media-Bar listgen"
        self.app_version = "0.0.1"
        self.__server_url = server_url
        
        # generate session persistent and device-dependent device name and id
        self.__device = socket.gethostname()
        self.__device_id = str(uuid.UUID(int=uuid.getnode())).replace("-", "")
        self.__logger.debug("generated device='%s' and device_id='%s'", self.__device, self.__device_id)
        
        # create cached session with 1 hour lifespan and authenticate as a user with a password to get a token
        self.__session = requests_cache.CachedSession(
            cache_name=f"{self.__logger.name}.cache",
            expire_after=dt.timedelta(hours=1),
        )
        self.__session.headers.update(headers)
        self.__session.headers.update({
            "Authorization": f'MediaBrowser Client="{self.app_name}", Device="{self.__device}", DeviceId="{self.__device_id}", Version="{self.app_version}"',
        })
        self.__authenticate_as_user(username, password)
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(server_url={self.__server_url.__repr__()}, username=***, password=***, headers={self.headers.__repr__()})\nuserid={self.__user_id.__repr__()}, token={self.__auth_token.__repr__()}"

    def __authenticate_as_user(self, username: str, password: str) -> None:
        response = self.__session.post(
            Toolkit.join_url(self.__server_url, "Users", "AuthenticateByName"),
            json={"username": username, "Pw": password}
        )
        response.raise_for_status()
        
        self.__auth_token = response.json()["AccessToken"]
        self.__user_id = response.json()["User"]["Id"]
        self.__session.headers["Authorization"] += f', Token="{self.__auth_token}"'
        self.__logger.info("authenticated as userid=%s and got token=%s", self.__user_id, self.__auth_token)

    def get(self, url: str, url_params: dict[str, Any] = {}, *, include_userid: bool = False, include_sort: bool = False) -> Any:
        if "://" not in url and not url.startswith(self.__server_url):
            url = Toolkit.join_url(self.__server_url, url)
        params = {}
        if include_userid:
            params["userId"] = self.__user_id
        if include_sort:
            params["SortBy"] = "SortName,ProductionYear"
            params["SortOrder"] = "Ascending"
            params["Recursive"] = "true"
        params.update(url_params)
        response = self.__session.get(url, params)
        response.raise_for_status()
        return response.json()
    
    def get_user(self, user_id: str) -> dict:
        return self.get(Toolkit.join_url("Users", user_id))
        
    def get_item(self, item_id: str) -> dict:
        return self.get(Toolkit.join_url("Users", self.__user_id, "Items", item_id))

    def get_items(self, item_ids: list[str], batch_size: int = 60) -> list[dict]:
        items = []
        # split up item ids into chunks to prevent to long urls
        item_ids_chunks = [ item_ids[ind:ind+batch_size] for ind in range(0, len(item_ids), batch_size) ]
        for chunk in item_ids_chunks:
            items.extend(self.get(Toolkit.join_url("Users", self.__user_id, "Items"), {"ids": ",".join(chunk)}).get("Items", []))
        return items

    def get_all_items(self, **url_params: Any) -> list[dict]:
        return self.get(Toolkit.join_url("Users", self.__user_id, "Items"), url_params, include_sort=True).get("Items", [])
    
    def get_all_libraries(self) -> list[dict]:
        return self.get("UserViews", include_userid=True).get("Items", [])
    
    def get_all_genres(self, **url_params: Any) -> list[dict]:
        return self.get("Genres", url_params, include_userid=True, include_sort=True).get("Items", [])
        


class Interval:
    def __init__(self, interval: str):
        self.__logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")
        self.__interval = str(interval)
        self.__parse_interval()
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(interval={self.__interval.__repr__()})"

    def __parse_interval(self) -> None:
        self.__data_type = None
        self.__lower_bound = None
        self.__upper_bound = None

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
        
        self.__logger.debug("matched %s interval type", self.__interval_type)

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
        
        _is_inverted = False
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
            _is_inverted = self.__lower_bound > self.__upper_bound
            
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
        
        self.__logger.debug("matched %s data type", self.__data_type)

        self.__logger.debug(
            "parsed interval '%s' as %s%s interval from %s to %s", 
            self.__interval, "inverted" if _is_inverted else "", self.__interval_type, self.__lower_bound, self.__upper_bound
        )
    
    def __contains__(self, value: Any) -> bool:
        return self.contains(value)
    
    def contains(self, value: Any) -> bool:
        # always in range without bounding
        if self.__interval_type == "open":
            return True
        
        # check if value is in range, depending on the interval type
        if self.__interval_type == "closed":
            # lower bound higher than upper bound is allowed and inverts the condition
            if self.__lower_bound > self.__upper_bound:
                return self.__lower_bound <= value or value <= self.__upper_bound
            else:
                return self.__lower_bound <= value <= self.__upper_bound
        
        elif self.__interval_type == "left-open":
            return value <= self.__upper_bound
        elif self.__interval_type == "right-open":
            return self.__lower_bound <= value
        
        elif self.__interval_type == "exact":
            return self.__lower_bound == value

        raise ValueError(f"Unknown interval type '{self.__interval_type}'")



class StaticPlaylist:
    def __init__(self, *, name: str, item_ids: list[str], sort_by: str, sort_ascending: bool, sort_strict: bool, limit: Optional[int] = None):
        self.__logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")

        self.name = name
        self.item_ids = sorted(set(item_ids), key=item_ids.index)       # remove duplicate item ids
        self.sort_by = sort_by
        self.raise_for_unsupported_sort_by()
        self.sort_ascending = sort_ascending
        self.sort_strict = sort_strict
        self.limit = limit
        
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, item_ids={self.item_ids.__repr__()}, sort_by={self.sort_by.__repr__()}, sort_ascending={self.sort_ascending.__repr__()}, sort_strict={self.sort_strict.__repr__()}, limit={self.limit.__repr__()})"

    def raise_for_unsupported_sort_by(self) -> None:
        self.__supported_sort_by = {                                                # data types:
            "order", "random",                                                      #   any
            "Name", "OriginalTitle", "SortName",                                    #   string
            "DateCreated", "PremiereDate",                                          #   datetime
            "CriticRating", "CommunityRating", "RunTimeTicks", "ProductionYear",    #   number
        }
        if self.sort_by not in self.__supported_sort_by:
            raise ValueError(f"Can't sort by '{self.sort_by}'")

    def sort(self, jellyfin: Jellyfin) -> list[str]:
        self.raise_for_unsupported_sort_by()
        self.__logger.debug("sort static playlist '%s' by '%s'", self.name, self.sort_by)
        
        match self.sort_by:
            case "order":
                item_ids = self.item_ids[:] if self.sort_ascending else self.item_ids[::-1]
                return Toolkit.limit(item_ids, self.limit, self.__logger)
            case "random":
                item_ids = self.item_ids[:]
                random.shuffle(item_ids)
                return Toolkit.limit(item_ids, self.limit, self.__logger)
        
        # request item metadata from jellyfin
        items_metadata = jellyfin.get_items(self.item_ids)
        self.__logger.debug("fetched %d items", len(items_metadata))

        # define strict sorting function
        sort_func = None

        match self.sort_by:
            case "Name" | "OriginalTitle" | "SortName":
                sort_func = lambda metadata: str(metadata.get(self.sort_by, ""))
            case "DateCreated" | "PremiereDate":
                sort_func = lambda metadata: dateutil.parser.isoparse(str(metadata.get(self.sort_by, "0001-01-01")))                    
            case "CriticRating" | "CommunityRating" | "RunTimeTicks" | "ProductionYear":
                sort_func = lambda metadata: float(metadata.get(self.sort_by, 0))
        
        if sort_func is None:
            raise LookupError("missing sort_func")
        
        _strict_sort_func = sort_func
        self.__logger.debug("strict sorting function defined")
        
        if not self.sort_strict:
            # overwrite strict sorting function if there is one
            match self.sort_by:
                case "Name" | "OriginalTitle" | "SortName":
                    sort_func = lambda metadata: str(Toolkit.dict_priority_get(metadata, "", self.sort_by, "SortName", "Name"))
                
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

            if sort_func is not _strict_sort_func:
                self.__logger.debug("strict sorting function replaced")
            else:
                self.__logger.debug("no non-strict sorting function found")
        
        # apply the defined sort function
        items_metadata.sort(key=sort_func, reverse=not self.sort_ascending)
        items_metadata = Toolkit.limit(items_metadata, self.limit, self.__logger)
        self.__logger.debug("sorted items order: %s", [ f"{item['Id']}: {item['Name']}" for item in items_metadata ])
        
        item_ids = Toolkit.dict_get_all(items_metadata, "Id")
        return item_ids


    
class DynamicPlaylist:
    def __init__(self, *, name: str, limit: int, include: dict[str, Any], exclude: dict[str, Any], sort_by: str, sort_ascending: bool, sort_strict: bool):
        self.__logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")

        self.name = name
        self.limit = limit
        self.include = include
        self.exclude = exclude
        self.sort_by = sort_by
        self.sort_ascending = sort_ascending
        self.sort_strict = sort_strict
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, limit={self.limit.__repr__()}, include={self.include.__repr__()}, exclude={self.exclude.__repr__()}, sort_by={self.sort_by.__repr__()}, sort_ascending={self.sort_ascending.__repr__()}, sort_strict={self.sort_strict.__repr__()})"

    def compile(self, jellyfin: Jellyfin) -> StaticPlaylist:
        self.__logger.debug("compile dynamic playlist '%s'", self.name)

        # START OF PARSING FILTERS FOR ITEM COLLECTION
        # ============================================

        # create a static playlist based on a variety of filters
        get_all_items__url_params = {}

        # get allowed item types list to include by default all
        item_types = set(map(str.lower, ["AggregateFolder", "BoxSet", "CollectionFolder", "Episode", "Movie", "Season", "Series", "Video"]))
        if (include_item_types := self.include.get("item_types")) is not None:
            item_types &= set(map(str.lower, Toolkit.parse_list(include_item_types)))
        elif (exclude_item_types := self.exclude.get("item_types")) is not None:
            item_types -= set(map(str.lower, Toolkit.parse_list(exclude_item_types)))
        get_all_items__url_params["includeItemTypes"] = ",".join(item_types)

        self.__logger.debug("include item_types: %s", item_types)

        # get genres list to include by default all
        genres = None
        jellyfin_genres = jellyfin.get_all_genres()
        self.__logger.debug("available genres: %s", Toolkit.dict_get_all(jellyfin_genres, "Name"))

        match_genre_name = lambda genre: Toolkit.match_fuzzy(genre, jellyfin_genres, lambda genre: genre["Name"], "")
        
        if (include_genres := self.include.get("genres")) is not None:
            genres = filter(len, map(match_genre_name, Toolkit.parse_list(include_genres)))
        elif (exclude_genres := self.exclude.get("genres")) is not None:
            genres = filter(len, map(match_genre_name, Toolkit.parse_list(exclude_genres)))
            genres = set(jellyfin_genres) - set(genres)

        if genres is not None and genres is not []:
            genres = list(genres)
            get_all_items__url_params["genreIds"] = "|".join(Toolkit.dict_get_all(genres, "Id"))
            self.__logger.debug("include genres: %s", Toolkit.dict_get_all(genres, "Name"))

        # get allowed library types list to include by default all
        library_types = set(map(str.lower, ["unknown", "movies", "tvshows", "homevideos", "boxsets", "playlists", "folders"]))
        self.__logger.debug("available library types: %s", library_types)

        if (include_library_types := self.include.get("library_types")) is not None:
            library_types &= set(map(str.lower, filter(bool, Toolkit.parse_list(include_library_types))))
        elif (exclude_library_types := self.exclude.get("library_types")) is not None:
            library_types -= set(map(str.lower, filter(bool, Toolkit.parse_list(exclude_library_types))))

        self.__logger.debug("include library_types: %s", library_types)

        # get libraries list to include by default all
        libraries = list(filter(lambda library: library["CollectionType"].lower() in library_types, jellyfin.get_all_libraries()))
        self.__logger.debug("available libraries: %s", [ f"{lib['Id']}: {lib['Name']}" for lib in libraries ])
 
        library_ids = set(Toolkit.dict_get_all(libraries, "Id"))
        if (include_library_ids := self.include.get("library_ids")) is not None:
            library_ids &= set(filter(bool, Toolkit.parse_list(include_library_ids)))
        elif (exclude_library_ids := self.exclude.get("library_ids")) is not None:
            library_ids -= set(filter(bool, Toolkit.parse_list(exclude_library_ids)))

        self.__logger.debug("include library_ids: %s", library_ids)

        # START OF COLLECTING ALL ITEMS BASED ON COLLECTED FILTERS LIKE: LIBRARY, MEDIA TYPE AND GENRE
        # ===========================================================================================

        # get all items from all filtered libraries
        all_items = []
        for library_id in library_ids:
            new_items = jellyfin.get_all_items(parentId=library_id, filters="IsNotFolder", **get_all_items__url_params)
            self.__logger.debug("fetched %d items from library id %s", len(new_items), library_id)
            all_items.extend(new_items)
        
        self.__logger.debug("fetched %d items", len(all_items))

        # remove items, to exclude always
        if (exclude_item_ids := self.exclude.get("item_ids")) is not None:
            exclude_item_ids = set(filter(bool, Toolkit.parse_list(exclude_item_ids)))
            all_items = list(filter(lambda item: item["Id"] not in exclude_item_ids, all_items))
            self.__logger.debug("exclude item_ids: %s", exclude_item_ids)

        # remove items of excluded item type
        _len_all_items_before = len(all_items)
        
        all_items = list(filter(lambda item: item.get("MediaType", "").lower() in item_types or item.get("Type", "").lower(), all_items))
        self.__logger.debug("removed %d items of excluded item type", _len_all_items_before - len(all_items))

        # START OF PARSING FILTERS FOR FILTERING ITEMS OUT
        # ================================================

        includes = {}
        excludes = {}
        
        # get years interval or list
        if (include_years := self.include.get("years")) is not None:
            try:
                includes["years"] = Interval(include_years)
            except SyntaxError:
                includes["years"] = list(filter(int, Toolkit.parse_list(include_years)))
            self.__logger.debug("include years: %s", includes["years"])
        elif (exclude_years := self.exclude.get("years")) is not None:
            try:
                excludes["years"] = Interval(exclude_years)
            except SyntaxError:
                excludes["years"] = list(filter(int, Toolkit.parse_list(exclude_years)))
            self.__logger.debug("exclude years: %s", excludes["years"])
            
        # get all list filters
        list_filter_names = ["tags", "people_ids"]
        for filter_name in list_filter_names:
            
            if (include_filter := self.include.get(filter_name)) is not None:
                includes[filter_name] = set(map(str.lower, filter(bool, Toolkit.parse_list(include_filter))))
                self.__logger.debug("include %s: %s", filter_name, includes[filter_name])
            elif (exclude_filter := self.exclude.get(filter_name)) is not None:
                excludes[filter_name] = set(map(str.lower, filter(bool, Toolkit.parse_list(exclude_filter))))
                self.__logger.debug("exclude %s: %s", filter_name, excludes[filter_name])

        # get all interval filters
        interval_filter_names = [
            "startwith_name", "runtime", "people_ids",
            "community_rating", "critic_rating", "official_rating", "custom_rating",
        ]
        for filter_name in interval_filter_names:
            
            if (include_filter := self.include.get(filter_name)) is not None:
                includes[filter_name] = Interval(str(include_filter).lower())
                self.__logger.debug("include %s: %s", filter_name, includes[filter_name])
            elif (exclude_filter := self.exclude.get(filter_name)) is not None:
                excludes[filter_name] = Interval(str(exclude_filter).lower())
                self.__logger.debug("exclude %s: %s", filter_name, excludes[filter_name])
        
        self.__logger.debug("%d include filters set", len(includes))
        self.__logger.debug("%d exclude filters set", len(excludes))
        
        # START OF FILTERING ALL COLLECTED ITEMS BASED ON COLLECTED FILTERS LIKE: YEAR, TAGS, RUNTIME, RATINGS, ETC.
        # ==========================================================================================================

        filter_name_get_func = {
            "years":            lambda item: item.get("ProductionYear"),
            "tags":             lambda item: item.get("Tags"),
            "startwith_name":   lambda item: item.get("Name"),
            "runtime":          lambda item: None if (ticks := item.get("RunTimeTicks")) is None else ticks / 10_000_000 / 60,
            "people_ids":       lambda item: None if len(_ids := Toolkit.dict_get_all(item.get("People", []), "Id", discard=True)) == 0 else _ids,
            "community_rating": lambda item: item.get("CommunityRating"),
            "critic_rating":    lambda item: item.get("CriticRating"),
            "official_rating":  lambda item: item.get("OfficialRating"),
            "custom_rating":    lambda item: item.get("CustomRating"),
        }

        # collect all items, where their specific values are contained in the specific include filter value
        if len(includes) != 0:
            included_items = []
            for item in all_items:
                self.__logger.debug("check item for includes: %s", item["Name"])
                for filter_name, filter_value in includes.items():
                    # get function of specific filter that extracts the value from the item dict
                    if (get_func := filter_name_get_func.get(filter_name)) is None:
                        self.__logger.warning("no getter function found for filter name: %s", filter_name)
                        continue
                    # get the value of the filter from the item dict
                    if (item_value := get_func(item)) is None:
                        self.__logger.debug("skip item without %s value", filter_name)
                        continue
                    # check if filter value contains value of item (only works, because all filters are of type list, set or Interval)
                    if Toolkit.contains_any(filter_value, item_value):
                        self.__logger.debug("include item %s", item["Name"])
                        included_items.append(item)
        else:
            included_items = all_items

        _len_included_items_before = len(included_items)
        self.__logger.debug("included %d items", _len_included_items_before)

        # remove all items, where their specific values are contained in the specific exclude filter value
        excluded_items = []
        if len(excludes) != 0:
            for item in included_items:
                self.__logger.debug("check item for excludes: %s", item["Name"])
                for filter_name, filter_value in excludes.items():
                    # get function of specific filter that extracts the value from the item dict
                    if (get_func := filter_name_get_func.get(filter_name)) is None:
                        self.__logger.warning("no getter function found for filter name: %s", filter_name)
                        continue
                    # get the value of the filter from the item dict
                    if (item_value := get_func(item)) is None:
                        self.__logger.debug("skip item without %s value", filter_name)
                        continue
                    # check if filter value not contains value of item (only works, because all filters are of type list, set or Interval)
                    if not Toolkit.contains_any(filter_value, item_value):
                        self.__logger.debug("exclude item %s", item["Name"])
                        excluded_items.append(item)

        self.__logger.debug("excluded %d items", len(excluded_items))
        
        # get item ids
        item_ids = []
        item_ids.extend( set(Toolkit.dict_get_all(included_items, "Id")) - set(Toolkit.dict_get_all(excluded_items, "Id")) )
        
        # add item ids, to include always
        if (include_item_ids := self.include.get("item_ids")) is not None:
            include_item_ids = list(filter(bool, Toolkit.parse_list(include_item_ids)))
            item_ids.extend(include_item_ids)
            self.__logger.debug("include item_ids: %s", include_item_ids)

        # remove duplicate ids
        item_ids = list(set(item_ids))
        self.__logger.debug("after all filters, collected %d items", len(item_ids))
                
        # create static playlist of all item ids
        new_playlist = StaticPlaylist(
            name = self.name,
            item_ids = item_ids,
            sort_by = self.sort_by,
            sort_ascending = self.sort_ascending,
            sort_strict = self.sort_strict,
            limit = self.limit,
        )
        self.__logger.debug(
            "created static playlist '%s' with %d items",
            new_playlist.name, len(new_playlist.item_ids)
        )
        return new_playlist



class Conditional:
    def __init__(self, name: str, conditions: dict[str, Any] = {}):
        self.__logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")
        self.name = name
        self.conditions = conditions
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(name={self.name.__repr__()}, conditions={self.conditions.__repr__()})"
    
    def __bool__(self) -> bool:
        return self.is_true()
    
    def is_true(self, *, jellyfin: Optional[Jellyfin] = None, user_id: Optional[str] = None) -> bool:
        self.__logger.debug("check conditional: %s", self.name)

        if self.conditions.get("disabled", False):          # always disables the entry, ignoring all other conditions
            return False
        elif self.conditions.get("selected", False):        # always selects the entry, ignoring all other conditions
            return True
        
        if (hours := self.conditions.get("hours")) is not None:             # from hour 0 to 23
            if not Interval(hours).contains(dt.datetime.now().hour):
                return False
        elif (weekdays := self.conditions.get("weekdays")) is not None:     # from monday=1 to sunday=7
            if not Interval(weekdays).contains(dt.datetime.now().isoweekday()):
                return False
        elif (days := self.conditions.get("days")) is not None:             # from 1st day of the month up to 31st day
            if not Interval(days).contains(dt.datetime.now().day):
                return False
        elif (weeks := self.conditions.get("weeks")) is not None:           # from 1st week of the year up to 52nd week
            if not Interval(weeks).contains(dt.datetime.now().isocalendar()[1]):
                return False
        elif (months := self.conditions.get("months")) is not None:         # from january=1 to december=12
            if not Interval(months).contains(dt.datetime.now().month):
                return False
        elif (years := self.conditions.get("years")) is not None:           # from year 1 AD up to year 9999 AD 
            if not Interval(years).contains(dt.datetime.now().year):
                return False
        elif (dates := self.conditions.get("dates")) is not None:           # date format YYYY_MM_DD
            if not Interval(dates).contains(dt.datetime.now()):
                return False
        
        # check conditions that require communication with jellyfin to get user data
        if isinstance(jellyfin, Jellyfin) and user_id is not None:
            self.__logger.debug("check conditional '%s' for userid='%s'", self.name, user_id)
            user = jellyfin.get_user(user_id)
            
            if (user_age := self.conditions.get("user_age")) is not None:
                if (max_parental_rating := user.get("Policy", {}).get("MaxParentalRating")) is not None:
                    # extract age from parental rating label
                    # TODO: support all jellyfin ratings correctly
                    parental_rating_num = int(re.findall(r"[0-9]+", f"0{max_parental_rating}")[0])
                    if not Interval(user_age).contains(parental_rating_num):
                        return False
    
        self.__logger.debug("conditional '%s' is true", self.name)
        return True



class MediaBar:
    def __init__(self, *, filename: Path):
        self.__logger = logging.getLogger(f"{Path(__file__).stem}.{__class__.__name__}")
        self.__filename = filename
        self.__parse_file()
    
    def __repr__(self) -> str:
        return f"{__class__.__name__}(filename={self.__filename.__repr__()}"
    
    def __parse_file(self) -> None:
        self.__logger.debug("load mediabar config '%s'", self.__filename)

        with open(self.__filename, "r", encoding="utf-8", errors="replace") as file:
            filedata = yaml.load(file.read(), yaml.Loader)
        
        # all playlist names are converted to lower case when imported
        # altough the StaticPlaylist/DynamicPlaylist and Conditional classes don't requiere lower case names
        self.conditionals = self.__parse_selection(filedata["selection"])
        self.playlists = self.__parse_playlists(filedata["playlists"])

    def __parse_selection(self, data: dict) -> list[Conditional]:
        self.__logger.debug("parse selection with %d conditionals", len(data))

        unique_names = set()
        conditionals = []
        for entry in data:
            name = entry.pop("name").lower()

            if name in unique_names:
                raise KeyError(f"Conditional for playlist '{name}' is already defined.")
            unique_names.add(name)
            
            new_conditional = Conditional(name, entry)
            conditionals.append(new_conditional)
        return conditionals

    def __parse_playlists(self, data: dict) -> list[Union[StaticPlaylist, DynamicPlaylist]]:
        self.__logger.debug("parse %d playlists", len(data))

        unique_names = set()
        playlists = []
        for entry in data:
            name = entry["name"].lower()
            items = entry["items"]
            _type = items.pop("type")       # only filters or item ids are left after popping the type
            
            if name in unique_names:
                raise KeyError(f"Playlist '{name}' is already defined.")
            unique_names.add(name)
            
            if _type == "static":
                new_playlist = StaticPlaylist(
                    name = name,
                    item_ids = items["ids"],
                    sort_by = entry.get("sort_by", "order"),
                    sort_ascending = entry.get("sort_ascending", True),
                    sort_strict = entry.get("sort_strict", False),
                )
                self.__logger.debug(
                    "found static playlist '%s' with %d items",
                    new_playlist.name, len(new_playlist.item_ids)
                )
            
            elif _type == "dynamic":
                new_playlist = DynamicPlaylist(
                    name = name,
                    limit = int(items.get("limit", 10)),
                    include = items.get("include", {}),
                    exclude = items.get("exclude", {}),
                    sort_by = entry.get("sort_by", "order"),
                    sort_ascending = entry.get("sort_ascending", True),
                    sort_strict = entry.get("sort_strict", False),
                )
                self.__logger.debug(
                    "found dynamic playlist '%s' with %d include rules and %d exclude rules",
                    new_playlist.name, len(new_playlist.include), len(new_playlist.exclude)
                )
            
            else:
                raise ValueError(f"Unknown playlist type '{_type}'")
            
            playlists.append(new_playlist)
        return playlists
    
    def get_selected(self, **conditional_kwargs) -> Conditional:
        # returns first Conditional where all conditions are met, otherwise the last one
        selected = self.conditionals[-1]
        for conditional in self.conditionals:
            if conditional.is_true(**conditional_kwargs):
                selected = conditional
                break
        return selected
    
    def get_playlist(self, name: str) -> Union[StaticPlaylist, DynamicPlaylist]:
        # returns first Playlist with matching name (with previous parsing, every playlist name should be unique)
        for playlist in self.playlists:
            if playlist.name.lower() == name.lower():
                return playlist
        raise KeyError(f"Selected playlist '{name}' not defined.")
    
    def evaluate(self, jellyfin: Jellyfin, *, user_id: Optional[str] = None) -> tuple[str, list[str]]:
        # evaluates the whole imported config and returns the selected playlist name and sorted playlist item ids
        conditional = self.get_selected(jellyfin=jellyfin, user_id=user_id)
        playlist = self.get_playlist(conditional.name)
        static_playlist = playlist.compile(jellyfin) if isinstance(playlist, DynamicPlaylist) else playlist
        item_ids = static_playlist.sort(jellyfin)
        return conditional.name, item_ids
    
    @staticmethod
    def export_legacy_format(playlist_name: str, item_ids: list[str], filename: Path = Path("list.txt")) -> None:
        # the name of the playlist, followed by a list of item ids, one per line
        with open(filename, "w", encoding="utf-8") as file:
            file.write(f"{playlist_name}\n")
            file.write("\n".join(item_ids))



def main() -> None:
    jellyfin = Jellyfin(
        server_url="http://192.168.0.10:8096",
        username="api-user",                            # this user needs access to all libraries that should be included in the list
        password=r"C5n0RS^8*Uv0D$I0ZEEr2D3Dn&QO&%b2",   # password leaked, but server url is local, so it doesn't matter
    )
    
    mediabar = MediaBar(filename=Path(r"mediabar.yaml"))
    playlist_name, item_ids = mediabar.evaluate(jellyfin)
    mediabar.export_legacy_format(playlist_name, item_ids)


if __name__ == "__main__":
    t0 = time.time()
    main()
    t1 = time.time()
    
    print(f"this took {t1-t0:.4f} seconds")
