# Udemy Downloader with DRM support

[![forthebadge](https://forthebadge.com/images/badges/built-with-love.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/designed-in-ms-paint.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/made-with-python.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/approved-by-george-costanza.svg)](https://forthebadge.com)
![GitHub forks](https://img.shields.io/github/forks/Puyodead1/udemy-downloader?style=for-the-badge)
![GitHub Repo stars](https://img.shields.io/github/stars/Puyodead1/udemy-downloader?style=for-the-badge)
![GitHub](https://img.shields.io/github/license/Puyodead1/udemy-downloader?style=for-the-badge)

# NOTE

-   If you ask about keys in the issues, your message will be deleted and you will be blocked.
-   **Downloading courses is against Udemy's Terms of Service, I am NOT held responsible for your account getting suspended as a result from the use of this program!**
-   This program is WIP, the code is provided as-is and I am not held resposible for any legal issues resulting from the use of this program.

# Description

Utility script to download Udemy courses, has support for DRM videos but requires the user to acquire the decryption key (for legal reasons).<br>
Windows is the primary development OS, but I've made an effort to support Linux also (Mac untested).

> [!IMPORTANT]  
> This tool will not work on encrypted courses without decryption keys being provided!
>
> Downloading courses is against Udemy's Terms of Service, I am NOT held responsible for your account getting suspended as a result from the use of this program!
>
> This program is WIP, the code is provided as-is and I am not held resposible for any legal issues resulting from the use of this program.

# Requirements

The following are a list of required third-party tools, you will need to ensure they are in your systems path and that typing their name in a terminal invokes them.

> [!NOTE]  
> These are seperate requirements that are not installed with the pip command!
>
> You will need to download and install these manually!

-   [Python 3](https://python.org/)
-   [ffmpeg](https://www.ffmpeg.org/) - This tool is also available in Linux package repositories.
    -   NOTE: It is recommended to use a custom build from the yt-dlp team that contains various patches for issues when used alongside yt-dlp, however it is not required. Latest builds can be found [here](https://github.com/yt-dlp/FFmpeg-Builds/releases/tag/latest)
-   [aria2/aria2c](https://github.com/aria2/aria2/) - This tool is also available in Linux package repositories
-   [shaka-packager](https://github.com/shaka-project/shaka-packager/releases/latest)
-   [yt-dlp](https://github.com/yt-dlp/yt-dlp/) - This tool is also available in Linux package repositories, but can also be installed using pip if desired (`pip install yt-dlp`)

# Usage

You will need to get a few things before you can use this program:

-   Decryption Key ID
-   Decryption Key
-   Udemy Course URL
-   Udemy Bearer Token (aka acccess token for udemy-dl users)
-   Udemy cookies (only required for subscription plans - see [Udemy Subscription Plans](#udemy-subscription-plans))

## Setting up

-   rename `.env.sample` to `.env` _(you only need to do this if you plan to use the .env file to store your bearer token)_
-   rename `keyfile.example.json` to `keyfile.json`

## Acquire Bearer Token

-   Firefox: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-491903900)
-   Chrome: [Udemy-DL Guide](https://github.com/r0oth3x49/udemy-dl/issues/389#issuecomment-492569372)
-   If you want to use the .env file to store your Bearer Token, edit the .env and add your token.

## Key ID and Key

> [!IMPORTANT]  
> For courses that are encrypted, It is up to you to acquire the decryption keys.
>
> Please **DO NOT** ask me for help acquiring these!

-   Enter the key and key id in the `keyfile.json`
-   ![keyfile example](https://i.imgur.com/e5aU0ng.png)
-   ![example key and kid from console](https://i.imgur.com/awgndZA.png)

## Cookies

> [!TIP]
> Cookies are not required for individually purchased courses.

To download a course included in a subscription plan that you did not purchase individually, you will need to use cookies. You can also use cookies as an alternative to Bearer Tokens.

The program can automatically extract them from your browser. You can specify what browser to extract cookies from with the `--browser` argument. Supported browsers are:

-   `chrome`
-   `firefox`
-   `opera`
-   `edge`
-   `brave`
-   `chromium`
-   `vivaldi`
-   `safari`

## Ready to go

You can now run the program, see the examples below. The course will download to `out_dir`.

# Advanced Usage

```
usage: __main__.py [-h] [-b BEARER_TOKEN] [-q QUALITY] [-l LANG] [-cd CONCURRENT_DOWNLOADS] [--skip-lectures]
                   [--download-assets] [--download-captions] [--download-quizzes] [--keep-vtt] [--skip-hls] [--info]
                   [--id-as-course-name] [-sc] [--save-to-file] [--load-from-file] [--log-level LOG_LEVEL]
                   [--browser {chrome,firefox,opera,edge,brave,chromium,vivaldi,safari,file}] [--use-h265]
                   [--h265-crf H265_CRF] [--h265-preset H265_PRESET] [--use-nvenc] [--out OUT]
                   [--continue-lecture-numbers] [--chapter CHAPTER_FILTER_RAW] [--device DEVICE]
                   course_url

Udemy Downloader

positional arguments:
  course_url            The URL of the course to download

options:
  -h, --help            show this help message and exit
  -b, --bearer BEARER_TOKEN
                        The Bearer token to use
  -q, --quality QUALITY
                        Download specific video quality. If the requested quality isn't available, the closest quality
                        will be used. If not specified, the best quality will be downloaded for each lecture
  -l, --lang LANG       The language to download for captions, specify 'all' to download all captions (Default is
                        'en')
  -cd, --concurrent-downloads CONCURRENT_DOWNLOADS
                        The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-30)
  --skip-lectures       If specified, lectures won't be downloaded
  --download-assets     If specified, lecture assets will be downloaded
  --download-captions   If specified, captions will be downloaded
  --download-quizzes    If specified, quizzes will be downloaded
  --keep-vtt            If specified, .vtt files won't be removed
  --skip-hls            If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p
                        quality for non-drm lectures)
  --info                If specified, only course information will be printed, nothing will be downloaded
  --id-as-course-name   If specified, the course id will be used in place of the course name for the output directory.
                        This is a 'hack' to reduce the path length
  -sc, --subscription-course
                        Mark the course as a subscription based course, use this if you are having problems with the
                        program auto detecting it
  --save-to-file        If specified, course content will be saved to a file that can be loaded later with --load-
                        from-file, this can reduce processing time (Note that asset links expire after a certain
                        amount of time)
  --load-from-file      If specified, course content will be loaded from a previously saved file with --save-to-file,
                        this can reduce processing time (Note that asset links expire after a certain amount of time)
  --log-level LOG_LEVEL
                        Logging level: one of DEBUG, INFO, ERROR, WARNING, CRITICAL (Default is INFO)
  --browser {chrome,firefox,opera,edge,brave,chromium,vivaldi,safari,file}
                        The browser to extract cookies from
  --use-h265            If specified, videos will be encoded with the H.265 codec
  --h265-crf H265_CRF   Set a custom CRF value for H.265 encoding. FFMPEG default is 28
  --h265-preset H265_PRESET
                        Set a custom preset value for H.265 encoding. FFMPEG default is medium
  --use-nvenc           Whether to use the NVIDIA hardware transcoding for H.265. Only works if you have a supported
                        NVIDIA GPU and ffmpeg with nvenc support
  --out, -o OUT         Set the path to the output directory
  --continue-lecture-numbers, -n
                        Use continuous lecture numbering instead of per-chapter
  --chapter CHAPTER_FILTER_RAW
                        Download specific chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').
  --device, -d DEVICE   Name of WVD file to use
```

-   Passing a Bearer Token and Course ID as an argument
    -   `python -m udemy_downloader <Course URL> -b <Bearer Token>`
    -   `python -m udemy_downloader https://www.udemy.com/courses/myawesomecourse -b <Bearer Token>`
-   Download a specific quality
    -   `python -m udemy_downloader <Course URL> -q 720`
-   Download assets along with lectures
    -   `python -m udemy_downloader <Course URL> --download-assets`
-   Download assets and specify a quality
    -   `python -m udemy_downloader <Course URL> -q 360 --download-assets`
-   Download captions (Defaults to English)
    -   `python -m udemy_downloader <Course URL> --download-captions`
-   Download captions with specific language
    -   `python -m udemy_downloader <Course URL> --download-captions -l en` - English subtitles
    -   `python -m udemy_downloader <Course URL> --download-captions -l es` - Spanish subtitles
    -   `python -m udemy_downloader <Course URL> --download-captions -l it` - Italian subtitles
    -   `python -m udemy_downloader <Course URL> --download-captions -l pl` - Polish Subtitles
    -   `python -m udemy_downloader <Course URL> --download-captions -l all` - Downloads all subtitles
    -   etc
-   Skip downloading lecture videos
    -   `python -m udemy_downloader <Course URL> --skip-lectures --download-captions` - Downloads only captions
    -   `python -m udemy_downloader <Course URL> --skip-lectures --download-assets` - Downloads only assets
-   Keep .VTT caption files:
    -   `python -m udemy_downloader <Course URL> --download-captions --keep-vtt`
-   Skip parsing HLS Streams (HLS streams usually contain 1080p quality for Non-DRM lectures):
    -   `python -m udemy_downloader <Course URL> --skip-hls`
-   Print course information only:
    -   `python -m udemy_downloader <Course URL> --info`
-   Specify max number of concurrent downloads:
    -   `python -m udemy_downloader <Course URL> --concurrent-downloads 20`
    -   `python -m udemy_downloader <Course URL> -cd 20`
-   Cache course information:
    -   `python -m udemy_downloader <Course URL> --save-to-file`
-   Load course cache:
    -   `python -m udemy_downloader <Course URL> --load-from-file`
-   Change logging level:
    -   `python -m udemy_downloader <Course URL> --log-level DEBUG`
    -   `python -m udemy_downloader <Course URL> --log-level WARNING`
    -   `python -m udemy_downloader <Course URL> --log-level INFO`
    -   `python -m udemy_downloader <Course URL> --log-level CRITICAL`
-   Use course ID as the course name:
    -   `python -m udemy_downloader <Course URL> --id-as-course-name`
-   Encode in H.265:
    -   `python -m udemy_downloader <Course URL> --use-h265`
-   Encode in H.265 with custom CRF:
    -   `python -m udemy_downloader <Course URL> --use-h265 -h265-crf 20`
-   Encode in H.265 with custom preset:
    -   `python -m udemy_downloader <Course URL> --use-h265 --h265-preset faster`
-   Encode in H.265 using NVIDIA hardware transcoding:
    -   `python -m udemy_downloader <Course URL> --use-h265 --use-nvenc`
-   Use continuous numbering (don't restart at 1 in every chapter):
    -   `python -m udemy_downloader <Course URL> --continue-lecture-numbers`
    -   `python -m udemy_downloader <Course URL> -n`
-   Download specific chapters:
    -   `python -m udemy_downloader <Course URL> --chapter "1,3,5"` - Downloads chapters 1, 3, and 5
    -   `python -m udemy_downloader <Course URL> --chapter "1-5"` - Downloads chapters 1 through 5
    -   `python -m udemy_downloader <Course URL> --chapter "1,3-5,7,9-11"` - Downloads chapters 1, 3 through 5, 7, and 9 through 11
-   Download specific chapters with quality:
    -   `python -m udemy_downloader <Course URL> --chapter "1-3" -q 720`
-   Download specific chapters with captions:
    -   `python -m udemy_downloader <Course URL> --chapter "1,3" --download-captions`

# Support

if you want help using the program, join my [Discord](https://discord.gg/tMzrSxQ) server or use [GitHub Issues](https://github.com/Puyodead1/udemy-downloader/issues)

# Credits

-   https://github.com/Jayapraveen/Drm-Dash-stream-downloader - For the original code which this is based on
-   https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
-   https://github.com/alastairmccormack/pymp4parse - For code related to mp4 box parsing (used by pywvpssh)
-   https://github.com/lbrayner/vtt-to-srt - For code related to converting subtitles from vtt to srt format
-   https://github.com/r0oth3x49/udemy-dl - For some of the informaton related to using the udemy api

## License

All code is licensed under the MIT license

## and finally, donations!

Woo, you made it this far!

I spend a lot of time coding things, and almost all of them are for nothing in return. When theres a lot of use of a program I make, I try to keep it updated, fix bugs, and even implement new features! But after a while, I do run out of motivation to keep doing it. If you like my work, and can help me out even a little, it would really help me out. If you are interested, you can find all the available options [here](https://github.com/Puyodead1/#supporting-me). Even if you don't, thank you anyways!
