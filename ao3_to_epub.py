import os
import re
import requests
import logging

from bs4 import BeautifulSoup
from ebooklib import epub


ao3_css_style = """
p.message { text-align: center; }
h1 { font-size: 1.5em; text-align: center; }
h2 { font-size: 1.25em; text-align: center; }
h2 { page-break-before: always; }
h3 { font-size: 1.25em; }
.byline { text-align: center; }
dl.tags { border: 1px solid; padding: 1em; }
dd { margin: -1em 0 0 10em; }
.endnote-link { font-size: .8em; }
/* List child related works under the labeling dt */
#afterword dd { margin: 1em 0 0 1em; }
#chapters { font-family: "Nimbus Roman No9 L", "Times New Roman", serif; padding: 1em; }
.userstuff { font-family: "Nimbus Roman No9 L", "Times New Roman", serif; padding: 1em; }
"""


def download_image(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.content


def extract_tags_as_copyright(dl):
    # Format metadata <dl> tags into HTML for a copyright page
    items = []
    for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
        key = dt.get_text(strip=True).rstrip(":")
        val = "".join(str(x) for x in dd.contents)
        items.append(f"<p><strong>{key}:</strong> {val}</p>")
    return "<section>" + "".join(items) + "</section>"


def parse_notes(curr):
    notes = []
    while True:
        curr = curr.find_next_sibling("p")
        if curr is None:
            break
        section = curr.get_text()
        content = curr.find_next_sibling("blockquote")
        if content is None:
            break
        notes.append((section, str(content)))
    return notes


def replace_images(book, tree):
    for img in tree.find_all("img"):
        img_url = img["src"]
        logging.info(f"Retrieving image from {img_url}")
        img_data = download_image(img_url)
        img_name = os.path.basename(img_url)
        epub_image = epub.EpubImage()
        epub_image.file_name = f"images/{img_name}"
        epub_image.media_type = f"image/{img_name.split('.')[-1]}"
        epub_image.content = img_data
        book.add_item(epub_image)
        # re-link
        img["src"] = epub_image.file_name
        img["style"] = "display:block; margin:0 auto;"


def ao3_html_to_epub(
    html_path, epub_path, include_author_notes=True, fetch_images=False
):
    # Parse HTML
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    book = epub.EpubBook()
    # css = soup.head.select('style[type="text/css"]')[0].get_text()
    ao3_css = epub.EpubItem(
        uid="ao3_style",
        file_name="style/ao3.css",
        media_type="text/css",
        content=ao3_css_style,
    )
    book.add_item(ao3_css)
    toc = []

    # -------- Preface --------
    preface = soup.find(id="preface")
    title = preface.find("b").get_text(strip=True)
    byline = preface.find("div", class_="byline")
    author = byline.find("a").get_text(strip=True)
    book.set_title(title)
    book.set_language(
        preface.find("dt", string="Language:")
        .find_next_sibling("dd")
        .get_text(strip=True)
    )
    book.add_author(author)
    titlepage = epub.EpubHtml(title="Title Page", file_name="titlepage.xhtml")
    titlepage.content = f"""<section id="titlepage" epub:type="titlepage"><div class="meta"><h1 epub:type="title">{title}</h1><div class="byline">By <b>{author}</b>.</div></div></section>"""
    titlepage.add_item(ao3_css)
    toc.append(epub.Link(titlepage.file_name, "Title Page", "titlepage"))
    book.add_item(titlepage)

    # Copyright page from tags dl
    tags_dl = preface.find("dl", class_="tags")
    copyright_html = extract_tags_as_copyright(tags_dl)
    copyright_item = epub.EpubHtml(title="Metadata", file_name="imprint.xhtml")
    copyright_item.content = copyright_html
    copyright_item.add_item(ao3_css)
    book.add_item(copyright_item)

    spine = [titlepage, copyright_item]
    # Preface page with remaining info
    booknotes = parse_notes(byline)
    if len(booknotes) > 0:
        for title, notes_block in booknotes:
            preface_html = f"<section><h2>{title}</h2>\n" + notes_block + "</section>"
            preface_item = epub.EpubHtml(
                title=title, file_name=f"{title.lower()}.xhtml"
            )
            preface_item.content = preface_html
            preface_item.add_item(ao3_css)
            toc.append(epub.Link(preface_item.file_name, title, title.lower()))
            book.add_item(preface_item)
            spine.append(preface_item)

    # -------- Chapters --------
    chapters_div = soup.find(id="chapters")
    chapter_sections = chapters_div.find_all("div", class_="meta group")
    if len(chapter_sections) == 0:
        # one-shot
        if fetch_images:
            replace_images(book, chapters_div)
        maintext = "".join(str(x) for x in chapters_div.contents)
        chap_item = epub.EpubHtml(title="Main Text", file_name="maintext.xhtml")
        chap_item.content = maintext
        chap_item.add_item(ao3_css)
        book.add_item(chap_item)
        spine.append(chap_item)
        toc.append(epub.Link(chap_item.file_name, "Main Text", "maintext"))
    else:
        # multi chapter
        chapters_toc = []
        for idx, meta in enumerate(chapter_sections, start=1):
            chap_title_loc = meta.find("h2", class_="heading")
            chap_title = chap_title_loc.get_text(strip=True)
            chapter_html = f"<h2>{chap_title}</h2>"

            # find beginning notes
            if include_author_notes:
                bnotes = parse_notes(chap_title_loc)
                if len(bnotes) > 0:
                    for sec, note in bnotes:
                        chapter_html += f"\n<h3>{sec}</h3>{note}"

            # chapter content is the next 'div.userstuff' after this meta
            content_div = meta.find_next_sibling("div", class_="userstuff")

            # Handle images inside chapter
            if fetch_images:
                replace_images(book, content_div)

            chapter_html += "".join(str(x) for x in content_div.contents)

            # find end notes
            if include_author_notes:
                enote = chapters_div.css.select(f"#endnotes{idx}")
                if len(enote) > 0:
                    note = str(enote[0].find("blockquote"))
                    chapter_html += f"\n<h3>Chapter End Notes</h3>{note}"

            chap_item = epub.EpubHtml(title=chap_title, file_name=f"chap_{idx}.xhtml")
            chap_item.content = chapter_html
            chap_item.add_item(ao3_css)
            book.add_item(chap_item)
            spine.append(chap_item)
            chapters_toc.append(
                epub.Link(chap_item.file_name, f"{idx}. {chap_title}", f"chap_{idx}")
            )
        toc.append((epub.Section("Chapters"), tuple(chapters_toc)))

    # -------- Afterword --------
    after = soup.find(id="afterword")
    if after:
        after_html = "<section>" + str(after) + "</section>"
        after_item = epub.EpubHtml(title="Afterword", file_name="afterword.xhtml")
        after_item.content = after_html
        book.add_item(after_item)
        spine.append(after_item)
        toc.append(epub.Link(after_item.file_name, "Afterword", "afterword"))

    # add default NCX and Nav
    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # write to file
    epub.write_epub(epub_path, book, {})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert AO3 HTML download to EPUB")
    parser.add_argument("html_file", help="Path to AO3 HTML file")
    parser.add_argument("epub_file", help="Output EPUB filename")
    parser.add_argument(
        "--exclude-notes", action="store_true", help="Exclude author notes in chapters"
    )
    parser.add_argument(
        "-i", "--fetch-images", action="store_true", help="Download linked images"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_const",
        dest="loglevel",
        const=logging.INFO,
    )
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    ao3_html_to_epub(
        args.html_file,
        args.epub_file,
        include_author_notes=not args.exclude_notes,
        fetch_images=args.fetch_images,
    )
