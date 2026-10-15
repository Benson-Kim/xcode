"""The CI workflow names the image the way Docker accepts it: the repository part of an
image reference is lower case, and the GitHub owner of this repository is not."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "xcode-api.yml"
OWNER = "Benson-Kim"
_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_REPOSITORY = re.compile(rf"^{_COMPONENT}(?:/{_COMPONENT})*$")


def _expand(value: str) -> str:
    """The shell and expression forms of the owner the workflow may use, as the runner
    expands them for a mixed-case owner."""
    lower = OWNER.lower()
    for form, expanded in (
        ("${{ github.repository_owner }}", OWNER),
        ("${GITHUB_REPOSITORY_OWNER,,}", lower),
        ("${GITHUB_REPOSITORY_OWNER}", OWNER),
        ("$GITHUB_REPOSITORY_OWNER", OWNER),
    ):
        value = value.replace(form, expanded)
    return value


def _image_names() -> list[str]:
    job = yaml.safe_load(WORKFLOW.read_text("utf-8"))["jobs"]["image"]
    names = [job.get("env", {}).get("IMAGE")]
    for step in job["steps"]:
        names += re.findall(r"IMAGE=([^\"'\s>]+)", step.get("run", ""))
    return [_expand(name) for name in names if name]


def test_the_image_job_names_its_image() -> None:
    assert _image_names()


def test_every_image_name_is_a_valid_docker_repository_for_a_mixed_case_owner() -> None:
    for name in _image_names():
        registry, _, repository = name.partition("/")
        assert registry == "ghcr.io", name
        assert _REPOSITORY.match(repository), name
