# Udemy Downloader with DRM support

# NOTE

This program is WIP, the code is provided as-is and i am not held resposible for any legal repercussions resulting from the use of this program.

# Support

if you want help using the program, join [my discord server](https://discord.gg/5B3XVb4RRX) or use [github issues](https://github.com/Puyodead1/udemy-downloader/issues)

# License

All code is licensed under the MIT license

# Description

Simple and hacky program to download a udemy course, has support for DRM videos but requires the user to aquire the decryption key (for legal reasons).

# Requirements

1. You would need to download ffmpeg and mp4decrypter from Bento4 SDK and ensure they are in path(typing their name in cmd invokes them).

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
  ![Valid udemy api requests](https://i.imgur.com/Or371l7.png)
- click a random request
- locate the `Request Headers` section
- copy the the text after `Authorization`, it should look like `Bearer xxxxxxxxxxx`
  ![bearer token example](https://i.imgur.com/FhQdwgD.png)
- enter this in the `.env` file after `UDEMY_BEARER=`

### Aquire Course ID

- Follow above before following this
- locate the request url field
  ![request url](https://i.imgur.com/EUIV3bk.png)
- copy the number after `/api-2.0/courses/` as seen highlighed in the above picture
- enter this in the `.env` file after `UDEMY_COURSE_ID=`

### Key ID and Key

It is up to you to aquire the key and key id.

- Enter the key and key id in the `keyfile.json`
  ![keyfile example](https://i.imgur.com/wLPsqOR.png)
  ![example key and kid from console](https://i.imgur.com/awgndZA.png)

### Start Downloading

You can now run `python main.py` to start downloading. The course will download to `out_dir`, chapters are seperated into folders.

# Credits

https://github.com/Jayapraveen/Drm-Dash-stream-downloader - for the original code which this is based on
https://github.com/alastairmccormack/pywvpssh - For code related to PSSH extraction
https://github.com/alastairmccormack/pymp4parse/ - For code related to mp4 box parsing (used by pywvpssh)
