# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
"""Unexecuted pure protocol fixtures; fake C API only, not a native proof."""
import ctypes
import re
import tempfile
import unittest
from pathlib import Path

from mycel_build import _credential_fixture_reader as reader
from mycel_build._credential_contract import FIXTURE_SOURCE

ROOT=Path(__file__).resolve().parents[1]

class API:
    def __init__(self,path,*,open_status=0,null_handle=False,unlock_status=0,find_status=0,lock_status=0,native_path=None):
        self.path=path;self.open_status=open_status;self.null_handle=null_handle
        self.unlock_status=unlock_status;self.find_status=find_status;self.lock_status=lock_status
        self.native_path=native_path;self.calls=[];self.payload=ctypes.create_string_buffer(b'public-standin')
        self.zeroed=False
    def SecKeychainSetUserInteractionAllowed(self,value):
        self.calls.append(('interaction',value));return 0
    def SecKeychainOpen(self,path,out):
        self.calls.append(('open',path));ctypes.cast(out,ctypes.POINTER(ctypes.c_void_p))[0]=None if self.null_handle or self.open_status else 101
        return self.open_status
    def SecKeychainGetPath(self,handle,size,buffer):
        self.calls.append(('path',handle.value));raw=str(self.native_path or self.path).encode()+b'\0'
        ctypes.memmove(buffer,raw,len(raw));ctypes.cast(size,ctypes.POINTER(ctypes.c_uint32))[0]=len(raw);return 0
    def SecKeychainUnlock(self,handle,length,password,use_password):
        self.calls.append(('unlock',handle.value));return self.unlock_status
    def SecKeychainFindGenericPassword(self,handle,sl,service,al,account,length,data,item):
        self.calls.append(('find',handle.value,service,account))
        if self.find_status:return self.find_status
        ctypes.cast(length,ctypes.POINTER(ctypes.c_uint32))[0]=len(b'public-standin')
        ctypes.cast(data,ctypes.POINTER(ctypes.c_void_p))[0]=ctypes.addressof(self.payload);return 0
    def SecKeychainItemFreeContent(self,attrs,data):
        self.calls.append(('free',));self.zeroed=ctypes.string_at(data,len(b'public-standin'))==b'\0'*len(b'public-standin');return 0
    def SecKeychainLock(self,handle):self.calls.append(('lock',handle.value));return self.lock_status
    def CFRelease(self,handle):self.calls.append(('release',handle.value))

class PrivateCredentialReaderTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='mycel-keychain-pure-unit-',dir='/private/tmp')
        self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name).resolve();self.root.chmod(0o700)
        s=(ROOT/FIXTURE_SOURCE).read_text()
        match=re.search(r'unsigned char test_keychain\[\]\s*=\s*\{([^}]+)\}',s,re.S)
        data=bytes(int(v,16) for v in re.findall(r'0x([0-9a-fA-F]{2})',match.group(1)))
        self.path=self.root/'fixture.keychain';self.path.write_bytes(data)
        st=self.root.stat();self.identity={'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,'mode':0o700}
    def run_fake(self,api):return reader.read_fixture(self.root,self.identity,api=(api,api))

if __name__=='__main__':unittest.main()

# Archived complete imports; restore needed names in their original scope, not at this file tail.
