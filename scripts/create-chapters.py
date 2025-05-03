"""
Credits: https://ikyle.me/blog/2020/add-mp4-chapters-ffmpeg

---

Add named chapters to any video file. Can be used in combination with the "merge-videos.py" script.

How to use this script:

- extract metadata with:
    ffmpeg -i "Star Wars Parodien.mkv" -f ffmetadata FFMETADATAFILE

- remove existing chapters from the output file and keep only this:
    ;FFMETADATA1
    title=Star Wars
    encoder=Lavf61.1.100

- create chapters.txt with one chapter title per line:
    HH:MM:SS Chapter 1
    HH:MM:SS Chapter 2

- convert to FFMETADATAFILE with this script

- merge this output file with the extracted metadata file

- write metadata back into the movie file with:
    ffmpeg -i input.mkv -i chapters.FFMETADATAFILE -map 0 -c copy -map_metadata 1 -map_chapters 1 -codec copy out.mkv
"""

import re, sys

if len(sys.argv) < 2:
    print(f"Usage: {__file__} [chapters file]")
    exit()

chapters = list()

with open(sys.argv[1], 'r') as f:
    for line in f:
        x = re.match(r"(\d):(\d{2}):(\d{2}) (.*)", line)
        hrs = int(x.group(1))
        mins = int(x.group(2))
        secs = int(x.group(3))
        title = x.group(4)

        minutes = (hrs * 60) + mins
        seconds = secs + (minutes * 60)
        timestamp = (seconds * 1000)
        chap = {
            "title": title,
            "startTime": timestamp
        }
        chapters.append(chap)

text = ""

for i in range(len(chapters)-1):
    chap = chapters[i]
    title = chap['title']
    start = chap['startTime']
    end = chapters[i+1]['startTime']-1
    text += f"""
[CHAPTER]
TIMEBASE=1/1000
START={start}
END={end}
title={title}
"""


with open(f"{sys.argv[1].rsplit('.',1)[0]}.FFMETADATAFILE", "a") as file:
    file.write(text)
