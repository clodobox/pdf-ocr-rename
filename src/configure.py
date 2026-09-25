#!/usr/bin/env python3
"""Interactive helper to design and preview the extraction/renaming pattern
used by app.py, without touching the running watcher or config.yml."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from renaming import autocorrect_match, build_filename, extract_matches

CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config.yml'


def load_config():
    with open(CONFIG_PATH, 'r') as file:
        return yaml.safe_load(file)


def read_sample_text():
    print("Texte d'exemple : chemin vers un fichier .pdf ou .txt, ou 'paste' pour coller du texte.")
    source = input('> ').strip()

    if source.lower() == 'paste':
        print('Collez le texte, terminez par une ligne vide :')
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        return '\n'.join(lines)

    path = Path(source)
    if not path.exists():
        print(f'Fichier introuvable : {path}')
        sys.exit(1)
    if path.suffix.lower() == '.pdf':
        from pdfminer.high_level import extract_text
        return extract_text(str(path))
    return path.read_text()


def prompt(label, default):
    value = input(f'{label} [{default}]: ').strip()
    return value or default


def main():
    config = load_config()
    rename_config = dict(config['rename'])
    autocorrect_config = config['autocorrect']

    text = read_sample_text()

    while True:
        rename_config['pattern'] = prompt("Regex d'extraction", rename_config['pattern'])
        rename_config['separator'] = prompt('Séparateur', rename_config.get('separator', '_'))
        rename_config['max_filename_length'] = int(
            prompt('Longueur max du nom de fichier', rename_config.get('max_filename_length', 150))
        )

        raw_matches = extract_matches(text, rename_config['pattern'])
        print(f'\nCorrespondances brutes trouvées : {raw_matches or "aucune"}')

        corrected = [autocorrect_match(match, autocorrect_config) for match in raw_matches]
        print(f'Après autocorrect : {corrected or "aucune"}')

        final_name = build_filename(text, rename_config, autocorrect_config)
        print(f'Nom de fichier généré : {final_name or "(fichier ignoré, aucune correspondance)"}\n')

        if input('Tester une autre configuration ? [o/N] ').strip().lower() != 'o':
            break

    print('À coller dans config.yml, sous "rename:" :\n')
    print(yaml.safe_dump({'rename': rename_config}, allow_unicode=True, sort_keys=False))


if __name__ == '__main__':
    main()
