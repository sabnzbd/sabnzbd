import socket
import http.client

import socks

import sabnzbd.cfg as cfg
import sabnzbd.misc as misc


def _restore_state(
    original_url,
    original_proxy,
    original_socket_cls,
    original_create_conn,
    original_http_connect,
    original_https_connect,
):
    """Put networking state back the way we found it."""
    cfg.socks5_proxy_url.set(original_url or "")
    if original_proxy:
        socks.set_default_proxy(*original_proxy)
    else:
        socks.set_default_proxy(None)
    socket.socket = original_socket_cls
    socket.create_connection = original_create_conn
    http.client.HTTPConnection.connect = original_http_connect
    http.client.HTTPSConnection.connect = original_https_connect

    # Re-apply the original proxy configuration to keep globals consistent for other tests.
    misc.set_socks5_proxy()


def test_set_socks5_proxy_patches_socket_and_http_connect():
    original_url = cfg.socks5_proxy_url()
    original_proxy = socks.socksocket.default_proxy
    original_socket_cls = misc._ORIGINAL_SOCKET
    original_create_conn = socket.create_connection
    original_http_connect = misc._ORIGINAL_HTTP_CONNECT
    original_https_connect = misc._ORIGINAL_HTTPS_CONNECT

    try:
        cfg.socks5_proxy_url.set("socks5://user:pass@127.0.0.1:1080")
        misc.set_socks5_proxy()

        assert socket.socket is socks.socksocket
        assert socket.create_connection is original_create_conn
        assert http.client.HTTPConnection.connect is misc._http_connect_with_proxy
        assert http.client.HTTPSConnection.connect is misc._https_connect_with_proxy
    finally:
        _restore_state(
            original_url,
            original_proxy,
            original_socket_cls,
            original_create_conn,
            original_http_connect,
            original_https_connect,
        )


def test_set_socks5_proxy_restores_originals_on_clear():
    original_url = cfg.socks5_proxy_url()
    original_proxy = socks.socksocket.default_proxy
    original_socket_cls = misc._ORIGINAL_SOCKET
    original_create_conn = socket.create_connection
    original_http_connect = misc._ORIGINAL_HTTP_CONNECT
    original_https_connect = misc._ORIGINAL_HTTPS_CONNECT

    try:
        cfg.socks5_proxy_url.set("socks5://127.0.0.1:1080")
        misc.set_socks5_proxy()

        cfg.socks5_proxy_url.set("")
        misc.set_socks5_proxy()

        assert socket.socket is original_socket_cls
        assert socket.create_connection is original_create_conn
        assert http.client.HTTPConnection.connect is original_http_connect
        assert http.client.HTTPSConnection.connect is original_https_connect
    finally:
        _restore_state(
            original_url,
            original_proxy,
            original_socket_cls,
            original_create_conn,
            original_http_connect,
            original_https_connect,
        )


def test_http_connection_uses_current_create_connection():
    original_url = cfg.socks5_proxy_url()
    original_proxy = socks.socksocket.default_proxy
    original_socket_cls = misc._ORIGINAL_SOCKET
    original_create_conn = socket.create_connection
    original_http_connect = misc._ORIGINAL_HTTP_CONNECT
    original_https_connect = misc._ORIGINAL_HTTPS_CONNECT
    original_socket_create = socket.create_connection

    # Simulate a connection created before enabling the proxy
    conn = http.client.HTTPConnection("example.com")

    try:
        cfg.socks5_proxy_url.set("socks5://127.0.0.1:1080")
        misc.set_socks5_proxy()

        def sentinel_create_connection(*args, **kwargs):
            raise RuntimeError("sentinel")

        socket.create_connection = sentinel_create_connection

        try:
            conn.connect()
        except RuntimeError as exc:
            assert "sentinel" in str(exc)
        else:
            raise AssertionError("HTTPConnection.connect did not use the current socket.create_connection")
    finally:
        socket.create_connection = original_socket_create
        _restore_state(
            original_url,
            original_proxy,
            original_socket_cls,
            original_create_conn,
            original_http_connect,
            original_https_connect,
        )
