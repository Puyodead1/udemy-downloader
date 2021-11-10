# Udemy Downloader with DRM support

[![forthebadge](https://forthebadge.com/images/badges/built-with-love.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/designed-in-ms-paint.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/made-with-python.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/approved-by-george-costanza.svg)](https://forthebadge.com)
![GitHub forks](https://img.shields.io/github/forks/Puyodead1/udemy-downloader?style=for-the-badge)
![GitHub Repo stars](https://img.shields.io/github/stars/Puyodead1/udemy-downloader?style=for-the-badge)
![GitHub](https://img.shields.io/github/license/Puyodead1/udemy-downloader?style=for-the-badge)

# NOTE

- **This tool will not work without decryption keys, and there currently no public way to get those keys. Do not bother installing unless you already have keys!**
- This program is WIP, the code is provided as-is and I am not held resposible for any legal issues resulting from the use of this program.

# Support

if you want help using the program, join [my discord server](https://discord.gg/5B3XVb4RRX) or use [github issues](https://github.com/Puyodead1/udemy-downloader/issues)

# License

All code is licensed under the MIT license

# Description

Utility script to download Udemy courses, has support for DRM videos but requires the user to acquire the decryption key (for legal reasons).<br>
Windows is the primary development OS, but I've made an effort to support Linux also.

# Requirements

1. You would need to download `ffmpeg`, `aria2c`, `mp4decrypt` (from Bento4 SDK) and `yt-dlp` (this is installed with the other requirements). Ensure they are in the system path (typing their name in cmd should invoke them).

# Usage

_quick and dirty how-to_

You will need to get a few things before you can use this program:

- Decryption Key ID
- Decryption Key
- Udemy Course URL
- Udemy Bearer Token (aka acccess token for udemy-dl users)

### Setting up

- install python 3.6+
- install requirements: `pip install -r requirements.txt`
- rename `.env.sample` to `.env` _(you only need to do this if you plan to use the .env file to store your bearer token)_
- rename `keyfile.example.json` to `keyfile.json` _(this is only required if you plan to download DRM encrypted lectures)_

### Acquire Bearer Token

- Firefox: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-491903900)
- Chrome: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-492569372)
- If you want to use the .env file to store your Bearer Token, edit the .env and add your token.

### Key ID and Key

I would rather not instruct you how to get these as its a grey area in terms of legality. I would prefer if you don't ask me for help getting these.

- Enter the key and key id in the `keyfile.json`
- ![keyfile example](https://i.imgur.com/e5aU0ng.png)
- ![example key and kid from console](https://i.imgur.com/awgndZA.png)

### Start Downloading

You can now run the program, see the examples below. The course will download to `out_dir`.

# Udemy Subscription Plans

To download a course included in a subscription plan that you did not purchase individually, you will need to follow a few more steps to get setup.

## Getting your cookies

- Go to the page of the course you want to download
- press `control` + `shift` + `i` (this may be different depending on your OS, just google how to open developer tools)
- click the `Console` tab
- copy and paste `document.cookie` and press enter
- copy the text between the quotes

## Setup token file

- Create a file called `cookies.txt`
- Paste the cookie into the file
- save and close the file

# Advanced Usage

```
usage: udemy_downloader [-h] -c COURSE_URL [-b BEARER_TOKEN] [-q QUALITY] [-l LANG] [-cd CONCURRENT_CONNECTIONS] [--skip-lectures] [--download-assets] [--download-captions] [--keep-vtt] [--skip-hls] [--info]
                        [--use-h265] [--h265-crf H265_CRF] [--ffmpeg-preset FFMPEG_PRESET] [--ffmpeg-framerate FFMPEG_FRAMERATE] [--h265-encoder H265_ENCODER] [-v]

Udemy Downloader

optional arguments:
  -h, --help            show this help message and exit
  -c COURSE_URL, --course-url COURSE_URL
                        The URL of the course to download
  -b BEARER_TOKEN, --bearer BEARER_TOKEN
                        The Bearer token to use
  -q QUALITY, --quality QUALITY
                        Download specific video quality. If the requested quality isn't available, the closest quality will be used. If not specified, the best quality will be downloaded for each lecture
  -l LANG, --lang LANG  The language to download for captions, specify 'all' to download all captions (Default is 'en')
  -cd CONCURRENT_CONNECTIONS, --concurrent-connections CONCURRENT_CONNECTIONS
                        The number of maximum concurrent connections per download for segments (HLS and DASH, must be a number 1-30)
  --skip-lectures       If specified, lectures won't be downloaded
  --download-assets     If specified, lecture assets will be downloaded
  --download-captions   If specified, captions will be downloaded
  --keep-vtt            If specified, .vtt files won't be removed
  --skip-hls            If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p quality for non-drm lectures)
  --info                If specified, only course information will be printed, nothing will be downloaded
  --use-h265            If specified, videos will be encoded with the H.265 codec
  --h265-crf H265_CRF   Set a custom CRF value for H.265 encoding. FFMPEG default is 28
  --ffmpeg-preset FFMPEG_PRESET
                        Set a custom preset value for encoding. This can vary depending on the encoder
  --ffmpeg-framerate FFMPEG_FRAMERATE
                        Changes the FPS used for encoding. FFMPEG default is 30
  --h265-encoder H265_ENCODER
                        Changes the HEVC encder that is used. Default is copy when not using h265, otherwise the default is libx265
  -v, --version         show program's version number and exit
```

- Passing a Bearer Token and Course ID as an argument
  - `python udemy_downloader -c <Course URL> -b <Bearer Token>`
  - `python udemy_downloader -c https://www.udemy.com/courses/myawesomecourse -b <Bearer Token>`
- Download a specific quality
  - `python udemy_downloader -c <Course URL> -q 720`
- Download assets along with lectures
  - `python udemy_downloader -c <Course URL> --download-assets`
- Download assets and specify a quality
  - `python udemy_downloader -c <Course URL> -q 360 --download-assets`
- Download captions (Defaults to English)
  - `python udemy_downloader -c <Course URL> --download-captions`
- Download captions with specific language
  - `python udemy_downloader -c <Course URL> --download-captions -l en` - English subtitles
  - `python udemy_downloader -c <Course URL> --download-captions -l es` - Spanish subtitles
  - `python udemy_downloader -c <Course URL> --download-captions -l it` - Italian subtitles
  - `python udemy_downloader -c <Course URL> --download-captions -l pl` - Polish Subtitles
  - `python udemy_downloader -c <Course URL> --download-captions -l all` - Downloads all subtitles
  - etc
- Skip downloading lecture videos
  - `python udemy_downloader -c <Course URL> --skip-lectures --download-captions` - Downloads only captions
  - `python udemy_downloader -c <Course URL> --skip-lectures --download-assets` - Downloads only assets
- Keep .VTT caption files:
  - `python udemy_downloader -c <Course URL> --download-captions --keep-vtt`
- Skip parsing HLS Streams (HLS streams usually contain 1080p quality for Non-DRM lectures):
  - `python udemy_downloader -c <Course URL> --skip-hls`
- Print course information only:
  - `python udemy_downloader -c <Course URL> --info`
- Specify max number of concurrent downloads:
  - `python udemy_downloader -c <Course URL> --concurrent-downloads 20`
  - `python udemy_downloader -c <Course URL> -cd 20`
- Encode in H.265:
  - `python udemy_downloader -c <Course URL> --use-h265`
- Encode in H.265 with custom CRF:
  - `python udemy_downloader -c <Course URL> --use-h265 -h265-crf 20`
- Encode in H.265 with custom preset using the default encoder (libx265):
  - `python udemy_downloader -c <Course URL> --use-h265 --h265-preset faster`
- Encode in H.265 with custom preset using a custom encoder:
  - **Note**: _The presets may be different depending on the encoder! For example: `hevc_nvenc` default is `p4` and `libx265` is `medium`_
  - _You can view encoder help with `ffmpeg -h encoder=<encoder name>`, ex: `ffmpeg -h encoder=hevc_nvenc`_
  - `python udemy_downloader -c <Course URL> --use-h265 --h265-encoder hevc_nvenc --h265-preset p7`
- Encode in H.265 with a custom framerate:
  - `python udemy_downloader -c <Course URL> --use-h265 --ffmpeg-framerate 24`

# Credits

- https://github.com/Jayapraveen/Drm-Dash-stream-downloader - For the original code which this is based on
- https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
- https://github.com/alastairmccormack/pymp4parse - For code related to mp4 box parsing (used by pywvpssh)
- https://github.com/lbrayner/vtt-to-srt - For code related to converting subtitles from vtt to srt format
- https://github.com/r0oth3x49/udemy-dl - For some of the informaton related to using the udemy api
