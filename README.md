# VIS-FileHandler4Linux
File download, upload and preview handler for the VIS document management system [web client](https://www.pdv.de/ecm-software/vis-webclient) from PDV GmbH, unofficial Linux implementation.

The web based VIS application does not use standard web technologies for up- and downloading; a special `viscs://` url handler is needed on the client side to to upload, download and preview files.

## Installation
```
# install system-wide dependencies from Debian/Ubuntu repos
apt install python3-pip python3-venv python3-pyinotify

# create a new Python venv dir
python3 -m venv --system-site-packages venv

# install it with requirements which are not available in Debian/Ubuntu repos in the venv
venv/bin/pip3 install .

# install protocol handler, make sure that the path to `venv/bin/viscs` is correct
sudo cp viscs-protocol-handler.desktop /usr/share/applications
sudo update-desktop-database
```

## Usage
```
# make sure you have a valid kerberos ticket
klist

# get a ticket if necessary
kinit user@DOMAIN.COM

# your browser must be configured to redirect the kerberos ticket (policy "AuthServerAllowlist" in Chrome, "Authentication": {"SPNEGO": ["domain.com"]} in Firefox)
# open web client and start a download, have a look at the output on the command line for debugging
google-chrome
```
