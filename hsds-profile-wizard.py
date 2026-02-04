#!/usr/bin/env python3

import os
import sys
import json
import click
import requests

from contextlib import suppress

from datetime import date
from datetime import datetime


def get_openapi_url_from_base_url(base_url):
    return f"{base_url}/schema/openapi.json"


#==================================
# CLI 
#==================================

@click.group()
def cli():
    """   
    HSDS Profile Wizard
    """
   
  


@cli.command()
@click.option("--title", prompt="What is the title of your Profile?", help="The title of your Profile", required=True)
@click.option("--url", prompt="What is the base url of your Profile? e.g. 'https://example.org'", help="The base URL of your profile e.g. 'https://example-profile.org'", required=True)
@click.option("--description", help="A brief human-readable description of your profile.")
@click.option("--docs-url", help="The url for your documentation e.g. https://docs.example-profile.org")
def init(title, url, description, docs_url):
    """
    Initialise a new Profile

    This command initialises a new HSDS Profile by doing the following:

    * Preparing a "profile.json" file in the current directory which contains useful metadata about the Profile\n
    * Setting up the current directory with `patches` and `schema` directories
    """

    profile_meta = {"title": title, "base_url": url, "openapi_url": get_openapi_url_from_base_url(url), "version": "0.0"}

    profile_meta['description'] = "" if description is None else description

    profile_meta['docs_url'] = "" if docs_url is None else docs_url

    with open('profile.json', 'w') as profile_file:
        profile_file.write(json.dumps(profile_meta, indent=2))

    print("✓ Created profile.json based on user input")

    with suppress(FileExistsError):
        os.mkdir("profile")
        print("✓ Created 'profile/' directory — put your schema patches and new schemas here.")
        os.mkdir("schema")
        print("✓ Created 'schema/' directory — your patched schemas for your profile will be placed here.")




#==================================
# !!! Program Entry !!!
#==================================

if __name__ == "__main__":
    cli(obj={})
