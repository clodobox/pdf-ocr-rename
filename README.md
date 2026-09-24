# PDF-OCR-RENAME

This program was created for a business need: the electronic management of delivery notes.

Here is my usage:

> Scanner -> Scan2file(SMB) -> OCR -> detect string of text -> rename
> PDF with the string of text

Thanks to OCRmyPDF for their Watchdog which works very well.
The OCRmyPDF watcher included in app.py is modified to preserve the original timestamp of the processed file.

This works on Synology x86-64 (with docker).
You just need to run the build commands below with "sudo" or use "Project" in Container Manager (DSM7.2+)

## What does it do?

1. Search for new files in "input".
2. app.py perform OCR on this file, rotate PDF pages if necessary
3. Autocorrect this text string and rename the PDF with
4. Moves file to processed

## How to run it ?
### Build docker container

This version allows you to mount either NFS or local shares for input/output folders.
You can choose what suits you best in docker-compose.yaml

Docker volume needed :

```
input
processed
log
```

(add sudo before command for synology)

```
docker-compose build
docker-compose up -d
```

**Or you can use `make` and the `Makefile` to build and run the containers.
Just run `make` to display the available commands. The `Makefile` detects if
`podman-compose` is installed and will try to use it. Otherwise it will fallback
to `docker-comspose`.**

## Configuration

Everything about how a file is matched and renamed lives in `config.yml`, under `rename:`:

* `pattern`: the regex used to find identifiers in the OCR'd text (case-insensitive).
* `separator`: what joins multiple identifiers found in the same file.
* `max_filename_length`: hard cap on the generated filename length, extension included.
* `duplicate_strategy`: what to do when the generated name already exists in `processed/` —
  `increment` (`name(1).pdf`, the default), `overwrite`, or `timestamp` (`name_20240101120000.pdf`).

`autocorrect:` still controls how a raw match is cleaned up and normalized (OCR typo fixes, prefix/character
mappings) before it's used in the filename.

### Trying out a pattern

`src/configure.py` lets you test a `pattern`/`separator`/`max_filename_length` against a sample text and
preview the resulting filename, without touching the running watcher:

```
python3 src/configure.py
```

It accepts a path to a `.pdf` or `.txt` file, or lets you paste text directly. At the end it prints a
`rename:` YAML snippet you can copy into `config.yml`.

## Information

* This is an unfinished project that will certainly never be completed.
  No notion of safety, optimization or simply common sense was used.
* This project is used in a very specific context and will certainly not be usable out-of-the-box by anyone.
* CPU requirements can be very high if you're processing a lot of files. It is possible to limit the number of threads in the config.yml.

## Next step
* ~~Fix "file not found" error~~
* ~~Group all parameters together so that anything useful can be changed quickly.~~
* ~~Making a version in a single docker~~
* Improved logging
