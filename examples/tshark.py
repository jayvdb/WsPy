import os
import sys
import time
import struct
import socket
from datetime import datetime as dt

from wspy.wireshark.lib.epan_ext import lib as epan_lib
from wspy.wireshark.lib.epan_ext import ffi as epan_ffi

from wspy.wireshark.lib.wtap_ext import lib as wtap_lib
from wspy.wireshark.lib.wtap_ext import ffi as wtap_ffi

_MAX_TO_PROCESS = 10000000


nstime_empty = epan_ffi.new('nstime_t *');

@epan_ffi.callback('const nstime_t *(*)(struct packet_provider_data *prov, guint32 frame_num)')
def wspy_get_ts(prov, frame_num):

    return nstime_empty

wspy_provider_funcs = epan_ffi.new('struct packet_provider_funcs *',
        [wspy_get_ts, epan_ffi.NULL, epan_ffi.NULL, epan_ffi.NULL])

# Below are some dict's required for printing few packet types

hfbases = {
        epan_lib.BASE_NONE : '{:d}', # Not sure how this is to be treated
        epan_lib.BASE_DEC : '{:d}',
        epan_lib.BASE_HEX : '0x{:x}',
        epan_lib.BASE_OCT : '{:o}',
        epan_lib.BASE_DEC_HEX: '{:d}(0x{:x})',
        epan_lib.BASE_HEX_DEC: '0x{:x}({:d})',
        epan_lib.BASE_PT_TCP: '{:d}',
        epan_lib.BASE_PT_UDP: '{:d}',
        epan_lib.BASE_PT_SCTP: '{:d}'

        }
def func_not_supported(*args):
    return "Not Supported"

def epan_ether_to_str(fvalue, ftype, display):

    eth_bytes = fvalue.value.bytes

    display_bytes = []
    for i in range(eth_bytes.len):
        display_byte = "{:02X}".format(eth_bytes.data[i])
        display_bytes.append(display_byte)

    return ":".join(display_bytes)

epan_bytes_to_str = epan_ether_to_str

def epan_str_to_str(fvalue, ftype, display):

    value = fvalue.value.string
    return epan_ffi.string(value).decode()

def epan_ipv4_to_str(fvalue, ftype, display):

    ipv4 = fvalue.value.ipv4

    return socket.inet_ntoa(struct.pack('!I', ipv4.addr))

def epan_bool_to_str(fvalue, ftype, display, on_off=False, json_compat=True):

    if on_off and json_compat:
        raise ValueError("Specify Either on_off or json_compat not both.")

    value = bool(fvalue.value.uinteger)

    if value:
        if json_compat:
            return "true"
        if on_off:
            return "ON"
    else:
        if json_compat:
            return "false"
        if on_off:
            return "OFF"

    return "{}".format(value)


def epan_int_to_str(fvalue, ftype, display):

    try:
        # We are not displaying 'Extended string for the value
        if display & epan_lib.BASE_EXT_STRING:
            display ^= epan_lib.BASE_EXT_STRING

        base_format = hfbases[display]
    except:
        return "type: {} display: {} Not Supported".format(ftype, display)

    return base_format.format(fvalue.value.uinteger,
            fvalue.value.uinteger)

def value_to_str(finfo):
    """
    Returns string representation of the `finfo.value`
    """

    fvalue = finfo.value
    ftype = finfo.hfinfo[0].type
    display = finfo.hfinfo[0].display

    epan_int_types = [
            epan_lib.FT_INT8,
            epan_lib.FT_INT16,
            epan_lib.FT_INT32,
            epan_lib.FT_INT40,
            epan_lib.FT_INT48,
            epan_lib.FT_INT56,
            epan_lib.FT_INT64]

    epan_uint32_types = [
            epan_lib.FT_CHAR,
            epan_lib.FT_UINT8,
            epan_lib.FT_UINT16,
            epan_lib.FT_UINT32,
            epan_lib.FT_FRAMENUM]

    epan_uint_types = epan_uint32_types + \
            [ epan_lib.FT_UINT40, epan_lib.FT_UINT48,
            epan_lib.FT_UINT56, epan_lib.FT_UINT64]

    epan_all_int_types = epan_int_types + epan_uint_types

    if ftype in epan_all_int_types:
        return epan_int_to_str(fvalue, ftype, display)

    if ftype == epan_lib.FT_ETHER:
        return epan_ether_to_str(fvalue, ftype, display)

    if ftype == epan_lib.FT_IPv4:
        return epan_ipv4_to_str(fvalue, ftype, display)

    if ftype == epan_lib.FT_BOOLEAN:
        return epan_bool_to_str(fvalue, ftype, display)

    if ftype == epan_lib.FT_STRING:
        return epan_str_to_str(fvalue, ftype, display)

    if ftype == epan_lib.FT_BYTES:
        return epan_bytes_to_str(fvalue, ftype, display)

    if ftype in [epan_lib.FT_NONE, epan_lib.FT_PROTOCOL]:
        return ""

    return "{} {}".format(ftype, display)

def print_dissected_tree(node_ptr, data_ptr):

    return_str = ""

    if data_ptr == epan_ffi.NULL:
        level = 1
    else:
        level = epan_ffi.cast('int *', data_ptr)[0]

    return_str = ""
    node = node_ptr[0]
    finfo = node.finfo
    if finfo != epan_ffi.NULL:

        hfinfo = finfo.hfinfo[0]
        abbrev = epan_ffi.string(hfinfo.abbrev).decode()
        abbrev_str = "\"{!s}\"".format(abbrev)
        return_str += abbrev_str + ": "
        finfo_display_str = value_to_str(finfo)
        if finfo_display_str:
            finfo_display_str = "\"{!s}\"".format(finfo_display_str)
    else:
        finfo_display_str = ""

    return_str += finfo_display_str

    data_ptr_new = epan_ffi.new('int *')
    data_ptr_new[0] = level + 1
    child = node.first_child
    if child != epan_ffi.NULL:

        if finfo_display_str:
            return_str += ",\n"

            abbrev_tree = abbrev + "_tree"
            abbrev_tree_str = "\"{!s}\"".format(abbrev_tree)
            return_str += "  " * (level -1)
            return_str += abbrev_tree_str + " : "

        return_str += "{ "
        return_str += "\n"
        while child != epan_ffi.NULL:
            return_str += "  " * level
            return_str += print_dissected_tree(child, data_ptr_new)
            child = child.next
        return_str += "  " * level

        return_str += "\n"
        return_str += "  " * (level-1)
        return_str += "}"
    if node.next != epan_ffi.NULL:
        return_str += ",\n"

    return return_str

def packet_to_json(frame_data_ptr, edt_ptr):
    fdata = frame_data_ptr[0]
    edt = edt_ptr[0]

    #print(print_dissected_tree(edt.tree, epan_ffi.NULL))

def wtap_open_file_offline(filepath):
    """
    Opens a file given by filepath  using `wtap_open_offline` and returns a tuple containing
    Handle and file type.
    """

    if not os.path.exists(filepath):
        return None, None


    wtap_lib.wtap_init(False)

    # Open a wtap file
    err = wtap_ffi.new('int *')
    err_str = wtap_ffi.new("gchar *[256]")
    filename = filepath
    open_type = wtap_lib.WTAP_TYPE_AUTO
    wth = wtap_lib.wtap_open_offline(filename.encode(), open_type, err, err_str, False)
    if wth is wtap_ffi.NULL:
        return None, None

    wtap_file_type = wtap_lib.wtap_file_type_subtype(wth)
    return wth, wtap_file_type

# Open `epan_lib`

def epan_lib_init():
    """
    Performs initialzation of the `epan` library. Calls
    1. `init_process_policies` (Required)
    2. `epan_init` (Required)
    3. `epan_load_settings` (Required)

    Returns True/False based upon result of operation.
    """

    epan_lib.init_process_policies()
    null_register_cb = epan_ffi.cast('register_cb', epan_ffi.NULL)
    register_protocols_handle = epan_ffi.callback('void (*)(register_cb, gpointer)',
            epan_lib.register_all_protocols)
    register_handoffs_handle = epan_ffi.callback('void (*)(register_cb, gpointer)',
            epan_lib.register_all_protocol_handoffs)
    result = epan_lib.epan_init(
            register_protocols_handle,
            register_handoffs_handle,
            null_register_cb, epan_ffi.NULL)
    if result:
        epan_lib.epan_load_settings()

    return result

def epan_perform_dissection(wth, wth_file_type):
    """
    Performs dissection of the file bound to `wth`
    """
    #empty_packet_provider_funcs = epan_ffi.new('struct packet_provider_funcs *')
    epan_session = epan_lib.epan_new(epan_ffi.NULL, wspy_provider_funcs)

    # TODO: make proper `epan_session` for us
    epan_dissect_obj = epan_lib.epan_dissect_new(epan_session, True, True)

    offset = wtap_ffi.new('gint64 *')
    frame_data_ref = epan_ffi.new('frame_data **')
    elapsed_time_ptr = epan_ffi.new('nstime_t *')

    err = wtap_ffi.new('int *')
    err_str = wtap_ffi.new("gchar **")

    frame_data_ref[0] = epan_ffi.NULL
    frame_data_ptr = epan_ffi.new('frame_data *')
    cum_bytes = epan_ffi.new('guint32 *')
    then = dt.now()
    processed = 0
    total_bytes = 0
    while True:
        result = wtap_lib.wtap_read(wth, err, err_str, offset)

        if result == True:
            processed += 1
            rec = wtap_lib.wtap_get_rec(wth)
            buf_ptr = wtap_lib.wtap_get_buf_ptr(wth)

            epan_rec = epan_ffi.cast('wtap_rec *', rec)
            pkt_len = rec.rec_header.packet_header.len
            pkt_reported_len = rec.rec_header.packet_header.caplen


            epan_lib.frame_data_init(frame_data_ptr, processed, epan_rec,
                    offset[0], cum_bytes[0])

            total_bytes += pkt_reported_len
            cum_bytes[0] = total_bytes
            # FIXME: Look at properly using `frame_data_ref`
            epan_lib.frame_data_set_before_dissect(frame_data_ptr,
                    elapsed_time_ptr, frame_data_ref, epan_ffi.NULL)


            # Not sure what this is - Just copied from `tshark` sources
            epan_lib.prime_epan_dissect_with_postdissector_wanted_hfids(
                    epan_dissect_obj)

            ## Do actual dissection here.
            # Get buffer and tvbuff first and then run dissector
            tvb_ptr = epan_lib.tvb_new_real_data(buf_ptr, pkt_len,
                    pkt_reported_len)

            epan_lib.epan_dissect_run(epan_dissect_obj, wth_file_type,
                    epan_rec, tvb_ptr, frame_data_ptr, epan_ffi.NULL)

            packet_to_json(frame_data_ptr, epan_dissect_obj)

            # Reset the frame data and dissector object
            epan_lib.frame_data_set_after_dissect(frame_data_ptr, cum_bytes)
            epan_lib.epan_dissect_reset(epan_dissect_obj)

            processed += 1

            if processed == _MAX_TO_PROCESS:
                break

        else:
            break

    now = dt.now()

    print("Processded {} bytes from {} packets in {}".format(
            total_bytes, processed, (now - then)))


if __name__ == '__main__':

    if not len(sys.argv) >= 2:
        print("Usage: tshark.py <filepath>")
        sys.exit(1)

    input_filepath = sys.argv[1]

    wth, wth_ftype = wtap_open_file_offline(input_filepath)
    if wth is None:
        print("Unable to get 'wiretap' File Handle.")
        sys.exit(1)

    epan_lib_result = epan_lib_init()
    if not epan_lib_result:
        print("Unable to open 'epan' library.")
        sys.exit(1)

    epan_perform_dissection(wth, wth_ftype)
