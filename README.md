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
- **Downloading courses is against Udemy's Terms of Service, I am NOT held responsible for your account getting suspended as a result from the use of this program!**
- This program is WIP, the code is provided as-is and I am not held resposible for any legal issues resulting from the use of this program.
- You can find information on downgrading the CDM version on the wiki, please note that CDM version 2209 is already revoked as of 12/5/2021 and most providers have already updated, 2209 is not guaranteed to work. This information is just to have it available.
  - Chrome: https://github.com/Puyodead1/udemy-downloader/wiki/Downgrade-CDM-to-2209-on-Chrome-(Windows)
  - FireFox: https://github.com/Puyodead1/udemy-downloader/wiki/Downgrade-CDM-to-2209-on-FireFox-(Windows)

# Description

Utility script to download Udemy courses, has support for DRM videos but requires the user to aquire the decryption key (for legal reasons).<br>
Windows is the primary development OS, but I've made an effort to support Linux also (Mac untested).

# Requirements

The following are a list of required third-party tools, you will need to ensure they are in your systems path and that typing their name in a terminal invokes them.

_**Note**:_ _These are seperate requirements that are not installed with the pip command! You will need to download and install these manually!_

- [ffmpeg](https://www.ffmpeg.org/) - This tool is available in Linux package repositories
- [aria2/aria2c](https://github.com/aria2/aria2/) - This tool is available in Linux package repositories
- [mp4decrypt](https://www.bento4.com/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp/) - This tool is available in Linux package repositories, but can also be installed using pip if desired (`pip install yt-dlp`)

# Usage

_quick and dirty how-to_

You will need to get a few things before you can use this program:

- Decryption Key ID
- Decryption Key
- Udemy Course URL
- Udemy Bearer Token (aka acccess token for udemy-dl users)
- Udemy cookies (only required for subscription plans - see [Udemy Subscription Plans](#udemy-subscription-plans))

## Setting up

- rename `.env.sample` to `.env` _(you only need to do this if you plan to use the .env file to store your bearer token)_
- rename `keyfile.example.json` to `keyfile.json`

## Aquire Bearer Token

- Firefox: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-491903900)
- Chrome: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-492569372)
- If you want to use the .env file to store your Bearer Token, edit the .env and add your token.

## Key ID and Key

It is up to you to aquire the key and key ID. Please **DO NOT** ask me for help acquiring these, decrypting DRM protected content can be considered piracy. The tool required for this has already been discused in a GitHub issue.

- Enter the key and key id in the `keyfile.json`
- ![keyfile example](https://i.imgur.com/e5aU0ng.png)
- ![example key and kid from console](https://i.imgur.com/awgndZA.png)

## Start Downloading

You can now run the program, see the examples below. The course will download to `out_dir`.

# Udemy Subscription Plans

To download a course included in a subscription plan that you did not purchase individually, you will need to follow a few more steps to get setup.

_**NOTE**:_ _You do **NOT** need to follow this section if you don't have a **Udemy Pro** or **Udemy Personal** subscription plan! This section is not for individually purchased courses._

## Getting your cookies

- Go to the page of the course you want to download
- press `control` + `shift` + `i` (this may be different depending on your OS, just google how to open developer tools)
- click the `Console` tab
- copy and paste `document.cookie` and press enter
- copy the text between the quotes

## Setup cookie file

- Create a file called `cookies.txt` in the same folder as `main.py`
- Paste the cookie into the file
- save and close the file

You will also need to ensure the link is in the following format: `https://www.udemy.com/course/<course name>/learn/`.

Note the link is `/course` not `/program-taking`. It is also important that the link has `/learn`, otherwise you will see an error when trying to fetch the course information.

# Advanced Usage

```
usage: main.py [-h] -c COURSE_URL [-b BEARER_TOKEN] [-q QUALITY] [-l LANG] [-cd CONCURRENT_DOWNLOADS] [--disable-ipv6]
               [--skip-lectures] [--download-assets] [--download-captions] [--keep-vtt] [--skip-hls] [--info] [-v]

Udemy Downloader

options:
  -h, --help            show this help message and exit
  -c COURSE_URL, --course-url COURSE_URL
                        The URL of the course to download
  -b BEARER_TOKEN, --bearer BEARER_TOKEN
                        The Bearer token to use
  -q QUALITY, --quality QUALITY
                        Download specific video quality. If the requested quality isn't available, the closest quality
                        will be used. If not specified, the best quality will be downloaded for each lecture
  -l LANG, --lang LANG  The language to download for captions, specify 'all' to download all captions (Default is
                        'en')
  -cd CONCURRENT_DOWNLOADS, --concurrent-downloads CONCURRENT_DOWNLOADS
                        The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-30)
  --disable-ipv6        If specified, ipv6 will be disabled in aria2
  --skip-lectures       If specified, lectures won't be downloaded
  --download-assets     If specified, lecture assets will be downloaded
  --download-captions   If specified, captions will be downloaded
  --keep-vtt            If specified, .vtt files won't be removed
  --skip-hls            If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p
                        quality for non-drm lectures)
  --info                If specified, only course information will be printed, nothing will be downloaded
  -v, --version         show program's version number and exit
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

If you encounter errors while downloading such as

`errorCode=1 Network problem has occurred. cause:Unknown socket error 10051 (0x2743)`

or

`errorCode=1 Network problem has occurred. cause:A socket operation was attempted to an unreachable network.`

Then try disabling ipv6 in aria2 using the `--disable-ipv6` option

# Support

if you want help using the program, join my [Discord](https://discord.gg/5B3XVb4RRX) server or use [GitHub Issues](https://github.com/Puyodead1/udemy-downloader/issues)

# Credits

- https://github.com/Jayapraveen/Drm-Dash-stream-downloader - For the original code which this is based on
- https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
- https://github.com/alastairmccormack/pymp4parse - For code related to mp4 box parsing (used by pywvpssh)
- https://github.com/lbrayner/vtt-to-srt - For code related to converting subtitles from vtt to srt format
- https://github.com/r0oth3x49/udemy-dl - For some of the informaton related to using the udemy api

## License

All code is licensed under the MIT license

## and finally, donations!

Woo, you made it this far!

I spend a lot of time coding things, and almost all of them are for nothing in return. When theres a lot of use of a program I make, I try to keep it updated, fix bugs, and even implement new features! But after a while, I do run out of motivation to keep doing it. If you like my work, and can help me out even a little, it would really help me out. If you are interested, you can find all the available options [here](https://github.com/Puyodead1/#supporting-me). Even if you don't, thank you anyways!
