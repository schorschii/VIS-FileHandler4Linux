#!/bin/python3

import gi
gi.require_version('Notify', '0.7')
gi.require_version('Gtk', '3.0')
from gi.repository import Notify, GLib, Gtk

from urllib.parse import urlparse, parse_qs, unquote, quote_plus
import urllib.request
import urllib_kerberos

from datetime import datetime
import hashlib
import pyinotify
import subprocess
import traceback
import sys, os


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
                # show notification
                notification = Notify.Notification.new('Dateien werden in VIS hochgeladen...', self._filePath)
                notification.show()
                # do upload
                UploadFile(self._filePath, self._uploadUrl)
                # update notification
                notification.update('Dateien wurden in VIS hochgeladen', self._filePath)
                notification.show()

def md5(fname):
    hash = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash.update(chunk)
    return hash.hexdigest()

def OpenFileDialog(title, filter):
    dialog1 = Gtk.FileChooserDialog(
        title = 'Bitte Dateien für VIS-Upload auswählen',
        parent = None, action = Gtk.FileChooserAction.OPEN
    )
    dialog1.add_buttons(
        Gtk.STOCK_CANCEL,
        Gtk.ResponseType.CANCEL,
        Gtk.STOCK_OPEN,
        Gtk.ResponseType.OK,
    )
    dialog1.set_select_multiple(True)
    response = dialog1.run()
    files = dialog1.get_filenames()
    dialog1.close()
    dialog1.destroy()
    if(response == Gtk.ResponseType.OK):
        return files
    else:
        return []

def WarningDialog(title, text):
    dialog = Gtk.MessageDialog(
        destroy_with_parent = True,
        text = title, secondary_text = text,
        buttons = Gtk.ButtonsType.YES_NO
    )
    response = dialog.run()
    dialog.close()
    dialog.destroy()
    return (response == Gtk.ResponseType.YES)

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

def OpenFile(notification, event):
    for path in notification.filePaths:
        print('Open Downloaded File:', path)
        subprocess.run(['xdg-open', path])
    Gtk.main_quit()

def QuitWatcher(notification, event):
    if(hasattr(notification, 'notifier')):
        notification.notifier.stop()
    Gtk.main_quit()

def NotificationClosed(notification):
    if(hasattr(notification, 'notifier')):
        notification.notifier.stop()
    Gtk.main_quit()

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

            # show info
            notification = Notify.Notification.new('Datei wurde aus VIS geöffnet', targetPath + ' wird auf Änderungen überwacht')
            notification.notifier = notifier
            notification.connect('closed', NotificationClosed)
            notification.add_action('clicked', 'Überwachung beenden', QuitWatcher)
            notification.show()

        # handle up-/downloads
        elif('transferQueueServlet' in parameters):
            transferQueueServlet = parameters['transferQueueServlet'][0]+'&transferQueueKey='+quote_plus(parameters['transferQueueKey'][0])

            # upload selected shit if requested
            if('uploadPath' in parameters):
                fileNames = OpenFileDialog('VIS File Upload', 'All Files (*.*)')

                if(len(fileNames) > 0):
                    # show notification
                    notification = Notify.Notification.new('Dateien werden in VIS hochgeladen...', "\n".join(fileNames))
                    notification.show()

                realUploads = []
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
                    realUploads.append(fileName)

                if(len(fileNames) > 0):
                    # update notification
                    fileNamesString = "\n".join(realUploads)
                    if(fileNamesString == ''):
                        notification.update('VIS-Upload abgebrochen', 'Keine Dateien')
                    else:
                        notification.update('Dateien wurden in VIS hochgeladen', fileNamesString)
                    notification.show()

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
                files = {}
                for fileInfos in responseBody.split(b'\x01'):
                    metadata = fileInfos.split(b'\x02')
                    if(len(metadata) < 4): continue
                    sourcePath = metadata[1].decode('utf-8')
                    targetPath = DOWNLOAD_DIR+'/'+metadata[3].decode('utf-8').strip()
                    files[targetPath] = sourcePath

                # show notification
                filePaths = []
                for targetPath, sourcePath in files.items():
                    filePaths.append(targetPath)
                if(len(filePaths) > 0):
                    notification = Notify.Notification.new('Dateien werden aus VIS heruntergeladen...', "\n".join(filePaths))
                    notification.filePaths = filePaths
                    notification.show()

                # execute the download(s)
                for targetPath, sourcePath in files.items():
                    print('Download:', sourcePath, ' -> ', targetPath)
                    urllib.request.urlretrieve(sourcePath, targetPath)

                # update notification
                if(len(filePaths) > 0):
                    notification.update('Dateien wurden aus VIS heruntergeladen', "\n".join(filePaths))
                    notification.connect('closed', NotificationClosed)
                    notification.add_action('clicked', 'Alle öffnen', OpenFile)
                    notification.show()

            elif(len(resultRows) > 1):
                # congratulations, it's a Fachverteilerexport :))
                csvContent = ParseFachverteiler(responseBody)
                now = datetime.now()
                targetPath = DOWNLOAD_DIR+'/export-'+now.strftime('%Y-%m-%d--%H-%M')+'.csv'
                print('Target Path:', targetPath)
                with open(targetPath, 'w') as f:
                    f.write(csvContent)
                    notification = Notify.Notification.new('Fachverteilerexport wurde gespeichert', targetPath)
                    notification.filePaths = [targetPath]
                    notification.connect('closed', NotificationClosed)
                    notification.add_action('clicked', 'Öffnen', OpenFile)
                    notification.show()

            print()

        # end event - this closes the "Please Wait..." window
        if('eventServlet' in parameters):
            endEventServlet = parameters['eventServlet'][0]+'&EventID=endcmd&EventMsg=0&formID='+quote_plus(parameters['de.pdv.visj.WEBSTART_FORMID'][0])
            response = urllib.request.urlopen(endEventServlet)
            print('End Event:', endEventServlet, ' -> ', response.getcode())
            print()

        Gtk.main()
        print('Finished. Thank you and goodbye.', "\n")
        print()

    except Exception as e:
        print(traceback.format_exc())
        notificationFinished = Notify.Notification.new('VIS File Handler Fehler', str(e))
        notificationFinished.show()

if __name__ == '__main__':
    main()
