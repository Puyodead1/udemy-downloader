import logging
import os
import time

HEADERS = {
    "Origin": "www.udemy.com",
    # "User-Agent":
    # "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Accept": "*/*",
    "Accept-Encoding": None,
}
LOGIN_URL = "https://www.udemy.com/join/login-popup/?ref=&display_type=popup&loc"
LOGOUT_URL = "https://www.udemy.com/user/logout"
# COURSE_URL = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items?fields[asset]=results,title,external_url,time_estimation,download_urls,slide_urls,filename,asset_type,captions,media_license_token,course_is_drmed,media_sources,stream_urls,body&fields[chapter]=object_index,title,sort_order&fields[lecture]=id,title,object_index,asset,supplementary_assets,view_html&page_size=10000"
CURRICULUM_ITEMS_URL = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/subscriber-curriculum-items/"
COURSE_URL = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/"
COURSE_SEARCH = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&page=1&page_size=500&search={course_name}"
SUBSCRIBED_COURSES = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses/?ordering=-last_accessed&fields[course]=id,title,url&page=1&page_size=12"
MY_COURSES_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&ordering=-last_accessed,-access_time&page=1&page_size=10000"
COLLECTION_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses-collections/?collection_has_courses=True&course_limit=20&fields[course]=last_accessed_time,title,published_title&fields[user_has_subscribed_courses_collection]=@all&page=1&page_size=1000"
QUIZ_URL = "https://{portal_name}.udemy.com/api-2.0/quizzes/{quiz_id}/assessments/?version=1&page_size=250&fields[assessment]=id,assessment_type,prompt,correct_response,section,question_plain,related_lectures"

CURRICULUM_ITEMS_PARAMS = {
    "fields[lecture]": "title,object_index,created,asset,supplementary_assets,description,download_url",
    "fields[quiz]": "title,object_index,type",
    "fields[practice]": "title,object_index",
    "fields[chapter]": "title,object_index",
    "fields[asset]": "title,filename,asset_type,status,is_external,media_license_token,course_is_drmed,media_sources,captions,slides,slide_urls,download_urls,external_url,stream_urls,@min,status,delayed_asset_message,processing_errors,body",
    "caching_intent": True,
    "page_size": "200",
}

COURSE_URL_PARAMS = {"fields[course]": "title", "use_remote_version": True, "caching_intent": True}

HOME_DIR = os.getcwd()
SAVED_DIR = os.path.join(os.getcwd(), "saved")
KEY_FILE_PATH = os.path.join(os.getcwd(), "keyfile.json")
COOKIE_FILE_PATH = os.path.join(os.getcwd(), "cookies.txt")
LOG_DIR_PATH = os.path.join(os.getcwd(), "logs")
LOG_FILE_PATH = os.path.join(os.getcwd(), "logs", f"{time.strftime('%Y-%m-%d-%I-%M-%S')}.log")
LOG_FORMAT = "[%(asctime)s] [%(name)s] [%(funcName)s:%(lineno)d] %(levelname)s: %(message)s"
LOG_DATE_FORMAT = "%I:%M:%S"
LOG_LEVEL = logging.INFO
