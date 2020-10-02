"""
tests.test_nzbstuff - Testing functions in nzbstuff.py
"""
import sabnzbd.nzbstuff as nzbstuff
from sabnzbd.config import ConfigCat
from sabnzbd.constants import NORMAL_PRIORITY
from sabnzbd.filesystem import globber

from tests.testhelper import *


@pytest.mark.usefixtures("clean_cache_dir")
class TestNZO:
    @set_config({"download_dir": SAB_CACHE_DIR})
    def test_nzo_basic(self):
        # Need to create the Default category, as we would in normal instance
        # Otherwise it will try to save the config
        def_cat = ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})

        # Create empty object, normally used to grab URL's
        nzo = nzbstuff.NzbObject("test_basic")
        assert nzo.work_name == "test_basic"
        assert not nzo.files
        assert not nzo.created

        # Create NZB-file to import
        nzb_data = create_and_read_nzb("basic_rar5")

        # Very basic test of NZO creation with data
        nzo = nzbstuff.NzbObject("test_basic_data", nzb=nzb_data)
        assert nzo.final_name == "test_basic_data"
        assert nzo.files
        assert nzo.files[0].filename == "testfile.rar"
        assert nzo.bytes == 120
        assert nzo.files[0].bytes == 120

        # work_name can be trimmed in Windows due to max-path-length
        assert "test_basic_data".startswith(nzo.work_name)
        assert os.path.exists(nzo.admin_path)

        # Check if there's an nzf file and the backed-up nzb
        assert globber(nzo.admin_path, "*.nzb.gz")
        assert globber(nzo.admin_path, "SABnzbd_nzf*")

        # Should have picked up the default category settings
        assert nzo.cat == "*"
        assert nzo.script == def_cat.script() == "None"
        assert nzo.priority == def_cat.priority() == NORMAL_PRIORITY
        assert nzo.repair and nzo.unpack and nzo.delete

        # TODO: More checks!


class TestNZBStuffHelpers:
    def test_scan_passwords(self):
        file_names = {
            "my_awesome_nzb_file{{password}}": "password",
            "file_with_text_after_pw{{passw0rd}}_[180519]": "passw0rd",
            "file_without_pw": None,
            "file_with_multiple_pw{{first-pw}}_{{second-pw}}": "first-pw",
        }

        for file_name, password in file_names.items():
            assert nzbstuff.scan_password(file_name)[1] == password

    def test_scan_passwords_filenames(self):
        file_names = {
            "my_awesome_nzb_file{{password}}": "my_awesome_nzb_file",
            "file_with_text_after_pw{{passw0rd}}_[310313]": "file_with_text_after_pw",
            "file_without_pw": "file_without_pw",
            "file_with_multiple_pw{{first-pw}}_{{second-pw}}": "file_with_multiple_pw",
        }

        for file_name, clean_file_name in file_names.items():
            assert nzbstuff.scan_password(file_name)[0] == clean_file_name

    def test_create_work_name(self):
        # Only test stuff specific for create_work_name
        # The sanitizing is already tested in tests for sanitize_foldername
        file_names = {
            "my_awesome_nzb_file.pAr2.nZb": "my_awesome_nzb_file",
            "my_awesome_nzb_file.....pAr2.nZb": "my_awesome_nzb_file",
            "my_awesome_nzb_file....par2..": "my_awesome_nzb_file",
            " my_awesome_nzb_file  .pAr.nZb": "my_awesome_nzb_file",
            "with.extension.and.period.par2.": "with.extension.and.period",
            "nothing.in.here": "nothing.in.here",
            "  just.space  ": "just.space",
            "http://test.par2  ": "http://test.par2",
        }

        for file_name, clean_file_name in file_names.items():
            assert nzbstuff.create_work_name(file_name) == clean_file_name
