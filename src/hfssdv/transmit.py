#
#   SSDV TX Lib
#

import logging
import os
import sys
import time
from PIL import Image
from .packets import *

class SSDVTX(object):
    """ Class to handle loading, compressing, and transmitting images. """

    def __init__(self, ssdv_path="./ssdv"):

        self.ssdv_path = ssdv_path
        self.image_id = 0

        self.image_store = {}

        self.current_image = None

        # Flag set to abort a currently running transmission.
        self.abort_tx = False


        if not os.path.isfile(ssdv_path):
            logging.critical("Could not find SSDV binary.")
            sys.exit(1)
            

    def resize_image(self, filename, outfile="txtemp.jpg"):
        """ Resize image if necessary """
        img = Image.open(filename)

        width, height = img.size

        # Round sizes to multples of 16
        _new_width = int(round(width/SSDV_RES_MULTIPLE)*SSDV_RES_MULTIPLE)
        _new_height = int(round(height/SSDV_RES_MULTIPLE)*SSDV_RES_MULTIPLE)

        if (_new_width != width) or (_new_height != height):
            logging.info(f"Resizing image to {_new_width}x{_new_height} for transmission.")
            img = img.resize((_new_width, _new_height))
        else:
            logging.info("Not resizing image.")
        
        img.save(outfile, "JPEG")
        img.close()


    def compress_image(self, infile="txtemp.jpg", id=0, outfile="txtemp.bin", callsign="N0CALL", quality=4):
        """ Attempt to compress a JPEG using SSDV. """

        _command = f"./ssdv -e -n -c {callsign} -i {id} -q {quality} {infile} {outfile}"

        retcode = os.system(_command)

        if retcode == 0:
            return True
        else:
            return False


    def read_in_packets(self,filename="txtemp.bin"):
        """ Read in a SSDV file ready for transmission """
        file_size = os.path.getsize(filename)

        packets = []

        try:
            f = open(filename,'rb')
            for x in range(file_size//256):
                data = f.read(256)
                packets.append(data)
            
            f.close()
        except Exception as e:
            logging.critical(f"Could not read in {filename}.")
            return None
        
        return packets


    def load_new_image(self,filename, callsign="N0CALL", quality=4):
        """ Load in a new JPEG file, resize it if necessary, compress, and add to our image store 
        
            Return a string with a status message.
        
        """

        # Resize image
        try:
            self.resize_image(filename)
        except Exception as e:
            _error = f"Could not load image: {str(e)}"
            logging.error(_error)
            return _error

        # Compress image
        _compress_ok =  self.compress_image(id=self.image_id, callsign=callsign, quality=quality)

        if not _compress_ok:
            _error = "Could not compress image."
            logging.error(_error)
            return _error
        
        # Now load in the SSDV data.
        _packets = self.read_in_packets()

        if _packets:
            # Add to local store.
            self.image_store[self.image_id] = {
                'callsign': callsign,
                'quality': quality,
                'packets': _packets
            }

            self.current_image = self.image_id

            # Increment image ID.
            self.image_id = (self.image_id + 1) % 256

            _status = f"Img ID {self.current_image}: ({os.path.basename(filename)}): {len(_packets)} packets."
            logging.info(_status)
            return _status

        else:
            _error = "Could not load in compressed file."
            logging.error(_error)
            return _error


    def transmit_current_image(self, tnc, delay=7, status_callback=None):
        """ Transmit the current loaded image through the supplied KISS TNC """

        if self.current_image in self.image_store:
            for _i in range(len(self.image_store[self.current_image]['packets'])):
                _packet = self.image_store[self.current_image]['packets'][_i]
                tnc.write(_packet)
                
                _status = f"TXing Image {self.current_image} packet {_i+1}/{len(self.image_store[self.current_image]['packets'])}."
                logging.info(_status)
                if status_callback:
                    status_callback(_status)
                
                time.sleep(delay)

                if self.abort_tx:
                    _status = "Aborting Transmission"
                    logging.info(_status)
                    if status_callback:
                        status_callback(_status)

                    self.abort_tx = False
                    return

            _status = "Transmit Done."
            logging.info(_status)
            if status_callback:
                status_callback(_status)
        
        else:
            _error = "No image to transmit."
            logging.error(_error)
            if status_callback:
                status_callback(_error)


    def abort(self):
        self.abort_tx = True

if __name__ == "__main__":
    # Simple test script.

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', level=logging.DEBUG
    )

    def status_callback(text):
        print(text)

    class DummyTNC(object):
        def __init__(self):
            pass

        def write(self,packet):
            print(f"TNC - Transmitted packet.")


    tnc = DummyTNC()

    _image = "./images/wut.jpg"

    tx = SSDVTX()

    tx.load_new_image(_image)

    tx.transmit_current_image(tnc=tnc, status_callback=status_callback)