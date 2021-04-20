# Drm Dash stream downloader

## Description
Downloads MPEG-DASH Cenc based drm contents by parsing the manifest if the keyID and key is known.

## Requirements
1. You would need to download ffmpeg and mp4decrypter from Bento4 SDK and ensure they are in path(typing their name in cmd invokes them).
2. Dash-IF conforming Manifest file having information about the cenc keyID ,PSSH box information.
3. Basic python knowledge to edit the script's manifest parser function according to your manifest and set your prefered download location.

## Usage
1. Clone the repository
2. Install the requirements in requirements.txt using pip
2. Find the manifest(mpd) file you would want to download and copy its url (Use Devtools if in a browser.)
3. View the mpd file and check if it uses single mp4 segment or multi segments($Number_xx$.mp4)
4. If it is of multi segments then use dashdownloader_multisegment.py
5. Paste the mpd url in the script at the bottom inside the standalone check condition in mpd variable.
4. Run the script after checking requirements are satisfied.

## Note
CBCS and SAMPLE-AES contents need to be manually analyzed and the script has to be modified for decrypting those content.
