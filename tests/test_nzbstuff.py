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
    @pytest.mark.parametrize(
        "argument, name, password",
        [
            ("my_awesome_nzb_file{{password}}", "my_awesome_nzb_file", "password"),
            ("file_with_text_after_pw{{passw0rd}}_[180519]", "file_with_text_after_pw", "passw0rd"),
            ("file_without_pw", "file_without_pw", None),
            ("multiple_pw{{first-pw}}_{{second-pw}}", "multiple_pw", "first-pw}}_{{second-pw"),  # Greed is Good
            ("デビアン", "デビアン", None),  # Unicode
            ("Gentoo_Hobby_Edition {{secret}}", "Gentoo_Hobby_Edition", "secret"),  # Space between name and password
            ("Mandrake{{top{{secret}}", "Mandrake", "top{{secret"),  # Double opening {{
            ("Красная}}{{Шляпа}}", "Красная}}", "Шляпа"),  # Double closing }}
            ("{{Jobname{{PassWord}}", "{{Jobname", "PassWord"),  # {{ at start
            ("Hello/kITTY", "Hello", "kITTY"),  # Notation with slash
            ("/Jobname", "/Jobname", None),  # Slash at start
            ("Jobname/Top{{Secret}}", "Jobname", "Top{{Secret}}"),  # Slash with braces
            ("Jobname / Top{{Secret}}", "Jobname", "Top{{Secret}}"),  # Slash with braces and extra spaces
            ("לינוקס/معلومات سرية", "לינוקס", "معلومات سرية"),  # LTR with slash
            ("לינוקס{{معلومات سرية}}", "לינוקס", "معلومات سرية"),  # LTR with brackets
            ("thư điện tử password=mật_khẩu", "thư điện tử", "mật_khẩu"),  # Password= notation
            ("password=PartOfTheJobname", "password=PartOfTheJobname", None),  # Password= at the start
            ("Job}}Name{{FTW", "Job}}Name{{FTW", None),  # Both {{ and }} present but incorrect order (no password)
            ("./Text", "./Text", None),  # Name would end up empty after the function strips the dot
        ],
    )
    def test_scan_password(self, argument, name, password):
        assert nzbstuff.scan_password(argument) == (name, password)

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

    @pytest.mark.parametrize(
        "subject, filename",
        [
            ('Great stuff (001/143) - "Filename.txt" yEnc (1/1)', "Filename.txt"),
            (
                '"910a284f98ebf57f6a531cd96da48838.vol01-03.par2" yEnc (1/3)',
                "910a284f98ebf57f6a531cd96da48838.vol01-03.par2",
            ),
            ('Subject-KrzpfTest [02/30] - ""KrzpfTest.part.nzb"" yEnc', "KrzpfTest.part.nzb"),
            (
                '[PRiVATE]-[WtFnZb]-[Supertje-_S03E11-12_-blabla_+_blabla_WEBDL-480p.mkv]-[4/12] - "" yEnc 9786 (1/1366)',
                "Supertje-_S03E11-12_-blabla_+_blabla_WEBDL-480p.mkv",
            ),
            (
                '[N3wZ] MAlXD245333\\::[PRiVATE]-[WtFnZb]-[Show.S04E04.720p.AMZN.WEBRip.x264-GalaxyTV.mkv]-[1/2] - "" yEnc  293197257 (1/573)',
                "Show.S04E04.720p.AMZN.WEBRip.x264-GalaxyTV.mkv",
            ),
            (
                'reftestnzb bf1664007a71 [1/6] - "20b9152c-57eb-4d02-9586-66e30b8e3ac2" yEnc (1/22) 15728640',
                "20b9152c-57eb-4d02-9586-66e30b8e3ac2",
            ),
            (
                "Re: REQ Author Child's The Book-Thanks much - Child, Lee - Author - The Book.epub (1/1)",
                "REQ Author Child's The Book-Thanks much - Child, Lee - Author - The Book.epub",
            ),
            ('63258-0[001/101] - "63258-2.0" yEnc (1/250) (1/250)', "63258-2.0"),
            (
                "Singer - A Album (2005) - [04/25] - 02 Sweetest Somebody (I Know).flac",
                "- 02 Sweetest Somebody (I Know).flac",
            ),
            ("<>random!>", "<>random!>"),
            ("nZb]-[Supertje-_S03E11-12_", "nZb]-[Supertje-_S03E11-12_"),
            ("Bla [Now it's done.exe]", "Now it's done.exe"),
            (
                '[PRiVATE]-[WtFnZb]-[Video_(2001)_AC5.1_-RELEASE_[TAoE].mkv]-[1/23] - "" yEnc 1234567890 (1/23456)',
                '[PRiVATE]-[WtFnZb]-[Video_(2001)_AC5.1_-RELEASE_[TAoE].mkv]-[1/23] - "" yEnc 1234567890 (1/23456)',
            ),
        ],
    )
    def test_name_extractor(self, subject, filename):
        assert nzbstuff.name_extractor(subject) == filename
