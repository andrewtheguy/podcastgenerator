#!/usr/bin/env python3
from subprocess import Popen, PIPE, DEVNULL
import sys
import os

class Web3Client:
    def __init__(self, api_key,):
        self.api_key = api_key

    def upload_to_web3storage(self,path,name = None):
        my_env = {**os.environ, 'WEB3STORAGE_TOKEN': self.api_key or ''}
        
        cmd = ["npx", "node@16", f"{sys.path[0]}/node_modules/.bin/storetoweb3", path ]

        if(name):
            cmd.extend(["--name",name])

        p = Popen(cmd, stdout=PIPE, stderr=sys.stderr, env=my_env)
        result = p.communicate()[0] # wait for process to finish; this also sets the returncode variable inside 'res'
        # print(p.returncode)
        if p.returncode != 0:

            raise RuntimeError(f"failed, exit code {p.returncode}")
        else:
            # cid
            return result.decode("utf-8").rstrip()

#if __name__ == "__main__":
#    upload_to_web3storage(sys.argv[1],'test2')        