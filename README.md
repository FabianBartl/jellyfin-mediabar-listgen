
# Jellyfin Scripts

A collection of scripts that make my life easier when managing a considerably large Jellyfin library.



## Scripts


### [merge-multi-versions.py](scripts/merge-multi-versions.py)

*Imagine you have many episoded of a tv show, but the subtitles are not embedded and instead of one video file with multiple audio tracks, there are multiple video files with one audio track each.*

This script will combine the video with all audio and subtitle languages present into a single file.


### [merge-videos.py](scripts/merge-videos.py)

Merges two videos into one and keeps the chapters with corrected timestamps. You can add chapters to any video with the [create-chapters.py](scripts/create-chapters.py) script.


### [create-chapters.py](scripts/create-chapters.py)

Add named chapters to any video file. Can be used in combination with the [merge-videos.py](scripts/merge-videos.py) script.


### [slow-reencode-to-h265.sh](scripts/slow-reencode-to-h265.sh)

Slowly re-encode high quality video files into H.265 format to reduce the file size while maintaining quality. The audio tracks are not re-encoded as they do not affect the file size as much as the video. If necessary, the video is also de-interlaced.

[This script](scripts/batch_slow-reencode-to-h265.sh) is a wrapper to process all files of a directory instead of a single file.


### [kps.py](scripts/kps.py)

A small cli script to quickly and easily get a shell for any pod of any kubernetes container.

*Written and tested for TrueNAS Scale Dragonfish 24.04*



## Tools

### [MediaBar listgen](tools/mediabar-listgen/README.md)

A Python script to generate a simple list of item IDs based on a variety of conditions and filters. The resulting list.txt file can be used by the [Jellyfin MediaBar Plugin](https://github.com/MakD/Jellyfin-Media-Bar).



