from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List
import io
import logging
import atexit
import sys
import asyncio
from pathlib import Path

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
from .utils.property_scraper import get_scraper
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


