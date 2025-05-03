#!/bin/bash

# Directory containing the files to process
input_dir="$1"

# Iterate over all files in the directory
for file in "$input_dir"/*; do
    if [ -f "$file" ]; then
        echo "Processing file: $file"
        bash /root/slow-reencode-to-h265.sh "$file"     # absolute path (!) to the script 'slow-reencode-to-h265.sh'
    fi
done
