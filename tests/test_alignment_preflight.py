from pathlib import Path

import pytest

from analysis_scripts.XY_alignment import xy_align
from analysis_scripts.pipeline_utils import PipelineError


@pytest.mark.parametrize("conventional_present", [False, True])
def test_missing_alignment_inputs_fail_before_writing(tmp_path, conventional_present):
    experiment = tmp_path / "experiment with spaces"
    acquisition = experiment / "acquisition"
    acquisition.mkdir(parents=True)
    if conventional_present:
        (acquisition / "Conv_000.dax").touch()
    before = sorted(tmp_path.rglob("*"))

    with pytest.raises(PipelineError) as error:
        xy_align(str(experiment), ["647storm_"], 561)

    message = str(error.value)
    assert "missing" in message.lower()
    assert str(acquisition) in message
    assert "FFC_*.dax" in message
    assert ("Conv_*.dax" in message) is (not conventional_present)
    assert sorted(tmp_path.rglob("*")) == before
    assert Path(experiment).is_dir()
