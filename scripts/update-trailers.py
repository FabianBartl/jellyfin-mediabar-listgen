
"""
Requirements for this script:

- every movie needs to be in its own folder
- in the library, the NFO metadata storage needs to actived
- any movie trailer needs to be inside a "trailers" folder inside the movie folder
- labels must be enclosed by square brackets
- to relate a trailer to a movie, the trailer name must contain the full movie name including the year

see more here: https://jellyfin.org/docs/general/server/media/movies/


There are two paths of the library:
- the BASE_PATH locates it on the sysem that executes this script 
- the JELLYFIN_BASE_PATH locates it on the system jellyfin is running on

In my case the script runs on a windows computer with access to the library via an SMB share, so BASE_PATH
is the windows path. And on the server the library is mounted to the jellyfin docker at the path set by
JELLYFIN_BASE_PATH. 


1. Option: _add_new_trailers = True

This script can move trailers from a directory to their related movies folder and update the movie.nfo file
accordingly. For this to work, the lowercase trailer filename must contain the corresponding lowercase movie
filename and the movie metadata have to be stored in a movie.nfo file. The directory of the new trailers can
be set by NEW_TRAILERS_BASE_PATH.


2. Option: _link_local_trailers = True

After refreshing the jellyfin library through the web dashboard and NFO-metadata storage is enabled, trailers
from youtube are searched and added to each movie.nfo file. With this option you can remove all remote trailers
and add instead all local trailers, that are present in each movie folder.


3. Option: _update_tags_by_filename = True

You can add labels to movies by putting them in square brackets in the movie filename. With this option, all these
labels from the filename are added to the tags listed in the movie.nfo file.
"""

import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional
import subprocess
import shutil
import json
from tqdm import tqdm
import re

# BASE_PATH = r"S:\media\_public-media-backup\movies"
# JELLYFIN_BASE_PATH = "/mnt/media/_public-media-backup/movies"

BASE_PATH = r"S:\media\_disc-media-backup\movies"
JELLYFIN_BASE_PATH = "/mnt/media/_disc-media-backup/movies"

NEW_TRAILERS_BASE_PATH = r"S:\tmp\trailers"


def backup_nfo(nfo_path: str) -> None:
    backup_path = nfo_path + ".backup"
    if not os.path.exists(backup_path):
        shutil.copyfile(nfo_path, backup_path)
        print(f"Backup created: {backup_path}")


def update_nfo_with_trailers(nfo_path: str, trailer_paths: list[str]) -> None:
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        for trailer in root.findall("trailer"):
            if trailer.text.startswith("plugin://"):
                root.remove(trailer)
                print(f"remote trailer removed: {trailer.text}")
            else:
                root.remove(trailer)
                print(f"trailer removed: {trailer.text}")

        for trailer_path in trailer_paths:
            trailer_elem = ET.Element("trailer")
            trailer_elem.text = trailer_path.replace(BASE_PATH, JELLYFIN_BASE_PATH).replace("\\", "/")
            root.append(trailer_elem)
            print(f"local trailer added: {trailer_path}")

        ET.indent(tree, space="  ", level=0)
        tree.write(nfo_path, encoding="utf-8", xml_declaration=True)
        print(f"Updated {nfo_path}")

    except ET.ParseError as e:
        print(f"Error updating {nfo_path}: {e}")


def update_nfo_with_tags(nfo_path: str, new_tags: set[str], *, extend_tags: bool = True) -> None:
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        all_tags = set([ tag.lower() for tag in new_tags ])
        if extend_tags:
            all_tags |= set([ tag.text.lower() for tag in root.findall("tag") ])

        for tag in root.findall("tag"):
            root.remove(tag)
            print(f"tag removed: {tag.text}")

        for tag in all_tags:
            tag_elem = ET.Element("tag")
            tag_elem.text = tag
            root.append(tag_elem)
            print(f"tag added: {tag_elem.text}")

        ET.indent(tree, space="  ", level=0)
        tree.write(nfo_path, encoding="utf-8", xml_declaration=True)
        print(f"Updated {nfo_path}")

    except ET.ParseError as e:
        print(f"Error updating {nfo_path}: {e}")


_add_new_trailers = False
_link_local_trailers = True
_update_tags_by_filename = True


new_trailers_paths = []
if _add_new_trailers:
    for path in os.listdir(NEW_TRAILERS_BASE_PATH):
        merged_path = os.path.join(NEW_TRAILERS_BASE_PATH, path)
        if os.path.isfile(merged_path) and path.endswith(".mp4"):
            new_trailers_paths.append(merged_path)
new_trailers_paths.sort()


for ind, (root, dirs, files) in enumerate(sorted(os.walk(BASE_PATH))):
    # if not ("_Serien" in root):
        # print("not in list")
        # continue
    
    # if ind > 2:
        # print("early exit")
        # break
        
    if "movie.nfo" in files:
        nfo_path = os.path.join(root, "movie.nfo")
        movie_name = os.path.basename(root)
        print(f"\nMovie: {movie_name}")

        if _add_new_trailers:
            found_movie_trailer = False
            for trailers_ind, path in enumerate(new_trailers_paths):
                if movie_name.lower() in path.lower():
                    found_movie_trailer = new_trailers_paths.pop(trailers_ind)
                    print(f"found movie trailer: {found_movie_trailer}")
                    break
            if not found_movie_trailer:
                continue
        
            # backup_nfo(nfo_path)
            #OR:
            # nfo_backup_path = nfo_path.replace("movie.nfo", "movie.nfo.backup")
            # if os.path.exists(nfo_backup_path):
            #     os.remove(nfo_backup_path)
            #     print("removed backup-nfo")

            trailers_folder = os.path.join(root, "trailers")
            os.makedirs(trailers_folder, exist_ok=True)
            #OR:
            # if os.path.exists(trailers_folder):
            #     shutil.rmtree(trailers_folder)
            #     continue

            path_at_share = os.path.join(root, "trailers", os.path.basename(found_movie_trailer))
            shutil.copyfile(found_movie_trailer, path_at_share)
            update_nfo_with_trailers(nfo_path, [path_at_share])
        
        if _link_local_trailers:
            trailers_folder = os.path.join(root, "trailers")
            if os.path.exists(trailers_folder):
                local_trailers = [ os.path.join(trailers_folder, trailer_path) for trailer_path in os.listdir(trailers_folder) ]
                update_nfo_with_trailers(nfo_path, local_trailers)
        
        if _update_tags_by_filename:
            movie_files = [ file for file in files if file.rsplit(".", 1)[-1] in {"mp4", "mkv"} ]
            for movie_file in movie_files:
                file_tags = re.findall(r"\[([^\[\]]+)\]", movie_file)
                update_nfo_with_tags(nfo_path, set(file_tags), extend_tags=True)
