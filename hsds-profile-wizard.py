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


def get_profile_base_url_from_profile_file():
    """
    Returns the value of `base_url` from `./profile.json`
    """
    with open('profile.json', 'r') as profile_file:
        return json.load(profile_file)['base_url']

def get_openapi_url_from_base_url(base_url):
    return f"{base_url}/schema/openapi.json"

def get_default_hsds_schema_branch():
    """
    Queries the Github API for the HSDS Repo's information, and returns the default branch as a string
    """

    url = "https://api.github.com/repos/openreferral/specification"

    return requests.get(url).json()["default_branch"]


def fetch_schemas_from_github(branch):
    """
    Retrieves the HSDS schemas from Github and returns them as dicts

    Parameters:
        branch (str): Which branch of the HSDS Schemas to use.

    Returns:
        list of dicts which represent the HSDS Schemas
    """

    url = f"https://api.github.com/repos/openreferral/specification/contents/schema?ref={branch}"

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
            )  # This error occurs when there's a fresh metadata.json file or not metadata.json file. This just means that there's an empty cache, or that the program thinks there's an empty cache. It's safe to return an empty dict here because that just means a fresh fetch of that branch of the HSDS schemas.


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


def get_cached_schema_dir_path_from_branch(branch):
    """
    Returns the path for the directory where the cached schemas are for the given branch

    Return:
        str: the path of the directory where the cached schemas would be for the given branch
    """

    return f".cache/{branch}"

def use_cached_schemas(branch):
    """
    Looks at the cache's metadata.json entry for the branch and decided whether to use the cached schemas or not based on the current time. If no entry is present, it defaults to returning False

    Return:
      bool: whether to use the cached schemas for that branch or not.
    """

    # If we don't have any cached files for this branch, we can't use the cache
    if not os.path.isdir(get_cached_schema_dir_path_from_branch(branch)):
        return False


    try:
        cache_metadata = get_cache_metadata()

        current_datetime = datetime.now()
        cached_schemas_datetime = datetime.fromisoformat(cache_metadata[branch])

        # Only use the cache if it's less than a day old. There's probably better heuristics than this out there, but this seems like an inoffensive place to start.

        return True if (current_datetime - cached_schemas_datetime).days <= 1 else False

    except:  # Exceptions likely mean that there's no cache metadata file, or key matching the branch string in the metadata file, so it's OK to say false not to use the cache here.
        return False


def fetch_schemas_from_directory(directory):
    """
    Fetches Schemas from a local directory and returns a list of maps from filename to schemas

    Returns:
        * schemas (list): list of dicts mapping filenames to schemas
    """

    schemas = []

    for schema_file_path in os.listdir(directory):
        with open(f'{directory}/{schema_file_path}', 'r') as schema_file:
            schemas.append({'filename': schema_file_path, 'schema': json.load(schema_file)})

    return schemas

def fetch_hsds_schemas(branch):
    """
    Returns a list of dicts mapping filenames to HSDS schemas. Makes a decision about whether to use the cache or fetch fresh schemas.

    Return:
        * schemas (list): list of dicts mapping filenames to schemas loaded into memory as dicts
    """

    if use_cached_schemas(branch):
        return fetch_schemas_from_directory(get_cached_schema_dir_path_from_branch(branch))
    else:
        schemas = fetch_schemas_from_github(branch)
        cache_schemas(branch, schemas)
        return schemas


def generate_profile(branch, base_url):
    """
    Generates a Profile by using patching the HSDS schemas with new schemas and patches defined in the `profile` directory.

    Parameters:
        * branch (str): the branch of the HSDS Schemas to use as a base for the Profile
        * base_url (str): the base_url of the profile to use as the $ids for schemas, etc.
    """

    hsds_schemas = fetch_hsds_schemas(branch)
    profile_schemas = fetch_schemas_from_directory('profile')

    # Profiles have the following abilities:
      # - leave any given HSDS Schema intact
      # - patch any given HSDS schema, including removing it, based on filename
      # - add new schemas which aren't present in the original HSDS Schemas

    # Therefore we need to handle these cases efficiently. As best I can tell, it should be OK  to generate three lists of filenames: the intersection of the two (needs patching), only in the hsds_schemas (needs copying with a new $id), and only in the profile schemas (needs copying with a new $id).

    hsds_schema_filenames = [item['filename'] for item in hsds_schemas]
    profile_schema_filenames = [item['filename'] for item in profile_schemas]
    
    filenames = {
            'intersection': [item for item in hsds_schema_filenames if item in profile_schema_filenames],
            'hsds_only': [item for item in hsds_schema_filenames if item not in profile_schema_filenames],
            'profile_only': [item for item in profile_schema_filenames if item not in hsds_schema_filenames]
            }

    print(json.dumps(filenames))

    # Loop over the HSDS Schemas.
      # if there is a patch in the profile directory, perform the merge-patch
      # generate the $id from the base_url and apply it to the $id field (Note: might need a special case to handle openapi.json)
      # put it in the `schema` directory
      # remove its patch from the list of Profile schemas

    # Loop over the remaining Profile schemas
      # These can simply be put into the `schema` directory
      # Might be good practice to set override the $id fields though!

    # Compile schemas
      # Check for the presence of compilations.json
      # Get contents if present, else get a default list of compilations
      # for each compilation, check to see if there's a corresponding file.
         # if not, send a warning
         # else compile it

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
@click.option(
    "--branch",
    default=None,
    help="The branch of HSDS Schemas to use as the basis for the profile. Defaults to the latest release of HSDS",
)
@click.option(
    "--url",
    default=None,
    help="The Base URL of the Profile. Provide this if you don't want to use the URL provided in profile.json. If not provided, the program will look for the `base_url` value inside of profile.json inside this directory.",
)
def generate(branch, url):
    """
    Generates and compiles Profile Schemas based on HSDS Schemas and the Patches in the `profile` directory.
    """

    if branch is None:
        branch = get_default_hsds_schema_branch()

    if url is None:
        url = get_profile_base_url_from_profile_file()

    #TODO inform user that tasks are done

@cli.command()
def test():

    generate_profile("3.0","https://mrshll.uk")


# ==================================
# !!! Program Entry !!!
# ==================================

if __name__ == "__main__":
    cli(obj={})
