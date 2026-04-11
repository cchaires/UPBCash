#!/usr/bin/env python3
"""
Convierte Reporte_Final_UPBCash_2026-I.md → PDF via WeasyPrint.
Ejecutar desde la carpeta Documentacion:
    python3 build_pdf.py
"""
import base64
import mimetypes
import os
import re
import sys

import markdown
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

DOC_DIR  = os.path.dirname(os.path.abspath(__file__))
MD_FILE  = os.path.join(DOC_DIR, "Reporte_Final_UPBCash_2026-I.md")
HTML_FILE = os.path.join(DOC_DIR, "Reporte_Final_UPBCash_2026-I.html")
PDF_FILE  = os.path.join(DOC_DIR, "Reporte_Final_UPBCash_2026-I.pdf")

CSS_CONTENT = """
@page {
    size: Letter;
    margin: 2.2cm 2.4cm 2.2cm 2.4cm;
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #888;
        font-family: Arial, sans-serif;
    }
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: Arial, 'Liberation Sans', sans-serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1a1a2e;
}

h1 {
    font-size: 17pt;
    font-weight: bold;
    color: #0d1b2a;
    text-align: center;
    margin-top: 8px;
    margin-bottom: 4px;
    padding-bottom: 6px;
    border-bottom: 3px solid #1565c0;
    page-break-after: avoid;
}
h2 {
    font-size: 13pt;
    font-weight: bold;
    color: #1565c0;
    margin-top: 20px;
    margin-bottom: 7px;
    padding: 3px 0 3px 8px;
    border-left: 4px solid #1565c0;
    border-bottom: 1px solid #bbdefb;
    page-break-after: avoid;
}
h3 {
    font-size: 11pt;
    font-weight: bold;
    color: #0d47a1;
    margin-top: 14px;
    margin-bottom: 5px;
    page-break-after: avoid;
}
h4 {
    font-size: 10.5pt;
    font-weight: bold;
    color: #1a237e;
    margin-top: 10px;
    margin-bottom: 4px;
    page-break-after: avoid;
}

p {
    margin-bottom: 7px;
    text-align: justify;
    orphans: 3;
    widows: 3;
}

ul, ol {
    margin: 5px 0 9px 20px;
}
li {
    margin-bottom: 3px;
    text-align: justify;
}

hr {
    border: none;
    border-top: 1.5px solid #bbdefb;
    margin: 16px 0;
}

/* ── Tablas ── */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 14px 0;
    font-size: 9pt;
    page-break-inside: auto;
}
thead { display: table-header-group; }
thead tr { background-color: #1565c0; color: #ffffff; }
th {
    padding: 6px 8px;
    text-align: left;
    font-weight: bold;
    border: 1px solid #0d47a1;
}
td {
    padding: 5px 8px;
    border: 1px solid #dde3f0;
    vertical-align: top;
}
tbody tr:nth-child(even) td { background-color: #f0f4fb; }

/* ── Código ── */
code {
    font-family: 'Courier New', Courier, monospace;
    font-size: 8.8pt;
    background-color: #f1f3f8;
    border: 1px solid #dde3f0;
    border-radius: 3px;
    padding: 1px 4px;
    color: #1a237e;
}
pre {
    background-color: #f5f7fc;
    border: 1px solid #dde3f0;
    border-left: 4px solid #1565c0;
    border-radius: 3px;
    padding: 9px 13px;
    margin: 9px 0 13px 0;
    font-size: 8pt;
    line-height: 1.45;
    page-break-inside: avoid;
    white-space: pre-wrap;
    word-break: break-all;
}
pre code {
    background: none;
    border: none;
    padding: 0;
    font-size: 8pt;
    color: #0d1b2a;
}

/* ── Imágenes: tamaño máximo estricto para evitar páginas en blanco ── */
figure {
    margin: 12px 0;
    text-align: center;
    page-break-inside: avoid;
    page-break-before: avoid;
}
figure img {
    max-width: 95%;
    max-height: 18cm;   /* nunca más alta que 3/4 de página */
    width: auto;
    height: auto;
    display: block;
    margin: 0 auto;
}
figcaption {
    font-size: 8pt;
    color: #555;
    margin-top: 4px;
    font-style: italic;
}
"""


def inline_images(html: str, base_dir: str) -> str:
    """
    Convierte <img src="archivo.png/jpg/..."> a data URI base64
    y envuelve en <figure> con <figcaption>.
    """
    def _replace(m):
        src = m.group(1)
        alt = m.group(2) if len(m.groups()) >= 2 and m.group(2) else ""
        img_path = os.path.join(base_dir, src)
        if os.path.exists(img_path):
            mime, _ = mimetypes.guess_type(img_path)
            mime = mime or "image/png"
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            data_uri = f"data:{mime};base64,{b64}"
            return (
                f'<figure>'
                f'<img src="{data_uri}" alt="{alt}"/>'
                f'<figcaption>{alt}</figcaption>'
                f'</figure>'
            )
        return m.group(0)

    # Patrones: src primero, alt primero
    html = re.sub(r'<img\s+src="([^"]+)"\s+alt="([^"]*)"[^>]*/?>',  _replace, html)
    html = re.sub(r'<img\s+alt="([^"]*)"\s+src="([^"]+)"[^>]*/?>',
                  lambda m: _replace(re.match(
                      r'<img\s+src="([^"]+)"\s+alt="([^"]*)"',
                      f'<img src="{m.group(2)}" alt="{m.group(1)}"',
                  )), html)
    return html


def build_html(md_content: str, base_dir: str) -> str:
    md_engine = markdown.Markdown(extensions=[
        "tables", "fenced_code", "nl2br", "sane_lists",
    ])
    body = md_engine.convert(md_content)
    body = inline_images(body, base_dir)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <title>Reporte Final UPBCash 2026-I</title>
</head>
<body>
{body}
</body>
</html>"""


def main():
    print(f"Leyendo: {MD_FILE}")
    with open(MD_FILE, "r", encoding="utf-8") as f:
        md_content = f.read()

    print("Convirtiendo Markdown → HTML con imágenes incrustadas...")
    html_content = build_html(md_content, DOC_DIR)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("Renderizando PDF con WeasyPrint...")
    font_config = FontConfiguration()
    css = CSS(string=CSS_CONTENT, font_config=font_config)
    HTML(string=html_content, base_url=DOC_DIR).write_pdf(
        PDF_FILE, stylesheets=[css], font_config=font_config,
    )

    size_kb = os.path.getsize(PDF_FILE) / 1024
    print(f"\n✓ PDF generado: {PDF_FILE}")
    print(f"  Tamaño: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
