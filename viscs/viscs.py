#!/bin/python3

import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify, GLib

from urllib.parse import urlparse, parse_qs, unquote, quote_plus
import urllib.request
import urllib_kerberos

from datetime import datetime
import hashlib
import pyinotify
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
APP_NAME        = 'VIS File Handler'
PROTOCOL_SCHEME = 'viscs:'
DOWNLOAD_DIR    = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)


class FileChangedHandler(pyinotify.ProcessEvent):
    def my_init(self, uploadUrl, filePath, fileMd5):
        self._uploadUrl = uploadUrl
        self._filePath = os.path.abspath(filePath)
        self._fileMd5 = fileMd5

    # IN_CLOSE to support Softmaker Office
    # (Does not modify the file but creates a temporary file, then deletes
    # the original and renames the temp file to the original file name.
    # That's why IN_MODIFY is not called.)
    def process_IN_CLOSE_WRITE(self, event):
        self.process_IN_MODIFY(event=event)

    # IN_MODIFY to support LibreOffice
    # (LibreOffice modifies the file directly.)
    def process_IN_MODIFY(self, event):
        if(self._filePath == event.pathname):
            newFileMd5 = md5(event.pathname)
            if(self._fileMd5 == newFileMd5):
                print('['+event.pathname+'] file content not changed, ignoring')
            else:
                print('['+event.pathname+'] file content changed, omg we need to upload the file!')
                self._fileMd5 = newFileMd5
                UploadFile(self._filePath, self._uploadUrl)

def md5(fname):
    hash = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash.update(chunk)
    return hash.hexdigest()

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

def UploadFile(filePath, uploadPath):
    print('Upload:', filePath, ' -> ', uploadPath)
    with open(filePath, 'rb') as file:
        try:
            # re-apply kerberos settings - dunno why this is necessary after previous GET/PROPFIND request
            SetupKerberos()
            # do the WebDAV PUT request
            request = urllib.request.Request(uploadPath, data=file.read(), method='PUT')
            urllib.request.urlopen(request)#.getcode()

        except Exception as e:
            # currently, there is an issue in urllib_kerberos, causing an error on success status code 201 (= Webdav file created) - we ignore this error here
            # https://github.com/willthames/urllib_kerberos/issues/3
            pass

        notificationFinished = Notify.Notification.new('Datei wurde in VIS hochgeladen', filePath)
        notificationFinished.show()

def GuessEncodingAndDecode(textBytes, codecs=['utf-8', 'cp1252', 'cp850']):
    for codec in codecs:
        try:
            return textBytes.decode(codec)
        except UnicodeDecodeError: pass
    return textBytes.decode(sys.stdout.encoding, 'replace') # fallback: replace invalid characters

def ParseFachverteiler(responseBody):
    csvContent   = ''
    csvSeparator = ';'
    for row in responseBody.split(b'\x02'):
        columns = []
        for field in row.split(b'\x01'):
            columns.append('"'+GuessEncodingAndDecode(field).replace('"', '\\"')+'"')
        csvContent += csvSeparator.join(columns) + "\r\n"
    return csvContent

def main():
    Notify.init(APP_NAME)
    urlToHandle = None

    # check parameter
    for arg in sys.argv:
        if(arg.startswith(PROTOCOL_SCHEME)):
            urlToHandle = arg
    if(urlToHandle == None):
        print('Error: no valid »%s« scheme parameter given.' % PROTOCOL_SCHEME)
        exit(1)

    try:
        # parse viscs:// url
        parsed = urlparse(urlToHandle)
        parameters = parse_qs(parsed.query)

        # init kerberos
        SetupKerberos()

        # handle preview links
        if('fileUrl' in parameters):
            sourcePath = parameters['fileUrl'][0].replace(' ', '%20')
            targetPath = DOWNLOAD_DIR+'/'+os.path.basename(unquote(parameters['fileUrl'][0]))
            print('Open:', sourcePath, ' -> ', targetPath)
            urllib.request.urlretrieve(sourcePath, targetPath)
            subprocess.run(['xdg-open', targetPath])
            notificationFinished = Notify.Notification.new('Datei wurde aus VIS geöffnet', targetPath)
            notificationFinished.show()

            # set up file watcher
            wm = pyinotify.WatchManager()
            wm.add_watch(DOWNLOAD_DIR, pyinotify.IN_MODIFY | pyinotify.IN_CLOSE_WRITE)
            notifier = pyinotify.ThreadedNotifier(wm,
                FileChangedHandler(
                    filePath = targetPath,
                    uploadUrl = sourcePath,
                    fileMd5 = md5(targetPath)
                )
            )
            notifier.start()
            print('File watcher is now active!')
            print()

        # handle up-/downloads
        elif('transferQueueServlet' in parameters):
            transferQueueServlet = parameters['transferQueueServlet'][0]+'&transferQueueKey='+quote_plus(parameters['transferQueueKey'][0])

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

                    # upload it
                    UploadFile(fileName, uploadPath)

                # assign upload to transfer queue - not truly necessary, but makes the uploaded file directly visible on the website without manual refresh
                headers = {'Content-Type':''} # urllib's default content type "application/x-www-form-urlencoded" confuses the VIS server
                fileBaseNames = []
                for fileName in fileNames:
                    fileBaseNames.append(os.path.basename(fileName))
                postUrl = transferQueueServlet+'&uploadToTransferQueue=true&mandant='+quote_plus(parameters['mandant'][0])
                postData = bytes('\x09'.join(fileBaseNames),'utf-8')+b'\x09' # file names, separated and finalized by 0x09, WTF
                print('Transfer Queue Assignment:', postUrl, ' -> ', postData)
                print()
                request = urllib.request.Request(postUrl, data=postData, method='POST', headers=headers)
                urllib.request.urlopen(request)#.getcode()

            # download file info
            print('Get File Info:', transferQueueServlet)
            response = urllib.request.urlopen(transferQueueServlet)
            responseBody = response.read()
            resultRows = responseBody.split(b'\x02')

            if(len(resultRows) > 1 and resultRows[0] == b'1'):
                # congratulations, it's a file download
                downloadedFiles = []
                for fileInfos in responseBody.split(b'\x01'):
                    metadata = fileInfos.split(b'\x02')
                    if(len(metadata) < 4): continue
                    sourcePath = metadata[1].decode('utf-8')
                    targetPath = DOWNLOAD_DIR+'/'+metadata[3].decode('utf-8').strip()
                    print('Download:', sourcePath, ' -> ', targetPath)
                    urllib.request.urlretrieve(sourcePath, targetPath)
                    downloadedFiles.append(targetPath)
                if(len(downloadedFiles) > 0):
                    notificationFinished = Notify.Notification.new('Datei wurde aus VIS heruntergeladen', "\n".join(downloadedFiles))
                    #notificationFinished.add_action('clicked', 'Öffnen', openFile)
                    notificationFinished.show()

            elif(len(resultRows) > 1):
                # congratulations, it's a Fachverteilerexport :))
                csvContent = ParseFachverteiler(responseBody)
                now = datetime.now()
                targetPath = DOWNLOAD_DIR+'/export-'+now.strftime('%Y-%m-%d--%H-%M')+'.csv'
                print('Target Path:', targetPath)
                with open(targetPath, 'w') as f:
                    f.write(csvContent)
                    notificationFinished = Notify.Notification.new('Fachverteilerexport wurde gespeichert', targetPath)
                    #notificationFinished.add_action('clicked', 'Öffnen', openFile)
                    notificationFinished.show()

            print()


        # end event - this closes the "Please Wait..." window
        if('eventServlet' in parameters):
            endEventServlet = parameters['eventServlet'][0]+'&EventID=endcmd&EventMsg=0&formID='+quote_plus(parameters['de.pdv.visj.WEBSTART_FORMID'][0])
            response = urllib.request.urlopen(endEventServlet)
            print('End Event:', endEventServlet, ' -> ', response.getcode())
            print()

        print('Finished. Thank you and goodbye.', "\n")
        print()

    except Exception as e:
        print(traceback.format_exc())
        notificationFinished = Notify.Notification.new('VIS File Handler Fehler', str(e))
        notificationFinished.show()

if __name__ == '__main__':
    main()
