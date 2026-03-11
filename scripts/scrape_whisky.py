#!/usr/bin/env python3
"""
Scraper de ofertas de whisky en Amazon.es
Usa Playwright con técnicas stealth para navegar Amazon.es y extraer ofertas actuales.
Genera un archivo HTML con el informe diario.

Características anti-detección:
- playwright-stealth para ocultar automatización
- Manejo de cookie consent de Amazon
- Headers realistas y viewport humanizado
- Delays aleatorios entre acciones
- Múltiples estrategias de búsqueda
- Scroll gradual tipo humano
- Captura de pantalla en caso de fallo
"""

import json
import re
import sys
import os
import time
import random
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Instalando playwright...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "playwright-stealth"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"])
    from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
except ImportError:
    print("Instalando playwright-stealth...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright-stealth"])
    from playwright_stealth import stealth_sync


# Mapeo de días y meses en español para evitar problemas de codificación
SPANISH_DAYS = {
    0: "lunes",
    1: "martes",
    2: "miércoles",
    3: "jueves",
    4: "viernes",
    5: "sábado",
    6: "domingo"
}

SPANISH_MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre"
}


def format_spanish_date(dt: datetime) -> str:
    """Formatea fecha en español sin problemas de codificación."""
    day_name = SPANISH_DAYS[dt.weekday()].capitalize()
    month_name = SPANISH_MONTHS[dt.month]
    return f"{day_name}, {dt.day} de {month_name} de {dt.year}"


def extract_price(text: str) -> float | None:
    """Extrae un precio de un string como '21,09€' o '21.09'."""
    if not text:
        return None
    match = re.search(r'(\d+)[,.](\d{2})', text)
    if match:
        return float(f"{match.group(1)}.{match.group(2)}")
    match = re.search(r'(\d+)', text)
    if match:
        return float(match.group(1))
    return None


def random_delay(min_sec: float = 2.0, max_sec: float = 5.0):
    """Pausa aleatoria entre min_sec y max_sec segundos."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def human_scroll(page, scrolls: int = 5):
    """Scroll gradual y humanizado."""
    for i in range(scrolls):
        page.evaluate(f"window.scrollBy(0, {random.randint(400, 800)})")
        random_delay(0.5, 1.5)


def accept_amazon_cookies(page):
    """Acepta el popup de cookies de Amazon."""
    try:
        # Esperar a que aparezca el botón de cookies
        page.wait_for_selector('input[aria-label*="Aceptar todo"], button:has-text("Aceptar todo"), a:has-text("Aceptar todo")',
                              timeout=5000)

        # Intentar múltiples selectores comunes para el botón
        selectors = [
            'input[aria-label*="Aceptar todo"]',
            'button:has-text("Aceptar todo")',
            'a:has-text("Aceptar todo")',
            'div[data-action-type="accept-all"]',
        ]

        for selector in selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    element.click()
                    print("  ✓ Cookies aceptadas")
                    random_delay(1.0, 2.0)
                    return True
            except:
                continue

    except Exception as e:
        print(f"  ! Advertencia al aceptar cookies: {e}")

    return False


def apply_stealth_patches(page):
    """Aplica técnicas stealth para evitar detección."""
    try:
        # Remover la propiedad navigator.webdriver
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
        """)

        # Ocultar Chrome automation
        page.add_init_script("""
            window.chrome = {
                runtime: {}
            };
        """)

        # Camuflar el user agent a nivel de JavaScript
        page.add_init_script("""
            Object.defineProperty(navigator, 'vendor', {
                get: () => 'Google Inc.',
            });
        """)

        print("  ✓ Técnicas stealth aplicadas")
        return True
    except Exception as e:
        print(f"  ! Error aplicando stealth: {e}")
        return False


def scrape_amazon_whisky() -> list[dict]:
    """Scrape whisky deals from Amazon.es using Playwright with stealth techniques."""
    deals = []

    search_urls = [
        "https://www.amazon.es/s?k=whisky&rh=n%3A6347789031&s=popularity-rank",
        "https://www.amazon.es/s?k=whisky+oferta&rh=n%3A6347789031&s=popularity-rank",
        "https://www.amazon.es/s?k=bourbon+whisky&rh=n%3A6347789031&s=popularity-rank",
    ]

    seen_titles = set()

    with sync_playwright() as p:
        # Opciones mejoradas del navegador
        browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-resources",
        ]

        browser = p.chromium.launch(
            headless=True,
            args=browser_args
        )

        # Contexto con opciones anti-detección realistas
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        page = context.new_page()

        # Aplicar stealth patches
        apply_stealth_patches(page)

        for url_index, url in enumerate(search_urls):
            try:
                print(f"\n[{url_index + 1}/{len(search_urls)}] Navegando a: {url[:80]}...")

                # Navegar a la URL con timeout generoso
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                random_delay(2.0, 4.0)

                # Aceptar cookies si aparece el popup
                accept_amazon_cookies(page)

                # Esperar a que carguen los resultados dinámicamente
                try:
                    page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)
                except:
                    print("  ! No se encontró selector de productos, intentando scroll...")

                # Scroll humanizado para cargar más productos
                print("  → Scrolling para cargar productos...")
                human_scroll(page, scrolls=6)

                # Esperar a carga adicional
                random_delay(1.0, 2.0)

                # Extraer productos
                products = page.query_selector_all('[data-component-type="s-search-result"]')
                print(f"  ✓ Encontrados {len(products)} elementos de producto")

                if len(products) == 0:
                    print(f"  ! Sin productos en esta URL, saltando...")
                    continue

                for product_idx, product in enumerate(products):
                    try:
                        # Título y enlace
                        title_el = product.query_selector("h2 a span")
                        link_el = product.query_selector("h2 a")

                        if not title_el:
                            continue

                        title = title_el.inner_text().strip()

                        # Filtrar no-whisky
                        title_lower = title.lower()
                        skip_keywords = [
                            "cerveza", "vino", "ginebra", "gin ", "vodka", "ron ",
                            "tequila", "licor", "vermouth", "sangría", "cava",
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
                        title_key = re.sub(r'[^a-záéíóúñ0-9]', '', title_lower)[:50]
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

                        try:
                            current_price = float(f"{current_price_str}{fraction}") if "." not in current_price_str else float(current_price_str)
                        except ValueError:
                            continue

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
                        reviews_el = product.query_selector('span[aria-label*="valoración"]')
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
                            elif "del día" in badge_text.lower():
                                deal_type = "Oferta del Día"
                            elif "flash" in badge_text.lower():
                                deal_type = "Oferta Flash"
                            else:
                                deal_type = badge_text

                        # Precio por litro
                        price_per_unit = None
                        unit_el = product.query_selector('.a-price + span')
                        if unit_el:
                            unit_text = unit_el.inner_text()
                            unit_match = re.search(r'(\d+[,.]?\d*)\s*€/l', unit_text)
                            if unit_match:
                                price_per_unit = unit_match.group(0)

                        # Determinar tipo de whisky
                        whisky_type = "Whisky"
                        if "single malt" in title_lower or "puro de malta" in title_lower:
                            whisky_type = "Single Malt"
                        elif "bourbon" in title_lower or "jim beam" in title_lower or "jack daniel" in title_lower or "maker" in title_lower:
                            whisky_type = "Bourbon"
                        elif "japonés" in title_lower or "japanese" in title_lower or "hibiki" in title_lower or "yamazaki" in title_lower or "nikka" in title_lower:
                            whisky_type = "Japonés"
                        elif "irlandés" in title_lower or "irish" in title_lower or "jameson" in title_lower:
                            whisky_type = "Irlandés"
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
                        print(f"    ✓ {title[:55]}... → {current_price}€ ({discount_pct or '?'}% off)")

                    except Exception as e:
                        print(f"    ! Error extrayendo producto: {e}")
                        continue

                # Pequeña pausa entre URLs
                if url_index < len(search_urls) - 1:
                    random_delay(3.0, 6.0)

            except Exception as e:
                print(f"✗ Error navegando {url[:50]}: {e}")
                # Captura de pantalla en caso de fallo
                screenshot_path = Path(__file__).parent.parent / "docs" / f"error-screenshot-{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                try:
                    page.screenshot(path=str(screenshot_path))
                    print(f"  Captura de error guardada: {screenshot_path}")
                except:
                    pass
                continue

        browser.close()

    # Ordenar por descuento (mayor primero), luego por precio
    deals.sort(key=lambda d: (-(d["discount_pct"] or 0), d["current_price"]))

    return deals


def generate_html(deals: list[dict], output_path: str):
    """Genera el archivo HTML del informe."""

    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    date_display = format_spanish_date(today)
    time_str = today.strftime("%H:%M")

    # Estadísticas
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
        elif "Día" in deal.get("deal_type", ""):
            badges += '<span class="badge badge-spring">Oferta del Día</span>\n'
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
    print(f"\n✓ Informe generado: {output_path}")
    print(f"  Total ofertas: {num_deals} | Mejor descuento: -{best_discount}%")


def main():
    # Directorio de salida: docs/ para GitHub Pages
    project_root = Path(__file__).parent.parent
    docs_dir = project_root / "docs"
    docs_dir.mkdir(exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")

    print("=" * 70)
    print("  SCRAPER DE OFERTAS DE WHISKY - AMAZON.ES")
    print(f"  Fecha: {today_str}")
    print("=" * 70)

    # Scrape
    deals = scrape_amazon_whisky()

    if not deals:
        print("\n✗ No se encontraron ofertas. Generando informe vacío...")
    else:
        print(f"\n✓ Total de ofertas recopiladas: {len(deals)}")

    # Generar informe del día
    daily_path = docs_dir / f"ofertas-{today_str}.html"
    generate_html(deals, str(daily_path))

    # Copiar como index.html (página principal)
    index_path = docs_dir / "index.html"
    generate_html(deals, str(index_path))

    # Guardar datos JSON para histórico
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
    print(f"✓ Datos JSON guardados: {json_path}")

    # Generar página de archivo
    generate_archive_page(docs_dir)

    print("\n" + "=" * 70)
    print("  ✓ PROCESO COMPLETADO")
    print("=" * 70)


def generate_archive_page(docs_dir: Path):
    """Genera una página con el listado de informes anteriores."""
    data_dir = docs_dir / "data"
    json_files = sorted(data_dir.glob("*.json"), reverse=True)

    entries = ""
    for jf in json_files[:90]:  # Últimos 90 días
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
    print(f"✓ Página de archivo actualizada: {docs_dir / 'archivo.html'}")


if __name__ == "__main__":
    main()
