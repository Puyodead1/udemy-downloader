import os, requests, json, glob, argparse, sys, re
from sanitize_filename import sanitize
from tqdm import tqdm
from dotenv import load_dotenv
from mpegdash.parser import MPEGDASHParser
from utils import extract_kid
from vtt_to_srt import convert
from downloader import FileDownloader

download_dir = os.path.join(os.getcwd(), "out_dir")
working_dir = os.path.join(os.getcwd(), "working_dir")
retry = 3
home_dir = os.getcwd()
keyfile_path = os.path.join(os.getcwd(), "keyfile.json")
valid_qualities = [144, 360, 480, 720, 1080]
downloader = None

if not os.path.exists(working_dir):
    os.makedirs(working_dir)

if not os.path.exists(download_dir):
    os.makedirs(download_dir)

#Get the keys
with open(keyfile_path, 'r') as keyfile:
    keyfile = keyfile.read()
keyfile = json.loads(keyfile)


def extract_course_name(url):
    """
    @author r0oth3x49
    """
    obj = re.search(
        r"(?i)(?://(?P<portal_name>.+?).udemy.com/(?:course(/draft)*/)?(?P<name_or_id>[a-zA-Z0-9_-]+))",
        url,
    )
    if obj:
        return obj.group("portal_name"), obj.group("name_or_id")


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


def mux_process(video_title, lecture_working_dir, outfile):
    """
    @author Jayapraveen
    """
    if os.name == "nt":
        command = "ffmpeg -y -i \"{}\" -i \"{}\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
            os.path.join(lecture_working_dir, "decrypted_audio.mp4"),
            os.path.join(lecture_working_dir, "decrypted_video.mp4"),
            video_title, outfile)
    else:
        command = "nice -n 7 ffmpeg -y -i \"{}\" -i \"{}\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{}\" \"{}\"".format(
            os.path.join(lecture_working_dir, "decrypted_audio.mp4"),
            os.path.join(lecture_working_dir, "decrypted_video.mp4"),
            video_title, outfile)
    os.system(command)


def decrypt(kid, filename, lecture_working_dir):
    """
    @author Jayapraveen
    """
    try:
        key = keyfile[kid.lower()]
    except KeyError:
        exit("Key not found")
    if (os.name == "nt"):
        code = os.system("mp4decrypt --key 1:{0} \"{1}\" \"{2}\"".format(
            key,
            os.path.join(lecture_working_dir,
                         "encrypted_{0}.mp4".format(filename)),
            os.path.join(lecture_working_dir,
                         "decrypted_{0}.mp4".format(filename))))
    else:
        os.system("nice -n 7 mp4decrypt --key 1:{0} \"{1}\" \"{2}\"".format(
            key,
            os.path.join(lecture_working_dir,
                         "encrypted_{0}.mp4".format(filename)),
            os.path.join(lecture_working_dir,
                         "decrypted_{0}.mp4".format(filename))))


def handle_segments(media_info, video_title, lecture_working_dir, output_path):
    """
    @author Jayapraveen
    """
    no_segment, video_url, video_init, video_extension, no_segment, audio_url, audio_init, audio_extension = media_info
    no_segment += 10  # because the download_media function relies on hittin a 404 to know when to finish
    download_media("video_0.seg.mp4", video_init, lecture_working_dir)
    video_kid = extract_kid(
        os.path.join(lecture_working_dir, "video_0.seg.mp4"))
    print("KID for video file is: " + video_kid)
    download_media("audio_0.seg.mp4", audio_init, lecture_working_dir)
    audio_kid = extract_kid(
        os.path.join(lecture_working_dir, "audio_0.seg.mp4"))
    print("KID for audio file is: " + audio_kid)
    for count in range(1, no_segment + 4):
        video_segment_url = video_url.replace("$Number$", str(count))
        audio_segment_url = audio_url.replace("$Number$", str(count))
        video_status = download_media(
            f"video_{str(count)}.seg.{video_extension}", video_segment_url,
            lecture_working_dir)
        audio_status = download_media(
            f"audio_{str(count)}.seg.{audio_extension}", audio_segment_url,
            lecture_working_dir)
        os.chdir(lecture_working_dir)
        if (video_status):
            if os.name == "nt":
                video_concat_command = "copy /b " + "+".join([
                    f"video_{i}.seg.{video_extension}"
                    for i in range(0, count)
                ]) + " encrypted_video.mp4"
                audio_concat_command = "copy /b " + "+".join([
                    f"audio_{i}.seg.{audio_extension}"
                    for i in range(0, count)
                ]) + " encrypted_audio.mp4"
            else:
                video_concat_command = "cat " + " ".join([
                    f"video_{i}.seg.{video_extension}"
                    for i in range(0, count)
                ]) + " > encrypted_video.mp4"
                audio_concat_command = "cat " + " ".join([
                    f"audio_{i}.seg.{audio_extension}"
                    for i in range(0, count)
                ]) + " > encrypted_audio.mp4"
            os.system(video_concat_command)
            os.system(audio_concat_command)
            decrypt(video_kid, "video", lecture_working_dir)
            decrypt(audio_kid, "audio", lecture_working_dir)
            os.chdir(home_dir)
            mux_process(video_title, lecture_working_dir, output_path)
            cleanup(lecture_working_dir)
            break


def handle_segments_threaded(media_info, video_title, lecture_working_dir,
                             output_path):
    """
    @author Jayapraveen
    """
    no_segment, video_url, video_init, video_extension, no_segment, audio_url, audio_init, audio_extension = media_info
    download_media("video_0.seg.mp4", video_init, lecture_working_dir)
    video_kid = extract_kid(
        os.path.join(lecture_working_dir, "video_0.seg.mp4"))
    print("KID for video file is: " + video_kid)
    download_media("audio_0.seg.mp4", audio_init, lecture_working_dir)
    audio_kid = extract_kid(
        os.path.join(lecture_working_dir, "audio_0.seg.mp4"))
    print("KID for audio file is: " + audio_kid)

    vbar = tqdm(total=no_segment,
                initial=1,
                unit='Video Segments',
                desc=video_title + " (Video)")
    abar = tqdm(total=no_segment,
                initial=1,
                unit='Audio Segments',
                desc=video_title + " (Audio)")

    threads = []

    for count in range(1, no_segment):
        video_filename = f"video_{str(count)}.seg.{video_extension}"
        video_path = os.path.join(lecture_working_dir, video_filename)
        video_segment_url = video_url.replace("$Number$", str(count))
        video = downloader.get_file(video_segment_url, video_path,
                                    video_filename, vbar)
        threads.append(video)

    for count in range(1, no_segment):
        audio_filename = f"audio_{str(count)}.seg.{audio_extension}"
        audio_path = os.path.join(lecture_working_dir, audio_filename)
        audio_segment_url = audio_url.replace("$Number$", str(count))
        audio = downloader.get_file(audio_segment_url, audio_path,
                                    audio_filename, abar)
        threads.append(audio)

    for x in threads:
        x.join()

    os.chdir(lecture_working_dir)
    if os.name == "nt":
        video_concat_command = "copy /b " + "+".join(
            [f"video_{i}.seg.{video_extension}"
             for i in range(0, count)]) + " encrypted_video.mp4"
        audio_concat_command = "copy /b " + "+".join(
            [f"audio_{i}.seg.{audio_extension}"
             for i in range(0, count)]) + " encrypted_audio.mp4"
    else:
        video_concat_command = "cat " + " ".join(
            [f"video_{i}.seg.{video_extension}"
             for i in range(0, count)]) + " > encrypted_video.mp4"
        audio_concat_command = "cat " + " ".join(
            [f"audio_{i}.seg.{audio_extension}"
             for i in range(0, count)]) + " > encrypted_audio.mp4"
    os.system(video_concat_command)
    os.system(audio_concat_command)
    decrypt(video_kid, "video", lecture_working_dir)
    decrypt(audio_kid, "audio", lecture_working_dir)
    os.chdir(home_dir)
    mux_process(video_title, lecture_working_dir, output_path)
    cleanup(lecture_working_dir)


def manifest_parser(mpd_url, quality):
    """
    @author Jayapraveen
    """
    video = []
    audio = []
    mpd = MPEGDASHParser.parse(mpd_url)
    for period in mpd.periods:
        for adapt_set in period.adaptation_sets:
            print("Processing " + adapt_set.mime_type)
            content_type = adapt_set.mime_type
            if content_type == "video/mp4":
                if quality:
                    repr = next((x for x in adapt_set.representations
                                 if x.height == quality), None)
                    if not repr:
                        qualities = []
                        for rep in adapt_set.representations:
                            qualities.append(rep.height)
                        if quality < qualities[0]:
                            # they want a lower quality than whats available
                            repr = adapt_set.representations[
                                0]  # Lowest Quality
                        elif quality > qualities[-1]:
                            # they want a higher quality than whats available
                            repr = adapt_set.representations[-1]  # Max Quality
                        print(
                            "> Could not find video with requested quality, falling back to closest!"
                        )
                        print("> Using quality of %s" % repr.height)
                    else:
                        print("> Found MPD representation with quality %s" %
                              repr.height)
                else:
                    repr = adapt_set.representations[-1]  # Max Quality
                    print("> Using max quality of %s" % repr.height)
            segment_count = 0

            segment = repr.segment_templates[0]
            timeline = segment.segment_timelines[0]
            segment_count += len(timeline.Ss)
            for s in timeline.Ss:
                if s.r:
                    segment_count += s.r

            print("Expected No of segments:", segment_count)
            if (content_type == "audio/mp4"):
                segment_extension = segment.media.split(".")[-1]
                audio.append(segment_count)
                audio.append(segment.media)
                audio.append(segment.initialization)
                audio.append(segment_extension)
            elif (content_type == "video/mp4"):
                segment_extension = segment.media.split(".")[-1]
                video.append(segment_count)
                video.append(segment.media)
                video.append(segment.initialization)
                video.append(segment_extension)

    return video + audio


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
                    use_threaded_downloader,
                    threads,
                    tries=0):
    filename = f"%s. %s_%s.%s" % (lecture_index, sanitize(lecture_title),
                                  caption.get("locale_id"), caption.get("ext"))
    filename_no_ext = f"%s. %s_%s" % (lecture_index, sanitize(lecture_title),
                                      caption.get("locale_id"))
    filepath = os.path.join(lecture_dir, filename)

    if os.path.isfile(filepath):
        print("> Captions '%s' already downloaded." % filename)
    else:
        print(f"> Downloading captions: '%s'" % filename)
        try:
            if use_threaded_downloader:
                thread = downloader.get_file(caption.get("url"), filepath,
                                             filename)
                thread.join()
            else:
                download(caption.get("url"), filepath, filename)
        except Exception as e:
            if tries >= 3:
                print(
                    f"> Error downloading captions: {e}. Exceeded retries, skipping."
                )
                return
            else:
                print(
                    f"> Error downloading captions: {e}. Will retry {3-tries} more times."
                )
                process_caption(caption, lecture_index, lecture_title,
                                lecture_dir, use_threaded_downloader, threads,
                                tries + 1)
        if caption.get("ext") == "vtt":
            try:
                print("> Converting captions to SRT format...")
                convert(lecture_dir, filename_no_ext)
                print("> Caption conversion complete.")
                os.remove(filepath)
            except Exception as e:
                print(f"> Error converting captions: {e}")


def process_lecture(lecture, lecture_index, lecture_path, lecture_dir, quality,
                    skip_lectures, dl_assets, dl_captions, caption_locale,
                    use_threaded_downloader):
    lecture_title = lecture["title"]
    lecture_asset = lecture["asset"]
    if not skip_lectures:
        if lecture_asset["media_license_token"] == None:
            # not encrypted
            media_sources = lecture_asset["media_sources"]
            if quality:  # if quality is specified, try to find the requested quality
                lecture_url = next(
                    (x["src"]
                     for x in media_sources if x["label"] == str(quality)),
                    media_sources[0]["src"]
                )  # find the quality requested or return the best available
            else:
                lecture_url = media_sources[0][
                    "src"]  # best quality is the first index

            if not os.path.isfile(lecture_path):
                try:
                    if use_threaded_downloader:
                        thread = downloader.get_file(lecture_url, lecture_path,
                                                     lecture_title)
                        thread.join()
                    else:
                        download(lecture_url, lecture_path, lecture_title)
                except Exception as e:
                    # We could add a retry here
                    print(f"> Error downloading lecture: {e}. Skipping...")
            else:
                print(f"> Lecture '%s' is already downloaded, skipping..." %
                      lecture_title)
        else:
            # encrypted
            print(f"> Lecture '%s' has DRM, attempting to download" %
                  lecture_title)
            lecture_working_dir = os.path.join(
                working_dir, str(lecture_asset["id"])
            )  # set the folder to download ephemeral files
            media_sources = lecture_asset["media_sources"]
            if not os.path.exists(lecture_working_dir):
                os.mkdir(lecture_working_dir)
            if not os.path.isfile(lecture_path):
                mpd_url = next((x["src"] for x in media_sources
                                if x["type"] == "application/dash+xml"), None)
                if not mpd_url:
                    print(
                        "> Couldn't find dash url for lecture '%s', skipping...",
                        lecture_title)
                    return
                media_info = manifest_parser(mpd_url, quality)
                if use_threaded_downloader:
                    handle_segments_threaded(media_info, lecture_title,
                                             lecture_working_dir, lecture_path)
                else:
                    handle_segments(media_info, lecture_title,
                                    lecture_working_dir, lecture_path)
            else:
                print("> Lecture '%s' is already downloaded, skipping..." %
                      lecture_title)

    # process assets
    if dl_assets:
        assets = []
        text_assets = ""
        all_assets = lecture["supplementary_assets"]
        for asset in all_assets:
            if asset["asset_type"] == "File":
                assets.append(asset)
                asset_filename = asset["filename"]
                download_url = next((x["file"]
                                     for x in asset["download_urls"]["File"]
                                     if x["label"] == "download"), None)
                if download_url:
                    try:
                        if use_threaded_downloader:
                            thread = downloader.get_file(
                                download_url,
                                os.path.join(lecture_dir, asset_filename),
                                asset_filename)
                            thread.join()
                        else:
                            download(download_url,
                                     os.path.join(lecture_dir, asset_filename),
                                     asset_filename)
                    except Exception as e:
                        print(
                            f"> Error downloading lecture asset: {e}. Skipping"
                        )
                        continue
            elif asset["asset_type"] == "Article":
                assets.append(asset)
                asset_path = os.path.join(lecture_dir, sanitize(lecture_title))
                with open(asset_path, 'w') as f:
                    f.write(asset["body"])
            elif asset["asset_type"] == "ExternalLink":
                assets.append(asset)
                asset_path = os.path.join(
                    lecture_dir, "{}. External URLs.txt".format(lecture_index))
                # with open(asset_path, 'a') as f:
                #     f.write(f"%s : %s\n" %
                #             (asset["title"], asset["external_url"]))
                text_assets += "{}: {}\n".format(asset["title"],
                                                 asset["external_url"])

        if not text_assets == "":
            with open(asset_path, 'w') as f:
                f.write(text_assets)

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

        for caption in captions:
            process_caption(caption, lecture_index, lecture_title, lecture_dir,
                            use_threaded_downloader)


def parse(data, course_id, course_name, skip_lectures, dl_assets, dl_captions,
          quality, caption_locale, use_threaded_downloader):
    course_dir = os.path.join(download_dir, course_name)
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
                lecture_path = os.path.join(
                    course_dir, "{}. {}.mp4".format(lecture_index,
                                                    sanitize(obj["title"])))
                process_lecture(
                    obj,
                    lecture_index,
                    lecture_path,
                    download_dir,
                    quality,
                    skip_lectures,
                    dl_assets,
                    dl_captions,
                    caption_locale,
                    use_threaded_downloader,
                )

    for chapter in chapters:
        chapter_dir = os.path.join(
            course_dir, "{}. {}".format(
                chapters.index(chapter) + 1, sanitize(chapter["title"])))
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)

        for lecture in chapter["lectures"]:
            lecture_index = chapter["lectures"].index(lecture) + 1
            lecture_path = os.path.join(
                chapter_dir, "{}. {}.mp4".format(lecture_index,
                                                 sanitize(lecture["title"])))
            process_lecture(lecture, lecture_index, lecture_path, chapter_dir,
                            quality, skip_lectures, dl_assets, dl_captions,
                            caption_locale, use_threaded_downloader)
    print("\n\n\n\n\n\n\n\n=====================")
    print("All downloads completed for course!")
    print("=====================")


def fetch_subscribed_courses_json(bearer_token, portal_name):
    res = requests.get(
        "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&ordering=-last_accessed,-access_time&page=1&page_size=10000"
        .format(portal_name=portal_name),
        headers={
            "Authorization":
            bearer_token,
            "x-udemy-authorization":
            bearer_token,
            "Host":
            "{portal_name}.udemy.com".format(portal_name=portal_name),
            "Referer":
            "https://{portal_name}.udemy.com/home/my-courses/search/?q={course_name}"
            .format(portal_name=portal_name, course_name=course_name)
        })
    res.raise_for_status()
    data = res.json()
    return data


def fetch_course_json(course_id, bearer_token, portal_name, course_name):
    res = requests.get(
        "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items?fields[asset]=results,title,external_url,time_estimation,download_urls,slide_urls,filename,asset_type,captions,media_license_token,course_is_drmed,media_sources,stream_urls,body&fields[chapter]=object_index,title,sort_order&fields[lecture]=id,title,object_index,asset,supplementary_assets,view_html&page_size=10000"
        .format(portal_name=portal_name, course_id=course_id),
        headers={
            "Authorization": bearer_token,
            "x-udemy-authorization": bearer_token,
            "Host": "{portal_name}.udemy.com".format(portal_name=portal_name),
            "Referer": "https://{portal_name}.udemy.com/"
        })
    res.raise_for_status()
    return res.json()


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
        help="Download specific video quality. (144, 360, 480, 720, 1080)",
    )
    parser.add_argument(
        "-t",
        "--threads",
        dest="threads",
        type=int,
        help=
        "Max number of threads to use when using the threaded downloader (default 10)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        type=str,
        help="The language to download for captions (Default is en)",
    )
    parser.add_argument(
        "--skip-lectures",
        dest="skip_lectures",
        action="store_true",
        help="If specified, lectures won't be downloaded.",
    )
    parser.add_argument(
        "--download-assets",
        dest="download_assets",
        action="store_true",
        help="If specified, lecture assets will be downloaded.",
    )
    parser.add_argument(
        "--download-captions",
        dest="download_captions",
        action="store_true",
        help="If specified, captions will be downloaded.",
    )
    parser.add_argument(
        "--use-threaded-downloader",
        dest="use_threaded_downloader",
        action="store_true",
        help="If specified, the experimental threaded downloader will be used",
    )
    parser.add_argument(
        "-d",
        "--debug",
        dest="debug",
        action="store_true",
        help="Use test_data.json rather than fetch from the udemy api.",
    )

    dl_assets = False
    skip_lectures = False
    dl_captions = False
    caption_locale = "en"
    quality = None
    bearer_token = None
    portal_name = None
    course_name = None
    use_threaded_downloader = False
    threads = 10

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
        if not args.quality in valid_qualities:
            print("Invalid quality specified! %s" % quality)
            sys.exit(1)
        else:
            quality = args.quality
    if args.use_threaded_downloader:
        use_threaded_downloader = args.use_threaded_downloader
    if args.threads:
        threads = args.threads
    downloader = FileDownloader(max_threads=threads)

    load_dotenv()
    if args.bearer_token:
        bearer_token = f"Bearer %s" % args.bearer_token
    else:
        bearer_token = f"Bearer %s" % os.getenv("UDEMY_BEARER")

    if args.course_url:
        portal_name, course_name = extract_course_name(args.course_url)

    if not course_name:
        print("> Unable to extract course name from URL!")
        sys.exit(1)
    if not portal_name:
        print("> Unable to extract portal name from URL!")
        sys.exit(1)
    if not bearer_token:
        print("> Missing Bearer Token!")
        sys.exit(1)

    print(f"> Fetching subscribed course data...")
    try:
        subscribed_courses = fetch_subscribed_courses_json(
            bearer_token, portal_name)
    except Exception as e:
        print("> Failed to fetch subscribed course information: %s" % e)

    course = next((x for x in subscribed_courses["results"]
                   if x["published_title"] == course_name), None)
    if not course:
        print("> Failed to find course in course list!")
        sys.exit(1)

    course_id = course["id"]
    course_title = course["title"]

    print(
        f"> Fetching information for course '%s', this might take a minute..."
        % course_name)
    try:
        course_data = fetch_course_json(course_id, bearer_token, portal_name,
                                        course_name)
    except Exception as e:
        print("> Failed to fetch course information: %s" % e)
        sys.exit(1)

    if not course_data:
        print("> Failed to fetch course data!")

    print("> Course information retrieved!")

    if args.debug:
        # this is for development purposes so we dont need to make tons of requests when testing
        # course data json is just stored and read from a file
        with open("test_data.json", encoding="utf8") as f:
            course_data = json.loads(f.read())
            parse(course_data["results"], course_id, course_name,
                  skip_lectures, dl_assets, dl_captions, quality,
                  caption_locale, use_threaded_downloader)
    else:
        parse(course_data["results"], course_id, course_name, skip_lectures,
              dl_assets, dl_captions, quality, caption_locale,
              use_threaded_downloader)
