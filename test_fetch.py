import requests
import json
import os
from sanitize_filename import sanitize
import urllib.request
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()


course_id = "657932" # the course id to download
bearer_token = os.getenv("UDEMY_BEARER") # you can find this in the network tab, its a request header under Authorization/x-udemy-authorization
header_bearer = "Bearer " + bearer_token
#r = requests.get(f"https://udemy.com/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items?fields[asset]=results,title,external_url,time_estimation,download_urls,slide_urls,filename,asset_type,captions,media_license_token,course_is_drmed,media_sources,stream_urls,body&fields[chapter]=object_index,title,sort_order&fields[lecture]=id,title,object_index,asset,supplementary_assets,view_html&page_size=10000".format(course_id), headers={"Authorization": header_bearer, "x-udemy-authorization": header_bearer})
# if r.status_code == 200:
#     # loop
#     data = r.json()
#     for result in data:
#         print(result)
# else:
#     print("An error occurred while trying to fetch coure data!")
#     print(r.text)

download_dir = os.getcwd() + "\\out_dir"

def download(url, path, filename):
    """
    @param: url to download file
    @param: path place to put the file
    @oaram: filename used for progress bar
    """
    file_size = int(requests.head(url).headers["Content-Length"])
    if os.path.exists(path):
        print("file exists")
        first_byte = os.path.getsize(path)
    else:
        first_byte = 0
    if first_byte >= file_size:
        return file_size
    header = {"Range": "bytes=%s-%s" % (first_byte, file_size)}
    pbar = tqdm(
        total=file_size, initial=first_byte,
        unit='MB', unit_scale=True, desc=filename)
    req = requests.get(url, headers=header, stream=True)
    with(open(path, 'ab')) as f:
        for chunk in req.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                pbar.update(1024)
    pbar.close()
    return file_size

with open("test_data.json", encoding="utf8") as f:
    data = json.loads(f.read())["results"]

    chapters = []

    for obj in data:
        if obj["_class"] == "chapter":
            obj["lectures"] = []
            chapters.append(obj)
        elif obj["_class"] == "lecture" and obj["asset"]["asset_type"] == "Video":
            chapters[-1]["lectures"].append(obj)
    
    for chapter in chapters:
        chapter_dir = f"%s\\%s. %s" % (download_dir,chapters.index(chapter) + 1,chapter["title"])
        if not os.path.isdir(chapter_dir):
            os.mkdir(chapter_dir)

        for lecture in chapter["lectures"]:
            lecture_title = lecture["title"]
            lecture_path = f"%s\\%s. %s.mp4" % (chapter_dir, chapter["lectures"].index(lecture) + 1,sanitize(lecture_title))
            lecture_asset = lecture["asset"]
            if lecture_asset["media_license_token"] == None:
                # not encrypted
                lecture_url = lecture_asset["media_sources"][0]["src"] # best quality is the first index
                download(lecture_url, lecture_path, lecture_title)
            else:
                # encrypted
                print("drm")
                pass