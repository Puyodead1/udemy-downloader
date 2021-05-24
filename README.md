# Udemy Downloader with DRM support
[![forthebadge](https://forthebadge.com/images/badges/built-with-love.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/designed-in-ms-paint.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/made-with-python.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/approved-by-george-costanza.svg)](https://forthebadge.com)
![GitHub forks](https://img.shields.io/github/forks/Puyodead1/udemy-downloader?style=for-the-badge)
![GitHub Repo stars](https://img.shields.io/github/stars/Puyodead1/udemy-downloader?style=for-the-badge)
![GitHub](https://img.shields.io/github/license/Puyodead1/udemy-downloader?style=for-the-badge)
# NOTE

This program is WIP, the code is provided as-is and I am not held resposible for any legal issues resulting from the use of this program.

# Support

if you want help using the program, join [my discord server](https://discord.gg/5B3XVb4RRX) or use [github issues](https://github.com/Puyodead1/udemy-downloader/issues)

# License

All code is licensed under the MIT license

# Description

Simple program to download a Udemy course, has support for DRM videos but requires the user to aquire the decryption key (for legal reasons).<br>
Current only Windows is supported but with some small modifications it should work on linux also (and maybe mac)

# Requirements

1. You would need to download `ffmpeg` and `mp4decrypter`from Bento4 SDK and ensure they are in path (typing their name in cmd invokes them).

# Usage

_quick and dirty how-to_

You will need to get a few things before you can use this program:

- Decryption Key ID
- Decryption Key
- Udemy Course ID
- Udemy Bearer Token

### Setting up

- rename `.env.sample` to `.env`
- rename `keyfile.example.json` to `keyfile.json`

### Aquire bearer token

- open dev tools
- go to network tab
- in the search field, enter `api-2.0/courses`
- ![Valid udemy api requests](https://i.imgur.com/Or371l7.png)
- click a random request
- locate the `Request Headers` section
- copy the the text after `Authorization`, it should look like `Bearer xxxxxxxxxxx`
- ![bearer token example](https://i.imgur.com/FhQdwgD.png)
- enter this in the `.env` file after `UDEMY_BEARER=` (you can also pass this as an argument, see advanced usage for more information)

### Aquire Course ID

- Follow above before following this
- locate the request url field
- ![request url](https://i.imgur.com/EUIV3bk.png)
- copy the number after `/api-2.0/courses/` as seen highlighed in the above picture
- enter this in the `.env` file after `UDEMY_COURSE_ID=` (you can also pass this as an argument, see advanced usage for more information)

### Key ID and Key

It is up to you to aquire the key and key id.

- Enter the key and key id in the `keyfile.json`
- ![keyfile example](https://i.imgur.com/wLPsqOR.png)
- ![example key and kid from console](https://i.imgur.com/awgndZA.png)

### Start Downloading

You can now run `python main.py` to start downloading. The course will download to `out_dir`, chapters are seperated into folders.

# Advanced Usage

```
usage: main.py [-h] [-d] [-b BEARER_TOKEN] [-c COURSE_ID] [-q QUALITY] [-l LANG] [--skip-lectures] [--download-assets] [--download-captions]

Udemy Downloader

optional arguments:
  -h, --help            show this help message and exit
  -d, --debug           Use test_data.json rather than fetch from the udemy api.
  -b BEARER_TOKEN, --bearer BEARER_TOKEN
                        The Bearer token to use
  -c COURSE_ID, --course-id COURSE_ID
                        The ID of the course to download
  -q QUALITY, --quality QUALITY
                        Download specific video quality. (144, 360, 480, 720, 1080)
  -l LANG, --lang LANG  The language to download for captions (Default is en)
  --skip-lectures       If specified, lectures won't be downloaded.
  --download-assets     If specified, lecture assets will be downloaded.
  --download-captions   If specified, captions will be downloaded.
```

- Passing a Bearer Token and Course ID as an argument
  - `python main.py -b <Bearer Token> -c <Course ID>`
- Download a specific quality
  - `python main.py -q 720`
- Download assets along with lectures
  - `python main.py --download-assets`
- Download assets and specify a quality
  - `python main.py -q 360 --download-assets`
- Download captions (Defaults to English)
  - `python main.py --download-captions`
- Download captions with specific language
  - `python main.py --download-captions -l en` - English subtitles
  - `python main.py --download-captions -l es` - Spanish subtitles
  - `python main.py --download-captions -l it` - Italian subtitles
  - `python main.py --download-captions -l pl` - Polish Subtitles
  - `python main.py --download-captions -l all` - Downloads all subtitles
  - etc
- Skip downloading lecture videos
  - `python main.py --skip-lectures --download-captions` - Downloads only captions
  - `python main.py --skip-lectures --download-assets` - Downloads only assets

# Getting an error about "Accepting the latest terms of service"?

- If you are using Udemy business, you must edit `main.py` and change `udemy.com` to `<portal name>.udemy.com`

# Credits

- https://github.com/Jayapraveen/Drm-Dash-stream-downloader - For the original code which this is based on
- https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
- https://github.com/alastairmccormack/pymp4parse/ - For code related to mp4 box parsing (used by pywvpssh)
- https://github.com/lbrayner/vtt-to-srt - For code related to converting subtitles from vtt to srt format
