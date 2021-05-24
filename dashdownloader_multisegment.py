#dashdrmmultisegmentdownloader
import os,requests,shutil,json,glob
from mpegdash.parser import MPEGDASHParser
from mpegdash.nodes import Descriptor
from mpegdash.utils import (
    parse_attr_value, parse_child_nodes, parse_node_value,
    write_attr_value, write_child_node, write_node_value
)
from utils import extract_kid

#global ids
retry = 3
download_dir = os.path.join(os.getcwd(), 'out_dir') # set the folder to output
working_dir = os.path.join(os.getcwd(), "working_dir") # set the folder to download ephemeral files
keyfile_path = os.path.join(os.getcwd(), "keyfile.json")

if not os.path.exists(working_dir):
    os.makedirs(working_dir)

#Get the keys
with open(keyfile_path,'r') as keyfile:
    keyfile = keyfile.read()
keyfile = json.loads(keyfile)


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
    self.key_id = parse_attr_value(xmlnode, 'cenc:default_KID', str)

def write(self, xmlnode):
    write_attr_value(xmlnode, 'schemeIdUri', self.scheme_id_uri)
    write_attr_value(xmlnode, 'value', self.value)
    write_attr_value(xmlnode, 'id', self.id)
    write_attr_value(xmlnode, 'cenc:default_KID', self.key_id)

Descriptor.__init__ = __init__
Descriptor.parse = parse
Descriptor.write = write

def durationtoseconds(period):
    #Duration format in PTxDxHxMxS
    if(period[:2] == "PT"):
        period = period[2:]   
        day = int(period.split("D")[0] if 'D' in period else 0)
        hour = int(period.split("H")[0].split("D")[-1]  if 'H' in period else 0)
        minute = int(period.split("M")[0].split("H")[-1] if 'M' in period else 0)
        second = period.split("S")[0].split("M")[-1]
        print("Total time: " + str(day) + " days " + str(hour) + " hours " + str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) + (int(second.split('.')[0]))) + '.' + str(int(second.split('.')[-1])))
        return total_time

    else:
        print("Duration Format Error")
        return None

def download_media(filename,url,epoch = 0):
    if(os.path.isfile(filename)):
        print("Segment already downloaded.. skipping..")
    else:
        media = requests.get(url, stream=True)
        media_length = int(media.headers.get("content-length"))
        if media.status_code == 200:
            if(os.path.isfile(filename) and os.path.getsize(filename) >= media_length):
                print("Segment already downloaded.. skipping write to disk..")
            else:
                try:
                    with open(filename, 'wb') as video_file:
                        shutil.copyfileobj(media.raw, video_file)
                        print("Segment downloaded: " + filename)
                        return False #Successfully downloaded the file
                except:
                    print("Connection error: Reattempting download of segment..")
                    download_media(filename,url, epoch + 1)

            if os.path.getsize(filename) >= media_length:
                pass
            else:
                print("Segment is faulty.. Redownloading...")
                download_media(filename,url, epoch + 1)
        elif(media.status_code == 404):
            print("Probably end hit!\n",url)
            return True #Probably hit the last of the file
        else:
            if (epoch > retry):
                exit("Error fetching segment, exceeded retry times.")
            print("Error fetching segment file.. Redownloading...")
            download_media(filename,url, epoch + 1)

def cleanup(path):
    leftover_files = glob.glob(path + '/*.mp4', recursive=True)
    mpd_files = glob.glob(path + '/*.mpd', recursive=True)
    leftover_files = leftover_files + mpd_files
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            print(f"Error deleting file: {file_list}")

def mux_process(video_title,outfile):
    if os.name == "nt":
        command = f"ffmpeg -y -i decrypted_audio.mp4 -i decrypted_video.mp4 -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{video_title}\" -metadata creation_time=2020-00-00T70:05:30.000000Z \"{outfile}.mp4\""
    else:
        command = f"nice -n 7 ffmpeg -y -i decrypted_audio.mp4 -i decrypted_video.mp4 -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{video_title}\" -metadata creation_time=2020-00-00T70:05:30.000000Z {outfile}.mp4"
    os.system(command)

def decrypt(kid,filename):
    try:
        key = keyfile[kid.lower()]
    except KeyError as error:
        exit("Key not found")
    if(os.name == "nt"):
        os.system(f"mp4decrypt --key 1:{key} encrypted_{filename}.mp4 decrypted_{filename}.mp4")
    else:
        os.system(f"nice -n 7 mp4decrypt --key 1:{key} encrypted_{filename}.mp4 decrypted_{filename}.mp4")


def handle_irregular_segments(media_info,video_title,output_path):
    no_segment,video_url,video_init,video_extension,no_segment,audio_url,audio_init,audio_extension = media_info
    download_media("video_0.seg.mp4",video_init)
    video_kid = extract_kid("video_0.seg.mp4")
    print("KID for video file is: " + video_kid)
    download_media("audio_0.seg.mp4",audio_init)
    audio_kid = extract_kid("audio_0.seg.mp4")
    print("KID for audio file is: " + audio_kid)
    for count in range(1,no_segment):
        video_segment_url = video_url.replace("$Number$",str(count))
        audio_segment_url = audio_url.replace("$Number$",str(count))
        video_status = download_media(f"video_{str(count)}.seg.{video_extension}",video_segment_url)   
        audio_status = download_media(f"audio_{str(count)}.seg.{audio_extension}",audio_segment_url)
        if(video_status):
            if os.name == "nt":
                video_concat_command = "copy /b " + "+".join([f"video_{i}.seg.{video_extension}" for i in range(0,count)]) + " encrypted_video.mp4"
                audio_concat_command = "copy /b " + "+".join([f"audio_{i}.seg.{audio_extension}" for i in range(0,count)]) + " encrypted_audio.mp4"
            else:
                video_concat_command = "cat " + " ".join([f"video_{i}.seg.{video_extension}" for i in range(0,count)]) + " > encrypted_video.mp4"
                audio_concat_command = "cat " + " ".join([f"audio_{i}.seg.{audio_extension}" for i in range(0,count)]) + " > encrypted_audio.mp4"
            print(video_concat_command)
            print(audio_concat_command)
            os.system(video_concat_command)
            os.system(audio_concat_command)
            decrypt(video_kid,"video")
            decrypt(audio_kid,"audio")
            mux_process(video_title,output_path)
            break
    

def manifest_parser(mpd_url):
    video = []
    audio = []
    manifest = requests.get(mpd_url).text
    with open("manifest.mpd",'w') as manifest_handler:
        manifest_handler.write(manifest)
    mpd = MPEGDASHParser.parse("./manifest.mpd")
    running_time = durationtoseconds(mpd.media_presentation_duration)
    for period in mpd.periods:
        for adapt_set in period.adaptation_sets:
            print("Processing " + adapt_set.mime_type)
            content_type = adapt_set.mime_type
            repr = adapt_set.representations[-1] # Max Quality
            for segment in repr.segment_templates:
                if(segment.duration):
                    print("Media segments are of equal timeframe")
                    segment_time = segment.duration / segment.timescale
                    total_segments = running_time / segment_time
                else:
                    print("Media segments are of inequal timeframe")
                    
                    approx_no_segments = round(running_time / 6) + 20 # aproximate of 6 sec per segment
                    print("Expected No of segments:",approx_no_segments)
                    if(content_type == "audio/mp4"):
                        segment_extension = segment.media.split(".")[-1]
                        audio.append(approx_no_segments)
                        audio.append(segment.media)
                        audio.append(segment.initialization)
                        audio.append(segment_extension)
                    elif(content_type == "video/mp4"):
                        segment_extension = segment.media.split(".")[-1]
                        video.append(approx_no_segments)
                        video.append(segment.media)
                        video.append(segment.initialization)
                        video.append(segment_extension)
    return video + audio



if __name__ == "__main__":
    mpd = "mpd url"
    base_url = mpd.split("index.mpd")[0]
    os.chdir(working_dir)
    media_info = manifest_parser(mpd)
    video_title = "175. Inverse Transforming Vectors" # the video title that gets embeded into the mp4 file metadata
    output_path = os.path.join(download_dir, "175. Inverse Transforming Vectors") # video title used in the filename, dont append .mp4
    handle_irregular_segments(media_info,video_title,output_path)
    cleanup(working_dir)
