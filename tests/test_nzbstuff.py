"""
tests.test_nzbstuff - Testing functions in nzbstuff.py
"""


import sabnzbd.nzbstuff as nzbstuff


class TestNzbstuff:
    def test_scan_passwords(self):
        file_names = {
            "my_awesome_nzb_file{{password}}": {"my_awesome_nzb_file", "password"},
            "file_with_text_after_pw{{passw0rd}}_[310313]": {"my_awesome_nzb_file", "passw0rd"},
            "file_without_pw": {"file_without_pw", None},
            "file_with_multiple_pw{{first-pw}}_{{second-pw}}": {"file_with_multiple_pw", "first-pw"},
        }

        for file_name, password in file_names.items():
            assert nzbstuff.scan_password(file_name)[1] == password
            assert nzbstuff.scan_password(file_name)[2] == file_name
