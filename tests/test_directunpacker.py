import os
import time
import pytest
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from sabnzbd.directunpacker import DirectUnpacker
from sabnzbd.nzbstuff import NzbObject, NzbFile


class TestDirectUnpacker:
    @pytest.fixture
    def mock_cfg(self):
        """Mock configuration settings"""
        with patch("sabnzbd.cfg") as mock_cfg:
            mock_cfg.direct_unpack_threads.return_value = 4
            mock_cfg.direct_unpack.return_value = True
            mock_cfg.enable_unrar.return_value = True
            mock_cfg.use_parallel_unrar.return_value = True
            yield mock_cfg

    @pytest.fixture
    def test_files(self):
        """Create test RAR files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy RAR files of 1MB each
            for i in range(1, 11):
                file_path = os.path.join(temp_dir, f"test.part{i:02d}.rar")
                with open(file_path, "wb") as f:
                    f.write(b"x" * 1024 * 1024)
            yield temp_dir

    @pytest.fixture
    def setup_unpacker(self, mock_cfg, test_files):
        """Set up DirectUnpacker with test environment"""
        nzo = MagicMock(spec=NzbObject)
        nzo.download_path = test_files
        nzo.files = []
        nzo.password = None
        nzo.correct_password = None

        # Create test NZB files
        for i in range(1, 11):
            nzf = MagicMock(spec=NzbFile)
            nzf.filename = f"test.part{i:02d}.rar"
            nzf.setname = "test"
            nzf.vol = i
            nzf.assembled = True
            nzo.files.append(nzf)

        unpacker = DirectUnpacker(nzo)
        unpacker.thread_pool = ThreadPoolExecutor(max_workers=4)
        return unpacker

    def test_worker_unrar(self, setup_unpacker):
        """Test worker_unrar method"""
        unpacker = setup_unpacker
        nzf = unpacker.nzo.files[0]

        with patch.object(unpacker, "create_unrar_instance") as mock_create:
            unpacker.worker_unrar(nzf)
            mock_create.assert_called_once_with(nzf)

        # Test error handling
        with patch.object(
            unpacker, "create_unrar_instance", side_effect=Exception("Test error")
        ):
            with patch("logging.error") as mock_log:
                unpacker.worker_unrar(nzf)
                mock_log.assert_called_with(
                    f"Error processing {nzf.filename}: Test error"
                )

    @pytest.mark.benchmark
    def test_performance_comparison(self, setup_unpacker):
        """Benchmark parallel vs sequential processing"""
        unpacker = setup_unpacker
        unpacker.cur_setname = "test"

        def run_test(parallel: bool) -> float:
            unpacker.reset_active()
            if parallel:
                unpacker.use_parallel_unrar = True
            else:
                unpacker.use_parallel_unrar = False

            start_time = time.time()
            with patch.object(unpacker, "create_unrar_instance"):
                for nzf in unpacker.nzo.files:
                    unpacker.add(nzf)
            return time.time() - start_time

        # Run tests multiple times to get average
        parallel_times = []
        sequential_times = []
        iterations = 5

        for _ in range(iterations):
            sequential_times.append(run_test(False))
            parallel_times.append(run_test(True))

        avg_parallel = sum(parallel_times) / iterations
        avg_sequential = sum(sequential_times) / iterations

        assert avg_parallel < avg_sequential, "Parallel processing should be faster"

    def test_abort_cleanup(self, setup_unpacker):
        """Test cleanup during abort"""
        unpacker = setup_unpacker
        unpacker.cur_setname = "test"

        # Start some processing
        with patch.object(unpacker, "create_unrar_instance"):
            for nzf in unpacker.nzo.files[:3]:
                unpacker.add(nzf)

        # Test abort
        unpacker.abort()
        assert unpacker.killed is True
        assert not unpacker.next_sets
        assert not unpacker.success_sets
        assert unpacker.active_instance is None
