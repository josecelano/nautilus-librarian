import os
from typing import List

import typer

from nautilus_librarian.domain.file_locator import file_locator
from nautilus_librarian.mods.console.domain.utils import (
    execute_console_command,
    get_current_working_directory,
)
from nautilus_librarian.mods.dvc.domain.utils import (
    extract_added_files_from_dvc_diff,
    extract_modified_media_file_list_from_dvd_diff_output,
)
from nautilus_librarian.mods.git.domain.repo import GitRepo
from nautilus_librarian.mods.namecodes.domain.filename import Filename
from nautilus_librarian.mods.namecodes.domain.filename_filters import filter_gold_images
from nautilus_librarian.mods.namecodes.domain.validate_filenames import (
    validate_filename,
)

app = typer.Typer()


class FileNotFoundException(Exception):
    """Raised when an expected file is not found"""

    pass


def validate_filenames_step(typer, dvc_diff):
    """
    Workflow step: it validates of the media file names.

    TODO: inject "console_printer" instead of "typer"
    so that we can test this step independently in the future.
    """
    if dvc_diff == "{}":
        typer.echo("No Gold image changes found")
        raise typer.Exit()

    filenames = extract_modified_media_file_list_from_dvd_diff_output(dvc_diff)

    for filename in filenames:
        try:
            validate_filename(filename)
            typer.echo(f"{filename} ✓")
        except ValueError as error:
            typer.echo(f"{filename} ✗ {error}", err=True)
            raise typer.Abort()


def get_new_gold_images_filenames_from_dvc_diff(dvc_diff) -> List[Filename]:
    """
    Parses the list of added Gold images from dvc diff output in json format
    and returns a list of Filenames.
    """
    added_files = extract_added_files_from_dvc_diff(dvc_diff)
    gold_images = filter_gold_images(added_files)
    return [Filename(gold_image) for gold_image in gold_images]


def auto_commit_base_images_step(typer, dvc_diff, git_repo_dir):
    """
    Workflow step: auto-commit new Base images generated during the workflow execution
    in previous steps.

    TODO:
    For each modified Gold image:
      [✓] 1. Calculate the corresponding Base image filename and filepath.
      [✓] 2. Check if the Base image exists.
      [✓] 3. Add the image to dvc.
      [✓] 4. Push the image to remote dvc storage.
      [ ] 5. Commit the image to the current branch with a signed commit. WIP

    Points 2 to 5 are different depending on whether we are adding,
    modifying or renaming the Gold image.
    """
    gold_images = get_new_gold_images_filenames_from_dvc_diff(dvc_diff)

    for gold_image in gold_images:
        corresponding_base_image = gold_image.generate_base_image_filename()
        corresponding_base_image_relative_path = (
            file_locator(corresponding_base_image) + "/" + str(corresponding_base_image)
        )
        corresponding_base_image_absolute_path = (
            git_repo_dir + "/" + corresponding_base_image_relative_path
        )

        typer.echo(
            f"New Gold image found: {gold_image} -> Base image: {corresponding_base_image_relative_path} ✓ "
        )

        if not os.path.isfile(corresponding_base_image_absolute_path):
            raise FileNotFoundException(
                f"Missing Base image: {corresponding_base_image_absolute_path}"
            )

        # TODO: replace by dvc mod functions (it's not merged yet)
        # Add the Base image to dvc
        execute_console_command(
            f"dvc add {corresponding_base_image_relative_path}", cwd=git_repo_dir
        )

        # TODO: replace by dvc mod functions (it's not merged yet)
        # Push the dvc image to the local "remote" storage
        execute_console_command(
            f"dvc push {corresponding_base_image_relative_path}.dvc", cwd=git_repo_dir
        )

        repo = GitRepo(git_repo_dir)

        # TODO: move to git mod
        git_global_user_name = execute_console_command(
            "git config --global --get user.name", cwd=git_repo_dir
        ).strip()

        # TODO: move to git mod
        git_global_user_email = execute_console_command(
            "git config --global --get user.email", cwd=git_repo_dir
        ).strip()

        # TODO: move to git mod
        git_global_user_signingkey = execute_console_command(
            "git config --global --get user.signingkey", cwd=git_repo_dir
        ).strip()

        # We are using the git global user configuration
        repo.set_git_global_user_config(git_global_user_name, git_global_user_email)

        commit_message = f"feat: new base image: {corresponding_base_image}"
        repo.create_signed_commit(
            corresponding_base_image_relative_path,
            commit_message,
            git_global_user_signingkey,
        )


@app.command("gold-drawings-processing")
def gold_drawings_processing(
    dvc_diff: str = typer.Argument("{}", envvar="INPUT_DVC_DIFF"),
    git_repo_dir: str = typer.Argument(
        get_current_working_directory, envvar="INPUT_GIT_REPO_DIR"
    ),
):
    """
    Gold Drawings Processing Workflow.

    This workflow process new or updated Gold images in a pull request:

    1. Get new or modified Gold images using dvc diff (TODO).

    2. Pull images from dvc remote storage (TODO).

    3. Validate filenames and filepaths.

    4. Validate image size (TODO).

    5. Generate Base image from Gold (change size and icc profile) (TODO).

    6. Auto-commit new Base images (TODO).

    Example:
        poetry run nautilus-librarian gold-drawings-processing '{"added":[{"path":"data/000001/32/000001-32.600.2.tif"}],"deleted":[],"modified":[],"renamed":[]}' # noqa
    """

    validate_filenames_step(typer, dvc_diff)
    auto_commit_base_images_step(typer, dvc_diff, git_repo_dir)


if __name__ == "__main__":
    app()
