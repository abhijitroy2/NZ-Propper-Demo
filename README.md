# NZ PROPPER - Property Flip Calculator

A web application for analyzing property flip opportunities in New Zealand. Upload CSV or Excel files containing property listings, and the app will calculate potential profit, identify good deals, and highlight stress sales.

## Features

- **File Upload**: Support for CSV and Excel (.xlsx, .xls) files
- **Duplicate Detection**: Automatically removes duplicate properties by address, keeping the latest entry
- **Flip Calculator**: Calculates profit based on:
  - Potential Purchase Price (from asking price or default $650k)
  - Renovation Budget (15% of purchase price)
  - Holding Costs (4% of purchase price)
  - Disposal Costs (2.5% of sale price)
  - Contingency (1.5% of renovation budget)
  - Potential Sale Price ($730k fixed)
- **Good Deal Detection**: Highlights properties where profit > 20% of purchase price
- **Stress Sale Detection**: Identifies properties with stress keywords in title
- **Visual Highlighting**: Color-coded results (green for good deals, orange for stress sales)
- **Export Functionality**: Export results to CSV

## Project Structure

```
NZ-PROPPER/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── models.py            # Pydantic models
│   │   ├── calculator.py        # Flip calculator logic
│   │   └── utils/
│   │       ├── file_parser.py   # CSV/Excel parsing
│   │       └── duplicate_handler.py  # Duplicate detection
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/        # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── FileUpload.jsx
│   │   │   ├── ResultsTable.jsx
│   │   │   └── CalculatorMode.jsx
│   │   └── services/
│   │       └── api.js
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── Dockerfile          # Unified Dockerfile for Railway deployment
├── railway.json        # Railway deployment configuration
└── README.md
```

## CSV Format

The application expects CSV files with the following columns (hardcoded):

- `Date (GMT)` - Used for duplicate detection
- `Property Address` - Used for duplicate detection (grouping key)
- `Property Title` - Used for stress keyword detection
- `Price` - Used to extract asking price (formats: "Asking price $599,900", "Auction on...", etc.)
- Other columns: Job Link, Origin URL, Auckland Property Listings Limit, Position, Open Home Status, Agent Name, Agency Name, Listing Date, Bedrooms, Bathrooms, Area, Property Link

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (optional, for containerized development)

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Run the backend server:
```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

### Docker Setup

1. Build and start all services:
```bash
docker-compose up --build
```

2. Access the application:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

## API Endpoints

### `GET /api/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "NZ PROPPER API"
}
```

### `POST /api/upload`
Upload and parse a CSV/Excel file.

**Request:** Multipart form data with `file` field

**Response:**
```json
{
  "success": true,
  "filename": "properties.csv",
  "properties_count": 100,
  "properties": [...]
}
```

### `POST /api/calculate`
Process uploaded file, remove duplicates, and calculate flip values.

**Request:** Multipart form data with `file` field

**Response:**
```json
{
  "results": [
    {
      "property_address": "123 Main St",
      "property_title": "Must Sell Property",
      "price": "Asking price $599,900",
      "potential_purchase_price": 599900,
      "renovation_budget": 89985,
      "holding_costs": 23996,
      "disposal_costs": 18250,
      "contingency": 1349.78,
      "potential_sale_price": 730000,
      "profit": 12519.22,
      "is_good_deal": false,
      "has_stress_keywords": true
    }
  ],
  "total_properties": 100,
  "good_deals_count": 15,
  "stress_sales_count": 8,
  "duplicates_removed": 5
}
```

## Deployment

### Railway Deployment (Unified - Single Service)

The project is configured for unified deployment on Railway, where both frontend and backend run in a single service with one URL.

1. **Connect GitHub Repository to Railway:**
   - Go to [Railway](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository: `NZ-Propper-Demo`

2. **Railway will automatically:**
   - Detect the `Dockerfile` at the root
   - Build the unified container (frontend + backend)
   - Deploy to a single service
   - Provide one URL for the entire application

3. **The unified deployment:**
   - Builds the React frontend during Docker build
   - Serves frontend static files via FastAPI
   - All API routes are under `/api/*`
   - Frontend routes are handled by FastAPI's catch-all route
   - Single port, single URL, single service

The `railway.json` file contains the deployment configuration for the unified service.

### Environment Variables

For production, set the following environment variables:

- `PORT`: Port for the backend server (Railway sets this automatically)
- `VITE_API_URL`: Backend API URL for the frontend (if different from default)

## Calculator Logic

### Profit Calculation

```
Profit = Potential Sale Price 
       - Potential Purchase Price 
       - Renovation Budget 
       - Holding Costs 
       - Disposal Costs 
       - Contingency
```

### Component Calculations

- **Potential Purchase Price**: Extracted from "Price" column if contains "Asking price", else defaults to $650,000
- **Renovation Budget**: 15% of Potential Purchase Price
- **Holding Costs**: 4% of Potential Purchase Price
- **Disposal Costs**: 2.5% of Potential Sale Price
- **Contingency**: 1.5% of Renovation Budget
- **Potential Sale Price**: Fixed at $730,000

### Good Deal Threshold

A property is considered a "good deal" if:
```
Profit > 20% of Potential Purchase Price
```

### Stress Keywords

Properties with the following keywords in the title are flagged as stress sales:
- "must sell"
- "must be sold"
- "urgent sale"
- "mortgagee"
- "auction"
- "foreclosure"
- "distressed"
- "vendor relocated"
- "relationship split"

## Technology Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React + Vite
- **File Parsing**: pandas
- **Deployment**: Railway

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.


