import re
import asyncio
import random
import logging
import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

# Fix Windows asyncio subprocess issue
# Note: In Python 3.12+, Windows event loops should support subprocess by default
if sys.platform == 'win32':
    # Set event loop policy (deprecated in 3.12+ but may still be needed)
    try:
        # Try ProactorEventLoop first (better subprocess support)
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        try:
            # Fallback to SelectorEventLoop
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            pass  # Use default policy in Python 3.12+

# Configure detailed logging for scraper - write to file and console
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "scraper.log"
cache_file = log_dir / "scraper_cache.json"

# Create file handler with immediate flushing
file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
# Force immediate flushing to disk
try:
    if hasattr(file_handler.stream, 'reconfigure'):
        file_handler.stream.reconfigure(line_buffering=True)
except Exception:
    pass  # Ignore if reconfigure not available

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False  # Prevent duplicate logs from parent loggers

# Store file_handler reference for flushing
_scraper_file_handler = file_handler

# Write initialization message immediately
logger.info(f"[SCRAPER INIT] Property scraper module loaded. Log file: {log_file.absolute()}")
file_handler.flush()

# Helper function to ensure logs are flushed
@dataclass
class PropertyScrapeResult:
    """Result from scraping a property page"""
    homes_estimate: Optional[float] = None  # Median of HomesEstimate range
    homes_estimate_range: Optional[Tuple[float, float]] = None  # (low, high) range
    sold_prices: List[float] = None  # List of sold property prices
    
    def __post_init__(self):
        if self.sold_prices is None:
            self.sold_prices = []

def log_and_flush(level, message):
    """Log message and immediately flush to file"""
    getattr(logger, level)(message)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()

class PropertyScraper:
    """Scraper for property estimates from TradeMe property pages"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.cache: Dict[str, Tuple[float, datetime]] = {}
        self.cache_expiration_hours = 24
        self.last_request_time: Optional[datetime] = None
        self.min_delay_seconds = 2
        self.max_delay_seconds = 5
        self._executor: Optional[ThreadPoolExecutor] = None
        self._playwright_instance = None
        self._cache_file = cache_file
        # Load cache from file on initialization
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from JSON file"""
        try:
            if self._cache_file.exists():
                # Check if file is empty
                if self._cache_file.stat().st_size == 0:
                    logger.info(f"[SCRAPER] Cache file is empty, starting with empty cache")
                    self.cache = {}
                    return
                
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        logger.info(f"[SCRAPER] Cache file is empty, starting with empty cache")
                        self.cache = {}
                        return
                    
                    cache_data = json.loads(content)
                    # Convert timestamp strings back to datetime objects
                    for key, value in cache_data.items():
                        if isinstance(value, (list, tuple)) and len(value) == 2:
                            # Old format: [estimate_value, timestamp_str]
                            estimate_value, timestamp_str = value
                            try:
                                timestamp = datetime.fromisoformat(timestamp_str)
                                self.cache[key] = (float(estimate_value), timestamp)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"[SCRAPER] Failed to parse cache entry for {key}: {e}")
                                continue
                        elif isinstance(value, dict):
                            # New format: dict with PropertyScrapeResult data
                            self.cache[key] = value
                logger.info(f"[SCRAPER] Loaded {len(self.cache)} entries from cache file: {self._cache_file}")
            else:
                logger.info(f"[SCRAPER] No cache file found at {self._cache_file}, starting with empty cache")
        except json.JSONDecodeError as e:
            logger.warning(f"[SCRAPER] Cache file contains invalid JSON, starting with empty cache: {e}")
            self.cache = {}  # Start with empty cache on JSON error
        except Exception as e:
            logger.error(f"[SCRAPER] Failed to load cache from file: {e}", exc_info=True)
            self.cache = {}  # Start with empty cache on error
    
    def _save_cache(self):
        """Save cache to JSON file"""
        try:
            # Convert datetime objects to ISO format strings for JSON serialization
            cache_data = {}
            for key, value in self.cache.items():
                if isinstance(value, tuple) and len(value) == 2:
                    # Old format: (estimate_value, timestamp)
                    estimate_value, timestamp = value
                    cache_data[key] = [estimate_value, timestamp.isoformat()]
                elif isinstance(value, dict):
                    # New format: PropertyScrapeResult dict with timestamp
                    cache_data[key] = value
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = self._cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self._cache_file)
            logger.debug(f"[SCRAPER] Saved {len(self.cache)} entries to cache file")
        except Exception as e:
            logger.error(f"[SCRAPER] Failed to save cache to file: {e}", exc_info=True)
    
    def _get_cached_result(self, property_link: str) -> Optional[PropertyScrapeResult]:
        """
        Check cache for property data.
        Returns PropertyScrapeResult if cache hit and not expired, None otherwise.
        """
        if property_link not in self.cache:
            return None
        
        cache_entry = self.cache[property_link]
        
        # Handle old cache format: (estimate_value, timestamp)
        if isinstance(cache_entry, tuple) and len(cache_entry) == 2:
            estimate_value, cached_time = cache_entry
            age_hours = (datetime.now() - cached_time).total_seconds() / 3600
            if age_hours < self.cache_expiration_hours:
                logger.info(f"[SCRAPER] Cache HIT (old format) for {property_link}: ${estimate_value:,.0f} (age: {age_hours:.1f} hours)")
                result = PropertyScrapeResult()
                result.homes_estimate = estimate_value
                return result
            else:
                logger.info(f"[SCRAPER] Cache EXPIRED for {property_link} (age: {age_hours:.1f} hours)")
                return None
        
        # Handle new cache format: dict with PropertyScrapeResult data
        elif isinstance(cache_entry, dict):
            timestamp_str = cache_entry.get('timestamp')
            if timestamp_str:
                try:
                    cached_time = datetime.fromisoformat(timestamp_str)
                    age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    if age_hours < self.cache_expiration_hours:
                        logger.info(f"[SCRAPER] Cache HIT for {property_link} (age: {age_hours:.1f} hours)")
                        result = PropertyScrapeResult()
                        result.homes_estimate = cache_entry.get('homes_estimate')
                        result.homes_estimate_range = cache_entry.get('homes_estimate_range')
                        result.sold_prices = cache_entry.get('sold_prices', [])
                        return result
                    else:
                        logger.info(f"[SCRAPER] Cache EXPIRED for {property_link} (age: {age_hours:.1f} hours)")
                        return None
                except (ValueError, TypeError) as e:
                    logger.warning(f"[SCRAPER] Failed to parse cache timestamp: {e}")
                    return None
        
        return None
    
    def _save_result_to_cache(self, property_link: str, result: PropertyScrapeResult):
        """
        Save PropertyScrapeResult to cache.
        """
        try:
            cache_entry = {
                'homes_estimate': result.homes_estimate,
                'homes_estimate_range': result.homes_estimate_range,
                'sold_prices': result.sold_prices,
                'timestamp': datetime.now().isoformat()
            }
            self.cache[property_link] = cache_entry
            self._save_cache()
            logger.info(f"[SCRAPER] Cached property data for {property_link}")
            _scraper_file_handler.flush()
        except Exception as e:
            logger.error(f"[SCRAPER] Failed to save result to cache: {e}", exc_info=True)
    
    async def _get_browser(self) -> Browser:
        """Get or create browser instance"""
        if self.browser is None:
            try:
                logger.info("[SCRAPER] Starting Playwright...")
                # On non-Windows platforms, use async API normally
                playwright = await async_playwright().start()
                logger.info("[SCRAPER] Playwright started, launching Chromium browser...")
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                logger.info("[SCRAPER] Chromium browser launched successfully")
            except Exception as e:
                logger.error(f"[SCRAPER] Failed to start browser: {e}", exc_info=True)
                raise
        return self.browser
    
    async def _rate_limit(self):
        """Enforce rate limiting with random delay"""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
            if elapsed < delay:
                wait_time = delay - elapsed
                logger.info(f"Rate limiting: waiting {wait_time:.2f} seconds before next request")
                await asyncio.sleep(wait_time)
            else:
                logger.info(f"Rate limiting: {elapsed:.2f} seconds since last request, proceeding immediately")
        else:
            logger.info("Rate limiting: First request, no delay needed")
        
        self.last_request_time = datetime.now()
    
    def _parse_price_range(self, text: str) -> Optional[float]:
        """
        Parse price range like "$840K - $945K" and return median.
        Handles formats: "$840K - $945K", "$840,000 - $945,000", etc.
        """
        try:
            # Remove dollar signs and extract numbers with K/M suffixes
            # Pattern to match: $840K, $840,000, 840K, etc.
            pattern = r'\$?\s*([\d,]+)\s*([KMkm]?)'
            matches = re.findall(pattern, text)
            
            if len(matches) < 2:
                return None
            
            def parse_value(match: Tuple[str, str]) -> float:
                value_str, suffix = match
                value = float(value_str.replace(',', ''))
                if suffix.upper() == 'K':
                    value *= 1000
                elif suffix.upper() == 'M':
                    value *= 1000000
                return value
            
            values = [parse_value(m) for m in matches[:2]]
            if len(values) == 2:
                median = (values[0] + values[1]) / 2
                return median
            
        except Exception as e:
            logger.warning(f"Error parsing price range '{text}': {e}")
        
        return None
    
    def _extract_homes_estimate_range(self, text: str) -> Optional[Tuple[float, float]]:
        """
        Extract HomesEstimate range and return (low, high) tuple.
        Returns None if not found.
        """
        try:
            # Look for HomesEstimate pattern with more flexible matching
            patterns = [
                # Exact "HomesEstimate" with various formats
                (r'HomesEstimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'HomesEstimate pattern'),
                (r'HomesEstimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*to\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'HomesEstimate to pattern'),
                # Property estimate variations
                (r'Property estimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Property estimate pattern'),
                (r'Property estimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*to\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Property estimate to pattern'),
                # More generic patterns
                (r'estimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Generic estimate pattern'),
                # Look for price ranges near "estimate" keywords
                (r'(?:Homes|Property|Estimated)[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*[-–—]\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Flexible estimate pattern'),
            ]
            
            def parse_value(value_str: str, suffix: str) -> float:
                value = float(value_str.replace(',', ''))
                if suffix.upper() == 'K':
                    value *= 1000
                elif suffix.upper() == 'M':
                    value *= 1000000
                return value
            
            for pattern, pattern_name in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    val1_str, suffix1, val2_str, suffix2 = match.groups()
                    try:
                        val1 = parse_value(val1_str, suffix1)
                        val2 = parse_value(val2_str, suffix2)
                        # Validate reasonable values (between 10k and 50M)
                        if 10000 <= val1 <= 50000000 and 10000 <= val2 <= 50000000:
                            # Return (low, high) ensuring low < high
                            result = (min(val1, val2), max(val1, val2))
                            logger.debug(f"[SCRAPER] Extracted range using pattern '{pattern_name}': ${result[0]:,.0f} - ${result[1]:,.0f}")
                            return result
                    except (ValueError, TypeError) as e:
                        logger.debug(f"[SCRAPER] Failed to parse values from pattern '{pattern_name}': {e}")
                        continue
            
            # If no pattern matched, log a sample of the text for debugging
            logger.debug(f"[SCRAPER] No HomesEstimate pattern matched. Text sample (first 1000 chars): {text[:1000]}")
            
        except Exception as e:
            logger.warning(f"Error extracting HomesEstimate range: {e}")
        
        return None
    
    def _scrape_property_data_sync(self, property_link: str) -> PropertyScrapeResult:
        """
        Unified synchronous scraping method for Windows.
        Scrapes both HomesEstimate and sold properties in a single page load.
        Returns PropertyScrapeResult with both values.
        """
        from playwright.sync_api import sync_playwright
        import time
        
        result = PropertyScrapeResult()
        
        try:
            logger.info(f"[SCRAPER SYNC] Starting unified scrape for: {property_link}")
            
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                
                try:
                    # Navigate to property page
                    logger.info(f"[SCRAPER SYNC] Navigating to {property_link}...")
                    try:
                        page.goto(property_link, wait_until='load', timeout=60000)
                        logger.info(f"[SCRAPER SYNC] Page loaded: {page.url}")
                    except Exception as load_error:
                        logger.warning(f"[SCRAPER SYNC] Load timeout, trying domcontentloaded: {load_error}")
                        page.goto(property_link, wait_until='domcontentloaded', timeout=30000)
                    
                    # Wait for page to be interactive and content to load
                    logger.info(f"[SCRAPER SYNC] Waiting for page to be interactive...")
                    time.sleep(3)
                    
                    # Wait for property content to appear (try multiple selectors)
                    content_selectors = [
                        '[class*="property"]',
                        '[class*="listing"]',
                        '[data-testid*="property"]',
                        'main',
                        '[role="main"]',
                    ]
                    content_found = False
                    for selector in content_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=10000, state='visible')
                            content_found = True
                            logger.info(f"[SCRAPER SYNC] Found content using selector: {selector}")
                            break
                        except Exception:
                            continue
                    
                    if not content_found:
                        logger.warning(f"[SCRAPER SYNC] Property content selectors not found, continuing anyway...")
                    
                    # Wait for dynamic content to fully load
                    logger.info(f"[SCRAPER SYNC] Waiting for dynamic content to load...")
                    time.sleep(5)
                    
                    # Scroll page to trigger lazy loading
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(2)
                    
                    # Get page HTML (not just text) for better extraction
                    page_html = page.content()
                    page_text = page.text_content('body') or ''
                    
                    # Extract HomesEstimate range from HTML (more reliable than text)
                    logger.info(f"[SCRAPER SYNC] Extracting HomesEstimate range...")
                    # Try HTML first (more reliable), then fall back to text
                    estimate_range = self._extract_homes_estimate_range(page_html)
                    if not estimate_range:
                        estimate_range = self._extract_homes_estimate_range(page_text)
                    if estimate_range:
                        low, high = estimate_range
                        result.homes_estimate_range = estimate_range
                        result.homes_estimate = (low + high) / 2
                        logger.info(f"[SCRAPER SYNC] Found HomesEstimate range: ${low:,.0f} - ${high:,.0f}, median: ${result.homes_estimate:,.0f}")
                    else:
                        logger.warning(f"[SCRAPER SYNC] Could not extract HomesEstimate range")
                    
                    # Find and scroll to "Nearby Sold Properties" section
                    logger.info(f"[SCRAPER SYNC] Searching for 'Nearby Sold Properties' section...")
                    
                    # Wait for section to appear with multiple strategies
                    sold_section_found = False
                    for attempt in range(5):  # Increased attempts from 3 to 5
                        # Try to find section by text content (case-insensitive)
                        page_text_current = page.text_content('body') or ''
                        page_text_lower = page_text_current.lower()
                        
                        # Check for various text patterns
                        text_patterns = [
                            'nearby sold properties',
                            'nearby sold',
                            'recently sold',
                            'sold properties',
                            'comparable sales',
                        ]
                        
                        for pattern in text_patterns:
                            if pattern in page_text_lower:
                                sold_section_found = True
                                logger.info(f"[SCRAPER SYNC] Found '{pattern}' text in page (attempt {attempt + 1})")
                                break
                        
                        if sold_section_found:
                            break
                        
                        # Try to find section by selector with more patterns
                        try:
                            selectors_to_try = [
                                'h2:has-text("Nearby Sold Properties")',
                                'h2:has-text("Nearby Sold")',
                                'h3:has-text("Nearby Sold Properties")',
                                'h3:has-text("Nearby Sold")',
                                '[class*="sold"]',
                                '[class*="nearby"]',
                                '[class*="comparable"]',
                                'section:has-text("Nearby Sold")',
                                '[data-testid*="sold"]',
                                '[aria-label*="sold" i]',
                            ]
                            for selector in selectors_to_try:
                                try:
                                    element = page.query_selector(selector)
                                    if element and element.is_visible():
                                        logger.info(f"[SCRAPER SYNC] Found section using selector: {selector}")
                                        sold_section_found = True
                                        break
                                except Exception:
                                    continue
                            if sold_section_found:
                                break
                        except Exception as e:
                            logger.debug(f"[SCRAPER SYNC] Selector search error: {e}")
                        
                        if attempt < 4:
                            logger.info(f"[SCRAPER SYNC] Section not found yet, waiting and scrolling (attempt {attempt + 1}/5)...")
                            # Scroll down progressively to trigger lazy loading
                            scroll_amount = 500 * (attempt + 1)
                            page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                            time.sleep(4)  # Wait longer for content to load
                            # Also try scrolling to bottom
                            if attempt == 2:
                                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                time.sleep(3)
                    
                    if not sold_section_found:
                        logger.warning(f"[SCRAPER SYNC] 'Nearby Sold Properties' section not found after multiple attempts")
                        # Log page URL and title for debugging
                        try:
                            page_url = page.url
                            page_title = page.title()
                            logger.debug(f"[SCRAPER SYNC] Page URL: {page_url}, Title: {page_title}")
                            # Log a sample of page text
                            page_text_sample = page.text_content('body')[:500] if page.text_content('body') else "No text"
                            logger.debug(f"[SCRAPER SYNC] Page text sample: {page_text_sample}")
                        except Exception:
                            pass
                        return result
                    
                    # Scroll to the section explicitly
                    logger.info(f"[SCRAPER SYNC] Scrolling to 'Nearby Sold Properties' section...")
                    page.evaluate("""
                        const elements = Array.from(document.querySelectorAll('*'));
                        const soldSection = elements.find(el => 
                            el.textContent && (
                                el.textContent.includes('Nearby Sold Properties') || 
                                el.textContent.includes('nearby sold')
                            )
                        );
                        if (soldSection) {
                            soldSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    """)
                    time.sleep(4)  # Wait longer for section to fully render
                    
                    # Extract sold prices with pagination
                    logger.info(f"[SCRAPER SYNC] Extracting sold properties...")
                    max_clicks = 50
                    click_count = 0
                    
                    while click_count < max_clicks:
                        # Extract sold prices from current view
                        page_html_current = page.content()
                        
                        # Extract all sold prices from page HTML with more patterns
                        sold_patterns = [
                            # Patterns matching actual HTML structure
                            r'SOLD[:\s]*\$?\s*([\d,]+)\s*([KMkm]?)',
                            r'\$\s*([\d,]+)\s*([KMkm]?)\s*(?:SOLD|sold)',
                            r'(?:Sold|SOLD)[:\s]*\$?\s*([\d,]+)\s*([KMkm]?)',
                            # Look for price patterns near "sold" text
                            r'(?:sold|Sold|SOLD)[^<]*\$?\s*([\d,]+)\s*([KMkm]?)',
                            # Look for price in divs/spans near sold indicators
                            r'<[^>]*sold[^>]*>[^<]*\$?\s*([\d,]+)\s*([KMkm]?)[^<]*</',
                            # Generic price patterns that might be sold prices (3+ digits)
                            r'\$\s*([\d]{3,}[\d,]*)\s*([KMkm]?)',
                        ]
                        
                        prices_before = len(result.sold_prices)
                        for pattern in sold_patterns:
                            matches = re.finditer(pattern, page_html_current, re.IGNORECASE)
                            for match in matches:
                                value_str = match.group(1)
                                suffix = match.group(2) if len(match.groups()) > 1 else ''
                                try:
                                    price = float(value_str.replace(',', ''))
                                    if suffix.upper() == 'K':
                                        price *= 1000
                                    elif suffix.upper() == 'M':
                                        price *= 1000000
                                    if price >= 1000 and price not in result.sold_prices:
                                        result.sold_prices.append(price)
                                        logger.debug(f"[SCRAPER SYNC] Found sold price: ${price:,.0f}")
                                except (ValueError, IndexError):
                                    continue
                        
                        prices_after = len(result.sold_prices)
                        if prices_after == prices_before and click_count > 0:
                            # No new prices found, likely at end
                            logger.info(f"[SCRAPER SYNC] No new prices found, stopping pagination")
                            break
                        
                        # Try to find and click '>' button
                        next_button = None
                        selectors = [
                            'button[aria-label*="next" i]',
                            'button[aria-label*=">" i]',
                            'button:has-text(">")',
                            '[class*="next"]',
                            '[class*="arrow-right"]',
                            'button >> text=">"',
                            'a[aria-label*="next" i]',
                            'a[aria-label*=">" i]',
                        ]
                        
                        for selector in selectors:
                            try:
                                next_button = page.query_selector(selector)
                                if next_button:
                                    # Check if button is disabled or not visible
                                    is_disabled = (
                                        next_button.get_attribute('disabled') or
                                        next_button.get_attribute('aria-disabled') == 'true' or
                                        'disabled' in (next_button.get_attribute('class') or '') or
                                        not next_button.is_visible()
                                    )
                                    if is_disabled:
                                        logger.info(f"[SCRAPER SYNC] Next button is disabled/not visible, stopping pagination")
                                        next_button = None
                                        break
                                    break
                            except Exception:
                                continue
                        
                        if not next_button:
                            logger.info(f"[SCRAPER SYNC] No next button found, stopping pagination")
                            break
                        
                        # Click next button
                        try:
                            logger.info(f"[SCRAPER SYNC] Clicking next button (click {click_count + 1})...")
                            next_button.click()
                            time.sleep(3)  # Wait longer for new content to load
                            click_count += 1
                        except Exception as e:
                            logger.warning(f"[SCRAPER SYNC] Failed to click next button: {e}")
                            break
                    
                    logger.info(f"[SCRAPER SYNC] Collected {len(result.sold_prices)} sold prices after {click_count} pagination clicks")
                    
                finally:
                    page.close()
                    context.close()
            finally:
                browser.close()
                playwright.stop()
                
        except Exception as e:
            logger.error(f"[SCRAPER SYNC] Error in unified scrape: {e}", exc_info=True)
        
        return result
    
    def _parse_sold_price(self, text: str) -> Optional[float]:
        """
        Parse sold price from text like "SOLD: $1,350,000" or "$722,000".
        Returns price as float or None if not found.
        """
        try:
            # Pattern to match: "SOLD: $1,350,000" or "$722,000" or "$1.35M"
            patterns = [
                (r'SOLD:\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'SOLD prefix pattern'),
                (r'\$\s*([\d,]+)\s*([KMkm]?)', 'Dollar amount pattern'),
            ]
            
            def parse_value(value_str: str, suffix: str) -> float:
                value = float(value_str.replace(',', ''))
                if suffix.upper() == 'K':
                    value *= 1000
                elif suffix.upper() == 'M':
                    value *= 1000000
                return value
            
            for pattern, pattern_name in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value_str, suffix = match.groups()
                    price = parse_value(value_str, suffix)
                    # Validate it's a reasonable price (>= 1000)
                    if price >= 1000:
                        return price
            
        except Exception as e:
            logger.debug(f"Error parsing sold price from '{text}': {e}")
        
        return None
    
    async def _slow_scroll(self, page: Page):
        """Slowly scroll down the page to load all elements"""
        try:
            logger.info("Starting slow scroll to load page content...")
            # Get page height
            page_height = await page.evaluate("document.body.scrollHeight")
            logger.info(f"Initial page height: {page_height}px")
            scroll_increment = 300
            current_position = 0
            scroll_count = 0
            
            while current_position < page_height:
                await page.evaluate(f"window.scrollTo(0, {current_position})")
                await asyncio.sleep(0.5)  # Delay between scrolls
                current_position += scroll_increment
                scroll_count += 1
                
                # Update page height in case new content loaded
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height > page_height:
                    logger.info(f"Page expanded during scroll: {page_height}px -> {new_height}px")
                    page_height = new_height
            
            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            logger.info(f"Slow scroll completed: {scroll_count} scroll steps, final height: {page_height}px")
            
        except Exception as e:
            logger.error(f"Error during slow scroll: {e}", exc_info=True)
    
    def _scrape_homes_estimate_sync(self, property_link: str) -> Optional[float]:
        """
        Synchronous version of scraping for Windows (runs in thread pool).
        Uses sync Playwright API to avoid asyncio subprocess issues.
        """
        from playwright.sync_api import sync_playwright, TimeoutError as SyncPlaywrightTimeoutError
        import time
        
        try:
            logger.info(f"[SCRAPER SYNC] Starting sync scrape for: {property_link}")
            
            # Use sync Playwright
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                
                try:
                    # Navigate - use 'load' instead of 'networkidle' (more reliable, networkidle often times out)
                    logger.info(f"[SCRAPER SYNC] Navigating to {property_link}...")
                    try:
                        page.goto(property_link, wait_until='load', timeout=60000)
                        logger.info(f"[SCRAPER SYNC] Page loaded (load event): {page.url}")
                    except Exception as load_error:
                        # Fallback to domcontentloaded if load times out
                        logger.warning(f"[SCRAPER SYNC] Load event timeout, trying domcontentloaded: {load_error}")
                        try:
                            page.goto(property_link, wait_until='domcontentloaded', timeout=30000)
                            logger.info(f"[SCRAPER SYNC] Page loaded (domcontentloaded): {page.url}")
                        except Exception as dom_error:
                            logger.error(f"[SCRAPER SYNC] Failed to load page: {dom_error}")
                            raise
                    
                    # Wait a bit for dynamic content to render
                    time.sleep(2)
                    logger.info(f"[SCRAPER SYNC] Waiting for dynamic content to render...")
                    
                    # Slow scroll
                    page_height = page.evaluate("document.body.scrollHeight")
                    scroll_step = 300
                    scroll_count = 0
                    current_position = 0
                    while current_position < page_height:
                        current_position += scroll_step
                        page.evaluate(f"window.scrollTo(0, {current_position})")
                        time.sleep(0.3)
                        scroll_count += 1
                        new_height = page.evaluate("document.body.scrollHeight")
                        if new_height > page_height:
                            page_height = new_height
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                    logger.info(f"[SCRAPER SYNC] Scroll completed: {scroll_count} steps")
                    
                    # Extract price range
                    page_text = page.text_content('body') or ''
                    logger.info(f"[SCRAPER SYNC] Page text length: {len(page_text)} chars")
                    
                    patterns = [
                        (r'HomesEstimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'HomesEstimate pattern'),
                        (r'Property estimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Property estimate pattern'),
                        (r'\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Generic price range pattern'),
                    ]
                    
                    estimate_value = None
                    for pattern, pattern_name in patterns:
                        match = re.search(pattern, page_text, re.IGNORECASE)
                        if match:
                            try:
                                val1_str, suffix1, val2_str, suffix2 = match.groups()
                                val1 = float(val1_str.replace(',', ''))
                                val2 = float(val2_str.replace(',', ''))
                                
                                if suffix1.upper() == 'K':
                                    val1 *= 1000
                                elif suffix1.upper() == 'M':
                                    val1 *= 1000000
                                
                                if suffix2.upper() == 'K':
                                    val2 *= 1000
                                elif suffix2.upper() == 'M':
                                    val2 *= 1000000
                                
                                estimate_value = (val1 + val2) / 2
                                logger.info(f"[SCRAPER SYNC] SUCCESS! Range: ${val1:,.0f} - ${val2:,.0f}, median: ${estimate_value:,.0f}")
                                break
                            except (ValueError, IndexError) as e:
                                logger.warning(f"[SCRAPER SYNC] Error parsing pattern {pattern_name}: {e}")
                                continue
                    
                    if estimate_value:
                        self.cache[property_link] = (estimate_value, datetime.now())
                        logger.info(f"[SCRAPER SYNC] Cached: ${estimate_value:,.0f}")
                        self._save_cache()  # Persist cache to file
                        return estimate_value
                    else:
                        logger.warning(f"[SCRAPER SYNC] No estimate found for {property_link}")
                        return None
                        
                finally:
                    page.close()
                    context.close()
            finally:
                browser.close()
                playwright.stop()
                
        except Exception as e:
            logger.error(f"[SCRAPER SYNC] Error: {e}", exc_info=True)
            return None
    
    async def scrape_homes_estimate(self, property_link: str, retry: bool = True) -> Optional[float]:
        """
        Scrape HomesEstimate from property page.
        
        Args:
            property_link: URL to the property page
            retry: Whether to retry once on failure
            
        Returns:
            Median of the price range, or None if not found
        """
        if not property_link:
            return None
        
        # Check cache first
        logger.info(f"[SCRAPER] Starting scrape for property: {property_link}")
        if property_link in self.cache:
            cached_value, cached_time = self.cache[property_link]
            age_hours = (datetime.now() - cached_time).total_seconds() / 3600
            if age_hours < self.cache_expiration_hours:
                logger.info(f"[SCRAPER] Cache HIT for {property_link}: ${cached_value:,.0f} (age: {age_hours:.1f} hours)")
                return cached_value
            else:
                logger.info(f"[SCRAPER] Cache EXPIRED for {property_link} (age: {age_hours:.1f} hours), will re-scrape")
        else:
            logger.info(f"[SCRAPER] Cache MISS for {property_link}, will scrape")
        
        # Enforce rate limiting
        await self._rate_limit()
        
        # On Windows, use sync API in thread pool to avoid asyncio subprocess issues
        if sys.platform == 'win32':
            logger.info(f"[SCRAPER] Using sync Playwright API in thread pool (Windows workaround)")
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
            
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    self._executor, self._scrape_homes_estimate_sync, property_link
                )
                return result
            except Exception as e:
                logger.error(f"[SCRAPER] Error in thread pool execution: {e}", exc_info=True)
                if retry:
                    retry_delay = random.uniform(2, 4)
                    logger.info(f"[SCRAPER] Retrying after {retry_delay:.2f} seconds...")
                    await asyncio.sleep(retry_delay)
                    return await self.scrape_homes_estimate(property_link, retry=False)
                return None
        
        # Non-Windows: use async API normally
        try:
            logger.info(f"[SCRAPER] Getting browser instance...")
            _scraper_file_handler.flush()
            browser = await self._get_browser()
            logger.info(f"[SCRAPER] Creating new browser context...")
            _scraper_file_handler.flush()
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                # Navigate to property page - use 'load' instead of 'networkidle' (more reliable)
                logger.info(f"[SCRAPER] Navigating to {property_link}...")
                _scraper_file_handler.flush()
                try:
                    await page.goto(property_link, wait_until='load', timeout=60000)
                    logger.info(f"[SCRAPER] Page loaded (load event), URL: {page.url}")
                except Exception as load_error:
                    # Fallback to domcontentloaded if load times out
                    logger.warning(f"[SCRAPER] Load event timeout, trying domcontentloaded: {load_error}")
                    try:
                        await page.goto(property_link, wait_until='domcontentloaded', timeout=30000)
                        logger.info(f"[SCRAPER] Page loaded (domcontentloaded), URL: {page.url}")
                    except Exception as dom_error:
                        logger.error(f"[SCRAPER] Failed to load page: {dom_error}")
                        raise
                
                # Wait a bit for dynamic content to render
                await asyncio.sleep(2)
                logger.info(f"[SCRAPER] Waiting for dynamic content to render...")
                _scraper_file_handler.flush()
                
                # Slowly scroll to load all content
                await self._slow_scroll(page)
                
                # Wait for property estimate section to load
                logger.info(f"[SCRAPER] Searching for Property estimate section...")
                # Look for common selectors for the estimate section
                selectors = [
                    'text="Property estimate"',
                    'text="HomesEstimate"',
                    '[data-testid*="estimate"]',
                    '.property-estimate',
                    'h2:has-text("Property estimate")'
                ]
                
                estimate_section = None
                for i, selector in enumerate(selectors):
                    try:
                        logger.info(f"[SCRAPER] Trying selector {i+1}/{len(selectors)}: {selector}")
                        estimate_section = await page.wait_for_selector(selector, timeout=5000)
                        if estimate_section:
                            logger.info(f"[SCRAPER] Found estimate section with selector: {selector}")
                            break
                    except PlaywrightTimeoutError:
                        logger.debug(f"[SCRAPER] Selector {selector} not found, trying next...")
                        continue
                
                if not estimate_section:
                    logger.warning(f"[SCRAPER] No estimate section found with standard selectors, searching in page content...")
                    # Try to find by text content
                    page_text = await page.content()
                    if 'Property estimate' in page_text or 'HomesEstimate' in page_text:
                        logger.info(f"[SCRAPER] Found 'Property estimate' or 'HomesEstimate' text in page, scrolling to it...")
                        # Scroll to find the section
                        await page.evaluate("""
                            const elements = Array.from(document.querySelectorAll('*'));
                            const estimateEl = elements.find(el => 
                                el.textContent && (
                                    el.textContent.includes('Property estimate') || 
                                    el.textContent.includes('HomesEstimate')
                                )
                            );
                            if (estimateEl) {
                                estimateEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            }
                        """)
                        await asyncio.sleep(2)
                        logger.info(f"[SCRAPER] Scrolled to estimate section")
                    else:
                        logger.warning(f"[SCRAPER] 'Property estimate' or 'HomesEstimate' text not found in page content")
                
                # Extract the price range text
                logger.info(f"[SCRAPER] Extracting price range from page text...")
                # Look for patterns like "$840K - $945K" or "$840,000 - $945,000"
                page_text = await page.text_content('body')
                logger.debug(f"[SCRAPER] Page text length: {len(page_text)} characters")
                
                # Try multiple patterns to find the estimate range
                patterns = [
                    (r'HomesEstimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'HomesEstimate pattern'),
                    (r'Property estimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Property estimate pattern'),
                    (r'\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)\s*/week', 'Weekly rent pattern'),
                    (r'\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Generic price range pattern'),
                ]
                
                estimate_value = None
                for i, (pattern, pattern_name) in enumerate(patterns):
                    logger.info(f"[SCRAPER] Trying pattern {i+1}/{len(patterns)}: {pattern_name}")
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        try:
                            val1_str, suffix1, val2_str, suffix2 = match.groups()
                            logger.info(f"[SCRAPER] Pattern matched! Values: {val1_str}{suffix1} - {val2_str}{suffix2}")
                            val1 = float(val1_str.replace(',', ''))
                            val2 = float(val2_str.replace(',', ''))
                            
                            # Handle K/M suffixes
                            if suffix1.upper() == 'K':
                                val1 *= 1000
                            elif suffix1.upper() == 'M':
                                val1 *= 1000000
                            
                            if suffix2.upper() == 'K':
                                val2 *= 1000
                            elif suffix2.upper() == 'M':
                                val2 *= 1000000
                            
                            estimate_value = (val1 + val2) / 2
                            logger.info(f"[SCRAPER] SUCCESS! Found estimate range: ${val1:,.0f} - ${val2:,.0f}, median: ${estimate_value:,.0f}")
                            break
                        except (ValueError, IndexError) as e:
                            logger.warning(f"[SCRAPER] Error parsing estimate pattern {pattern_name}: {e}")
                            continue
                    else:
                        logger.debug(f"[SCRAPER] Pattern {pattern_name} did not match")
                
                if estimate_value:
                    # Cache the result
                    self.cache[property_link] = (estimate_value, datetime.now())
                    logger.info(f"[SCRAPER] Cached estimate for {property_link}: ${estimate_value:,.0f}")
                    self._save_cache()  # Persist cache to file
                    _scraper_file_handler.flush()
                    return estimate_value
                else:
                    logger.warning(f"[SCRAPER] FAILED: Could not find estimate range on page: {property_link}")
                    # Log a sample of page text for debugging
                    sample_text = page_text[:500] if page_text else "No page text available"
                    logger.debug(f"[SCRAPER] Page text sample (first 500 chars): {sample_text}")
                    _scraper_file_handler.flush()
                    return None
                    
            finally:
                await page.close()
                await context.close()
                
        except PlaywrightTimeoutError as e:
            logger.error(f"[SCRAPER] TIMEOUT scraping {property_link}: {e}")
            if retry:
                retry_delay = random.uniform(2, 4)
                logger.info(f"[SCRAPER] Retrying scrape for {property_link} after {retry_delay:.2f} seconds...")
                await asyncio.sleep(retry_delay)
                return await self.scrape_homes_estimate(property_link, retry=False)
            logger.error(f"[SCRAPER] Final failure after retry for {property_link}")
            return None
        except Exception as e:
            logger.error(f"[SCRAPER] ERROR scraping {property_link}: {e}", exc_info=True)
            if retry:
                retry_delay = random.uniform(2, 4)
                logger.info(f"[SCRAPER] Retrying scrape for {property_link} after {retry_delay:.2f} seconds...")
                await asyncio.sleep(retry_delay)
                return await self.scrape_homes_estimate(property_link, retry=False)
            logger.error(f"[SCRAPER] Final failure after retry for {property_link}")
            return None
    
    def _scrape_sold_properties_sync(self, property_link: str) -> list[float]:
        """
        Synchronous version of scraping sold properties for Windows (runs in thread pool).
        Scrapes "Nearby Sold Properties" section and collects all sold prices.
        """
        from playwright.sync_api import sync_playwright, TimeoutError as SyncPlaywrightTimeoutError
        import time
        
        sold_prices = []
        
        try:
            logger.info(f"[SCRAPER SYNC] Starting sold properties scrape for: {property_link}")
            
            # Use sync Playwright
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            try:
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                
                try:
                    # Navigate to property page
                    logger.info(f"[SCRAPER SYNC] Navigating to {property_link}...")
                    try:
                        page.goto(property_link, wait_until='load', timeout=60000)
                        logger.info(f"[SCRAPER SYNC] Page loaded: {page.url}")
                    except Exception as load_error:
                        logger.warning(f"[SCRAPER SYNC] Load timeout, trying domcontentloaded: {load_error}")
                        page.goto(property_link, wait_until='domcontentloaded', timeout=30000)
                    
                    # Wait for dynamic content
                    time.sleep(2)
                    
                    # Scroll to find "Nearby Sold Properties" section
                    logger.info(f"[SCRAPER SYNC] Searching for 'Nearby Sold Properties' section...")
                    page_text = page.text_content('body') or ''
                    
                    if 'Nearby Sold Properties' not in page_text and 'nearby sold' not in page_text.lower():
                        logger.warning(f"[SCRAPER SYNC] 'Nearby Sold Properties' section not found on page")
                        return sold_prices
                    
                    # Scroll to the section
                    logger.info(f"[SCRAPER SYNC] Scrolling to 'Nearby Sold Properties' section...")
                    page.evaluate("""
                        const elements = Array.from(document.querySelectorAll('*'));
                        const soldSection = elements.find(el => 
                            el.textContent && (
                                el.textContent.includes('Nearby Sold Properties') || 
                                el.textContent.includes('nearby sold')
                            )
                        );
                        if (soldSection) {
                            soldSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    """)
                    time.sleep(2)
                    
                    # Find and click '>' button repeatedly to paginate
                    max_clicks = 50  # Safety limit
                    click_count = 0
                    
                    while click_count < max_clicks:
                        # Extract sold prices from current view
                        page_html = page.content()
                        
                        # Extract all sold prices from page text
                        # Look for patterns like "SOLD: $1,350,000" or "$722,000"
                        sold_patterns = [
                            r'SOLD:\s*\$?\s*([\d,]+)\s*([KMkm]?)',
                            r'\$\s*([\d,]+)\s*([KMkm]?)\s*(?:SOLD|sold)',
                        ]
                        
                        for pattern in sold_patterns:
                            matches = re.finditer(pattern, page_html, re.IGNORECASE)
                            for match in matches:
                                value_str = match.group(1)
                                suffix = match.group(2) if len(match.groups()) > 1 else ''
                                try:
                                    price = float(value_str.replace(',', ''))
                                    if suffix.upper() == 'K':
                                        price *= 1000
                                    elif suffix.upper() == 'M':
                                        price *= 1000000
                                    if price >= 1000 and price not in sold_prices:
                                        sold_prices.append(price)
                                        logger.debug(f"[SCRAPER SYNC] Found sold price: ${price:,.0f}")
                                except (ValueError, IndexError):
                                    continue
                        
                        # Try to find and click '>' button
                        next_button = None
                        selectors = [
                            'button[aria-label*="next" i]',
                            'button[aria-label*=">" i]',
                            'button:has-text(">")',
                            '[class*="next"]',
                            '[class*="arrow-right"]',
                            'button >> text=">"',
                        ]
                        
                        for selector in selectors:
                            try:
                                next_button = page.query_selector(selector)
                                if next_button:
                                    # Check if button is disabled
                                    is_disabled = next_button.get_attribute('disabled') or \
                                                next_button.get_attribute('aria-disabled') == 'true' or \
                                                'disabled' in (next_button.get_attribute('class') or '')
                                    if is_disabled:
                                        logger.info(f"[SCRAPER SYNC] Next button is disabled, stopping pagination")
                                        next_button = None
                                        break
                                    break
                            except Exception:
                                continue
                        
                        if not next_button:
                            logger.info(f"[SCRAPER SYNC] No next button found, stopping pagination")
                            break
                        
                        # Click next button
                        try:
                            logger.info(f"[SCRAPER SYNC] Clicking next button (click {click_count + 1})...")
                            next_button.click()
                            time.sleep(2)  # Wait for new content to load
                            click_count += 1
                        except Exception as e:
                            logger.warning(f"[SCRAPER SYNC] Failed to click next button: {e}")
                            break
                    
                    logger.info(f"[SCRAPER SYNC] Collected {len(sold_prices)} sold prices after {click_count} pagination clicks")
                    
                finally:
                    page.close()
                    context.close()
            finally:
                browser.close()
                playwright.stop()
                
        except Exception as e:
            logger.error(f"[SCRAPER SYNC] Error scraping sold properties: {e}", exc_info=True)
        
        return sold_prices
    
    async def scrape_property_data(self, property_link: str) -> PropertyScrapeResult:
        """
        Unified method to scrape both HomesEstimate and sold properties in one page load.
        Returns PropertyScrapeResult with both values.
        This is the main method to use - it encapsulates all scraping logic.
        Checks cache before scraping and saves results to cache after.
        """
        if not property_link:
            return PropertyScrapeResult()
        
        logger.info(f"[SCRAPER] Starting unified scrape for: {property_link}")
        
        # Check cache first
        cached_result = self._get_cached_result(property_link)
        if cached_result is not None:
            logger.info(f"[SCRAPER] Using cached data for {property_link}")
            return cached_result
        
        logger.info(f"[SCRAPER] Cache MISS for {property_link}, will scrape")
        
        # Enforce rate limiting
        await self._rate_limit()
        
        # On Windows, use sync API in thread pool
        if sys.platform == 'win32':
            logger.info(f"[SCRAPER] Using sync Playwright API in thread pool (Windows workaround)")
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
            
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    self._executor, self._scrape_property_data_sync, property_link
                )
                # Save to cache if we got valid results
                if result.homes_estimate or result.sold_prices:
                    self._save_result_to_cache(property_link, result)
                return result
            except Exception as e:
                logger.error(f"[SCRAPER] Error in thread pool execution: {e}", exc_info=True)
                return PropertyScrapeResult()
        
        # Non-Windows: use async API (similar logic but async)
        result = PropertyScrapeResult()
        try:
            browser = await self._get_browser()
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                # Navigate
                logger.info(f"[SCRAPER] Navigating to {property_link}...")
                try:
                    await page.goto(property_link, wait_until='load', timeout=60000)
                except Exception:
                    await page.goto(property_link, wait_until='domcontentloaded', timeout=30000)
                
                # Wait longer for dynamic content
                await asyncio.sleep(5)
                
                # Scroll to trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(2)
                
                # Get page text for HomesEstimate
                page_text = await page.text_content('body') or ''
                
                # Extract HomesEstimate range
                estimate_range = self._extract_homes_estimate_range(page_text)
                if estimate_range:
                    low, high = estimate_range
                    result.homes_estimate_range = estimate_range
                    result.homes_estimate = (low + high) / 2
                    logger.info(f"[SCRAPER] Found HomesEstimate range: ${low:,.0f} - ${high:,.0f}")
                
                # Find "Nearby Sold Properties" section with retries
                sold_section_found = False
                for attempt in range(3):
                    page_text_current = await page.text_content('body') or ''
                    if 'Nearby Sold Properties' in page_text_current or 'nearby sold' in page_text_current.lower():
                        sold_section_found = True
                        break
                    if attempt < 2:
                        await page.evaluate("window.scrollBy(0, 500)")
                        await asyncio.sleep(3)
                
                if not sold_section_found:
                    logger.warning(f"[SCRAPER] 'Nearby Sold Properties' section not found")
                    return result
                
                # Scroll to section
                await page.evaluate("""
                    const elements = Array.from(document.querySelectorAll('*'));
                    const soldSection = elements.find(el => 
                        el.textContent && (
                            el.textContent.includes('Nearby Sold Properties') || 
                            el.textContent.includes('nearby sold')
                        )
                    );
                    if (soldSection) {
                        soldSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                """)
                await asyncio.sleep(4)
                
                # Extract sold prices with pagination
                max_clicks = 50
                click_count = 0
                
                while click_count < max_clicks:
                    page_html = await page.content()
                    sold_patterns = [
                        r'SOLD:\s*\$?\s*([\d,]+)\s*([KMkm]?)',
                        r'\$\s*([\d,]+)\s*([KMkm]?)\s*(?:SOLD|sold)',
                    ]
                    
                    prices_before = len(result.sold_prices)
                    for pattern in sold_patterns:
                        matches = re.finditer(pattern, page_html, re.IGNORECASE)
                        for match in matches:
                            value_str = match.group(1)
                            suffix = match.group(2) if len(match.groups()) > 1 else ''
                            try:
                                price = float(value_str.replace(',', ''))
                                if suffix.upper() == 'K':
                                    price *= 1000
                                elif suffix.upper() == 'M':
                                    price *= 1000000
                                if price >= 1000 and price not in result.sold_prices:
                                    result.sold_prices.append(price)
                            except (ValueError, IndexError):
                                continue
                    
                    if len(result.sold_prices) == prices_before and click_count > 0:
                        break
                    
                    # Find next button
                    next_button = None
                    selectors = [
                        'button[aria-label*="next" i]',
                        'button[aria-label*=">" i]',
                        'button:has-text(">")',
                        '[class*="next"]',
                        '[class*="arrow-right"]',
                        'a[aria-label*="next" i]',
                    ]
                    
                    for selector in selectors:
                        try:
                            next_button = await page.query_selector(selector)
                            if next_button:
                                is_disabled = (
                                    await next_button.get_attribute('disabled') or
                                    await next_button.get_attribute('aria-disabled') == 'true' or
                                    not await next_button.is_visible()
                                )
                                if is_disabled:
                                    next_button = None
                                    break
                                break
                        except Exception:
                            continue
                    
                    if not next_button:
                        break
                    
                    try:
                        await next_button.click()
                        await asyncio.sleep(3)
                        click_count += 1
                    except Exception as e:
                        logger.warning(f"[SCRAPER] Failed to click next: {e}")
                        break
                
                logger.info(f"[SCRAPER] Collected {len(result.sold_prices)} sold prices")
                
            finally:
                await page.close()
                await context.close()
            
            # Save to cache if we got valid results
            if result.homes_estimate or result.sold_prices:
                self._save_result_to_cache(property_link, result)
                
        except Exception as e:
            logger.error(f"[SCRAPER] Error in unified scrape: {e}", exc_info=True)
        
        return result
    
    async def scrape_sold_properties(self, property_link: str) -> list[float]:
        """
        Legacy method - now uses unified scrape_property_data.
        Kept for backward compatibility.
        """
        result = await self.scrape_property_data(property_link)
        return result.sold_prices
    
    async def close(self):
        """Close browser instance"""
        if self.browser:
            if sys.platform == 'win32' and self._playwright_instance:
                # Sync API cleanup
                try:
                    self.browser.close()
                    self._playwright_instance.stop()
                except Exception as e:
                    logger.warning(f"[SCRAPER] Error closing sync browser: {e}")
            else:
                # Async API cleanup
                await self.browser.close()
            self.browser = None
            self._playwright_instance = None
        
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

# Global scraper instance
_scraper_instance: Optional[PropertyScraper] = None

def get_scraper() -> PropertyScraper:
    """Get or create global scraper instance"""
    global _scraper_instance
    if _scraper_instance is None:
        logger.info("[SCRAPER] Creating new PropertyScraper instance")
        _scraper_file_handler.flush()
        _scraper_instance = PropertyScraper()
        logger.info("[SCRAPER] PropertyScraper instance created successfully")
        _scraper_file_handler.flush()
    return _scraper_instance

async def scrape_property_data(property_link: str) -> PropertyScrapeResult:
    """
    Unified convenience function to scrape both HomesEstimate and sold properties.
    This is the main function to use - it loads the page once and gets both values.
    """
    logger.info(f"[SCRAPER] scrape_property_data called for: {property_link}")
    _scraper_file_handler.flush()
    scraper = get_scraper()
    return await scraper.scrape_property_data(property_link)

async def scrape_property_estimate(property_link: str) -> Optional[float]:
    """
    Convenience function to scrape property estimate.
    Uses unified scrape_property_data internally for efficiency.
    """
    logger.info(f"[SCRAPER] scrape_property_estimate called for: {property_link}")
    _scraper_file_handler.flush()
    scraper = get_scraper()
    result = await scraper.scrape_property_data(property_link)
    return result.homes_estimate

async def scrape_sold_properties(property_link: str) -> list[float]:
    """
    Convenience function to scrape sold properties.
    Uses unified scrape_property_data internally for efficiency.
    """
    logger.info(f"[SCRAPER] scrape_sold_properties called for: {property_link}")
    _scraper_file_handler.flush()
    scraper = get_scraper()
    result = await scraper.scrape_property_data(property_link)
    return result.sold_prices

