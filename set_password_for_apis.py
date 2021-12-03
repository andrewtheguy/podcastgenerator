#!/usr/bin/env python3
import keyring,sys,os,yaml

if(sys.argv[1]):
    config_file = sys.argv[1]
else:    
    directory = os.cwd()
    config_filename = 'podcastconfig_ipfs.yaml'
    config_file = f'{directory}/{config_filename}'

if not os.path.isfile(config_file):
    raise RuntimeError(f'{config_file} is not a file')

with open(config_file, "r") as stream:
    dataconf = yaml.safe_load(stream)
config = dataconf['config']

print('enter json for google storage account, blank to skip:',file=sys.stderr)
password = sys.stdin.readline().rstrip()
if(len(password)>0):
    print('changing password',file=sys.stderr)
    keyring.set_password("podcastgenerator", config['google_cloud']['json_token_keyring_name'], password)

print('enter api key for web3.storage, blank to skip:',file=sys.stderr)
password = sys.stdin.readline().rstrip()
if(len(password)>0):
    print('changing password',file=sys.stderr)
    keyring.set_password("podcastgenerator", config['ipfs']['web3_api_keyring_name'], password)

enable_publish_to_ipns = config['enable_publish_to_ipns'] == "yes"
if enable_publish_to_ipns:
    print('enter api token for cloudflare dns, blank to skip:',file=sys.stderr)
    password = sys.stdin.readline().rstrip()
    if(len(password)>0):
        print('changing password',file=sys.stderr)
        keyring.set_password("podcastgenerator", config['ipns']['cloudflare_dns_api_token_keyring_name'], password)