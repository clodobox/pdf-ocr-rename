#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pikepdf
import ocrmypdf
from pdfminer.high_level import extract_text
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
import yaml
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from renaming import build_filename, resolve_duplicate

with open('./config.yml', 'r') as file:
    config = yaml.safe_load(file)

OCR_CONFIG = {**config['ocr']}
RENAME_CONFIG = config['rename']
AUTOCORRECT_CONFIG = config['autocorrect']

def delete_old_logs(log_dir, retention_days):
    now = datetime.now()
    for file in log_dir.glob('*'):
        if file.is_file():
            modified_time = datetime.fromtimestamp(file.stat().st_mtime)
            if (now - modified_time).days > retention_days:
                file.unlink()

def setup_logging(config):
    log_dir = Path(config['logging']['directory'])
    log_dir.mkdir(parents=True, exist_ok=True)  # Crée le dossier "log" s'il n'existe pas

    log_file = log_dir / config['logging']['filename']
    log_level = getattr(logging, config['logging']['level'].upper())
    log_format = config['logging']['format']

    if config['logging']['mode'] == 'daily':
        handler = TimedRotatingFileHandler(log_file, when='midnight', backupCount=config['logging']['backup_count'])
    else:
        max_bytes = config['logging']['max_size']
        handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=config['logging']['backup_count'])

    handler.setFormatter(logging.Formatter(log_format))

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.addHandler(handler)

    # Supprimez les anciens fichiers log
    delete_old_logs(log_dir, config['logging']['retention_days'])

setup_logging(config)

# pylint: disable=logging-format-interpolation

def move_to_error_folder(file_path, error_dir):
    file_path = Path(file_path)
    if not file_path.exists():
        return False
    Path(error_dir).mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(Path(error_dir) / file_path.name))
    return True

def wait_for_file_ready(file_path):
    retries = OCR_CONFIG.get('retries_loading_file', 5)  # Get the number of retries from the config, default to 5
    poll_seconds = OCR_CONFIG.get('poll_new_file_seconds', 5)  # Get the number of seconds to wait between retries, default to 5

    for i in range(retries):
        try:
            pdf = pikepdf.open(file_path)
            pdf.close()
            return True
        except (FileNotFoundError, pikepdf._core.PdfError) as e:
            if i == retries - 1:
                logging.info(f'[watcher] Gave up waiting for {file_path} to become ready')
                return False
            else:
                logging.info(f'[watcher] File {file_path} is not ready yet')
                time.sleep(poll_seconds)

def execute_ocrmypdf(file_path):
    logger = logging.getLogger()
    ocr_args = {
        'language': OCR_CONFIG.get('language'),
        'image_dpi': OCR_CONFIG.get('image_dpi'),
        'use_threads': OCR_CONFIG.get('use_threads'),
        'author': OCR_CONFIG.get('author'),
        'subject': OCR_CONFIG.get('subject'),
        'rotate_pages': OCR_CONFIG.get('rotate_pages'),
        'remove_background': OCR_CONFIG.get('remove_background'),
        'deskew': OCR_CONFIG.get('deskew'),
        'oversample': OCR_CONFIG.get('oversample'),
        'optimize': OCR_CONFIG.get('optimize'),
        'tesseract_thresholding': OCR_CONFIG.get('tesseract_thresholding'),
        'tesseract_timeout': OCR_CONFIG.get('tesseract_timeout'),
        'rotate_pages_threshold': OCR_CONFIG.get('rotate_pages_threshold'),
        'pdfa_image_compression': OCR_CONFIG.get('pdfa_image_compression'),
        'progress_bar': OCR_CONFIG.get('progress_bar'),
        'jpg_quality': OCR_CONFIG.get('jpg_quality'),
        'png_quality': OCR_CONFIG.get('png_quality'),
        'jbig2_lossy': OCR_CONFIG.get('jbig2_lossy'),
        'jbig2_page_group_size': OCR_CONFIG.get('jbig2_page_group_size'),
        'tesseract_oem': OCR_CONFIG.get('tesseract_oem'),
        'force_ocr': OCR_CONFIG.get('force_ocr'),
    }
    
    ocr_args = {k: v for k, v in ocr_args.items() if v is not None}
    ocr_args.update(OCR_CONFIG['ocr_json_settings'])
    
    file_path = Path(file_path)
    output_path = Path(OCR_CONFIG['output_directory']) / file_path.name

    logger.info("[watcher] " + "-" * 20)
    logger.info(f'[watcher] New file: {file_path}. Waiting until fully loaded...')
    if not wait_for_file_ready(file_path):
        logger.info(f"[watcher] Gave up waiting for {file_path} to become ready")
        return
    logger.info(f'[watcher] Attempting to OCRmyPDF to: {output_path}')

    if OCR_CONFIG['backup_directory']:
        backup_path = Path(OCR_CONFIG['backup_directory']) / file_path.name
        logger.info(f'[watcher] Backing up file to: {backup_path}')
        shutil.copy2(file_path, backup_path)

    try:
        exit_code = ocrmypdf.ocr(
            input_file=str(file_path),
            output_file=str(output_path),
            **ocr_args,
        )
    except (ValueError, ocrmypdf.ExitCodeException) as e:
        logger.error(f"[watcher] OCRmyPDF failed with error: {str(e)}")
        if move_to_error_folder(file_path, OCR_CONFIG['error_directory']):
            logger.info(f'[watcher] Moved file with error to error folder: {file_path}')
        return

    if exit_code == 0:
        if OCR_CONFIG['on_success_delete']:
            logger.info(f'[watcher] OCR is done. Deleting: {file_path}')
            file_path.unlink()
        else:
            logger.info('[watcher] OCR is done')
        
        process_pdf(output_path)
    else:
        logger.info('[watcher] OCR is done with errors')

def process_pdf(path):
    path_str = str(path)
    if not path_str.endswith('.pdf'):
        return

    print(f'[renamer] Processing file: {path_str}')
    try:
        text = extract_text(path_str)
        final_name = build_filename(text, RENAME_CONFIG, AUTOCORRECT_CONFIG)
        if final_name is None:
            return

        output_dir = os.path.dirname(path_str)
        # os.rename overwrites an existing destination on POSIX, which is how the
        # 'overwrite' duplicate_strategy takes effect.
        final_name = resolve_duplicate(output_dir, final_name, RENAME_CONFIG.get('duplicate_strategy'))
        os.rename(path_str, os.path.join(output_dir, final_name))
        print(f'[renamer] Processed file: {final_name}')
    except Exception as e:
        print(f'[renamer] Error processing file: {path_str}. Error: {e}')
        if move_to_error_folder(path_str, OCR_CONFIG['error_directory']):
            print(f'[renamer] Moved file with error to error folder: {path_str}')

class HandleObserverEvent(PatternMatchingEventHandler):
    def on_any_event(self, event):
        if event.event_type in ['created']:
            execute_ocrmypdf(event.src_path)

def ensure_directory_exists(directory):
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f'[watcher] Created directory: {directory}')

def main():
    ocrmypdf.configure_logging(
        verbosity=(
            ocrmypdf.Verbosity.default
            if OCR_CONFIG['loglevel'] != 'DEBUG'
            else ocrmypdf.Verbosity.debug
        ),
        manage_root_logger=True,
    )
    logging.getLogger().setLevel(OCR_CONFIG['loglevel'])
    logging.info(
        f"[watcher] Starting OCRmyPDF watcher with config:\n"
        f"Input Directory: {OCR_CONFIG['input_directory']}\n"
        f"Output Directory: {OCR_CONFIG['output_directory']}\n"
    )
    logging.debug(
        f"[watcher] OCR_CONFIG: {OCR_CONFIG}\n"
        f"AUTOCORRECT_CONFIG: {AUTOCORRECT_CONFIG}\n"
    )
    if 'input_file' in OCR_CONFIG['ocr_json_settings'] or 'output_file' in OCR_CONFIG['ocr_json_settings']:
        logging.error('[watcher] OCR_JSON_SETTINGS should not specify input file or output file')
        sys.exit(1)
    
    ensure_directory_exists(OCR_CONFIG['input_directory'])
    ensure_directory_exists(OCR_CONFIG['output_directory'])
    ensure_directory_exists(OCR_CONFIG['backup_directory'])

    handler = HandleObserverEvent(patterns=OCR_CONFIG['patterns'])
    if OCR_CONFIG['use_polling']:
        observer = PollingObserver()
    else:
        observer = Observer()
    observer.schedule(handler, OCR_CONFIG['input_directory'], recursive=False)
    observer.start()
    logging.info('[watcher] Watching for new files...')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()