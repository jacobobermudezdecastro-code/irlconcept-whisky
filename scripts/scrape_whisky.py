#!/usr/bin/env python3
"""
Scraper de ofertas de whisky en Amazon.es
Usa Playwright para navegar Amazon.es y extraer ofertas actuales.
Genera un archivo HTML con el informe diario.
"""

import json
import re
import sys
import os
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Instalando playwright...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    from playwright.sync_api import sync_playwright


def extract_price(text: str) -> float | None:
    """Extrae un precio de un string como '21,09â¬' o '21.09'."""
    if not text:
        return None
    match = re.search(r'(\d+)[,.](\d{2})', text)
    if match:
        return float(f"{match.group(1)}.{match.group(2)}")
    match = re.search(r'(\d+)', text)
    if match:
        return float(match.group(1))
    return None


def scrape_amazon_whisky() -> list[dict]:
    """Scrape whisky deals from Amazon.es using Playwright."""
    deals = []

    search_urls = [
        # Ofertas de whisky - ordenado por destacados
        "https://www.amazon.es/s?k=whisky+oferta&rh=n%3A6347789031&s=popularity-rank",
        # Whisky con descuento 10-50%
        "https://www.amazon.es/s?k=whisky&rh=n%3A6347789031%2Cp_8%3A10-50&s=popularity-rank",
        # Bourbon ofertas
        "https://www.amazon.es/s?k=bourbon+whisky&rh=n%3A6347789031&s=popularity-rank",
    ]

    seen_titles = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            viewport={"width": 1920, "height": 1080},
        )

        page = context.new_page()

        for url in search_urls:
            try:
                print(f"Navegando a: {url[:80]}...")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)  # Esperar carga dinÃ¡mica

                # Scroll para cargar mÃ¡s productos
                for _ in range(5):
                    page.evaluate("window.scrollBy(0, 800)")
                    page.wait_for_timeout(500)

                # Extraer productos
                products = page.query_selector_all('[data-component-type="s-search-result"]')
                print(f"  Encontrados {len(products)} resultados")

                for product in products:
                    try:
                        # TÃ­tulo y enlace
                        title_el = product.query_selector("h2 a span")
                        link_el = product.query_selector("h2 a")

                        if not title_el:
                            continue

                        title = title_el.inner_text().strip()

                        # Filtrar no-whisky
                        title_lower = title.lower()
                        skip_keywords = [
                            "cerveza", "vino", "ginebra", "gin ", "vodka", "ron ",
                            "tequila", "licor", "vermouth", "sangrÃ­a", "cava",
                            "copa", "vaso", "piedras", "hielo", "set de",
                            "pack de regalo", "lata", "refresco"
                        ]
                        whisky_keywords = [
                            "whisky", "whiskey", "bourbon", "scotch", "malt",
                            "blended", "single malt", "rye"
                        ]

                        if any(kw in title_lower for kw in skip_keywords):
                            continue
                        if not any(kw in title_lower for kw in whisky_keywords):
                            # Check brand names as fallback
                            brands = [
                                "johnnie walker", "glenfiddich", "macallan",
                                "talisker", "cardhu", "monkey shoulder",
                                "ballantine", "chivas", "j&b", "jameson",
                                "jack daniel", "jim beam", "maker's mark",
                                "hibiki", "yamazaki", "nikka", "suntory",
                                "laphroaig", "lagavulin", "caol ila",
                                "cragganmore", "singleton", "dewar",
                                "famous grouse", "passport", "cutty sark",
                                "grant's", "clan campbell", "label 5"
                            ]
                            if not any(b in title_lower for b in brands):
                                continue

                        # Deduplicar
                        title_key = re.sub(r'[^a-zÃ¡Ã©Ã­Ã³ÃºÃ±0-9]', '', title_lower)[:50]
                        if title_key in seen_titles:
                            continue
                        seen_titles.add(title_key)

                        href = link_el.get_attribute("href") if link_el else ""
                        if href and not href.startswith("http"):
                            href = f"https://www.amazon.es{href}"

                        # Precio actual
                        price_whole = product.query_selector(".a-price .a-price-whole")
                        price_fraction = product.query_selector(".a-price .a-price-fraction")

                        if not price_whole:
                            continue

                        current_price_str = price_whole.inner_text().strip().replace(".", "").replace(",", ".")
                        fraction = price_fraction.inner_text().strip() if price_fraction else "00"
                        current_price = float(f"{current_price_str}{fraction}") if "." not in current_price_str else float(current_price_str)

                        if current_price <= 0 or current_price > 500:
                            continue

                        # Precio original / recomendado
                        original_price = None
                        original_el = product.query_selector('.a-text-price .a-offscreen')
                        if original_el:
                            original_price = extract_price(original_el.inner_text())

                        if not original_el:
                            rec_el = product.query_selector('span:has-text("Recomendado:")')
                            if rec_el:
                                original_price = extract_price(rec_el.inner_text())

                        # Descuento
                        discount_pct = None
                        if original_price and original_price > current_price:
                            discount_pct = round((1 - current_price / original_price) * 100)

                        # Rating
                        rating = None
                        rating_el = product.query_selector('[aria-label*="de 5 estrellas"]')
                        if rating_el:
                            rating_text = rating_el.get_attribute("aria-label")
                            rating_match = re.search(r'(\d[,.]?\d?)', rating_text or "")
                            if rating_match:
                                rating = float(rating_match.group(1).replace(",", "."))

                        # Num reviews
                        num_reviews = None
                        reviews_el = product.query_selector('span[aria-label*="valoraciÃ³n"]')
                        if not reviews_el:
                            reviews_el = product.query_selector('.a-size-base.s-underline-text')
                        if reviews_el:
                            rev_text = reviews_el.inner_text().strip()
                            rev_text = rev_text.replace(".", "").replace(",", "")
                            rev_match = re.search(r'(\d+)', rev_text)
                            if rev_match:
                                num_reviews = int(rev_match.group(1))

                        # Tipo de oferta
                        deal_type = "Descuento"
                        badge_el = product.query_selector('.a-badge-text')
                        if badge_el:
                            badge_text = badge_el.inner_text().strip()
                            if "Primavera" in badge_text:
                                deal_type = "Oferta de Primavera"
                            elif "del dÃ­a" in badge_text.lower():
                                deal_type = "Oferta del DÃ­a"
                            elif "flash" in badge_text.lower():
                                deal_type = "Oferta Flash"
                            else:
                                deal_type = badge_text

                        # Precio por litro
                        price_per_unit = None
                        unit_el = product.query_selector('.a-price + span')
                        if unit_el:
                            unit_text = unit_el.inner_text()
                            unit_match = re.search(r'(\d+[,.]?\d*)\s*â¬/l', unit_text)
                            if unit_match:
                                price_per_unit = unit_match.group(0)

                        # Determinar tipo de whisky
                        whisky_type = "Whisky"
                        if "single malt" in title_lower or "puro de malta" in title_lower:
                            whisky_type = "Single Malt"
                        elif "bourbon" in title_lower or "jim beam" in title_lower or "jack daniel" in title_lower or "maker" in title_lower:
                            whisky_type = "Bourbon"
                        elif "japonÃ©s" in title_lower or "japanese" in title_lower or "hibiki" in title_lower or "yamazaki" in title_lower or "nikka" in title_lower:
                            whisky_type = "JaponÃ©s"
                        elif "irlandÃ©s" in title_lower or "irish" in title_lower or "jameson" in title_lower:
                            whisky_type = "IrlandÃ©s"
                        elif "blended" in title_lower or "mezcla" in title_lower:
                            whisky_type = "Blended"
                        elif any(b in title_lower for b in ["johnnie walker", "ballantine", "j&b", "dewar", "chivas", "passport", "grant", "famous"]):
                            whisky_type = "Blended"

                        deal = {
                            "title": title,
                            "url": href,
                            "current_price": current_price,
                            "original_price": original_price,
                            "discount_pct": discount_pct,
                            "rating": rating,
                            "num_reviews": num_reviews,
                            "deal_type": deal_type,
                            "price_per_unit": price_per_unit,
                            "whisky_type": whisky_type,
                        }
                        deals.append(deal)
                        print(f"  + {title[:60]}... -> {current_price}â¬ ({discount_pct or '?'}% off)")

                    except Exception as e:
                        print(f"  Error extrayendo producto: {e}")
                        continue

            except Exception as e:
                print(f"Error navegando {url[:50]}: {e}")
                continue

        browser.close()

    # Ordenar por descuento (mayor primero), luego por precio
    deals.sort(key=lambda d: (-(d["discount_pct"] or 0), d["current_price"]))

    return deals


def generate_html(deals: list[dict], output_path: str):
    """Genera el archivo HTML del informe."""

    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    date_display = today.strftime("%A, %d de %B de %Y").replace(
        "Monday", "Lunes"
    ).replace(
        "Tuesday", "Martes"
    ).replace(
        "Wednesday", "MiÃ©rcoles"
    ).replace(
        "Thursday", "Jueves"
    ).replace(
        "Friday", "Viernes"
    ).replace(
        "Saturday", "SÃ¡bado"
    ).replace(
        "Sunday", "Domingo"
    ).replace(
        "January", "enero"
    ).replace(
        "February", "febrero"
    ).replace(
        "March", "marzo"
    ).replace(
        "April", "abril"
    ).replace(
        "May", "mayo"
    ).replace(
        "June", "junio"
    ).replace(
        "July", "julio"
    ).replace(
        "August", "agosto"
    ).replace(
        "September", "septiembre"
    ).replace(
        "October", "octubre"
    ).replace(
        "November", "noviembre"
    ).replace(
        "December", "diciembre"
    )
    time_str = today.strftime("%H:%M")

    # EstadÃ­sticas
    num_deals = len(deals)
    best_discount = max((d["discount_pct"] for d in deals if d["discount_pct"]), default=0)
    prices = [d["current_price"] for d in deals]
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0
    spring_deals = sum(1 for d in deals if "Primavera" in d.get("deal_type", ""))

    # Leer template
    template_path = Path(__file__).parent.parent / "templates" / "report.html"
    template = template_path.read_text(encoding="utf-8")

    # Generar cards HTML
    cards_html = ""
    for deal in deals:
        stars = ""
        if deal["rating"]:
            full = int(deal["rating"])
            half = 1 if deal["rating"] - full >= 0.3 else 0
            empty = 5 - full - half
            stars = "&#9733;" * full + ("&#9734;" if half else "") + "&#9734;" * empty

        reviews_str = ""
        if deal["num_reviews"]:
            if deal["num_reviews"] >= 1000:
                reviews_str = f'{deal["num_reviews"]/1000:.1f}K'.replace('.0K', 'K')
            else:
                reviews_str = str(deal["num_reviews"])

        badges = ""
        if deal["discount_pct"]:
            badges += f'<span class="badge badge-discount">-{deal["discount_pct"]}%</span>\n'
        if "Primavera" in deal.get("deal_type", ""):
            badges += '<span class="badge badge-spring">Oferta de Primavera</span>\n'
        elif "Flash" in deal.get("deal_type", ""):
            badges += '<span class="badge badge-flash">Oferta Flash</span>\n'
        elif "DÃ­a" in deal.get("deal_type", ""):
            badges += '<span class="badge badge-spring">Oferta del DÃ­a</span>\n'
        badges += f'<span class="badge badge-type">{deal["whisky_type"]}</span>\n'

        original_html = ""
        if deal["original_price"]:
            original_html = f'<span class="price-original">{deal["original_price"]:.2f}&euro;</span>'

        unit_html = ""
        if deal["price_per_unit"]:
            unit_html = f'<div class="price-unit">{deal["price_per_unit"]}</div>'

        rating_html = ""
        if deal["rating"]:
            rating_html = f'''<div class="card-rating">
        <span class="stars">{stars}</span>
        <span>{deal["rating"]}</span>
        <span class="rating-count">({reviews_str} valoraciones)</span>
      </div>'''

        cards_html += f'''
  <div class="card">
    <div class="card-body">
      <div class="card-badges">
        {badges}
      </div>
      <div class="card-title">{deal["title"]}</div>
      {rating_html}
      <div class="card-price">
        <span class="price-current">{deal["current_price"]:.2f}&euro;</span>
        {original_html}
        {unit_html}
      </div>
      <a class="btn" href="{deal["url"]}" target="_blank" rel="noopener">Ver en Amazon &rarr;</a>
    </div>
  </div>
'''

    # Reemplazar placeholders
    html = template.replace("{{DATE_DISPLAY}}", date_display)
    html = html.replace("{{DATE_ISO}}", date_str)
    html = html.replace("{{TIME}}", time_str)
    html = html.replace("{{NUM_DEALS}}", str(num_deals))
    html = html.replace("{{BEST_DISCOUNT}}", str(best_discount))
    html = html.replace("{{MIN_PRICE}}", f"{min_price:.2f}")
    html = html.replace("{{MAX_PRICE}}", f"{max_price:.2f}")
    html = html.replace("{{SPRING_DEALS}}", str(spring_deals))
    html = html.replace("{{CARDS}}", cards_html)

    # Escribir archivo
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"\nInforme generado: {output_path}")
    print(f"Total ofertas: {num_deals} | Mejor descuento: -{best_discount}%")


def main():
    # Directorio de salida: docs/ para GitHub Pages
    project_root = Path(__file__).parent.parent
    docs_dir = project_root / "docs"
    docs_dir.mkdir(exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"  Scraper de Ofertas de Whisky - Amazon.es")
    print(f"  Fecha: {today_str}")
    print("=" * 60)

    # Scrape
    deals = scrape_amazon_whisky()

    if not deals:
        print("\nNo se encontraron ofertas. Generando informe vacÃ­o...")

    # Generar informe del dÃ­a
    daily_path = docs_dir / f"ofertas-{today_str}.html"
    generate_html(deals, str(daily_path))

    # Copiar como index.html (pÃ¡gina principal)
    index_path = docs_dir / "index.html"
    generate_html(deals, str(index_path))

    # Guardar datos JSON para histÃ³rico
    data_dir = docs_dir / "data"
    data_dir.mkdir(exist_ok=True)
    json_path = data_dir / f"{today_str}.json"

    serializable_deals = []
    for d in deals:
        serializable_deals.append({
            "title": d["title"],
            "url": d["url"],
            "current_price": d["current_price"],
            "original_price": d["original_price"],
            "discount_pct": d["discount_pct"],
            "rating": d["rating"],
            "num_reviews": d["num_reviews"],
            "deal_type": d["deal_type"],
            "whisky_type": d["whisky_type"],
        })

    json_path.write_text(
        json.dumps({"date": today_str, "deals": serializable_deals}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Datos JSON guardados: {json_path}")

    # Generar pÃ¡gina de archivo
    generate_archive_page(docs_dir)


def generate_archive_page(docs_dir: Path):
    """Genera una pÃ¡gina con el listado de informes anteriores."""
    data_dir = docs_dir / "data"
    json_files = sorted(data_dir.glob("*.json"), reverse=True)

    entries = ""
    for jf in json_files[:90]:  # Ãltimos 90 dÃ­as
        date_str = jf.stem
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            num = len(data.get("deals", []))
            entries += f'<li><a href="ofertas-{date_str}.html">{date_str}</a> &mdash; {num} ofertas</li>\n'
        except Exception:
            entries += f'<li><a href="ofertas-{date_str}.html">{date_str}</a></li>\n'

    archive_html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Archivo de Ofertas - irlconcept.com</title>
<style>
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #1a1a2e; color: #e0e0e0;
    max-width: 800px; margin: 0 auto; padding: 2rem 1rem;
  }}
  h1 {{ color: #d4a574; }}
  a {{ color: #d4a574; }}
  li {{ margin: 0.5rem 0; }}
  .back {{ display: inline-block; margin-bottom: 1.5rem; }}
</style>
</head>
<body>
  <a class="back" href="index.html">&larr; Volver al informe de hoy</a>
  <h1>&#128218; Archivo de Ofertas</h1>
  <ul>
    {entries}
  </ul>
</body>
</html>'''

    (docs_dir / "archivo.html").write_text(archive_html, encoding="utf-8")


if __name__ == "__main__":
    main()
