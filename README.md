# AO3 HTML to EPUB

This script converts a downloaded AO3 fic in HTML to EPUB. The downloader on AO3 has trouble generating EPUB files for large fics, while directly converting from the HTML file using tools like pandoc never seem to get the job done perfectly. This script tries to fix that.

## Features

- Metadata with title and author; title page
- Well-formated table of content
- Toggle to remove chapter beginning/end notes
- Option to retrieve embedded images and include them in the EPUB file

## Limitations

- No validation of the input file
- Not the most efficient
- Hard-coded CSS; no user skin support currently
