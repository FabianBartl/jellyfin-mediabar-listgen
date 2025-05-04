
# Jellyfin Scripts and Tools

A collection of scripts and tools that make my life easier when managing a considerably large Jellyfin library.



## Tools

### [MediaBar listgen](tools/mediabar-listgen/README.md)

A Python script to generate a simple list of item IDs based on a variety of conditions and filters. The resulting list.txt file can be used by the [Jellyfin MediaBar Plugin](https://github.com/MakD/Jellyfin-Media-Bar).



## Scripts


### [merge-multi-versions.py](scripts/merge-multi-versions.py)

*Imagine you have many episoded of a tv show, but the subtitles are not embedded and instead of one video file with multiple audio tracks, there are multiple video files with one audio track each.*

This script will combine the video with all audio and subtitle languages present into a single file.

To be able to automatically find the related files, they need to follow certain naming rules, that can be configured using regular expressions. The regex can look quite complex, so next to each such config is a regex101.com link that contains the expression and an example to visualize it and help modifying it.

The config comes after all the imports and each option is described. The order of the config itself is not importent, but it is by default in order of file processing.


### [update-trailers.py](scripts/update-trailers.py)

1. **Option: _add_new_trailers = True**

    This script can move trailers from a directory to their related movies folder and update the movie.nfo file accordingly. For this to work, the lowercase trailer filename must contain the corresponding lowercase movie filename and the movie metadata have to be stored in a movie.nfo file.

2. **Option: _link_local_trailers = True**

    After refreshing the jellyfin library through the web dashboard and NFO-metadata storage is enabled, trailers from youtube are searched and added to each movie.nfo file. With this option you can remove all remote trailers and add instead all local trailers, that are present in each movie folder.

3. **Option: _update_tags_by_filename = True**

    You can add labels to movies by putting them in square brackets in the movie filename. With this option, all these labels from the filename are added to the tags listed in the movie.nfo file.



### [create-chapters.py](scripts/create-chapters.py) and [merge-videos.py](scripts/merge-videos.py)

You can add chapters to any video with the first script. And with the second, you can merges two videos into one while keeping the chapters with corrected timestamps.


### [slow-reencode-to-h265.sh](scripts/slow-reencode-to-h265.sh)

Slowly re-encode high quality video files into H.265 format to reduce the file size while maintaining quality. The audio tracks are not re-encoded as they do not affect the file size as much as the video. If necessary, the video is also de-interlaced.

[This script](scripts/batch_slow-reencode-to-h265.sh) is a wrapper to process all files of a directory instead of a single file.


### [kps.py](scripts/kps.py)

A small cli script to quickly and easily get a shell for any pod of any kubernetes container.

*Written and tested for TrueNAS Scale Dragonfish 24.04; in version 24.10 TrueNAS switched to docker*


### [jellyfin.css](scripts/jellyfin.css)

Not a script, but just for backup, here is the custom CSS of my Jellyfin server.


### [extract-yt-videos-from-playlist-html.py](scripts/extract-yt-videos-from-playlist-html.py)

*Open any youtube page in a desktop browser and store its html as "youtube.html" by pressing Ctrl+S.*

This script will extract every youtube video from all html a-tags, stores their urls in the file links.txt and then downloads every video in best available quality using yt-dlp.





