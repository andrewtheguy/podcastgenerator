#!/usr/bin/env python3
# This is a sample Python script.

from argparse import ArgumentParser

import argparse
import os
import sys
import glob
import hashlib
import mimetypes
from pathlib import Path
from tinytag import TinyTag
from natsort import natsorted
import logging
import keyring
from jinja2 import Environment, FileSystemLoader, select_autoescape
from webdav3.client import Client
import yaml
from datetime import datetime, timezone
from datetime import timedelta
from urllib.parse import urlparse, urlunparse, quote
from requests.auth import HTTPBasicAuth
import requests

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


mime_extension_mapping = {
    'audio/mp4a-latm':'.m4a'
}

parser = ArgumentParser(
    description=f"Publish podcasts on IPFS"
)

subparsers = parser.add_subparsers(help="Command")
parser.set_defaults(command=lambda _: parser.print_help())

cmd_new = subparsers.add_parser(
    "generate",
    description="generate podcast info in a folder from new files, it will not update podcast feed",
    epilog="These fields all fill out a template and are easily changed later,"
           " in particular description should probably be longer than is"
           " conveniently given as an option.")

cmd_new.add_argument('-d','--directory', help='directory', required=True)


def process_directory(args):
    directory = args.directory
    dir = os.path.abspath(directory)

    if not os.path.isdir(dir):
        raise RuntimeError(f'{dir} is not a folder')


    config_filename = 'podcastconfig.yaml'
    config_file = f'{dir}/{config_filename}'
    if not os.path.isfile(config_file):
        raise RuntimeError(f'{config_file} is not a file')


    with open(config_file, "r") as stream:
        dataconf = yaml.safe_load(stream)
    config = dataconf['config']

    timestamp_strategy = config['timestamp']['generate_method']

    if timestamp_strategy == 'seed_ts':
        base_date = datetime.fromisoformat(config['timestamp']['seed_ts'])
    elif timestamp_strategy == 'modified':
        pass
    else:
        raise ValueError("only generate_method: 'seed_ts' is supported for now")

    info_file = f'{dir}/podcastinfo.yaml'

    data = {"items": []}

    hash_md5s = set()

    if(os.path.isfile(info_file)):
        with open(info_file, "r") as stream:
            filedata = yaml.safe_load(stream)
            if type(filedata) is dict and 'items' in filedata:
                data['items'] = filedata['items']


    for obj in data["items"]:
        hash_md5s.add(obj['hash_md5'])

    #logging.info(hash_md5s)
    files = glob.glob(f"{dir}/*.m4a")

    if timestamp_strategy == 'seed_ts':
        files_sorted = natsorted(files)
    elif timestamp_strategy == 'modified':
        files_sorted = sorted(files, key=lambda file: os.path.getmtime(file))
    #count = 0

    for file in files_sorted:

        with open(file,'rb') as f:
            file_hash = hashlib.md5()
            while chunk := f.read(8192):
                file_hash.update(chunk)
        hash_md5 = file_hash.hexdigest()
        #hash_md5 = hashlib.md5(open(file,'rb').read()).hexdigest()
        if(hash_md5 in hash_md5s):
            logging.info(f'hash_md5 {hash_md5} for {file} already exists, skipping')
            continue
        #file_len = Path(file).stat().st_size
        file_type = mimetypes.guess_type(file)[0]

        tag = TinyTag.get(file)

        filename = os.path.basename(file)
        if timestamp_strategy == 'seed_ts':
            ts = (base_date + timedelta(days=len(data["items"])))
        elif timestamp_strategy == 'modified':
            ts = datetime.fromtimestamp(os.path.getmtime(file))

        data["items"].append({'file': filename,
                      'hash_md5': hash_md5,
                      'timestamp': ts.isoformat(),
                      'file_type': file_type,
                      'tag': tag.as_dict(),
                      })
        #count = count + 1
    with open(info_file, 'w') as outfile:
        #yaml.dump(data, outfile, Dumper=MyDumper, encoding='utf-8', allow_unicode=True, default_flow_style=False, sort_keys=False)
        yaml.safe_dump(data, outfile, encoding='utf-8', allow_unicode=True,indent=4, sort_keys=False)

cmd_new.set_defaults(command=process_directory)

cmd_upload = subparsers.add_parser(
    "upload",
    description="upload podcast to webdav and then generate feed",
    epilog="These fields all fill out a template and are easily changed later,"
           " in particular description should probably be longer than is"
           " conveniently given as an option.")

cmd_upload.add_argument('-d','--directory', help='directory', required=True)
cmd_upload.add_argument('--delete-extra', help='delete extra files not found', default=False, action='store_true')


def uploadpodcast(args):
    argdir = args.directory
    delete_extra = args.delete_extra
    dir = os.path.abspath(argdir)
    if not os.path.isdir(dir):
        raise RuntimeError(f'{dir} is not a directory')
    info_filename = 'podcastinfo.yaml'
    info_file = f'{dir}/{info_filename}'
    if not os.path.isfile(info_file):
        raise RuntimeError(f'{info_file} is not a file')

    config_filename = 'podcastconfig.yaml'
    config_file = f'{dir}/{config_filename}'
    if not os.path.isfile(config_file):
        raise RuntimeError(f'{config_file} is not a file')

    with open(info_file, "r") as stream:
        data = yaml.safe_load(stream)

    with open(config_file, "r") as stream:
        dataconf = yaml.safe_load(stream)
    config = dataconf['config']

    remote_dir = config['remote']['base_folder']

    password = keyring.get_password("podcastgenerator", config['webdav']['password_keyring'])
    options = {
        'webdav_hostname': config['webdav']['hostname'],
        'webdav_login': config['webdav']['login'],
        'webdav_root': config['webdav']['root'],
        'webdav_password': password
    }

    audio_dir = remote_dir + '/audio'

    client = Client(options)
    client.verify = True  # To not check SSL certificates (Default = True)
    #client.session.proxies(...)  # To set proxy directly into the session (Optional)
    #client.session.auth(...)  # To set proxy auth directly into the session (Optional)
    client.mkdir(remote_dir)
    client.mkdir(audio_dir)

    alllist = client.list(audio_dir,get_info=True)
    filelist = list(filter(lambda item: not item['isdir'], alllist))
    filenames = list(map(lambda item: item['name'], filelist))
    #print(alllist)
    #print(filelist)
    #print(filenames)
    files_set = set(filenames)

    now = datetime.now(timezone.utc)

    for obj in data["items"]:
        ext = mime_extension_mapping[obj['file_type']]
        filename = obj['hash_md5'] + ext
        remote_path = audio_dir + '/' + filename
        if(filename not in files_set):
            local_path = os.path.join(dir, obj['file'])
            if not os.path.isfile(local_path):
                raise RuntimeError(f'{local_path} is not an existing file')
            logging.info(f"uploading new file {obj['file']} to {remote_path}")
            client.upload_sync(remote_path=remote_path, local_path=local_path)
        else:
            files_set.remove(filename)

    # delete only extra ones remaining
    if delete_extra and len(files_set) > 0:
        print('delete these files:')
        for file in sorted(files_set):
            print(file)
        should_continue = query_yes_no(f"type yes to confirm")
        if should_continue:
            for file in files_set:
                path = audio_dir+'/'+file
                logging.info(f'deleting extra file {path}')
                client.clean(path)

    env = Environment(
        loader=FileSystemLoader(os.path.dirname(os.path.realpath(__file__))),
        autoescape=select_autoescape(['html', 'xml', 'jinja'])
    )
    template = env.get_template("feed_template.xml.jinja")

    last_build_date = None

    channel = config['channel']


    episodes = []

    for obj in data["items"]:
        ext = mime_extension_mapping[obj['file_type']]
        link = urlunparse(urlparse(config['remote']['base_host']+'/'+config['webdav']['root']+'/'+config['remote']['base_folder']+'/audio/'+obj['hash_md5'] + ext))
        enclosure = {'file_len': obj['tag']['filesize'], "file_type": obj['file_type']}

        date = datetime.fromisoformat(obj['timestamp'])

        # if not last_build_date:
        #     last_build_date = date
        # elif date > last_build_date:
        #     last_build_date = date


        datestr = date.strftime("%a, %d %b %Y %H:%M:%S %z")

        filename, file_extension = os.path.splitext(obj['file'])

        episodes.append({
            'title': obj['tag']['title'] or filename,
            'link': link,
            'hash_md5': obj['hash_md5'],
            'author': obj['tag']['artist'],
            'date': datestr,
            'enclosure': enclosure,
        })

    # if not last_build_date:
    #     last_build_date = now

    last_build_date = now

    feed = template.render(channel=channel, episodes=episodes, last_build_date=last_build_date.strftime("%a, %d %b %Y %H:%M:%S %z"))
    feed_file = f'{dir}/feed.xml'
    with open(feed_file, 'w') as f:
        f.write(feed)

    client.upload_sync(remote_path=remote_dir+f'/{config_filename}', local_path=config_file)
    client.upload_sync(remote_path=remote_dir+f'/{info_filename}', local_path=info_file)
    client.upload_sync(remote_path=remote_dir+f'/feed.xml', local_path=feed_file)



def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


cmd_upload.set_defaults(command=uploadpodcast)

# Finally, use the new parser
all_args = parser.parse_args()
# Invoke whichever command is appropriate for the arguments
all_args.command(all_args)