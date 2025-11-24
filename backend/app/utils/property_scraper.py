import re
import asyncio
import random
import logging
import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Tuple
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
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # Convert timestamp strings back to datetime objects
                    for key, value in cache_data.items():
                        if isinstance(value, (list, tuple)) and len(value) == 2:
                            estimate_value, timestamp_str = value
                            try:
                                timestamp = datetime.fromisoformat(timestamp_str)
                                self.cache[key] = (float(estimate_value), timestamp)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"[SCRAPER] Failed to parse cache entry for {key}: {e}")
                                continue
                logger.info(f"[SCRAPER] Loaded {len(self.cache)} entries from cache file: {self._cache_file}")
            else:
                logger.info(f"[SCRAPER] No cache file found at {self._cache_file}, starting with empty cache")
        except Exception as e:
            logger.error(f"[SCRAPER] Failed to load cache from file: {e}", exc_info=True)
            self.cache = {}  # Start with empty cache on error
    
    def _save_cache(self):
        """Save cache to JSON file"""
        try:
            # Convert datetime objects to ISO format strings for JSON serialization
            cache_data = {}
            for key, (estimate_value, timestamp) in self.cache.items():
                cache_data[key] = [estimate_value, timestamp.isoformat()]
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = self._cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self._cache_file)
            logger.debug(f"[SCRAPER] Saved {len(self.cache)} entries to cache file")
        except Exception as e:
            logger.error(f"[SCRAPER] Failed to save cache to file: {e}", exc_info=True)
    
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
            # Look for HomesEstimate pattern
            patterns = [
                (r'HomesEstimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'HomesEstimate pattern'),
                (r'Property estimate[^$]*\$?\s*([\d,]+)\s*([KMkm]?)\s*-\s*\$?\s*([\d,]+)\s*([KMkm]?)', 'Property estimate pattern'),
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
                    val1_str, suffix1, val2_str, suffix2 = match.groups()
                    val1 = parse_value(val1_str, suffix1)
                    val2 = parse_value(val2_str, suffix2)
                    # Return (low, high) ensuring low < high
                    return (min(val1, val2), max(val1, val2))
            
        except Exception as e:
            logger.warning(f"Error extracting HomesEstimate range: {e}")
        
        return None
    
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
    
    async def scrape_sold_properties(self, property_link: str) -> list[float]:
        """
        Scrape sold properties from "Nearby Sold Properties" section.
        Returns list of sold prices (floats).
        """
        if not property_link:
            return []
        
        logger.info(f"[SCRAPER] Starting sold properties scrape for: {property_link}")
        
        # On Windows, use sync API in thread pool
        if sys.platform == 'win32':
            logger.info(f"[SCRAPER] Using sync Playwright API in thread pool (Windows workaround)")
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
            
            loop = asyncio.get_event_loop()
            try:
                sold_prices = await loop.run_in_executor(
                    self._executor, self._scrape_sold_properties_sync, property_link
                )
                return sold_prices
            except Exception as e:
                logger.error(f"[SCRAPER] Error in thread pool execution: {e}", exc_info=True)
                return []
        
        # Non-Windows: use async API
        sold_prices = []
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
                
                await asyncio.sleep(2)
                
                # Find "Nearby Sold Properties" section
                page_text = await page.text_content('body') or ''
                if 'Nearby Sold Properties' not in page_text and 'nearby sold' not in page_text.lower():
                    logger.warning(f"[SCRAPER] 'Nearby Sold Properties' section not found")
                    return sold_prices
                
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
                await asyncio.sleep(2)
                
                # Paginate and collect prices
                max_clicks = 50
                click_count = 0
                
                while click_count < max_clicks:
                    # Extract prices from current view
                    page_html = await page.content()
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
                            except (ValueError, IndexError):
                                continue
                    
                    # Find next button
                    next_button = None
                    selectors = [
                        'button[aria-label*="next" i]',
                        'button[aria-label*=">" i]',
                        'button:has-text(">")',
                        '[class*="next"]',
                        '[class*="arrow-right"]',
                    ]
                    
                    for selector in selectors:
                        try:
                            next_button = await page.query_selector(selector)
                            if next_button:
                                is_disabled = await next_button.get_attribute('disabled') or \
                                            await next_button.get_attribute('aria-disabled') == 'true'
                                if is_disabled:
                                    next_button = None
                                    break
                                break
                        except Exception:
                            continue
                    
                    if not next_button:
                        break
                    
                    # Click next
                    try:
                        await next_button.click()
                        await asyncio.sleep(2)
                        click_count += 1
                    except Exception as e:
                        logger.warning(f"[SCRAPER] Failed to click next: {e}")
                        break
                
                logger.info(f"[SCRAPER] Collected {len(sold_prices)} sold prices")
                
            finally:
                await page.close()
                await context.close()
                
        except Exception as e:
            logger.error(f"[SCRAPER] Error scraping sold properties: {e}", exc_info=True)
        
        return sold_prices
    
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

async def scrape_property_estimate(property_link: str) -> Optional[float]:
    """
    Convenience function to scrape property estimate.
    This is the main function to use from outside this module.
    """
    # Ensure logger is initialized
    logger.info(f"[SCRAPER] scrape_property_estimate called for: {property_link}")
    _scraper_file_handler.flush()
    scraper = get_scraper()
    return await scraper.scrape_homes_estimate(property_link)

async def scrape_sold_properties(property_link: str) -> list[float]:
    """
    Convenience function to scrape sold properties.
    Returns list of sold prices from "Nearby Sold Properties" section.
    """
    logger.info(f"[SCRAPER] scrape_sold_properties called for: {property_link}")
    _scraper_file_handler.flush()
    scraper = get_scraper()
    return await scraper.scrape_sold_properties(property_link)

