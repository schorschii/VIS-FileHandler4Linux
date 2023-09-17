#!/bin/python3

import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify
from gi.repository import GLib
from urllib.parse import urlparse
from urllib.parse import parse_qs
from urllib.parse import quote_plus
import urllib.request
import urllib_kerberos
import subprocess
import traceback
import sys, os

# gtk2 theme is more convenient when it comes to
# selecting files from network shares using QFileDialog (on linux)
if os.environ.get('QT_QPA_PLATFORMTHEME') == 'qt5ct':
	os.environ['QT_QPA_PLATFORMTHEME'] = 'gtk2'
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from locale import getdefaultlocale

APP             = QApplication(sys.argv)
APP_NAME        = "VIS File Handler"
PROTOCOL_SCHEME = "viscs:"
DOWNLOAD_DIR    = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)


def OpenFileDialog(title, filter):
    fileNames, _ = QFileDialog.getOpenFileNames(None, title, None, filter)
    return fileNames

def WarningDialog(title, text):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    return (msg.exec_() == QMessageBox.Yes)

def SetupKerberos():
    handlers = [urllib_kerberos.HTTPKerberosAuthHandler()]
    opener = urllib.request.build_opener(*handlers)
    urllib.request.install_opener(opener)

def main():
    Notify.init(APP_NAME)
    urlToHandle = None

    # check parameter
    for arg in sys.argv:
        if(arg.startswith(PROTOCOL_SCHEME)):
            urlToHandle = arg
    if(urlToHandle == None):
        print("Error: no valid '"+PROTOCOL_SCHEME+"' scheme parameter given.")
        exit(1)

    try:
        # parse viscs:// url
        parsed = urlparse(urlToHandle)
        parameters = parse_qs(parsed.query)

        # kerberos setup
        SetupKerberos()

        # handle preview links
        if('fileUrl' in parameters):
            sourcePath = parameters['fileUrl'][0].replace(' ', '%20')
            targetPath = DOWNLOAD_DIR+'/'+os.path.basename(parameters['fileUrl'][0])
            print('Open URL     :', sourcePath)
            print('Target Path  :', targetPath)
            print()
            urllib.request.urlretrieve(sourcePath, targetPath)
            subprocess.run(['xdg-open', targetPath])
            notificationFinished = Notify.Notification.new('Datei wurde aus VIS geöffnet', targetPath)
            notificationFinished.show()

        # handle up-/downloads
        elif('transferQueueServlet' in parameters):
            transferQueueServlet = parameters['transferQueueServlet'][0]+'&transferQueueKey='+quote_plus(parameters['transferQueueKey'][0])
            eventServlet = parameters['eventServlet'][0]

            # upload selected shit if requested
            if('uploadPath' in parameters):
                fileNames = OpenFileDialog('VIS File Upload', 'All Files (*.*)')
                for fileName in fileNames:
                    uploadPath = parameters['uploadPath'][0]+'/'+quote_plus(os.path.basename(fileName))

                    # check if file already exists and show warning
                    try:
                        # due to the urllib_kerberos bug mentioned below, we currently cannot use PROPFIND here, which would be more performant since it does not download the file
                        request = urllib.request.Request(uploadPath, method='GET')
                        if(urllib.request.urlopen(request).getcode() == 200
                        and not WarningDialog('Dateikonflikt', 'Die Datei »%s« existiert bereits. Überschreiben?' % os.path.basename(fileName))):
                            continue
                    except Exception as e:
                        # HTTPError 404 means no file exists with this name -> we can upload it without questions
                        pass

                    # open file and upload it
                    print('Source Path :', fileName)
                    print('Upload URL  :', uploadPath)
                    print()
                    with open(fileName,'rb') as file:
                        try:
                            # re-apply kerberos settings - dunno why this is necessary after previous GET/PROPFIND request
                            SetupKerberos()
                            # currently, there is an issue in urllib_kerberos, causing an error on success status code 201 (= Webdav file created) - we ignore this error here
                            # https://github.com/willthames/urllib_kerberos/issues/3
                            request = urllib.request.Request(uploadPath, data=file.read(), method='PUT')
                            urllib.request.urlopen(request)#.getcode()
                        except Exception as e: pass
                        notificationFinished = Notify.Notification.new('Datei wurde in VIS hochgeladen', fileName)
                        notificationFinished.show()

                # assign upload to transfer queue - not truly necessary, but makes the uploaded file directly visible on the website without manual refresh
                headers = {'Content-Type':''} # urllib's default content type "application/x-www-form-urlencoded" confuses the VIS server
                fileBaseNames = []
                for fileName in fileNames:
                    fileBaseNames.append(os.path.basename(fileName))
                postUrl = transferQueueServlet+'&uploadToTransferQueue=true&mandant='+quote_plus(parameters['mandant'][0])
                postData = bytes('\x09'.join(fileBaseNames),'utf-8')+b'\x09' # file names, separated and finalized by 0x09, WTF
                print('Transfer Queue Assignment:', postUrl, postData)
                print()
                request = urllib.request.Request(postUrl, data=postData, method='POST', headers=headers)
                urllib.request.urlopen(request)#.getcode()

            # download file info
            print('File Info URL:', transferQueueServlet)
            print()
            response = urllib.request.urlopen(transferQueueServlet)
            files = response.read().split(b'\x01')

            # download files if requested
            for fileInfos in files:
                metadata = fileInfos.split(b'\x02')
                if(len(metadata) < 4): continue
                sourcePath = metadata[1].decode('utf-8')
                targetPath = DOWNLOAD_DIR+'/'+metadata[3].decode('utf-8').strip()
                print('Download URL :', sourcePath)
                print('Target Path  :', targetPath)
                print()
                urllib.request.urlretrieve(sourcePath, targetPath)
                notificationFinished = Notify.Notification.new('Datei wurde aus VIS heruntergeladen', targetPath)
                #notificationFinished.add_action('clicked', 'Öffnen', openFile)
                notificationFinished.show()

            # end event - close "Please Wait..." window
            endEventServlet = eventServlet+'&EventID=endcmd&EventMsg=0&formID='+quote_plus(parameters['de.pdv.visj.WEBSTART_FORMID'][0])
            response = urllib.request.urlopen(endEventServlet)
            print('End Event URL:', endEventServlet, response.getcode())
            print()

        print('Finished! Thank you and goodbye.')
        print()

    except Exception as e:
        print(traceback.format_exc())
        notificationFinished = Notify.Notification.new('VIS File Handler Fehler', str(e))
        notificationFinished.show()

if __name__ == '__main__':
    main()
