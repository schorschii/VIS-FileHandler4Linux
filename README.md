# VIS-FileHandler4Linux
File download, upload and preview handler for the VIS document management system [web client](https://www.pdv.de/ecm-software/vis-webclient) from PDV GmbH, unofficial Linux implementation.

The web based VIS application does not use standard web technologies for up- and downloading; a special `viscs://` url handler is needed on the client side to to upload, download and preview files.

## Installation
```
pip3 install -r requirements.txt
sudo cp viscs.py /usr/bin/viscs
sudo cp viscs-protocol-handler.desktop /usr/share/applications
sudo update-desktop-database
google-chrome # open web client and start a download, have a look at the output on the command line for debugging
```
