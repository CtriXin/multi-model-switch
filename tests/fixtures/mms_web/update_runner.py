"""Test-only deterministic release source. Production never reads this variable."""
import os
from pathlib import Path
from mms_web.update_coordinator import UpdateCoordinator
from mms_web.update_stage import validate_bundle, probe_release
original = UpdateCoordinator.__init__
def fixture_init(self, *args, **kwargs):
    def stage(root, tag):
        source = Path(os.environ['MMS_UPDATE_FIXTURE_SOURCE'])
        validate_bundle(source, tag)
        probe_release(source, tag)
        return source
    kwargs['stager'] = stage
    original(self, *args, **kwargs)
UpdateCoordinator.__init__ = fixture_init
from mms_web.__main__ import main
main()
