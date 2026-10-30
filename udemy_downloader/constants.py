LOGGER_NAME = "udemy-downloader"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US",
    "Referer": "https://www.udemy.com",
    "X-Requested-With": "XMLHttpRequest",
    "DNT": "1",
    "Connection": "keep-alive",
}
CURRICULUM_ITEMS_URL = (
    "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/subscriber-curriculum-items/?caching_intent=False"
)
COURSE_URL = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/"
COURSE_SEARCH = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&page=1&page_size=500&search={course_name}"
MY_COURSES_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses?fields[course]=id,url,title,published_title&ordering=-last_accessed,-access_time&page=1&page_size=10000"
COLLECTION_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses-collections/?collection_has_courses=True&course_limit=20&fields[course]=last_accessed_time,title,published_title&fields[user_has_subscribed_courses_collection]=@all&page=1&page_size=1000"
QUIZ_URL = "https://{portal_name}.udemy.com/api-2.0/quizzes/{quiz_id}/assessments/?version=1&page_size=250&fields[assessment]=id,assessment_type,prompt,correct_response,section,question_plain,related_lectures"
LECTURE_URL = "https://{portal_name}.udemy.com/api-2.0/users/me/subscribed-courses/{course_id}/lectures/{lecture_id}/?fields[lecture]=asset,description,download_url,is_free,last_watched_second&fields[asset]=asset_type,length,media_license_token,course_is_drmed,media_sources,captions,thumbnail_sprite,slides,slide_urls,download_urls,external_url&q={rand}"
LICENSE_URL = (
    "https://{portal_name}.udemy.com/media-license-server/validate-auth-token?drm_type=widevine&auth_token={auth_token}"
)

CURRICULUM_ITEMS_PARAMS = {
    "fields[lecture]": "title,object_index,created,asset,supplementary_assets,description,download_url",
    "fields[quiz]": "title,object_index,type",
    "fields[practice]": "title,object_index",
    "fields[chapter]": "title,object_index",
    "fields[asset]": "title,filename,asset_type,status,is_external,course_is_drmed,media_sources,captions,slides,slide_urls,download_urls,external_url,stream_urls,@min,status,delayed_asset_message,processing_errors,body",
    "caching_intent": True,
    "page_size": "200",
}
