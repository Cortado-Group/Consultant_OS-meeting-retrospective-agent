from agent_sdk.contract.manifest import load_manifest
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name("manifest.yaml")
manifest = load_manifest(MANIFEST_PATH)
AGENT_ID = manifest.agent.id
JOB_NAMES: tuple[str, ...] = tuple(job.name for job in manifest.jobs)
ACTION_NAMES: tuple[str, ...] = tuple(
    dict.fromkeys(action for job in manifest.jobs for action in job.actions)
)
