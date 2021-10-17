#!/usr/bin/env python3
# This is a sample Python script.

from argparse import ArgumentParser

import argparse
import os
import glob
import jsonlines
import hashlib
import filetype
from pathlib import Path
from tinytag import TinyTag
from natsort import natsorted
import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

parser = argparse.ArgumentParser(description='Podcast.')
parser.add_argument('-d','--directory', help='directory')
args = parser.parse_args()

def process_directory(directory):

    dir = os.path.abspath(directory)

    if not os.path.isdir(dir):
        raise f'{dir} is not a folder'

    hash_md5s = set()

    with jsonlines.open(f'{dir}/output.jsonl') as reader:
        for obj in reader:
            hash_md5s.add(obj['hash_md5'])

    #logging.info(hash_md5s)

    files_sorted = natsorted(glob.glob(f"{dir}/*.m4a"))

    with jsonlines.open(f'{dir}/output.jsonl', mode='a') as writer:

        for file in files_sorted:
            hash_md5 = hashlib.md5(open(file,'rb').read()).hexdigest()
            if(hash_md5 in hash_md5s):
                logging.info(f'hash_md5 {hash_md5} for {file} already exists, skipping')
                continue
            #file_len = Path(file).stat().st_size
            file_type = filetype.guess_mime(file)

            tag = TinyTag.get(file)

            writer.write({'file': file,
                          'hash_md5': hash_md5,
                          #'file_len': file_len,
                          'file_type': file_type,
                          'tag': tag.as_dict(),
                          })

process_directory(args.directory)