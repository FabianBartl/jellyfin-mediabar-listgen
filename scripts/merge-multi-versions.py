
"""
Imagine you have many episoded of a tv show, but the subtitles are not embedded and instead of one video file
with multiple audio tracks, there are multiple video files with one audio track each.

This script will combine the video with all audio and subtitle languages present into a single file without
re-encoding anything.

To be able to automatically find the related files, they need to follow certain naming rules, that can be configured
using regular expressions. The regex can look quite complex, so next to each such config is a regex101.com link that
contains the expression and an example to visualize it and help modifying it. 

The config comes after all the imports and each option is described. The order of the config itself is not importent,
but it is by default in order of file processing.

---

License: MIT
Author: Fabian Bartl
Repository: https://github.com/FabianBartl/jellyfin-scripts
Last update: 2025-05-03
"""

try:
    import ttml2srt     # not as a package available
except ImportError:
    print("Please download ttml2srt.py from https://github.com/yuppity/ttml2srt")
    ttml_to_srt_unsupported = input("Continue without automatic conversion of ttml to srt? [y/N] ").lower() == "y"
    if not ttml_to_srt_unsupported:
        import ttml2srt

try:
    # pip install colorama
    from colorama import init as colorama_init
    from colorama import Fore, Back, Style
    colorama_init(autoreset=True)
    colored_ffmpeg = True
except ImportError:
    colored_ffmpeg = False

import re
import os
from pathlib import Path
from pprint import pprint
from typing import Any, Callable, Iterable, Optional
from typing_extensions import Self

"""################### START OF USER CONFIG ###################"""

# the folder where all the files are, note that the script does not expect nested input files
INPUT_FOLDER: Path = Path(r"C:\Users\fabia\Downloads")

# this just renames the input files if needed, but it should normalize the series-episode marker, title and language marker
# https://regex101.com/r/kloyKZ/2
# 'The Rookie-100 Tage Rookie (S01_E14) (Englisch)-0851818866.mp4' -> 'The Rookie - 100 Tage Rookie S01E14 [ÖRR] [1080p] [LANG-Englisch].mp4'
# 'The Rookie-100 Tage Rookie (S01_E14)-0851818866.mp4' -> 'The Rookie - 100 Tage Rookie S01E14 [ÖRR] [1080p] [LANG-].mp4'
FILE_RENAME_PATTERN = {
    "pattern": r"^(?P<series>[^\-]+)-(?P<title>[^\(]+) \(S(?P<season>\d+)_E(?P<episode>\d+)\)(?: \((?P<lang>[^)]+)\))?-\d+(?P<ext>\..+)$",
    "repl": r"\g<series> - \g<title> S\g<season>E\g<episode>" + " [ÖRR] [1080p]" + r" [LANG-\g<lang>]\g<ext>",
}
# you can skip renaming with this regex:
FILE_RENAME_PATTERN = {
    "pattern": r"^(?P<filename>.+)$",
    "repl": r"\g<filename>",
}

# all files from the input folder will be renamed by this, so if you mess up the regex, you will need to revert the renaming
# (by loading the backup you made)
# if the first step goes right, you can execute the script as many times as you want without breaking something, because the
# following steps only modify the output, which can be re-generated

# every file of the same episode is identified by this regex
# in my case for example: S01E22 or S1E3, but not S1-E2 or SE4
COMMON_EPISODE_PATTERN = r"S\d+E\d+"

# to mark the audio and subtitle tracks with the correct languages, they need to be named according to "ISO 639 Set 3"
# see: https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes
# the language of a file is matched by this regex: https://regex101.com/r/CFxbag/1
COMMON_LANGUAGE_PATTERN = r"\[LANG-([^\]]*)\]"
# if you only have one language, you can set this variable to None
COMMON_LANGUAGE_PATTERN = None

# the matched language will be replaced by their 3-letter code for setting the track language by this mapping:
# in my case are the unmarked files in germann (deu) and the english (eng) ones marked with 'Englisch'
LANGUAGE_MAP = {
    "": "deu",
    "Englisch": "eng",
}
# if COMMON_LANGUAGE_PATTERN is None, use this map and replace the 3-letter code by yours
LANGUAGE_MAP = {
    "": "deu",
}

# the 3-letter code or None of the audio and subtitle track that should be set to default if present
# you should always set a default audio language
DEFAULT_AUDIO_LANG = "deu"
DEFAULT_SUBTITLE_LANG = None

# the folder where all the merged files should be stored in
OUTPUT_FOLDER = INPUT_FOLDER / "merged"

# one of the video files of an episode is renamed by this regex to be used as the name of the output file
# because the output contains all languages, i want to remove the language part that may be present
# https://regex101.com/r/qGuDOX/1
OUTPUT_RENAME_PATTERN = {
    "pattern": r"^(?P<before_lang>.*)(?P<lang> \[LANG-[^\]]*\])(?P<after_lang>.*)(?P<ext>\..+)$",
    "repl": r"\g<before_lang>\g<after_lang>\g<ext>",
}

# should the ffmpeg command be executed or just shown?
FFMPEG_EXECUTE = False
# the command or location of the ffmpeg binary
FFMPEG_BIN = r"ffmpeg"
# append the -y option to the ffmpeg command?
FFMPEG_YES = True

# set this to True, if you are happy with your config 
START_THE_SCRIPT = False

"""################### END OF USER CONFIG ###################"""


if not START_THE_SCRIPT:
    print("you need to read the config before you can execute the script")
    print("(you probably just forgot to set the very last parameter of the config)")
    exit()


# collect all files from a directory (non-recursive)
all_files = list([ path for path in INPUT_FOLDER.iterdir() if path.is_file() ])
pprint(all_files)


# rename all files according to the regex pattern
if FILE_RENAME_PATTERN.get("pattern") is None or FILE_RENAME_PATTERN.get("repl") is None:
    raise KeyError("check your FILE_RENAME_PATTERN")

renamed_files = []
for file in all_files[:]:
    new_file = file.rename(file.parent / re.sub(**FILE_RENAME_PATTERN, string=file.name))
    renamed_files.append(new_file)
    print("renamed to", new_file.name)


# group all files by episode
COMMON_EPISODE_PATTERN = r"S\d+E\d+"
related_episodes = {}
for file in renamed_files:
    if len(common_match := re.findall(COMMON_EPISODE_PATTERN, file.stem)) > 0:
        related_episodes.update({ common_match[0]: related_episodes.get(common_match[0], []) + [file] })
pprint(related_episodes)


# group all episode files by language
# rename languages according to "ISO 639 Set 3" (see: https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes)
for episode, files in list(related_episodes.items()):

    related_languages = {}
    for file in files:
        
        if COMMON_LANGUAGE_PATTERN is not None:
            if len(common_match := re.findall(COMMON_LANGUAGE_PATTERN, file.stem)) > 0:
                lang = LANGUAGE_MAP[common_match[0]]
                related_languages.update({ lang: related_languages.get(lang, []) + [file] })
        else:
            lang = LANGUAGE_MAP[""]
            related_languages.update({ lang: related_languages.get(lang, []) + [file] })

    related_episodes[episode] = related_languages
pprint(related_episodes)


# group all language files by file type
supported_filetypes = {
    "video": {"mp4", "mkv", "webm"},
    "audio": {"mp3", "m4a", "weba"},
    "subtitle": {"srt"},
}
for episode, languages in list(related_episodes.items()):

    related_languages = {}
    for lang, files in list(languages.items()):

        filetypes = {}
        for file in files:
        
            # sort files by their type
            suffix = file.suffix.removeprefix(".")
            if suffix in supported_filetypes["video"]:
                filetypes["video"] = file
            elif suffix in supported_filetypes["audio"]:
                filetypes["audio"] = file
            elif suffix in supported_filetypes["subtitle"]:
                filetypes["subtitle"] = file
            elif suffix in {"ttml", "xml"}:
                filetypes["subtitle_unsupported"] = file
        
        # if only unsupported subtitles are present, convert them
        try:
            if filetypes.get("subtitle") is None and (subtitle_file := filetypes.get("subtitle_unsupported")) is not None:
                if not ttml_to_srt_unsupported and subtitle_file.suffix.removeprefix(".") in {"ttml", "xml"}:
                    srt_subtitle_file = subtitle_file.with_suffix("srt")
                    with open(srt_subtitle_file, "w", encoding="utf-8") as srt_file:
                        converter = ttml2srt.Ttml2Srt(ttml_filepath=str(subtitle_file))
                        converter.write2file(output=srt_file, close_fd=False)
                    filetypes["subtitle"] = srt_subtitle_file
        except Exception as exc:
            print(f"{episode}:{lang}: automatic conversion of unsupported subtitles failed")
            print(exc)
        
        # discard audio if video is present (assuming the video has an audio track) 
        if filetypes.get("audio") is not None and filetypes.get("video") is not None:
            filetypes.pop("audio")

        # discard language if no supported filetype found
        if len(filetypes) > 0:
            related_languages[lang] = filetypes
        else:
            print(f"{episode}:{lang}: no supported filetypes found")

    # discard episode if no supported filetype for any language found
    if len(related_languages) > 0:
        related_episodes[episode] = related_languages
    else:
        print(f"{episode}: no supported filetypes for any language found")

pprint(related_episodes)


# create output folder and handle existing files
try:
    OUTPUT_FOLDER.mkdir(exist_ok=False, parents=True)
except (FileExistsError, OSError):
    print(f"output folder already exists:", str(OUTPUT_FOLDER))
    existing_files = [ path for path in OUTPUT_FOLDER.iterdir() if path.is_file() ]
    print(f"output folder contains {len(existing_files)} files")
    
    overwrite_files = input("Continue and risk overwriting files? [y/N] ").lower() == "y"
    if not overwrite_files:
        print("exit script")
        exit()
    
    OUTPUT_FOLDER.mkdir(exist_ok=True, parents=True)
    print("output folder created")
    


class Counters:
    def __init__(self, **counters: int) -> Self:
        self.__counters = counters
        for key in self.__counters:
            self.__add_method(self.__make_getter(key))
            self.__add_method(self.__make_updater(key))
    
    def total(self) -> int:
        return sum(self.__iter__())

    def __iter__(self) -> Iterable:
        return self.__counters.values()
    
    def __add_method(self, func: Callable) -> None:
        self_func = lambda self, _f=func, *args, **kwargs: _f(self, *args, **kwargs)
        setattr(type(self), func.__name__, self_func)

    def __make_getter(self, key: str) -> Callable:
        def get(self):
            return self.__counters[key]
        get.__name__ = f"get_{key}"
        return get

    def __make_updater(self, key: str) -> Callable:
        def update(self):
            self.__counters[key] += 1
        update.__name__ = f"update_{key}"
        return update


class FFmpeg:
    def __init__(self, *, ffmpeg_bin: str = "ffmpeg", yes: bool = False, colored_echo: bool = False) -> Self:
        self.yes: bool = yes
        self.colored_echo: bool = colored_echo
        self.__ffmpeg_bin: str = ffmpeg_bin
        self.__inputs: list[str] = []
        self.__arguments: list[str] = []
        self.__output: list[str] = []

    @staticmethod
    def escape_path(path: Path) -> str:
        path = re.sub(r"\\+", "/", str(path))       # basically convert windows path to linux path
        return f'"{path}"'
    
    def option(self, key: str, value: Optional[str] = None, *, _type: str = "argument") -> Self:
        match _type:
            case "input":
                _list = self.__inputs
            case "output":
                _list = self.__output
            case "argument":
                _list = self.__arguments
            case _:
                raise TypeError
        _list.append(f"-{key.removeprefix('-')}")
        if value is not None:
            _list.append(value)
        return self
    
    def input(self, file: Path) -> Self:
        return self.option("i", self.escape_path(file.absolute()), _type="input")
    
    def output(self, file: Path, options: dict[str, str]) -> Self:
        for key, value in options.items():
            self = self.option(key, value, _type="output")
        self.__output.append(self.escape_path(file.absolute()))
        return self

    def echo(self) -> str:
        if not self.colored_echo:
            return " ".join(self.build())

        arguments = []
        reset = Fore.RESET + Back.RESET + Style.RESET_ALL
        arguments.extend([ Style.BRIGHT + self.__ffmpeg_bin + reset])
        arguments.extend([ Fore.CYAN + arg + reset for arg in self.__inputs ])
        arguments.extend([ Fore.GREEN + arg + reset for arg in self.__arguments ])
        arguments.extend([ Fore.RED + arg + reset for arg in self.__output ])
        if self.yes:
            arguments.extend([ Style.BRIGHT + "-y" + reset])
        return " ".join(arguments)

    def build(self) -> list[str]:
        arguments = [self.__ffmpeg_bin]
        arguments.extend(self.__inputs)
        arguments.extend(self.__arguments)
        arguments.extend(self.__output)
        if self.yes:
            arguments.append("-y")
        return arguments

    def execute(self) -> int:
        command = self.build()
        return os.system(" ".join(command))         # subprocess.run refuses to work with ffmpeg on windows


# build an ffmpeg command for each episode
if OUTPUT_RENAME_PATTERN.get("pattern") is None or OUTPUT_RENAME_PATTERN.get("repl") is None:
    raise KeyError("check your OUTPUT_RENAME_PATTERN")

for episode, languages in related_episodes.items():
    ffmpeg = FFmpeg(yes=FFMPEG_YES, colored_echo=colored_ffmpeg)
    counter = Counters(video=0, audio=0, subtitle=0)
    
    # get video track
    video_track = None
    for lang, filetypes in languages.items():
        if (file := filetypes.get("video")) is not None:
            video_track = file
            print(f"{episode}: use video track of language {lang}")
            break
    if video_track is None:
        print(f"{episode}: no video file found")
        break

    ffmpeg = ffmpeg.input(video_track).option("map", f"{counter.total()}:v:0")
    counter.update_video()
    
    # get audio or audio from video per language
    for lang, filetypes in languages.items():
        
        if (audio_track := filetypes.get("video", filetypes.get("audio"))) is None:
            print(f"{episode}:{lang}: no audio track found")
            continue
        print(f"{episode}:{lang}: use audio track", str(audio_track))
            
        ffmpeg = (
            ffmpeg
            .input(audio_track)
            .option("map", f"{counter.total()}:a:0")
            .option(f"metadata:s:a:{counter.get_audio()}", f"language={lang}")
            .option(f"disposition:a:{counter.get_audio()}", "+default" if DEFAULT_AUDIO_LANG == lang else "-default")
        )
        counter.update_audio()
    
    # get subtitle per language
    for lang, filetypes in languages.items():
        
        if (subtitle_track := filetypes.get("subtitle")) is None:
            print(f"{episode}:{lang}: no subtitle track found")
            continue
        print(f"{episode}:{lang}: use subtitle track", str(subtitle_track))
        
        ffmpeg = (
            ffmpeg
            .input(subtitle_track)
            .option("map", f"{counter.total()}:s:0")
            .option(f"metadata:s:s:{counter.get_subtitle()}", f"language={lang}")
            .option(f"disposition:s:{counter.get_subtitle()}", "+default" if DEFAULT_SUBTITLE_LANG == lang else "-default")
        )
        counter.update_subtitle()
    
    # get output file
    output_file = OUTPUT_FOLDER / re.sub(**OUTPUT_RENAME_PATTERN, string=video_track.name)
    output_options = {"c:v": "copy", "c:a": "copy"}
    if counter.get_subtitle() > 0:
        output_options["c:s"] = "srt"
        output_file = output_file.with_suffix(".mkv")
        
    ffmpeg = ffmpeg.output(output_file, output_options)
    print(f"{episode}: output as", str(output_file))

    # execute ffmpeg
    print(f"{episode}:\n", ffmpeg.echo())

    if FFMPEG_EXECUTE:
        ffmpeg.execute()
    else:
        print("skipped ffmpeg execution, or set FFMPEG_EXECUTE to True")

