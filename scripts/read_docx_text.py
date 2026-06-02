from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_docx(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for para in root.iter(NS + "p"):
        text = "".join(node.text or "" for node in para.iter(NS + "t")).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def main() -> None:
    for raw_path in sys.argv[1:]:
        path = Path(raw_path)
        print(f"FILE {path.name}")
        print("\n".join(read_docx(path)))
        print("---")


if __name__ == "__main__":
    main()
