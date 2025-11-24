import pandas as pd
import io
from typing import List, Dict, Any
from ..models import PropertyInput


def parse_file(file_content: bytes, filename: str) -> List[Dict[str, Any]]:
    """
    Parse CSV or Excel file and return list of dictionaries.
    Hardcoded column headers matching the expected CSV structure.
    """
    # Expected column names (hardcoded)
    expected_columns = [
        "Date (GMT)",
        "Job Link",
        "Origin URL",
        "Auckland Property Listings Limit",
        "Position",
        "Open Home Status",
        "Agent Name",
        "Agency Name",
        "Listing Date",
        "Property Title",
        "Property Address",
        "Bedrooms",
        "Bathrooms",
        "Area",
        "Price",
        "Property Link"
    ]
    
    try:
        # Determine file type and parse
        if filename.endswith('.csv'):
            # Try multiple encodings, starting with Windows-1252 (common for Windows CSV exports)
            # since the error shows byte 0x92 which is a Windows-1252 smart quote
            encodings = ['windows-1252', 'cp1252', 'latin-1', 'iso-8859-1', 'utf-8']
            
            df = None
            last_error = None
            
            for encoding in encodings:
                try:
                    # Reset file pointer for each attempt
                    file_obj = io.BytesIO(file_content)
                    df = pd.read_csv(file_obj, encoding=encoding, on_bad_lines='skip', engine='python')
                    break  # Successfully read, exit loop
                except (UnicodeDecodeError, UnicodeError) as e:
                    last_error = e
                    continue  # Try next encoding
                except Exception as e:
                    # Check if it's an encoding-related error by examining the message
                    error_str = str(e).lower()
                    if any(keyword in error_str for keyword in ['codec', 'decode', 'encoding', 'utf-8', 'invalid start byte', '0x92']):
                        last_error = e
                        continue  # Try next encoding
                    else:
                        # Re-raise if it's not an encoding error
                        raise
            
            if df is None:
                raise ValueError(f"Could not decode file with any supported encoding. Last error: {str(last_error)}")
                    
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError(f"Unsupported file type: {filename}")
        
        # Normalize column names (strip whitespace, handle case)
        df.columns = df.columns.str.strip()
        
        # Check for required columns
        missing_columns = []
        for col in expected_columns:
            if col not in df.columns:
                missing_columns.append(col)
        
        if missing_columns:
            # Log warning but continue - we'll handle missing columns gracefully
            print(f"Warning: Missing columns: {missing_columns}")
        
        # Fill missing columns with None
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None
        
        # Select only expected columns and fill NaN with empty string
        df = df[expected_columns].fillna("")
        
        # Convert numeric columns that should be strings to strings
        # This handles cases where pandas reads "3" as 3.0 (float) or 3 (int)
        string_columns = ["Bedrooms", "Bathrooms", "Area", "Price"]
        for col in string_columns:
            if col in df.columns:
                # Convert to string, handling NaN, int, and float values
                def convert_to_string(x):
                    if pd.isna(x) or x == "":
                        return ""
                    if isinstance(x, float) and x.is_integer():
                        return str(int(x))
                    if isinstance(x, (int, float)):
                        return str(x)
                    return str(x)
                
                df[col] = df[col].apply(convert_to_string)
        
        # Convert to list of dictionaries
        properties = df.to_dict('records')
        
        return properties
    
    except Exception as e:
        raise ValueError(f"Error parsing file: {str(e)}")

