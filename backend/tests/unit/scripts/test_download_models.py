import subprocess
from pathlib import Path
from unittest.mock import patch

from backend.scripts import download_models


def test_download_silero_vad_falls_back_to_zip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ECHOFLOW_CACHE_DIR", str(tmp_path))
    target_dir = tmp_path / "vad" / "silero-vad"
    error = subprocess.CalledProcessError(
        returncode=128,
        cmd=["git", "clone"],
        stderr=b"network timeout",
    )

    with patch("backend.scripts.download_models.subprocess.run", side_effect=error), \
         patch("backend.scripts.download_models.download_silero_vad_from_zip", return_value=True) as fallback:
        download_models.download_silero_vad_model()

    fallback.assert_called_once_with(target_dir)
    output = capsys.readouterr().out
    assert "network timeout" in output
    assert "尝试使用 zip 下载" in output
