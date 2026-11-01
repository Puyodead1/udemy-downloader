import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from udemy_downloader.constants import NVENC_PRESETS, X265_PRESETS
from udemy_downloader.Udemy import Udemy
from udemy_downloader.utils import parse_chapter_filter


def int_in_range(minimum: int, maximum: int):
    def parse(value: str):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"'{value}' is not a whole number")
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}, got {number}")
        return number

    return parse


def course_url(value: str):
    if not re.search(r"(?i)//[^/]+\.udemy\.com/", value):
        raise argparse.ArgumentTypeError(
            f"'{value}' doesn't look like a Udemy course URL (e.g. https://www.udemy.com/course/<name>/)"
        )
    return value


def chapter_filter(value: str):
    try:
        parse_chapter_filter(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error))
    return value


def main():
    # allow UDEMY_BEARER to be set in a .env file
    load_dotenv()

    parser = argparse.ArgumentParser(description="Udemy Downloader")
    parser.add_argument("course_url", type=course_url, help="The URL of the course to download")
    parser.add_argument(
        "-b",
        "--bearer",
        dest="bearer_token",
        type=str,
        default=os.getenv("UDEMY_BEARER"),
        help="The Bearer token to use (Default is the UDEMY_BEARER environment variable)",
    )
    parser.add_argument(
        "-q",
        "--quality",
        dest="quality",
        type=int_in_range(1, 4320),
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
        type=int_in_range(1, 30),
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
        help="If specified, quizzes, practice assignments and role plays will be downloaded",
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
        "-y",
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Answer yes to confirmation prompts (e.g. --info on courses with many lectures)",
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
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
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
        type=int_in_range(0, 51),
        default=28,
        help="Set a custom quality value for H.265 encoding, lower is better quality (CRF for libx265, CQ for NVENC). Default is 28",
    )
    parser.add_argument(
        "--h265-preset",
        dest="h265_preset",
        type=str.lower,
        default="medium",
        help=f"Set the preset for H.265 encoding, one of {', '.join(X265_PRESETS)}. With --use-nvenc these map to the closest NVENC preset, and p1-p7 can also be used. Default is medium",
    )
    parser.add_argument(
        "--use-nvenc",
        dest="use_nvenc",
        action="store_true",
        help="Encode H.265 with NVIDIA hardware encoding (implies --use-h265). Only works if you have a supported NVIDIA GPU and ffmpeg with nvenc support",
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
        type=chapter_filter,
        help="Download specific chapters. Use comma separated values and ranges (e.g., '1,3-5,7,9-11').",
    )
    parser.add_argument("--device", "-d", dest="device", type=str, help="Name of WVD file to use")

    args = parser.parse_args()

    # the encoders accept different preset names
    valid_presets = NVENC_PRESETS if args.use_nvenc else X265_PRESETS
    if args.h265_preset not in valid_presets:
        if args.h265_preset in NVENC_PRESETS:
            reason = "is an NVENC preset, use it with --use-nvenc"
        else:
            reason = "isn't a valid preset" + (" for NVENC" if args.use_nvenc else "")
        parser.error(
            f"argument --h265-preset: '{args.h265_preset}' {reason} (choose from {', '.join(valid_presets)})"
        )

    # rename log_level to log_level_str
    args.log_level_str = args.log_level
    del args.log_level

    udemy = Udemy(**vars(args))

    udemy.pre_check()

    if udemy.out:
        out_path = Path(udemy.out)
        if out_path.is_file():
            udemy.logger.error("The output path is a file")
            sys.exit(1)
        udemy.download_dir = out_path

    udemy.logger.info(f"Output directory set to {udemy.download_dir}")

    udemy.download_dir.mkdir(parents=True, exist_ok=True)

    # Get the keys
    udemy.load_keys()

    udemy.visit()
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
