#!/usr/bin/env python3

import os
import sys
import json
import click
import requests
import shutil

from contextlib import suppress

from datetime import date
from datetime import datetime


def get_openapi_url_from_base_url(base_url):
    return f"{base_url}/schema/openapi.json"


def get_default_hsds_schema_branch():
    """
    Queries the Github API for the HSDS Repo's information, and returns the default branch as a string
    """

    url = "https://api.github.com/repos/openreferral/specification"

    return requests.get(url).json()["default_branch"]


def fetch_schemas_from_github(branch=None):
    """
    Retrieves the HSDS schemas from Github and returns them as dicts

    Parameters:
        branch (str): Which branch of the HSDS Schemas to use. Defaults to 'None' which will use the default branch of the repo.

    Returns:
        list of dicts which represent the HSDS Schemas
    """

    url = "https://api.github.com/repos/openreferral/specification/contents/schema"

    if branch is not None:
        url += f"?ref={branch}"

    data = json.loads(requests.get(url).text)

    schemas = (
        []
    )  # Each item of this list will be a dict with a 'filename' key for the schema's filename (for cacheing, etc) and a 'schema' key containing the actual schema.

    for file in data:
        if (
            file["download_url"] is not None
        ):  # Skip directories e.g. 'compiled' and 'simple'
            schemas.append(
                {
                    "filename": file["name"],
                    "schema": json.loads(requests.get(file["download_url"]).text),
                }
            )

    return schemas


def get_cache_metadata_filepath():
    """
    Returns the location of the cache's metadata.json file as a string
    """

    return ".cache/metadata.json"


def get_cache_metadata():
    """
    Returns the cache's metadata.json file as a dict

    Returns:
        dict - resulting from json.loads on the metadata file
    """

    with open(get_cache_metadata_filepath(), "r") as cache_metadata_file:
        try:
            return json.load(cache_metadata_file)
        except (FileNotFoundError, json.JSONDecodeError):
            return (
                {}
            )  # This error occurs when there's a fresh metadata.json file or not metadata.json file. This just means that there's an empty cache, or thsat the program thinks there's an empty cache. It's safe to return an empty dict here because that just means a fresh fetch of that branch of the HSDS schemas.


def write_cache_metadata(metadata):
    """
    Writes the cache metadata to the cache's metadata.json file
    """
    with open(get_cache_metadata_filepath(), "w") as cache_metadata_file:
        cache_metadata_file.write(json.dumps(metadata))


def cache_schemas(branch, schemas):
    """
    Stores copies of the schemas in a local cache organised by branch and updates the cache metadata.json with the timestamp this branch was updated.

    Parameters:
        branch (str): the branch of the repo
        schemas (list): a list of schemas and filenames to write to the cache
    """

    cache_dir_for_branch = f".cache/{branch}"

    with suppress(FileNotFoundError):
        shutil.rmtree(cache_dir_for_branch)

    os.mkdir(cache_dir_for_branch)

    for schema_file in schemas:
        with open(
            f'{cache_dir_for_branch}/{schema_file["filename"]}', "w"
        ) as cache_schema_file:
            cache_schema_file.write(json.dumps(schema_file["schema"], indent=2))

    cache_metadata = get_cache_metadata()

    cache_metadata[branch] = datetime.now().isoformat()
    write_cache_metadata(cache_metadata)


def use_cached_schemas(branch):
    """
    Looks at the cache's metadata.json entry for the branch and decided whether to use the cached schemas or not based on the current time. If no entry is present, it defaults to returning False

    Return:
      bool: whether to use the cached schemas for that branch or not.
    """
    cache_metadata = get_cache_metadata()

    try:

        current_datetime = datetime.now()
        cached_schemas_datetime = datetime.fromisoformat(cache_metadata[branch])

        # Only use the cache if it's less than a day old. There's probably better heuristics than this out there, but this seems like an inoffensive place to start.

        return True if (current_datetime - cached_schemas_datetime).days <= 1 else False

    except:  # Exceptions likely mean that there's no cache metadata file, or key matching the branch string in the metadata file, so it's OK to say false not to use the cache here.
        return False


# ==================================
# CLI
# ==================================


@click.group()
def cli():
    """
    HSDS Profile Wizard
    """


@cli.command()
@click.option(
    "--title",
    prompt="What is the title of your Profile?",
    help="The title of your Profile",
    required=True,
)
@click.option(
    "--url",
    prompt="What is the base url of your Profile? e.g. 'https://example.org'",
    help="The base URL of your profile e.g. 'https://example-profile.org'",
    required=True,
)
@click.option(
    "--description", help="A brief human-readable description of your profile."
)
@click.option(
    "--docs-url",
    help="The url for your documentation e.g. https://docs.example-profile.org",
)
def init(title, url, description, docs_url):
    """
    Initialise a new Profile

    This command initialises a new HSDS Profile by doing the following:

    * Preparing a "profile.json" file in the current directory which contains useful metadata about the Profile\n
    * Setting up the current directory with `patches` and `schema` directories
    """

    profile_meta = {
        "title": title,
        "base_url": url,
        "openapi_url": get_openapi_url_from_base_url(url),
        "version": "0.0",
    }

    profile_meta["description"] = "" if description is None else description

    profile_meta["docs_url"] = "" if docs_url is None else docs_url

    with open("profile.json", "w") as profile_file:
        profile_file.write(json.dumps(profile_meta, indent=2))

    print("✓ Created profile.json based on user input")

    with suppress(FileExistsError):
        os.mkdir("profile")
        print(
            "✓ Created 'profile/' directory — put your schema patches and new schemas here."
        )
        os.mkdir("schema")
        print(
            "✓ Created 'schema/' directory — your patched schemas for your profile will be placed here."
        )

        os.mkdir(".cache")
        with open(".cache/metadata.json", "w") as cache_metadata_file:
            cache_metadata_file.write(
                "{}"
            )  # Create an empty cache file to start us off.
        print(
            "✓ Created '.cache/' directory — this will keep cached local copies of the HSDS schemas to save bandwidth and stopGithub rate-limiting you."
        )


@cli.command()
def test():

    print(use_cached_schemas("3.2"))


# ==================================
# !!! Program Entry !!!
# ==================================

if __name__ == "__main__":
    cli(obj={})
