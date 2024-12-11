import argparse
import json
import sys
from pathlib import Path

from udemy_downloader.Udemy import Udemy


def main():
    parser = argparse.ArgumentParser(description="Udemy Downloader")
    parser.add_argument("course_url", type=str, help="The URL of the course to download")
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
        help="Download specific video quality. If the requested quality isn't available, the closest quality will be used. If not specified, the best quality will be downloaded for each lecture",
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        type=str,
        help="The language to download for captions, specify 'all' to download all captions (Default is 'en')",
    )
    parser.add_argument(
        "-cd",
        "--concurrent-downloads",
        dest="concurrent_downloads",
        type=int,
        help="The number of maximum concurrent downloads for segments (HLS and DASH, must be a number 1-30)",
        default=1,
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
        "--download-quizzes",
        dest="download_quizzes",
        action="store_true",
        help="If specified, quizzes will be downloaded",
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
        help="If specified, hls streams will be skipped (faster fetching) (hls streams usually contain 1080p quality for non-drm lectures)",
    )
    parser.add_argument(
        "--info",
        dest="info",
        action="store_true",
        help="If specified, only course information will be printed, nothing will be downloaded",
    )
    parser.add_argument(
        "--id-as-course-name",
        dest="id_as_course_name",
        action="store_true",
        help="If specified, the course id will be used in place of the course name for the output directory. This is a 'hack' to reduce the path length",
    )
    parser.add_argument(
        "-sc",
        "--subscription-course",
        dest="is_subscription_course",
        action="store_true",
        help="Mark the course as a subscription based course, use this if you are having problems with the program auto detecting it",
    )
    parser.add_argument(
        "--save-to-file",
        dest="save_to_file",
        action="store_true",
        help="If specified, course content will be saved to a file that can be loaded later with --load-from-file, this can reduce processing time (Note that asset links expire after a certain amount of time)",
    )
    parser.add_argument(
        "--load-from-file",
        dest="load_from_file",
        action="store_true",
        help="If specified, course content will be loaded from a previously saved file with --save-to-file, this can reduce processing time (Note that asset links expire after a certain amount of time)",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        type=str,
        help="Logging level: one of DEBUG, INFO, ERROR, WARNING, CRITICAL (Default is INFO)",
        default="INFO",
    )
    parser.add_argument(
        "--browser",
        dest="browser",
        help="The browser to extract cookies from",
        choices=["chrome", "firefox", "opera", "edge", "brave", "chromium", "vivaldi", "safari", "file"],
    )
    parser.add_argument(
        "--use-h265",
        dest="use_h265",
        action="store_true",
        help="If specified, videos will be encoded with the H.265 codec",
    )
    parser.add_argument(
        "--h265-crf",
        dest="h265_crf",
        type=int,
        default=28,
        help="Set a custom CRF value for H.265 encoding. FFMPEG default is 28",
    )
    parser.add_argument(
        "--h265-preset",
        dest="h265_preset",
        type=str,
        default="medium",
        help="Set a custom preset value for H.265 encoding. FFMPEG default is medium",
    )
    parser.add_argument(
        "--use-nvenc",
        dest="use_nvenc",
        action="store_true",
        help="Whether to use the NVIDIA hardware transcoding for H.265. Only works if you have a supported NVIDIA GPU and ffmpeg with nvenc support",
    )
    parser.add_argument(
        "--out",
        "-o",
        dest="out",
        type=str,
        help="Set the path to the output directory",
    )
    parser.add_argument(
        "--continue-lecture-numbers",
        "-n",
        dest="use_continuous_lecture_numbers",
        action="store_true",
        help="Use continuous lecture numbering instead of per-chapter",
    )
    parser.add_argument(
        "--chapter",
        dest="chapter_filter_raw",
        type=str,
        help="Download specific chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').",
    )
    # parser.add_argument("-v", "--version", action="version", version="You are running version {version}".format(version=__version__))

    args = parser.parse_args()

    # rename log_level to log_level_str
    args.log_level_str = args.log_level
    del args.log_level

    udemy = Udemy(**vars(args))

    udemy.init_logger()

    udemy.pre_check()

    if udemy.out:
        out_path = Path(udemy.out)
        if out_path.is_file():
            udemy.logger.error(f"The output path is a file")
            sys.exit(1)
        udemy.download_dir = out_path

    udemy.logger.info(f"Output directory set to {udemy.download_dir}")

    udemy.download_dir.mkdir(parents=True, exist_ok=True)

    # Get the keys
    if udemy.key_file_path.exists():
        with udemy.key_file_path.open("r") as keyfile:
            udemy.keys = json.loads(keyfile.read())
    else:
        udemy.logger.warning("> Keyfile not found! You won't be able to decrypt any encrypted videos!")

    udemy.update_auth()

    udemy.get_course_info()
    udemy.get_course_content()

    if udemy.save_to_file:
        udemy.logger.info("> 'save_to_file' was specified, caching data")
        udemy.save_content_file()

    if udemy.load_from_file:
        udemy.logger.info("> 'load_from_file' was specified, loading data from cache")
        udemy.load_parsed_file()
        if udemy.info:
            udemy.print_course_info()
        else:
            udemy.process_parsed_content()
    else:
        udemy.parse_course_data()


if __name__ == "__main__":
    main()
