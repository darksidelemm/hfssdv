#
#   SSDV RX Lib
#

import datetime
import logging
import os
import sys
import time
from .packets import *

class SSDVRX(object):
    """ Class to handle receipt of SSDV packets and their organisation into images. """

    def __init__(self, ssdv_path="./ssdv"):

        self.ssdv_path = ssdv_path

        self.image_store = {}
        
        self.latest_update = None

        if not os.path.isfile(ssdv_path):
            logging.critical("Could not find SSDV binary.")
            sys.exit(1)
    

    def calculateMissing(self, received):
        """ Calculate the missing packets based on the received packets """
        _missing = []
        for i in range(max(received)):
            if i not in received:
                _missing.append(i)
        
        return _missing


    def decode(self, image, tempfile='rxtemp.bin', outfile='rxtemp.jpg'):
        """ Attempt to write-out a SSDV image to a file """
        
        # Grab list of packets and sort.
        _packet_numbers = list(image['packets'].keys())
        _packet_numbers.sort()

        # Write out to disk.
        _f = open(tempfile, 'wb')
        for _pkt in _packet_numbers:
            _f.write(image['packets'][_pkt])
        _f.close()

        # Attempt to SSDV decode the file.

        _command = f"./ssdv -d {tempfile} {outfile} 2>/dev/null > /dev/null"

        retcode = os.system(_command)

        if retcode == 0:
            return outfile
        else:
            return None


    def addPacket(self, packet):
        """ Handle receipt of a new packet from the TNC """
        if len(packet) == 257:
            # Possibly a SSDV packet
            if packet[1] == SSDV_HEADER:
                # Strip off TNC port (first byte)
                packet = packet[1:]

                pkt_info = ssdv_packet_info(packet)

                _callsign = pkt_info['callsign']
                _img_id = pkt_info['image_id']
                _pkt_id = pkt_info['packet_id']
                _width = pkt_info['width']
                _height = pkt_info['height']

                if _callsign not in self.image_store:
                    self.image_store[_callsign] = {}

                if _img_id not in self.image_store[_callsign]:
                    self.image_store[_callsign][_img_id] = {
                        'packets': {
                            _pkt_id: packet
                        },
                        'missing': [],
                        'width': _width,
                        'height': _height,
                        'callsign': _callsign,
                        'id': _img_id,
                        'time': datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
                    }

                else:
                    self.image_store[_callsign][_img_id]['packets'][_pkt_id] = packet
                
                # Calculate missing packets from image.
                self.image_store[_callsign][_img_id]['missing'] = self.calculateMissing(
                    list(self.image_store[_callsign][_img_id]['packets'].keys())
                )

                self.latest_update = self.image_store[_callsign][_img_id]

                logging.info(f"New SSDV Packet. Call: {_callsign}, ID: {_img_id}, Pkt No:{_pkt_id}")

                return {
                    'type': 'image_update', 
                    'latest': self.latest_update,
                    'store': self.image_store
                    }

            elif packet[1] == RESEND_HEADER:
                # TODO: Handle resend request
                logging.info("Got resend request! (Not implemented yet)")
                return None

        else:
            logging.error("Unknown packet size.")
            return None


    def clearStore(self):
        """ Erase the internal image store """
        self.image_store = {}

