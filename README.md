# About

generate a podcast feed from a directory with audio files and upload it to a ipfs(currently only works with m4a)

# Instructions

## install dependencies
```
pipenv install
```

## ipfs

it uses a helper library @andrewtheguy/web3storage to upload to web3.storage
need to run `npm install` first to use it

## run shell
```
pipenv shell
```

## create config file
Create a yaml file `podcastconfig_ipfs.yaml` in the directory with the following info
```
config:
  enable_publish_to_ipns: 'yes' # publish to ipns
  enable_publish_to_google_cloud: 'no' # no longer works
  enable_publish_to_s3: 'no' # publish to s3
  timestamp:
    # for generate_method, it will sort the new files added and increment 
    # the file from seed_ts by a day from top to bottom based on list size starting from 0
    # for modified, it will use the file's modified timestamp
    generate_method: 'seed_ts'
    seed_ts: '2019-02-01T08:00:00+00:00'
  channel: 
    title: "cool podcast"
    link: "https://ipfs.io/"
    description: "no description"
  remote:
    base_folder: "folder1" # use a random suffix to avoid people guessing its name
  ipfs: # for generating url for media and feed
    media_host: "https://infura-ipfs.io" # gateway for podcast media links 
                                    #make sure it supports byte range otherwise apple podcast will complaint
    web3_api_keyring_name: "keyringname"
  ipns: # for generating url for feed
    cloudflare_dns_api_token_keyring_name: "keyringname2"
    cloudflare_zone_name: "cloudflare zone (domain name)"
  s3:
    endpoint_url: "https://url"
    region_name: us-sanjose-1
    aws_access_key_id: "key"
    aws_secret_access_key_keyring_name: "secret_keyring_not_actual_key"
    bucket: "mybucket"
```


timestamp `generate_method` supports `seed_ts` and `modified`

it will sort the new files before adding to list, but not existing ones

## set password and api keys on key chain

```
./set_password_for_apis.py configfile
```


## generate info file
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
    ipfs_cid: cid
```

## upload
if --directory is not passed, it'll use current working directory
```
./main.py upload --directory=/directory_with_audio
```


will upload those w/o ipfs_cid and then save the new cid to podcastinfo_ipfs.yaml
```
-   file: filename1.m4a
    file_type: video/mp4
    ...
    ipfs_cid: cid for the file wrapped with directory in this format cid/md5sum.extension
```

after that, the podcast feed will be available under the outputted url like `https://gateway/ipns/domain?filename=feed.xml`


upload and delete extra (not supported by web3.storage)
```
./main.py upload --directory=/directory_with_audio --delete-extra
```


# Sample wrapper script to enable it to run in working directory w/o specifying --directory
create ~/bin/podcastgenerator.sh with content similar to this and make it executable
```
#!/bin/bash

exec /Users/andrew/.local/share/virtualenvs/podcastgenerator-PTp5dkkQ/bin/python /Users/andrew/codes/podcastgenerator/podcastgenerator.py "$@"
```


## Note
Regenerating `podcastconfig.yaml` won't remove deleted source file entries from the file; however, if the source file is deleted before it gets uploaded, it will cause upload to fail for that file.

if hosting your files in custom server instead, password protect or deny access all files except those for podcast such as xml and audio files on the public host for static asset:
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
