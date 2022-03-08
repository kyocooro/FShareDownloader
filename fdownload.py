#!/usr/bin/python3
from __future__ import print_function

#from apiclient import errors
from colorama import init,Fore,Back,Style
from termcolor import colored
from tqdm import tqdm
from requests.exceptions import HTTPError
import os.path
from os import path
import configparser 
import os
import sys
import requests
import re
import json
import math
import string

from hyper import HTTPConnection

# Requires: get_fshare requests  lxml  hyper apiclient colorama termcolor tqdm
# Debian package: python3-lxml
# libxml2 libxslt

# Main FShare URLs
FShare_File_URL = 'https://www.fshare.vn/file/'
FShare_Folder_URL = 'https://www.fshare.vn/folder/'
re_folder_pattern = r"(https://www\.fshare\.vn/folder/)([^\?]+)(?:(\?.*))?"
re_folder_name_pattern = r"(.*/)(.*)"
File_Indicator = '/file/'
Folder_Indicator = '/folder/'
Folder_Reference_Filename = "Folder_Information.txt"

CONFIG_FILE = "credentials.ini"

service=''


class FSAPI:
    """
    API Interface of Fshare.vn
    """
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.token = ''
        self.s = requests.Session()
        self.s.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0'

    def login(self):
        conn = HTTPConnection('api.fshare.vn:443')
        data = {
            'user_email': self.email,
            'password': self.password,
            'app_key': "L2S7R6ZMagggC5wWkQhX2+aDi467PPuftWUMRFSn"
        }
        login_request = conn.request('POST', '/api/user/login/', body=json.dumps(data), headers=self.s.headers)
        response = conn.get_response(login_request)
        login_data = json.loads(response.read().decode('utf-8'))

        self.token = login_data['token']
        cookie = login_data['session_id']
        self.s.cookies.set('session_id', cookie)
        return data

    def profile(self):
        r = self.s.get('https://api.fshare.vn/api/user/get')
        return r.json()

    def check_valid(self, url):
        url = url.strip()
        if not url.startswith('https://www.fshare.vn/'):
            raise Exception("Must be Fshare url")
        return url

    def download(self, url, password=None):
        url = self.check_valid(url)
        payload = {
            'token': self.token,
            'url': url
        }
        if password:
            payload['password'] = password

        r = self.s.post(
            'https://api.fshare.vn/api/session/download',
            json=payload
        )

        if r.status_code == 403:
            raise Exception("Password invalid")

        if r.status_code != 200:
            raise Exception("Link is dead")

        data = r.json()
        link = data['location']
        return link

    def get_folder_urls(self, url, page=0, limit=60):
        url = self.check_valid(url)
        r = self.s.post(
            'https://api.fshare.vn/api/fileops/getFolderList',
            json={
                'token': self.token,
                'url': url,
                'dirOnly': 0,
                'pageIndex': page,
                'limit': limit
            }
        )
        data = r.json()
        return data

    def get_home_folders(self):
        r = self.s.get('https://api.fshare.vn/api/fileops/list?pageIndex=0&dirOnly=0&limit=60')
        return r.json()

    def get_file_info(self, url):
        url = self.check_valid(url)
        r = self.s.post(
            'https://api.fshare.vn/api/fileops/get',
            json={
                'token': self.token,
                'url': url,
            }
        )
        print(str(self.s.cookies) + url)
        return r.json()

    def upload(self, local_path, remote_path, secured=1):
        import os
        import io
        import ntpath
        import unidecode
        file_name = ntpath.basename(local_path)
        def format_filename(s):
            valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
            filename = ''.join(c for c in s if c in valid_chars)
            return filename
        file_name = format_filename(unidecode.unidecode(file_name))
        file_size = str(os.path.getsize(local_path))
        try:
            data = io.open(local_path, 'rb', buffering=25000000)
        except FileNotFoundError:
            raise Exception('File does not exist!')

        r = self.s.post(
            'https://api.fshare.vn/api/session/upload',
            json={
                'token': self.token,
                'name': file_name,
                'path': remote_path,
                'secured': 1,
                'size': file_size
            }
        )
        print(self.token, local_path, remote_path)
        print(r.json())

        location = r.json()['location']

        # OPTIONS for chunk upload configuration
        max_chunk_size = 25000000
        chunk_total = math.ceil(int(file_size)/max_chunk_size)

        for i in range(chunk_total):
            chunk_number = i + 1
            sent = last_index = i * max_chunk_size
            remaining = int(file_size) - sent
            if remaining < max_chunk_size:
                current_chunk = remaining
            else:
                current_chunk = max_chunk_size

            next_index = last_index + current_chunk

            chunk_params = {
                'flowChunkNumber': chunk_number,
                'flowChunkSize': max_chunk_size,
                'flowCurrentChunkSize': current_chunk,
                'flowTotalSize': file_size,
                'flowIdentifier': '{0}-{1}'.format(current_chunk, file_name),
                'flowFilename': file_name,
                'flowRelativePath': file_name,
                'flowTotalChunks': chunk_total
            }

            res = self.s.options(location, params=chunk_params)
            # POST upload data
            headers = {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Range': 'bytes {0}-{1}/{2}'.format(
                    last_index,
                    next_index - 1,
                    file_size),
                'DNT': '1',
                'Connection': 'keep-alive'
            }
            res = self.s.post(location,
                              params=chunk_params,
                              headers=headers,
                              data=data.read(max_chunk_size))
            try:
                if res.json():
                    return res.json()
                pass
            except Exception:
                pass
        data.close()


def main():
    splash_screen()
    print(colored('Loading configuration...','white'))
    login_credential = configuration_read(CONFIG_FILE)
    print(colored('Login...','white'))
    login_status = perform_login(login_credential)

    if login_status:
        print(colored('Logged in successfully!','white'))
    else:
        print(colored('Login failed! Please check login credentials in {}'.format(CONFIG_FILE),'white'))
        print(colored('Quit','white'))
        exit()

    if(len(sys.argv))<3:
        # Require user's inputs to to download / ID and location
        location = "./media/new/"
        downloadID = sys.argv[1]
        # location = input("Local Path (Enter . for current directory): ")
        # while not location:
        #     location = input("Local Path (Enter . for current directory): ")
        # if location[-1] != '/':
        #     location += '/'
        #
        # downloadID = input("FShare Folder/File URL: ")
        # while not downloadID:
        #     downloadID = input("FShare Folder/File URL: ")
        
    else:
        downloadID = sys.argv[1]
        location = sys.argv[2]
        if location[-1] != '/':
            location += '/'
    if (path.isfile(downloadID)):
        with open(downloadID) as file:
            id_lists = [line.strip() for line in file]
    else:
        id_lists = [downloadID]

    for downloadID in id_lists:
        # Check file or folder
        if not is_folder(downloadID):
            # It's a file, download it now
            fileInfo = service.get_file_info(downloadID)
            print(colored('File: ','white'),colored('{}'.format(fileInfo['name']),'yellow'))
            # print(f'Saving to {location}')
            download_file(service.download(FShare_File_URL+fileInfo['linkcode']),location,fileInfo['name'])
            print(colored('{} downloaded'.format(fileInfo['name']),'yellow'))

        elif is_folder(downloadID):
            # It's folder, explode and download
            print("Folder detected, recursively download folder")
            download_folder(downloadID,location)
        else:
            print('Error, unknown link')

                
    splash_screen_end()
    exit(0)

def get_valid_filename(s):
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)

def download_folder(url, location):
    """
    Download whole fshare folder / a local folder name with folderID being read from URL will be created if it doesn't exist
    """
    match = re.search(re_folder_pattern,url)
    if match is not None:
        folderID = match.group(2)
    else:
        print(colored("Folder Link error, please make sure it's welformed as https://www.fshare.vn/folder/XXXXXXXXXX (token trail is optional)",'red'))
        return 1
    
    folderList = service.get_folder_urls(url)
    if (len(folderList)) < 1:
        print("Folder empty!")
        return 1

    # We will try to detect the folder name and write it down to the file for reference later
    # Fshare store the name including the parent folder so we have to regex to match

    match2 = re.search(re_folder_name_pattern,folderList[0]['path'])
    folder_name = get_valid_filename(match2.group(2))
    if not folder_name:
        folder_name = folderID
    if not os.path.exists(location + folder_name):
        os.makedirs(location + folder_name)
    # Update new location to new directory
    location += folder_name + "/"


    
    # detect and count sub-folders / we will ignore subfolder
    sub_folder_count = 0
    for fileInfo in folderList:
        if is_folder(fileInfo['furl']):
            sub_folder_count += 1
    if sub_folder_count > 0:
        print(colored("We found {} file(s) and {} sub-folder(s) in the link, we're skipping folder, ONLY FILES will be downloaded!".format(len(folderList)-sub_folder_count,sub_folder_count),'yellow'))

        # We will try to detect the folder name and write it down to the file for reference later
        # Fshare store the name including the parent folder so we have to regex to match

        with open(location + Folder_Reference_Filename, "w") as f:
            f.writelines(f"Folder URL: {url} \n")
            f.writelines(f"Folder name: {match2.group(2)} \n")
            f.writelines(f"File count: {len(folderList) - sub_folder_count} \n")
            f.writelines(f"Sub-Folder count: {sub_folder_count} \n")
        
    print(colored("We found {} file(s) in the link, download them now".format(len(folderList)-sub_folder_count),'yellow'))
    # loop through whole directory and download
    fileCount = 0
    for fileInfo in folderList:
        if not is_folder(fileInfo['furl']):
            print(colored('File #{}: '.format(fileCount),'white'),colored('{}'.format(fileInfo['name']),'yellow'))
            download_file(service.download(FShare_File_URL+fileInfo['linkcode']),location,fileInfo['name'])
            fileCount += 1
    
def download_file(url, location,filename):
    """
    Download a particular file from with direct link provided from service payload with download bar
    """
    # local_filename = url.split('/')[-1]
    local_filename = filename
    local_filename = no_accent_vietnamese(local_filename)
    if os.path.exists(location + local_filename):
        print('Local File Existed ! Ignore downloading')
        return 1
    else:
        try:
            with requests.get(url, stream=True,timeout=(2,3)) as r:
                try:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length'))
                    if (total_size > (2*1024*1024*1024)):
                    #File is greater than 2Gb, use bigger chunk size
                        download_chunk_size = 2*1024*1024
                    else:
                        download_chunk_size = 1024*1024
                    downloaded_chunk = 0
                    progressbar = tqdm(total=total_size,desc="Downloading",ncols=70, unit_scale=True, unit="B")
                    with open(location + local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=download_chunk_size): 
                            if chunk: # filter out keep-alive new chunks
                                f.write(chunk)
                                f.flush()
                                progressbar.update(len(chunk))
                                # progressbar.update(float((downloaded_chunk*(download_chunk_size)/total_size)))
                                # downloaded_chunk += 1
                        progressbar.close()
                except HTTPError:
                    print("HTTP Error")
            return (location + local_filename)
        except Timeout:
            print('Please check Internet connection, the request timed out')
        
        
def is_folder(url):
    if (url.find(Folder_Indicator)) != -1:
        return True
    else:
        return False

def perform_login(login_credential):
    """
    Perform login and return the status True/False
    """    
    global service
    service = FSAPI(login_credential['username'],login_credential['password'])
    login_status = True
    try:
        service.login()
    except KeyError:
        login_status=False
    return login_status

def configuration_read(filename):
    """
    Read configuration from file / without header section
    """
    config = configparser.ConfigParser()
    # Append a header section to avoid header section in the configuration file
    # config.read(filename,encoding="utf-8")
    with open(filename) as f:
        config.read_string('[DEFAULT]\n'+f.read())
    return config['DEFAULT']


def cls():
    os.system('cls' if os.name=='nt' else 'clear')

def splash_screen():
# use Colorama to make Termcolor work on Windows too
    init()
    # now, to clear the screen
    cls()


    print(colored('_______      _______. __    __       ___      .______       _______     ____    ____ .__   __.                     ', 'red'))
    print(colored('|   ____|    /       ||  |  |  |     /   \     |   _  \     |   ____|    \   \  /   / |  \ |  |                    ', 'red'))
    print(colored('|  |__      |   (----`|  |__|  |    /  ^  \    |  |_)  |    |  |__        \   \/   /  |   \|  |                    ', 'red')) 
    print(colored('|   __|      \   \    |   __   |   /  /_\  \   |      /     |   __|        \      /   |  . `  |                    ', 'yellow'))
    print(colored('|  |     .----)   |   |  |  |  |  /  _____  \  |  |\  \----.|  |____  __    \    /    |  |\   |                    ', 'yellow'))
    print(colored('|__|     |_______/    |__|  |__| /__/     \__\ | _| `._____||_______|(__)    \__/     |__| \__|                    ', 'green'))
    print(colored('_______   ______   ____    __    ____ .__   __.  __        ______        ___       _______   _______ .______       ', 'blue'))
    print(colored('|       \ /  __  \  \   \  /  \  /   / |  \ |  | |  |      /  __  \      /   \     |       \ |   ____||   _  \     ', 'blue'))
    print(colored('|  .--.  |  |  |  |  \   \/    \/   /  |   \|  | |  |     |  |  |  |    /  ^  \    |  .--.  ||  |__   |  |_)  |    ', 'magenta'))
    print(colored('|  |  |  |  |  |  |   \            /   |  . `  | |  |     |  |  |  |   /  /_\  \   |  |  |  ||   __|  |      /     ', 'magenta'))
    print(colored("|  '--'  |  `--'  |    \    /\    /    |  |\   | |  `----.|  `--'  |  /  _____  \  |  '--'  ||  |____ |  |\  \----.", 'cyan'))
    print(colored('|_______/ \______/      \__/  \__/     |__| \__| |_______| \______/  /__/     \__\ |_______/ |_______|| _| `._____|', 'cyan'))
    print(colored('===================================================================================================================', 'white'))
    print(colored('                                                                             Version : ', 'yellow'), (1.0))
    print(colored('                                                                              Author : ', 'yellow'), ('haind'))
    print(colored('                                        Github : ', 'yellow'), ('https://github.com/haindvn/FShareDownloader'))
    print(colored('===================================================================================================================', 'white'))

def splash_screen_end():
    print(colored('===================================================================================================================', 'white'))
    print(colored('Download Finished','green'))

def no_accent_vietnamese(s):
    #s = s.decode('utf-8', errors='ignore')
    s = re.sub(u'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', s)
    s = re.sub(u'[ÀÁẠẢÃĂẰẮẶẲẴÂẦẤẬẨẪ]', 'A', s)
    s = re.sub(u'[èéẹẻẽêềếệểễ]', 'e', s)
    s = re.sub(u'[ÈÉẸẺẼÊỀẾỆỂỄ]', 'E', s)
    s = re.sub(u'[òóọỏõôồốộổỗơờớợởỡ]', 'o', s)
    s = re.sub(u'[ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ]', 'O', s)
    s = re.sub(u'[ìíịỉĩ]', 'i', s)
    s = re.sub(u'[ÌÍỊỈĨ]', 'I', s)
    s = re.sub(u'[ùúụủũưừứựửữ]', 'u', s)
    s = re.sub(u'[ƯỪỨỰỬỮÙÚỤỦŨ]', 'U', s)
    s = re.sub(u'[ỳýỵỷỹ]', 'y', s)
    s = re.sub(u'[ỲÝỴỶỸ]', 'Y', s)
    s = re.sub(u'[Đ]', 'D', s)
    s = re.sub(u'[đ]', 'd', s)
    return s

if __name__ == '__main__':
    main()

#fileinfo = bot.get_file_info(URL)
#print("Direct Link:",bot.download("https://www.fshare.vn/file/{}".format(fileinfo['linkcode'])))
