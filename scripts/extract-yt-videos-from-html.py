
"""
Open any youtube page in a desktop browser and store its html as "youtube.html" by pressing Ctrl+S.

This script will extract every youtube video from all html a-tags, stores their urls in the file links.txt and then
downloads every video in best available quality using yt-dlp.
"""


import os
from pathlib import Path
from bs4 import BeautifulSoup

skip_parsing = False
htmlpath = Path(r"C:\Users\fabia\Downloads\youtube.html")
outdirpath = Path(r"C:\Users\fabia\Downloads\videos")

outdirpath.mkdir(exist_ok=True, parents=True)


if not skip_parsing:
    with open(htmlpath, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "html.parser")
        links = [ tag.get("href") for tag in soup.find_all("a") if tag.get("href") ]
        
    cleaned_links = set()
    for link in links:
        if "/watch?v=" in link:
            cleaned_links.add(f"https://youtube.com{link.split('&')[0]}")

    with open(outdirpath/"links.txt", "w", encoding="utf-8") as file:
        for link in cleaned_links:
            file.write(f"{link}\n")

exit()
with open(outdirpath/"links.txt", "r", encoding="utf-8") as file:
    links = []
    for line in file.readlines():
        links.append(line.replace("\n", ""))

os.chdir(outdirpath)
for ind, link in enumerate(links, start=1):
    print(f"\n{ind} / {len(links)} --- {link}")
    os.system(f"yt-dlp -f bestvideo+bestaudio --merge-output-format mp4 {link}")
