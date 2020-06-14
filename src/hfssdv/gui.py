#!/usr/bin/env python
#
#   HF SSDV GUI
#
#   Mark Jessop <vk5qi@rfhead.net>
#


# Python 3 check
import sys

if sys.version_info < (3, 0):
    print("This script requires Python 3!")
    sys.exit(1)

import glob
import kissfix
import logging
import pyqtgraph as pg
import numpy as np
from queue import Queue
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from pyqtgraph.dockarea import *
from threading import Thread

from .widgets import *
from .transmit import *
from .receive import *


# Setup Logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s", level=logging.DEBUG
)

# Defaults

DEFAULT_TNC_HOST = 'localhost'
DEFAULT_TNC_PORT = 8001

VALID_IMAGE_QUALITY = [0,1,2,3,4,5,5,6,7]
DEFAULT_IMAGE_QUALITY = 4

DEFAULT_CALLSIGN = 'N0CALL'

# Singleton instances of TNC Connection, SSDV TX/RX Objects, to be instantiated later.
tnc = None
ssdv_tx = SSDVTX()
ssdv_rx = SSDVRX()

# Thread to deal with packets from the KISS TNC
ssdv_rx_thread = None
ssdv_rx_thread_running = True

ssdv_tx_thread = None
ssdv_tx_thread_running = False


# Queues for handling updates to image / status indications.
image_update_queue = Queue(256)
status_update_queue = Queue(256)



#
#   GUI Creation - The Bad way.
#

# Create a Qt App.
pg.mkQApp()

# GUI LAYOUT - Gtk Style!
win = QtGui.QMainWindow()
area = DockArea()
win.setCentralWidget(area)
win.setWindowTitle("HF SSDV")

# Create multiple dock areas, for displaying our data.
d0 = Dock("Controls", size=(300,800))
d1 = Dock("Image List", size=(300,800))
d2 = Dock("RX Image", size=(800, 800))
d3 = Dock("Image Metadata",size=(800,50))
area.addDock(d0, "left")
area.addDock(d1, "right", d0)
area.addDock(d2, "right", d1)
area.addDock(d3, "bottom", d2)



# Controls
w1 = pg.LayoutWidget()
# TNC Connection
tncHostLabel = QtGui.QLabel("<b>TNC Host:</b>")
tncHostEntry = QtGui.QLineEdit(DEFAULT_TNC_HOST)
tncPortLabel = QtGui.QLabel("<b>TNC Port:</b>")
tncPortEntry = QtGui.QLineEdit(str(DEFAULT_TNC_PORT))
tncConnectButton = QtGui.QPushButton("Connect")
tncStatusLabel = QtGui.QLabel("Not Connected")

# User Information & Image TX Settings

userCallLabel = QtGui.QLabel("<b>Callsign:</b>")
userCallEntry = QtGui.QLineEdit(DEFAULT_CALLSIGN)
userCallEntry.setMaxLength(6) # Maximum SSDV callsign length.

imageQualityLabel = QtGui.QLabel("<b>Img Quality:</b>")
imageQualitySelector = QtGui.QComboBox()
for _qual in VALID_IMAGE_QUALITY:
    imageQualitySelector.addItem(str(_qual))
imageQualitySelector.setCurrentIndex(
    imageQualitySelector.findText(str(DEFAULT_IMAGE_QUALITY))
)
packetDelayLabel = QtGui.QLabel("<b>Delay (s)</b>")
packetDelayEntry = QtGui.QLineEdit("8")


# Load Image
loadImageButton = QtGui.QPushButton("Load JPEG")
loadImageStatus = QtGui.QLabel("No Image Loaded")

txImageButton = QtGui.QPushButton("Transmit")
txImageStatus = QtGui.QLabel("Not TXing.")
abortTxButton = QtGui.QPushButton("Halt TX")

# Layout the Control pane.
w1.addWidget(tncHostLabel, 0, 0, 1, 1)
w1.addWidget(tncHostEntry, 0, 1, 1, 1)
w1.addWidget(tncPortLabel, 1, 0, 1, 1)
w1.addWidget(tncPortEntry, 1, 1, 1, 1)
w1.addWidget(tncConnectButton, 2, 0, 1, 2)
w1.addWidget(tncStatusLabel, 3, 0, 1, 2)
w1.addWidget(QHLine(), 4, 0, 1, 2)
w1.addWidget(userCallLabel, 5, 0, 1, 1)
w1.addWidget(userCallEntry, 5, 1, 1, 1)
w1.addWidget(imageQualityLabel, 6, 0, 1, 1)
w1.addWidget(imageQualitySelector, 6, 1, 1, 1)
w1.addWidget(packetDelayLabel, 7, 0, 1, 1)
w1.addWidget(packetDelayEntry, 7, 1, 1, 1)
w1.addWidget(QHLine(), 8, 0, 1, 2)
w1.addWidget(loadImageButton, 9, 0, 1, 2)
w1.addWidget(loadImageStatus, 10, 0, 1, 2)
w1.addWidget(QHLine(), 11, 0, 1, 2)
w1.addWidget(txImageButton, 12, 0, 1, 2)
w1.addWidget(txImageStatus, 13, 0, 1, 2)
w1.addWidget(abortTxButton, 14, 0, 1, 2)
w1.layout.setSpacing(1)
d0.addWidget(w1)


# Received Image List
w2 = pg.LayoutWidget()

rxImageList = QtGui.QListWidget()
rxImageList.addItem('No Images')
resendButton = QtGui.QPushButton("Request Resend")

# Layout
w2.addWidget(rxImageList,0,0,1,1)
w2.addWidget(resendButton,1,0,1,1)

d1.addWidget(w2)


# Image Pane - Just the one ImageLabel
w3 = pg.LayoutWidget()
rxImageLabel = ImageLabel()
w3.addWidget(rxImageLabel, 0, 0, 1, 1)
d2.addWidget(w3)

# Image Metadata
w4 = pg.LayoutWidget()
rxImageStatus = QtGui.QLabel("No Image Data Yet.")
w4.addWidget(rxImageStatus, 0, 0, 1, 1)
d3.addWidget(w4)

# Resize window to final resolution, and display.
logging.info("Starting GUI.")
win.resize(1500, 800)
win.show()



# Image Update Functions

def changeImage(filename):
    """ Load and display the supplied image, and update the status text field. """
    global rxImageLabel

    logging.debug(f"Loading image: {filename}")
    pixmap = QtGui.QPixmap(filename)

    rxImageLabel.pixmap = pixmap
    rxImageLabel.repaint()



# Load an image
def loadNewImage():
    """ Attempt to load a new image file into the TX image store. """
    global ssdv_tx, loadImageStatus, userCallEntry, imageQualitySelector

    fname = QtWidgets.QFileDialog.getOpenFileName(None,'Open Image','.',"Image files (*.jpg *.jpeg)")

    if fname[0] != '':

        _call = userCallEntry.text()
        _quality = int(imageQualitySelector.currentText())

        _result = ssdv_tx.load_new_image(
            filename=fname[0],
            callsign=_call,
            quality=_quality
        )

        loadImageStatus.setText(_result)
    else:
        logging.error("No file selected.")
        
loadImageButton.clicked.connect(loadNewImage)


def transmitImageThread():
    global ssdv_tx, txImageStatus, tnc

    ssdv_tx_thread_running = True

    try:
        _delay = int(packetDelayEntry.text())
        _callback = txImageStatus.setText
        ssdv_tx.transmit_current_image(
            tnc=tnc,
            delay=_delay,
            status_callback=_callback
        )
    except Exception as e:
        _error = f"Error sending image: {str(e)}"
        logging.error(_error)


    ssdv_tx_thread_running = False


def transmitImage():
    global ssdv_tx, txImageStatus, tnc, ssdv_tx_thread

    if tnc is None:
        error_dialog = QtWidgets.QErrorMessage()
        error_dialog.showMessage('No TNC Connected!')
        error_dialog.exec_()
        return

    # Start up a thread to transmit an image
    if ssdv_tx_thread_running:
        error_dialog = QtWidgets.QErrorMessage()
        error_dialog.showMessage('Transmission in progress!')
        error_dialog.exec_()
        return

    else:
        ssdv_tx_thread = Thread(target=transmitImageThread)
        ssdv_tx_thread.start()


txImageButton.clicked.connect(transmitImage)



def abortTransmit():
    global ssdv_tx
    logging.info("Aborting current transmission.")
    ssdv_tx.abort()

abortTxButton.clicked.connect(abortTransmit)

# Callback functions for receiving packets.
def rxPacketHandler(packet):
    """ Handle a received packet """
    global ssdv_rx
    logging.debug(f"Received New Packet: {str(packet)}")

    # Add to SSDV RX object
    if ssdv_rx:
        _resp = ssdv_rx.addPacket(packet)
        
        if _resp:
            if _resp['type'] == 'image_update':
                # Try and writeout the current image.
                _outfile = ssdv_rx.decode(_resp['latest'])

                if _outfile:
                    _status = f"Callsign: {_resp['latest']['callsign']}, ID: {_resp['latest']['id']}, Size: {_resp['latest']['width']}x{_resp['latest']['height']}px, Packets: {len(_resp['latest']['packets'])}, Missing: {len(_resp['latest']['missing'])}"

                    image_update_queue.put_nowait(
                        {'filename': _outfile,
                        'status': _status})
                    


def rxPacketLoop():
    """ Pass on a received packet to rxPacketHandler """
    global tnc
    tnc.read(callback=rxPacketHandler)


# TNC Connect Function.
def connectTNC():
    """ Attempt to Connect to a TCP KISS TNC """
    global tncHostEntry, tncPortEntry, tncStatusLabel, tnc, ssdv_rx_thread
    _host = tncHostEntry.text()
    _port = int(tncPortEntry.text())

    try:
        tnc = kissfix.TCPKISS(host=_host, port=_port)
        tnc.start()
    except Exception as e:
        _error = f"Could not connect to TNC: {str(e)}"
        logging.error(_error)
        tncStatusLabel.setText(_error)
        return
    
    # Connected! Start up RX thread.
    ssdv_rx_thread = Thread(target=rxPacketLoop)
    ssdv_rx_thread.start()

    _status = f"Connected: {_host}:{_port}"
    tncStatusLabel.setText(_status)
    logging.info(_status)

tncConnectButton.clicked.connect(connectTNC)


# GUI Image Update Loop
def updateImageDisplay():
    """ Read in data from the image update queue, and update the image display and status """
    global image_update_queue, rxImageStatus

    while image_update_queue.qsize() > 0:
        _data = image_update_queue.get()

        changeImage(_data['filename'])
        rxImageStatus.setText(_data['status'])


image_update_timer = QtCore.QTimer()
image_update_timer.timeout.connect(updateImageDisplay)
image_update_timer.start(250)


# Main
def main():
    # Start the Qt Loop
    if (sys.flags.interactive != 1) or not hasattr(QtCore, "PYQT_VERSION"):
        QtGui.QApplication.instance().exec_()
    
    try:
        tnc.stop()
    except:
        pass


if __name__ == "__main__":
    main()

