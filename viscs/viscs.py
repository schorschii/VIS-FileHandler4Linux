#!/bin/python3

from . import __version__

from urllib.parse import urlparse, parse_qs, unquote, quote_plus
import requests
from requests_kerberos import HTTPKerberosAuth, OPTIONAL

from datetime import datetime
import hashlib
import subprocess
import traceback
import sys, os

if(sys.platform == 'win32'):
    import tkinter as tk
    from tkinter import filedialog
else:
    import gi
    gi.require_version('Notify', '0.7')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Notify, GLib, Gtk
    import pyinotify


PROTOCOL_SCHEME = 'viscs:'
DOWNLOAD_DIR    = '.'


if(sys.platform == 'win32'):
    pass
else:
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
                    print('['+event.pathname+'] file content not changed, ignoring', flush=True)
                else:
                    print('['+event.pathname+'] file content changed, omg we need to upload the file!', flush=True)
                    self._fileMd5 = newFileMd5
                    # show notification
                    notification = notify(None, 'Dateien werden in VIS hochgeladen...', self._filePath)
                    # do upload
                    UploadFile(self._filePath, self._uploadUrl)
                    # update notification
                    notify(notification, 'Dateien wurden in VIS hochgeladen', self._filePath)

def notify(notification, title, message, closedAction=None, actions=None):
    if(sys.platform == 'win32'):
        print(title, ':', message, "\n")
        return None
    else:
        if(not notification):
            notification = Notify.Notification.new(title, message)
        else:
            notification.update(title, message)
        if(closedAction):
            notification.connect('closed', closedAction)
        if(actions):
            for title, func in actions.items():
                notification.add_action('clicked', title, func)
        notification.show()
        return notification

def md5(fname):
    hash = hashlib.md5()
    with open(fname, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash.update(chunk)
    return hash.hexdigest()

def OpenFileDialog(title, filter):
    TITLE = 'Bitte Dateien für VIS-Upload auswählen'
    if(sys.platform == 'win32'):
        # tk file dialog looks horrible under Linux, so we only use it on Windows
        root = tk.Tk()
        root.withdraw()
        files = []
        for file in filedialog.askopenfilenames(title=TITLE):
            files.append(file)
        return files
    else:
        dialog1 = Gtk.FileChooserDialog(title=TITLE, parent=None, action=Gtk.FileChooserAction.OPEN)
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

def UploadFile(filePath, uploadPath):
    print('Upload:', filePath, ' -> ', uploadPath, flush=True)
    with open(filePath, 'rb') as file:
        # do the WebDAV PUT request
        r = requests.put(uploadPath, data=file, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
        r.raise_for_status()

def ParseFachverteiler(responseBody):
    csvContent   = ''
    csvSeparator = ';'
    for row in responseBody.split('\x02'):
        columns = []
        for field in row.split('\x01'):
            columns.append('"'+field.replace('"', '\\"')+'"')
        csvContent += csvSeparator.join(columns) + "\r\n"
    return csvContent

def OpenFile(notification, event):
    for path in notification.filePaths:
        print('Open Downloaded File:', path, flush=True)
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

def getTargetPath(downloadDir, fileName):
    testName = downloadDir + '/' + fileName
    if(not os.path.isfile(testName)):
        return testName
    print('Already exists:', testName, ' - appending a number...', flush=True)

    fileParts = fileName.rsplit('.', 1)
    fileName = fileParts[0]
    fileExt = ''
    if(len(fileParts) > 1): fileExt = fileParts[1]

    counter = 0
    while True:
        counter += 1
        testName = downloadDir + '/' + fileName + ' ('+str(counter)+')' + '.' + fileExt
        if(not os.path.isfile(testName)):
            return testName
        print('Already exists:', testName, ' - trying next number...', flush=True)

def main():
    try:
        print('Welcome to the VIS-FileHandler4Linux '+__version__+', inofficial Linux port (c) Georg Sieber 2024', flush=True)

        # init notifications, Linux only
        try:
            Notify.init('VIS File Handler')
        except NameError as e:
            print(str(e), flush=True)

        # check parameter
        urlToHandle = None
        for arg in sys.argv:
            if(arg.startswith(PROTOCOL_SCHEME)):
                urlToHandle = arg
        if(urlToHandle == None):
            raise Exception('No valid »%s« scheme parameter given, I don\'t know what to do.' % PROTOCOL_SCHEME)

        # find download dir
        if(sys.platform == 'win32'):
            from pathlib import Path
            DOWNLOAD_DIR = str(os.path.join(Path.home(), 'Downloads'))
        else:
            DOWNLOAD_DIR = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)

        # parse viscs:// url
        parsed = urlparse(urlToHandle)
        parameters = parse_qs(parsed.query)

        # handle preview links
        if('fileUrl' in parameters):
            sourcePath = parameters['fileUrl'][0].replace(' ', '%20')
            targetPath = getTargetPath(DOWNLOAD_DIR, os.path.basename(unquote(parameters['fileUrl'][0])))
            print('Open:', sourcePath, ' -> ', targetPath, flush=True)
            r = requests.get(sourcePath, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
            r.raise_for_status()
            with open(targetPath, 'wb') as fd:
                fd.write(r.content)

            if(sys.platform == 'win32'):
                os.startfile(targetPath)
            else:
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
                print('File watcher is now active!', flush=True)
                print(flush=True)

            # show info
            notification = notify(None,
                'Datei wurde aus VIS geöffnet',
                targetPath + ' wird auf Änderungen überwacht',
                NotificationClosed,
                {'Überwachung beenden': QuitWatcher}
            )
            if(notification): notification.notifier = notifier

        # handle up-/downloads
        elif('transferQueueServlet' in parameters):
            transferQueueServlet = parameters['transferQueueServlet'][0]+'&transferQueueKey='+quote_plus(parameters['transferQueueKey'][0])

            # upload selected shit if requested
            if('uploadPath' in parameters):
                fileNames = OpenFileDialog('VIS File Upload', 'All Files (*.*)')

                if(len(fileNames) > 0):
                    # show notification
                    notification = notify(None, 'Dateien werden in VIS hochgeladen...', "\n".join(fileNames))

                realUploads = []
                for fileName in fileNames:
                    uploadPath = parameters['uploadPath'][0]+'/'+quote_plus(os.path.basename(fileName))
                    # check if file already exists and show warning
                    r = requests.request('PROPFIND', url=uploadPath, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
                    print('Check if file exists:', uploadPath, ' - ', r.status_code)
                    print(flush=True)
                    if((r.status_code >= 200 and r.status_code <= 299)
                    and not WarningDialog('Dateikonflikt', 'Die Datei »%s« existiert bereits. Überschreiben?' % os.path.basename(fileName))):
                        continue
                    # upload it
                    UploadFile(fileName, uploadPath)
                    realUploads.append(fileName)

                if(len(fileNames) > 0):
                    # update notification
                    fileNamesString = "\n".join(realUploads)
                    if(fileNamesString == ''):
                        notify(notification, 'VIS-Upload abgebrochen', 'Keine Dateien')
                    else:
                        notify(notification, 'Dateien wurden in VIS hochgeladen', fileNamesString)

                # assign upload to transfer queue - not truly necessary, but makes the uploaded file directly visible on the website without manual refresh
                headers = {'Content-Type':''} # urllib's default content type "application/x-www-form-urlencoded" confuses the VIS server
                fileBaseNames = []
                for fileName in fileNames:
                    fileBaseNames.append(os.path.basename(fileName))
                postUrl = transferQueueServlet+'&uploadToTransferQueue=true&mandant='+quote_plus(parameters['mandant'][0])
                postData = bytes('\x09'.join(fileBaseNames),'utf-8')+b'\x09' # file names, separated and finalized by 0x09, WTF
                print('Transfer Queue Assignment:', postUrl, ' -> ', postData, flush=True)
                print(flush=True)
                r = requests.post(postUrl, data=postData, headers=headers, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
                r.raise_for_status()

            # download file info
            print('Get File Info:', transferQueueServlet, flush=True)
            r = requests.get(transferQueueServlet, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
            r.raise_for_status()
            responseBody = r.text
            resultRows = responseBody.split('\x02')

            if(len(resultRows) > 1 and resultRows[0] == '1'):
                # congratulations, it's a file download
                files = {}
                for fileInfos in responseBody.split('\x01'):
                    metadata = fileInfos.split('\x02')
                    if(len(metadata) < 4): continue
                    sourcePath = metadata[1]
                    targetPath = DOWNLOAD_DIR+'/'+metadata[3].strip()
                    files[targetPath] = sourcePath

                # show notification
                filePaths = []
                for targetPath, sourcePath in files.items():
                    filePaths.append(targetPath)
                if(len(filePaths) > 0):
                    notification = notify(None, 'Dateien werden aus VIS heruntergeladen...', "\n".join(filePaths))
                    if(notification): notification.filePaths = filePaths

                # execute the download(s)
                for targetPath, sourcePath in files.items():
                    print('Download:', sourcePath, ' -> ', targetPath, flush=True)
                    r = requests.get(sourcePath, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
                    r.raise_for_status()
                    with open(targetPath, 'wb') as fd:
                        fd.write(r.content)

                # update notification
                if(len(filePaths) > 0):
                    notify(notification,
                        'Dateien wurden aus VIS heruntergeladen',
                        "\n".join(filePaths),
                        NotificationClosed,
                        {'Alle öffnen': OpenFile}
                    )

            elif(len(resultRows) > 1):
                # congratulations, it's a Fachverteilerexport :))
                csvContent = ParseFachverteiler(responseBody)
                now = datetime.now()
                targetPath = DOWNLOAD_DIR+'/export-'+now.strftime('%Y-%m-%d--%H-%M')+'.csv'
                print('Target Path:', targetPath, flush=True)
                with open(targetPath, 'w') as f:
                    f.write(csvContent)
                    notification = notify(None,
                        'Fachverteilerexport wurde gespeichert',
                        targetPath,
                        NotificationClosed,
                        {'Öffnen': OpenFile}
                    )
                    if(notification): notification.filePaths = [targetPath]

            print(flush=True)

        # end event - this closes the "Please Wait..." window
        if('eventServlet' in parameters):
            endEventServlet = parameters['eventServlet'][0]+'&EventID=endcmd&EventMsg=0&formID='+quote_plus(parameters['de.pdv.visj.WEBSTART_FORMID'][0])
            r = requests.get(endEventServlet, auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL))
            print('End Event:', endEventServlet, ' - ', r.status_code, flush=True)
            print(flush=True)

        # start Gtk GUI mainloop, Linux only
        try:
            Gtk.main()
        except NameError as e:
            print(str(e), flush=True)

        print('Finished. Thank you and goodbye..', "\n", flush=True)
        print(flush=True)

    except Exception as e:
        print(traceback.format_exc(), flush=True)
        if(sys.platform == 'win32'): input()
        notify(None, 'VIS File Handler Fehler', str(e))

if __name__ == '__main__':
    main()
