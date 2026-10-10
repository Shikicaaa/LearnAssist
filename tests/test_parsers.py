import io

import pytest

from app.modules.jobs import PermanentError
from app.modules.sources.parsers import (
    ParseError,
    SourceFormat,
    detect_format,
    parse_docx,
    parse_pdf,
    parse_plain_text,
    parse_text_file,
)
from tests.files import (
    LOREM,
    SERBIAN_FONT,
    add_rendered_break,
    docx_bytes,
    encrypt_pdf,
    make_docx,
    make_pdf,
    make_scanned_pdf,
    make_zip_bomb,
)


class TestDetectFormat:
    def test_pdf_and_docx_are_detected_by_content(self):
        assert detect_format(make_pdf([LOREM]), "a.pdf") == SourceFormat.PDF
        assert detect_format(docx_bytes(make_docx(["x"])), "a.docx") == SourceFormat.DOCX

    def test_content_wins_over_extension(self):
        assert detect_format(make_pdf([LOREM]), "notes.txt") == SourceFormat.PDF
        assert detect_format(io.BytesIO(b"%PDF-1.4 hello"), "x.pdf") == SourceFormat.PDF
        assert detect_format(io.BytesIO(b"plain text, not a pdf"), "x.pdf") is None

    def test_text_formats_use_extension_to_pick_txt_or_md(self):
        data = b"Zdravo, svete"
        assert detect_format(io.BytesIO(data), "a.txt") == SourceFormat.TXT
        assert detect_format(io.BytesIO(data), "A.MD") == SourceFormat.MD
        assert detect_format(io.BytesIO(data), "a.markdown") == SourceFormat.MD
        assert detect_format(io.BytesIO(data), "a.csv") is None
        assert detect_format(io.BytesIO(data), "noextension") is None

    @pytest.mark.parametrize(
        "payload",
        [b"", b"\x00\x01\x02binary", bytes(range(256)) * 4, b"PK\x03\x04 not really a zip"],
    )
    def test_binary_or_empty_content_is_rejected(self, payload):
        assert detect_format(io.BytesIO(payload), "a.txt") is None

    def test_zip_that_is_not_docx_is_rejected(self):
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("hello.txt", "hi")
        buffer.seek(0)
        assert detect_format(buffer, "a.docx") is None

    def test_stream_is_rewound(self):
        stream = make_pdf([LOREM])
        detect_format(stream, "a.pdf")
        assert stream.tell() == 0


class TestParsePdf:
    def test_extracts_text_with_page_numbers(self):
        doc = parse_pdf(make_pdf([f"Page one. {LOREM}", f"Page two. {LOREM}", f"Page 3. {LOREM}"]))
        assert [p.number for p in doc.pages] == [1, 2, 3]
        assert doc.page_count == 3
        assert "Page two" in doc.pages[1].text

    def test_blank_page_is_skipped_but_numbering_is_kept(self):
        doc = parse_pdf(make_pdf([LOREM, "", LOREM]))
        assert [p.number for p in doc.pages] == [1, 3]
        assert doc.page_count == 3

    @pytest.mark.skipif(not SERBIAN_FONT.exists(), reason="Liberation Sans font not installed")
    def test_serbian_diacritics_survive_extraction(self):
        text = "Šta je đak? Čaj, ćevapi i žaba su na stolu. Ђак и чај су на столу."
        doc = parse_pdf(make_pdf([text], serbian_font=True))
        for fragment in ("Šta je đak", "Čaj, ćevapi i žaba", "Ђак и чај"):
            assert fragment in doc.pages[0].text

    def test_scanned_pdf_is_rejected_with_clear_message(self):
        with pytest.raises(ParseError, match="scan"):
            parse_pdf(make_scanned_pdf())

    def test_password_protected_pdf_is_rejected(self):
        locked = encrypt_pdf(make_pdf([LOREM]), user_password="secret", owner_password="owner")
        with pytest.raises(ParseError, match="password"):
            parse_pdf(locked)

    def test_pdf_with_only_owner_password_is_readable(self):
        restricted = encrypt_pdf(make_pdf([LOREM]), user_password="", owner_password="owner")
        assert "quick brown fox" in parse_pdf(restricted).pages[0].text

    def test_corrupted_pdf_is_rejected(self):
        with pytest.raises(ParseError, match="could not be read"):
            parse_pdf(io.BytesIO(b"%PDF-1.4\nthis is garbage, not a pdf"))

    def test_truncated_pdf_is_rejected(self):
        data = make_pdf([LOREM]).getvalue()
        with pytest.raises(ParseError):
            parse_pdf(io.BytesIO(data[: len(data) // 2]))

    def test_page_limit_is_enforced(self):
        with pytest.raises(ParseError, match="limit is 2"):
            parse_pdf(make_pdf([LOREM] * 3), max_pages=2)

    def test_parse_errors_are_permanent_so_they_are_never_retried(self):
        assert issubclass(ParseError, PermanentError)


class TestParseDocx:
    def test_paragraphs_and_tables_are_read_in_order(self):
        document = make_docx(["Intro paragraph.", "Second paragraph."], [["A", "B"], ["1", "2"]])
        doc = parse_docx(docx_bytes(document))
        text = doc.pages[0].text
        order = [text.index(part) for part in ("Intro", "Second", "A | B", "1 | 2")]
        assert order == sorted(order)

    def test_no_page_numbers_without_rendered_markers(self):
        # A hard page break alone is not proof of real page numbers, so none are reported.
        doc = parse_docx(docx_bytes(make_docx(["First.", None, "Second."])))
        assert len(doc.pages) == 1 and doc.pages[0].number is None
        assert doc.page_count is None
        assert "First." in doc.pages[0].text and "Second." in doc.pages[0].text

    def test_page_numbers_from_rendered_page_breaks(self):
        document = make_docx(["Page one text.", "Page two text.", "Page three text."])
        add_rendered_break(document, 1)
        add_rendered_break(document, 2)
        doc = parse_docx(docx_bytes(document))
        assert [(p.number, p.text) for p in doc.pages] == [
            (1, "Page one text."),
            (2, "Page two text."),
            (3, "Page three text."),
        ]

    def test_hard_break_plus_rendered_break_counts_once(self):
        document = make_docx(["Page one.", None, "Page two."])
        add_rendered_break(document, 2)
        doc = parse_docx(docx_bytes(document))
        assert [p.number for p in doc.pages] == [1, 2]

    def test_empty_document_is_rejected(self):
        with pytest.raises(ParseError, match="no text"):
            parse_docx(docx_bytes(make_docx([])))

    def test_corrupted_docx_is_rejected(self):
        with pytest.raises(ParseError):
            parse_docx(io.BytesIO(b"PK\x03\x04 definitely not a real archive"))

    def test_zip_bomb_is_rejected_before_unpacking(self):
        with pytest.raises(ParseError, match="too large"):
            parse_docx(make_zip_bomb())


class TestParseText:
    def test_utf8_serbian_text_is_preserved(self):
        raw = "Šta je đak? Čaj, ćevapi, žaba.".encode()
        assert parse_text_file(io.BytesIO(raw)).pages[0].text == "Šta je đak? Čaj, ćevapi, žaba."

    def test_utf8_bom_is_removed(self):
        raw = "\ufeffZdravo".encode()
        assert parse_text_file(io.BytesIO(raw)).pages[0].text == "Zdravo"

    def test_windows_1250_files_are_decoded(self):
        raw = "Šta je đak? Čaj, ćevapi, žaba.".encode("cp1250")
        assert parse_text_file(io.BytesIO(raw)).pages[0].text == "Šta je đak? Čaj, ćevapi, žaba."

    def test_text_has_no_page_numbers(self):
        doc = parse_plain_text("Some text.")
        assert doc.pages[0].number is None and doc.page_count is None

    def test_line_endings_are_normalized_and_blank_runs_collapsed(self):
        text = parse_plain_text("a\r\nb\r\n\r\n\r\n\r\nc  \n").pages[0].text
        assert text == "a\nb\n\nc"

    def test_markdown_indentation_is_kept(self):
        md = "# Title\n\n```python\nif x:\n    run()\n```"
        assert "    run()" in parse_plain_text(md).pages[0].text

    @pytest.mark.parametrize("text", ["", "   \n\t  \n", "\x00\x00"])
    def test_empty_text_is_rejected(self, text):
        with pytest.raises(ParseError, match="empty"):
            parse_plain_text(text)

    def test_undecodable_bytes_are_rejected(self):
        with pytest.raises(ParseError, match="encoding"):
            parse_text_file(io.BytesIO(b"abc \x81\x8d\x8f\x90\x9d xyz"))
