"""PDF helper: build tiny raw one/two-page PDFs with arbitrary MediaBox.

Hand-rolled bytes keep fixtures small and ensure dimension preflight is
exercised WITHOUT ever allocating a bitmap (PIL would need gigabytes for
a 20000pt page).
"""

NL = b"\n"


def _xref_pdf(objects: list[bytes], root_size: int) -> bytes:
    out = bytearray(b"%PDF-1.4" + NL)
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj".encode() + body + b"endobj" + NL
    xref_at = len(out)
    out += f"xref{NL.decode()}0 {root_size}{NL.decode()}0000000000 65535 f {NL.decode()}".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n {NL.decode()}".encode()
    out += (f"trailer<</Size {root_size}/Root 1 0 R>>{NL.decode()}"
            f"startxref{NL.decode()}").encode() + str(xref_at).encode() \
        + NL + b"%%EOF"
    return bytes(out)


def make_raw_pdf(media_w: float, media_h: float) -> bytes:
    page = (f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 {media_w} {media_h}]>>"
            ).encode()
    return _xref_pdf([
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        page,
    ], root_size=4)


def make_pdf_with_two_large_pages() -> bytes:
    page = b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 900 450]>>"
    return _xref_pdf([
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>",
        page,
        page,
    ], root_size=5)
