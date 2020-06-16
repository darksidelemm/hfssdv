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
from .packets import *
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

image_store = {}
latest_image = None



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
saveImageButton = QtGui.QPushButton("Save Image")

# Layout
w2.addWidget(rxImageList,0,0,1,1)
w2.addWidget(resendButton,1,0,1,1)
w2.addWidget(saveImageButton,2,0,1,1)

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


def updateImageList():
    """ Update the Image list based on data from an image store dict """
    global rxImageList, image_store

    # Get current selection
    _selection = rxImageList.currentItem()
    if _selection:
        _selected_text = _selection.text()
    else:
        _selected_text = None
    
    # Clear list and re-populate from image store.
    rxImageList.clear()
    
    _callsigns = list(image_store.keys())
    _callsigns.sort()

    for _call in _callsigns:
        _images = list(image_store[_call].keys())
        _images.sort()

        for _img in _images:
            _width = image_store[_call][_img]['width']
            _height = image_store[_call][_img]['height']
            _entry = f"{_call}, {_img}, {_width}x{_height}"
            rxImageList.addItem(_entry)
    

    rxImageList.addItem('Latest')

    # Iterate through the list and select the item which was previously selected
    if _selected_text:
        for i in range(rxImageList.count()):
            if rxImageList.item(i).text() == _selected_text:
                rxImageList.setCurrentRow(i)



# Callback functions for receiving packets.
def rxPacketHandler(packet):
    """ Handle a received packet """
    global ssdv_rx, image_store, latest_image
    logging.debug(f"Received New Packet: {str(packet)}")

    # Add to SSDV RX object
    if ssdv_rx:
        _resp = ssdv_rx.addPacket(packet)
        
        if _resp:
            if _resp['type'] == 'image_update':
                # Try and writeout the current image.
                _outfile = ssdv_rx.decode(_resp['latest'])

                image_store = _resp['store']
                latest_image = _resp['latest']

                if _outfile:
                    _status = f"Callsign: {_resp['latest']['callsign']}, ID: {_resp['latest']['id']}, Size: {_resp['latest']['width']}x{_resp['latest']['height']}px, Packets: {len(_resp['latest']['packets'])}, Missing: {len(_resp['latest']['missing'])}"

                    image_update_queue.put_nowait(
                        {'filename': _outfile,
                        'status': _status})
            elif _resp['type'] == 'resend':
                status_update_queue.put_nowait(
                    _resp
                )
                    

def rxPacketLoop():
    """ Pass on a received packet to rxPacketHandler """
    global tnc
    tnc.read(callback=rxPacketHandler)


def saveImage():
    """ Save a selected image to a file. """
    global rxImageList, image_store, latest_image

    # Get current selection
    _selection = rxImageList.currentItem()
    if _selection:
        _selected_text = _selection.text()
    else:
        _selected_text = None

    if _selected_text:
        if _selected_text == 'Latest':
            if latest_image:
                _outimg = latest_image
            else:
                return
        elif _selected_text == 'No Images':
            return
        else:
            # Determine image based on call and ID
            _fields = _selected_text.split(',')
            _call = _fields[0]
            _id = int(_fields[1])

            _outimg = image_store[_call][_id]
        
        _filename = f"./{_outimg['time']}_{_outimg['callsign']}_{_outimg['id']}.jpg"

        # Prompt for save location
        fname = QtWidgets.QFileDialog.getSaveFileName(None,'Save Image',_filename,"Image files (*.jpg *.jpeg)")

        if fname[0] != "":
            _filename = fname[0]

            # Decode and save file!
            if ssdv_rx.decode(_outimg, outfile=_filename):
                logging.info(f"Saved image to {_filename}")
            else:
                logging.error("Could not save image.")


saveImageButton.clicked.connect(saveImage)


def requestResend():
    global rxImageList, userCallEntry, image_store, latest_image, tnc

    # Get current selection
    _selection = rxImageList.currentItem()
    if _selection:
        _selected_text = _selection.text()
    else:
        _selected_text = None

    if _selected_text:
        if _selected_text == 'Latest':
            if latest_image:
                _outimg = latest_image
            else:
                return
        elif _selected_text == 'No Images':
            return
        else:
            # Determine image based on call and ID
            _fields = _selected_text.split(',')
            _call = _fields[0]
            _id = int(_fields[1])

            _outimg = image_store[_call][_id]

        _mycall = userCallEntry.text()
        _theircall = _outimg['callsign']
        _id = _outimg['id']
        _lastpacket = max(list(_outimg['packets'].keys()))
        _missing = _outimg['missing']

        _resend_packet = encode_resend_packet(_theircall, _mycall, _id, _lastpacket, _missing)

        if tnc:
            tnc.write(_resend_packet)

resendButton.clicked.connect(requestResend)

resend_image_info = None

def handleStatusUpdate(data):
    """ Handle a status update message """
    global ssdv_tx, tnc, userCallEntry, resend_image_info
    if (data['type'] == 'resend'):
        # Someone else has requested a resend of parts of an image.

        # Check re-send request is for us.
        _call = data['data']['dst_call']
        if _call != userCallEntry.text():
            logging.info(f"Got Resend request for {_call}, discarding.")
            return

        _src_call = data['data']['src_call']
        _img_id = data['data']['img_id']
        _last_pkt = data['data']['last_packet']
        _missing = data['data']['missing']

        # Check if we have image data to resend.
        _resend_list = ssdv_tx.check_resend_ability(_img_id, _last_pkt, _missing)

        if _resend_list:
            # Check with the user to confirm resend.
            msgBox = QtWidgets.QMessageBox()
            msgBox.setText(f"Re-send {len(_resend_list)} packets of Image {_img_id} to {_src_call}?")
            msgBox.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msgBox.setDefaultButton(QtWidgets.QMessageBox.No)
            reply = msgBox.exec_()
            if reply == QtWidgets.QMessageBox.No:
                return
            else:
                # Resend.
                resend_image_info = {'img_id': _img_id, 'packets':_resend_list}
                if tnc is None:
                    error_dialog = QtWidgets.QErrorMessage()
                    error_dialog.showMessage('No TNC Connected!')
                    error_dialog.exec_()
                    return

                # Start up a thread to transmit an image
                if ssdv_tx_thread_running:
                    error_dialog = QtWidgets.QErrorMessage()
                    error_dialog.showMessage('Transmission already in progress!')
                    error_dialog.exec_()
                    return

                else:
                    ssdv_tx_thread = Thread(target=resendImageThread)
                    ssdv_tx_thread.start()

        else:
            logging.info(f"Received resend request for img ID {_img_id}, but not in database.")


def resendImageThread():
    global ssdv_tx, txImageStatus, tnc, resend_image_info

    ssdv_tx_thread_running = True

    if resend_image_info:
        try:
            _delay = int(packetDelayEntry.text())
            _callback = txImageStatus.setText
            ssdv_tx.transmit_image_subset(
                image_id=resend_image_info['img_id'],
                packets=resend_image_info['packets'],
                tnc=tnc,
                delay=_delay,
                status_callback=_callback
            )
        except Exception as e:
            _error = f"Error sending image: {str(e)}"
            logging.error(_error)

    resend_image_info = None
    ssdv_tx_thread_running = False





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
def processQueues():
    """ Read in data from the queues, this decouples the GUI and async inputs somewhat. """
    global image_update_queue, status_update_queue, rxImageStatus

    while image_update_queue.qsize() > 0:
        _data = image_update_queue.get()

        changeImage(_data['filename'])
        rxImageStatus.setText(_data['status'])

        updateImageList()

    while status_update_queue.qsize() > 0:
        handleStatusUpdate(status_update_queue.get())


image_update_timer = QtCore.QTimer()
image_update_timer.timeout.connect(processQueues)
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


