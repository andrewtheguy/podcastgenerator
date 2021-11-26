# About

generate a podcast feed from a directory with audio files and upload it to a webdav server (currently only works with m4a)

# Instructions

## install dependencies
```
pipenv install
```

## run shell
```
pipenv shell
```

## create config file
Create a yaml file `podcastconfig_ipfs.yaml` in the directory with the following info
```
config:
  timestamp:
    # for generate_method, it will sort the new files added and increment the file from seed_ts by a day from top to bottom based on list size starting from 0
    # for modified, it will use the file's modified timestamp
    generate_method: 'seed_ts'
    seed_ts: '2019-02-01T08:00:00+00:00'
  channel: 
    title: "cool podcast"
    link: "https://ipfs.io/"
    description: "no description"
  remote:
    base_host: "https://basehost.com"
    base_folder: "folder1" # use a random suffix to avoid people guessing its name
  webdav: # for backing up config and feed, might be removed in the future
    hostname: "https://webdavserver/"
    root: "webdav"
    login: "podcast"
    password_keyring: "podcast"
  ipfs: # for storing audio and feed
    base_host: "https://ipfs.io"
    web3_api_keyring: "keyringname"
    cloudflare_dns_api_token_keyring: "keyringname2"
    cloudflare_zone_name: "cloudflare zone (domain name)"
```

will result in podcast url with this setup: `https://basehost.com/webdav/folder1/audio/md5sum_of_file.extension` # base_host is public facing host which might not be the same as webdav host

timestamp `generate_method` supports `seed_ts` and `modified`

it will sort the new files before adding to list, but not existing ones yet

## set password for webdav
run `python3`

```
import keyring
keyring.set_password("podcastgenerator", "(value under webdav.password_keyring from podcastconfig.yaml)", "password")
```

see `setpassword_sample.py` for example. 

## generate
```
./podcast_generator_ipfs.py add_files --directory=/directory_with_audio
```
it will generate a `podcastinfo_ipfs.yaml` with the following data for each audio file:
if --directory is not passed, it'll use current working directory
```
-   file: filename1.m4a
    file_type: video/mp4
    hash_md5: 92670de1a93449841a5841ec68da996e
    tag:
        album: 'album1'
        albumartist: null
        artist: 'artist1'
        audio_offset: null
        bitrate: 127.996
        channels: 2
        comment: 'none'
        composer: null
        disc: null
        disc_total: null
        duration: 1377.757
        extra: {}
        filesize: 22282335
        genre: null
        samplerate: 44100
        title: 'title1'
        track: null
        track_total: null
        year: '2019'
```

## upload
if --directory is not passed, it'll use current working directory
```
./main.py upload --directory=/directory_with_audio
```
### upload and delete extra (not supported by web3.storage)
```
./main.py upload --directory=/directory_with_audio --delete-extra
```

will upload those w/o ipfs_cid and then save the new cid to podcastinfo_ipfs.yaml
```
-   file: filename1.m4a
    file_type: video/mp4
    ...
    ipfs_cid: cid for the file wrapped with directory in this format cid/md5sum.extension
```

after that, the podcast feed will be available under the outputed url like `https://ipfs.io/ipns/domain?filename=feed.xml`

## Note
Regenerating `podcastconfig.yaml` won't remove deleted source file entries from the file; however, if the source file is deleted before it gets uploaded, it will cause upload to fail for that file.

password protect or deny access all files except those for podcast such as xml and audio files on the public host for static asset:
sample nginx config file:
```
auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/passwordfile;

location / {
        try_files $uri $uri/ =404;
}


# allow podcast related files w/o password
location ~ "\.(xml|mp3|mp4|m4a|aac)$" {
    auth_basic off;
}
```
# Sample wrapper script
create ~/bin/podcastgenerator.sh with content similar to this and make it executable
```
#!/bin/bash

exec /Users/andrew/.local/share/virtualenvs/podcastgenerator-PTp5dkkQ/bin/python /Users/andrew/codes/podcastgenerator/podcastgenerator.py "$@"
```

# ipfs
```
it uses a helper library @andrewtheguy/web3storage to upload to web3.storage
need to run npm install first to use it
```