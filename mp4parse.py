""" MP4 Parser based on:
http://download.macromedia.com/f4v/video_file_format_spec_v10_1.pdf 

@author: Alastair McCormack
@license: MIT License

"""

import bitstring
from datetime import datetime
from collections import namedtuple
import logging
import six

log = logging.getLogger(__name__)
#log.addHandler(logging.NullHandler())
log.setLevel(logging.WARN)

class MixinDictRepr(object):
    def __repr__(self, *args, **kwargs):
        return "{class_name} : {content!r} ".format(class_name=self.__class__.__name__,
                                                    content=self.__dict__)
        
class MixinMinimalRepr(object):
    """ A minimal representaion when the payload could be large """
   
    def __repr__(self, *args, **kwargs):
        return "{class_name} : {content!r} ".format(class_name=self.__class__.__name__,
                                                    content=self.__dict__.keys())

class FragmentRunTableBox(MixinDictRepr):
    pass


class UnImplementedBox(MixinDictRepr):
    type = "na"
    pass


class MovieFragmentBox(MixinDictRepr):
    type = "moof"

class MovieBox(MixinDictRepr):
    type = "moov"

class BootStrapInfoBox(MixinDictRepr):
    type = "abst"
        
    @property
    def current_media_time(self):
        return self._current_media_time
    
    @current_media_time.setter
    def current_media_time(self, epoch_timestamp):
        """ Takes a timestamp arg and saves it as datetime """
        self._current_media_time = datetime.utcfromtimestamp(epoch_timestamp/float(self.time_scale))
        
class FragmentRandomAccessBox(MixinDictRepr):
    """ aka afra """
    type = "afra"
    
    FragmentRandomAccessBoxEntry = namedtuple("FragmentRandomAccessBoxEntry", ["time", "offset"])
    FragmentRandomAccessBoxGlobalEntry = namedtuple("FragmentRandomAccessBoxGlobalEntry", ["time", "segment_number", "fragment_number", "afra_offset", "sample_offset"])
    
    pass


class SegmentRunTable(MixinDictRepr):
    type = "asrt"

    SegmentRunTableEntry = namedtuple('SegmentRunTableEntry', ["first_segment", "fragments_per_segment"])
    pass

class FragmentRunTable(MixinDictRepr):
    type = "afrt"

    class FragmentRunTableEntry( namedtuple('FragmentRunTableEntry', 
                                       ["first_fragment", 
                                        "first_fragment_timestamp", 
                                        "fragment_duration",
                                        "discontinuity_indicator"]) ):
        
        DI_END_OF_PRESENTATION = 0
        DI_NUMBERING = 1
        DI_TIMESTAMP = 2
        DI_TIMESTAMP_AND_NUMBER = 3
        
        def __eq__(self, other):
            if self.first_fragment == other.first_fragment and \
                self.first_fragment_timestamp == other.first_fragment_timestamp and \
                self.fragment_duration == other.fragment_duration and \
                self.discontinuity_indicator == other.discontinuity_indicator:
                    return True
        
    
    def __repr__(self, *args, **kwargs):
        return str(self.__dict__)

class MediaDataBox(MixinMinimalRepr):
    """ aka mdat """
    type = "mdat"

class MovieFragmentHeader(MixinDictRepr):
    type = "mfhd"

class ProtectionSystemSpecificHeader(MixinDictRepr):
    type = "pssh"

BoxHeader = namedtuple( "BoxHeader", ["box_size", "box_type", "header_size"] )
 
    
class F4VParser(object):

    @classmethod
    def parse(cls, filename=None, bytes_input=None, file_input=None, offset_bytes=0, headers_only=False):
        """
        Parse an MP4 file or bytes into boxes


        :param filename: filename of mp4 file.
        :type filename: str.
        :param bytes_input: bytes of mp4 file.
        :type bytes_input: bytes / Python 2.x str.
        :param offset_bytes: start parsing at offset.
        :type offset_bytes: int.
        :param headers_only: Ignore data and return just headers. Useful when data is cut short
        :type: headers_only: boolean
        :return: BMFF Boxes or Headers

        """

        box_lookup = {
            BootStrapInfoBox.type:                  cls._parse_abst,
            FragmentRandomAccessBox.type:           cls._parse_afra,
            MediaDataBox.type:                      cls._parse_mdat,
            MovieFragmentBox.type:                  cls._parse_moof,
            MovieBox.type:                          cls._parse_moov,
            MovieFragmentHeader.type:               cls._parse_mfhd,
            ProtectionSystemSpecificHeader.type:    cls._parse_pssh
        }
        
        if filename:
            bs = bitstring.ConstBitStream(filename=filename, offset=offset_bytes * 8)
        elif bytes_input:
            bs = bitstring.ConstBitStream(bytes=bytes_input, offset=offset_bytes * 8)
        else:
            bs = bitstring.ConstBitStream(auto=file_input, offset=offset_bytes * 8)
        
        log.debug("Starting parse")
        log.debug("Size is %d bits", bs.len)

        while bs.pos < bs.len:
            log.debug("Byte pos before header: %d relative to (%d)", bs.bytepos, offset_bytes)
            log.debug("Reading header")
            try:
                header = cls._read_box_header(bs)
            except bitstring.ReadError as e:
                log.error("Premature end of data while reading box header")
                raise
            
            log.debug("Header type: %s", header.box_type)
            log.debug("Byte pos after header: %d relative to (%d)", bs.bytepos, offset_bytes)

            if headers_only:
                yield header

                # move pointer to next header if possible
                try:
                    bs.bytepos += header.box_size
                except ValueError:
                    log.warning("Premature end of data")
                    raise
            else:
                # Get parser method for header type
                parse_function = box_lookup.get(header.box_type, cls._parse_unimplemented)
                try:
                    yield parse_function(bs, header)
                except ValueError as e:
                    log.error("Premature end of data")
                    raise

    @classmethod
    def _is_mp4(cls, parser):
        try:
            for box in parser:
                return True
        except ValueError:
            return False

    @classmethod
    def is_mp4_s(cls, bytes_input):
        """ Is bytes_input the contents of an MP4 file

        :param bytes_input: str/bytes to check.
        :type bytes_input: str/bytes.
        :return:
        """

        parser = cls.parse(bytes_input=bytes_input, headers_only=True)
        return cls._is_mp4(parser)

    @classmethod
    def is_mp4(cls, file_input):
        """ Checks input if it's an MP4 file

        :param input: Filename or file object
        :type input: str, file
        :param state: Current state to be in.
        :type state: bool.
        :returns:  bool.
        :raises: AttributeError, KeyError
        """

        if hasattr(file_input, "read"):
           parser = cls.parse(file_input=file_input, headers_only=True)
        else:
           parser = cls.parse(filename=file_input, headers_only=True)
        return cls._is_mp4(parser)

    @staticmethod
    def _read_string(bs):
        """ read UTF8 null terminated string """
        result = bs.readto('0x00', bytealigned=True).bytes.decode("utf-8")[:-1]
        return result if result else None

    @classmethod
    def _read_count_and_string_table(cls, bs):
        """ Read a count then return the strings in a list """
        result = []
        entry_count = bs.read("uint:8")
        for _ in six.range(0, entry_count):
            result.append( cls._read_string(bs) )
        return result

    @staticmethod
    def _read_box_header(bs):
        header_start_pos = bs.bytepos
        size, box_type = bs.readlist("uint:32, bytes:4")

        # box_type should be an ASCII string. Decode as UTF-8 in case
        try:
            box_type = box_type.decode('utf-8')
        except UnicodeDecodeError:
            # we'll leave as bytes instead
            pass

        # if size == 1, then this is an extended size type.
        # Therefore read the next 64 bits as size
        if size == 1:
            size = bs.read("uint:64")
        header_end_pos = bs.bytepos
        header_size = header_end_pos - header_start_pos    
        
        return BoxHeader(box_size=size-header_size, box_type=box_type, header_size=header_size)

    @staticmethod
    def _parse_unimplemented(bs, header):
        ui = UnImplementedBox()
        ui.header = header

        bs.bytepos += header.box_size
        
        return ui

    @classmethod
    def _parse_afra(cls, bs, header):
    
        afra = FragmentRandomAccessBox()
        afra.header = header
        
        # read the entire box in case there's padding
        afra_bs = bs.read(header.box_size * 8)
        # skip Version and Flags
        afra_bs.pos += 8 + 24
        long_ids, long_offsets, global_entries, afra.time_scale, local_entry_count  = \
                afra_bs.readlist("bool, bool, bool, pad:5, uint:32, uint:32")
        
        if long_ids:
            id_bs_type = "uint:32"
        else:
            id_bs_type = "uint:16"
                
        if long_offsets:
            offset_bs_type = "uint:64"
        else:
            offset_bs_type = "uint:32"
        
        log.debug("local_access_entries entry count: %s", local_entry_count)
        afra.local_access_entries = []        
        for _ in six.range(0, local_entry_count):
            time = cls._parse_time_field(afra_bs, afra.time_scale)
            
            offset = afra_bs.read(offset_bs_type)
            
            afra_entry = \
                FragmentRandomAccessBox.FragmentRandomAccessBoxEntry(time=time, 
                                                                     offset=offset)
            afra.local_access_entries.append(afra_entry)
        
        afra.global_access_entries = []
        
        if global_entries:
            global_entry_count = afra_bs.read("uint:32")
            
            log.debug("global_access_entries entry count: %s", global_entry_count)  
            
            for _ in six.range(0, global_entry_count):
                time = cls._parse_time_field(afra_bs, afra.time_scale)
                
                segment_number = afra_bs.read(id_bs_type)
                fragment_number = afra_bs.read(id_bs_type)
                
                afra_offset = afra_bs.read(offset_bs_type)
                sample_offset = afra_bs.read(offset_bs_type)
                
                afra_global_entry = \
                    FragmentRandomAccessBox.FragmentRandomAccessBoxGlobalEntry(
                                            time=time,
                                            segment_number=segment_number,
                                            fragment_number=fragment_number,
                                            afra_offset=afra_offset,
                                            sample_offset=sample_offset)
    
                afra.global_access_entries.append(afra_global_entry)
       
        return afra

    @classmethod
    def _parse_moof(cls, bootstrap_bs, header):
        moof = MovieFragmentBox()
        moof.header = header

        box_bs = bootstrap_bs.read(moof.header.box_size * 8)

        for child_box in cls.parse(bytes_input=box_bs.bytes):
            setattr(moof, child_box.type, child_box)

        return moof

    @classmethod
    def _parse_moov(cls, bootstrap_bs, header):
        moov = MovieBox()
        moov.header = header
        psshs = []

        box_bs = bootstrap_bs.read(moov.header.box_size * 8)

        for child_box in cls.parse(bytes_input=box_bs.bytes):
            if(child_box.type == "pssh"):
                psshs.append(child_box)
            else:
                setattr(moov, child_box.type, child_box)
        setattr(moov, "pssh", psshs)

        return moov

    @classmethod
    def _parse_mfhd(cls, bootstrap_bs, header):
        mfhd = MovieFragmentHeader()
        mfhd.header = header

        box_bs = bootstrap_bs.read(mfhd.header.box_size * 8)
        return mfhd

    @staticmethod
    def _parse_pssh(bootstrap_bs, header):
        pssh = ProtectionSystemSpecificHeader()
        pssh.header = header

        box_bs = bootstrap_bs.read(pssh.header.box_size*8)
        # Payload appears to be 8 bytes in.
        data = box_bs.hex[8:]
        pssh.system_id = data[:32]
        pssh.payload = data[40:]
        return pssh

    @classmethod
    def _parse_abst(cls, bootstrap_bs, header):
        
        abst = BootStrapInfoBox()
        abst.header = header
        
        box_bs = bootstrap_bs.read(abst.header.box_size * 8)
        
        abst.version, abst.profile_raw, abst.live, abst.update, \
        abst.time_scale, abst.current_media_time, abst.smpte_timecode_offset = \
                box_bs.readlist("""pad:8, pad:24, uint:32, uint:2, bool, bool,
                                   pad:4,
                                   uint:32, uint:64, uint:64""")
        abst.movie_identifier = cls._read_string(box_bs)
        
        abst.server_entry_table = cls._read_count_and_string_table(box_bs)
        abst.quality_entry_table = cls._read_count_and_string_table(box_bs)
            
        abst.drm_data = cls._read_string(box_bs)
        abst.meta_data = cls._read_string(box_bs)
                
        abst.segment_run_tables = []
        
        segment_count = box_bs.read("uint:8")
        log.debug("segment_count: %d" % segment_count)
        for _ in six.range(0, segment_count):
            abst.segment_run_tables.append( cls._parse_asrt(box_bs) )

        abst.fragment_tables = []
        fragment_count = box_bs.read("uint:8")
        log.debug("fragment_count: %d" % fragment_count)
        for _ in xrange(0, fragment_count):
            abst.fragment_tables.append( cls._parse_afrt(box_bs) )
        
        log.debug("Finished parsing abst")
        
        return abst

    @classmethod
    def _parse_asrt(cls, box_bs):
        """ Parse asrt / Segment Run Table Box """
        
        asrt = SegmentRunTable()
        asrt.header = cls._read_box_header(box_bs)
        # read the entire box in case there's padding
        asrt_bs_box = box_bs.read(asrt.header.box_size * 8)
        
        asrt_bs_box.pos += 8
        update_flag = asrt_bs_box.read("uint:24")
        asrt.update = True if update_flag == 1 else False
        
        asrt.quality_segment_url_modifiers = cls._read_count_and_string_table(asrt_bs_box)
        
        asrt.segment_run_table_entries = []
        segment_count = asrt_bs_box.read("uint:32")
        
        for _ in six.range(0, segment_count):
            first_segment = asrt_bs_box.read("uint:32")
            fragments_per_segment = asrt_bs_box.read("uint:32")
            asrt.segment_run_table_entries.append( 
                SegmentRunTable.SegmentRunTableEntry(first_segment=first_segment,
                                                     fragments_per_segment=fragments_per_segment) )
        return asrt

    @classmethod
    def _parse_afrt(cls, box_bs):
        """ Parse afrt / Fragment Run Table Box """
        
        afrt = FragmentRunTable()
        afrt.header = cls._read_box_header(box_bs)
        # read the entire box in case there's padding
        afrt_bs_box = box_bs.read(afrt.header.box_size * 8)
        
        afrt_bs_box.pos += 8
        update_flag = afrt_bs_box.read("uint:24")
        afrt.update = True if update_flag == 1 else False
 
        afrt.time_scale = afrt_bs_box.read("uint:32")
        afrt.quality_fragment_url_modifiers = cls._read_count_and_string_table(afrt_bs_box)
        
        fragment_count = afrt_bs_box.read("uint:32")
        
        afrt.fragments = []

        for _ in six.range(0, fragment_count):
            first_fragment = afrt_bs_box.read("uint:32")
            first_fragment_timestamp_raw = afrt_bs_box.read("uint:64")
            
            try:
                first_fragment_timestamp = datetime.utcfromtimestamp(first_fragment_timestamp_raw/float(afrt.time_scale))
            except ValueError:
                # Elemental sometimes create odd timestamps
                first_fragment_timestamp = None
                
            fragment_duration = afrt_bs_box.read("uint:32")
            
            if fragment_duration == 0:
                discontinuity_indicator = afrt_bs_box.read("uint:8")
            else:
                discontinuity_indicator = None
            
            frte = FragmentRunTable.FragmentRunTableEntry(first_fragment=first_fragment,
                                                          first_fragment_timestamp=first_fragment_timestamp,
                                                          fragment_duration=fragment_duration,
                                                          discontinuity_indicator=discontinuity_indicator)
            afrt.fragments.append(frte)
        return afrt

    @staticmethod
    def _parse_mdat(box_bs, header):
        """ Parse afrt / Fragment Run Table Box """
                
        mdat = MediaDataBox()
        mdat.header = header
        mdat.payload = box_bs.read(mdat.header.box_size * 8).bytes
        return mdat

    @staticmethod
    def _parse_time_field(bs, scale):
        timestamp = bs.read("uint:64")
        return datetime.utcfromtimestamp(timestamp / float(scale) )