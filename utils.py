import base64
import codecs
import os

import mp4parse
import widevine_pssh_data_pb2


def extract_kid(mp4_file):
    """
    Parameters
    ----------
    mp4_file : str
        MP4 file with a PSSH header


    Returns
    -------
    String

    """

    boxes = mp4parse.F4VParser.parse(filename=mp4_file)
    if not os.path.exists(mp4_file):
        raise Exception("File does not exist")
    for box in boxes:
        if box.header.box_type == "moov":
            pssh_box = next(x for x in box.pssh if x.system_id == "edef8ba979d64acea3c827dcd51d21ed")
            hex = codecs.decode(pssh_box.payload, "hex")

            pssh = widevine_pssh_data_pb2.WidevinePsshData()
            pssh.ParseFromString(hex)
            content_id = base64.b16encode(pssh.content_id)
            return content_id.decode("utf-8").lower()

    # No Moof or PSSH header found
    return None
