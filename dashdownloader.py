#dashdownloader
import os,requests,shutil,json,glob
from mpegdash.parser import MPEGDASHParser
from mpegdash.nodes import Descriptor
from mpegdash.utils import (
    parse_attr_value, parse_child_nodes, parse_node_value,
    write_attr_value, write_child_node, write_node_value
)

#global ids
retry = 3
download_dir = os.getcwd() # set the folder to output
working_dir = os.getcwd() # set the folder to download ephemeral files
keyfile_path = working_dir + "/keyfile.json"

#Patching the Mpegdash lib for keyID
def __init__(self):
    self.scheme_id_uri = ''                               # xs:anyURI (required)
    self.value = None                                     # xs:string
    self.id = None                                        # xs:string
    self.key_id = None                                    # xs:string

def parse(self, xmlnode):
    self.scheme_id_uri = parse_attr_value(xmlnode, 'schemeIdUri', str)
    self.value = parse_attr_value(xmlnode, 'value', str)
    self.id = parse_attr_value(xmlnode, 'id', str)
    self.key_id = parse_attr_value(xmlnode, 'ns2:default_KID', str)
    if(self.key_id == None):
        self.key_id = parse_attr_value(xmlnode, 'cenc:default_KID', str)

def write(self, xmlnode):
    write_attr_value(xmlnode, 'schemeIdUri', self.scheme_id_uri)
    write_attr_value(xmlnode, 'value', self.value)
    write_attr_value(xmlnode, 'id', self.id)
    write_attr_value(xmlnode, 'ns2:default_KID', self.key_id)
    if(self.key_id == None):
        write_attr_value(xmlnode, 'cenc:default_KID', self.key_id)

Descriptor.__init__ = __init__
Descriptor.parse = parse
Descriptor.write = write

#Get the keys
with open(keyfile_path,'r') as keyfile:
    keyfile = keyfile.read()
keyfile = json.loads(keyfile)

def manifest_parser(mpd_url):
    manifest = requests.get(mpd_url).text
    with open("manifest.mpd",'w') as manifest_handler:
        manifest_handler.write(manifest)
    mpd = MPEGDASHParser.parse("./manifest.mpd")
    audio = []
    video = []
    for period in mpd.periods:
        for adapt_set in period.adaptation_sets:
            #print(adapt_set.content_type)
            content_type = adapt_set.content_type
            for repr in adapt_set.representations:
                base_url = repr.base_urls[0].base_url_value
                if(content_type == "audio"):
                    audio.append(base_url)
                elif(content_type == "video"):
                    video.append(base_url)
            for prot in adapt_set.content_protections:
                if(prot.value == "cenc"):
                    kId = prot.key_id.replace('-','')
                    if(content_type == "audio"):
                        audio.append(kId)
                    elif(content_type == "video"):
                        video.append(kId)
                    break
    return video + audio

def download(url,filename,count = 0):
    video = requests.get(url, stream=True)
    if video.status_code is 200:
        video_length = int(video.headers.get('content-length'))
        if(os.path.isfile(filename) and os.path.getsize(filename) >= video_length):
            print("Video already downloaded.. skipping write to disk..")
        else:
            try:
                with open(filename, 'wb') as video_file:
                    shutil.copyfileobj(video.raw, video_file)
            except:
                print(url,filename)
                print("Write to disk error: Reattempting download and write..")
                if(count <= retry):
                    count += 1
                    download(url,filename,count)
                else:
                    exit("Error Writing Video to Disk. Exiting...")

        if os.path.getsize(filename) >= video_length:
            pass
        else:
            print("Error downloaded video is faulty.. Retrying to download")
            if(count <= retry):
                count += 1
                download(url,filename,count)
            else:
                exit("Error Writing Video to Disk. Exiting...")
    else:
        print("Video file is not accessible",filename,"Retrying...")
        if(count <= retry):
            count += 1
            download(url,filename,count)
        else:
            print("Adding Video file not accessible to log")
            with open(download_dir + "\video_access_error.txt",'a') as videoaccerr:
                videoaccerr.write(filename + " " + url +"\n")

def decrypt(filename,keyid,video_title):
    try:
        key = keyfile[keyid]
        print(key)
        os.system(f"ffmpeg -y -decryption_key {key} -i {filename} -codec copy -metadata title={video_title} dec_{filename}")
    except KeyError as error:
        print("Key not found")
        exit()

def mux_process(outfile):
    command = f"ffmpeg -y -i dec_audio.mp4 -i dec_video.mp4 -acodec copy -vcodec copy -metadata title=\"{video_title}\" {outfile}.mp4"
    print(command)
    os.system(command)

def cleanup(path):
    leftover_files = glob.glob(path + '/*.mp4', recursive=True)
    mpd_files = glob.glob(path + '/*.mpd', recursive=True)
    leftover_files = leftover_files + mpd_files
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            print(f"Error deleting file: {file_list}")


if __name__ == "__main__":
    mpd = "https://demo.com/stream.mpd"
    base_url = mpd.split("stream.mpd")[0]
    os.chdir(working_dir)
    video_url,video_keyid,audio_url,audio_keyid = manifest_parser(mpd)
    video_url = base_url + video_url
    audio_url = base_url + audio_url
    audio_filename = "audio.mp4"
    video_filename = "video.mp4"
    video_title = "Video Title"
    audio_title = video_title
    download(video_url,video_filename)
    download(audio_url,audio_filename)
    decrypt(video_filename,video_keyid,video_title)
    decrypt(audio_filename,audio_keyid,audio_title)
    final_file = download_dir + '/' + video_title
    print(final_file)
    mux_process(final_file)
    cleanup(working_dir)
