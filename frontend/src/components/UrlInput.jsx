import React, { useState } from 'react';

const UrlInput = ({ onUrlSubmit, disabled }) => {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');

  const validateUrl = (urlString) => {
    if (!urlString.trim()) {
      return 'Please enter a TradeMe URL';
    }
    
    // Basic URL validation
    try {
      const urlObj = new URL(urlString);
      if (!urlObj.protocol.startsWith('http')) {
        return 'URL must start with http:// or https://';
      }
      return null;
    } catch (e) {
      return 'Please enter a valid URL';
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');
    
    const validationError = validateUrl(url);
    if (validationError) {
      setError(validationError);
      return;
    }

    onUrlSubmit(url.trim());
  };

  const handleChange = (e) => {
    setUrl(e.target.value);
    if (error) {
      setError(''); // Clear error when user starts typing
    }
  };

  return (
    <div style={{ marginBottom: '2rem' }}>
      <form onSubmit={handleSubmit}>
        <div
          style={{
            border: '2px solid #ccc',
            borderRadius: '8px',
            padding: '1.5rem',
            backgroundColor: '#fff',
            opacity: disabled ? 0.6 : 1,
          }}
        >
          <label
            htmlFor="trademe-url"
            style={{
              display: 'block',
              fontSize: '1.1rem',
              marginBottom: '0.75rem',
              color: '#333',
              fontWeight: '500',
            }}
          >
            TradeMe Property URL
          </label>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
            <input
              id="trademe-url"
              type="url"
              value={url}
              onChange={handleChange}
              placeholder="https://www.trademe.co.nz/a/property/residential/sale/..."
              disabled={disabled}
              style={{
                flex: 1,
                padding: '0.75rem',
                fontSize: '1rem',
                border: `1px solid ${error ? '#f44336' : '#ccc'}`,
                borderRadius: '4px',
                outline: 'none',
                transition: 'border-color 0.3s ease',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#2196F3';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = error ? '#f44336' : '#ccc';
              }}
            />
            <button
              type="submit"
              disabled={disabled || !url.trim()}
              style={{
                padding: '0.75rem 2rem',
                fontSize: '1rem',
                backgroundColor: disabled || !url.trim() ? '#ccc' : '#2196F3',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: disabled || !url.trim() ? 'not-allowed' : 'pointer',
                fontWeight: '500',
                transition: 'background-color 0.3s ease',
              }}
              onMouseEnter={(e) => {
                if (!disabled && url.trim()) {
                  e.target.style.backgroundColor = '#1976D2';
                }
              }}
              onMouseLeave={(e) => {
                if (!disabled && url.trim()) {
                  e.target.style.backgroundColor = '#2196F3';
                }
              }}
            >
              Analyze
            </button>
          </div>
          {error && (
            <p
              style={{
                color: '#f44336',
                fontSize: '0.9rem',
                marginTop: '0.5rem',
                marginBottom: 0,
              }}
            >
              {error}
            </p>
          )}
          <p
            style={{
              color: '#666',
              fontSize: '0.85rem',
              marginTop: '0.75rem',
              marginBottom: 0,
            }}
          >
            Paste a TradeMe property listing URL to analyze a single property
          </p>
        </div>
      </form>
    </div>
  );
};

export default UrlInput;

