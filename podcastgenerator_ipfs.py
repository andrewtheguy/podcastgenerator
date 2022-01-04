#!/usr/bin/env python3
# This is a sample Python script.

from argparse import ArgumentError, ArgumentParser

import argparse
import os
import re
from subprocess import DEVNULL, PIPE, Popen
import sys
import glob
import hashlib
import pathlib
from pathlib import Path
from tinytag import TinyTag
from natsort import natsorted
import logging
import keyring
from jinja2 import Environment, FileSystemLoader, select_autoescape
import yaml
from datetime import datetime, timezone
from datetime import timedelta
from urllib.parse import urlparse, urlunparse, quote
import secrets
from datetime import datetime, timezone
from web3client import Web3Client
import urllib
import CloudFlare
from dateutil.parser import parse
from keyrings.cryptfile.cryptfile import CryptFileKeyring


logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


mime_extension_mapping = {
    ".m4a":"audio/mp4"
}


class PodcastGenerator:
    def __init__(self, directory):

        config_filename = 'podcastconfig_ipfs.yaml'
        config_file = f'{directory}/{config_filename}'
        if not os.path.isfile(config_file):
            raise RuntimeError(f'{config_file} is not a file')

        with open(config_file, "r") as stream:
            dataconf = yaml.safe_load(stream)
        config = dataconf['config']

        remote_dir = config['remote']['base_folder']
        kr = CryptFileKeyring()
        # password to unlock keyring
        kr.keyring_key = Path(Path.home(),'.config','pythoncryptfilepass').read_text()
        web3_api_key = kr.get_password("podcastgenerator", config['ipfs']['web3_api_keyring_name'])

        enable_publish_to_ipns = config['enable_publish_to_ipns'] == "yes"

        cloudflare_zone_name = ""
        cloudflare_dns_api_token = ""
        if enable_publish_to_ipns:
            cloudflare_zone_name = config['ipns']['cloudflare_zone_name']
            cloudflare_dns_api_token = kr.get_password("podcastgenerator", config['ipns']['cloudflare_dns_api_token_keyring_name'])

        web3client = Web3Client(api_key=web3_api_key)

        
        self.info_filename = 'podcastinfo_ipfs.yaml'
        self.info_file = f'{directory}/{self.info_filename}'
        self.config_filename = config_filename
        self.config_file = config_file

        self.remote_dir = remote_dir
        self.channel = config['channel']
        self.config = config
        self.ipfs_media_host = urlunparse(urlparse(
            config['ipfs']['media_host']))

        self.web3client = web3client

        self.enable_publish_to_ipns = enable_publish_to_ipns
        self.cloudflare_dns_api_token = cloudflare_dns_api_token
        self.cloudflare_zone_name = cloudflare_zone_name
        
parser = ArgumentParser(
    description=f"Publish podcasts"
)

subparsers = parser.add_subparsers(help="Command")
parser.set_defaults(command=lambda _: parser.print_help())


cmd_generate = subparsers.add_parser(
    "add_files",
    description="add new files in a folder to podcast info yml, it will not update podcast feed or upload",
    epilog="")

cmd_generate.add_argument('-d', '--directory', help='directory', required=False)


def process_directory(args):
    directory = args.directory or os.getcwd()
    dir = os.path.abspath(directory)

    if not os.path.isdir(dir):
        raise RuntimeError(f'{dir} is not a folder')

    podcast_generator = PodcastGenerator(directory=dir)

    config = podcast_generator.config

    timestamp_strategy = config['timestamp']['generate_method']

    if timestamp_strategy == 'seed_ts':
        base_date = datetime.fromisoformat(config['timestamp']['seed_ts'])
    elif timestamp_strategy == 'modified':
        pass
    else:
        raise ValueError("only generate_method: 'seed_ts' and 'modified' is supported for now")

    info_file = podcast_generator.info_file

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
        file_extension = pathlib.Path(file).suffix

        file_type = mime_extension_mapping[file_extension]

        tag = TinyTag.get(file)

        filename = os.path.basename(file)
        if timestamp_strategy == 'seed_ts':
            ts = (base_date + timedelta(days=len(data["items"])))
        elif timestamp_strategy == 'modified':
            ts = datetime.fromtimestamp(os.path.getmtime(file),timezone.utc)

        data["items"].append({'file': filename,
                      'hash_md5': hash_md5,
                      'timestamp': ts.isoformat(),
                      'file_type': file_type,
                      'file_extension': file_extension,
                      'tag': tag.as_dict(),
                      })
        #count = count + 1
    with open(info_file, 'w') as outfile:
        #yaml.dump(data, outfile, Dumper=MyDumper, encoding='utf-8', allow_unicode=True, default_flow_style=False, sort_keys=False)
        yaml.safe_dump(data, outfile, encoding='utf-8', allow_unicode=True,indent=4, sort_keys=False)

cmd_generate.set_defaults(command=process_directory)

def publish_to_ipns(podcast_generator,path,name):
    cid = podcast_generator.web3client.upload_to_web3storage(path,name,True)
    if(len(cid)==0):
        raise ValueError('cid cannot be empty')
        
    cf = CloudFlare.CloudFlare(token = podcast_generator.cloudflare_dns_api_token)
    # cloudflare
    subdomain_name = podcast_generator.remote_dir

    zone_name = podcast_generator.cloudflare_zone_name

    r = cf.zones.get(params={'name': zone_name})[0]
    
    zone_id = r['id']
    record_name = '_dnslink.'+subdomain_name
    # DNS records to create
    new_record = {'name': record_name, 'type':'TXT','content': f'dnslink=/ipfs/{cid}'}

    dns_record = cf.zones.dns_records.get(zone_id, params={'name': record_name + '.' + zone_name })

    dns_record_id = dns_record[0]['id'] if dns_record else None

    if dns_record_id:
        r = cf.zones.dns_records.put(zone_id, dns_record_id, data=new_record)
    else:
        r = cf.zones.dns_records.post(zone_id, data=new_record)
    
    # use one that doesn't redirect
    print(f"ipns published to https://gateway.ipfs.io/ipns/{subdomain_name}.{zone_name}/feed.xml")

def get_filename_ipfs(obj):
    ext = obj['file_extension']        
    filename_ipfs = obj['hash_md5'] + ext
    return filename_ipfs

cmd_upload = subparsers.add_parser(
    "upload",
    description="upload podcast files and updated feed to ipfs",
    epilog="")

cmd_upload.add_argument('-d','--directory', help='directory', required=False)
cmd_upload.add_argument('-f','--force', help='force upload local files even if cid exists in info yaml', required=False, default=False, action='store_true')
cmd_upload.add_argument('--delete-extra', help='delete extra files not found', default=False, action='store_true')

def uploadpodcast(args):
    argdir = args.directory or os.getcwd()
    delete_extra = args.delete_extra
    force = args.force

    if(delete_extra):
        raise ArgumentError("delete_extra is not supported by web3.storage")
    dir = os.path.abspath(argdir)
    if not os.path.isdir(dir):
        raise RuntimeError(f'{dir} is not a directory')

    podcast_generator = PodcastGenerator(directory=dir)

    info_file = podcast_generator.info_file
    if not os.path.isfile(info_file):
        raise RuntimeError(f'{info_file} is not a file')

    with open(info_file, "r") as stream:
        data = yaml.safe_load(stream)

    remote_dir = podcast_generator.remote_dir

    enable_publish_to_ipns = podcast_generator.enable_publish_to_ipns

    now = datetime.now(timezone.utc)

    tmpdir = dir+'/'+'tmp'
    os.makedirs(tmpdir,exist_ok=True)
    for obj in data["items"]:
        if(force or ('ipfs_cid' not in obj)):
            local_path = os.path.join(dir, obj['file'])  
            filename_ipfs = get_filename_ipfs(obj)
            upload_path = tmpdir+'/'+filename_ipfs
            try:
                Path(upload_path).unlink(missing_ok=True)
                os.symlink(local_path,upload_path)
                #ext = obj['file_extension']
                ipfs_cid = podcast_generator.web3client.upload_to_web3storage(upload_path, obj['file'] ,wrap_directory=True)
            finally:    
                Path(upload_path).unlink(missing_ok=True)
            if(len(ipfs_cid)==0):
                raise ValueError('cid cannot be empty')
            obj['ipfs_cid'] = ipfs_cid
            logging.info(f"saving config file to prevent progress from getting lost")
            with open(info_file, 'w') as outfile:
                yaml.safe_dump(data, outfile, encoding='utf-8', allow_unicode=True,indent=4, sort_keys=False)

    

    env = Environment(
        loader=FileSystemLoader(os.path.dirname(os.path.realpath(__file__))),
        autoescape=select_autoescape(['html', 'xml', 'jinja'])
    )
    template = env.get_template("feed_template.xml.jinja")

    last_build_date = None

    channel = podcast_generator.channel


    episodes = []

    for obj in data["items"]:
        
        enclosure = {'file_len': obj['tag']['filesize'], "file_type": obj['file_type']}

        date = datetime.fromisoformat(obj['timestamp'])

        if not last_build_date:
            last_build_date = date
        elif date > last_build_date:
            last_build_date = date


        datestr = date.strftime("%a, %d %b %Y %H:%M:%S %z")

        filename, file_extension = os.path.splitext(obj['file'])

        ## use this one instead because it matches destination
        filename_ipfs = get_filename_ipfs(obj)

        #link = podcast_generator.ipfs_media_host + '/ipfs/'+obj['ipfs_cid']+'?filename='+urllib.parse.quote_plus(filename_ipfs)

        # match original filename
        link = podcast_generator.ipfs_media_host + '/ipfs/'+obj['ipfs_cid']+'/'+urllib.parse.quote_plus(filename_ipfs)


        episodes.append({
            'title': obj['tag']['title'] or filename,
            'link': link,
            'hash_md5': obj['hash_md5'],
            'author': obj['tag']['artist'],
            'date': datestr,
            'enclosure': enclosure,
        })

    if not last_build_date:
         last_build_date = now

    #last_build_date = now

    feed = template.render(channel=channel, episodes=episodes, last_build_date=last_build_date.strftime("%a, %d %b %Y %H:%M:%S %z"))
    feed_file = f'{dir}/feed.xml'
    with open(feed_file, 'w') as f:
        f.write(feed)

    logging.info(f"saving config file")
    with open(info_file, 'w') as outfile:
        yaml.safe_dump(data, outfile, encoding='utf-8', allow_unicode=True,indent=4, sort_keys=False)

    if enable_publish_to_ipns:    
        publish_to_ipns(podcast_generator,feed_file, remote_dir)    

cmd_upload.set_defaults(command=uploadpodcast)

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



cmd_restore = subparsers.add_parser(
    "restore",
    description="restore files from ipfs based on existing podcastinfo_ipfs.yml",
    epilog="")

cmd_restore.add_argument('-d','--directory', help='directory', required=False)

def download_with_curl(ipfs_media_host,cid,filename,dest):

    url = ipfs_media_host+f"/ipfs/{cid}/{filename}" 

    p = Popen(["curl","-f", url,'-o',dest] , stdout=DEVNULL, stderr=PIPE)
    p.wait() # wait for process to finish; this also sets the returncode variable inside 'res'
    #print(p.returncode)
    if p.returncode != 0:
        #print('chafa')
        raise Exception(f"{url} download failed, exit code {p.returncode}")
    else:
        logging.info(f'finished downloading through {url}')


def restore_from_ipfs(args):
    argdir = args.directory or os.getcwd()
    dir = os.path.abspath(argdir)
    if not os.path.isdir(dir):
        raise RuntimeError(f'{dir} is not a directory')

    podcast_generator = PodcastGenerator(directory=dir)

    info_file = podcast_generator.info_file
    if not os.path.isfile(info_file):
        raise RuntimeError(f'{info_file} is not a file')

    with open(info_file, "r") as stream:
        data = yaml.safe_load(stream)

    tmpdir = dir+'/'+'tmp'
    os.makedirs(tmpdir,exist_ok=True)

    for obj in data["items"]:
        ts = parse(obj['timestamp']).timestamp()
        if('hash_md5' in obj and 'file_extension' in obj and 'file' in obj):
            orig_path = os.path.join(dir, obj['file'])
            if(os.path.isfile(orig_path)):
                continue # skip
            filename_ipfs = get_filename_ipfs(obj)
            hashed_path = os.path.join(tmpdir, filename_ipfs)
            if(not os.path.isfile(orig_path)):
                download_with_curl(podcast_generator.ipfs_media_host,obj['ipfs_cid'],filename_ipfs,hashed_path)
                os.utime(hashed_path,(ts,ts))
                os.rename(hashed_path,orig_path)

# sample script to fix ts for existing files from config                
def fix_ts():
    argdir = os.getcwd()
    dir = os.path.abspath(argdir)
    if not os.path.isdir(dir):
        raise RuntimeError(f'{dir} is not a directory')

    podcast_generator = PodcastGenerator(directory=dir)

    info_file = podcast_generator.info_file
    if not os.path.isfile(info_file):
        raise RuntimeError(f'{info_file} is not a file')

    with open(info_file, "r") as stream:
        data = yaml.safe_load(stream)

    tmpdir = dir+'/'+'tmp'
    os.makedirs(tmpdir,exist_ok=True)

    for obj in data["items"]:
        ts = parse(obj['timestamp']).timestamp()
        orig_path = os.path.join(dir, obj['file'])
        if(os.path.isfile(orig_path)):                
            os.utime(orig_path,(ts,ts))



cmd_restore.set_defaults(command=restore_from_ipfs)

if __name__ == "__main__":
    # Finally, use the new parser
    all_args = parser.parse_args()
    # Invoke whichever command is appropriate for the arguments
    all_args.command(all_args)