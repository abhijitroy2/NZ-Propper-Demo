import React, { useState } from 'react';
import CalculatorMode from './components/CalculatorMode';
import FileUpload from './components/FileUpload';
import UrlInput from './components/UrlInput';
import ResultsTable from './components/ResultsTable';
import { calculateProperties, analyzeSingleProperty } from './services/api';
import './App.css';

function App() {
  const [mode, setMode] = useState('flip');
  const [file, setFile] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileSelect = async (selectedFile) => {
    setFile(selectedFile);
    setError(null);
    setResults(null);

    if (mode === 'rental') {
      return; // Rental mode not implemented yet
    }

    setLoading(true);
    try {
      const data = await calculateProperties(selectedFile);
      setResults(data.results);
    } catch (err) {
      setError(err.message || 'An error occurred while processing the file');
    } finally {
      setLoading(false);
    }
  };

  const handleUrlSubmit = async (url) => {
    setError(null);
    setResults(null);
    setFile(null);

    setLoading(true);
    try {
      const data = await analyzeSingleProperty(url);
      // API returns { result: CalculationResult }, convert to array for ResultsTable
      setResults([data.result]);
    } catch (err) {
      setError(err.message || 'An error occurred while analyzing the property');
    } finally {
      setLoading(false);
    }
  };

  const handleModeChange = (newMode) => {
    setMode(newMode);
    setFile(null);
    setResults(null);
    setError(null);
  };

  return (
    <div className="App">
      <header style={{ backgroundColor: '#2196F3', color: 'white', padding: '2rem', textAlign: 'center' }}>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>NZ PROPPER</h1>
        <p style={{ fontSize: '1.2rem' }}>Property Flip Calculator</p>
      </header>

      <main style={{ maxWidth: '1400px', margin: '0 auto', padding: '2rem' }}>
        <CalculatorMode mode={mode} onModeChange={handleModeChange} />

        {mode === 'rental' ? (
          <div
            style={{
              padding: '3rem',
              textAlign: 'center',
              backgroundColor: '#fff',
              borderRadius: '8px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            }}
          >
            <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem', color: '#666' }}>
              Under Construction
            </h2>
            <p style={{ color: '#999' }}>Rental mode is currently under development.</p>
          </div>
        ) : mode === 'flip-or-rent' ? (
          <>
            <UrlInput onUrlSubmit={handleUrlSubmit} disabled={loading} />

            {loading && (
              <div style={{ textAlign: 'center', padding: '2rem' }}>
                <p style={{ fontSize: '1.1rem', color: '#666' }}>
                  Analyzing property... This may take a minute.
                </p>
              </div>
            )}

            {error && (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: '#ffebee',
                  color: '#c62828',
                  borderRadius: '8px',
                  marginBottom: '1rem',
                }}
              >
                <strong>Error:</strong> {error}
              </div>
            )}

            {results && results.length > 0 && (
              <ResultsTable
                results={results}
                summary={{
                  total_properties: results.length,
                  good_deals_count: results.filter((r) => r.is_good_deal).length,
                  stress_sales_count: results.filter((r) => r.has_stress_keywords).length,
                  duplicates_removed: 0,
                }}
              />
            )}
          </>
        ) : (
          <>
            <FileUpload onFileSelect={handleFileSelect} disabled={loading} />

            {loading && (
              <div style={{ textAlign: 'center', padding: '2rem' }}>
                <p style={{ fontSize: '1.1rem', color: '#666' }}>Processing file...</p>
              </div>
            )}

            {error && (
              <div
                style={{
                  padding: '1rem',
                  backgroundColor: '#ffebee',
                  color: '#c62828',
                  borderRadius: '8px',
                  marginBottom: '1rem',
                }}
              >
                <strong>Error:</strong> {error}
              </div>
            )}

            {results && results.length > 0 && (
              <ResultsTable
                results={results}
                summary={{
                  total_properties: results.length,
                  good_deals_count: results.filter((r) => r.is_good_deal).length,
                  stress_sales_count: results.filter((r) => r.has_stress_keywords).length,
                  duplicates_removed: 0, // This would come from the API response
                }}
              />
            )}

            {results && results.length === 0 && (
              <div
                style={{
                  padding: '2rem',
                  textAlign: 'center',
                  backgroundColor: '#fff',
                  borderRadius: '8px',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                }}
              >
                <p style={{ color: '#666' }}>No properties found in the file.</p>
              </div>
            )}
          </>
        )}
      </main>

      <footer style={{ textAlign: 'center', padding: '2rem', color: '#666', marginTop: '3rem' }}>
        <p>NZ PROPPER - Property Flip Calculator v1.0.0</p>
      </footer>
    </div>
  );
}

export default App;


