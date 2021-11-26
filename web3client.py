#!/usr/bin/env python3
from subprocess import Popen, PIPE, DEVNULL
import sys
import os

def upload_to_web3storage(path,name = None):

    my_env = {**os.environ, 'WEB3STORAGE_TOKEN': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkaWQ6ZXRocjoweDc4MTAxMGVFZDVlQzcxOTIxRTRmRTYyNDE0NjkwMzU4OEZGMzQ3QzAiLCJpc3MiOiJ3ZWIzLXN0b3JhZ2UiLCJpYXQiOjE2Mzc4NjMwNDk4MTMsIm5hbWUiOiJkZWZhdWx0In0.7n4blcyo51DSij9DFcFCZrTzZEeHhzwV5PPiLL2YXr0'}
    
    cmd = [f"{sys.path[0]}/node_modules/.bin/storetoweb3", path ]

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