#!/usr/bin/env python3
"""Pure text-extraction / renaming logic, shared by app.py and configure.py."""
from __future__ import annotations

import os
import re
from datetime import datetime


def extract_matches(text, pattern):
    matches = re.findall(pattern, text, re.IGNORECASE)
    return [match.upper() for match in matches]


# OCR commonly renders a hyphen as one of these lookalike dashes, and a hard space
# as a non-breaking space; normalize both before anything else runs.
_DASH_VARIANTS = '‐‑‒–—―'
_CHAR_NORMALIZATION = {c: '-' for c in _DASH_VARIANTS} | {'\xa0': ' '}


def _normalize(match):
    for old, new in _CHAR_NORMALIZATION.items():
        match = match.replace(old, new)
    return re.sub(r'\s+', '', match)


def autocorrect_match(match, autocorrect_config):
    """Clean up and reformat a raw match using autocorrect_config.

    `regex` parses the match into named groups (`(?P<name>...)`). Each group can be
    post-processed via `groups.<name>` (zero-padding, a character mapping, or a
    `force_first_char` rule copying a fixed value in based on another group's
    value), then `output_format` rebuilds the final string from those groups.
    """
    match = _normalize(match)

    for rule in autocorrect_config.get('rules', []):
        if re.match(rule['pattern'], match):
            match = re.sub(rule['pattern'], rule['replacement'], match)
            break

    parts = re.match(autocorrect_config['regex'], match)
    if parts is None:
        return match

    groups_config = autocorrect_config.get('groups', {})
    default_mapping = autocorrect_config.get('default_character_mapping', {})

    values = {}
    for name, value in parts.groupdict().items():
        if value is None:
            continue
        # Only groups listed under `groups:` are post-processed; others (e.g. an
        # alphabetic prefix) are kept exactly as matched.
        if name in groups_config:
            group_config = groups_config[name]

            zfill = group_config.get('zfill')
            if zfill:
                value = value.zfill(zfill)

            for old, new in group_config.get('character_mapping', default_mapping).items():
                value = value.replace(old, new)

        values[name] = value

    for name, group_config in groups_config.items():
        force = group_config.get('force_first_char')
        if not force or name not in values:
            continue
        if values.get(force['depends_on_group']) in force['when_value_in']:
            values[name] = force['value'] + values[name][1:]

    try:
        return autocorrect_config['output_format'].format(**values)
    except KeyError:
        return match


def build_filename(text, rename_config, autocorrect_config):
    """Return the target filename for `text`, or None if no identifier was found."""
    matches = extract_matches(text, rename_config['pattern'])
    if not matches:
        return None

    matches = [autocorrect_match(match, autocorrect_config) for match in matches]
    matches = sorted(set(matches))

    separator = rename_config.get('separator', '_')
    final_name = separator.join(matches) + '.pdf'

    max_length = rename_config.get('max_filename_length', 150) - len('.pdf')
    if len(final_name) > max_length:
        final_name = final_name[:max_length] + '.pdf'

    return final_name


def resolve_duplicate(output_dir, final_name, strategy):
    """Adapt `final_name` if it already exists in `output_dir`, per `strategy`."""
    if not os.path.exists(os.path.join(output_dir, final_name)):
        return final_name

    strategy = (strategy or 'increment').lower()

    if strategy == 'overwrite':
        return final_name

    if strategy == 'timestamp':
        suffix = datetime.now().strftime('%Y%m%d%H%M%S')
        return final_name[:-4] + f'_{suffix}.pdf'

    num = 1
    while os.path.exists(os.path.join(output_dir, final_name[:-4] + f'({num}).pdf')):
        num += 1
    return final_name[:-4] + f'({num}).pdf'
