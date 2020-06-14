import struct
import traceback

#
# SSDV - Packets as per https://ukhas.org.uk/guides:ssdv
#

SSDV_RES_MULTIPLE = 16 # All SSDV packets need to have width/heights that are multiples of this.


SSDV_HEADER = 0x55
RESEND_HEADER = 0x50

_ssdv_callsign_alphabet = '-0123456789---ABCDEFGHIJKLMNOPQRSTUVWXYZ'
def ssdv_decode_callsign(code):
    """ Decode a SSDV callsign from a supplied array of ints,
        extract from a SSDV packet.

        Args:
            list: List of integers, corresponding to bytes 2-6 of a SSDV packet.

        Returns:
            str: Decoded callsign.

    """

    code = bytes(bytearray(code))
    code = struct.unpack('>I',code)[0]
    callsign = ''

    while code:
        callsign += _ssdv_callsign_alphabet[code % 40]
        code = code // 40
    
    return callsign


def ssdv_packet_info(packet):
    """ Extract various information out of a SSDV packet, and present as a dict. """
    packet = list(bytearray(packet))
    # Check packet is actually a SSDV packet.
    if len(packet) != 256:
        return None

    if packet[0] != 0x55: # A first byte of 0x55 indicates a SSDV packet.
        return None

    # We got this far, may as well try and extract the packet info.
    try:
        packet_info = {
            'callsign' : ssdv_decode_callsign(packet[2:6]), # TODO: Callsign decoding.
            'packet_type' : "FEC" if (packet[1]==0x66) else "No-FEC",
            'image_id' : packet[6],
            'packet_id' : (packet[7]<<8) + packet[8],
            'width' : packet[9]*16,
            'height' : packet[10]*16,
            'error' : "None"
        }

        return packet_info
    except Exception as e:
        traceback.print_exc()
        return None


def ssdv_packet_string(packet):
    """ Produce a textual representation of a SSDV packet. """
    if packet_info:
        return "SSDV: %s, Callsign: %s, Img:%d, Pkt:%d, %dx%d" % (packet_info['packet_type'],packet_info['callsign'],packet_info['image_id'],packet_info['packet_id'],packet_info['width'],packet_info['height'])



def encode_resend_packet(theircall, mycall, img_id, last_packet, packets):
    """ Generate a Resend request packet """
    pass


def decode_resend_packet(packet):
    """ Decode a Resend request packet """
    pass