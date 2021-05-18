# Udemy Downloader with DRM support

### NOTE
This program is WIP, the code is provided as-is and i am not held resposible for any legal repercussions resulting from the use of this program.

## License
All code is licensed under the MIT license

## Description
Simple and hacky program to download a udemy course, has support for DRM videos but requires the user to aquire the decryption key (for legal reasons).

## Requirements
1. You would need to download ffmpeg and mp4decrypter from Bento4 SDK and ensure they are in path(typing their name in cmd invokes them).

## Usage
*quick and dirty how-to*
1. you need to open the network tab, and find the index.mpd file url
![index mpd](https://i.imgur.com/MW78CAu.png)
2. open the `dashdownloader_multisegment.py` file and replace ``mpd url`` with the url
![mpd url](https://i.imgur.com/YfGSPKd.png)
3. Change the video title and output path to whatever you want the video to be called
![title](https://i.imgur.com/lymSmag.png)
``175. Inverse Transforming Vectors`` is what your would replace
4. rename ``keyfile.example.json`` to ``keyfile.json``
5. open ``keyfile.json`` and enter the key id and decryption key for the video
![keyfile example](https://i.imgur.com/naABWva.png)
![example key and kid from console](https://i.imgur.com/awgndZA.png)
6. run ``python dashdownloader_multisegment.py`` in the terminal to start the download.
make sure you have ffmpeg and mp4decrypt installed in your path

# Credits
https://github.com/Jayapraveen/Drm-Dash-stream-downloader - for the original code which this is based on
https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
https://github.com/alastairmccormack/pymp4parse/ - For code related to mp4 box parsing (used by pywvpssh)
