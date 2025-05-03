#!/bin/bash

# Input file
input_file="$1"

# Extract pixel format using ffprobe and trim any excess whitespace or lines
pix_fmt=$(ffprobe -hide_banner -v error -select_streams v:0 -show_entries stream=pix_fmt -of default=noprint_wrappers=1:nokey=1 "$input_file" 2>/dev/null | head -n 1 | xargs)

# Determine the appropriate profile based on the pixel format
if [[ "$pix_fmt" == *"yuv420p10le"* ]]; then
    profile="main10"
else
    profile="main"
fi

# Check if the video is interlaced using ffprobe
field_order=$(ffprobe -hide_banner -v error -select_streams v:0 -show_entries stream=field_order -of default=noprint_wrappers=1:nokey=1 "$input_file" 2>/dev/null | head -n 1)
echo "field_order='$field_order'"

# If the field order indicates interlacing (tt or bt), enable deinterlacing
if [[ "$field_order" == *"tt"* || "$field_order" == *"bt"* ]]; then
    deinterlace_filter="-vf yadif"
else
    deinterlace_filter=""
fi

# CRF 18-23: High quality, larger file sizes.
# CRF 24-27: Good balance of quality and file size.
# CRF 28-30: Smaller file size, but with a noticeable drop in quality.
crf=23

# Display used settings.
echo "input_file='$input_file'"
echo "crf='$crf'"
echo "profile='$profile'"
echo "pix_fmt='$pix_fmt'"
echo "deinterlace_filter='$deinterlace_filter'"

# Create the "export" subfolder
output_dir="$(dirname "$input_file")/export"
mkdir -p "$output_dir"

# Run the ffmpeg command dynamically based on the input file's pixel format and profile,
# preserving all audio and subtitle tracks without re-encoding the audio.
ffmpeg -i "$input_file" \
    -map 0:v -c:v libx265 -crf "$crf" -preset medium -profile:v "$profile" -pix_fmt "$pix_fmt" $deinterlace_filter \
    -map 0:a -c:a copy \
    -map 0:s:? -c:s copy \
    "$output_dir/$(basename "${input_file%.*}") [crf-"${crf}"].mkv"

# send pushover notifivation with: https://github.com/markus-perl/pushover-cli
pushover-cli -d "script" "$(basename "${input_file%.*}")" "Movie re-encoded"
