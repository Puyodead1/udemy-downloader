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
Windows is the primary development OS, but I've made an effort to support linux also.

# Requirements

1. You would need to download `ffmpeg`, `aria2c` and `mp4decrypt` (from Bento4 SDK) and ensure they are in path (typing their name in cmd should invoke them).

# Usage

_quick and dirty how-to_

You will need to get a few things before you can use this program:

- Decryption Key ID
- Decryption Key
- Udemy Course URL
- Udemy Bearer Token (aka acccess token for udemy-dl users)

### Setting up

- rename `.env.sample` to `.env` _(you only need to do this if you plan to use the .env file to store your bearer token)_
- rename `keyfile.example.json` to `keyfile.json`

### Aquire Bearer Token

- Firefox: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-491903900)
- Chrome: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-492569372)
- If you want to use the .env file to store your Bearer Token, edit the .env and add your token.

### Key ID and Key

It is up to you to aquire the key and key id. Please don't ask me for help acquiring these, decrypting DRM protected content can be considered piracy.

- Enter the key and key id in the `keyfile.json`
- ![keyfile example](https://i.imgur.com/e5aU0ng.png)
- ![example key and kid from console](https://i.imgur.com/awgndZA.png)

### Start Downloading

You can now run the program, see the examples below. The course will download to `out_dir`.

# Advanced Usage

```
usage: main.py [-h] -c COURSE_URL [-b BEARER_TOKEN] [-q QUALITY] [-l LANG] [-cd CONCURRENT_DOWNLOADS] [--skip-lectures] [--download-assets]
               [--download-captions] [--keep-vtt] [--skip-hls] [--info]

Udemy Downloader

optional arguments:
  -h, --help            show this help message and exit
  -c COURSE_URL, --course-url COURSE_URL
                        The URL of the course to download
  -b BEARER_TOKEN, --bearer BEARER_TOKEN
                        The Bearer token to use
  -q QUALITY, --quality QUALITY
                        Download specific video quality. If the requested quality isn't available, the closest quality will be used. If not
                        specified, the best quality will be downloaded for each lecture
  -l LANG, --lang LANG  The language to download for captions, specify 'all' to download all captions (Default is 'en')
  -cd CONCURRENT_DOWNLOADS, --concurrent-downloads CONCURRENT_DOWNLOADS
                        The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-50)
  --skip-lectures       If specified, lectures won't be downloaded
  --download-assets     If specified, lecture assets will be downloaded
  --download-captions   If specified, captions will be downloaded
  --keep-vtt            If specified, .vtt files won't be removed
  --skip-hls            If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p quality for non-drm
                        lectures)
  --info                If specified, only course information will be printed, nothing will be downloaded
```

- Passing a Bearer Token and Course ID as an argument
  - `python main.py -c <Course URL> -b <Bearer Token>`
  - `python main.py -c https://www.udemy.com/courses/myawesomecourse -b <Bearer Token>`
- Download a specific quality
  - `python main.py -c <Course URL> -q 720`
- Download assets along with lectures
  - `python main.py -c <Course URL> --download-assets`
- Download assets and specify a quality
  - `python main.py -c <Course URL> -q 360 --download-assets`
- Download captions (Defaults to English)
  - `python main.py -c <Course URL> --download-captions`
- Download captions with specific language
  - `python main.py -c <Course URL> --download-captions -l en` - English subtitles
  - `python main.py -c <Course URL> --download-captions -l es` - Spanish subtitles
  - `python main.py -c <Course URL> --download-captions -l it` - Italian subtitles
  - `python main.py -c <Course URL> --download-captions -l pl` - Polish Subtitles
  - `python main.py -c <Course URL> --download-captions -l all` - Downloads all subtitles
  - etc
- Skip downloading lecture videos
  - `python main.py -c <Course URL> --skip-lectures --download-captions` - Downloads only captions
  - `python main.py -c <Course URL> --skip-lectures --download-assets` - Downloads only assets
- Keep .VTT caption files:
  - `python main.py -c <Course URL> --download-captions --keep-vtt`
- Skip parsing HLS Streams (HLS streams usually contain 1080p quality for Non-DRM lectures):
  - `python main.py -c <Course URL> --skip-hls`
- Print course information only:
  - `python main.py -c <Course URL> --info`
- Specify max number of concurrent downloads:
  - `python main.py -c <Course URL> --concurrent-downloads 20`
  - `python main.py -c <Course URL> -cd 20`

# Credits

- https://github.com/Jayapraveen/Drm-Dash-stream-downloader - For the original code which this is based on
- https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
- https://github.com/alastairmccormack/pymp4parse - For code related to mp4 box parsing (used by pywvpssh)
- https://github.com/lbrayner/vtt-to-srt - For code related to converting subtitles from vtt to srt format
- https://github.com/r0oth3x49/udemy-dl - For some of the informaton related to using the udemy api
