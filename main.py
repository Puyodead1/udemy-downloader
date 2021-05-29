import os, requests, shutil, json, glob, urllib.request, argparse, sys, datetime
from sanitize_filename import sanitize
import urllib.request
from tqdm import tqdm
from dotenv import load_dotenv
from mpegdash.parser import MPEGDASHParser
from utils import extract_kid
from vtt_to_srt import convert
from requests.exceptions import ConnectionError as conn_error
from html.parser import HTMLParser as compat_HTMLParser
from sanitize import sanitize, slugify, SLUG_OK
from pyffmpeg import FFMPeg as FFMPEG
import subprocess

course_id = None
header_bearer = None
download_dir = os.path.join(os.getcwd(), "out_dir")
working_dir = os.path.join(os.getcwd(), "working_dir")  # set the folder to download segments for DRM videos
retry = 3
home_dir = os.getcwd()
keyfile_path = os.path.join(os.getcwd(), "keyfile.json")
dl_assets = False
dl_captions = False
skip_lectures = False
caption_locale = "en"
quality = None  # None will download the best possible
valid_qualities = [144, 360, 480, 720, 1080]

if not os.path.exists(working_dir):
    os.makedirs(working_dir)

if not os.path.exists(download_dir):
    os.makedirs(download_dir)

#Get the keys
with open(keyfile_path, 'r') as keyfile:
    keyfile = keyfile.read()
keyfile = json.loads(keyfile)


def durationtoseconds(period):
    """
    @author Jayapraveen
    """

    #Duration format in PTxDxHxMxS
    if (period[:2] == "PT"):
        period = period[2:]
        day = int(period.split("D")[0] if 'D' in period else 0)
        hour = int(period.split("H")[0].split("D")[-1] if 'H' in period else 0)
        minute = int(
            period.split("M")[0].split("H")[-1] if 'M' in period else 0)
        second = period.split("S")[0].split("M")[-1]
        print("Total time: " + str(day) + " days " + str(hour) + " hours " +
              str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(
            str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) +
                (int(second.split('.')[0]))) + '.' +
            str(int(second.split('.')[-1])))
        return total_time

    else:
        print("Duration Format Error")
        return None


def download_media(filename, url, lecture_working_dir, epoch=0):
    if (os.path.isfile(filename)):
        print("Segment already downloaded.. skipping..")
    else:
        media = requests.get(url, stream=True)
        media_length = int(media.headers.get("content-length"))
        if media.status_code == 200:
            if (os.path.isfile(filename)
                    and os.path.getsize(filename) >= media_length):
                print("Segment already downloaded.. skipping write to disk..")
            else:
                try:
                    pbar = tqdm(total=media_length,
                                initial=0,
                                unit='B',
                                unit_scale=True,
                                desc=filename)
                    with open(os.path.join(lecture_working_dir, filename),
                              'wb') as video_file:
                        for chunk in media.iter_content(chunk_size=1024):
                            if chunk:
                                video_file.write(chunk)
                                pbar.update(1024)
                    pbar.close()
                    print("Segment downloaded: " + filename)
                    return False  #Successfully downloaded the file
                except:
                    print(
                        "Connection error: Reattempting download of segment..")
                    download_media(filename, url, lecture_working_dir,
                                   epoch + 1)

            if os.path.getsize(filename) >= media_length:
                pass
            else:
                print("Segment is faulty.. Redownloading...")
                download_media(filename, url, lecture_working_dir, epoch + 1)
        elif (media.status_code == 404):
            print("Probably end hit!\n", url)
            return True  #Probably hit the last of the file
        else:
            if (epoch > retry):
                exit("Error fetching segment, exceeded retry times.")
            print("Error fetching segment file.. Redownloading...")
            download_media(filename, url, lecture_working_dir, epoch + 1)


"""
@author Jayapraveen
"""


def cleanup(path):
    """
    @author Jayapraveen
    """
    leftover_files = glob.glob(path + '/*.mp4', recursive=True)
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            print(f"Error deleting file: {file_list}")
    os.removedirs(path)


"""
@author Jayapraveen
"""


def mux_process(video_title, lecture_working_dir, outfile):
    time_stamp = datetime.datetime.now().isoformat()+'Z'
    if os.name == "nt":
        command = f"ffmpeg -y -i \"{lecture_working_dir}\\decrypted_audio.mp4\" -i \"{lecture_working_dir}\\decrypted_video.mp4\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{video_title}\" -metadata creation_time=\"{time_stamp}\" \"{outfile}\""
    else:
        command = f"nice -n 7 ffmpeg -y -i \"{lecture_working_dir}//decrypted_audio.mp4\" -i \"{lecture_working_dir}//decrypted_video.mp4\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{video_title}\" -metadata creation_time=\"{time_stamp}\" \"{outfile}\""
    os.system(command)


def decrypt(kid, filename, lecture_working_dir):
    """
    @author Jayapraveen
    """
    print("> Decrypting, this might take a minute...")
    try:
        key = keyfile[kid.lower()]
    except KeyError as error:
        exit("Key not found")
    if (os.name == "nt"):
        os.system(
            f"mp4decrypt --key 1:{key} \"{lecture_working_dir}\\encrypted_{filename}.mp4\" \"{lecture_working_dir}\\decrypted_{filename}.mp4\""
        )
    else:
        os.system(
            f"nice -n 7 mp4decrypt --key 1:{key} \"{lecture_working_dir}//encrypted_{filename}.mp4\" \"{lecture_working_dir}//decrypted_{filename}.mp4\""
        )

    with open(list_path, 'w') as f:
        f.write("{}\n{}".format(audio_urls, video_urls))
        f.close()

    print("> Downloading Lecture Segments...")
    ret_code = subprocess.Popen([
        "aria2c", "-i", list_path, "-j16", "-s20", "-x16", "-c",
        "--auto-file-renaming=false", "--summary-interval=0"
    ]).wait()
    print("> Lecture Segments Downloaded")

    print("Return code: " + str(ret_code))

def handle_irregular_segments(media_info, video_title, lecture_working_dir,
                              output_path):
    no_segment, video_url, video_init, video_extension, no_segment, audio_url, audio_init, audio_extension = media_info
    download_media("video_0.seg.mp4", video_init, lecture_working_dir)
    video_kid = extract_kid(os.path.join(lecture_working_dir, "video_0.seg.mp4"))
    print("KID for video file is: " + video_kid)
    download_media("audio_0.seg.mp4", audio_init, lecture_working_dir)
    audio_kid = extract_kid(os.path.join(lecture_working_dir, "audio_0.seg.mp4"))
    print("KID for audio file is: " + audio_kid)

    os.chdir(lecture_working_dir)

    if os.name == "nt":
        video_concat_command = "copy /b " + "+".join([
            f"video_{i}.{video_extension}" for i in range(0, no_vid_segments)
        ]) + " encrypted_video.mp4"
        audio_concat_command = "copy /b " + "+".join([
            f"audio_{i}.{audio_extension}" for i in range(0, no_aud_segments)
        ]) + " encrypted_audio.mp4"
    else:
        video_concat_command = "cat " + " ".join([
            f"video_{i}.{video_extension}" for i in range(0, no_aud_segments)
        ]) + " > encrypted_video.mp4"
        audio_concat_command = "cat " + " ".join([
            f"audio_{i}.{audio_extension}" for i in range(0, no_vid_segments)
        ]) + " > encrypted_audio.mp4"
    os.system(video_concat_command)
    os.system(audio_concat_command)
    os.chdir(home_dir)
    try:
        decrypt(video_kid, "video", lecture_working_dir)
        decrypt(audio_kid, "audio", lecture_working_dir)
        os.chdir(home_dir)
        mux_process(video_title, lecture_working_dir, output_path)
        cleanup(lecture_working_dir)
    except Exception as e:
        print(f"Error: ", e)


def check_for_aria():
    try:
        subprocess.Popen(["aria2c", "-v"],
                         stdout=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print(
            "> Unexpected exception while checking for Aria2c, please tell the program author about this! ",
            e)
        return True


def check_for_ffmpeg():
    try:
        subprocess.Popen(["ffmpeg"],
                         stdout=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print(
            "> Unexpected exception while checking for FFMPEG, please tell the program author about this! ",
            e)
        return True


def check_for_mp4decrypt():
    try:
        subprocess.Popen(["mp4decrypt"],
                         stdout=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print(
            "> Unexpected exception while checking for MP4Decrypt, please tell the program author about this! ",
            e)
        return True


def download(url, path, filename):
    """
    @author Puyodead1
    """
    file_size = int(requests.head(url).headers["Content-Length"])
    if os.path.exists(path):
        first_byte = os.path.getsize(path)
    else:
        first_byte = 0
    if first_byte >= file_size:
        return file_size
    header = {"Range": "bytes=%s-%s" % (first_byte, file_size)}
    pbar = tqdm(total=file_size,
                initial=first_byte,
                unit='B',
                unit_scale=True,
                desc=filename)
    res = requests.get(url, headers=header, stream=True)
    res.raise_for_status()
    with (open(path, 'ab')) as f:
        for chunk in res.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                pbar.update(1024)
    pbar.close()
    return file_size


def process_caption(caption,
                    lecture_index,
                    lecture_title,
                    lecture_dir,
                    tries=0):
    filename = f"%s. %s_%s.%s" % (lecture_index, sanitize(lecture_title),
                                  caption.get("locale_id"), caption.get("ext"))
    filename_no_ext = f"%s. %s_%s" % (lecture_index, sanitize(lecture_title),
                                      caption.get("locale_id"))
    filepath = os.path.join(lecture_dir, filename)

    if os.path.isfile(filepath):
        print("    > Caption '%s' already downloaded." % filename)
    else:
        print(f"    >  Downloading caption: '%s'" % filename)
        try:
            download_aria(caption.get("download_url"), lecture_dir, filename)
        except Exception as e:
            if tries >= 3:
                print(
                    f"    > Error downloading caption: {e}. Exceeded retries, skipping."
                )
                return
            else:
                print(
                    f"    > Error downloading caption: {e}. Will retry {3-tries} more times."
                )
                process_caption(caption, lecture_title, lecture_dir, keep_vtt,
                                tries + 1)
        if caption.get("extension") == "vtt":
            try:
                print("    > Converting caption to SRT format...")
                convert(lecture_dir, filename_no_ext)
                print("    > Caption conversion complete.")
                if not keep_vtt:
                    os.remove(filepath)
            except Exception as e:
                print(f"    > Error converting caption: {e}")


def process_lecture(lecture, lecture_path, lecture_dir, quality, access_token):
    lecture_title = lecture.get("lecture_title")
    is_encrypted = lecture.get("is_encrypted")
    lecture_video_sources = lecture.get("video_sources")
    lecture_audio_sources = lecture.get("audio_sources")

    if is_encrypted:
        if len(lecture_audio_sources) > 0 and len(lecture_video_sources) > 0:
            lecture_working_dir = os.path.join(working_dir,
                                               str(lecture.get("asset_id")))

            if not os.path.isfile(lecture_path):
                video_source = lecture_video_sources[
                    -1]  # last index is the best quality
                audio_source = lecture_audio_sources[-1]
                if isinstance(quality, int):
                    video_source = min(
                        lecture_video_sources,
                        key=lambda x: abs(int(x.get("height")) - quality))
                if not os.path.exists(lecture_working_dir):
                    os.mkdir(lecture_working_dir)
                print(f"      > Lecture '%s' has DRM, attempting to download" %
                      lecture_title)
                handle_segments(video_source, audio_source, lecture_title,
                                lecture_working_dir, lecture_path)
            else:
                print(
                    "      > Lecture '%s' is already downloaded, skipping..." %
                    lecture_title)
        else:
            print(f"      > Lecture '%s' is missing media links" %
                  lecture_title)
            lecture_working_dir = os.path.join(
                working_dir, str(lecture_asset["id"])
            )  # set the folder to download ephemeral files
            media_sources = lecture_asset["media_sources"]
            if not os.path.exists(lecture_working_dir):
                os.mkdir(lecture_working_dir)
            if not os.path.isfile(lecture_path):
                print(
                    "      > Lecture doesn't have DRM, attempting to download..."
                )
                source = sources[0]  # first index is the best quality
                if isinstance(quality, int):
                    source = min(
                        sources,
                        key=lambda x: abs(int(x.get("height")) - quality))
                try:
                    print("      ====== Selected quality: ",
                          source.get("type"), source.get("height"))
                    url = source.get("download_url")
                    source_type = source.get("type")
                    if source_type == "hls":
                        temp_filepath = lecture_path.replace(".mp4", "")
                        temp_filepath = temp_filepath + ".hls-part.mp4"
                        retVal = FFMPEG(None, url, access_token,
                                        temp_filepath).download()
                        if retVal:
                            os.rename(temp_filepath, lecture_path)
                            print("      > HLS Download success")
                    else:
                        download_aria(url, lecture_dir, lecture_title + ".mp4")
                except Exception as e:
                    print(f"      > Error downloading lecture: ", e)
            else:
                print(
                    "      > Lecture '%s' is already downloaded, skipping..." %
                    lecture_title)
        else:
            print("      > Missing sources for lecture", lecture)


def parse_new(_udemy, quality, skip_lectures, dl_assets, dl_captions,
              caption_locale, keep_vtt, access_token):
    total_chapters = _udemy.get("total_chapters")
    total_lectures = _udemy.get("total_lectures")
    print(f"Chapter(s) ({total_chapters})")
    print(f"Lecture(s) ({total_lectures})")

    course_name = _udemy.get("course_title")
    course_dir = os.path.join(download_dir, course_name)
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)

    for chapter in _udemy.get("chapters"):
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_dir = os.path.join(course_dir, chapter_title)
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)
        print(
            f"======= Processing chapter {chapter_index} of {total_chapters} ======="
        )

        for lecture in chapter.get("lectures"):
            lecture_title = lecture.get("lecture_title")
            lecture_index = lecture.get("lecture_index")

            extension = lecture.get("extension")
            print(
                f"  > Processing lecture {lecture_index} of {total_lectures}")
            if not skip_lectures:
                if extension == "html":
                    html_content = lecture.get("html_content").encode(
                        "ascii", "ignore").decode("utf8")
                    lecture_path = os.path.join(
                        chapter_dir, "{}.html".format(sanitize(lecture_title)))
                    try:
                        download(download_url,
                                 os.path.join(lecture_dir, asset_filename),
                                 asset_filename)
                    except Exception as e:
                        print("    > Failed to write html file: ", e)
                        continue
                else:
                    lecture_path = os.path.join(
                        chapter_dir, "{}.mp4".format(sanitize(lecture_title)))
                    process_lecture(lecture, lecture_path, chapter_dir,
                                    quality, access_token)

            if dl_assets:
                assets = lecture.get("assets")
                print("    > Processing {} asset(s) for lecture...".format(
                    len(assets)))

                for asset in assets:
                    asset_type = asset.get("type")
                    filename = asset.get("filename")
                    download_url = asset.get("download_url")

                    if asset_type == "article":
                        print(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        continue
            elif asset["asset_type"] == "Article":
                assets.append(asset)
                asset_path = os.path.join(lecture_dir,
                                               sanitize(lecture_title))
                with open(asset_path, 'w') as f:
                    f.write(asset["body"])
            elif asset["asset_type"] == "ExternalLink":
                assets.append(asset)
                asset_path = os.path.join(lecture_dir, f"{lecture_index}. External URLs.txt")
                with open(asset_path, 'a') as f:
                    f.write(f"%s : %s\n" %
                            (asset["title"], asset["external_url"]))
        print("> Found %s assets for lecture '%s'" %
              (len(assets), lecture_title))

    # process captions
    if dl_captions:
        captions = []
        for caption in lecture_asset.get("captions"):
            if not isinstance(caption, dict):
                continue
            if caption.get("_class") != "caption":
                continue
            download_url = caption.get("url")
            if not download_url or not isinstance(download_url, str):
                continue
            lang = (caption.get("language") or caption.get("srclang")
                    or caption.get("label")
                    or caption.get("locale_id").split("_")[0])
            ext = "vtt" if "vtt" in download_url.rsplit(".", 1)[-1] else "srt"
            if caption_locale == "all" or caption_locale == lang:
                captions.append({
                    "language": lang,
                    "locale_id": caption.get("locale_id"),
                    "ext": ext,
                    "url": download_url
                })

                        content = u"\n{}\n{}\n".format(name, download_url)
                        if name.lower() not in file_data:
                            with open(filename,
                                      'a',
                                      encoding="utf-8",
                                      errors="ignore") as f:
                                f.write(content)
                                f.close()

            subtitles = lecture.get("subtitles")
            if dl_captions and subtitles:
                print("Processing {} caption(s)...".format(len(subtitles)))
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    if lang == caption_locale or caption_locale == "all":
                        process_caption(subtitle, lecture_title, chapter_dir,
                                        keep_vtt)

def parse(data):
    course_dir = os.path.join(download_dir, course_id)
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)
    chapters = []
    lectures = []

    for obj in data:
        if obj["_class"] == "chapter":
            obj["lectures"] = []
            chapters.append(obj)
        elif obj["_class"] == "lecture" and obj["asset"][
                "asset_type"] == "Video":
            try:
                chapters[-1]["lectures"].append(obj)
            except IndexError:
                # This is caused by there not being a starting chapter
                lectures.append(obj)
                lecture_index = lectures.index(obj) + 1
                lecture_path = os.path.join(course_dir, f'{lecture_index}. {sanitize(obj["title"])}.mp4')
                process_lecture(obj, lecture_index, lecture_path, download_dir)

def course_info(course_data):
    print("\n\n\n\n")
    course_title = course_data.get("title")
    chapter_count = course_data.get("total_chapters")
    lecture_count = course_data.get("total_lectures")

    print("> Course: {}".format(course_title))
    print("> Total Chapters: {}".format(chapter_count))
    print("> Total Lectures: {}".format(lecture_count))
    print("\n")

    chapters = course_data.get("chapters")
    for chapter in chapters:
        chapter_dir = os.path.join(course_dir, f'{chapters.index(chapter) + 1}. {sanitize(chapter["title"])}')
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)

        for lecture in chapter["lectures"]:
            lecture_index = chapter["lectures"].index(lecture) + 1
            lecture_path = os.path.join(chapter_dir, f'{lecture_index}. {sanitize(lecture["title"])}.mp4')
            process_lecture(lecture, lecture_index, lecture_path, chapter_dir)
    print("\n\n\n\n\n\n\n\n=====================")
    print("All downloads completed for course!")
    print("=====================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Udemy Downloader')
    parser.add_argument("-c",
                        "--course-url",
                        dest="course_url",
                        type=str,
                        help="The URL of the course to download",
                        required=True)
    parser.add_argument(
        "-b",
        "--bearer",
        dest="bearer_token",
        type=str,
        help="The Bearer token to use",
    )
    parser.add_argument(
        "-q",
        "--quality",
        dest="quality",
        type=int,
        help=
        "Download specific video quality. If the requested quality isn't available, the closest quality will be used. If not specified, the best quality will be downloaded for each lecture",
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        type=str,
        help=
        "The language to download for captions, specify 'all' to download all captions (Default is 'en')",
    )
    parser.add_argument(
        "--skip-lectures",
        dest="skip_lectures",
        action="store_true",
        help="If specified, lectures won't be downloaded",
    )
    parser.add_argument(
        "--download-assets",
        dest="download_assets",
        action="store_true",
        help="If specified, lecture assets will be downloaded",
    )
    parser.add_argument(
        "--download-captions",
        dest="download_captions",
        action="store_true",
        help="If specified, captions will be downloaded",
    )
    parser.add_argument(
        "--keep-vtt",
        dest="keep_vtt",
        action="store_true",
        help="If specified, .vtt files won't be removed",
    )
    parser.add_argument(
        "--skip-hls",
        dest="skip_hls",
        action="store_true",
        help=
        "If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p quality for non-drm lectures)",
    )
    parser.add_argument(
        "--info",
        dest="info",
        action="store_true",
        help=
        "If specified, only course information will be printed, nothing will be downloaded",
    )

    parser.add_argument(
        "--save-to-file",
        dest="save_to_file",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--load-from-file",
        dest="load_from_file",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    dl_assets = False
    skip_lectures = False
    dl_captions = False
    caption_locale = "en"
    quality = None
    bearer_token = None
    portal_name = None
    course_name = None
    keep_vtt = False
    skip_hls = False

    args = parser.parse_args()
    if args.download_assets:
        dl_assets = True
    if args.lang:
        caption_locale = args.lang
    if args.download_captions:
        dl_captions = True
    if args.skip_lectures:
        skip_lectures = True
    if args.quality:
        quality = args.quality
    if args.keep_vtt:
        keep_vtt = args.keep_vtt
    if args.skip_hls:
        skip_hls = args.skip_hls

    aria_ret_val = check_for_aria()
    if not aria_ret_val:
        print("> Aria2c is missing from your system or path!")
        sys.exit(1)

    ffmpeg_ret_val = check_for_aria()
    if not ffmpeg_ret_val:
        print("> FFMPEG is missing from your system or path!")
        sys.exit(1)

    mp4decrypt_ret_val = check_for_mp4decrypt()
    if not mp4decrypt_ret_val:
        print(
            "> MP4Decrypt is missing from your system or path! (This is part of Bento4 tools)"
        )
        sys.exit(1)

    if args.load_from_file:
        print(
            "> 'load_from_file' was specified, data will be loaded from json files instead of fetched"
        )
    if args.save_to_file:
        print(
            "> 'save_to_file' was specified, data will be saved to json files")

    if not os.path.isfile(keyfile_path):
        print("> Keyfile not found! Did you rename the file correctly?")
        sys.exit(1)

    load_dotenv()
    access_token = None
    if args.bearer_token:
        access_token = args.bearer_token
    else:
        access_token = os.getenv("UDEMY_BEARER")

    udemy = Udemy(access_token)

    print("> Fetching course information, this may take a minute...")
    if not args.load_from_file:
        course_id, course_info = udemy._extract_course_info(args.course_url)
        print("> Course information retrieved!")
        if course_info and isinstance(course_info, dict):
            title = _clean(course_info.get("title"))
            course_title = course_info.get("published_title")
            portal_name = course_info.get("portal_name")

    print("> Fetching course content, this may take a minute...")
    if args.load_from_file:
        course_json = json.loads(
            open(os.path.join(os.getcwd(), "saved", "course_content.json"),
                 'r').read())
        title = course_json.get("title")
        course_title = course_json.get("published_title")
        portal_name = course_json.get("portal_name")
    else:
        course_json = udemy._extract_course_json(args.course_url, course_id,
                                                 portal_name)
    if args.save_to_file:
        with open(os.path.join(os.getcwd(), "saved", "course_content.json"),
                  'w') as f:
            f.write(json.dumps(course_json))
            f.close()

    print("> Course content retrieved!")
    course = course_json.get("results")
    resource = course_json.get("detail")

    if args.load_from_file:
        _udemy = json.loads(
            open(os.path.join(os.getcwd(), "saved", "_udemy.json")).read())
        if args.info:
            course_info(_udemy)
        else:
            parse_new(_udemy, quality, skip_lectures, dl_assets, dl_captions,
                      caption_locale, keep_vtt, access_token)
    else:
        _udemy = {}
        _udemy["access_token"] = access_token
        _udemy["course_id"] = course_id
        _udemy["title"] = title
        _udemy["course_title"] = course_title
        _udemy["chapters"] = []
        counter = -1

        if resource:
            print("> Trying to logout")
            udemy.session.terminate()
            print("> Logged out.")

        if course:
            print("> Processing course data, this may take a minute. ")
            lecture_counter = 0
            for entry in course:
                clazz = entry.get("_class")
                asset = entry.get("asset")
                supp_assets = entry.get("supplementary_assets")

                if clazz == "chapter":
                    lecture_counter = 0
                    lectures = []
                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} ".format(chapter_index) + _clean(
                        entry.get("title"))

                    if chapter_title not in _udemy["chapters"]:
                        _udemy["chapters"].append({
                            "chapter_title": chapter_title,
                            "chapter_id": entry.get("id"),
                            "chapter_index": chapter_index,
                            "lectures": []
                        })
                        counter += 1
                elif clazz == "lecture":
                    lecture_counter += 1
                    lecture_id = entry.get("id")
                    if len(_udemy["chapters"]) == 0:
                        lectures = []
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} ".format(
                            chapter_index) + _clean(entry.get("title"))
                        if chapter_title not in _udemy["chapters"]:
                            _udemy["chapters"].append({
                                "chapter_title": chapter_title,
                                "chapter_id": lecture_id,
                                "chapter_index": chapter_index,
                                "lectures": []
                            })
                            counter += 1

                    if lecture_id:
                        retVal = []

                        if isinstance(asset, dict):
                            asset_type = (asset.get("asset_type").lower()
                                          or asset.get("assetType").lower)
                            if asset_type == "article":
                                if isinstance(supp_assets,
                                              list) and len(supp_assets) > 0:
                                    retVal = udemy._extract_supplementary_assets(
                                        supp_assets)
                            elif asset_type == "video":
                                if isinstance(supp_assets,
                                              list) and len(supp_assets) > 0:
                                    retVal = udemy._extract_supplementary_assets(
                                        supp_assets)
                            elif asset_type == "e-book":
                                retVal = udemy._extract_ebook(asset)
                            elif asset_type == "file":
                                retVal = udemy._extract_file(asset)
                            elif asset_type == "presentation":
                                retVal = udemy._extract_ppt(asset)
                            elif asset_type == "audio":
                                retVal = udemy._extract_audio(asset)

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(
                            lecture_counter) + _clean(entry.get("title"))

                        if asset.get("stream_urls") != None:
                            # not encrypted
                            data = asset.get("stream_urls")
                            if data and isinstance(data, dict):
                                sources = data.get("Video")
                                tracks = asset.get("captions")
                                #duration = asset.get("time_estimation")
                                sources = udemy._extract_sources(
                                    sources, skip_hls)
                                subtitles = udemy._extract_subtitles(tracks)
                                sources_count = len(sources)
                                subtitle_count = len(subtitles)
                                lectures.append({
                                    "index": lecture_counter,
                                    "lecture_index": lecture_index,
                                    "lecture_id": lecture_id,
                                    "lecture_title": lecture_title,
                                    # "duration": duration,
                                    "assets": retVal,
                                    "assets_count": len(retVal),
                                    "sources": sources,
                                    "subtitles": subtitles,
                                    "subtitle_count": subtitle_count,
                                    "sources_count": sources_count,
                                    "is_encrypted": False,
                                    "asset_id": asset.get("id")
                                })
                            else:
                                lectures.append({
                                    "index":
                                    lecture_counter,
                                    "lecture_index":
                                    lecture_index,
                                    "lectures_id":
                                    lecture_id,
                                    "lecture_title":
                                    lecture_title,
                                    "html_content":
                                    asset.get("body"),
                                    "extension":
                                    "html",
                                    "assets":
                                    retVal,
                                    "assets_count":
                                    len(retVal),
                                    "subtitle_count":
                                    0,
                                    "sources_count":
                                    0,
                                    "is_encrypted":
                                    False,
                                    "asset_id":
                                    asset.get("id")
                                })
                        else:
                            # encrypted
                            data = asset.get("media_sources")
                            if data and isinstance(data, list):
                                video_media_sources, audio_media_sources = udemy._extract_media_sources(
                                    data)
                                tracks = asset.get("captions")
                                # duration = asset.get("time_estimation")
                                subtitles = udemy._extract_subtitles(tracks)
                                sources_count = len(video_media_sources)
                                subtitle_count = len(subtitles)
                                lectures.append({
                                    "index": lecture_counter,
                                    "lecture_index": lecture_index,
                                    "lectures_id": lecture_id,
                                    "lecture_title": lecture_title,
                                    # "duration": duration,
                                    "assets": retVal,
                                    "assets_count": len(retVal),
                                    "video_sources": video_media_sources,
                                    "audio_sources": audio_media_sources,
                                    "subtitles": subtitles,
                                    "subtitle_count": subtitle_count,
                                    "sources_count": sources_count,
                                    "is_encrypted": True,
                                    "asset_id": asset.get("id")
                                })
                            else:
                                lectures.append({
                                    "index":
                                    lecture_counter,
                                    "lecture_index":
                                    lecture_index,
                                    "lectures_id":
                                    lecture_id,
                                    "lecture_title":
                                    lecture_title,
                                    "html_content":
                                    asset.get("body"),
                                    "extension":
                                    "html",
                                    "assets":
                                    retVal,
                                    "assets_count":
                                    len(retVal),
                                    "subtitle_count":
                                    0,
                                    "sources_count":
                                    0,
                                    "is_encrypted":
                                    False,
                                    "asset_id":
                                    asset.get("id")
                                })
                    _udemy["chapters"][counter]["lectures"] = lectures
                    _udemy["chapters"][counter]["lecture_count"] = len(
                        lectures)
                elif clazz == "quiz":
                    lecture_id = entry.get("id")
                    if len(_udemy["chapters"]) == 0:
                        lectures = []
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} ".format(
                            chapter_index) + _clean(entry.get("title"))
                        if chapter_title not in _udemy["chapters"]:
                            lecture_counter = 0
                            _udemy["chapters"].append({
                                "chapter_title": chapter_title,
                                "chapter_id": lecture_id,
                                "chapter_index": chapter_index,
                                "lectures": [],
                            })
                            counter += 1

                    _udemy["chapters"][counter]["lectures"] = lectures
                    _udemy["chapters"][counter]["lectures_count"] = len(
                        lectures)

            _udemy["total_chapters"] = len(_udemy["chapters"])
            _udemy["total_lectures"] = sum([
                entry.get("lecture_count", 0) for entry in _udemy["chapters"]
                if entry
            ])

        if args.save_to_file:
            with open(os.path.join(os.getcwd(), "saved", "_udemy.json"),
                      'w') as f:
                f.write(json.dumps(_udemy))
                f.close()
            print("Saved parsed data to json")

        if args.info:
            course_info(_udemy)
        else:
            parse_new(_udemy, quality, skip_lectures, dl_assets, dl_captions,
                      caption_locale, keep_vtt, access_token)
