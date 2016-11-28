# __init__.py

"""
Monkey patches cryptography's backend detection.
Objective: support py2exe/pyinstaller freezing.
https://github.com/pyca/cryptography/issues/2039#issuecomment-115432291
Required for RARfile.py and CertGen.py!
"""
try:
    from cryptography.hazmat import backends
    try:
        from cryptography.hazmat.backends.commoncrypto.backend import backend as backend_cc
    except ImportError:
        backend_cc = None
    try:
        from cryptography.hazmat.backends.openssl.backend import backend as backend_ossl
    except ImportError:
        backend_ossl = None
    backends._available_backends_list = [
        backend for backend in (backend_cc, backend_ossl) if backend is not None
    ]
except:
    # No crypto
    pass