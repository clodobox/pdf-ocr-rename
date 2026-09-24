#!/usr/bin/env python3
"""Pure text-extraction / renaming logic, shared by app.py and configure.py."""
from __future__ import annotations

import os
import re
from datetime import datetime


def extract_matches(text, pattern):
    matches = re.findall(pattern, text, re.IGNORECASE)
    return [match.upper() for match in matches]


def autocorrect_match(match, autocorrect_config):
    match = match.replace(" ", "")

    for rule in autocorrect_config['rules']:
        if re.match(rule['pattern'], match):
            match = re.sub(rule['pattern'], rule['replacement'], match)
            break

    parts = re.match(autocorrect_config['regex'], match)

    if parts is None:
        return match

    prefix = parts.group(1)
    second_part = parts.group(2).zfill(2)
    last_part = parts.group(3).zfill(4)

    for old, new in autocorrect_config['format']['second_part_mapping'].items():
        second_part = second_part.replace(old, new)
    for old, new in autocorrect_config['format']['last_part_mapping'].items():
        last_part = last_part.replace(old, new)

    if prefix in autocorrect_config['format']['prefix_mapping']:
        second_part = "2" + second_part[1:]

    return f"{prefix}-{second_part}-{last_part}"


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
