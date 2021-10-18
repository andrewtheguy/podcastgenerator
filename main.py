#!/usr/bin/env python3
# This is a sample Python script.

from argparse import ArgumentParser

import argparse
import os
import glob
import hashlib
import filetype
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

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


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

    if config['timestamp']['generate_method'] == 'seed_ts':
        base_date = datetime.fromisoformat(config['timestamp']['seed_ts'])
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

    files_sorted = natsorted(glob.glob(f"{dir}/*.m4a"))

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
        file_type = filetype.guess_mime(file)

        tag = TinyTag.get(file)

        filename = os.path.basename(file)
        data["items"].append({'file': filename,
                      'hash_md5': hash_md5,
                      'timestamp': (base_date + timedelta(days=len(data["items"]))).isoformat(),
                      'file_type': file_type,
                      'tag': tag.as_dict(),
                      })
        #count = count + 1
    with open(info_file, 'w') as outfile:
        yaml.safe_dump(data, outfile, encoding='utf-8', allow_unicode=True,indent=4)

cmd_new.set_defaults(command=process_directory)

cmd_upload = subparsers.add_parser(
    "upload",
    description="upload podcast to webdav and then generate feed",
    epilog="These fields all fill out a template and are easily changed later,"
           " in particular description should probably be longer than is"
           " conveniently given as an option.")

cmd_upload.add_argument('-d','--directory', help='directory', required=True)


def uploadpodcast(args):
    argdir = args.directory
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
    client = Client(options)
    client.verify = True  # To not check SSL certificates (Default = True)
    #client.session.proxies(...)  # To set proxy directly into the session (Optional)
    #client.session.auth(...)  # To set proxy auth directly into the session (Optional)
    client.mkdir(remote_dir)
    client.mkdir(remote_dir + '/audio')

    now = datetime.now(timezone.utc)

    for obj in data["items"]:
        filename, file_extension = os.path.splitext(obj['file'])
        ext = file_extension.lower()
        remote_path = remote_dir + '/audio/' + obj['hash_md5']+ext
        if(not client.check(remote_path)):
            local_path = os.path.join(dir, obj['file'])
            if not os.path.isfile(local_path):
                raise RuntimeError(f'{local_path} is not an existing file')
            logging.info(f"uploading new file {obj['file']} to {remote_path}")
            client.upload_sync(remote_path=remote_path, local_path=local_path)

    env = Environment(
        loader=FileSystemLoader(os.path.dirname(os.path.realpath(__file__))),
        autoescape=select_autoescape(['html', 'xml', 'jinja'])
    )
    template = env.get_template("feed_template.xml.jinja")

    last_build_date = None

    channel = config['channel']


    episodes = []

    for obj in data["items"]:
        filename, file_extension = os.path.splitext(obj['file'])
        ext = file_extension.lower()
        #logging.debug(ext)
        remote_path = remote_dir + '/audio/' + obj['hash_md5'] + ext
        link = urlunparse(urlparse(config['remote']['base_host']+'/'+config['webdav']['root']+'/'+config['remote']['base_folder']+'/audio/'+obj['hash_md5'] + ext))
        enclosure = {'file_len': obj['tag']['filesize'], "file_type": obj['file_type']}

        date = datetime.fromisoformat(obj['timestamp'])

        # if not last_build_date:
        #     last_build_date = date
        # elif date > last_build_date:
        #     last_build_date = date


        datestr = date.strftime("%a, %d %b %Y %H:%M:%S %z")

        episodes.append({
            'title': obj['tag']['title'],
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

cmd_upload.set_defaults(command=uploadpodcast)

# Finally, use the new parser
all_args = parser.parse_args()
# Invoke whichever command is appropriate for the arguments
all_args.command(all_args)