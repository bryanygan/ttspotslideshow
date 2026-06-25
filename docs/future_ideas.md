# Future Ideas & TikTok Automation Suggestions

This document lists future ideas and automation features proposed to extend the Spotify TikTok Slideshow project.

---

## 1. Semi-Automated TikTok Uploading (Bypassing the API)
Since TikTok's official Content Posting API is restricted to business and approved developer accounts, you can automate uploads using browser automation:
* **How it works**: Write a script using **Playwright** or **Selenium** in Python. 
* **The Flow**:
  1. Open a browser window and save your TikTok session cookies once (to stay logged in).
  2. The script launches a headless browser, loads the cookies, and navigates to the TikTok upload portal.
  3. It uploads the generated images from `output/slides/<date>/`.
  4. It auto-fills the caption (see suggestion #2) and hits **Post**.
* **Benefit**: Complete end-to-end automation from music capture to social media publication without manual clicking.

---

## 2. Dynamic Smart Captions & Hashtag Generator
Automate the generation of TikTok post descriptions by reading the metadata of the selected tracks for each run:
* **How it works**: Query the SQLite database `plays.db` to extract the primary genre buckets of the selected tracks.
* **Result**: Generate a copy-paste-ready (or auto-posted) text file:
  > "Today's rotation: featuring Kendrick Lamar, Travis Scott, and Ken Carson. Slanted towards #trap, #rage, and #plugg. What are you listening to? 🎧 #nowplaying #music #fyp #foryou"

---

## 3. Video Slide Compilations (MP4 Video with Audio Snippets)
Turn the static slide images into an MP4 video compilation synced to the actual audio of the songs:
* **Audio Snippets**: The Spotify API track payloads contain a `preview_url` (a link to a 30-second high-quality audio clip of the song).
* **The Compilation**:
  1. Download the preview audio clips for the 16 selected tracks.
  2. Use a Python library like **MoviePy** or **ffmpeg** to stitch the audio clips together.
  3. Overlay the corresponding card images so that the card transitions precisely as the next song snippet starts playing.
  4. Save the output as a high-definition vertical MP4 file.
* **Benefit**: Engaging vertical videos that automatically play the audio previews of the tracks as they scroll.

---

## 4. Automated Spotify "Rotation" Playlist Syncer
Synchronize your slideshows with a public Spotify playlist so your followers can listen to the full songs:
* **How it works**: When `run_bidaily.py` generates a new slideshow, it calls the Spotify Web API to clear and update a specific playlist (e.g. "Bryan's Bi-Daily Rotation") with the 12–16 selected tracks.
* **Benefit**: You can link this playlist in your TikTok bio, creating a community loop where followers can easily save the songs they discover on your slides.

---

## 5. Telegram / Discord Integration (Remote Control)
Expose the Screenshot OCR pipeline as an interactive bot:
* **How it works**: Connect a simple Discord or Telegram bot to your Python script.
* **Usage**: When you are browsing music on your phone, simply screenshot your queue and send it to your personal bot channel. The bot runs `ocr.py` in the background on your PC, generates the slide images, and replies to your message with the rendered PNG slides, ready for you to save and upload!
