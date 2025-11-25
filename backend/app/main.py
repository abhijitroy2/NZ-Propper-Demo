from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import List
from pydantic import BaseModel, HttpUrl
import io
import logging
import atexit
import sys
import asyncio
from pathlib import Path
import re

# Fix Windows asyncio subprocess issue for Playwright
# Note: In Python 3.12+, Windows event loops should support subprocess by default
# But we'll set the policy explicitly for compatibility
if sys.platform == 'win32':
    # Use nest_asyncio to allow nested event loops (workaround for subprocess issues)
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass  # nest_asyncio not installed, continue without it
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

from .models import ProcessResponse, CalculationResult
from .utils.file_parser import parse_file
from .utils.duplicate_handler import remove_duplicates
from .utils.property_scraper import get_scraper, scrape_property_data
from .calculator import FlipCalculator

# Configure logging to file and console
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "app.log"

# Create file handler with immediate flushing
file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
# Force immediate flushing to disk
file_handler.stream.reconfigure(line_buffering=True)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
))

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_file.absolute()}")

app = FastAPI(title="NZ PROPPER - Property Flip Calculator", version="1.0.0")

# Ensure Windows event loop policy is set on startup
@app.on_event("startup")
async def startup_event():
    """Ensure Windows event loop policy is set before any async operations"""
    if sys.platform == 'win32':
        try:
            loop = asyncio.get_running_loop()
            logger.info(f"[STARTUP] Event loop type: {type(loop).__name__}")
            # Try to set ProactorEventLoop policy (supports subprocess better)
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                logger.info("[STARTUP] Set WindowsProactorEventLoopPolicy")
            except AttributeError:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                logger.info("[STARTUP] Set WindowsSelectorEventLoopPolicy (fallback)")
        except RuntimeError:
            # No running loop yet, set policy for future loops
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                logger.info("[STARTUP] Set WindowsProactorEventLoopPolicy (no running loop)")
            except AttributeError:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                logger.info("[STARTUP] Set WindowsSelectorEventLoopPolicy (no running loop, fallback)")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend build) - must be after CORS middleware
# Check if static directory exists (for unified deployment)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Mounted static files from: {static_dir.absolute()}")
else:
    logger.warning(f"Static directory not found: {static_dir.absolute()} - frontend may not be available")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "NZ PROPPER API"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload and parse CSV/Excel file.
    Returns parsed properties data.
    """
    try:
        # Read file content
        contents = await file.read()
        
        # Parse file
        properties = parse_file(contents, file.filename)
        
        return {
            "success": True,
            "filename": file.filename,
            "properties_count": len(properties),
            "properties": properties[:10]  # Return first 10 for preview
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calculate")
async def calculate_properties(file: UploadFile = File(...)):
    """
    Process uploaded file, remove duplicates, and calculate flip values.
    Returns results with all calculations.
    """
    try:
        # Read and parse file
        contents = await file.read()
        properties = parse_file(contents, file.filename)
        
        # Remove duplicates
        deduplicated, duplicates_removed = remove_duplicates(properties)
        
        # Calculate for each property (using async version for web scraping support)
        results: List[CalculationResult] = []
        for prop in deduplicated:
            result = await FlipCalculator.calculate_async(prop)
            results.append(result)
        
        # Calculate summary stats
        good_deals_count = sum(1 for r in results if r.is_good_deal)
        stress_sales_count = sum(1 for r in results if r.has_stress_keywords)
        
        response = ProcessResponse(
            results=results,
            total_properties=len(results),
            good_deals_count=good_deals_count,
            stress_sales_count=stress_sales_count,
            duplicates_removed=duplicates_removed
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AnalyzeSingleRequest(BaseModel):
    """Request model for single property analysis"""
    url: str


@app.post("/api/analyze-single")
async def analyze_single_property(request: AnalyzeSingleRequest):
    """
    Analyze a single property from TradeMe URL.
    Scrapes property details, performs flip calculations, and returns result with rental yield.
    """
    try:
        url = request.url.strip()
        
        # Validate URL format (basic validation)
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Invalid URL format. URL must start with http:// or https://")
        
        # Check if it's a TradeMe URL (optional, but helpful)
        if 'trademe.co.nz' not in url.lower():
            logger.warning(f"URL does not appear to be a TradeMe URL: {url}")
        
        logger.info(f"[API] Analyzing single property from URL: {url}")
        
        # Scrape property data
        scraper = get_scraper()
        scrape_result = await scrape_property_data(url)
        
        # Extract property details from scrape result
        property_data = {
            "Property Link": url,
            "Property Address": scrape_result.property_address,
            "Property Title": scrape_result.property_title,
            "Price": scrape_result.price,
            "Bedrooms": scrape_result.bedrooms,
            "Bathrooms": scrape_result.bathrooms,
            "Area": scrape_result.area,
        }
        
        # Try to extract more details from the page if needed
        # For now, we'll use what we have and let the calculator handle defaults
        
        # Calculate flip values
        result = await FlipCalculator.calculate_async(property_data)
        
        # Add rental yield information from scrape result
        result.rental_yield_percentage = scrape_result.rental_yield_percentage
        result.rental_yield_range = scrape_result.rental_yield_range
        
        logger.info(f"[API] Analysis complete. Profit: ${result.profit:,.2f}, Rental Yield: {result.rental_yield_percentage}%")
        
        return {"result": result}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error analyzing single property: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing property: {str(e)}")


# Serve frontend index.html for React Router (catch-all route)
# This must be last to not interfere with API routes
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """
    Serve frontend static files. For SPA routing, return index.html for non-API routes.
    """
    # Don't serve frontend for API routes
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Check if static directory exists
    static_dir = Path(__file__).parent.parent / "static"
    index_file = static_dir / "index.html"
    
    if index_file.exists():
        # If requesting a file that exists, serve it
        requested_file = static_dir / full_path
        if requested_file.exists() and requested_file.is_file():
            return FileResponse(str(requested_file))
        # Otherwise serve index.html for SPA routing
        return FileResponse(str(index_file))
    else:
        raise HTTPException(status_code=404, detail="Frontend not available")


# Cleanup browser on shutdown
@atexit.register
def cleanup_scraper():
    """Cleanup browser instance on application shutdown"""
    scraper = get_scraper()
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(scraper.close())
        else:
            loop.run_until_complete(scraper.close())
    except Exception as e:
        logger.warning(f"Error cleaning up scraper: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


