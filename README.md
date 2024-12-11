# VIS-FileHandler4Linux
File download, upload and preview handler for the VIS document management system [web client](https://www.pdv.de/ecm-software/vis-webclient) from PDV GmbH, unofficial Linux implementation.

The web based VIS application does not use standard web technologies for up- and downloading; a special `viscs://` url handler is needed on the client side to to upload, download and preview files.

## Installation
1. Install system-wide dependencies from Debian/Ubuntu repos.
   ```
   apt install python3-pip python3-venv python3-pyinotify libkrb5-dev
   ```

2. Create a new Python venv dir and install it with requirements which are not available in Debian/Ubuntu repos in the venv.
   ```
   python3 -m venv --system-site-packages venv
   venv/bin/pip3 install .
   ```

3. Install protocol handler, make sure that the path to `venv/bin/viscs` is correct.
   ```
   sudo cp viscs-protocol-handler.desktop /usr/share/applications
   sudo update-desktop-database
   ```

## Usage
1. Make sure you have a valid kerberos ticket using `klist`. Get a ticket if necessary with `kinit user@DOMAIN.COM`.

2. Your browser must be configured to use the kerberos ticket.
   - Chrome: policy "AuthServerAllowlist"
   - Firefox: policy "Authentication": {"SPNEGO": ["domain.com"]} or setting `network.negotiate-auth.trusted-uris` in "about:config"

3. Open a browser in terminal and navigate to the web client. Start a download and have a look at the output on the command line for debugging. A desktop notification will appear informing you about the current file handler background activity.

   Note: When editing a file, the file monitoring will be cancelled as soon as the desktop notification is closed. Make sure that the notification is visible until you finished editing your document. If you closed the notification accidentally, you can still upload the file manually.
