#!/usr/bin/env python3

import os
import sys
import json
import click
import requests
import shutil
import json_merge_patch

from contextlib import suppress

from datetime import date
from datetime import datetime


def get_property_from_profile_file(the_property):
    """
    Returns the value of property from `./profile.json` if present.
    """
    with open('profile.json', 'r') as profile_file:
        return json.load(profile_file)[the_property]

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

def generate_schema_id_from_schema_name_url_and_version(schema_name, base_url, version):
    """
    Generates a schema $id from the schema's filename, the Profile's base_url, and the version of the Profile. https://json-schema.org/draft/2020-12/json-schema-core#name-the-id-keyword

    It assumes that the resulting schemas will be stored at {base_url}/{version}/schema/{schema_name}.json

    Important note: some popular source control systems are treated specially to give $id values which can resolve to the actual files. List of source control systems handled:

    https://github.com/user/repo -> https://raw.githubusercontent.com/{version}/schema/{schema_name}
    https://gitlab.com/user/repo -> https://gitlab.com/user/repo/-/raw/{version}/schema/{schema_name}
    https://git.sr.ht/~user/repo_name -> https://git.sr.ht/~user/repo/blob/{version}/schema/{schema_name}
    https://codeberg.org/user/repo -> https://codeberg.org/user/repo/raw/branch/{version}/schema/{schema_name}
    """

    # Can't guarantee that user has omitted a trailing / or not
    base_url = base_url.strip('/')

    # Github base urls: https://github.com/user/repo_name
    # Need transforming to https://raw.githubusercontent.com/organization_name/repo_name/version/schema/schema_file.json

    if base_url.startswith("https://github.com"):
        return f"{base_url.replace('https://github.com', 'https://raw.githubusercontent.com')}/{version}/schema/{schema_name}"

    # Gitlab base urls: https://gitlab.com/user/repo_name
    # Target format: https://gitlab.com/organization_name/repo_name/-/raw/{version}/{schema_name}

    if base_url.startswith("https://gitlab.com"):
        return f"{base_url}/-/raw/{version}/{schema_name}"

    # Sourcehut base urls https://git.sr.ht/~user/repo_name
    # Target format: https://git.sr.ht/~user/repo/blob/{version}/schema/{schema_name}
    if base_url.startswith("https://git.sr.ht"):
        return f"{base_url}/blob/{version}/schema/{schema_name}"

    # Codeberg base urls: https://codeberg.org/user/repo
    # Target format: https://codeberg.org/user/repo/raw/branch/{version}/schema/{schema_name}
    if base_url.startswith("https://codeberg.org"):
        return f"{base_url}/raw/branch/{version}/{schema_name}"

    return f"{base_url}/{version}/schema/{schema_name}"


def get_profile_schemas(hsds_base_schemas, profile_source_schemas):
    """
    Generates a dict of profile schemas which is the result of performing a JSON Merge Patch on the base HSDS Schemas and the profile source schemas.

    For schemas which only appear in either set, these schemas are copied.

    Parameters:
        * hsds_base_schemas (dict): mapping of schema filename to schema dict e.g. {'example.json': {}}
        * profile_source_schemas (dict): mapping of schema filename to schema dict e.g. {'example.json': {}}
    """

    # Profiles in HSDS have the following abilities: https://docs.openreferral.org/en/latest/hsds/profiles.html
      # - leave any given HSDS Schema intact
      # - patch any given HSDS schema, including removing it, based on filename
      # - add new schemas which aren't present in the original HSDS Schemas

    # Therefore we have to handle the following:
      # - schemas which only appear in the hsds_base_schemas dict (they might not have been overridden in the Profile)
      # - schemas which only appear in the profile_source_schemas dict (they might be entirely new schemas)
      # - schemas which appear in both dicts, meaning they need patching via https://tools.ietf.org/html/rfc7386 (provided by the json_merge_patch library)

    # Generate a dict based on XOR of keys across both dicts

    profile_schemas = {
            **{k: v for k,v in hsds_base_schemas if k not in profile_source_schemas},
            **{k: v for k,v in profile_source_schemas if k not in hsds_base_schemas}
            }

    # Get a list which is the intersection of the two keys (i.e. which schemas are in both dicts)
    schemas_to_patch = [k in hsds_base_schemas.keys() if k in profile_source_schemas]

    # Patch all the schemas which need patching by using the intersection as a set of keys
    profile_schemas.update(dict(map(lambda x : {x: json_merge_patch.merge(hsds_base_schemas[x], profile_source_schemas[x])}, schemas_to_patch)))

    # TODO: TEST this!
    # TODO: for each entry in the profile_schemas, replace the $id with the exception of openapi.json


def generate_profile(branch, base_url, version):
    """
    Generates a Profile by using patching the HSDS schemas with new schemas and patches defined in the `profile` directory.

    Parameters:
        * branch (str): the branch of the HSDS Schemas to use as a base for the Profile
        * base_url (str): the base_url of the profile to use as the $ids for schemas, etc.
        * version (str): the version of the profile to use in $ids for schemas etc.
    """

    #TODO move most of this logic into the get_profile_schemas function

    hsds_schemas = fetch_hsds_schemas(branch)
    profile_source_schemas = fetch_schemas_from_directory('profile')

        # Therefore we need to handle these cases efficiently. As best I can tell, it should be OK  to generate three lists of filenames: the intersection of the two (schemas which need patching), only in the hsds_schemas (needs copying with a new $id), and only in the profile schemas (needs copying with a new $id).

    hsds_schema_filenames = [item['filename'] for item in hsds_schemas]
    profile_schema_filenames = [item['filename'] for item in profile_source_schemas]
    
    filenames = {
            'intersection': [item for item in hsds_schema_filenames if item in profile_schema_filenames],
            'hsds_only': [item for item in hsds_schema_filenames if item not in profile_schema_filenames],
            'profile_only': [item for item in profile_schema_filenames if item not in hsds_schema_filenames]
            }

    
    # Easy to get a list of schemas we don't need to patch.

    profile_schemas = [item for item in hsds_schemas if item['filename'] in filenames['hsds_only']] + [item for item in profile_source_schemas if item['filename'] in filenames['profile_only']]
    
    # What we have now:
    # two lists that look like this: [{'filename': example.json, 'schema': {}}]
    # A list of filenames that represent an intersection e.g. 'example.json'
    # I need to: extract the schemas from each array where the value of the filename key is 'example.json', and merge the value of each 'schema' key together to produce a patched schema

    # Use list comprehension to flatten it, so I get a dict of {'example.json': schema
    # Map over the filenames as a key

    # We want a whole pile of profile schemas with new $ids


    # The one exception being `openapi.json`, which doesn't get an ID due to its format not requiring it.
    # However, we *do* need to take the patched `openapi.json` and then manually update all the $refs to point to our compiled schema versions if they match the old patterns.


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
    help="The Base URL of the Profile. Provide this to override the `base_url` property inside of profile.json",
)
@click.option(
    "--version",
    default=None,
    help="The version of the Profile you're generating. Provide this to override the `version` property inside of profile.json",
)
def generate(branch, url, version):
    """
    Generates and compiles Profile Schemas based on HSDS Schemas and the Patches in the `profile` directory.
    """

    if branch is None:
        branch = get_default_hsds_schema_branch()

    if url is None:
        url = get_property_from_profile_file("base_url")

    if version is None:
        version = get_property_from_profile_file("version")

    #TODO inform user that tasks are done

@cli.command()
def test():

    generate_profile("3.0","https://mrshll.uk", "0.0.1")


# ==================================
# !!! Program Entry !!!
# ==================================

if __name__ == "__main__":
    cli(obj={})
