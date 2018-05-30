################################################################################
#
# Copyright (c) 2007-2008 Christopher J. Stawarz
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
################################################################################



"""

Pure-Python interface to Apple Bonjour and compatible DNS-SD libraries

pybonjour provides a pure-Python interface (via ctypes) to Apple
Bonjour and compatible DNS-SD libraries (such as Avahi).  It allows
Python scripts to take advantage of Zero Configuration Networking
(Zeroconf) to register, discover, and resolve services on both local
and wide-area networks.  Since pybonjour is implemented in pure
Python, scripts that use it can easily be ported to Mac OS X, Windows,
Linux, and other systems that run Bonjour.

Note on strings: Internally, all strings used in DNS-SD are UTF-8
strings.  String arguments passed to the DNS-SD functions provided by
pybonjour must be either unicode instances or str instances that can
be converted to unicode using the default encoding.  (Passing a
non-convertible str will result in an exception.)  Strings returned
from pybonjour (either directly from API functions or passed to
application callbacks) are always unicode instances.

"""


__author__   = 'Christopher Stawarz <cstawarz@csail.mit.edu>'
__version__  = '1.1.1'
__revision__ = int('$Revision: 6125 $'.split()[1])


import ctypes
import os
import re
import socket
import sys



################################################################################
#
# Global setup
#
################################################################################



class _DummyLock(object):

    @staticmethod
    def acquire():
        pass

    @staticmethod
    def release():
        pass

_global_lock = _DummyLock()


if sys.platform == 'win32':
    # Need to use the stdcall variants
    _libdnssd = ctypes.windll.dnssd
    _CFunc = ctypes.WINFUNCTYPE
else:
    if sys.platform == 'darwin':
        _libdnssd = 'libSystem.B.dylib'
    else:
        _libdnssd = 'libdns_sd.so.1'

        # If libdns_sd is actually Avahi's Bonjour compatibility
        # layer, silence its annoying warning messages, and use a real
        # RLock as the global lock, since the compatibility layer
        # isn't thread safe.
        try:
            ctypes.cdll.LoadLibrary('libavahi-client.so.3')
        except OSError:
            pass
        else:
            os.environ['AVAHI_COMPAT_NOWARN'] = '1'
            import threading
            _global_lock = threading.RLock()

    _libdnssd = ctypes.cdll.LoadLibrary(_libdnssd)
    _CFunc = ctypes.CFUNCTYPE



################################################################################
#
# Constants
#
################################################################################



#
# General flags
#

kDNSServiceFlagsMoreComing          = 0x1
kDNSServiceFlagsAdd                 = 0x2
kDNSServiceFlagsDefault             = 0x4
kDNSServiceFlagsNoAutoRename        = 0x8
kDNSServiceFlagsShared              = 0x10
kDNSServiceFlagsUnique              = 0x20
kDNSServiceFlagsBrowseDomains       = 0x40
kDNSServiceFlagsRegistrationDomains = 0x80
kDNSServiceFlagsLongLivedQuery      = 0x100
kDNSServiceFlagsAllowRemoteQuery    = 0x200
kDNSServiceFlagsForceMulticast      = 0x400
kDNSServiceFlagsReturnCNAME         = 0x800


#
# Service classes
#

kDNSServiceClass_IN                 = 1


#
# Service types
#

kDNSServiceType_A                   = 1
kDNSServiceType_NS                  = 2
kDNSServiceType_MD                  = 3
kDNSServiceType_MF                  = 4
kDNSServiceType_CNAME               = 5
kDNSServiceType_SOA                 = 6
kDNSServiceType_MB                  = 7
kDNSServiceType_MG                  = 8
kDNSServiceType_MR                  = 9
kDNSServiceType_NULL                = 10
kDNSServiceType_WKS                 = 11
kDNSServiceType_PTR                 = 12
kDNSServiceType_HINFO               = 13
kDNSServiceType_MINFO               = 14
kDNSServiceType_MX                  = 15
kDNSServiceType_TXT                 = 16
kDNSServiceType_RP                  = 17
kDNSServiceType_AFSDB               = 18
kDNSServiceType_X25                 = 19
kDNSServiceType_ISDN                = 20
kDNSServiceType_RT                  = 21
kDNSServiceType_NSAP                = 22
kDNSServiceType_NSAP_PTR            = 23
kDNSServiceType_SIG                 = 24
kDNSServiceType_KEY                 = 25
kDNSServiceType_PX                  = 26
kDNSServiceType_GPOS                = 27
kDNSServiceType_AAAA                = 28
kDNSServiceType_LOC                 = 29
kDNSServiceType_NXT                 = 30
kDNSServiceType_EID                 = 31
kDNSServiceType_NIMLOC              = 32
kDNSServiceType_SRV                 = 33
kDNSServiceType_ATMA                = 34
kDNSServiceType_NAPTR               = 35
kDNSServiceType_KX                  = 36
kDNSServiceType_CERT                = 37
kDNSServiceType_A6                  = 38
kDNSServiceType_DNAME               = 39
kDNSServiceType_SINK                = 40
kDNSServiceType_OPT                 = 41
kDNSServiceType_TKEY                = 249
kDNSServiceType_TSIG                = 250
kDNSServiceType_IXFR                = 251
kDNSServiceType_AXFR                = 252
kDNSServiceType_MAILB               = 253
kDNSServiceType_MAILA               = 254
kDNSServiceType_ANY                 = 255


#
# Error codes
#

kDNSServiceErr_NoError              = 0
kDNSServiceErr_Unknown              = -65537
kDNSServiceErr_NoSuchName           = -65538
kDNSServiceErr_NoMemory             = -65539
kDNSServiceErr_BadParam             = -65540
kDNSServiceErr_BadReference         = -65541
kDNSServiceErr_BadState             = -65542
kDNSServiceErr_BadFlags             = -65543
kDNSServiceErr_Unsupported          = -65544
kDNSServiceErr_NotInitialized       = -65545
kDNSServiceErr_AlreadyRegistered    = -65547
kDNSServiceErr_NameConflict         = -65548
kDNSServiceErr_Invalid              = -65549
kDNSServiceErr_Firewall             = -65550
kDNSServiceErr_Incompatible         = -65551
kDNSServiceErr_BadInterfaceIndex    = -65552
kDNSServiceErr_Refused              = -65553
kDNSServiceErr_NoSuchRecord         = -65554
kDNSServiceErr_NoAuth               = -65555
kDNSServiceErr_NoSuchKey            = -65556
kDNSServiceErr_NATTraversal         = -65557
kDNSServiceErr_DoubleNAT            = -65558
kDNSServiceErr_BadTime              = -65559


#
# Other constants
#

kDNSServiceMaxServiceName           = 64
kDNSServiceMaxDomainName            = 1005
kDNSServiceInterfaceIndexAny        = 0
kDNSServiceInterfaceIndexLocalOnly  = -1



################################################################################
#
# Error handling
#
################################################################################



class BonjourError(Exception):

    """

    Exception representing an error returned by the DNS-SD library.
    The errorCode attribute contains the actual integer error code
    returned.

    """

    _errmsg = {
        kDNSServiceErr_NoSuchName:      'no such name',
        kDNSServiceErr_NoMemory:        'no memory',
        kDNSServiceErr_BadParam:        'bad param',
        kDNSServiceErr_BadReference:        'bad reference',
        kDNSServiceErr_BadState:        'bad state',
        kDNSServiceErr_BadFlags:        'bad flags',
        kDNSServiceErr_Unsupported:     'unsupported',
        kDNSServiceErr_NotInitialized:      'not initialized',
        kDNSServiceErr_AlreadyRegistered:   'already registered',
        kDNSServiceErr_NameConflict:        'name conflict',
        kDNSServiceErr_Invalid:         'invalid',
        kDNSServiceErr_Firewall:        'firewall',
        kDNSServiceErr_Incompatible:        'incompatible',
        kDNSServiceErr_BadInterfaceIndex:   'bad interface index',
        kDNSServiceErr_Refused:         'refused',
        kDNSServiceErr_NoSuchRecord:        'no such record',
        kDNSServiceErr_NoAuth:          'no auth',
        kDNSServiceErr_NoSuchKey:       'no such key',
        kDNSServiceErr_NATTraversal:        'NAT traversal',
        kDNSServiceErr_DoubleNAT:       'double NAT',
        kDNSServiceErr_BadTime:         'bad time',
        }

    @classmethod
    def _errcheck(cls, result, func, args):
        if result != kDNSServiceErr_NoError:
            raise cls(result)
        return args

    def __init__(self, errorCode):
        self.errorCode = errorCode
        Exception.__init__(self,
                           (errorCode, self._errmsg.get(errorCode, 'unknown')))



################################################################################
#
# Data types
#
################################################################################



class _utf8_char_p(ctypes.c_char_p):

    @classmethod
    def from_param(cls, obj):
        if (obj is not None) and (not isinstance(obj, cls)):
            if not str(obj):
                raise TypeError('parameter must be a string type instance')

            obj = obj.encode('utf-8')
        return ctypes.c_char_p.from_param(obj)

    def decode(self):
        if self.value is None:
            return None
        return self.value.decode('utf-8')


class _utf8_char_p_non_null(_utf8_char_p):

    @classmethod
    def from_param(cls, obj):
        if obj is None:
            raise ValueError('parameter cannot be None')
        return _utf8_char_p.from_param(obj)


_DNSServiceFlags     = ctypes.c_uint32
_DNSServiceErrorType = ctypes.c_int32


class DNSRecordRef(ctypes.c_void_p):

    """

    A DNSRecordRef pointer.  DO NOT CREATE INSTANCES OF THIS CLASS!
    Only instances returned by the DNS-SD library are valid.  Using
    others will likely cause the Python interpreter to crash.

    Application code should not use any of the methods of this class.
    The only valid use of a DNSRecordRef instance is as an argument to
    a DNS-SD function.

    To compare two DNSRecordRef instances for equality, use '=='
    rather than 'is'.

    """

    @classmethod
    def from_param(cls, obj):
        if type(obj) is not cls:
            raise TypeError("expected '%s', got '%s'" %
                            (cls.__name__, type(obj).__name__))
        if obj.value is None:
            raise ValueError('invalid %s instance' % cls.__name__)
        return obj

    def __eq__(self, other):
        return ((type(other) is type(self)) and (other.value == self.value))

    def __ne__(self, other):
        return not (other == self)

    def _invalidate(self):
        self.value = None

    def _valid(self):
        return (self.value is not None)


class _DNSRecordRef_or_null(DNSRecordRef):

    @classmethod
    def from_param(cls, obj):
        if obj is None:
            return obj
        return DNSRecordRef.from_param(obj)


class DNSServiceRef(DNSRecordRef):

    """

    A DNSServiceRef pointer.  DO NOT CREATE INSTANCES OF THIS CLASS!
    Only instances returned by the DNS-SD library are valid.  Using
    others will likely cause the Python interpreter to crash.

    An instance of this class represents an active connection to the
    mDNS daemon.  The connection remains open until the close() method
    is called (which also terminates the associated browse, resolve,
    etc.).  Note that this method is *not* called automatically when
    the instance is deallocated; therefore, application code must be
    certain to call close() when the connection is no longer needed.

    The primary use of a DNSServiceRef instance is in conjunction with
    select() or poll() to determine when a response from the daemon is
    available.  When the file descriptor returned by fileno() is ready
    for reading, a reply from the daemon is available and should be
    processed by passing the DNSServiceRef instance to
    DNSServiceProcessResult(), which will invoke the appropriate
    application callback function.  (Note that the file descriptor
    should never be read from or written to directly.)

    The DNSServiceRef class supports the context management protocol
    introduced in Python 2.5, meaning applications can use the 'with'
    statement to ensure that DNSServiceRef instances are closed
    regardless of whether an exception occurs, e.g.

      sdRef = DNSServiceBrowse(...)
      with sdRef:
          # sdRef will be closed regardless of how this block is
          # exited
          ...

    To compare two DNSServiceRef instances for equality, use '=='
    rather than 'is'.

    """

    def __init__(self, *args, **kwargs):
        DNSRecordRef.__init__(self, *args, **kwargs)

        # Since callback functions are called asynchronously, we need
        # to hold onto references to them for as long as they're in
        # use.  Otherwise, Python could deallocate them before we call
        # DNSServiceProcessResult(), meaning the Bonjour library would
        # dereference freed memory when it tried to invoke the
        # callback.
        self._callbacks = []

        # A DNSRecordRef is invalidated if DNSServiceRefDeallocate()
        # is called on the corresponding DNSServiceRef, so we need to
        # keep track of all our record refs and invalidate them when
        # we're closed.
        self._record_refs = []

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def _add_callback(self, cb):
        self._callbacks.append(cb)

    def _add_record_ref(self, ref):
        self._record_refs.append(ref)

    def close(self):
        """

        Close the connection to the mDNS daemon and terminate any
        associated browse, resolve, etc. operations.

        """

        if self._valid():
            for ref in self._record_refs:
                ref._invalidate()
            del self._record_refs

            _global_lock.acquire()
            try:
                _DNSServiceRefDeallocate(self)
            finally:
                _global_lock.release()

            self._invalidate()
            del self._callbacks

    def fileno(self):
        """

        Return the file descriptor associated with this connection.
        This descriptor should never be read from or written to
        directly.  It should only be passed to select() or poll() to
        determine when a response from the mDNS daemon is available.

        """

        _global_lock.acquire()
        try:
            fd = _DNSServiceRefSockFD(self)
        finally:
            _global_lock.release()

        return fd


_DNSServiceDomainEnumReply = _CFunc(
    None,
    DNSServiceRef,      # sdRef
    _DNSServiceFlags,       # flags
    ctypes.c_uint32,        # interfaceIndex
    _DNSServiceErrorType,   # errorCode
    _utf8_char_p,       # replyDomain
    ctypes.c_void_p,        # context
    )


_DNSServiceRegisterReply = _CFunc(
    None,
    DNSServiceRef,      # sdRef
    _DNSServiceFlags,       # flags
    _DNSServiceErrorType,   # errorCode
    _utf8_char_p,       # name
    _utf8_char_p,       # regtype
    _utf8_char_p,       # domain
    ctypes.c_void_p,        # context
    )


_DNSServiceBrowseReply = _CFunc(
    None,
    DNSServiceRef,      # sdRef
    _DNSServiceFlags,       # flags
    ctypes.c_uint32,        # interfaceIndex
    _DNSServiceErrorType,   # errorCode
    _utf8_char_p,       # serviceName
    _utf8_char_p,       # regtype
    _utf8_char_p,       # replyDomain
    ctypes.c_void_p,        # context
    )


_DNSServiceResolveReply = _CFunc(
    None,
    DNSServiceRef,      # sdRef
    _DNSServiceFlags,       # flags
    ctypes.c_uint32,        # interfaceIndex
    _DNSServiceErrorType,   # errorCode
    _utf8_char_p,       # fullname
    _utf8_char_p,       # hosttarget
    ctypes.c_uint16,        # port
    ctypes.c_uint16,        # txtLen
    ctypes.c_void_p,        # txtRecord (not null-terminated, so c_void_p)
    ctypes.c_void_p,        # context
    )


_DNSServiceRegisterRecordReply = _CFunc(
    None,
    DNSServiceRef,      # sdRef
    DNSRecordRef,       # RecordRef
    _DNSServiceFlags,       # flags
    _DNSServiceErrorType,   # errorCode
    ctypes.c_void_p,        # context
    )


_DNSServiceQueryRecordReply = _CFunc(
    None,
    DNSServiceRef,      # sdRef
    _DNSServiceFlags,       # flags
    ctypes.c_uint32,        # interfaceIndex
    _DNSServiceErrorType,   # errorCode
    _utf8_char_p,       # fullname
    ctypes.c_uint16,        # rrtype
    ctypes.c_uint16,        # rrclass
    ctypes.c_uint16,        # rdlen
    ctypes.c_void_p,        # rdata
    ctypes.c_uint32,        # ttl
    ctypes.c_void_p,        # context
    )



################################################################################
#
# Low-level function bindings
#
################################################################################



def _create_function_bindings():

    ERRCHECK    = True
    NO_ERRCHECK = False

    OUTPARAM    = (lambda index: index)
    NO_OUTPARAM = None

    specs = {

        #'funcname':
        #(
        #    return_type,
        #    errcheck,
        #    outparam,
        #    (
        #   param_1_type,
        #   param_2_type,
        #   ...
        #   param_n_type,
        #   )),

        'DNSServiceRefSockFD':
        (
            ctypes.c_int,
            NO_ERRCHECK,
            NO_OUTPARAM,
            (
                DNSServiceRef,          # sdRef
                )),

        'DNSServiceProcessResult':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            NO_OUTPARAM,
            (
                DNSServiceRef,          # sdRef
                )),

        'DNSServiceRefDeallocate':
        (
            None,
            NO_ERRCHECK,
            NO_OUTPARAM,
            (
                DNSServiceRef,          # sdRef
                )),

        'DNSServiceEnumerateDomains':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.POINTER(DNSServiceRef),  # sdRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _DNSServiceDomainEnumReply, # callBack
                ctypes.c_void_p,        # context
                )),

        'DNSServiceRegister':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.POINTER(DNSServiceRef),  # sdRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _utf8_char_p,           # name
                _utf8_char_p_non_null,      # regtype
                _utf8_char_p,           # domain
                _utf8_char_p,           # host
                ctypes.c_uint16,        # port
                ctypes.c_uint16,        # txtLen
                ctypes.c_void_p,        # txtRecord
                _DNSServiceRegisterReply,   # callBack
                ctypes.c_void_p,        # context
                )),

        'DNSServiceAddRecord':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(1),
            (
                DNSServiceRef,          # sdRef
                ctypes.POINTER(DNSRecordRef),   # RecordRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint16,        # rrtype
                ctypes.c_uint16,        # rdlen
                ctypes.c_void_p,        # rdata
                ctypes.c_uint32,        # ttl
                )),

        'DNSServiceUpdateRecord':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            NO_OUTPARAM,
            (
                DNSServiceRef,          # sdRef
                _DNSRecordRef_or_null,      # RecordRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint16,        # rdlen
                ctypes.c_void_p,        # rdata
                ctypes.c_uint32,        # ttl
                )),

        'DNSServiceRemoveRecord':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            NO_OUTPARAM,
            (
                DNSServiceRef,          # sdRef
                DNSRecordRef,           # RecordRef
                _DNSServiceFlags,       # flags
                )),

        'DNSServiceBrowse':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.POINTER(DNSServiceRef),  # sdRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _utf8_char_p_non_null,      # regtype
                _utf8_char_p,           # domain
                _DNSServiceBrowseReply,     # callBack
                ctypes.c_void_p,        # context
                )),

        'DNSServiceResolve':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.POINTER(DNSServiceRef),  # sdRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _utf8_char_p_non_null,      # name
                _utf8_char_p_non_null,      # regtype
                _utf8_char_p_non_null,      # domain
                _DNSServiceResolveReply,    # callBack
                ctypes.c_void_p,        # context
                )),

        'DNSServiceCreateConnection':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.POINTER(DNSServiceRef),  # sdRef
                )),

        'DNSServiceRegisterRecord':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(1),
            (
                DNSServiceRef,          # sdRef
                ctypes.POINTER(DNSRecordRef),   # RecordRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _utf8_char_p_non_null,      # fullname
                ctypes.c_uint16,        # rrtype
                ctypes.c_uint16,        # rrclass
                ctypes.c_uint16,        # rdlen
                ctypes.c_void_p,        # rdata
                ctypes.c_uint32,        # ttl
                _DNSServiceRegisterRecordReply, # callBack
                ctypes.c_void_p,        # context
                )),

        'DNSServiceQueryRecord':
        (
            _DNSServiceErrorType,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.POINTER(DNSServiceRef),  # sdRef
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _utf8_char_p_non_null,      # fullname
                ctypes.c_uint16,        # rrtype
                ctypes.c_uint16,        # rrclass
                _DNSServiceQueryRecordReply,    # callBack
                ctypes.c_void_p,        # context
                )),

        'DNSServiceReconfirmRecord':
        (
            None,       # _DNSServiceErrorType in more recent versions
            NO_ERRCHECK,
            NO_OUTPARAM,
            (
                _DNSServiceFlags,       # flags
                ctypes.c_uint32,        # interfaceIndex
                _utf8_char_p_non_null,      # fullname
                ctypes.c_uint16,        # rrtype
                ctypes.c_uint16,        # rrclass
                ctypes.c_uint16,        # rdlen
                ctypes.c_void_p,        # rdata
                )),

        'DNSServiceConstructFullName':
        (
            ctypes.c_int,
            ERRCHECK,
            OUTPARAM(0),
            (
                ctypes.c_char * kDNSServiceMaxDomainName,   # fullName
                _utf8_char_p,                   # service
                _utf8_char_p_non_null,              # regtype
                _utf8_char_p_non_null,              # domain
                )),

        }


    for name, (restype, errcheck, outparam, argtypes) in specs.items():
        prototype = _CFunc(restype, *argtypes)

        paramflags = [1] * len(argtypes)
        if outparam is not None:
            paramflags[outparam] = 2
        paramflags = tuple((val,) for val in paramflags)

        func = prototype((name, _libdnssd), paramflags)

        if errcheck:
            func.errcheck = BonjourError._errcheck

        globals()['_' + name] = func


# Only need to do this once
_create_function_bindings()
del _create_function_bindings



################################################################################
#
# Internal utility types and functions
#
################################################################################



class _NoDefault(object):

    def __repr__(self):
        return '<NO DEFAULT>'

    def check(self, obj):
        if obj is self:
            raise ValueError('required parameter value missing')

_NO_DEFAULT = _NoDefault()


def _string_to_length_and_void_p(string):
    if isinstance(string, TXTRecord):
        string = str(string)
    void_p = ctypes.cast(ctypes.c_char_p(string), ctypes.c_void_p)
    return len(string), void_p


def _length_and_void_p_to_string(length, void_p):
    char_p = ctypes.cast(void_p, ctypes.POINTER(ctypes.c_char))
    return ''.join(char_p[i].decode('utf-8') for i in range(length))



################################################################################
#
# High-level functions
#
################################################################################



def DNSServiceProcessResult(
    sdRef,
    ):

    """

    Read a reply from the daemon, calling the appropriate application
    callback.  This call will block until the daemon's response is
    received.  Use sdRef in conjunction with select() or poll() to
    determine the presence of a response from the server before
    calling this function to process the reply without blocking.  Call
    this function at any point if it is acceptable to block until the
    daemon's response arrives.  Note that the client is responsible
    for ensuring that DNSServiceProcessResult() is called whenever
    there is a reply from the daemon; the daemon may terminate its
    connection with a client that does not process the daemon's
    responses.

      sdRef:
        A DNSServiceRef returned by any of the DNSService calls that
        take a callback parameter.

    """

    _global_lock.acquire()
    try:
        _DNSServiceProcessResult(sdRef)
    finally:
        _global_lock.release()


def DNSServiceEnumerateDomains(
    flags,
    interfaceIndex = kDNSServiceInterfaceIndexAny,
    callBack = None,
    ):

    """

    Asynchronously enumerate domains available for browsing and
    registration.

    The enumeration MUST be cancelled by closing the returned
    DNSServiceRef when no more domains are to be found.

      flags:
        Possible values are:
          kDNSServiceFlagsBrowseDomains to enumerate domains
          recommended for browsing.
          kDNSServiceFlagsRegistrationDomains to enumerate domains
          recommended for registration.

      interfaceIndex:
        If non-zero, specifies the interface on which to look for
        domains.  Most applications will pass
        kDNSServiceInterfaceIndexAny (0) to enumerate domains on all
        interfaces.

      callBack:
        The function to be called when a domain is found or the call
        asynchronously fails.  Its signature should be
        callBack(sdRef, flags, interfaceIndex, errorCode, replyDomain).

      return value:
        A DNSServiceRef instance.

    Callback Parameters:

      sdRef:
        The DNSServiceRef returned by DNSServiceEnumerateDomains().

      flags:
        Possible values are:
          kDNSServiceFlagsMoreComing
          kDNSServiceFlagsAdd
          kDNSServiceFlagsDefault

      interfaceIndex:
        Specifies the interface on which the domain exists.

      errorCode:
        Will be kDNSServiceErr_NoError (0) on success, otherwise
        indicates the failure that occurred (in which case other
        parameters are undefined).

      replyDomain:
        The name of the domain.

    """

    @_DNSServiceDomainEnumReply
    def _callback(sdRef, flags, interfaceIndex, errorCode, replyDomain,
                  context):
        if callBack is not None:
            callBack(sdRef, flags, interfaceIndex, errorCode,
                     replyDomain.decode())

    _global_lock.acquire()
    try:
        sdRef = _DNSServiceEnumerateDomains(flags,
                                            interfaceIndex,
                                            _callback,
                                            None)
    finally:
        _global_lock.release()

    sdRef._add_callback(_callback)

    return sdRef


def DNSServiceRegister(
    flags = 0,
    interfaceIndex = kDNSServiceInterfaceIndexAny,
    name = None,
    regtype = _NO_DEFAULT,
    domain = None,
    host = None,
    port = _NO_DEFAULT,
    txtRecord = '',
    callBack = None,
    ):

    """

    Register a service that is discovered via DNSServiceBrowse() and
    DNSServiceResolve() calls.

      flags:
        Indicates the renaming behavior on name conflict.  Most
        applications will pass 0.

      interfaceIndex:
        If non-zero, specifies the interface on which to register the
        service.  Most applications will pass
        kDNSServiceInterfaceIndexAny (0) to register on all available
        interfaces.

      name:
        If not None, specifies the service name to be registered.
        Most applications will not specify a name, in which case the
        computer name is used.  (This name is communicated to the
        client via the callback.)  If a name is specified, it must be
        1-63 bytes of UTF-8 text.  If the name is longer than 63
        bytes, it will be automatically truncated to a legal length,
        unless the flag kDNSServiceFlagsNoAutoRename is set, in which
        case a BonjourError exception will be thrown.

      regtype:
        The service type followed by the protocol, separated by a dot
        (e.g. "_ftp._tcp"). The service type must be an underscore,
        followed by 1-14 characters, which may be letters, digits, or
        hyphens.  The transport protocol must be "_tcp" or "_udp". New
        service types should be registered at
        <http://www.dns-sd.org/ServiceTypes.html>.

      domain:
        If not None, specifies the domain on which to advertise the
        service.  Most applications will not specify a domain, instead
        automatically registering in the default domain(s).

      host:
        If not None, specifies the SRV target host name.  Most
        applications will not specify a host, instead automatically
        using the machine's default host name(s).  Note that
        specifying a host name does NOT create an address record for
        that host; the application is responsible for ensuring that
        the appropriate address record exists, or creating it via
        DNSServiceRegisterRecord().

      port:
        The port, in host (not network) byte order, on which the
        service accepts connections.  Pass 0 for a "placeholder"
        service (i.e. a service that will not be discovered by
        browsing, but will cause a name conflict if another client
        tries to register that same name).  Most clients will not use
        placeholder services.

      txtRecord:
        The TXT record rdata.  If not None, txtRecord must be either a
        TXTRecord instance or a string containing a properly formatted
        DNS TXT record, i.e.
        <length byte> <data> <length byte> <data> ...

      callBack:
        The function to be called when the registration completes or
        asynchronously fails.  Its signature should be
        callBack(sdRef, flags, errorCode, name, regtype, domain).
        The client MAY pass None for the callback, in which case the
        client will NOT be notified of the default values picked on
        its behalf, and the client will NOT be notified of any
        asynchronous errors (e.g. out of memory errors, etc.) that may
        prevent the registration of the service.  The client may NOT
        pass the flag kDNSServiceFlagsNoAutoRename if the callback is
        None.  The client may still deregister the service at any time
        by closing the returned DNSServiceRef.

      return value:
        A DNSServiceRef instance.  The registration will remain active
        indefinitely until the client terminates it by closing the
        DNSServiceRef.

    Callback Parameters:

      sdRef:
        The DNSServiceRef returned by DNSServiceRegister().

      flags:
        Currently unused, reserved for future use.

      errorCode:
        Will be kDNSServiceErr_NoError on success, otherwise will
        indicate the failure that occurred (including name conflicts,
        if the kDNSServiceFlagsNoAutoRename flag was used when
        registering).  Other parameters are undefined if an error
        occurred.

      name:
        The service name registered.  (If the application did not
        specify a name in DNSServiceRegister(), this indicates what
        name was automatically chosen.)

      regtype:
        The type of service registered, as it was passed to the
        callout.

      domain:
        The domain on which the service was registered.  (If the
        application did not specify a domain in DNSServiceRegister(),
        this indicates the default domain on which the service was
        registered.)

    """

    _NO_DEFAULT.check(regtype)
    _NO_DEFAULT.check(port)

    port = socket.htons(port)

    # From here on txtRecord has to be a bytes type, so convert what
    # we have:
    if type(txtRecord) == TXTRecord:
        txtRecord = str(txtRecord).encode('utf-8')
    elif type(txtRecord) == str:
        txtRecord = txtRecord.encode('utf-8')
    else:
        raise TypeError('txtRecord is unhandlable type: {type}'.format(
            type=type(txtRecord)))

    if not txtRecord:
        txtLen, txtRecord = 1, '\0'
    else:
        txtLen, txtRecord = _string_to_length_and_void_p(txtRecord)

    @_DNSServiceRegisterReply
    def _callback(sdRef, flags, errorCode, name, regtype, domain, context):
        if callBack is not None:
            callBack(sdRef, flags, errorCode, name.decode(), regtype.decode(),
                     domain.decode())

    _global_lock.acquire()
    try:
        sdRef = _DNSServiceRegister(flags,
                                    interfaceIndex,
                                    name,
                                    regtype,
                                    domain,
                                    host,
                                    port,
                                    txtLen,
                                    txtRecord,
                                    _callback,
                                    None)
    finally:
        _global_lock.release()

    sdRef._add_callback(_callback)

    return sdRef


def DNSServiceAddRecord(
    sdRef,
    flags = 0,
    rrtype = _NO_DEFAULT,
    rdata = _NO_DEFAULT,
    ttl = 0,
    ):

    """

    Add a record to a registered service.  The name of the record will
    be the same as the registered service's name.  The record can
    later be updated or deregistered by passing the DNSRecordRef
    returned by this function to DNSServiceUpdateRecord() or
    DNSServiceRemoveRecord().

    Note that DNSServiceAddRecord/UpdateRecord/RemoveRecord are NOT
    thread-safe with respect to a single DNSServiceRef.  If you plan
    to have multiple threads in your program simultaneously add,
    update, or remove records from the same DNSServiceRef, then it's
    the caller's responsibility to use a lock or take similar
    appropriate precautions to serialize those calls.

      sdRef:
        A DNSServiceRef returned by DNSServiceRegister().

      flags:
        Currently ignored, reserved for future use.

      rrtype:
        The type of the record (e.g. kDNSServiceType_TXT,
        kDNSServiceType_SRV, etc.).

      rdata:
        A string containing the raw rdata to be contained in the added
        resource record.

      ttl:
        The time to live of the resource record, in seconds.  Pass 0
        to use a default value.

      return value:
        A DNSRecordRef instance, which may be passed to
        DNSServiceUpdateRecord() or DNSServiceRemoveRecord().  If
        sdRef is closed, the DNSRecordRef is also invalidated and may
        not be used further.

    """

    _NO_DEFAULT.check(rrtype)
    _NO_DEFAULT.check(rdata)

    rdlen, rdata = _string_to_length_and_void_p(rdata)

    _global_lock.acquire()
    try:
        RecordRef = _DNSServiceAddRecord(sdRef,
                                         flags,
                                         rrtype,
                                         rdlen,
                                         rdata,
                                         ttl)
    finally:
        _global_lock.release()

    sdRef._add_record_ref(RecordRef)

    return RecordRef


def DNSServiceUpdateRecord(
    sdRef,
    RecordRef = None,
    flags = 0,
    rdata = _NO_DEFAULT,
    ttl = 0,
    ):

    """

    Update a registered resource record.  The record must either be:
      - The primary txt record of a service registered via
        DNSServiceRegister(), or
      - A record added to a registered service via
        DNSServiceAddRecord(), or
      - An individual record registered by DNSServiceRegisterRecord()

      sdRef:
        A DNSServiceRef returned by DNSServiceRegister() or
        DNSServiceCreateConnection().

      RecordRef:
        A DNSRecordRef returned by DNSServiceAddRecord(), or None to
        update the service's primary txt record.

      flags:
        Currently ignored, reserved for future use.

      rdata:
        A string containing the new rdata to be contained in the
        updated resource record.

      ttl:
        The time to live of the updated resource record, in seconds.

    """

    _NO_DEFAULT.check(rdata)

    rdlen, rdata = _string_to_length_and_void_p(rdata)

    _global_lock.acquire()
    try:
        _DNSServiceUpdateRecord(sdRef,
                                RecordRef,
                                flags,
                                rdlen,
                                rdata,
                                ttl)
    finally:
        _global_lock.release()


def DNSServiceRemoveRecord(
    sdRef,
    RecordRef,
    flags = 0,
    ):

    """

    Remove a record previously added to a service record set via
    DNSServiceAddRecord(), or deregister a record registered
    individually via DNSServiceRegisterRecord().

      sdRef:
        A DNSServiceRef returned by DNSServiceRegister() (if the
        record being removed was registered via DNSServiceAddRecord())
        or by DNSServiceCreateConnection() (if the record being
        removed was registered via DNSServiceRegisterRecord()).

      recordRef:
        A DNSRecordRef returned by DNSServiceAddRecord() or
        DNSServiceRegisterRecord().

      flags:
        Currently ignored, reserved for future use.

    """

    _global_lock.acquire()
    try:
        _DNSServiceRemoveRecord(sdRef,
                                RecordRef,
                                flags)
    finally:
        _global_lock.release()

    RecordRef._invalidate()


def DNSServiceBrowse(
    flags = 0,
    interfaceIndex = kDNSServiceInterfaceIndexAny,
    regtype = _NO_DEFAULT,
    domain = None,
    callBack = None,
    ):

    """

    Browse for instances of a service.

      flags:
        Currently ignored, reserved for future use.

      interfaceIndex:
        If non-zero, specifies the interface on which to browse for
        services.  Most applications will pass
        kDNSServiceInterfaceIndexAny (0) to browse on all available
        interfaces.

      regtype:
        The service type being browsed for followed by the protocol,
        separated by a dot (e.g. "_ftp._tcp").  The transport protocol
        must be "_tcp" or "_udp".

      domain:
        If not None, specifies the domain on which to browse for
        services.  Most applications will not specify a domain,
        instead browsing on the default domain(s).

      callBack:
        The function to be called when an instance of the service
        being browsed for is found, or if the call asynchronously
        fails.  Its signature should be
        callBack(sdRef, flags, interfaceIndex, errorCode,
                 serviceName, regtype, replyDomain).

      return value:
        A DNSServiceRef instance.  The browse operation will run
        indefinitely until the client terminates it by closing the
        DNSServiceRef.

    Callback Parameters:

      sdRef:
        The DNSServiceRef returned by DNSServiceBrowse().

      flags:
        Possible values are kDNSServiceFlagsMoreComing and
        kDNSServiceFlagsAdd.

      interfaceIndex:
        The interface on which the service is advertised.  This index
        should be passed to DNSServiceResolve() when resolving the
        service.

      errorCode:
        Will be kDNSServiceErr_NoError (0) on success, otherwise will
        indicate the failure that occurred.  Other parameters are
        undefined if an error occurred.

      serviceName:
        The discovered service name.  This name should be displayed to
        the user and stored for subsequent use in the
        DNSServiceResolve() call.

      regtype:
        The service type, which is usually (but not always) the same
        as was passed to DNSServiceBrowse().  One case where the
        discovered service type may not be the same as the requested
        service type is when using subtypes: The client may want to
        browse for only those ftp servers that allow anonymous
        connections.  The client will pass the string
        "_ftp._tcp,_anon" to DNSServiceBrowse(), but the type of the
        service that's discovered is simply "_ftp._tcp".  The regtype
        for each discovered service instance should be stored along
        with the name, so that it can be passed to DNSServiceResolve()
        when the service is later resolved.

      replyDomain:
        The domain of the discovered service instance.  This may or
        may not be the same as the domain that was passed to
        DNSServiceBrowse().  The domain for each discovered service
        instance should be stored along with the name, so that it can
        be passed to DNSServiceResolve() when the service is later
        resolved.

    """

    _NO_DEFAULT.check(regtype)

    @_DNSServiceBrowseReply
    def _callback(sdRef, flags, interfaceIndex, errorCode, serviceName, regtype,
                  replyDomain, context):
        if callBack is not None:
            callBack(sdRef, flags, interfaceIndex, errorCode,
                     serviceName.decode(), regtype.decode(),
                     replyDomain.decode())

    _global_lock.acquire()
    try:
        sdRef = _DNSServiceBrowse(flags,
                                  interfaceIndex,
                                  regtype,
                                  domain,
                                  _callback,
                                  None)
    finally:
        _global_lock.release()

    sdRef._add_callback(_callback)

    return sdRef


def DNSServiceResolve(
    flags = 0,
    interfaceIndex = _NO_DEFAULT,
    name = _NO_DEFAULT,
    regtype = _NO_DEFAULT,
    domain = _NO_DEFAULT,
    callBack = None,
    ):

    """

    Resolve a service name discovered via DNSServiceBrowse() to a
    target host name, port number, and txt record.

    Note: Applications should NOT use DNSServiceResolve() solely for
    txt record monitoring; use DNSServiceQueryRecord() instead, as it
    is more efficient for this task.

    Note: When the desired results have been returned, the client MUST
    terminate the resolve by closing the returned DNSServiceRef.

    Note: DNSServiceResolve() behaves correctly for typical services
    that have a single SRV record and a single TXT record.  To resolve
    non-standard services with multiple SRV or TXT records,
    DNSServiceQueryRecord() should be used.

      flags:
        Currently ignored, reserved for future use.

      interfaceIndex:
        The interface on which to resolve the service.  If this
        resolve call is as a result of a currently active
        DNSServiceBrowse() operation, then the interfaceIndex should
        be the index reported in the browse callback.  If this resolve
        call is using information previously saved (e.g. in a
        preference file) for later use, then use
        kDNSServiceInterfaceIndexAny (0), because the desired service
        may now be reachable via a different physical interface.

      name:
        The name of the service instance to be resolved, as reported
        to the DNSServiceBrowse() callback.

      regtype:
        The type of the service instance to be resolved, as reported
        to the DNSServiceBrowse() callback.

      domain:
        The domain of the service instance to be resolved, as reported
        to the DNSServiceBrowse() callback.

      callBack:
        The function to be called when a result is found, or if the
        call asynchronously fails.  Its signature should be
        callBack(sdRef, flags, interfaceIndex, errorCode, fullname,
                 hosttarget, port, txtRecord).

      return value:
        A DNSServiceRef instance.  The resolve operation will run
        indefinitely until the client terminates it by closing the
        DNSServiceRef.

    Callback Parameters:

      sdRef:
        The DNSServiceRef returned by DNSServiceResolve().

      flags:
        Currently unused, reserved for future use.

      interfaceIndex:
        The interface on which the service was resolved.

      errorCode:
        Will be kDNSServiceErr_NoError (0) on success, otherwise will
        indicate the failure that occurred.  Other parameters are
        undefined if an error occurred.

      fullname:
        The full service domain name, in the form
        <servicename>.<protocol>.<domain>.

      hosttarget:
        The target hostname of the machine providing the service.

      port:
        The port, in host (not network) byte order, on which
        connections are accepted for this service.

      txtRecord:
        A string containing the service's primary txt record, in
        standard txt record format.

    """

    _NO_DEFAULT.check(interfaceIndex)
    _NO_DEFAULT.check(name)
    _NO_DEFAULT.check(regtype)
    _NO_DEFAULT.check(domain)

    @_DNSServiceResolveReply
    def _callback(sdRef, flags, interfaceIndex, errorCode, fullname, hosttarget,
                  port, txtLen, txtRecord, context):
        if callBack is not None:
            port = socket.ntohs(port)
            txtRecord = _length_and_void_p_to_string(txtLen, txtRecord)
            callBack(sdRef, flags, interfaceIndex, errorCode, fullname.decode(),
                     hosttarget.decode(), port, txtRecord)

    _global_lock.acquire()
    try:
        sdRef = _DNSServiceResolve(flags,
                                   interfaceIndex,
                                   name,
                                   regtype,
                                   domain,
                                   _callback,
                                   None)
    finally:
        _global_lock.release()

    sdRef._add_callback(_callback)

    return sdRef


def DNSServiceCreateConnection():

    """

    Create a connection to the daemon allowing efficient registration
    of multiple individual records.

      return value:
        A DNSServiceRef instance.  Closing it severs the connection
        and deregisters all records registered on this connection.

    """

    _global_lock.acquire()
    try:
        sdRef = _DNSServiceCreateConnection()
    finally:
        _global_lock.release()

    return sdRef


def DNSServiceRegisterRecord(
    sdRef,
    flags,
    interfaceIndex = kDNSServiceInterfaceIndexAny,
    fullname = _NO_DEFAULT,
    rrtype = _NO_DEFAULT,
    rrclass = kDNSServiceClass_IN,
    rdata = _NO_DEFAULT,
    ttl = 0,
    callBack = None,
    ):

    """

    Register an individual resource record on a connected
    DNSServiceRef.

    Note that name conflicts occurring for records registered via this
    call must be handled by the client in the callback.

      sdRef:
        A DNSServiceRef returned by DNSServiceCreateConnection().

      flags:
        Possible values are kDNSServiceFlagsShared or
        kDNSServiceFlagsUnique.

      interfaceIndex:
        If non-zero, specifies the interface on which to register the
        record.  Passing kDNSServiceInterfaceIndexAny (0) causes the
        record to be registered on all interfaces.

      fullname:
        The full domain name of the resource record.

      rrtype:
        The numerical type of the resource record
        (e.g. kDNSServiceType_PTR, kDNSServiceType_SRV, etc.).

      rrclass:
        The class of the resource record (usually
        kDNSServiceClass_IN).

      rdata:
        A string containing the raw rdata, as it is to appear in the
        DNS record.

      ttl:
        The time to live of the resource record, in seconds.  Pass 0
        to use a default value.

      callBack:
        The function to be called when a result is found, or if the
        call asynchronously fails (e.g. because of a name conflict).
        Its signature should be
        callBack(sdRef, RecordRef, flags, errorCode).

      return value:
        A DNSRecordRef instance, which may be passed to
        DNSServiceUpdateRecord() or DNSServiceRemoveRecord().  (To
        deregister ALL records registered on a single connected
        DNSServiceRef and deallocate each of their corresponding
        DNSRecordRefs, close the DNSServiceRef.)

    Callback Parameters:

      sdRef:
        The connected DNSServiceRef returned by
        DNSServiceCreateConnection().

      RecordRef:
        The DNSRecordRef returned by DNSServiceRegisterRecord().

      flags:
        Currently unused, reserved for future use.

      errorCode:
        Will be kDNSServiceErr_NoError on success, otherwise will
        indicate the failure that occurred (including name conflicts).
        Other parameters are undefined if an error occurred.

    """

    _NO_DEFAULT.check(fullname)
    _NO_DEFAULT.check(rrtype)
    _NO_DEFAULT.check(rdata)

    rdlen, rdata = _string_to_length_and_void_p(rdata)

    @_DNSServiceRegisterRecordReply
    def _callback(sdRef, RecordRef, flags, errorCode, context):
        if callBack is not None:
            callBack(sdRef, RecordRef, flags, errorCode)

    _global_lock.acquire()
    try:
        RecordRef = _DNSServiceRegisterRecord(sdRef,
                                              flags,
                                              interfaceIndex,
                                              fullname,
                                              rrtype,
                                              rrclass,
                                              rdlen,
                                              rdata,
                                              ttl,
                                              _callback,
                                              None)
    finally:
        _global_lock.release()

    sdRef._add_callback(_callback)
    sdRef._add_record_ref(RecordRef)

    return RecordRef


def DNSServiceQueryRecord(
    flags = 0,
    interfaceIndex = kDNSServiceInterfaceIndexAny,
    fullname = _NO_DEFAULT,
    rrtype = _NO_DEFAULT,
    rrclass = kDNSServiceClass_IN,
    callBack = None,
    ):

    """

    Query for an arbitrary DNS record.

      flags:
        Pass kDNSServiceFlagsLongLivedQuery to create a "long-lived"
        unicast query in a non-local domain.  Without setting this
        flag, unicast queries will be one-shot; that is, only answers
        available at the time of the call will be returned.  By
        setting this flag, answers (including Add and Remove events)
        that become available after the initial call is made will
        generate callbacks.  This flag has no effect on link-local
        multicast queries.

      interfaceIndex:
        If non-zero, specifies the interface on which to issue the
        query.  Passing kDNSServiceInterfaceIndexAny (0) causes the
        name to be queried for on all interfaces.

      fullname:
        The full domain name of the resource record to be queried for.

      rrtype:
        The numerical type of the resource record to be queried for
        (e.g. kDNSServiceType_PTR, kDNSServiceType_SRV, etc.).

      rrclass:
        The class of the resource record (usually
        kDNSServiceClass_IN).

      callBack:
        The function to be called when a result is found, or if the
        call asynchronously fails.  Its signature should be
        callBack(sdRef, flags, interfaceIndex, errorCode, fullname,
                 rrtype, rrclass, rdata, ttl).

      return value:
        A DNSServiceRef instance.  The query operation will run
        indefinitely until the client terminates it by closing the
        DNSServiceRef.

    Callback Parameters:

      sdRef:
        The DNSServiceRef returned by DNSServiceQueryRecord().

      flags:
        Possible values are kDNSServiceFlagsMoreComing and
        kDNSServiceFlagsAdd.  The Add flag is NOT set for PTR records
        with a ttl of 0, i.e. "Remove" events.

      interfaceIndex:
        The interface on which the query was resolved.

      errorCode:
        Will be kDNSServiceErr_NoError on success, otherwise will
        indicate the failure that occurred.  Other parameters are
        undefined if an error occurred.

      fullname:
        The resource record's full domain name.

      rrtype:
        The resource record's type (e.g. kDNSServiceType_PTR,
        kDNSServiceType_SRV, etc.).

      rrclass:
        The class of the resource record (usually
        kDNSServiceClass_IN).

      rdata:
        A string containing the raw rdata of the resource record.

      ttl:
        The resource record's time to live, in seconds.

    """

    _NO_DEFAULT.check(fullname)
    _NO_DEFAULT.check(rrtype)

    @_DNSServiceQueryRecordReply
    def _callback(sdRef, flags, interfaceIndex, errorCode, fullname, rrtype,
                  rrclass, rdlen, rdata, ttl, context):
        if callBack is not None:
            rdata = _length_and_void_p_to_string(rdlen, rdata)
            callBack(sdRef, flags, interfaceIndex, errorCode, fullname.decode(),
                     rrtype, rrclass, rdata, ttl)

    _global_lock.acquire()
    try:
        sdRef = _DNSServiceQueryRecord(flags,
                                       interfaceIndex,
                                       fullname,
                                       rrtype,
                                       rrclass,
                                       _callback,
                                       None)
    finally:
        _global_lock.release()

    sdRef._add_callback(_callback)

    return sdRef


def DNSServiceReconfirmRecord(
    flags = 0,
    interfaceIndex = kDNSServiceInterfaceIndexAny,
    fullname = _NO_DEFAULT,
    rrtype = _NO_DEFAULT,
    rrclass = kDNSServiceClass_IN,
    rdata = _NO_DEFAULT,
    ):

    """

    Instruct the daemon to verify the validity of a resource record
    that appears to be out of date (e.g. because tcp connection to a
    service's target failed).  Causes the record to be flushed from
    the daemon's cache (as well as all other daemons' caches on the
    network) if the record is determined to be invalid.

      flags:
        Currently unused, reserved for future use.

      interfaceIndex:
        If non-zero, specifies the interface of the record in
        question.  Passing kDNSServiceInterfaceIndexAny (0) causes all
        instances of this record to be reconfirmed.

      fullname:
        The resource record's full domain name.

      rrtype:
        The resource record's type (e.g. kDNSServiceType_PTR,
        kDNSServiceType_SRV, etc.).

      rrclass:
        The class of the resource record (usually
        kDNSServiceClass_IN).

      rdata:
        A string containing the raw rdata of the resource record.

    """

    _NO_DEFAULT.check(fullname)
    _NO_DEFAULT.check(rrtype)
    _NO_DEFAULT.check(rdata)

    rdlen, rdata = _string_to_length_and_void_p(rdata)

    _global_lock.acquire()
    try:
        _DNSServiceReconfirmRecord(flags,
                                   interfaceIndex,
                                   fullname,
                                   rrtype,
                                   rrclass,
                                   rdlen,
                                   rdata)
    finally:
        _global_lock.release()


def DNSServiceConstructFullName(
    service = None,
    regtype = _NO_DEFAULT,
    domain = _NO_DEFAULT,
    ):

    """

    Concatenate a three-part domain name (as returned by a callback
    function) into a properly-escaped full domain name.  Note that
    callback functions already escape strings where necessary.

      service:
        The service name; any dots or backslashes must NOT be escaped.
        May be None (to construct a PTR record name, e.g.
        "_ftp._tcp.apple.com.").

      regtype:
        The service type followed by the protocol, separated by a dot
        (e.g. "_ftp._tcp").

      domain:
        The domain name, e.g. "apple.com.".  Literal dots or
        backslashes, if any, must be escaped,
        e.g. "1st\. Floor.apple.com."

      return value:
        The resulting full domain name.

    """

    _NO_DEFAULT.check(regtype)
    _NO_DEFAULT.check(domain)

    _global_lock.acquire()
    try:
        fullName = _DNSServiceConstructFullName(service, regtype, domain)
    finally:
        _global_lock.release()

    return fullName.value.decode('utf-8')



################################################################################
#
# TXTRecord class
#
################################################################################



class TXTRecord(object):

    """

    A mapping representing a DNS TXT record.  The TXT record's
    name=value entries are stored as key/value pairs in the mapping.
    Although keys can be accessed in a case-insensitive fashion
    (meaning txt['foo'] and txt['FoO'] refer to the same value), key
    case is preserved in the wire representation of the record (so
    txt['FoO'] = 'bar' will generate a FoO=bar entry in the TXT
    record).  Key order is also preserved, so keys appear in the wire
    format in the order in which they were created.

    Note that in addition to being valid as a txtRecord parameter to
    DNSServiceRegister(), a TXTRecord instance can be used in place of
    a resource record data string (i.e. rdata parameter) with any
    function that accepts one.

    """

    def __init__(self, items={}, strict=True):
        """

        Create a new TXTRecord instance, initializing it with the
        contents of items.  If strict is true, then strict conformance
        to the DNS TXT record format will be enforced, and attempts to
        add a name containing invalid characters or a name/value pair
        whose wire representation is longer than 255 bytes will raise
        a ValueError exception.

        """

        self.strict = strict
        self._names = []
        self._items = {}

        for name, value in items.items():
            self[name] = value

    def __contains__(self, name):
        'Return True if name is a key in the record, False otherwise'
        return (name.lower() in self._items)

    def __iter__(self):
        'Return an iterator over name/value pairs'
        for name in self._names:
            yield self._items[name]

    def __len__(self):
        'Return the number of name/value pairs'
        return len(self._names)

    def __bool__(self):
        'Return False if the record is empty, True otherwise'
        return bool(self._items)

    def __str__(self):
        """

        Return the wire representation of the TXT record as a string.
        If self.strict is false, any name/value pair whose wire length
        if greater than 255 bytes will be truncated to 255 bytes.  If
        the record is empty, '\\0' is returned.

        """

        if not self:
            return '\0'

        parts = []
        for name, value in self:
            if value is None:
                item = name
            else:
                item = '%s=%s' % (name, value)
            if (not self.strict) and (len(item) > 255):
                item = item[:255]
            parts.append(chr(len(item)))
            parts.append(item)

        return ''.join(parts)

    def __getitem__(self, name):
        """

        Return the value associated with name.  The value is either
        None (meaning name has no associated value) or an str instance
        (which may be of length 0).  Raises KeyError if name is not a
        key.

        """
        return self._items[name.lower()][1]

    # Require one or more printable ASCII characters (0x20-0x7E),
    # excluding '=' (0x3D)
    _valid_name_re = re.compile(r'^[ -<>-~]+$')

    def __setitem__(self, name, value):
        """

        Add a name/value pair to the record.  If value is None, then
        name will have no associated value.  If value is a unicode
        instance, it will be encoded as a UTF-8 string.  Otherwise,
        value will be converted to an str instance.

        """

        stored_name = name
        name = name.lower()
        length = len(name)

        if value is not None:
            value = str(value)
            length += 1 + len(value)

        if self.strict and (length > 255):
            raise ValueError('name=value string must be 255 bytes or less')

        if name not in self._items:
            if self.strict and (self._valid_name_re.match(stored_name) is None):
                raise ValueError("invalid name: '%s'" % stored_name)
            self._names.append(name)

        self._items[name] = (stored_name, value)

    def __delitem__(self, name):
        """

        Remove name and its corresponding value from the record.
        Raises KeyError if name is not a key.

        """
        name = name.lower()
        del self._items[name]
        self._names.remove(name)

    @classmethod
    def parse(cls, data, strict=False):
        """

        Given a string data containing the wire representation of a
        DNS TXT record, parse it and return a TXTRecord instance.  The
        strict parameter is passed to the TXTRecord constructor.

        """

        txt = cls(strict=strict)

        while data:
            length = ord(data[0])
            item = data[1:length+1].split('=', 1)

            # Add the item only if the name is non-empty and there are
            # no existing items with the same name
            if item[0] and (item[0] not in txt):
                if len(item) == 1:
                    txt[item[0]] = None
                else:
                    txt[item[0]] = item[1]

            data = data[length+1:]

        return txt