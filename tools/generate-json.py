# ====================== BEGIN GPL LICENSE BLOCK ======================
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ======================= END GPL LICENSE BLOCK ========================
#
# This script is a prototype which generates a JSON file
# for use in the package manager add-on.

import os
import ast
import argparse
import logging
import urllib.parse
import json

logging.basicConfig(format='%(asctime)-15s %(levelname)8s %(name)s %(message)s',
                    level=logging.INFO)
log = logging.getLogger('generate-json')

REQUIRED_KEYS = ('name', 'blender')
RECOMMENDED_KEYS = ('author', 'description', 'location', 'wiki_url', 'category')
CURRENT_SCHEMA_VERSION = 1


def iter_addons(addons_dir: str) -> (str, str, str):
    """Generator, yields IDs and filenames of addons.

    If the addon is a package, yields its __init__.py as filename.
    """

    for item in os.scandir(addons_dir):
        if item.name.startswith('.'):
            continue

        base, ext = os.path.splitext(item.name)

        if item.is_dir():
            fname = os.path.join(item.path, '__init__.py')
            if not os.path.exists(fname):
                log.info('Skipping %s, it does not seem to be a Python package', item.path)
                continue

            yield (base, fname, '.zip')
        else:
            yield (base, item.path, '.py')


def parse_blinfo(addon_fname: str) -> dict:
    """Parses a Python file, returning its bl_info dict.

    Returns None if the file doesn't contain a bl_info dict.
    """

    log.debug('Parsing %s', addon_fname)

    with open(addon_fname) as infile:
        try:
            source = infile.read()
        except UnicodeDecodeError as ex:
            log.warning('Skipping addon: UnicodeDecodeError in %s: %s', addon_fname, ex)
            return None

    try:
        tree = ast.parse(source, addon_fname)
    except SyntaxError as ex:
        log.warning('Skipping addon: SyntaxError in %s: %s', addon_fname, ex)
        return None

    for body in tree.body:
        if body.__class__ != ast.Assign:
            continue

        if len(body.targets) != 1:
            continue

        if getattr(body.targets[0], 'id', '') != 'bl_info':
            continue

        return ast.literal_eval(body.value)

    log.warning('Unable to find bl_info dict in %s', addon_fname)
    return None


def blinfo_to_json(bl_info, addon_id, source, url) -> dict:
    """Augments the bl_info dict with information for the package manager.

    Also checks for missing required/recommended keys.

    :returns: the augmented dict, or None if there were missing required keys.
    """

    missing_req_keys = [key for key in REQUIRED_KEYS
                        if key not in bl_info]
    if missing_req_keys:
        log.warning('Addon %s misses required key(s) %s; skipping this addon.',
                    addon_id, ', '.join(missing_req_keys))
        return None

    missing_rec_keys = [key for key in RECOMMENDED_KEYS
                        if key not in bl_info]
    if missing_rec_keys:
        log.info('Addon %s misses recommended key(s) %s',
                 addon_id, ', '.join(missing_rec_keys))

    json_data = bl_info.copy()
    json_data.update({
        'download_url': url,
        'source': source,
    })

    return json_data


def parse_addons(addons_dir: str, addons_source: str, addons_base_url: str) -> dict:
    """Parses info of all addons in the given directory."""

    json_data = {}

    for (addon_id, addon_fname, addon_ext) in iter_addons(addons_dir):
        bl_info = parse_blinfo(addon_fname)
        if bl_info is None:
            # The reason why has already been logged.
            continue

        url = urllib.parse.urljoin(addons_base_url, addon_id + addon_ext)
        as_json = blinfo_to_json(bl_info, addon_id, addons_source, url)
        if as_json is None:
            # The reason why has already been logged.
            continue

        json_data[addon_id] = as_json

    return json_data


def parse_existing_index(index_fname: str) -> dict:
    """Parses an existing index JSON file, returning its 'addons' dict.

    Raises a ValueError if the schema version is unsupported.
    """

    log.info('Reading existing %s', index_fname)

    with open(index_fname, 'r', encoding='utf8') as infile:
        existing_data = json.load(infile)

    # Check the schema version.
    schema_version = existing_data.get('schema-version', '-missing-')
    if schema_version != CURRENT_SCHEMA_VERSION:
        log.fatal('Unable to load existing data, wrong schema version: %s',
                  schema_version)
        raise ValueError('Unsupported schema %s' % schema_version)

    addon_data = existing_data['addons']
    return addon_data


def write_index_file(index_fname: str, addon_data: dict):
    """Writes the index JSON file."""

    log.info('Writing addon index to %s', index_fname)
    with open(index_fname, 'w', encoding='utf8') as outfile:
        json.dump(addon_data, outfile, indent=4, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description='Generate index.json from addons dir.')

    parser.add_argument('--merge', action='store_true', default=False,
                        help='merge with any existing index.json file')
    parser.add_argument('--source', nargs='?', type=str, default='internal',
                        help='set the source of the addons')
    parser.add_argument('--base', nargs='?', type=str, default='http://localhost:8000/',
                        help='set the base download URL of the addons')
    parser.add_argument('dir', metavar='DIR', type=str,
                        help='addons directory')
    args = parser.parse_args()

    # Load the existing index.json if requested.
    if args.merge:
        addon_data = parse_existing_index('index.json')
    else:
        addon_data = {}

    new_addon_data = parse_addons(args.dir, args.source, args.base)
    addon_data.update(new_addon_data)

    final_json = {
        'schema-version': CURRENT_SCHEMA_VERSION,
        'addons': addon_data,
    }

    write_index_file('index.json', final_json)
    log.info('Done!')


if __name__ == '__main__':
    main()
